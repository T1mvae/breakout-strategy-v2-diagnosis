import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_code.diagnostics import (  # noqa: E402
    DecisionTrace,
    MarketTrace,
    PortfolioTrace,
    TradeRecorder,
)


class DiagnosticsTestCase(unittest.TestCase):
    def test_market_trace_stores_row(self):
        trace = MarketTrace()
        trace.log(run_id="r1", time="t", symbol="BTCUSD", bar_index=1, close=100.0)
        self.assertEqual(len(trace.rows), 1)
        self.assertEqual(trace.rows[0]["close"], 100.0)

    def test_portfolio_trace_stores_row(self):
        trace = PortfolioTrace()
        trace.log(run_id="r1", time="t", bar_index=1, cash=50000.0)
        self.assertEqual(len(trace.rows), 1)
        self.assertEqual(trace.rows[0]["cash"], 50000.0)

    def test_decision_trace_stores_row(self):
        trace = DecisionTrace()
        trace.log(run_id="r1", final_decision="SKIP", rejection_code="NO_BOS")
        self.assertEqual(len(trace.rows), 1)

    def test_trade_recorder_long_r_multiple(self):
        rec = TradeRecorder()
        rec.log_entry(
            run_id="r1",
            trade_id="t1",
            symbol="BTCUSD",
            direction="LONG",
            entry_price=100.0,
            sl_price=90.0,
            quantity=1.0,
        )
        rec.log_exit(trade_id="t1", exit_price=110.0)
        row = rec.rows[0]
        self.assertAlmostEqual(row["r_multiple"], 1.0)

    def test_trade_recorder_short_r_multiple(self):
        rec = TradeRecorder()
        rec.log_entry(
            run_id="r1",
            trade_id="t2",
            symbol="BTCUSD",
            direction="SHORT",
            entry_price=100.0,
            sl_price=110.0,
            quantity=1.0,
        )
        rec.log_exit(trade_id="t2", exit_price=90.0)
        row = rec.rows[0]
        self.assertAlmostEqual(row["r_multiple"], 1.0)

    def test_trade_recorder_long_mfe_mae(self):
        rec = TradeRecorder()
        rec.log_entry(
            run_id="r1",
            trade_id="t3",
            symbol="BTCUSD",
            direction="LONG",
            entry_price=100.0,
            sl_price=95.0,
            quantity=1.0,
        )
        rec.update_excursions(trade_id="t3", bar_high=103.0, bar_low=98.0)
        rec.update_excursions(trade_id="t3", bar_high=106.0, bar_low=97.0)
        row = rec.rows[0]
        self.assertAlmostEqual(row["mfe_price"], 6.0)
        self.assertAlmostEqual(row["mae_price"], 3.0)
        self.assertAlmostEqual(row["mfe_r"], 6.0 / 5.0)
        self.assertAlmostEqual(row["mae_r"], 3.0 / 5.0)

    def test_trade_recorder_short_mfe_mae(self):
        rec = TradeRecorder()
        rec.log_entry(
            run_id="r1",
            trade_id="t4",
            symbol="BTCUSD",
            direction="SHORT",
            entry_price=100.0,
            sl_price=105.0,
            quantity=1.0,
        )
        rec.update_excursions(trade_id="t4", bar_high=102.0, bar_low=94.0)
        rec.update_excursions(trade_id="t4", bar_high=101.0, bar_low=92.0)
        row = rec.rows[0]
        self.assertAlmostEqual(row["mfe_price"], 8.0)
        self.assertAlmostEqual(row["mae_price"], 2.0)


if __name__ == "__main__":
    unittest.main()
