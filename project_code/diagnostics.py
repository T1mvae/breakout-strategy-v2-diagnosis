"""
Diagnostics / observability recorders for BOS breakout strategy backtests.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Optional

import pandas as pd


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        f = float(value)
        if f != f:  # NaN
            return default
        return f
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_str(value: Any, default: Optional[str] = None) -> Optional[str]:
    try:
        if value is None:
            return default
        return str(value)
    except Exception:
        return default


def safe_bool(value: Any, default: Optional[bool] = None) -> Optional[bool]:
    try:
        if value is None:
            return default
        return bool(value)
    except Exception:
        return default


def safe_enum(value: Any, default: Optional[str] = None) -> Optional[str]:
    try:
        if value is None:
            return default
        if isinstance(value, Enum):
            return safe_str(value.value, default)
        return safe_str(value, default)
    except Exception:
        return default


def safe_json(data: Any, default: str = "{}") -> str:
    try:
        return json.dumps(data, default=str)
    except Exception:
        return default


def safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        if obj is None:
            return default
        return getattr(obj, name, default)
    except Exception:
        return default


def manifest_to_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, sort_keys=True, default=str)


class _BaseTrace:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def log(self, row: Optional[dict[str, Any]] = None, **kwargs: Any) -> None:
        if row is not None:
            self.rows.append(dict(row))
        else:
            self.rows.append(dict(kwargs))

    def to_dataframe(self) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame()
        return pd.DataFrame(self.rows)

    def to_csv_string(self) -> str:
        return self.to_dataframe().to_csv(index=False)


class MarketTrace(_BaseTrace):
    pass


class PortfolioTrace(_BaseTrace):
    pass


class DecisionTrace(_BaseTrace):
    pass


class OrderEventTrace(_BaseTrace):
    pass


class TradeRecorder:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self._active: dict[str, dict[str, Any]] = {}

    def log(self, row: Optional[dict[str, Any]] = None, **kwargs: Any) -> None:
        if row is not None:
            self.rows.append(dict(row))
        else:
            self.rows.append(dict(kwargs))

    def log_entry(self, **kwargs: Any) -> None:
        trade_id = safe_str(kwargs.get("trade_id"))
        if not trade_id:
            return
        row = {
            "run_id": kwargs.get("run_id"),
            "trade_id": trade_id,
            "symbol": kwargs.get("symbol"),
            "direction": safe_enum(kwargs.get("direction")),
            "signal_time": kwargs.get("signal_time"),
            "entry_time": kwargs.get("entry_time"),
            "exit_time": None,
            "signal_candle_index": kwargs.get("signal_candle_index"),
            "entry_candle_index": kwargs.get("entry_candle_index"),
            "entry_price": safe_float(kwargs.get("entry_price")),
            "exit_price": None,
            "sl_price": safe_float(kwargs.get("sl_price")),
            "tp_price": safe_float(kwargs.get("tp_price")),
            "quantity": safe_float(kwargs.get("quantity")),
            "notional_entry": safe_float(kwargs.get("notional_entry")),
            "exit_reason": None,
            "r_multiple": None,
            "pnl_cash": None,
            "pnl_pct": None,
            "fees_total": None,
            "holding_bars": None,
            "holding_minutes": None,
            "mfe_price": 0.0,
            "mae_price": 0.0,
            "mfe_r": None,
            "mae_r": None,
            "regime_at_entry": kwargs.get("regime_at_entry"),
            "adx_at_entry": safe_float(kwargs.get("adx_at_entry")),
            "atr_at_entry": safe_float(kwargs.get("atr_at_entry")),
            "spread_at_entry": safe_float(kwargs.get("spread_at_entry")),
            "spread_pct_at_entry": safe_float(kwargs.get("spread_pct_at_entry")),
            "portfolio_value_at_entry": safe_float(kwargs.get("portfolio_value_at_entry")),
            "cash_at_entry": safe_float(kwargs.get("cash_at_entry")),
            "margin_remaining_at_entry": safe_float(kwargs.get("margin_remaining_at_entry")),
            "regime_at_exit": None,
            "adx_at_exit": None,
            "atr_at_exit": None,
            "spread_at_exit": None,
            "spread_pct_at_exit": None,
            "portfolio_value_at_exit": None,
            "cash_at_exit": None,
            "margin_remaining_at_exit": None,
            "_entry_bar_index": safe_int(kwargs.get("entry_candle_index")),
            "_last_bar_index": safe_int(kwargs.get("entry_candle_index")),
            "_entry_time_str": kwargs.get("entry_time"),
        }
        self._active[trade_id] = row
        self.rows.append(row)

    def update_excursions(
        self,
        *,
        trade_id: str,
        bar_high: float,
        bar_low: float,
        current_bar_index: Optional[int] = None,
        current_time: Optional[str] = None,
    ) -> None:
        row = self._active.get(trade_id)
        if row is None:
            return
        entry_price = safe_float(row.get("entry_price"))
        sl_price = safe_float(row.get("sl_price"))
        direction = safe_str(row.get("direction"), "") or ""
        if entry_price is None or sl_price is None:
            return
        risk = abs(entry_price - sl_price)
        if risk <= 0:
            return

        bh = float(bar_high)
        bl = float(bar_low)
        if direction.upper() == "LONG":
            favorable = bh - entry_price
            adverse = entry_price - bl
        else:
            favorable = entry_price - bl
            adverse = bh - entry_price

        favorable = max(0.0, favorable)
        adverse = max(0.0, adverse)

        row["mfe_price"] = max(safe_float(row.get("mfe_price"), 0.0) or 0.0, favorable)
        row["mae_price"] = max(safe_float(row.get("mae_price"), 0.0) or 0.0, adverse)
        row["mfe_r"] = row["mfe_price"] / risk
        row["mae_r"] = row["mae_price"] / risk
        if current_bar_index is not None:
            row["_last_bar_index"] = current_bar_index
        if current_time is not None:
            row["_last_time_str"] = current_time

    def log_exit(self, *, trade_id: str, **kwargs: Any) -> None:
        row = self._active.get(trade_id)
        if row is None:
            for r in reversed(self.rows):
                if r.get("trade_id") == trade_id:
                    row = r
                    break
        if row is None:
            return

        exit_price = safe_float(kwargs.get("exit_price"))
        entry_price = safe_float(row.get("entry_price"))
        sl_price = safe_float(row.get("sl_price"))
        direction = safe_str(row.get("direction"), "") or ""
        quantity = safe_float(row.get("quantity"))

        row["exit_time"] = kwargs.get("exit_time")
        row["exit_price"] = exit_price
        row["exit_reason"] = kwargs.get("exit_reason")
        row["regime_at_exit"] = kwargs.get("regime_at_exit")
        row["adx_at_exit"] = safe_float(kwargs.get("adx_at_exit"))
        row["atr_at_exit"] = safe_float(kwargs.get("atr_at_exit"))
        row["spread_at_exit"] = safe_float(kwargs.get("spread_at_exit"))
        row["spread_pct_at_exit"] = safe_float(kwargs.get("spread_pct_at_exit"))
        row["portfolio_value_at_exit"] = safe_float(kwargs.get("portfolio_value_at_exit"))
        row["cash_at_exit"] = safe_float(kwargs.get("cash_at_exit"))
        row["margin_remaining_at_exit"] = safe_float(kwargs.get("margin_remaining_at_exit"))
        if kwargs.get("fees_total") is not None:
            row["fees_total"] = safe_float(kwargs.get("fees_total"))

        if entry_price is not None and exit_price is not None and sl_price is not None:
            risk = abs(entry_price - sl_price)
            if risk > 0:
                if direction.upper() == "LONG":
                    row["r_multiple"] = (exit_price - entry_price) / risk
                else:
                    row["r_multiple"] = (entry_price - exit_price) / risk
                if quantity is not None:
                    if direction.upper() == "LONG":
                        row["pnl_cash"] = (exit_price - entry_price) * quantity
                    else:
                        row["pnl_cash"] = (entry_price - exit_price) * abs(quantity)
                    notional = safe_float(row.get("notional_entry"))
                    if notional and notional > 0 and row["pnl_cash"] is not None:
                        row["pnl_pct"] = row["pnl_cash"] / notional

        entry_bi = safe_int(row.get("_entry_bar_index"))
        last_bi = safe_int(row.get("_last_bar_index"))
        if entry_bi is not None and last_bi is not None:
            row["holding_bars"] = max(0, last_bi - entry_bi)

        self._active.pop(trade_id, None)

    def to_dataframe(self) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame()
        clean_rows = []
        for r in self.rows:
            clean_rows.append({k: v for k, v in r.items() if not str(k).startswith("_")})
        return pd.DataFrame(clean_rows)

    def to_csv_string(self) -> str:
        return self.to_dataframe().to_csv(index=False)


class DiagnosticsBundle:
    def __init__(self) -> None:
        self.market_trace = MarketTrace()
        self.portfolio_trace = PortfolioTrace()
        self.decision_trace = DecisionTrace()
        self.order_event_trace = OrderEventTrace()
        self.trade_recorder = TradeRecorder()

    def to_summary_dict(self) -> dict[str, int]:
        return {
            "market_rows": len(self.market_trace.rows),
            "portfolio_rows": len(self.portfolio_trace.rows),
            "decision_rows": len(self.decision_trace.rows),
            "order_event_rows": len(self.order_event_trace.rows),
            "trade_rows": len(self.trade_recorder.rows),
        }
