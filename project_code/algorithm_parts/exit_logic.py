# region imports
from AlgorithmImports import *
# endregion

from typing import Optional

from project_code.entry_exit import (
    Bar as SimBar,
    PositionDirection,
    check_exit_rules,
    check_partial_1r_reached,
    compute_trailing_stop,
)
from project_code.utils.trade_math import round_quantity_for_security


def _try_exit_with_v2_rules(self, bar: SimBar) -> bool:
    if self.ts.plan is None:
        return False
    if not self.Portfolio[self.symbol].Invested:
        return False
    if self.exit_ticket is not None and self._has_open_orders():
        return True
    if self.ts.phase == "EXIT_SUBMITTED":
        return True

    if self.ts.sl_price is None:
        return False

    sl_price = float(self.ts.sl_price)

    if self.ts.partial_exit_done:
        atr = self.atr_trailing_values[-1] if self.atr_trailing_values else float("nan")
        sl_price = compute_trailing_stop(
            close=bar.close,
            atr=atr,
            direction=self.ts.plan.direction,
            old_stop=sl_price,
            k_trail=self.k_trail,
        )
        self.ts.sl_price = sl_price
        self.ts.trailing_stop_price = sl_price
        tp_for_check = None
    else:
        tp_for_check = float(self.ts.tp_price) if self.ts.tp_price is not None else None

    exit_event = check_exit_rules(
        bar=bar,
        direction=self.ts.plan.direction,
        sl_price=sl_price,
        tp_price=tp_for_check,
        same_bar_rule=self.same_bar_rule,
    )
    if exit_event is not None:
        qty_to_close = -float(self.Portfolio[self.symbol].Quantity)
        if abs(qty_to_close) > 1e-12:
            self.ts.submit_exit(
                reason=exit_event.exit_reason.value,
                model_price=float(exit_event.exit_price),
            )
            self.exit_ticket = None
            self.exit_ticket = self.MarketOrder(
                self.symbol,
                qty_to_close,
                tag=f"EXIT|{exit_event.exit_reason.value}",
            )
            return True
        self._reset_trade(cooldown=True)
        return True

    if (
        self.enable_partial_trailing
        and not self.ts.partial_exit_done
        and not self.ts.partial_submitted
        and check_partial_1r_reached(
            bar=bar,
            direction=self.ts.plan.direction,
            entry_price=self.ts.entry_fill_price or self.ts.plan.entry_price,
            sl_price=float(self.ts.sl_price),
            r_mult=self.partial_exit_at_r,
        )
    ):
        current_qty = float(self.Portfolio[self.symbol].Quantity)
        qty_to_close = -current_qty * self.partial_exit_pct
        qty_to_close = round_quantity_for_security(
            self.Securities[self.symbol], qty_to_close, self.qty_decimals
        )
        if qty_to_close != 0:
            entry = self.ts.entry_fill_price or self.ts.plan.entry_price
            r = abs(entry - self.ts.sl_price)
            one_r_price = entry + (r if self.ts.plan.direction == PositionDirection.LONG else -r)
            self.ts.submit_exit(
                reason="PARTIAL_1R",
                model_price=float(one_r_price),
            )
            self.exit_ticket = None
            self.exit_ticket = self.MarketOrder(
                self.symbol,
                qty_to_close,
                tag="EXIT|PARTIAL_1R",
            )
            return True

    return False


def _update_active_trade_excursions(self, sim_bar: SimBar) -> None:
    if self.current_trade_id is None or self.ts.plan is None:
        return
    try:
        self.diagnostics.trade_recorder.update_excursions(
            trade_id=self.current_trade_id,
            bar_high=sim_bar.high,
            bar_low=sim_bar.low,
            current_bar_index=self.bar_index,
            current_time=str(self.Time),
        )
    except Exception:
        pass


def _log_trade_exit(self, *, fill_price: Optional[float], reason: str) -> None:
    if self.current_trade_id is None:
        return
    try:
        context = self._get_strategy_context_snapshot()
        self.diagnostics.trade_recorder.log_exit(
            trade_id=self.current_trade_id,
            exit_time=str(self.Time),
            exit_price=fill_price,
            exit_reason=reason,
            regime_at_exit=context.get("regime"),
            adx_at_exit=context.get("adx"),
            atr_at_exit=context.get("atr"),
            spread_at_exit=context.get("spread"),
            spread_pct_at_exit=context.get("spread_pct"),
            portfolio_value_at_exit=context.get("total_portfolio_value"),
            cash_at_exit=context.get("cash"),
            margin_remaining_at_exit=context.get("margin_remaining"),
            fees_total=None,
        )
    except Exception:
        pass
