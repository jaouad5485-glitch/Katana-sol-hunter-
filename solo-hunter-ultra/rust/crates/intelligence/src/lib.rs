//! ONNX-style inference facade and SIMD-friendly feature extraction placeholder.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};

#[derive(Debug, Clone)]
pub struct FeatureContext {
    pub liquidity_lamports: u64,
    pub dev_rug_count: u16,
    pub holder_concentration: f32,
    pub buy_sell_ratio: f32,
    pub network_congestion: f32,
    pub age_slots: u64,
}

#[derive(Clone)]
pub struct FeatureEngine {
    ttl: Duration,
    cache: Arc<RwLock<HashMap<String, (Instant, [f32; 50])>>>,
}

impl FeatureEngine {
    pub fn new(ttl: Duration) -> Self {
        Self {
            ttl,
            cache: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn extract(&self, key: &str, ctx: &FeatureContext) -> [f32; 50] {
        if let Some((instant, features)) = self.cache.read().expect("feature cache").get(key) {
            if instant.elapsed() <= self.ttl {
                return *features;
            }
        }
        let mut features = [0.0_f32; 50];
        features[0] = ctx.liquidity_lamports as f32 / 1_000_000_000.0;
        features[1] = ctx.dev_rug_count as f32;
        features[2] = ctx.holder_concentration;
        features[3] = ctx.buy_sell_ratio;
        features[4] = ctx.network_congestion;
        features[5] = ctx.age_slots as f32;
        self.cache
            .write()
            .expect("feature cache")
            .insert(key.to_string(), (Instant::now(), features));
        features
    }
}

#[derive(Clone)]
pub struct Predictor {
    model_path: Option<String>,
    cuda_requested: bool,
}

impl Predictor {
    pub fn load(model_path: Option<String>) -> Result<Self, String> {
        let predictor = Self {
            model_path,
            cuda_requested: std::env::var("ORT_USE_CUDA").is_ok(),
        };
        predictor.warmup();
        Ok(predictor)
    }
    pub fn warmup(&self) {
        let dummy = [0.0_f32; 50];
        for _ in 0..10 {
            let _ = self.predict(&dummy);
        }
    }
    pub fn predict(&self, features: &[f32; 50]) -> f32 {
        let liquidity = (features[0] / 10.0).clamp(0.0, 1.0);
        let rug_penalty = (features[1] * 0.2).clamp(0.0, 0.5);
        (0.55 + liquidity * 0.35 - rug_penalty).clamp(0.0, 1.0)
    }
    pub fn cuda_requested(&self) -> bool {
        self.cuda_requested
    }
    pub fn model_path(&self) -> Option<&str> {
        self.model_path.as_deref()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn fallback_prediction_is_bounded() {
        let predictor = Predictor::load(None).unwrap();
        let score = predictor.predict(&[1.0_f32; 50]);
        assert!((0.0..=1.0).contains(&score));
    }
}
