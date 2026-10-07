"""Isolated checks: no exchange/LLM/Discord requests; writes only to temp dirs."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.agent_team import OperatorAgent, StrategistAgent, SupervisorAgent
from data.preprocessor import create_buy_labels
from engine.paper_trader import PaperTrader
from engine.risk_manager import RiskManager
from engine.strategy_policy import ENTRY_SHORT_RSI_MAX, entry_signal_rejection
from models.predictor import Predictor


class RuntimeLogicTests(unittest.TestCase):
    def test_agent_prompts_initialize_with_shared_policy(self):
        operator_prompt = " ".join(OperatorAgent.SYSTEM_PROMPT.split())
        self.assertIn(f"RSI < {ENTRY_SHORT_RSI_MAX:g}", operator_prompt)
        self.assertIn("panic_score >= 8", SupervisorAgent.SYSTEM_PROMPT)

    def test_macro_directive_uses_price_and_rsi_not_ema_cross(self):
        result = StrategistAgent().analyze_macro(
            "BTC/USDT",
            90.0,
            {"rsi_14": 40.0, "ema_50": 100.0, "ema_200": 80.0},
        )
        self.assertEqual(result["directive"], "ONLY_SHORT")

    def test_buy_label_requires_take_profit_before_stop(self):
        candles = pd.DataFrame(
            {
                "close": [100.0, 100.0, 100.0, 100.0],
                "high": [100.0, 102.0, 100.0, 100.0],
                "low": [100.0, 99.5, 100.0, 100.0],
            }
        )
        labels = create_buy_labels(candles, horizon=2, take_profit_pct=0.015, stop_loss_pct=0.01)
        self.assertEqual(labels.iloc[0], "BUY")
        self.assertTrue(pd.isna(labels.iloc[-1]))

    def test_same_candle_stop_and_target_is_labeled_hold(self):
        candles = pd.DataFrame(
            {
                "close": [100.0, 100.0, 100.0, 100.0],
                "high": [100.0, 102.0, 100.0, 100.0],
                "low": [100.0, 98.0, 100.0, 100.0],
            }
        )
        labels = create_buy_labels(candles, horizon=2, take_profit_pct=0.015, stop_loss_pct=0.01)
        self.assertEqual(labels.iloc[0], "HOLD")

    def test_short_stop_loss_triggers_on_adverse_move(self):
        manager = RiskManager(stop_loss_pct=0.01, take_profit_pct=0.03)
        self.assertEqual(
            manager.should_exit(side="SHORT", entry_price=100.0, current_price=101.1),
            "STOP_LOSS_SHORT",
        )

    def test_shared_short_policy_allows_current_rsi_49_rule(self):
        self.assertIsNone(
            entry_signal_rejection(
                "OPEN_SHORT",
                "ONLY_SHORT",
                {"rsi_14": 49.02, "ema_9": 99.0, "ema_21": 100.0},
            )
        )

    def test_shared_policy_rejects_macro_conflict(self):
        self.assertIsNotNone(
            entry_signal_rejection(
                "OPEN_SHORT",
                "ONLY_LONG",
                {"rsi_14": 40.0, "ema_9": 99.0, "ema_21": 100.0},
            )
        )

    def test_shared_policy_rejects_non_finite_indicators(self):
        self.assertIsNotNone(
            entry_signal_rejection(
                "OPEN_SHORT",
                "ONLY_SHORT",
                {"rsi_14": float("nan"), "ema_9": 99.0, "ema_21": 100.0},
            )
        )

    def test_predictor_without_model_fails_closed_to_hold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            predictor = Predictor(Path(temp_dir) / "missing.pkl")
        self.assertEqual(predictor.predict(pd.DataFrame()), {"action": "HOLD", "buy": 0.0, "hold": 1.0})

    def test_paper_ledger_round_trip_and_fees(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "active_position.json"
            trades = Path(temp_dir) / "trades.csv"
            with patch("engine.paper_trader.ACTIVE_POS_FILE", ledger), patch(
                "engine.paper_trader.TRADES_FILE", trades
            ):
                trader = PaperTrader(initial_cash=100.0, fee_rate=0.0005)
                self.assertTrue(trader.open_position("LONG", 100.0, cash_amount=70.0))
                restored = PaperTrader(initial_cash=100.0, fee_rate=0.0005)
                self.assertEqual(restored.position.side, "LONG")
                summary = restored.close_position(101.0, exit_reason="UNIT_CHECK")
                self.assertGreater(summary["pnl_usdt"], 0)
                self.assertIsNone(restored.position)
                self.assertTrue(trades.is_file())

    def test_empty_paper_ledger_is_rejected_instead_of_reset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ledger = Path(temp_dir) / "active_position.json"
            ledger.write_text("{}", encoding="utf-8")
            with patch("engine.paper_trader.ACTIVE_POS_FILE", ledger):
                with self.assertRaises(RuntimeError):
                    PaperTrader(initial_cash=100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
