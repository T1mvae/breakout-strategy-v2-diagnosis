import math
from typing import List, Optional, Tuple

from project_code.utils.trade_math import realized_close_pnl
from project_code.utils.trade_state import TradeState


def compute_exit_pnl(
    ts: TradeState,
    fill_price: Optional[float],
    qty_closed: Optional[float] = None,
) -> float:
    """Direction-aware PnL for a partial or full exit.

    Returns 0.0 when any required field is missing, fill_price <= 0,
    or quantity is zero.
    """
    direction = ts.direction
    if (
        ts.entry_fill_price is None
        or fill_price is None
        or direction is None
        or fill_price <= 0
        or not math.isfinite(fill_price)
    ):
        return 0.0
    q = abs(qty_closed) if qty_closed is not None else abs(ts.active_qty)
    if q <= 0:
        return 0.0
    return realized_close_pnl(
        direction=direction,
        entry_price=ts.entry_fill_price,
        fill_price=fill_price,
        qty_closed=q,
    )


def finalize_exit(
    ts: TradeState,
    *,
    reason: str,
    fill_price: Optional[float],
    qty_closed: Optional[float] = None,
) -> dict:
    """Compute exit accounting for a tracked or untracked closure.

    Does NOT reset state — caller must call ts.reset() / _reset_trade().
    Returns dict: {pnl, effective_reason, sl_hit, tp_hit, pending_exit_price}.
    """
    effective_reason = ts.pending_exit_reason or reason
    pnl = compute_exit_pnl(ts, fill_price, qty_closed)
    return {
        "pnl": pnl,
        "effective_reason": effective_reason,
        "sl_hit": effective_reason == "SL",
        "tp_hit": effective_reason == "TP",
        "pending_exit_price": ts.pending_exit_price,
    }


def heal_state(
    ts: TradeState,
    *,
    is_invested: bool,
    portfolio_qty: float,
    has_open_orders: bool,
    current_time: object = None,
) -> List[Tuple[str, str]]:
    """Detect and recover from inconsistent trade state.

    Returns (action, detail) pairs the caller must handle:
        FINALIZE       — caller must finalize_exit + reset
        CLEAR_EXIT     — caller clears exit_ticket
        CLEAR_ENTRY    — caller clears entry_ticket
        RESET          — ts was reset; caller clears tickets + SL manager
        LOG            — informational only
    """
    actions: List[Tuple[str, str]] = []

    if ts.phase == "OPEN":
        if not is_invested and not has_open_orders:
            actions.append(("FINALIZE", "HEAL_OPEN_NO_POSITION"))
            return actions
        if not has_open_orders and ts.pending_exit_reason is not None:
            ts.pending_exit_reason = None
            ts.pending_exit_price = None
            actions.append(("CLEAR_EXIT", "stale_exit_fields"))

    elif ts.phase == "ENTRY_SUBMITTED":
        if is_invested and not has_open_orders:
            ts.phase = "OPEN"
            if ts.entry_fill_time is None:
                ts.entry_fill_time = current_time
            if ts.entry_fill_price is None and ts.plan is not None:
                ts.entry_fill_price = float(ts.plan.entry_price)
            ts.active_qty = portfolio_qty
            actions.append(("CLEAR_ENTRY", "healed_entry_to_open"))
        elif not is_invested and not has_open_orders:
            ts.reset()
            actions.append(("RESET", "entry_never_filled"))

    elif ts.phase == "EXIT_SUBMITTED":
        if is_invested and not has_open_orders:
            ts.phase = "OPEN"
            ts.pending_exit_reason = None
            ts.pending_exit_price = None
            ts.active_qty = portfolio_qty
            actions.append(("CLEAR_EXIT", "healed_exit_to_open"))
        elif not is_invested and not has_open_orders:
            actions.append(("FINALIZE", "HEAL_EXIT_NO_POSITION"))

    return actions
