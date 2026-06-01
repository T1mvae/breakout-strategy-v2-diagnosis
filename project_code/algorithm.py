# region imports
from AlgorithmImports import *
# endregion

from project_code.config_setup import configure
from project_code.entry_exit import Bar as SimBar
from project_code.utils.state_utils import finalize_exit
from project_code.utils.trade_math import safe_final_price

from project_code.algorithm_parts.entry_logic import (
    _try_entry,
    _position_sizer_fractional,
    _log_signal_accepted,
)

from project_code.algorithm_parts.exit_logic import (
    _try_exit_with_v2_rules,
    _update_active_trade_excursions,
    _log_trade_exit,
)

from project_code.algorithm_parts.order_events import (
    OnOrderEvent,
    _handle_entry_event,
    _handle_exit_event,
    _handle_untracked_event,
)

from project_code.algorithm_parts.state_runtime import (
    _reset_trade,
    _heal,
    _has_open_orders,
    _update_swings,
)

from project_code.algorithm_parts.snapshots import (
    _bars_to_dataframe,
    _get_indicator_snapshot,
    _get_security_snapshot,
    _get_portfolio_snapshot,
    _get_strategy_context_snapshot,
)

from project_code.algorithm_parts.diagnostics_runtime import (
    _log_market_snapshot,
    _log_portfolio_snapshot,
    _log_decision,
    _log_order_event,
    _save_diagnostics_artifacts,
)

from project_code.algorithm_parts.plotting import _plot_levels


class BosBreakoutBtc15m(QCAlgorithm):
    _try_entry = _try_entry
    _position_sizer_fractional = _position_sizer_fractional
    _log_signal_accepted = _log_signal_accepted

    _try_exit_with_v2_rules = _try_exit_with_v2_rules
    _update_active_trade_excursions = _update_active_trade_excursions
    _log_trade_exit = _log_trade_exit

    OnOrderEvent = OnOrderEvent
    _handle_entry_event = _handle_entry_event
    _handle_exit_event = _handle_exit_event
    _handle_untracked_event = _handle_untracked_event

    _reset_trade = _reset_trade
    _heal = _heal
    _has_open_orders = _has_open_orders
    _update_swings = _update_swings

    _bars_to_dataframe = _bars_to_dataframe
    _get_indicator_snapshot = _get_indicator_snapshot
    _get_security_snapshot = _get_security_snapshot
    _get_portfolio_snapshot = _get_portfolio_snapshot
    _get_strategy_context_snapshot = _get_strategy_context_snapshot

    _log_market_snapshot = _log_market_snapshot
    _log_portfolio_snapshot = _log_portfolio_snapshot
    _log_decision = _log_decision
    _log_order_event = _log_order_event
    _save_diagnostics_artifacts = _save_diagnostics_artifacts

    _plot_levels = _plot_levels

    def Initialize(self):
        configure(self)

    def OnData(self, data: Slice):
        pass

    def On15MinuteBar(self, sender, tb: TradeBar):
        sim_bar = SimBar(
            open=float(tb.Open),
            high=float(tb.High),
            low=float(tb.Low),
            close=float(tb.Close),
            volume=float(tb.Volume) if tb.Volume is not None else None,
            time=str(tb.EndTime),
        )

        self.bars_15m.append(sim_bar)
        self.bar_index += 1

        self._log_market_snapshot(tb, sim_bar)
        self._log_portfolio_snapshot(tb)

        rsi_now = self.rsi_engine.update(sim_bar.close)
        atr_breakout_now = self.atr_breakout_engine.update(sim_bar.high, sim_bar.low, sim_bar.close)
        atr_trailing_now = (
            atr_breakout_now
            if self.atr_trailing_engine is self.atr_breakout_engine
            else self.atr_trailing_engine.update(sim_bar.high, sim_bar.low, sim_bar.close)
        )
        adx_now = self.adx_engine.update(sim_bar.high, sim_bar.low, sim_bar.close)
        regime_now = self.regime_engine.update(sim_bar.close)
        compressed_now = self.compression_engine.update(sim_bar.high, sim_bar.low, atr_breakout_now)

        self.rsi_values.append(rsi_now)
        self.atr_breakout_values.append(atr_breakout_now)
        self.atr_trailing_values.append(atr_trailing_now)
        self.adx_values.append(adx_now)
        self.regime_values.append(regime_now)
        self.compression_values.append(compressed_now)

        should_plot = (self.bar_index % self.plot_every_n_bars) == 0
        if should_plot:
            self.Plot("Price", "Close", sim_bar.close)
            if rsi_now is not None:
                self.Plot("RSI", "RSI", rsi_now)
                self.Plot("RSI", "Gate", self.rsi_threshold)

        day = tb.EndTime.date()
        if self.current_day is None or day != self.current_day:
            self.current_day = day
            self.trades_today = 0

        if len(self.bars_15m) < self.required_warmup_bars:
            self.warmup_count += 1
            return

        self._update_swings()
        self._plot_levels(should_plot)
        self._heal()

        if self.ts.is_open:
            self._update_active_trade_excursions(sim_bar)
            if self._try_exit_with_v2_rules(sim_bar):
                self._log_decision(
                    tb=tb,
                    sim_bar=sim_bar,
                    final_decision="EXIT_SUBMITTED",
                    rejection_code=None,
                )
                return

        if self.ts.is_flat and self.Portfolio[self.symbol].Invested:
            qty = abs(float(self.Portfolio[self.symbol].Quantity))
            notional = qty * float(self.Securities[self.symbol].Price)
            if notional < 10.0:
                self.Liquidate(self.symbol, "micro residual")
            else:
                self.stat_state_mismatch += 1
                if self._log_count_state < self.log_limit:
                    self.Debug(f"STATE MISMATCH {tb.EndTime} | FLAT but invested qty={qty:.8f} notional={notional:.2f}")
                    self._log_count_state += 1
                return

        if not self.ts.is_flat:
            self.position_not_flat_count += 1
            return

        if self.max_trades_per_day is not None and self.trades_today >= self.max_trades_per_day:
            self._log_decision(
                tb=tb,
                sim_bar=sim_bar,
                final_decision="SKIP",
                rejection_code="DAILY_LIMIT_REACHED",
            )
            return

        if self.cooldown_bars > 0 and self.bar_index < self.ts.cooldown_until:
            self._log_decision(
                tb=tb,
                sim_bar=sim_bar,
                final_decision="SKIP",
                rejection_code="COOLDOWN_ACTIVE",
            )
            return

        if self._has_open_orders():
            self.open_orders_skip_count += 1
            self._log_decision(
                tb=tb,
                sim_bar=sim_bar,
                final_decision="SKIP",
                rejection_code="OPEN_ORDERS",
            )
            return

        self._try_entry(tb, sim_bar)

    def OnEndOfAlgorithm(self):
        if not self.ts.is_flat:
            final_price, fallback_msg = safe_final_price(
                self.bars_15m, float(self.Securities[self.symbol].Price)
            )
            if fallback_msg:
                self.Debug(f"END PRICE FALLBACK | {fallback_msg}")
            if final_price is not None:
                result = finalize_exit(self.ts, reason="END_OF_ALGO", fill_price=final_price)
                self.total_trade_pnl += result["pnl"]
                self.stat_exit += 1
                self.Debug(
                    f"END FINALIZE | Reason={result['effective_reason']} "
                    f"Price={final_price:.2f} PnL={result['pnl']:.2f}"
                )
                self._log_trade_exit(fill_price=final_price, reason="END_OF_ALGO")
            else:
                self.Debug("END FINALIZE | skipped PnL — no valid final price")
                self.stat_exit += 1
            self._reset_trade(cooldown=False)
            self.current_trade_id = None
        if self.Portfolio[self.symbol].Invested:
            self.Liquidate(self.symbol, "EndOfAlgorithm")

        rej = self.stat_filter_reject_reasons
        self.Debug(
            f"DONE | Trades={self.stat_entries} Exits={self.stat_exit} SL={self.stat_sl} TP={self.stat_tp} "
            f"BOS={self.stat_bos} Cand={self.stat_signal_candidates} Acc={self.stat_signal_accepted} "
            f"PlanOK={self.stat_plan_ok} PlanFail={self.stat_plan_fail} "
            f"Qty0Skips={self.stat_skip_qty0} EntryReject={self.stat_entry_reject} "
            f"RiskRef={self.stat_risk_refused} SizeCapped={self.stat_size_capped} "
            f"FilterBlocked={self.stat_filter_blocked} ExternalExit={self.stat_external_exit} "
            f"StateMismatch={self.stat_state_mismatch} "
            f"Rejects(regime={rej['regime']},range={rej['range_or_compressed']},adx={rej['adx']},rsi={rej['rsi']}) "
            f"ApproxPnL={self.total_trade_pnl:.2f}"
        )
        self._save_diagnostics_artifacts()
