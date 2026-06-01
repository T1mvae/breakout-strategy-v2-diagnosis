# region imports
from AlgorithmImports import *
# endregion

from project_code.utils.state_utils import finalize_exit, heal_state
from project_code.utils.swing_utils import update_swings_from_bars


def _reset_trade(self, cooldown: bool):
    """Full trade reset: QC tickets, SL manager, and domain state."""
    self.stop_loss_manager.reset()
    self.entry_ticket = None
    self.exit_ticket = None
    self.ts.reset(
        cooldown_bars=self.cooldown_bars if cooldown else 0,
        bar_index=self.bar_index,
    )


def _heal(self):
    """Invoke heal_state and execute any required recovery actions."""
    actions = heal_state(
        self.ts,
        is_invested=self.Portfolio[self.symbol].Invested,
        portfolio_qty=float(self.Portfolio[self.symbol].Quantity),
        has_open_orders=self._has_open_orders(),
        current_time=self.Time,
    )
    for action, detail in actions:
        if self._log_count_state < self.log_limit:
            self.Debug(f"HEAL {self.Time} | {action}: {detail}")
            self._log_count_state += 1

        if action == "FINALIZE":
            result = finalize_exit(self.ts, reason=detail, fill_price=None)
            self.total_trade_pnl += result["pnl"]
            self.stat_exit += 1
            self.stat_external_exit += 1
            if result["sl_hit"]:
                self.stat_sl += 1
            if result["tp_hit"]:
                self.stat_tp += 1
            self._log_trade_exit(fill_price=None, reason=detail)
            self._reset_trade(cooldown=True)
            self.current_trade_id = None
        elif action == "CLEAR_EXIT":
            self.exit_ticket = None
        elif action == "CLEAR_ENTRY":
            self.entry_ticket = None
        elif action == "RESET":
            self.entry_ticket = None
            self.exit_ticket = None
            self.stop_loss_manager.reset()


def _has_open_orders(self) -> bool:
    return len(self.Transactions.GetOpenOrders(self.symbol)) > 0


def _update_swings(self):
    (
        self.swing_levels,
        self.last_applied_swing_bar_index,
        self.last_swing_high_bar_index,
        self.last_swing_low_bar_index,
    ) = update_swings_from_bars(
        self.bars_15m,
        self.N_candidates,
        self.N_confirmation,
        self.min_move_threshold,
        self.min_bars_between_swings,
        self.swing_levels,
        self.last_applied_swing_bar_index,
        self.last_swing_high_bar_index,
        self.last_swing_low_bar_index,
    )
