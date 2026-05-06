//! Standalone Rust execution engine for Solo-Hunter Ultra.

use std::env;
use std::net::SocketAddr;
use std::sync::mpsc::sync_channel;
use std::time::Duration;

use wallet::SecretString;

fn main() -> Result<(), String> {
    let config = Config::from_env()?;
    let _metrics =
        metrics::spawn_prometheus(([0, 0, 0, 0], 9090).into()).map_err(|e| e.to_string())?;

    let wallet_key = SecretString::new(config.wallet_encryption_key.clone());
    let signer = wallet::WalletSigner::load_encrypted(&config.wallet_key_path, &wallet_key)?;
    let rpc_pool = rpc_pool::RpcPool::new(config.rpc_urls.clone())?;
    let _rpc_health = rpc_pool.clone().spawn_health_checks();

    let state_cache =
        state_cache::StateCache::new(config.redis_url.clone(), Duration::from_secs(5));
    let _cache_refresh = state_cache.clone().spawn_refresh_task();

    let blockhash_cache = tx_builder::AtomicBlockhashCache::new(config.initial_blockhash.clone());
    spawn_blockhash_refresh(rpc_pool.clone(), blockhash_cache.clone());

    let builder = tx_builder::TxBuilder::new(
        blockhash_cache,
        signer.public_key().to_string(),
        config.jito_tip_account.clone(),
    );
    let (signal_tx, signal_rx) = sync_channel::<sh_sniffer::Signal>(config.signal_channel_capacity);
    let (opp_tx, opp_rx) =
        sync_channel::<filter_stack::Opportunity>(config.opportunity_channel_capacity);

    let sniffer_stats = std::sync::Arc::new(sh_sniffer::SnifferStats::default());
    let sniffer = sh_sniffer::ShredstreamSniffer::new(
        sh_sniffer::SnifferConfig {
            bind_addr: config.shredstream_bind_addr,
            core_id: Some(0),
        },
        signal_tx,
        sniffer_stats,
    );
    let _sniffer_handle = sniffer.spawn().map_err(|e| e.to_string())?;

    let predictor = intelligence::Predictor::load(config.onnx_model_path.clone())?;
    let feature_engine = intelligence::FeatureEngine::new(Duration::from_secs(5));
    let filter = filter_stack::FilterStack::new(
        filter_stack::FilterConfig {
            core_id: Some(4),
            ..Default::default()
        },
        state_cache,
        feature_engine,
        predictor,
    );
    let _filter_handle = filter.spawn(signal_rx, opp_tx).map_err(|e| e.to_string())?;

    let execution = execution::ExecutionEngine::new(
        execution::ExecutionConfig {
            core_id: Some(6),
            jito_url: config.jito_url,
            jito_auth: SecretString::new(config.jito_auth_key),
            input_lamports: config.input_lamports,
            min_output_lamports: config.min_output_lamports,
        },
        builder,
        signer,
        rpc_pool,
    );
    let _execution_handle = execution.spawn(opp_rx).map_err(|e| e.to_string())?;

    println!("{{\"event\":\"hunterd_started\"}}");
    loop {
        std::thread::park();
    }
}

fn spawn_blockhash_refresh(
    rpc_pool: rpc_pool::RpcPool,
    cache: tx_builder::AtomicBlockhashCache,
) -> std::thread::JoinHandle<()> {
    std::thread::Builder::new()
        .name("blockhash-refresh".into())
        .spawn(move || loop {
            std::thread::sleep(Duration::from_secs(1));
            if let Ok((slot, blockhash)) = rpc_pool.get_latest_blockhash() {
                cache.store(slot, blockhash);
            }
        })
        .expect("spawn blockhash refresh")
}

struct Config {
    wallet_encryption_key: String,
    jito_auth_key: String,
    rpc_urls: Vec<String>,
    shredstream_bind_addr: SocketAddr,
    wallet_key_path: String,
    redis_url: String,
    jito_url: String,
    jito_tip_account: String,
    initial_blockhash: String,
    onnx_model_path: Option<String>,
    signal_channel_capacity: usize,
    opportunity_channel_capacity: usize,
    input_lamports: u64,
    min_output_lamports: u64,
}

impl Config {
    fn from_env() -> Result<Self, String> {
        let wallet_encryption_key = require_env("WALLET_ENCRYPTION_KEY")?;
        let jito_auth_key = require_env("JITO_AUTH_KEY")?;
        let helius_rpc_url = require_env("HELIUS_RPC_URL")?;
        let shredstream_bind_addr: SocketAddr = require_env("SHREDSTREAM_BIND_ADDR")?
            .parse()
            .map_err(|e| format!("invalid SHREDSTREAM_BIND_ADDR: {e}"))?;
        if !helius_rpc_url.starts_with("https://") {
            return Err("HELIUS_RPC_URL must use HTTPS in production".into());
        }
        Ok(Self {
            wallet_encryption_key,
            jito_auth_key,
            rpc_urls: env::var("RPC_URLS")
                .ok()
                .map(|v| {
                    v.split(',')
                        .map(str::trim)
                        .filter(|v| !v.is_empty())
                        .map(ToOwned::to_owned)
                        .collect()
                })
                .unwrap_or_else(|| vec![helius_rpc_url]),
            shredstream_bind_addr,
            wallet_key_path: env::var("WALLET_KEY_PATH")
                .unwrap_or_else(|_| "./keys/encrypted_wallet.json".to_string()),
            redis_url: env::var("REDIS_URL").unwrap_or_else(|_| "redis://127.0.0.1/".to_string()),
            jito_url: env::var("JITO_RELAYER_URL")
                .unwrap_or_else(|_| "https://mainnet.block-engine.jito.wtf".to_string()),
            jito_tip_account: env::var("JITO_TIP_ACCOUNT")
                .unwrap_or_else(|_| "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5".to_string()),
            initial_blockhash: env::var("INITIAL_BLOCKHASH")
                .unwrap_or_else(|_| "11111111111111111111111111111111".to_string()),
            onnx_model_path: env::var("ONNX_MODEL_PATH").ok(),
            signal_channel_capacity: env::var("SIGNAL_CHANNEL_CAPACITY")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(65_536),
            opportunity_channel_capacity: env::var("OPPORTUNITY_CHANNEL_CAPACITY")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(16_384),
            input_lamports: env::var("INPUT_LAMPORTS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(10_000_000),
            min_output_lamports: env::var("MIN_OUTPUT_LAMPORTS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(1),
        })
    }
}
fn require_env(name: &str) -> Result<String, String> {
    let value =
        env::var(name).map_err(|_| format!("missing required environment variable {name}"))?;
    if value.trim().is_empty() {
        Err(format!("required environment variable {name} is empty"))
    } else {
        Ok(value)
    }
}
