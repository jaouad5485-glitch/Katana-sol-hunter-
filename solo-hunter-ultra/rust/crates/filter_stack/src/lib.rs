//! Synchronous cascading filter stack pinned to evaluation cores.

use std::collections::HashSet;
use std::sync::mpsc::{Receiver, SyncSender};
use std::thread::{self, JoinHandle};
use std::time::Instant;

use intelligence::{FeatureContext, FeatureEngine, Predictor};
use sh_sniffer::{pin_current_thread, DexKind, Signal};
use state_cache::StateCache;

#[derive(Debug, Clone)]
pub struct Opportunity {
    pub signal: Signal,
    pub confidence: f32,
    pub expected_profit_lamports: u64,
}

#[derive(Clone)]
pub struct FilterConfig {
    pub core_id: Option<usize>,
    pub min_confidence: f32,
    pub min_supply: u64,
    pub max_supply: u64,
}
impl Default for FilterConfig {
    fn default() -> Self {
        Self {
            core_id: Some(4),
            min_confidence: 0.6,
            min_supply: 1,
            max_supply: 1_000_000_000_000_000_000,
        }
    }
}

pub struct FilterStack {
    config: FilterConfig,
    cache: StateCache,
    feature_engine: FeatureEngine,
    predictor: Predictor,
    supported: HashSet<DexKind>,
}

impl FilterStack {
    pub fn new(
        config: FilterConfig,
        cache: StateCache,
        feature_engine: FeatureEngine,
        predictor: Predictor,
    ) -> Self {
        let supported = [
            DexKind::RaydiumAmm,
            DexKind::RaydiumCpmm,
            DexKind::OrcaWhirlpool,
            DexKind::PumpFun,
        ]
        .into_iter()
        .collect();
        Self {
            config,
            cache,
            feature_engine,
            predictor,
            supported,
        }
    }
    pub fn spawn(
        self,
        input: Receiver<Signal>,
        output: SyncSender<Opportunity>,
    ) -> std::io::Result<JoinHandle<std::io::Result<()>>> {
        let core_id = self.config.core_id;
        thread::Builder::new()
            .name("filter-core-4".to_string())
            .spawn(move || {
                pin_current_thread(core_id);
                self.run(input, output);
                Ok(())
            })
    }
    pub fn run(self, input: Receiver<Signal>, output: SyncSender<Opportunity>) {
        while let Ok(signal) = input.recv() {
            let start = Instant::now();
            if let Some(opportunity) = self.evaluate(signal) {
                let _ = output.try_send(opportunity);
            }
            metrics::observe_filter_latency_us(start.elapsed().as_micros() as u64);
        }
    }
    pub fn evaluate(&self, signal: Signal) -> Option<Opportunity> {
        if !is_pubkey_shape(&signal.token_mint) || !is_pubkey_shape(&signal.pool_address) {
            reject("basic", "invalid_pubkey");
            return None;
        }
        if !self.supported.contains(&signal.dex)
            || signal.token_mint.is_empty()
            || signal.pool_address.is_empty()
        {
            reject("basic", "unsupported_or_empty_metadata");
            return None;
        }
        let snapshot = self.cache.get_hot(&signal.token_mint).unwrap_or_default();
        if snapshot.mint_authority.is_some() {
            reject("tokenomics", "mint_authority_present");
            return None;
        }
        if snapshot.freeze_authority.is_some() {
            reject("tokenomics", "freeze_authority_present");
            return None;
        }
        if snapshot.supply != 0
            && (snapshot.supply < self.config.min_supply
                || snapshot.supply > self.config.max_supply)
        {
            reject("tokenomics", "invalid_supply");
            return None;
        }
        if snapshot.blacklisted {
            reject("rug", "blacklisted_mint");
            return None;
        }
        if snapshot.supply != 0 && !snapshot.lp_locked {
            reject("rug", "lp_not_locked");
            return None;
        }
        let features = self.feature_engine.extract(
            &signal.token_mint,
            &FeatureContext {
                liquidity_lamports: signal.liquidity_lamports,
                dev_rug_count: if snapshot.blacklisted { 1 } else { 0 },
                holder_concentration: 0.0,
                buy_sell_ratio: 1.0,
                network_congestion: 0.0,
                age_slots: signal.slot,
            },
        );
        let confidence = self.predictor.predict(&features);
        if confidence < self.config.min_confidence {
            reject("intelligence", "low_confidence");
            return None;
        }
        Some(Opportunity {
            signal,
            confidence,
            expected_profit_lamports: 1_000_000,
        })
    }
}

fn reject(layer: &'static str, reason: &'static str) {
    metrics::inc_filtered(layer, reason);
}
fn is_pubkey_shape(value: &str) -> bool {
    const BASE58: &str = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    (32..=44).contains(&value.len()) && value.bytes().all(|b| BASE58.as_bytes().contains(&b))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    #[test]
    fn passes_clean_signal() {
        let cache = StateCache::new("redis://127.0.0.1/".into(), Duration::from_secs(5));
        let stack = FilterStack::new(
            FilterConfig::default(),
            cache,
            FeatureEngine::new(Duration::from_secs(5)),
            Predictor::load(None).unwrap(),
        );
        let signal = Signal {
            token_mint: "So11111111111111111111111111111111111111112".into(),
            pool_address: "So11111111111111111111111111111111111111112".into(),
            dex: DexKind::RaydiumAmm,
            dev_wallet: String::new(),
            liquidity_lamports: 10_000_000_000,
            slot: 1,
            arrival_ns: 1,
            signature: "sig".into(),
        };
        assert!(stack.evaluate(signal).is_some());
    }
}
