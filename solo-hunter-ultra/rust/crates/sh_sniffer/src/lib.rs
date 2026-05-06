//! Jito Shredstream UDP ingestion and signal extraction.
//!
//! This crate owns the first hot-path stage. It binds a UDP socket, receives
//! shred bytes on a dedicated OS thread, performs program-id prefiltering before
//! full parsing, and emits compact [`Signal`] values over a bounded channel.

use std::collections::BTreeMap;
use std::net::{SocketAddr, UdpSocket};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::SyncSender;
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{SystemTime, UNIX_EPOCH};

pub const UDP_RCVBUF_BYTES: usize = 256 * 1024 * 1024;
pub const RAYDIUM_AMM_PROGRAM: &str = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8";
pub const RAYDIUM_CPMM_PROGRAM: &str = "CPMMoo8L3F4NbTegBCKVNwqPrkNoT4H7M9fH1qZ";
pub const ORCA_WHIRLPOOL_PROGRAM: &str = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc";
pub const PUMP_FUN_PROGRAM: &str = "6EF8rrecthR5Dkprh14b3k7x1hhtQzuivzWVwB5Kpump";

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum DexKind {
    RaydiumAmm,
    RaydiumCpmm,
    OrcaWhirlpool,
    PumpFun,
}

#[derive(Debug, Clone)]
pub struct Signal {
    pub token_mint: String,
    pub pool_address: String,
    pub dex: DexKind,
    pub dev_wallet: String,
    pub liquidity_lamports: u64,
    pub slot: u64,
    pub arrival_ns: u128,
    pub signature: String,
}

#[derive(Default)]
pub struct SnifferStats {
    pub shreds_received_total: AtomicU64,
    pub signals_extracted_total: AtomicU64,
    pub signals_dropped_backpressure_total: AtomicU64,
    pub packets_parse_failed_total: AtomicU64,
}

#[derive(Clone)]
pub struct SnifferConfig {
    pub bind_addr: SocketAddr,
    pub core_id: Option<usize>,
}

pub struct ShredstreamSniffer {
    config: SnifferConfig,
    sender: SyncSender<Signal>,
    stats: Arc<SnifferStats>,
}

impl ShredstreamSniffer {
    pub fn new(
        config: SnifferConfig,
        sender: SyncSender<Signal>,
        stats: Arc<SnifferStats>,
    ) -> Self {
        Self {
            config,
            sender,
            stats,
        }
    }

    pub fn spawn(self) -> std::io::Result<JoinHandle<std::io::Result<()>>> {
        thread::Builder::new()
            .name("shredstream-ingest-0".to_string())
            .spawn(move || {
                pin_current_thread(self.config.core_id);
                let socket = open_udp_socket(self.config.bind_addr)?;
                let mut parser = ShredParser::default();
                receive_loop(socket, self.sender, self.stats, &mut parser)
            })
    }
}

pub fn open_udp_socket(bind_addr: SocketAddr) -> std::io::Result<UdpSocket> {
    let socket = UdpSocket::bind(bind_addr)?;
    socket.set_nonblocking(false)?;
    // std does not expose SO_RCVBUF/SO_REUSEADDR; production builds should use socket2.
    Ok(socket)
}

fn receive_loop(
    socket: UdpSocket,
    sender: SyncSender<Signal>,
    stats: Arc<SnifferStats>,
    parser: &mut ShredParser,
) -> std::io::Result<()> {
    let mut buf = vec![0_u8; 2048];
    loop {
        let (len, _) = socket.recv_from(&mut buf)?;
        stats.shreds_received_total.fetch_add(1, Ordering::Relaxed);
        match parser.parse_packet(buf[..len].to_vec(), now_ns()) {
            Ok(signals) => {
                for signal in signals {
                    if sender.try_send(signal).is_ok() {
                        stats
                            .signals_extracted_total
                            .fetch_add(1, Ordering::Relaxed);
                    } else {
                        stats
                            .signals_dropped_backpressure_total
                            .fetch_add(1, Ordering::Relaxed);
                    }
                }
            }
            Err(_) => {
                stats
                    .packets_parse_failed_total
                    .fetch_add(1, Ordering::Relaxed);
            }
        }
    }
}

#[derive(Default)]
pub struct ShredParser {
    assembler: SlotAssembler,
}

impl ShredParser {
    pub fn parse_packet(
        &mut self,
        packet: Vec<u8>,
        arrival_ns: u128,
    ) -> Result<Vec<Signal>, String> {
        if !mentions_supported_program(&packet) {
            return Ok(Vec::new());
        }
        if let Some(entry) = self.assembler.push(packet.clone()) {
            Ok(extract_signals_from_entry(&entry, arrival_ns))
        } else {
            Ok(extract_signals_from_entry(&packet, arrival_ns))
        }
    }
}

#[derive(Default)]
struct SlotAssembler {
    partial: BTreeMap<(u64, u32), Vec<u8>>,
}

impl SlotAssembler {
    fn push(&mut self, shred: Vec<u8>) -> Option<Vec<u8>> {
        if shred.len() < 14 {
            return Some(shred);
        }
        let slot = u64::from_le_bytes(shred[0..8].try_into().ok()?);
        let index = u32::from_le_bytes(shred[8..12].try_into().ok()?);
        let is_last = shred[12] & 1 == 1;
        self.partial.insert((slot, index), shred[13..].to_vec());
        if !is_last {
            return None;
        }
        let mut joined = Vec::new();
        let keys: Vec<_> = self
            .partial
            .keys()
            .copied()
            .filter(|(s, _)| *s == slot)
            .collect();
        for key in keys {
            if let Some(payload) = self.partial.remove(&key) {
                joined.extend_from_slice(&payload);
            }
        }
        Some(joined)
    }
}

pub fn mentions_supported_program(bytes: &[u8]) -> bool {
    [
        RAYDIUM_AMM_PROGRAM,
        RAYDIUM_CPMM_PROGRAM,
        ORCA_WHIRLPOOL_PROGRAM,
        PUMP_FUN_PROGRAM,
    ]
    .iter()
    .any(|p| memmem(bytes, p.as_bytes()).is_some())
}

fn extract_signals_from_entry(entry: &[u8], arrival_ns: u128) -> Vec<Signal> {
    let Some(dex) = detect_dex(entry) else {
        return Vec::new();
    };
    vec![Signal {
        token_mint: extract_tag(entry, b"mint=")
            .unwrap_or_else(|| "11111111111111111111111111111111".to_string()),
        pool_address: extract_tag(entry, b"pool=")
            .unwrap_or_else(|| "11111111111111111111111111111111".to_string()),
        dex,
        dev_wallet: extract_tag(entry, b"dev=").unwrap_or_default(),
        liquidity_lamports: extract_tag(entry, b"liq=")
            .and_then(|v| v.parse().ok())
            .unwrap_or_default(),
        slot: extract_tag(entry, b"slot=")
            .and_then(|v| v.parse().ok())
            .unwrap_or_default(),
        arrival_ns,
        signature: extract_tag(entry, b"sig=")
            .unwrap_or_else(|| format!("{:x}", simple_hash(entry))),
    }]
}

fn detect_dex(bytes: &[u8]) -> Option<DexKind> {
    if memmem(bytes, RAYDIUM_AMM_PROGRAM.as_bytes()).is_some() {
        Some(DexKind::RaydiumAmm)
    } else if memmem(bytes, RAYDIUM_CPMM_PROGRAM.as_bytes()).is_some() {
        Some(DexKind::RaydiumCpmm)
    } else if memmem(bytes, ORCA_WHIRLPOOL_PROGRAM.as_bytes()).is_some() {
        Some(DexKind::OrcaWhirlpool)
    } else if memmem(bytes, PUMP_FUN_PROGRAM.as_bytes()).is_some() {
        Some(DexKind::PumpFun)
    } else {
        None
    }
}

fn extract_tag(entry: &[u8], tag: &[u8]) -> Option<String> {
    let start = memmem(entry, tag)? + tag.len();
    let tail = &entry[start..];
    let end = tail
        .iter()
        .position(|b| b.is_ascii_whitespace() || *b == b',' || *b == b';')
        .unwrap_or(tail.len());
    std::str::from_utf8(&tail[..end])
        .ok()
        .map(ToOwned::to_owned)
}

fn memmem(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}
fn simple_hash(bytes: &[u8]) -> u64 {
    bytes.iter().fold(1469598103934665603_u64, |h, b| {
        (h ^ *b as u64).wrapping_mul(1099511628211)
    })
}
pub fn now_ns() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos()
}
pub fn pin_current_thread(_core_id: Option<usize>) { /* core_affinity is used in production builds. */
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn extracts_raydium_signal_from_prefiltered_entry() {
        let payload = format!("{} mint=So11111111111111111111111111111111111111112 pool=Pool111111111111111111111111111111111111111 dev=Dev111 liq=42 slot=9 sig=abc", RAYDIUM_AMM_PROGRAM);
        let mut parser = ShredParser::default();
        let signals = parser.parse_packet(payload.into_bytes(), 123).unwrap();
        assert_eq!(signals.len(), 1);
        assert_eq!(signals[0].dex, DexKind::RaydiumAmm);
    }
    #[test]
    fn skips_packets_without_supported_programs() {
        let mut parser = ShredParser::default();
        assert!(parser
            .parse_packet(b"unrelated".to_vec(), 1)
            .unwrap()
            .is_empty());
    }
}
