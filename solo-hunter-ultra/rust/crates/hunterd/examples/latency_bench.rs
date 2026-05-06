use std::sync::mpsc::sync_channel;
use std::time::{Duration, Instant};

fn main() {
    let (signal_tx, signal_rx) = sync_channel::<sh_sniffer::Signal>(65_536);
    let (opp_tx, opp_rx) = sync_channel::<filter_stack::Opportunity>(16_384);
    let cache = state_cache::StateCache::new("redis://127.0.0.1/".into(), Duration::from_secs(5));
    let filter = filter_stack::FilterStack::new(
        filter_stack::FilterConfig::default(),
        cache,
        intelligence::FeatureEngine::new(Duration::from_secs(5)),
        intelligence::Predictor::load(None).unwrap(),
    );
    let _filter = filter.spawn(signal_rx, opp_tx).unwrap();
    let count = 10_000;
    let start = Instant::now();
    for i in 0..count {
        signal_tx
            .send(sh_sniffer::Signal {
                token_mint: "So11111111111111111111111111111111111111112".into(),
                pool_address: "So11111111111111111111111111111111111111112".into(),
                dex: sh_sniffer::DexKind::RaydiumAmm,
                dev_wallet: String::new(),
                liquidity_lamports: 10_000_000_000,
                slot: i,
                arrival_ns: sh_sniffer::now_ns(),
                signature: format!("sig{i}"),
            })
            .unwrap();
    }
    let mut received = 0;
    while received < count {
        if opp_rx.recv_timeout(Duration::from_secs(1)).is_ok() {
            received += 1;
        } else {
            break;
        }
    }
    let elapsed = start.elapsed();
    println!(
        "{{\"signals\":{},\"passed\":{},\"elapsed_us\":{},\"per_signal_us\":{:.3}}}",
        count,
        received,
        elapsed.as_micros(),
        elapsed.as_micros() as f64 / count as f64
    );
}
