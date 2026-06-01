import math
from collections import deque
from typing import Optional


class WilderSmoother:
    def __init__(self, period: int):
        if period <= 0:
            raise ValueError(f"period must be > 0, got {period}")
        self.period = period
        self._seed_values: list[float] = []
        self.value: Optional[float] = None

    def update(self, x: float) -> float:
        xv = float(x)
        if self.value is None:
            self._seed_values.append(xv)
            if len(self._seed_values) < self.period:
                return float("nan")
            self.value = sum(self._seed_values) / self.period
            return self.value
        self.value = ((self.value * (self.period - 1)) + xv) / self.period
        return self.value


class AtrEngine:
    def __init__(self, period: int):
        self.period = period
        self._prev_close: Optional[float] = None
        self._smooth = WilderSmoother(period)
        self._count = 0

    def update(self, high: float, low: float, close: float) -> float:
        h, l, c = float(high), float(low), float(close)
        if self._prev_close is None:
            tr = max(h - l, 0.0)
        else:
            tr = max(h - l, abs(h - self._prev_close), abs(l - self._prev_close), 0.0)
        self._prev_close = c
        self._count += 1
        atr = self._smooth.update(tr)
        if self._count < self.period:
            return float("nan")
        return float(atr)


class AdxEngine:
    def __init__(self, period: int):
        self.period = period
        self._prev_high: Optional[float] = None
        self._prev_low: Optional[float] = None
        self._prev_close: Optional[float] = None
        self._tr_smooth = WilderSmoother(period)
        self._plus_dm_smooth = WilderSmoother(period)
        self._minus_dm_smooth = WilderSmoother(period)
        self._adx_smooth = WilderSmoother(period)

    def update(self, high: float, low: float, close: float) -> float:
        h, l, c = float(high), float(low), float(close)
        if self._prev_close is None:
            tr = max(h - l, 0.0)
            plus_dm = 0.0
            minus_dm = 0.0
        else:
            tr = max(h - l, abs(h - self._prev_close), abs(l - self._prev_close), 0.0)
            up_move = h - self._prev_high  # type: ignore[arg-type]
            down_move = self._prev_low - l  # type: ignore[operator]
            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

        self._prev_high = h
        self._prev_low = l
        self._prev_close = c

        atr = self._tr_smooth.update(tr)
        plus_dm_s = self._plus_dm_smooth.update(plus_dm)
        minus_dm_s = self._minus_dm_smooth.update(minus_dm)

        if not math.isfinite(atr) or atr <= 1e-10 or not math.isfinite(plus_dm_s) or not math.isfinite(minus_dm_s):
            dx = 0.0
        else:
            plus_di = 100.0 * plus_dm_s / atr
            minus_di = 100.0 * minus_dm_s / atr
            di_sum = plus_di + minus_di
            dx = 0.0 if di_sum <= 1e-10 else 100.0 * abs(plus_di - minus_di) / di_sum

        adx = self._adx_smooth.update(dx)
        if not math.isfinite(adx):
            return 0.0
        return float(adx)


class EmaRegimeEngine:
    def __init__(self, period: int):
        if period <= 0:
            raise ValueError(f"period must be > 0, got {period}")
        self.period = period
        self._alpha = 2.0 / (period + 1.0)
        self._ema: Optional[float] = None
        self._prev_ema: Optional[float] = None
        self._count = 0

    def update(self, close: float) -> str:
        c = float(close)
        if self._ema is None:
            self._ema = c
            self._prev_ema = None
            self._count += 1
            return "range"
        self._prev_ema = self._ema
        self._ema = (c * self._alpha) + (self._ema * (1.0 - self._alpha))
        self._count += 1
        if self._count < self.period or self._prev_ema is None:
            return "range"
        slope = self._ema - self._prev_ema
        if c > self._ema and slope > 0:
            return "trend_up"
        if c < self._ema and slope < 0:
            return "trend_down"
        return "range"


class CompressionEngine:
    def __init__(self, lookback: int, atr_multiplier: float):
        if lookback <= 0:
            raise ValueError(f"lookback must be > 0, got {lookback}")
        if atr_multiplier <= 0:
            raise ValueError(f"atr_multiplier must be > 0, got {atr_multiplier}")
        self.lookback = lookback
        self.atr_multiplier = float(atr_multiplier)
        self._highs: deque[float] = deque(maxlen=lookback)
        self._lows: deque[float] = deque(maxlen=lookback)

    def update(self, high: float, low: float, atr: float) -> bool:
        self._highs.append(float(high))
        self._lows.append(float(low))
        if len(self._highs) < self.lookback:
            return False
        if not math.isfinite(atr) or atr <= 0:
            return False
        range_width = max(self._highs) - min(self._lows)
        return range_width <= (float(atr) * self.atr_multiplier)
