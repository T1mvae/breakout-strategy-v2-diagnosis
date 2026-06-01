from dataclasses import dataclass
from typing import Optional

from project_code.entry_exit import PositionDirection, TradePlan


@dataclass
class TradeState:
    """
    Single source of truth for per-trade execution state.

    Phases: FLAT -> ENTRY_SUBMITTED -> OPEN -> EXIT_SUBMITTED -> FLAT

    Transition methods enforce valid state changes.
    reset() clears all per-trade fields atomically.
    """

    phase: str = "FLAT"
    plan: Optional[TradePlan] = None

    active_qty: float = 0.0
    sl_price: Optional[float] = None
    tp_price: Optional[float] = None

    pending_exit_reason: Optional[str] = None
    pending_exit_price: Optional[float] = None

    entry_fill_price: Optional[float] = None
    entry_fill_time: object = None

    partial_exit_done: bool = False
    partial_submitted: bool = False
    trailing_stop_price: Optional[float] = None
    remaining_qty: float = 0.0

    cooldown_until: int = -1

    @property
    def is_flat(self) -> bool:
        return self.phase == "FLAT"

    @property
    def is_open(self) -> bool:
        return self.phase == "OPEN"

    @property
    def direction(self) -> Optional[PositionDirection]:
        return self.plan.direction if self.plan is not None else None

    def submit_entry(
        self, *, plan: TradePlan, sl: float, tp: Optional[float]
    ) -> None:
        """FLAT -> ENTRY_SUBMITTED. Clears all per-trade fields."""
        self.phase = "ENTRY_SUBMITTED"
        self.plan = plan
        self.sl_price = sl
        self.tp_price = tp
        self.active_qty = 0.0
        self.pending_exit_reason = None
        self.pending_exit_price = None
        self.entry_fill_price = None
        self.entry_fill_time = None
        self.partial_exit_done = False
        self.partial_submitted = False
        self.trailing_stop_price = None
        self.remaining_qty = 0.0

    def mark_entry_filled(
        self, *, fill_price: float, fill_time: object, qty: float
    ) -> None:
        """ENTRY_SUBMITTED -> OPEN on first fill."""
        self.phase = "OPEN"
        self.entry_fill_price = fill_price
        self.entry_fill_time = fill_time
        self.active_qty = qty

    def submit_exit(
        self, *, reason: str, model_price: Optional[float]
    ) -> None:
        """OPEN -> EXIT_SUBMITTED."""
        self.phase = "EXIT_SUBMITTED"
        self.pending_exit_reason = reason
        self.pending_exit_price = model_price
        if reason == "PARTIAL_1R":
            self.partial_submitted = True

    def mark_partial_filled(
        self, *, remaining_qty: float, trailing_stop: float
    ) -> None:
        """EXIT_SUBMITTED (partial) -> OPEN with trailing active."""
        self.phase = "OPEN"
        self.remaining_qty = remaining_qty
        self.active_qty = remaining_qty
        self.partial_exit_done = True
        self.partial_submitted = False
        self.trailing_stop_price = trailing_stop
        self.pending_exit_reason = None
        self.pending_exit_price = None

    def reset(self, *, cooldown_bars: int = 0, bar_index: int = 0) -> None:
        """Return to FLAT. Clears all per-trade fields atomically."""
        self.phase = "FLAT"
        self.plan = None
        self.active_qty = 0.0
        self.sl_price = None
        self.tp_price = None
        self.pending_exit_reason = None
        self.pending_exit_price = None
        self.entry_fill_price = None
        self.entry_fill_time = None
        self.partial_exit_done = False
        self.partial_submitted = False
        self.trailing_stop_price = None
        self.remaining_qty = 0.0
        if cooldown_bars > 0:
            self.cooldown_until = bar_index + cooldown_bars
