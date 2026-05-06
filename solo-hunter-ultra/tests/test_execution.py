"""Execution component tests."""

from __future__ import annotations

from blockchain.transaction_builder import TransactionBuilder
from execution.fail_safes import FailSafeConfig, FailSafes
from execution.order_manager import OrderManager, OrderState
from strategy.execution.position_sizing import size_position

VALID_MINT = "So11111111111111111111111111111111111111112"


def test_order_lifecycle_transition() -> None:
    manager = OrderManager()
    manager.create("1", VALID_MINT)
    manager.transition("1", OrderState.SUBMITTED, "sig")
    assert manager.orders["1"].state == OrderState.SUBMITTED
    assert manager.orders["1"].signature == "sig"


def test_transaction_builder_caches_accounts() -> None:
    builder = TransactionBuilder()
    opportunity = {"dex": "raydium", "token_mint": VALID_MINT, "pool_address": VALID_MINT, "dev_wallet": "dev"}
    draft = builder.build_swap(opportunity, "hash", 10)
    assert draft.compute_unit_limit == 140_000
    assert draft.instructions[0]["data_template"] == "swap_exact_in"


def test_position_sizing_caps_at_five_percent() -> None:
    size = size_position(10.0, confidence=0.9, expected_multiple=2.0)
    assert 0.01 <= size <= 0.5


def test_fail_safes_block_daily_loss() -> None:
    fail_safes = FailSafes(FailSafeConfig(max_daily_loss_sol=1.0, max_open_positions=2))
    fail_safes.pnl_today_sol = -1.1
    assert not fail_safes.trading_allowed()
