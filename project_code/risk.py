from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from project_code.entry_exit import PositionDirection


@dataclass(frozen=True)
class RiskConfig:
    risk_pct: float
    max_position_size: Optional[float] = None
    min_stop_distance: Optional[float] = None
    min_stop_distance_pct: Optional[float] = 0.001
    max_leverage: Optional[float] = None
    # Kept for backward compatibility; buying power is always enforced as a hard
    # notional cap when buying_power_cash is provided.
    use_buying_power_cap: bool = False


@dataclass(frozen=True)
class SizingResult:
    accepted: bool
    refusal_reason: Optional[str]
    qty: Optional[float]
    target_risk_cash: float
    target_risk_pct: float
    stop_distance: float
    stop_distance_pct: float
    raw_qty: float
    # "actual_*" here means sizing-implied planned risk after caps/rounding
    # (not slippage-adjusted realized live risk).
    actual_risk_cash: float
    actual_risk_pct: float
    notional: float
    caps_applied: tuple[str, ...] = field(default_factory=tuple)


def _refusal(
    *,
    reason: str,
    target_risk_cash: float,
    target_risk_pct: float,
    stop_distance: float,
    stop_distance_pct: float,
    raw_qty: float,
) -> SizingResult:
    return SizingResult(
        accepted=False,
        refusal_reason=reason,
        qty=None,
        target_risk_cash=target_risk_cash,
        target_risk_pct=target_risk_pct,
        stop_distance=stop_distance,
        stop_distance_pct=stop_distance_pct,
        raw_qty=raw_qty,
        actual_risk_cash=0.0,
        actual_risk_pct=0.0,
        notional=0.0,
        caps_applied=tuple(),
    )


def size_position_detailed(
    *,
    direction: "PositionDirection",
    entry_price: float,
    sl_price: float,
    risk_config: RiskConfig,
    equity: float,
    buying_power_cash: Optional[float] = None,
    round_func: Callable[[float], float] = lambda x: x,
) -> SizingResult:
    del direction  # sizing is symmetric for long/short in this engine

    if not math.isfinite(entry_price) or entry_price <= 0:
        raise ValueError(f"entry_price must be > 0, got {entry_price}")
    if not math.isfinite(sl_price) or sl_price <= 0:
        raise ValueError(f"sl_price must be > 0, got {sl_price}")
    if not math.isfinite(equity) or equity <= 0:
        raise ValueError(f"equity must be > 0, got {equity}")
    if risk_config.risk_pct <= 0 or risk_config.risk_pct > 1:
        raise ValueError(f"risk_pct must be in (0, 1], got {risk_config.risk_pct}")
    if risk_config.max_position_size is not None and risk_config.max_position_size <= 0:
        raise ValueError(f"max_position_size must be > 0, got {risk_config.max_position_size}")
    if risk_config.max_leverage is not None and risk_config.max_leverage <= 0:
        raise ValueError(f"max_leverage must be > 0, got {risk_config.max_leverage}")
    if risk_config.min_stop_distance is not None and risk_config.min_stop_distance <= 0:
        raise ValueError(f"min_stop_distance must be > 0, got {risk_config.min_stop_distance}")
    if risk_config.min_stop_distance_pct is not None and risk_config.min_stop_distance_pct <= 0:
        raise ValueError(f"min_stop_distance_pct must be > 0, got {risk_config.min_stop_distance_pct}")

    stop_distance = abs(entry_price - sl_price)
    stop_distance_pct = stop_distance / entry_price
    if stop_distance <= 0:
        raise ValueError("stop_distance must be > 0 (entry and SL cannot coincide).")

    effective_min_stop_distance = 0.0
    if risk_config.min_stop_distance is not None:
        effective_min_stop_distance = max(effective_min_stop_distance, risk_config.min_stop_distance)
    if risk_config.min_stop_distance_pct is not None:
        effective_min_stop_distance = max(
            effective_min_stop_distance, entry_price * risk_config.min_stop_distance_pct
        )
    if stop_distance < effective_min_stop_distance:
        return _refusal(
            reason=(
                "stop_too_tight:"
                f"stop_distance={stop_distance:.6f},"
                f"min_required={effective_min_stop_distance:.6f}"
            ),
            target_risk_cash=equity * risk_config.risk_pct,
            target_risk_pct=risk_config.risk_pct,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance_pct,
            raw_qty=0.0,
        )

    target_risk_cash = equity * risk_config.risk_pct
    target_risk_pct = risk_config.risk_pct
    # Hard safety policy: whenever buying_power_cash is provided, enforce it.
    if buying_power_cash is not None:
        if not math.isfinite(buying_power_cash):
            raise ValueError(f"buying_power_cash must be finite, got {buying_power_cash}")
        if buying_power_cash <= 0:
            return _refusal(
                reason="buying_power_not_available",
                target_risk_cash=target_risk_cash,
                target_risk_pct=target_risk_pct,
                stop_distance=stop_distance,
                stop_distance_pct=stop_distance_pct,
                raw_qty=0.0,
            )

    raw_qty = target_risk_cash / stop_distance
    qty = float(raw_qty)
    caps_applied: list[str] = []

    def mark_cap(name: str) -> None:
        if name not in caps_applied:
            caps_applied.append(name)

    if risk_config.max_leverage is not None:
        max_qty_by_leverage = (equity * risk_config.max_leverage) / entry_price
        if qty > max_qty_by_leverage:
            qty = max_qty_by_leverage
            mark_cap("max_leverage")

    if buying_power_cash is not None and buying_power_cash > 0:
        max_qty_by_notional = buying_power_cash / entry_price
        if qty > max_qty_by_notional:
            qty = max_qty_by_notional
            mark_cap("buying_power_notional")

    if risk_config.max_position_size is not None and qty > risk_config.max_position_size:
        qty = risk_config.max_position_size
        mark_cap("max_position_size")
    rounded_qty = float(round_func(qty))
    if not math.isfinite(rounded_qty):
        return _refusal(
            reason="qty_non_finite_after_rounding",
            target_risk_cash=target_risk_cash,
            target_risk_pct=target_risk_pct,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance_pct,
            raw_qty=raw_qty,
        )
    # Conservative rounding: never allow rounding to increase size.
    qty = min(rounded_qty, qty)
    if rounded_qty > qty + 1e-15:
        mark_cap("conservative_rounding")

    # Post-rounding hard cap re-checks (float-safe).
    if risk_config.max_leverage is not None:
        max_qty_by_leverage = (equity * risk_config.max_leverage) / entry_price
        if qty > max_qty_by_leverage:
            qty = max_qty_by_leverage
            mark_cap("max_leverage_post")
    if buying_power_cash is not None and buying_power_cash > 0:
        max_qty_by_notional = buying_power_cash / entry_price
        if qty > max_qty_by_notional:
            qty = max_qty_by_notional
            mark_cap("buying_power_notional_post")
    if risk_config.max_position_size is not None and qty > risk_config.max_position_size:
        qty = risk_config.max_position_size
        mark_cap("max_position_size_post")
    max_qty_by_target_risk = target_risk_cash / stop_distance
    if qty > max_qty_by_target_risk:
        qty = max_qty_by_target_risk
        mark_cap("target_risk_post")

    if qty <= 0:
        return _refusal(
            reason="qty_zero_after_caps",
            target_risk_cash=target_risk_cash,
            target_risk_pct=target_risk_pct,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance_pct,
            raw_qty=raw_qty,
        )

    actual_risk_cash = qty * stop_distance
    actual_risk_pct = actual_risk_cash / equity
    notional = qty * entry_price
    if risk_config.max_leverage is not None and notional > (equity * risk_config.max_leverage) + 1e-9:
        return _refusal(
            reason="post_check_leverage_exceeded",
            target_risk_cash=target_risk_cash,
            target_risk_pct=target_risk_pct,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance_pct,
            raw_qty=raw_qty,
        )
    if buying_power_cash is not None and notional > buying_power_cash + 1e-9:
        return _refusal(
            reason="post_check_notional_exceeded",
            target_risk_cash=target_risk_cash,
            target_risk_pct=target_risk_pct,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance_pct,
            raw_qty=raw_qty,
        )
    if actual_risk_cash > target_risk_cash + 1e-9:
        return _refusal(
            reason="post_check_target_risk_exceeded",
            target_risk_cash=target_risk_cash,
            target_risk_pct=target_risk_pct,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance_pct,
            raw_qty=raw_qty,
        )

    return SizingResult(
        accepted=True,
        refusal_reason=None,
        qty=float(qty),
        target_risk_cash=float(target_risk_cash),
        target_risk_pct=float(target_risk_pct),
        stop_distance=float(stop_distance),
        stop_distance_pct=float(stop_distance_pct),
        raw_qty=float(raw_qty),
        actual_risk_cash=float(actual_risk_cash),
        actual_risk_pct=float(actual_risk_pct),
        notional=float(notional),
        caps_applied=tuple(caps_applied),
    )


def size_position(
    *,
    direction: "PositionDirection",
    entry_price: float,
    sl_price: float,
    risk_config: RiskConfig,
    equity: float,
    buying_power_cash: Optional[float] = None,
    round_func: Callable[[float], float] = lambda x: x,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Backward-compatible tuple API used by entry planning.
    """
    result = size_position_detailed(
        direction=direction,
        entry_price=entry_price,
        sl_price=sl_price,
        risk_config=risk_config,
        equity=equity,
        buying_power_cash=buying_power_cash,
        round_func=round_func,
    )
    if not result.accepted:
        return None, result.refusal_reason
    return result.qty, None
