# region imports
from AlgorithmImports import *
# endregion

from typing import Any, Optional

import pandas as pd

from project_code.adx_filter import compute_adx_series
from project_code.atr_module import compute_atr_series, compute_true_range
from project_code.diagnostics import (
    safe_bool,
    safe_float,
    safe_getattr,
    safe_json,
    safe_str,
)
from project_code.ma_regime_filter import compute_regime_series


def _bars_to_dataframe(self) -> pd.DataFrame:
    if not self.bars_15m:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    rows = []
    for b in self.bars_15m:
        rows.append(
            {
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": safe_float(b.volume, 0.0),
            }
        )
    return pd.DataFrame(rows)


def _get_indicator_snapshot(self) -> dict[str, Any]:
    empty = {
        "ema": None,
        "ema_slope": None,
        "regime": None,
        "adx": None,
        "trend_strong": None,
        "atr": None,
        "true_range": None,
        "atr_pct": None,
    }
    try:
        df = self._bars_to_dataframe()
        if df.empty:
            return dict(empty)
        close = df["close"]
        high = df["high"]
        low = df["low"]
        regime_df = compute_regime_series(close, self.ema_period)
        adx_df = compute_adx_series(
            high, low, close, self.adx_period, self.adx_threshold
        )
        atr_df = compute_atr_series(high, low, close, self.atr_period)
        tr = compute_true_range(high, low, close)
        last_close = safe_float(close.iloc[-1])
        ema = safe_float(regime_df["ema"].iloc[-1])
        ema_slope = safe_float(regime_df["ema_slope"].iloc[-1])
        regime = safe_str(regime_df["regime"].iloc[-1])
        adx = safe_float(adx_df["adx"].iloc[-1])
        trend_strong = safe_bool(adx_df["trend_strong"].iloc[-1])
        atr = safe_float(atr_df["atr"].iloc[-1])
        true_range = safe_float(tr.iloc[-1])
        atr_pct = (atr / last_close) if atr is not None and last_close and last_close > 0 else None
        return {
            "ema": ema,
            "ema_slope": ema_slope,
            "regime": regime,
            "adx": adx,
            "trend_strong": trend_strong,
            "atr": atr,
            "true_range": true_range,
            "atr_pct": atr_pct,
        }
    except Exception:
        if self.regime_values:
            empty["regime"] = self.regime_values[-1]
        if self.adx_values:
            empty["adx"] = safe_float(self.adx_values[-1])
            empty["trend_strong"] = (
                safe_float(self.adx_values[-1]) > self.adx_threshold
                if self.adx_enabled
                else None
            )
        if self.atr_breakout_values:
            empty["atr"] = safe_float(self.atr_breakout_values[-1])
        return empty


def _get_security_snapshot(self) -> dict[str, Any]:
    out: dict[str, Any] = {
        "security_price": None,
        "bid_price": None,
        "ask_price": None,
        "spread": None,
        "spread_pct": None,
        "is_tradable": None,
        "is_market_open": None,
        "leverage": None,
        "quote_currency": None,
        "base_currency": None,
        "minimum_price_variation": None,
        "lot_size": None,
    }
    try:
        security = self.Securities[self.symbol]
        out["security_price"] = safe_float(security.Price)
        out["bid_price"] = safe_float(safe_getattr(security, "BidPrice"))
        out["ask_price"] = safe_float(safe_getattr(security, "AskPrice"))
        out["is_tradable"] = safe_bool(safe_getattr(security, "IsTradable"))
        exchange = safe_getattr(security, "Exchange")
        if exchange is not None:
            try:
                out["is_market_open"] = safe_bool(exchange.DateTimeIsOpen(self.Time))
            except Exception:
                pass
        out["leverage"] = safe_float(safe_getattr(security, "Leverage"))
        props = safe_getattr(security, "SymbolProperties")
        if props is not None:
            out["minimum_price_variation"] = safe_float(
                safe_getattr(props, "MinimumPriceVariation")
            )
            out["lot_size"] = safe_float(safe_getattr(props, "LotSize"))
            out["quote_currency"] = safe_str(safe_getattr(props, "QuoteCurrency"))
            out["base_currency"] = safe_str(safe_getattr(props, "BaseCurrency"))
        bid = out["bid_price"]
        ask = out["ask_price"]
        px = out["security_price"]
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            out["spread"] = ask - bid
            if px is not None and px > 0:
                out["spread_pct"] = out["spread"] / px
    except Exception:
        pass
    return out


def _get_portfolio_snapshot(self) -> dict[str, Any]:
    out: dict[str, Any] = {
        "total_portfolio_value": None,
        "cash": None,
        "margin_remaining": None,
        "total_margin_used": None,
        "total_fees": None,
        "total_unrealized_profit": None,
        "total_profit": None,
        "net_profit": None,
        "is_invested": None,
        "symbol_invested": None,
        "symbol_quantity": None,
        "symbol_absolute_quantity": None,
        "symbol_average_price": None,
        "symbol_holdings_value": None,
        "symbol_unrealized_profit": None,
        "symbol_unrealized_profit_percent": None,
        "open_orders_count": None,
        "open_orders_quantity": None,
        "open_orders_value_estimate": None,
        "cashbook_json": "{}",
    }
    try:
        p = self.Portfolio
        out["total_portfolio_value"] = safe_float(p.TotalPortfolioValue)
        out["cash"] = safe_float(p.Cash)
        out["margin_remaining"] = safe_float(safe_getattr(p, "MarginRemaining"))
        out["total_margin_used"] = safe_float(safe_getattr(p, "TotalMarginUsed"))
        out["total_fees"] = safe_float(safe_getattr(p, "TotalFees"))
        out["total_unrealized_profit"] = safe_float(safe_getattr(p, "TotalUnrealizedProfit"))
        out["total_profit"] = safe_float(safe_getattr(p, "TotalProfit"))
        out["net_profit"] = safe_float(safe_getattr(p, "NetProfit"))
        out["is_invested"] = safe_bool(p.Invested)
        holding = p[self.symbol]
        out["symbol_invested"] = safe_bool(safe_getattr(holding, "Invested"))
        out["symbol_quantity"] = safe_float(safe_getattr(holding, "Quantity"))
        out["symbol_absolute_quantity"] = safe_float(safe_getattr(holding, "AbsoluteQuantity"))
        out["symbol_average_price"] = safe_float(safe_getattr(holding, "AveragePrice"))
        out["symbol_holdings_value"] = safe_float(safe_getattr(holding, "HoldingsValue"))
        out["symbol_unrealized_profit"] = safe_float(safe_getattr(holding, "UnrealizedProfit"))
        out["symbol_unrealized_profit_percent"] = safe_float(
            safe_getattr(holding, "UnrealizedProfitPercent")
        )
        open_orders = self.Transactions.GetOpenOrders(self.symbol)
        out["open_orders_count"] = len(open_orders)
        qty_sum = 0.0
        value_est = 0.0
        px = safe_float(self.Securities[self.symbol].Price) or 0.0
        for order in open_orders:
            q = safe_float(safe_getattr(order, "Quantity"), 0.0) or 0.0
            qty_sum += abs(q)
            value_est += abs(q) * px
        out["open_orders_quantity"] = qty_sum
        out["open_orders_value_estimate"] = value_est
        cashbook_rows = []
        cashbook = safe_getattr(p, "CashBook")
        if cashbook is not None:
            try:
                for kvp in cashbook:
                    try:
                        currency = safe_getattr(kvp, "Key")
                        cash = safe_getattr(kvp, "Value")
                    except Exception:
                        continue

                    cashbook_rows.append(
                        {
                            "currency": safe_str(currency),
                            "amount": safe_float(safe_getattr(cash, "Amount")),
                            "value_in_account_currency": safe_float(
                                safe_getattr(cash, "ValueInAccountCurrency")
                            ),
                            "conversion_rate": safe_float(
                                safe_getattr(cash, "ConversionRate")
                            ),
                            "symbol": safe_str(safe_getattr(cash, "Symbol")),
                        }
                    )
            except Exception:
                pass
        out["cashbook_json"] = safe_json(cashbook_rows)
    except Exception:
        pass
    return out


def _get_strategy_context_snapshot(self, sim_bar_close: Optional[float] = None) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    try:
        ctx.update(self._get_indicator_snapshot())
    except Exception:
        pass

    try:
        ctx.update(self._get_security_snapshot())
    except Exception:
        pass

    try:
        ctx.update(self._get_portfolio_snapshot())
    except Exception:
        pass
    close = sim_bar_close
    if close is None and self.bars_15m:
        close = safe_float(self.bars_15m[-1].close)
    hi = safe_float(self.swing_levels.last_swing_high_price)
    lo = safe_float(self.swing_levels.last_swing_low_price)
    ctx["last_swing_high"] = hi
    ctx["last_swing_low"] = lo
    if close is not None and hi is not None:
        ctx["distance_to_swing_high"] = close - hi
    else:
        ctx["distance_to_swing_high"] = None
    if close is not None and lo is not None:
        ctx["distance_to_swing_low"] = close - lo
    else:
        ctx["distance_to_swing_low"] = None
    if self.last_swing_high_bar_index is not None:
        ctx["bars_since_last_swing_high"] = self.bar_index - self.last_swing_high_bar_index
    else:
        ctx["bars_since_last_swing_high"] = None
    if self.last_swing_low_bar_index is not None:
        ctx["bars_since_last_swing_low"] = self.bar_index - self.last_swing_low_bar_index
    else:
        ctx["bars_since_last_swing_low"] = None
    return ctx
