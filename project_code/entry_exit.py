from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from project_code.risk import RiskConfig, size_position

# IMPORTANT:
# If your stop_loss module imports Bar and PositionDirection from this file,
# these names must exist here and keep the same meaning.


class PositionDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ExitReason(str, Enum):
    SL = "SL"
    TP = "TP"
    PARTIAL_1R = "PARTIAL_1R"


class TakeProfitMode(str, Enum):
    RR_BASED = "RR_BASED"
    RANGE_BASED = "RANGE_BASED"


class SameBarSlTpRule(str, Enum):
    WORST_CASE = "WORST_CASE"
    OPEN_PROXIMITY = "OPEN_PROXIMITY"
    LOWER_TIMEFRAME = "LOWER_TIMEFRAME"


# V2 regime values (for entry filter gating)
REGIME_TREND_UP = "trend_up"
REGIME_TREND_DOWN = "trend_down"
REGIME_RANGE = "range"


@dataclass(frozen=True)
class Bar:
    """
    OHLC candlestick bar.
    Volume/time are optional and not required for V1 entry/exit rules.
    """
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    time: Optional[str] = None  # Replace with datetime if you prefer.


@dataclass(frozen=True)
class SwingLevels:
    """
    Snapshot of swing levels used by the strategy.

    Names match the V1 document:
      - last_swing_high_price == lastSwingHighPrice
      - last_swing_low_price == lastSwingLowPrice
    """
    last_swing_high_price: Optional[float] = None
    last_swing_low_price: Optional[float] = None


def has_level(level: Optional[float]) -> bool:
    """Level is usable only if it is not None/NaN."""
    return level is not None and not (isinstance(level, float) and math.isnan(level))


def bos_up(close: float, last_high: Optional[float], buffer: float = 0.0) -> bool:
    """Break of structure to the upside with optional buffer."""
    return has_level(last_high) and close > last_high + buffer


def bos_down(close: float, last_low: Optional[float], buffer: float = 0.0) -> bool:
    """Break of structure to the downside with optional buffer."""
    return has_level(last_low) and close < last_low - buffer


def update_last_swing_levels(
    swing_levels: SwingLevels,
    *,
    highlow_flag: Optional[float],
    level: Optional[float],
) -> SwingLevels:
    """
    Update last swing levels only when a confirmed swing is observed.

    Args:
        highlow_flag: 1 for swing high, -1 for swing low, anything else leaves levels unchanged.
        level: swing price level; ignored if invalid.
    """
    if not has_level(level):
        return swing_levels

    if highlow_flag == 1:
        return SwingLevels(last_swing_high_price=level, last_swing_low_price=swing_levels.last_swing_low_price)
    if highlow_flag == -1:
        return SwingLevels(last_swing_high_price=swing_levels.last_swing_high_price, last_swing_low_price=level)
    return swing_levels


@dataclass(frozen=True)
class BosSignal:
    """
    BOS signal detected on the CLOSE of the signal candle (t).

    Execution in V1 is deterministic:
      - signal is confirmed on Close[t]
      - entry is executed on Open[t+1]
    """
    direction: PositionDirection
    signal_candle_index: int  # t


@dataclass(frozen=True)
class TradePlan:
    """
    Trade plan created at entry time (V1 fixes SL at entry; TP optional for V2).

    Contains:
      - signal_candle_index: t (where BOS was detected on close)
      - entry_candle_index: t+1 (where we execute on open)
      - entry_price, sl_price, quantity
      - tp_price: optional; None when using dynamic exits (partial + trailing)
    """
    direction: PositionDirection
    signal_candle_index: int
    entry_candle_index: int
    entry_price: float
    sl_price: float
    quantity: float
    tp_price: Optional[float] = None  # None = no fixed TP (dynamic management)


@dataclass(frozen=True)
class TradeExit:
    """
    Exit event for a trade: price and reason (SL or TP).
    """
    exit_price: float
    exit_reason: ExitReason


def detect_bos_signal(
    *,
    bars: list[Bar],
    t: int,
    swing_levels: SwingLevels,
    k_buffer: float = 0.0,
    atr: Optional[float] = None,
) -> Optional[BosSignal]:
    """
    V2 BOS definition with optional ATR-based breakout buffer:

      - BOS Long:  Close[t] > lastSwingHighPrice + buffer
      - BOS Short: Close[t] < lastSwingLowPrice - buffer

    Signal is evaluated on the CLOSE of bar t.
    Entry requires bar t+1 to exist (executed on Open[t+1]).
    
    Args:
        bars: List of Bar objects
        t: Current bar index for signal detection
        swing_levels: Current swing levels
        k_buffer: ATR multiplier for breakout buffer (default 0.0 = no buffer)
        atr: ATR value (optional, required if k_buffer > 0)
    """
    if t < 0 or t >= len(bars):
        raise IndexError("Bar index out of range.")

    # We need the next bar for execution on Open[t+1].
    if t + 1 >= len(bars):
        return None

    close_t = bars[t].close
    
    # Calculate buffer from ATR
    buffer = 0.0
    if atr is not None and k_buffer > 0 and not math.isnan(atr):
        buffer = k_buffer * atr

    if not has_level(swing_levels.last_swing_high_price):
        assert not bos_up(close_t, swing_levels.last_swing_high_price, buffer=buffer)
    if not has_level(swing_levels.last_swing_low_price):
        assert not bos_down(close_t, swing_levels.last_swing_low_price, buffer=buffer)

    if bos_up(close_t, swing_levels.last_swing_high_price, buffer=buffer):
        return BosSignal(direction=PositionDirection.LONG, signal_candle_index=t)

    if bos_down(close_t, swing_levels.last_swing_low_price, buffer=buffer):
        return BosSignal(direction=PositionDirection.SHORT, signal_candle_index=t)

    return None


def calculate_take_profit_price(
    *,
    direction: PositionDirection,
    tp_mode: TakeProfitMode,
    entry_price: float,
    sl_price: float,
    tp_mult: float,
    swing_levels: SwingLevels,
) -> float:
    """
    V1 Take Profit modes:

    1) RR_BASED:
        R = abs(Entry - SL)
        Long:  TP = Entry + k * R
        Short: TP = Entry - k * R

    2) RANGE_BASED:
        range = lastSwingHighPrice - lastSwingLowPrice
        Long:  TP = Entry + range
        Short: TP = Entry - range
    """
    if tp_mode == TakeProfitMode.RR_BASED:
        r = abs(entry_price - sl_price)
        if r <= 0:
            raise ValueError("RR_BASED: invalid R (entry_price must differ from sl_price).")
        if tp_mult <= 0:
            raise ValueError("RR_BASED: tp_mult must be > 0.")

        if direction == PositionDirection.LONG:
            return entry_price + tp_mult * r
        return entry_price - tp_mult * r

    if tp_mode == TakeProfitMode.RANGE_BASED:
        hi = swing_levels.last_swing_high_price
        lo = swing_levels.last_swing_low_price
        if not (has_level(hi) and has_level(lo)):
            raise ValueError("RANGE_BASED: requires both last swing high and last swing low.")
        assert hi is not None and lo is not None
        rng = hi - lo
        if rng <= 0:
            raise ValueError("RANGE_BASED: invalid range (swing high must be > swing low).")

        if direction == PositionDirection.LONG:
            return entry_price + rng
        return entry_price - rng

    raise ValueError(f"Unsupported tp_mode: {tp_mode}")


def plan_trade_from_signal(
    *,
    bars: list[Bar],
    bos_signal: BosSignal,
    swing_levels: SwingLevels,
    stop_loss_manager,
    tp_mode: TakeProfitMode,
    tp_mult: float,
    risk_config: RiskConfig,
    equity: float,
    buying_power_cash: Optional[float] = None,
    position_sizer=size_position,
    use_fixed_tp: bool = True,
    atr_for_sl: Optional[float] = None,
) -> TradePlan:
    """
    WHERE ENTRY HAPPENS (V1):

      - Signal candle index = t (BOS confirmed on Close[t])
      - Entry candle index  = t+1
      - Entry price         = Open[t+1]

    This function:
      1) Takes entry_price from Open[t+1]
      2) Fixes SL using your StopLossManager.on_entry(...)
      3) Calculates position size (risk-based)
      4) Calculates TP (RR-based or Range-based) if use_fixed_tp=True
      5) Returns a TradePlan with entry/sl/qty fixed; tp_price optional (None if use_fixed_tp=False)

    Args:
      atr_for_sl: Pre-computed ATR value for ATR SL mode. When provided,
                  avoids expensive O(N) recomputation from bars.
    """
    t = bos_signal.signal_candle_index
    entry_candle_index = t + 1
    if entry_candle_index >= len(bars):
        raise ValueError("Cannot plan entry: next candle (t+1) does not exist.")

    entry_price = bars[entry_candle_index].open

    on_entry_kw: dict = {
        "direction": bos_signal.direction,
        "entry_price": entry_price,
        "last_swing_high": swing_levels.last_swing_high_price,
        "last_swing_low": swing_levels.last_swing_low_price,
        "signal_bar": bars[t],
    }
    if getattr(stop_loss_manager, "mode", None) == "atr":
        if atr_for_sl is not None:
            on_entry_kw["atr"] = atr_for_sl
        else:
            on_entry_kw["bars"] = bars
            on_entry_kw["entry_candle_index"] = entry_candle_index
    sl_price = stop_loss_manager.on_entry(**on_entry_kw)

    qty, refuse_reason = position_sizer(
        direction=bos_signal.direction,
        entry_price=entry_price,
        sl_price=sl_price,
        risk_config=risk_config,
        equity=equity,
        buying_power_cash=buying_power_cash,
    )
    if qty is None or qty <= 0:
        raise ValueError(
            f"Position sizing refused (reason={refuse_reason}, dir={bos_signal.direction}, entry={entry_price}, sl={sl_price})"
        )

    tp_price: Optional[float] = None
    if use_fixed_tp:
        tp_price = calculate_take_profit_price(
            direction=bos_signal.direction,
            tp_mode=tp_mode,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_mult=tp_mult,
            swing_levels=swing_levels,
        )

    return TradePlan(
        direction=bos_signal.direction,
        signal_candle_index=t,
        entry_candle_index=entry_candle_index,
        entry_price=entry_price,
        sl_price=sl_price,
        quantity=qty,
        tp_price=tp_price,
    )


# -----------------------------------------------------------------------------
# Entry filter layer (V2)
# -----------------------------------------------------------------------------
# BOS detection = pure signal. Filters = decision gate. Planning = execution.
# This layer gates entries: BOS → validate_entry_filters → plan_trade_from_signal
# -----------------------------------------------------------------------------


def validate_entry_filters(
    *,
    direction: PositionDirection,
    regime: str,
    adx: Optional[float] = None,
    adx_threshold: Optional[float] = None,
    rsi: Optional[float] = None,
    rsi_threshold: Optional[float] = None,
    is_range_or_compressed: Optional[bool] = None,
) -> bool:
    """
    V2 entry filter gating. Returns True if entry is allowed, False otherwise.

    Rules:
      - Regime (MANDATORY): LONG only if regime == "trend_up", SHORT only if regime == "trend_down"
      - ADX (optional): if adx provided, require adx >= adx_threshold (default 25)
      - RSI (optional): LONG require rsi >= threshold, SHORT require rsi <= threshold (default 50)
      - Range filter (optional): if is_range_or_compressed is True → reject
    """
    # Regime (MANDATORY)
    if direction == PositionDirection.LONG and regime != REGIME_TREND_UP:
        return False
    if direction == PositionDirection.SHORT and regime != REGIME_TREND_DOWN:
        return False

    # Range filter (optional): reject if market is range/compressed
    if is_range_or_compressed is True:
        return False

    # ADX (optional): require trend strength
    if adx is not None:
        threshold = adx_threshold if adx_threshold is not None else 25.0
        if not math.isfinite(adx) or adx < threshold:
            return False

    # RSI (optional): momentum confirmation
    if rsi is not None:
        threshold = rsi_threshold if rsi_threshold is not None else 50.0
        if not math.isfinite(rsi):
            return False
        if direction == PositionDirection.LONG and rsi < threshold:
            return False
        if direction == PositionDirection.SHORT and rsi > threshold:
            return False

    return True


def get_entry_filter_rejection_reason(
    *,
    direction: PositionDirection,
    regime: str,
    adx: Optional[float] = None,
    adx_threshold: Optional[float] = None,
    rsi: Optional[float] = None,
    rsi_threshold: Optional[float] = None,
    is_range_or_compressed: Optional[bool] = None,
) -> Optional[str]:
    """
    Returns the reason an entry would be rejected, or None if filters would pass.

    For research/debugging: use when validate_entry_filters returns False to inspect why.
    Reject reasons: "regime", "range_or_compressed", "adx", "rsi".
    """
    if direction == PositionDirection.LONG and regime != REGIME_TREND_UP:
        return "regime"
    if direction == PositionDirection.SHORT and regime != REGIME_TREND_DOWN:
        return "regime"

    if is_range_or_compressed is True:
        return "range_or_compressed"

    if adx is not None:
        threshold = adx_threshold if adx_threshold is not None else 25.0
        if not math.isfinite(adx) or adx < threshold:
            return "adx"

    if rsi is not None:
        threshold = rsi_threshold if rsi_threshold is not None else 50.0
        if not math.isfinite(rsi):
            return "rsi"
        if direction == PositionDirection.LONG and rsi < threshold:
            return "rsi"
        if direction == PositionDirection.SHORT and rsi > threshold:
            return "rsi"

    return None


def generate_trade_plan_with_filters(
    *,
    bars: list[Bar],
    t: int,
    swing_levels: SwingLevels,
    regime: str,
    stop_loss_manager,
    tp_mode: TakeProfitMode,
    tp_mult: float,
    risk_config: RiskConfig,
    equity: float,
    k_buffer: float = 0.0,
    atr: Optional[float] = None,
    adx: Optional[float] = None,
    adx_threshold: Optional[float] = None,
    rsi: Optional[float] = None,
    rsi_threshold: Optional[float] = None,
    is_range_or_compressed: Optional[bool] = None,
    buying_power_cash: Optional[float] = None,
    position_sizer=size_position,
    use_fixed_tp: bool = True,
    atr_for_sl: Optional[float] = None,
) -> Optional[TradePlan]:
    """
    V2 orchestration: BOS detection layer → Entry filter layer → Trade planning layer.

    Flow:
      1. detect_bos_signal(...)  — BOS detection layer (pure)
      2. validate_entry_filters(...) — Entry filter layer (V2 gating)
      3. plan_trade_from_signal(...) — Trade planning layer (execution)

    Returns TradePlan if all pass, None otherwise.
    EMA/ADX/RSI/compression are passed in; not computed here.
    """
    # BOS detection layer
    bos_signal = detect_bos_signal(
        bars=bars,
        t=t,
        swing_levels=swing_levels,
        k_buffer=k_buffer,
        atr=atr,
    )
    if bos_signal is None:
        return None

    # Entry filter layer (V2)
    if not validate_entry_filters(
        direction=bos_signal.direction,
        regime=regime,
        adx=adx,
        adx_threshold=adx_threshold,
        rsi=rsi,
        rsi_threshold=rsi_threshold,
        is_range_or_compressed=is_range_or_compressed,
    ):
        return None

    # Trade planning layer
    return plan_trade_from_signal(
        bars=bars,
        bos_signal=bos_signal,
        swing_levels=swing_levels,
        stop_loss_manager=stop_loss_manager,
        tp_mode=tp_mode,
        tp_mult=tp_mult,
        risk_config=risk_config,
        equity=equity,
        buying_power_cash=buying_power_cash,
        position_sizer=position_sizer,
        use_fixed_tp=use_fixed_tp,
        atr_for_sl=atr_for_sl if atr_for_sl is not None else atr,
    )


def check_exit_rules(
    *,
    bar: Bar,
    direction: PositionDirection,
    sl_price: float,
    tp_price: Optional[float] = None,
    same_bar_rule: SameBarSlTpRule,
) -> Optional[TradeExit]:
    """
    V1 exit rules (supports SL-only mode when tp_price is None):

    LONG:
      - SL hit if Low <= SL
      - TP hit if High >= TP (when tp_price provided)

    SHORT:
      - SL hit if High >= SL
      - TP hit if Low <= TP (when tp_price provided)

    When tp_price is None (SL-only / dynamic management): only SL is checked.
    Same-bar SL/TP logic does not apply.

    When tp_price is provided: if both SL and TP hit in same bar, tie-breaking applies:
      - WORST_CASE: assume SL first
      - OPEN_PROXIMITY: whichever level is closer to bar.open
      - LOWER_TIMEFRAME: not implemented in this module
    """
    if direction == PositionDirection.LONG:
        sl_hit = bar.low <= sl_price
        tp_hit = bar.high >= tp_price if tp_price is not None else False
    else:
        sl_hit = bar.high >= sl_price
        tp_hit = bar.low <= tp_price if tp_price is not None else False

    if not sl_hit and not tp_hit:
        return None

    if sl_hit and not tp_hit:
        return TradeExit(exit_price=sl_price, exit_reason=ExitReason.SL)

    if tp_hit and not sl_hit:
        assert tp_price is not None  # tp_hit implies tp_price was provided
        return TradeExit(exit_price=tp_price, exit_reason=ExitReason.TP)

    # Both hit in the same bar (tp_price must be present)
    if tp_price is None:
        return TradeExit(exit_price=sl_price, exit_reason=ExitReason.SL)

    if same_bar_rule == SameBarSlTpRule.WORST_CASE:
        return TradeExit(exit_price=sl_price, exit_reason=ExitReason.SL)

    if same_bar_rule == SameBarSlTpRule.OPEN_PROXIMITY:
        sl_dist = abs(bar.open - sl_price)
        tp_dist = abs(bar.open - tp_price)
        if sl_dist <= tp_dist:
            return TradeExit(exit_price=sl_price, exit_reason=ExitReason.SL)
        return TradeExit(exit_price=tp_price, exit_reason=ExitReason.TP)

    if same_bar_rule == SameBarSlTpRule.LOWER_TIMEFRAME:
        raise NotImplementedError(
            "LOWER_TIMEFRAME requires lower timeframe data and must be handled in the backtest engine."
        )

    raise ValueError(f"Unsupported same_bar_rule: {same_bar_rule}")


def check_partial_1r_reached(
    *,
    bar: Bar,
    direction: PositionDirection,
    entry_price: float,
    sl_price: float,
    r_mult: float = 1.0,
) -> bool:
    """
    True if price reached 1R (r_mult * R) on this bar. R = abs(entry - sl).
    LONG: True if bar.high >= entry + r_mult * R.
    SHORT: True if bar.low <= entry - r_mult * R.
    """
    r = abs(entry_price - sl_price)
    if r <= 0:
        return False
    one_r = r_mult * r
    if direction == PositionDirection.LONG:
        return bar.high >= entry_price + one_r
    return bar.low <= entry_price - one_r


def compute_trailing_stop(
    *,
    close: float,
    atr: float,
    direction: PositionDirection,
    old_stop: float,
    k_trail: float,
) -> float:
    """
    Compute new trailing stop from bar close and ATR (trailing updates only after candle close).
    LONG: new_stop = max(old_stop, close - k_trail * ATR)
    SHORT: new_stop = min(old_stop, close + k_trail * ATR)
    """
    if not math.isfinite(atr) or atr <= 0:
        return old_stop
    if direction == PositionDirection.LONG:
        candidate = close - k_trail * atr
        return max(old_stop, candidate)
    candidate = close + k_trail * atr
    return min(old_stop, candidate)
