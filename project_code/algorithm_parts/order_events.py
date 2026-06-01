# region imports
from AlgorithmImports import *
# endregion

from project_code.utils.state_utils import compute_exit_pnl, finalize_exit


def OnOrderEvent(self, orderEvent: OrderEvent):
    self._log_order_event(orderEvent)
    if orderEvent.Symbol != self.symbol:
        return

    oid = orderEvent.OrderId

    if self.entry_ticket is not None and oid == self.entry_ticket.OrderId:
        self._handle_entry_event(orderEvent)
        return
    if self.exit_ticket is not None and oid == self.exit_ticket.OrderId:
        self._handle_exit_event(orderEvent)
        return

    # Phase-based fallback: handles synchronous fills where OnOrderEvent
    # fires during MarketOrder() before the ticket variable is assigned.
    if self.ts.phase == "ENTRY_SUBMITTED":
        self._handle_entry_event(orderEvent)
        return
    if self.ts.phase == "EXIT_SUBMITTED":
        self._handle_exit_event(orderEvent)
        return

    self._handle_untracked_event(orderEvent)


def _handle_entry_event(self, orderEvent: OrderEvent):
    if orderEvent.Status in [OrderStatus.Filled, OrderStatus.PartiallyFilled]:
        filled_qty = abs(float(orderEvent.FillQuantity))
        if filled_qty == 0:
            return
        if self.ts.entry_fill_time is None:
            fill_price = (
                float(orderEvent.FillPrice)
                if orderEvent.FillPrice > 0
                else float(self.ts.plan.entry_price)
            )
            self.ts.mark_entry_filled(
                fill_price=fill_price,
                fill_time=self.Time,
                qty=filled_qty,
            )
            if self.current_trade_id is None and self.ts.plan is not None:
                self.trade_counter += 1
                self.current_trade_id = f"{self.run_id}_{self.trade_counter}"
                context = self._get_strategy_context_snapshot(sim_bar_close=fill_price)
                signal_time = None
                sig_idx = self.ts.plan.signal_candle_index
                if sig_idx is not None and 0 <= sig_idx < len(self.bars_15m):
                    signal_time = str(self.bars_15m[sig_idx].time)
                self.diagnostics.trade_recorder.log_entry(
                    run_id=self.run_id,
                    trade_id=self.current_trade_id,
                    symbol=str(self.symbol),
                    direction=self.ts.plan.direction.value,
                    signal_time=signal_time,
                    entry_time=str(self.Time),
                    signal_candle_index=self.ts.plan.signal_candle_index,
                    entry_candle_index=self.ts.plan.entry_candle_index,
                    entry_price=fill_price,
                    sl_price=float(self.ts.sl_price) if self.ts.sl_price is not None else None,
                    tp_price=float(self.ts.tp_price) if self.ts.tp_price is not None else None,
                    quantity=filled_qty,
                    notional_entry=abs(filled_qty * fill_price),
                    regime_at_entry=context.get("regime"),
                    adx_at_entry=context.get("adx"),
                    atr_at_entry=context.get("atr"),
                    spread_at_entry=context.get("spread"),
                    spread_pct_at_entry=context.get("spread_pct"),
                    portfolio_value_at_entry=context.get("total_portfolio_value"),
                    cash_at_entry=context.get("cash"),
                    margin_remaining_at_entry=context.get("margin_remaining"),
                )
            self.trades_today += 1
            self.stat_entries += 1
            tp_text = f"{self.ts.tp_price:.2f}" if self.ts.tp_price is not None else "None"
            self.Debug(
                f"ENTRY {self.Time} | Qty={filled_qty:.6f} Entry={fill_price:.2f} "
                f"SL={self.ts.sl_price:.2f} TP={tp_text}"
            )
        else:
            if self.entry_ticket is not None:
                self.ts.active_qty = abs(float(self.entry_ticket.QuantityFilled))
            else:
                self.ts.active_qty += filled_qty
        return

    if orderEvent.Status in [OrderStatus.Canceled, OrderStatus.Invalid]:
        self.stat_entry_reject += 1
        if self._log_count_plan_fail < self.log_limit:
            self.Debug(f"ENTRY REJECTED {self.Time} | {orderEvent.Message}")
            self._log_count_plan_fail += 1
        self._reset_trade(cooldown=False)


def _handle_exit_event(self, orderEvent: OrderEvent):
    if orderEvent.Status in [OrderStatus.Filled, OrderStatus.PartiallyFilled]:
        reason = self.ts.pending_exit_reason or "UNKNOWN"
        is_partial_1r = reason == "PARTIAL_1R"

        if is_partial_1r:
            remaining_qty = float(self.Portfolio[self.symbol].Quantity)
            if abs(remaining_qty) > 1e-12:
                filled_qty = abs(float(orderEvent.FillQuantity))
                fill_px = float(orderEvent.FillPrice) if orderEvent.FillPrice > 0 else None
                pnl = compute_exit_pnl(self.ts, fill_px, qty_closed=filled_qty)
                self.total_trade_pnl += pnl

                trailing_stop = float(self.ts.sl_price) if self.ts.sl_price is not None else 0.0
                self.ts.mark_partial_filled(
                    remaining_qty=remaining_qty,
                    trailing_stop=trailing_stop,
                )
                self.exit_ticket = None
                return

        if orderEvent.Status == OrderStatus.PartiallyFilled:
            return

        fill_price = float(orderEvent.FillPrice) if orderEvent.FillPrice > 0 else None
        result = finalize_exit(self.ts, reason=reason, fill_price=fill_price)
        self.total_trade_pnl += result["pnl"]
        self.stat_exit += 1
        if result["sl_hit"]:
            self.stat_sl += 1
        if result["tp_hit"]:
            self.stat_tp += 1
        model_exit = f"{result['pending_exit_price']:.2f}" if result["pending_exit_price"] is not None else "n/a"
        fill_text = f"{fill_price:.2f}" if fill_price is not None else "n/a"
        self.Debug(f"EXIT {self.Time} | Reason={result['effective_reason']} Fill={fill_text} ModelExit={model_exit}")
        self._log_trade_exit(fill_price=fill_price, reason=result["effective_reason"])
        self._reset_trade(cooldown=True)
        self.current_trade_id = None
        if self.Portfolio[self.symbol].Invested:
            self.Liquidate(self.symbol, "residual cleanup")
        return

    if orderEvent.Status in [OrderStatus.Canceled, OrderStatus.Invalid]:
        if self.Portfolio[self.symbol].Invested:
            self.Liquidate(self.symbol, "Exit order failed")
        self._reset_trade(cooldown=True)


def _handle_untracked_event(self, orderEvent: OrderEvent):
    if (
        orderEvent.Symbol == self.symbol
        and orderEvent.Status in [OrderStatus.Filled, OrderStatus.PartiallyFilled]
        and self.ts.phase in {"OPEN", "EXIT_SUBMITTED"}
        and not self.Portfolio[self.symbol].Invested
        and not self._has_open_orders()
    ):
        message = (orderEvent.Message or "").lower()
        ext_reason = "MARGIN_CALL" if "margin" in message else "EXTERNAL_EXIT"
        fill_price = float(orderEvent.FillPrice) if orderEvent.FillPrice > 0 else None
        result = finalize_exit(self.ts, reason=ext_reason, fill_price=fill_price)
        self.total_trade_pnl += result["pnl"]
        self.stat_exit += 1
        self.stat_external_exit += 1
        if result["sl_hit"]:
            self.stat_sl += 1
        if result["tp_hit"]:
            self.stat_tp += 1
        if self._log_count_state < self.log_limit:
            fill_text = f"{fill_price:.2f}" if fill_price is not None else "n/a"
            self.Debug(
                f"UNTRACKED EXIT {self.Time} | Reason={result['effective_reason']} "
                f"Source={ext_reason} Fill={fill_text}"
            )
            self._log_count_state += 1
        self._log_trade_exit(fill_price=fill_price, reason=result["effective_reason"])
        self._reset_trade(cooldown=True)
        self.current_trade_id = None
