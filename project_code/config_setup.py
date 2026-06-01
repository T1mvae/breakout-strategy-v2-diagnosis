# region imports
from AlgorithmImports import *
# endregion

from datetime import timedelta
from typing import Optional

from project_code.diagnostics import DiagnosticsBundle
from project_code.entry_exit import (
    Bar as SimBar,
    SameBarSlTpRule,
    SwingLevels,
    TakeProfitMode,
)
from project_code.momentum_confirmation_rsi import RSIEngine
from project_code.risk import RiskConfig, SizingResult
from project_code.stop_loss import StopLossManager
from project_code.utils.performance_indicators import (
    AdxEngine,
    AtrEngine,
    CompressionEngine,
    EmaRegimeEngine,
)
from project_code.utils.trade_state import TradeState


def configure(self) -> None:
    """Full algorithm configuration and state initialization.

    Called from BosBreakoutBtc15m.Initialize. Sets every parameter, engine and
    runtime field on ``self`` exactly as the original monolithic Initialize did.
    """
    self.SetTimeZone("UTC")
    self.SetStartDate(2021, 1, 1)
    self.SetEndDate(2025, 1, 1)
    self.SetCash(100000)

    self.SetBrokerageModel(BrokerageName.Bitfinex, AccountType.Margin)
    self.symbol = self.AddCrypto("BTCUSD", Resolution.Minute).Symbol
    self.SetBenchmark(self.symbol)

    self.qty_decimals = 6

    self.sl_mode = "atr"
    self.fixed_pct = 0.0100
    self.buffer_pct = 0.000
    self.k_sl = 2.0
    self.atr_period_sl = 14

    self.use_fixed_tp = True
    self.tp_mode = TakeProfitMode.RR_BASED
    self.tp_mult = 3.0

    self.enable_partial_trailing = False
    self.partial_exit_pct = 0.5
    self.partial_exit_at_r = 1.0
    self.k_trail = 2.0
    self.atr_period_trailing = 14

    self.k_buffer = 0.5
    self.atr_period_breakout = 14

    self.ema_period = 50
    self.adx_enabled = True
    self.adx_period = 14
    self.adx_threshold = 20.0
    self.atr_period = self.atr_period_breakout
    self.rsi_enabled = True
    self.rsi_period = 14
    self.rsi_threshold = 45.0
    self.compression_enabled = False
    self.compression_lookback = 10
    self.compression_atr_multiplier = 1.5
    self.plot_every_n_bars = 10

    self.same_bar_rule = SameBarSlTpRule.WORST_CASE
    self.cooldown_bars = 4
    self.max_trades_per_day = 3

    self.risk_config = RiskConfig(
        risk_pct=0.01,
        max_position_size=2.0,
        min_stop_distance=50.0,
        min_stop_distance_pct=0.002,
        max_leverage=0.3,
        use_buying_power_cap=True,
    )
    self.min_equity = 10000

    self.N_candidates = [5, 10, 20]
    self.N_confirmation = 3
    self.min_move_threshold = 0.0
    self.min_bars_between_swings = 3

    self.required_warmup_bars = max(
        max(self.N_candidates) + self.N_confirmation + 20,
        self.ema_period + 2,
        self.adx_period * 2 + 2,
        self.rsi_period + 2,
        self.atr_period_breakout + 2,
        self.atr_period_trailing + 2,
        self.compression_lookback + 2,
    )

    self.stop_loss_manager = StopLossManager(
        mode=self.sl_mode,
        fixed_pct=self.fixed_pct,
        buffer_pct=self.buffer_pct,
        k_sl=self.k_sl,
        atr_period=self.atr_period_sl,
    )
    self.rsi_engine = RSIEngine(length=self.rsi_period)
    self.atr_breakout_engine = AtrEngine(self.atr_period_breakout)
    self.atr_trailing_engine = (
        self.atr_breakout_engine
        if self.atr_period_trailing == self.atr_period_breakout
        else AtrEngine(self.atr_period_trailing)
    )
    self.adx_engine = AdxEngine(self.adx_period)
    self.regime_engine = EmaRegimeEngine(self.ema_period)
    self.compression_engine = CompressionEngine(
        lookback=self.compression_lookback,
        atr_multiplier=self.compression_atr_multiplier,
    )

    self.swing_levels = SwingLevels()
    self.bars_15m: list[SimBar] = []
    self.rsi_values: list[Optional[float]] = []
    self.atr_breakout_values: list[float] = []
    self.atr_trailing_values: list[float] = []
    self.adx_values: list[float] = []
    self.regime_values: list[str] = []
    self.compression_values: list[bool] = []
    self.last_applied_swing_bar_index = -1

    self.bar_index = 0
    self.current_day = None
    self.trades_today = 0

    self.ts = TradeState()
    self.entry_ticket = None
    self.exit_ticket = None

    self.stat_bos = 0
    self.stat_signal_candidates = 0
    self.stat_signal_accepted = 0
    self.stat_plan_ok = 0
    self.stat_plan_fail = 0
    self.stat_skip_qty0 = 0
    self.stat_entries = 0
    self.stat_exit = 0
    self.stat_sl = 0
    self.stat_tp = 0
    self.stat_entry_reject = 0
    self.stat_risk_refused = 0
    self.stat_size_capped = 0
    self.stat_filter_blocked = 0
    self.stat_external_exit = 0
    self.stat_state_mismatch = 0
    self.stat_filter_reject_reasons = {
        "regime": 0,
        "range_or_compressed": 0,
        "adx": 0,
        "rsi": 0,
    }
    self.stat_other_fail = 0
    self.total_trade_pnl = 0.0

    self.log_limit = 25
    self._log_count_plan_fail = 0
    self._log_count_filter = 0
    self._log_count_state = 0
    self._log_count_signal = 0
    self._log_count_sizing = 0
    self._last_sizing_result: Optional[SizingResult] = None

    self.run_id = "BOS_BTCUSD_15M_2021_2025_v2_full_diagnostics"
    self.diagnostics = DiagnosticsBundle()
    self.current_trade_id = None
    self.trade_counter = 0
    self.log_market_every_bar = True
    self.log_portfolio_every_bar = True
    self.log_no_bos_decisions = False
    self.no_bos_count = 0
    self.warmup_count = 0
    self.position_not_flat_count = 0
    self.open_orders_skip_count = 0
    self.last_swing_high_bar_index = None
    self.last_swing_low_bar_index = None

    self.consolidator = TradeBarConsolidator(timedelta(minutes=15))
    self.consolidator.DataConsolidated += self.On15MinuteBar
    self.SubscriptionManager.AddConsolidator(self.symbol, self.consolidator)

    self.Debug(
        "READY | BTCUSD 15m | V2 wrapper flow | "
        f"SL={self.sl_mode} | fixedTP={self.use_fixed_tp}({self.tp_mode.value},{self.tp_mult}) | "
        f"filters: regime(EMA{self.ema_period}), adx={self.adx_enabled}({self.adx_period},{self.adx_threshold}), "
        f"rsi={self.rsi_enabled}({self.rsi_period},{self.rsi_threshold}), "
        f"compression={self.compression_enabled}({self.compression_lookback},{self.compression_atr_multiplier})"
    )
