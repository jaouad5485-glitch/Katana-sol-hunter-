//! Minimal metrics registry and Prometheus text endpoint.

use std::collections::HashMap;
use std::io::Write;
use std::net::{SocketAddr, TcpListener};
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use std::thread;

pub static SHREDS_RECEIVED_TOTAL: AtomicU64 = AtomicU64::new(0);
pub static SIGNALS_EXTRACTED_TOTAL: AtomicU64 = AtomicU64::new(0);
pub static BUNDLES_SUBMITTED_TOTAL: AtomicU64 = AtomicU64::new(0);
pub static OPEN_POSITIONS: AtomicI64 = AtomicI64::new(0);

static FILTERED: OnceLock<Mutex<HashMap<(String, String), u64>>> = OnceLock::new();
static FILTER_LATENCY_US: OnceLock<Mutex<Vec<u64>>> = OnceLock::new();
static EXECUTION_LATENCY_US: OnceLock<Mutex<Vec<u64>>> = OnceLock::new();
static RPC_LATENCY_MS: OnceLock<Mutex<HashMap<String, f64>>> = OnceLock::new();

pub fn inc_filtered(layer: &str, reason: &str) {
    let mut map = FILTERED
        .get_or_init(Default::default)
        .lock()
        .expect("filtered lock");
    *map.entry((layer.to_string(), reason.to_string()))
        .or_default() += 1;
}

pub fn observe_filter_latency_us(value: u64) {
    FILTER_LATENCY_US
        .get_or_init(Default::default)
        .lock()
        .expect("lat lock")
        .push(value);
}
pub fn observe_execution_latency_us(value: u64) {
    EXECUTION_LATENCY_US
        .get_or_init(Default::default)
        .lock()
        .expect("exec lock")
        .push(value);
}
pub fn set_rpc_endpoint_latency_ms(endpoint: &str, value: f64) {
    RPC_LATENCY_MS
        .get_or_init(Default::default)
        .lock()
        .expect("rpc lock")
        .insert(endpoint.to_string(), value);
}

pub fn spawn_prometheus(
    addr: SocketAddr,
) -> std::io::Result<thread::JoinHandle<std::io::Result<()>>> {
    thread::Builder::new()
        .name("prometheus-metrics".into())
        .spawn(move || {
            let listener = TcpListener::bind(addr)?;
            for stream in listener.incoming() {
                let mut stream = stream?;
                let body = render();
                let response = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: text/plain\r\ncontent-length: {}\r\n\r\n{}",
                    body.len(),
                    body
                );
                stream.write_all(response.as_bytes())?;
            }
            Ok(())
        })
}

pub fn render() -> String {
    let mut out = String::new();
    out.push_str(&format!(
        "shreds_received_total {}\n",
        SHREDS_RECEIVED_TOTAL.load(Ordering::Relaxed)
    ));
    out.push_str(&format!(
        "signals_extracted_total {}\n",
        SIGNALS_EXTRACTED_TOTAL.load(Ordering::Relaxed)
    ));
    out.push_str(&format!(
        "bundles_submitted_total {}\n",
        BUNDLES_SUBMITTED_TOTAL.load(Ordering::Relaxed)
    ));
    out.push_str(&format!(
        "open_positions {}\n",
        OPEN_POSITIONS.load(Ordering::Relaxed)
    ));
    if let Some(map) = FILTERED.get() {
        for ((layer, reason), value) in map.lock().expect("filtered lock").iter() {
            out.push_str(&format!(
                "opportunities_filtered_total{{layer=\"{}\",reason=\"{}\"}} {}\n",
                layer, reason, value
            ));
        }
    }
    if let Some(values) = FILTER_LATENCY_US.get() {
        for value in values.lock().expect("lat lock").iter() {
            out.push_str(&format!("filter_latency_us {}\n", value));
        }
    }
    if let Some(values) = EXECUTION_LATENCY_US.get() {
        for value in values.lock().expect("exec lock").iter() {
            out.push_str(&format!("execution_latency_us {}\n", value));
        }
    }
    if let Some(map) = RPC_LATENCY_MS.get() {
        for (endpoint, value) in map.lock().expect("rpc lock").iter() {
            out.push_str(&format!(
                "rpc_endpoint_latency_ms{{endpoint=\"{}\"}} {}\n",
                endpoint, value
            ));
        }
    }
    out
}
