# region imports
from AlgorithmImports import *
# endregion

from typing import Optional

from project_code.diagnostics import (
    manifest_to_json,
    safe_bool,
    safe_enum,
    safe_float,
    safe_getattr,
    safe_str,
)
from project_code.entry_exit import Bar as SimBar


def _log_market_snapshot(self, tb: TradeBar, sim_bar: SimBar) -> None:
    if not self.log_market_every_bar:
        return
    try:
        ctx = self._get_strategy_context_snapshot(sim_bar_close=sim_bar.close)
        prev_close = (
            safe_float(self.bars_15m[-2].close) if len(self.bars_15m) >= 2 else None
        )
        o, h, l, c = sim_bar.open, sim_bar.high, sim_bar.low, sim_bar.close
        bar_return = (c / prev_close - 1.0) if prev_close and prev_close > 0 else None
        bar_range = h - l
        bar_body = abs(c - o)
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        atr = ctx.get("atr")
        spread = ctx.get("spread")
        spread_to_atr = (spread / atr) if spread is not None and atr and atr > 0 else None
        range_to_atr = (bar_range / atr) if atr and atr > 0 else None
        self.diagnostics.market_trace.log(
            run_id=self.run_id,
            time=str(tb.EndTime),
            symbol=str(self.symbol),
            bar_index=self.bar_index,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=safe_float(sim_bar.volume),
            security_price=ctx.get("security_price"),
            bid_price=ctx.get("bid_price"),
            ask_price=ctx.get("ask_price"),
            spread=spread,
            spread_pct=ctx.get("spread_pct"),
            is_tradable=ctx.get("is_tradable"),
            is_market_open=ctx.get("is_market_open"),
            leverage=ctx.get("leverage"),
            quote_currency=ctx.get("quote_currency"),
            base_currency=ctx.get("base_currency"),
            minimum_price_variation=ctx.get("minimum_price_variation"),
            lot_size=ctx.get("lot_size"),
            bar_return=bar_return,
            bar_range=bar_range,
            bar_body=bar_body,
            upper_wick=upper_wick,
            lower_wick=lower_wick,
            ema=ctx.get("ema"),
            ema_slope=ctx.get("ema_slope"),
            regime=ctx.get("regime"),
            adx=ctx.get("adx"),
            trend_strong=ctx.get("trend_strong"),
            atr=atr,
            true_range=ctx.get("true_range"),
            atr_pct=ctx.get("atr_pct"),
            spread_to_atr=spread_to_atr,
            range_to_atr=range_to_atr,
            last_swing_high=ctx.get("last_swing_high"),
            last_swing_low=ctx.get("last_swing_low"),
            distance_to_swing_high=ctx.get("distance_to_swing_high"),
            distance_to_swing_low=ctx.get("distance_to_swing_low"),
            bars_since_last_swing_high=ctx.get("bars_since_last_swing_high"),
            bars_since_last_swing_low=ctx.get("bars_since_last_swing_low"),
        )
    except Exception:
        pass


def _log_portfolio_snapshot(self, tb: TradeBar) -> None:
    if not self.log_portfolio_every_bar:
        return
    try:
        snap = self._get_portfolio_snapshot()
        self.diagnostics.portfolio_trace.log(
            run_id=self.run_id,
            time=str(tb.EndTime),
            bar_index=self.bar_index,
            **snap,
        )
    except Exception:
        pass


def _log_decision(
    self,
    *,
    tb: TradeBar,
    sim_bar: SimBar,
    bos_direction: Optional[str] = None,
    signal_candle_index: Optional[int] = None,
    entry_candle_index: Optional[int] = None,
    final_decision: str,
    rejection_code: Optional[str] = None,
    rejection_detail: Optional[str] = None,
    passed_regime_filter: Optional[bool] = None,
    passed_adx_filter: Optional[bool] = None,
    passed_risk_filter: Optional[bool] = None,
    passed_bracket_validation: Optional[bool] = None,
    planned_entry: Optional[float] = None,
    planned_sl: Optional[float] = None,
    planned_tp: Optional[float] = None,
    planned_qty: Optional[float] = None,
) -> None:
    try:
        ctx = self._get_strategy_context_snapshot(sim_bar_close=sim_bar.close)
        planned_risk_per_unit = None
        planned_notional = None
        planned_rr = None
        if planned_entry is not None and planned_sl is not None:
            planned_risk_per_unit = abs(planned_entry - planned_sl)
        if planned_entry is not None and planned_qty is not None:
            planned_notional = abs(planned_entry * planned_qty)
        if (
            planned_tp is not None
            and planned_entry is not None
            and planned_risk_per_unit
            and planned_risk_per_unit > 0
        ):
            planned_rr = abs(planned_tp - planned_entry) / planned_risk_per_unit
        self.diagnostics.decision_trace.log(
            run_id=self.run_id,
            time=str(tb.EndTime),
            symbol=str(self.symbol),
            bar_index=self.bar_index,
            state=self.ts.phase,
            close=sim_bar.close,
            last_swing_high=ctx.get("last_swing_high"),
            last_swing_low=ctx.get("last_swing_low"),
            bos_direction=bos_direction,
            signal_candle_index=signal_candle_index,
            entry_candle_index=entry_candle_index,
            regime=ctx.get("regime"),
            adx=ctx.get("adx"),
            trend_strong=ctx.get("trend_strong"),
            atr=ctx.get("atr"),
            spread=ctx.get("spread"),
            spread_pct=ctx.get("spread_pct"),
            passed_regime_filter=passed_regime_filter,
            passed_adx_filter=passed_adx_filter,
            passed_risk_filter=passed_risk_filter,
            passed_bracket_validation=passed_bracket_validation,
            final_decision=final_decision,
            rejection_code=rejection_code,
            rejection_detail=rejection_detail,
            planned_entry=planned_entry,
            planned_sl=planned_sl,
            planned_tp=planned_tp,
            planned_qty=planned_qty,
            planned_risk_per_unit=planned_risk_per_unit,
            planned_notional=planned_notional,
            planned_rr=planned_rr,
            portfolio_cash_at_decision=ctx.get("cash"),
            portfolio_value_at_decision=ctx.get("total_portfolio_value"),
            margin_remaining_at_decision=ctx.get("margin_remaining"),
            open_orders_count=ctx.get("open_orders_count"),
        )
    except Exception:
        pass


def _log_order_event(self, orderEvent: OrderEvent) -> None:
    try:
        ticket = None
        try:
            ticket = self.Transactions.GetOrderTicket(orderEvent.OrderId)
        except Exception:
            pass
        if ticket is None and self.entry_ticket is not None:
            if orderEvent.OrderId == self.entry_ticket.OrderId:
                ticket = self.entry_ticket
        if ticket is None and self.exit_ticket is not None:
            if orderEvent.OrderId == self.exit_ticket.OrderId:
                ticket = self.exit_ticket

        fee_val = None
        try:
            fee_val = safe_float(orderEvent.OrderFee.Value) if orderEvent.OrderFee is not None else None
        except Exception:
            fee_val = safe_float(safe_getattr(orderEvent.OrderFee, "Value"))

        snap = self._get_portfolio_snapshot()
        holding = self.Portfolio[orderEvent.Symbol] if orderEvent.Symbol in self.Portfolio else None
        self.diagnostics.order_event_trace.log(
            run_id=self.run_id,
            time=str(self.Time),
            order_id=orderEvent.OrderId,
            symbol=str(orderEvent.Symbol),
            status=safe_enum(orderEvent.Status),
            direction=safe_enum(orderEvent.Direction),
            fill_price=safe_float(orderEvent.FillPrice),
            fill_price_currency=safe_str(safe_getattr(orderEvent, "FillPriceCurrency")),
            fill_quantity=safe_float(orderEvent.FillQuantity),
            order_fee=fee_val,
            message=safe_str(orderEvent.Message),
            is_assignment=safe_bool(safe_getattr(orderEvent, "IsAssignment")),
            stop_price=safe_float(safe_getattr(ticket, "StopPrice") if ticket else None),
            limit_price=safe_float(safe_getattr(ticket, "LimitPrice") if ticket else None),
            ticket_quantity=safe_float(safe_getattr(ticket, "Quantity") if ticket else None),
            ticket_quantity_filled=safe_float(
                safe_getattr(ticket, "QuantityFilled") if ticket else None
            ),
            ticket_average_fill_price=safe_float(
                safe_getattr(ticket, "AverageFillPrice") if ticket else None
            ),
            ticket_status=safe_enum(safe_getattr(ticket, "Status") if ticket else None),
            ticket_order_type=safe_enum(safe_getattr(ticket, "OrderType") if ticket else None),
            ticket_tag=safe_str(safe_getattr(ticket, "Tag") if ticket else None),
            portfolio_cash_after=snap.get("cash"),
            portfolio_value_after=snap.get("total_portfolio_value"),
            holdings_quantity_after=safe_float(safe_getattr(holding, "Quantity") if holding else None),
            holdings_avg_price_after=safe_float(
                safe_getattr(holding, "AveragePrice") if holding else None
            ),
        )
    except Exception:
        pass


def _save_diagnostics_artifacts(self) -> None:
    summary = self.diagnostics.to_summary_dict()
    files = {
        f"{self.run_id}_market_trace.csv": self.diagnostics.market_trace.to_csv_string(),
        f"{self.run_id}_portfolio_trace.csv": self.diagnostics.portfolio_trace.to_csv_string(),
        f"{self.run_id}_decision_trace.csv": self.diagnostics.decision_trace.to_csv_string(),
        f"{self.run_id}_order_events.csv": self.diagnostics.order_event_trace.to_csv_string(),
        f"{self.run_id}_trade_lifecycle.csv": self.diagnostics.trade_recorder.to_csv_string(),
    }
    risk_budget = safe_float(safe_getattr(self.risk_config, "risk_budget_cash"))
    if risk_budget is None:
        risk_budget = safe_float(safe_getattr(self.risk_config, "risk_pct"))
    manifest = {
        "run_id": self.run_id,
        "symbol": str(self.symbol),
        "timeframe": "15m",
        "start": "2021-01-01",
        "end": "2025-01-01",
        "sl_mode": self.sl_mode,
        "fixed_pct": self.fixed_pct,
        "buffer_pct": self.buffer_pct,
        "tp_mode": self.tp_mode.value if hasattr(self.tp_mode, "value") else str(self.tp_mode),
        "tp_mult": self.tp_mult,
        "same_bar_rule": (
            self.same_bar_rule.value
            if hasattr(self.same_bar_rule, "value")
            else str(self.same_bar_rule)
        ),
        "cooldown_bars": self.cooldown_bars,
        "max_trades_per_day": self.max_trades_per_day,
        "ema_period": self.ema_period,
        "adx_period": self.adx_period,
        "adx_threshold": self.adx_threshold,
        "atr_period": self.atr_period,
        "risk_budget_cash": risk_budget,
        "log_market_every_bar": self.log_market_every_bar,
        "log_portfolio_every_bar": self.log_portfolio_every_bar,
        "log_no_bos_decisions": self.log_no_bos_decisions,
        "no_bos_count": self.no_bos_count,
        "warmup_count": self.warmup_count,
        "position_not_flat_count": self.position_not_flat_count,
        "open_orders_skip_count": self.open_orders_skip_count,
        "diagnostics_summary": summary,
    }
    files[f"{self.run_id}_manifest.json"] = manifest_to_json(manifest)
    for key, content in files.items():
        try:
            self.ObjectStore.Save(key, content)
        except Exception as e:
            self.Debug(f"DIAGNOSTICS SAVE FAILED | {key} | {str(e)[:200]}")
    self.Debug(
        "SAVED DIAGNOSTICS | "
        f"market={summary['market_rows']} "
        f"portfolio={summary['portfolio_rows']} "
        f"decisions={summary['decision_rows']} "
        f"orders={summary['order_event_rows']} "
        f"trades={summary['trade_rows']}"
    )
