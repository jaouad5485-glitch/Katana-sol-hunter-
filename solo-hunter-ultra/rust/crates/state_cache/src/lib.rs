//! Two-tier account cache facade. Hot path uses only in-memory tier one.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::thread;
use std::time::{Duration, Instant};

#[derive(Debug, Clone, Default)]
pub struct AccountSnapshot {
    pub mint_authority: Option<String>,
    pub freeze_authority: Option<String>,
    pub supply: u64,
    pub lp_locked: bool,
    pub blacklisted: bool,
}

#[derive(Clone)]
pub struct StateCache {
    tier1: Arc<RwLock<HashMap<String, (Instant, AccountSnapshot)>>>,
    ttl: Duration,
    pub redis_url: String,
}

impl StateCache {
    pub fn new(redis_url: String, ttl: Duration) -> Self {
        Self {
            tier1: Arc::new(RwLock::new(HashMap::new())),
            ttl,
            redis_url,
        }
    }

    pub fn get_hot(&self, key: &str) -> Option<AccountSnapshot> {
        self.tier1
            .read()
            .ok()?
            .get(key)
            .and_then(|(instant, snapshot)| {
                if instant.elapsed() <= self.ttl {
                    Some(snapshot.clone())
                } else {
                    None
                }
            })
    }

    pub fn insert_hot(&self, key: String, value: AccountSnapshot) {
        self.tier1
            .write()
            .expect("cache lock")
            .insert(key, (Instant::now(), value));
    }

    pub fn spawn_refresh_task(self) -> thread::JoinHandle<()> {
        thread::Builder::new()
            .name("state-cache-refresh".into())
            .spawn(move || loop {
                thread::sleep(Duration::from_secs(1));
                let expired: Vec<String> = self
                    .tier1
                    .read()
                    .expect("cache lock")
                    .iter()
                    .filter(|(_, (i, _))| i.elapsed() > self.ttl)
                    .map(|(k, _)| k.clone())
                    .collect();
                let mut write = self.tier1.write().expect("cache lock");
                for key in expired {
                    write.remove(&key);
                }
            })
            .expect("spawn refresh")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn hot_cache_respects_ttl() {
        let cache = StateCache::new("redis://127.0.0.1/".to_string(), Duration::from_secs(5));
        cache.insert_hot(
            "mint".into(),
            AccountSnapshot {
                supply: 7,
                ..Default::default()
            },
        );
        assert_eq!(cache.get_hot("mint").unwrap().supply, 7);
    }
}
