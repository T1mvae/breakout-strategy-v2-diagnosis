# region imports
from AlgorithmImports import *
# endregion

from project_code.entry_exit import (
    Bar as SimBar,
    PositionDirection,
    detect_bos_signal,
    generate_trade_plan_with_filters,
    get_entry_filter_rejection_reason,
)
from project_code.risk import size_position_detailed
from project_code.utils.trade_math import (
    is_valid_entry_levels,
    round_price_for_security,
    round_quantity_for_security,
)


def _try_entry(self, tb: TradeBar, sim_bar: SimBar):
    signal_t = len(self.bars_15m) - 2
    if signal_t < 0:
        return
    if float(self.Portfolio.TotalPortfolioValue) < self.min_equity:
        return

    regime = self.regime_values[signal_t]
    adx_value = self.adx_values[signal_t] if self.adx_enabled else None
    rsi_value = self.rsi_values[signal_t] if self.rsi_enabled and signal_t < len(self.rsi_values) else None
    is_compressed = self.compression_values[signal_t] if self.compression_enabled else None
    atr_for_bos = self.atr_breakout_values[signal_t]

    bos_probe = detect_bos_signal(
        bars=self.bars_15m,
        t=signal_t,
        swing_levels=self.swing_levels,
        k_buffer=self.k_buffer,
        atr=atr_for_bos,
    )
    if bos_probe is None:
        self.no_bos_count += 1
        if self.log_no_bos_decisions:
            self._log_decision(
                tb=tb,
                sim_bar=sim_bar,
                final_decision="SKIP",
                rejection_code="NO_BOS",
            )
        self.stop_loss_manager.reset()
        return

    self.stat_bos += 1
    self.stat_signal_candidates += 1
    bos_direction = bos_probe.direction.value

    self.stop_loss_manager.reset()
    self._last_sizing_result = None

    try:
        plan = generate_trade_plan_with_filters(
            bars=self.bars_15m,
            t=signal_t,
            swing_levels=self.swing_levels,
            regime=regime,
            stop_loss_manager=self.stop_loss_manager,
            tp_mode=self.tp_mode,
            tp_mult=self.tp_mult,
            risk_config=self.risk_config,
            equity=float(self.Portfolio.TotalPortfolioValue),
            k_buffer=self.k_buffer,
            atr=atr_for_bos,
            adx=adx_value,
            adx_threshold=self.adx_threshold if self.adx_enabled else None,
            rsi=rsi_value,
            rsi_threshold=self.rsi_threshold if self.rsi_enabled else None,
            is_range_or_compressed=is_compressed,
            buying_power_cash=float(self.Portfolio.Cash),
            position_sizer=self._position_sizer_fractional,
            use_fixed_tp=self.use_fixed_tp,
            atr_for_sl=atr_for_bos,
        )
    except Exception as e:
        self.stop_loss_manager.reset()
        self.stat_plan_fail += 1
        self.stat_other_fail += 1
        if "Position sizing refused" in str(e) or self._last_sizing_result is not None:
            self.stat_risk_refused += 1
            if self._log_count_sizing < self.log_limit:
                reason = (
                    self._last_sizing_result.refusal_reason
                    if self._last_sizing_result is not None
                    else str(e)
                )
                self.Debug(f"SIZE REFUSE {tb.EndTime} | {reason}")
                self._log_count_sizing += 1
        if self._log_count_plan_fail < self.log_limit:
            self.Debug(f"PLAN FAIL {tb.EndTime} | {e}")
            self._log_count_plan_fail += 1
        self._log_decision(
            tb=tb,
            sim_bar=sim_bar,
            bos_direction=bos_direction,
            signal_candle_index=signal_t,
            final_decision="REJECT",
            rejection_code="PLAN_FAIL",
            rejection_detail=str(e)[:300],
        )
        return

    if plan is None:
        self.stat_filter_blocked += 1
        reason = get_entry_filter_rejection_reason(
            direction=bos_probe.direction,
            regime=regime,
            adx=adx_value,
            adx_threshold=self.adx_threshold if self.adx_enabled else None,
            rsi=rsi_value,
            rsi_threshold=self.rsi_threshold if self.rsi_enabled else None,
            is_range_or_compressed=is_compressed,
        )
        if reason in self.stat_filter_reject_reasons:
            self.stat_filter_reject_reasons[reason] += 1
        if self._log_count_filter < self.log_limit:
            self.Debug(
                f"FILTER BLOCK {tb.EndTime} | Dir={bos_probe.direction.value} Regime={regime} "
                f"ADX={adx_value if adx_value is not None else 'n/a'} "
                f"RSI={rsi_value if rsi_value is not None else 'n/a'} "
                f"Compressed={is_compressed} Reason={reason or 'unknown'}"
            )
            self._log_count_filter += 1
        rejection_code = "FILTER_FAIL"
        if reason == "regime":
            rejection_code = "REGIME_FILTER_FAIL"
        elif reason == "adx":
            rejection_code = "ADX_FILTER_FAIL"
        self._log_decision(
            tb=tb,
            sim_bar=sim_bar,
            bos_direction=bos_direction,
            signal_candle_index=signal_t,
            final_decision="REJECT",
            rejection_code=rejection_code,
            rejection_detail=reason,
            passed_regime_filter=reason != "regime",
            passed_adx_filter=reason != "adx",
        )
        return

    expected_entry_index = len(self.bars_15m) - 1
    if plan.entry_candle_index != expected_entry_index:
        self.stat_plan_fail += 1
        if self._log_count_plan_fail < self.log_limit:
            self.Debug(
                f"PLAN INDEX MISMATCH {tb.EndTime} | signal_t={signal_t} "
                f"plan.entry_candle_index={plan.entry_candle_index} expected={expected_entry_index}"
            )
            self._log_count_plan_fail += 1
        return

    self._log_signal_accepted(tb, plan, regime, adx_value, rsi_value, is_compressed)

    signed_qty = plan.quantity if plan.direction == PositionDirection.LONG else -plan.quantity
    signed_qty = round_quantity_for_security(
        self.Securities[self.symbol], float(signed_qty), self.qty_decimals
    )
    if signed_qty == 0:
        self.stat_skip_qty0 += 1
        self._log_decision(
            tb=tb,
            sim_bar=sim_bar,
            bos_direction=bos_direction,
            signal_candle_index=plan.signal_candle_index,
            entry_candle_index=plan.entry_candle_index,
            final_decision="REJECT",
            rejection_code="QTY_ZERO",
            planned_entry=float(plan.entry_price),
            planned_sl=float(plan.sl_price),
            planned_tp=float(plan.tp_price) if plan.tp_price is not None else None,
            planned_qty=float(plan.quantity),
            passed_regime_filter=True,
            passed_adx_filter=True,
            passed_risk_filter=True,
        )
        return

    sl_price = round_price_for_security(self.Securities[self.symbol], float(plan.sl_price))
    tp_price = (
        round_price_for_security(self.Securities[self.symbol], float(plan.tp_price))
        if plan.tp_price is not None
        else None
    )

    if not is_valid_entry_levels(plan.direction, float(plan.entry_price), sl_price, tp_price):
        self.stat_plan_fail += 1
        self._log_decision(
            tb=tb,
            sim_bar=sim_bar,
            bos_direction=bos_direction,
            signal_candle_index=plan.signal_candle_index,
            entry_candle_index=plan.entry_candle_index,
            final_decision="REJECT",
            rejection_code="INVALID_BRACKET",
            planned_entry=float(plan.entry_price),
            planned_sl=sl_price,
            planned_tp=tp_price,
            planned_qty=float(plan.quantity),
            passed_regime_filter=True,
            passed_adx_filter=True,
            passed_risk_filter=True,
            passed_bracket_validation=False,
        )
        return

    self.ts.submit_entry(plan=plan, sl=sl_price, tp=tp_price)
    self.entry_ticket = self.MarketOrder(
        self.symbol,
        signed_qty,
        tag=f"ENTRY|{plan.direction.value}|sig={plan.signal_candle_index}",
    )
    self.stat_plan_ok += 1
    self._log_decision(
        tb=tb,
        sim_bar=sim_bar,
        bos_direction=bos_direction,
        signal_candle_index=plan.signal_candle_index,
        entry_candle_index=plan.entry_candle_index,
        final_decision="ENTRY_SUBMITTED",
        rejection_code=None,
        passed_regime_filter=True,
        passed_adx_filter=True,
        passed_risk_filter=True,
        passed_bracket_validation=True,
        planned_entry=float(plan.entry_price),
        planned_sl=sl_price,
        planned_tp=tp_price,
        planned_qty=float(plan.quantity),
    )


def _position_sizer_fractional(self, **kwargs):
    result = size_position_detailed(
        **kwargs,
        round_func=lambda x: float(round(x, self.qty_decimals)),
    )
    self._last_sizing_result = result
    if not result.accepted:
        return None, result.refusal_reason
    qty = result.qty
    if qty is not None and qty <= 0:
        return None, "qty <= 0 after rounding"
    return qty, None


def _log_signal_accepted(self, tb, plan, regime, adx_value, rsi_value, is_compressed):
    if self._log_count_signal >= self.log_limit:
        self.stat_signal_accepted += 1
        return
    sizing = self._last_sizing_result
    sizing_text = ""
    if sizing is not None and sizing.accepted and sizing.qty is not None:
        if len(sizing.caps_applied) > 0:
            self.stat_size_capped += 1
        sizing_text = (
            f" | Qty={sizing.qty:.6f} Notional={sizing.notional:.2f} "
            f"Stop={sizing.stop_distance:.4f}({100*sizing.stop_distance_pct:.3f}%) "
            f"TargetRisk={sizing.target_risk_cash:.2f} "
            f"ActualRisk={sizing.actual_risk_cash:.2f}({100*sizing.actual_risk_pct:.3f}%) "
            f"Caps={','.join(sizing.caps_applied) if sizing.caps_applied else 'none'}"
        )
    self.Debug(
        f"SIGNAL ACCEPT {tb.EndTime} | Dir={plan.direction.value} Regime={regime} "
        f"ADX={adx_value if adx_value is not None else 'n/a'} "
        f"RSI={rsi_value if rsi_value is not None else 'n/a'} "
        f"Compressed={is_compressed} TP={'on' if plan.tp_price is not None else 'off'}"
        f"{sizing_text}"
    )
    self._log_count_signal += 1
    self.stat_signal_accepted += 1
