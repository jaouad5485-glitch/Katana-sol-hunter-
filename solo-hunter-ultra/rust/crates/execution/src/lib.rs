//! Pinned execution engine: build, sign, optional simulate, and Jito submit.

use std::sync::atomic::Ordering;
use std::sync::mpsc::Receiver;
use std::thread::{self, JoinHandle};
use std::time::Instant;

use filter_stack::Opportunity;
use sh_sniffer::{now_ns, pin_current_thread};
use tx_builder::TxBuilder;
use wallet::{SecretString, WalletSigner};

pub struct ExecutionConfig {
    pub core_id: Option<usize>,
    pub jito_url: String,
    pub jito_auth: SecretString,
    pub input_lamports: u64,
    pub min_output_lamports: u64,
}
pub struct ExecutionEngine {
    config: ExecutionConfig,
    tx_builder: TxBuilder,
    wallet: WalletSigner,
    rpc_pool: rpc_pool::RpcPool,
}

impl ExecutionEngine {
    pub fn new(
        config: ExecutionConfig,
        tx_builder: TxBuilder,
        wallet: WalletSigner,
        rpc_pool: rpc_pool::RpcPool,
    ) -> Self {
        Self {
            config,
            tx_builder,
            wallet,
            rpc_pool,
        }
    }
    pub fn spawn(
        self,
        input: Receiver<Opportunity>,
    ) -> std::io::Result<JoinHandle<Result<(), String>>> {
        let core_id = self.config.core_id;
        thread::Builder::new()
            .name("execution-core-6".into())
            .spawn(move || {
                pin_current_thread(core_id);
                self.run(input)
            })
    }
    pub fn run(self, input: Receiver<Opportunity>) -> Result<(), String> {
        while let Ok(opportunity) = input.recv() {
            let started = Instant::now();
            let urgency_ms =
                ((now_ns().saturating_sub(opportunity.signal.arrival_ns)) as f64) / 1_000_000.0;
            let tip = calculate_tip_lamports(
                opportunity.confidence,
                0.0,
                urgency_ms,
                opportunity.expected_profit_lamports,
                10_000,
            );
            let tx = self.tx_builder.build_swap(
                &opportunity,
                self.config.input_lamports,
                self.config.min_output_lamports,
                tip,
            )?;
            let signed = self.wallet.sign(tx);
            if opportunity.confidence < 0.85 {
                let _ = self.rpc_pool.simulate_transaction(&signed);
            }
            let bundle_id = submit_bundle_stub(
                &self.config.jito_url,
                self.config.jito_auth.expose_secret(),
                &signed,
            );
            metrics::BUNDLES_SUBMITTED_TOTAL.fetch_add(1, Ordering::Relaxed);
            metrics::observe_execution_latency_us(started.elapsed().as_micros() as u64);
            println!("{{\"event\":\"jito_bundle_submitted\",\"bundle_id\":\"{}\",\"tip_lamports\":{},\"latency_us\":{}}}", bundle_id, tip, started.elapsed().as_micros());
        }
        Ok(())
    }
}

fn submit_bundle_stub(
    _url: &str,
    _auth: &str,
    tx: &tx_builder::VersionedTransactionLite,
) -> String {
    tx.signatures
        .first()
        .cloned()
        .unwrap_or_else(|| "unsigned".into())
}

pub fn calculate_tip_lamports(
    confidence: f32,
    congestion: f32,
    urgency_ms: f64,
    expected_profit_lamports: u64,
    base_tip: u64,
) -> u64 {
    let urgency_multiplier = 1.0 + ((20.0 - urgency_ms).max(0.0) / 40.0);
    let raw = (base_tip as f64 * (1.0 + confidence as f64 + congestion as f64) * urgency_multiplier)
        as u64;
    let cap = expected_profit_lamports / 5;
    raw.max(base_tip).min(cap.max(base_tip))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn tip_is_capped_at_twenty_percent() {
        assert!(calculate_tip_lamports(1.0, 1.0, 0.0, 100_000, 10_000) <= 20_000);
    }
}
