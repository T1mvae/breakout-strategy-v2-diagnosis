# region imports
from AlgorithmImports import *
# endregion


def _plot_levels(self, should_plot: bool):
    if not should_plot:
        return
    hi = self.swing_levels.last_swing_high_price
    lo = self.swing_levels.last_swing_low_price
    if hi is not None:
        self.Plot("Levels", "SwingHigh", float(hi))
    if lo is not None:
        self.Plot("Levels", "SwingLow", float(lo))
    if self.ts.is_open and self.ts.sl_price is not None:
        self.Plot("Levels", "SL", float(self.ts.sl_price))
        if self.ts.tp_price is not None:
            self.Plot("Levels", "TP", float(self.ts.tp_price))
