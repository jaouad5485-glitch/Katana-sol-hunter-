"""Order lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OrderState(StrEnum):
    """Order states."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    FAILED = "failed"


@dataclass(slots=True)
class Order:
    """Tracked order."""

    order_id: str
    token_mint: str
    state: OrderState = OrderState.PENDING
    signature: str | None = None


class OrderManager:
    """Stores active orders and state transitions."""

    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}

    def create(self, order_id: str, token_mint: str) -> Order:
        """Create a pending order."""
        order = Order(order_id=order_id, token_mint=token_mint)
        self.orders[order_id] = order
        return order

    def transition(self, order_id: str, state: OrderState, signature: str | None = None) -> None:
        """Move an order to a new state."""
        order = self.orders[order_id]
        order.state = state
        if signature:
            order.signature = signature
