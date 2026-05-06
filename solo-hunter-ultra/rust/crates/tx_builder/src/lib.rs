//! Deterministic pre-templated swap transaction builder.

use std::collections::BTreeMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock};

use filter_stack::Opportunity;
use sh_sniffer::DexKind;

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct AccountMetaLite {
    pub pubkey: String,
    pub is_signer: bool,
    pub is_writable: bool,
}
#[derive(Debug, Clone)]
pub struct InstructionLite {
    pub program_id: String,
    pub accounts: Vec<AccountMetaLite>,
    pub data: Vec<u8>,
}
#[derive(Debug, Clone)]
pub struct VersionedMessageV0Lite {
    pub payer: String,
    pub recent_blockhash: String,
    pub instructions: Vec<InstructionLite>,
}
#[derive(Debug, Clone)]
pub struct VersionedTransactionLite {
    pub message: VersionedMessageV0Lite,
    pub signatures: Vec<String>,
}

#[derive(Clone)]
pub struct AtomicBlockhashCache {
    slot: Arc<AtomicU64>,
    blockhash: Arc<RwLock<String>>,
}
impl AtomicBlockhashCache {
    pub fn new(initial: String) -> Self {
        Self {
            slot: Arc::new(AtomicU64::new(0)),
            blockhash: Arc::new(RwLock::new(initial)),
        }
    }
    pub fn load(&self) -> String {
        self.blockhash.read().expect("blockhash lock").clone()
    }
    pub fn store(&self, slot: u64, blockhash: String) {
        *self.blockhash.write().expect("blockhash lock") = blockhash;
        self.slot.store(slot, Ordering::Release);
    }
}

#[derive(Clone)]
pub struct Template {
    program_id: String,
    accounts: Vec<AccountMetaLite>,
    data_prefix: Vec<u8>,
}
#[derive(Clone)]
pub struct TxBuilder {
    templates: BTreeMap<DexKind, Template>,
    blockhash_cache: AtomicBlockhashCache,
    payer: String,
    jito_tip_account: String,
    compute_unit_limit: u32,
}

impl TxBuilder {
    pub fn new(
        blockhash_cache: AtomicBlockhashCache,
        payer: String,
        jito_tip_account: String,
    ) -> Self {
        let mut templates = BTreeMap::new();
        for (dex, program_id) in [
            (DexKind::RaydiumAmm, sh_sniffer::RAYDIUM_AMM_PROGRAM),
            (DexKind::RaydiumCpmm, sh_sniffer::RAYDIUM_CPMM_PROGRAM),
            (DexKind::OrcaWhirlpool, sh_sniffer::ORCA_WHIRLPOOL_PROGRAM),
            (DexKind::PumpFun, sh_sniffer::PUMP_FUN_PROGRAM),
        ] {
            templates.insert(
                dex,
                Template {
                    program_id: program_id.to_string(),
                    accounts: Vec::with_capacity(16),
                    data_prefix: b"swap_exact_in".to_vec(),
                },
            );
        }
        Self {
            templates,
            blockhash_cache,
            payer,
            jito_tip_account,
            compute_unit_limit: 140_000,
        }
    }
    pub fn build_swap(
        &self,
        opportunity: &Opportunity,
        input_lamports: u64,
        min_output_lamports: u64,
        tip_lamports: u64,
    ) -> Result<VersionedTransactionLite, String> {
        let template = self
            .templates
            .get(&opportunity.signal.dex)
            .ok_or("missing DEX template")?;
        let mut swap_accounts = template.accounts.clone();
        swap_accounts.push(AccountMetaLite {
            pubkey: opportunity.signal.pool_address.clone(),
            is_signer: false,
            is_writable: true,
        });
        swap_accounts.push(AccountMetaLite {
            pubkey: opportunity.signal.token_mint.clone(),
            is_signer: false,
            is_writable: true,
        });
        swap_accounts.sort_by(|a, b| a.pubkey.cmp(&b.pubkey));
        let mut swap_data = template.data_prefix.clone();
        swap_data.extend_from_slice(&input_lamports.to_le_bytes());
        swap_data.extend_from_slice(&min_output_lamports.to_le_bytes());
        let compute_budget = InstructionLite {
            program_id: "ComputeBudget111111111111111111111111111111".to_string(),
            accounts: Vec::new(),
            data: self.compute_unit_limit.to_le_bytes().to_vec(),
        };
        let swap = InstructionLite {
            program_id: template.program_id.clone(),
            accounts: swap_accounts,
            data: swap_data,
        };
        let tip = InstructionLite {
            program_id: "11111111111111111111111111111111".to_string(),
            accounts: vec![
                AccountMetaLite {
                    pubkey: self.payer.clone(),
                    is_signer: true,
                    is_writable: true,
                },
                AccountMetaLite {
                    pubkey: self.jito_tip_account.clone(),
                    is_signer: false,
                    is_writable: true,
                },
            ],
            data: tip_lamports.to_le_bytes().to_vec(),
        };
        Ok(VersionedTransactionLite {
            message: VersionedMessageV0Lite {
                payer: self.payer.clone(),
                recent_blockhash: self.blockhash_cache.load(),
                instructions: vec![compute_budget, swap, tip],
            },
            signatures: Vec::new(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use filter_stack::Opportunity;
    use sh_sniffer::{DexKind, Signal};
    #[test]
    fn builds_deterministic_swap() {
        let builder = TxBuilder::new(
            AtomicBlockhashCache::new("hash".into()),
            "payer".into(),
            "tip".into(),
        );
        let opportunity = Opportunity {
            signal: Signal {
                token_mint: "mint".into(),
                pool_address: "pool".into(),
                dex: DexKind::PumpFun,
                dev_wallet: String::new(),
                liquidity_lamports: 1,
                slot: 1,
                arrival_ns: 1,
                signature: "sig".into(),
            },
            confidence: 0.9,
            expected_profit_lamports: 1000,
        };
        let tx = builder.build_swap(&opportunity, 10, 9, 1).unwrap();
        assert_eq!(tx.message.instructions.len(), 3);
        assert_eq!(tx.message.recent_blockhash, "hash");
    }
}
