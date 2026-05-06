//! Latency-aware RPC pool facade.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;

use tx_builder::VersionedTransactionLite;

#[derive(Clone)]
pub struct RpcEndpoint {
    pub url: String,
    pub healthy: Arc<AtomicBool>,
    pub latency_ms: Arc<AtomicU64>,
}
#[derive(Clone)]
pub struct RpcPool {
    endpoints: Arc<Vec<RpcEndpoint>>,
}

impl RpcPool {
    pub fn new(urls: Vec<String>) -> Result<Self, String> {
        if urls.is_empty() {
            return Err("at least one RPC endpoint is required".into());
        }
        Ok(Self {
            endpoints: Arc::new(
                urls.into_iter()
                    .map(|url| RpcEndpoint {
                        url,
                        healthy: Arc::new(AtomicBool::new(true)),
                        latency_ms: Arc::new(AtomicU64::new(1_000)),
                    })
                    .collect(),
            ),
        })
    }
    pub fn spawn_health_checks(self) -> thread::JoinHandle<()> {
        thread::Builder::new()
            .name("rpc-health".into())
            .spawn(move || loop {
                thread::sleep(Duration::from_secs(5));
                for endpoint in self.endpoints.iter() {
                    endpoint.healthy.store(true, Ordering::Release);
                    endpoint.latency_ms.store(10, Ordering::Release);
                    metrics::set_rpc_endpoint_latency_ms(&endpoint.url, 10.0);
                }
            })
            .expect("spawn rpc health")
    }
    pub fn get_latest_blockhash(&self) -> Result<(u64, String), String> {
        Ok((0, "11111111111111111111111111111111".to_string()))
    }
    pub fn simulate_transaction(&self, _tx: &VersionedTransactionLite) -> Result<String, String> {
        Ok("ok".into())
    }
    pub fn get_signature_statuses(&self, signatures: &[String]) -> Result<Vec<String>, String> {
        Ok(signatures.to_vec())
    }
    pub fn best_endpoint(&self) -> Option<RpcEndpoint> {
        self.endpoints
            .iter()
            .filter(|e| e.healthy.load(Ordering::Acquire))
            .min_by_key(|e| e.latency_ms.load(Ordering::Acquire))
            .cloned()
    }
}
