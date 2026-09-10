import copy
import json
import math
import tempfile
import threading
import time
import unittest
from pathlib import Path

from trader.cognition import ContractError, RuleCognition, validate_proposal
from trader.engine import Engine, FEE, SLIPPAGE
from trader.market import SYMBOLS
from trader.research import evaluate, ranks, research


class BuyCognition(RuleCognition):
    def plan(self, snapshot):
        return {"regime": "trend", "risk_scale": 1, "thesis": "测试提议", "actions": [{"symbol": "BTC", "side": "buy"}]}

    def review(self, snapshot, proposal):
        return {"verdict": "approve", "reason": "测试批准"}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.engine = Engine(self.path, BuyCognition())

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def test_fill_accounting_and_stop_coverage(self):
        e = self.engine
        e.cognize()
        view = e.view()
        p = view["positions"][0]
        self.assertEqual(view["health"]["stop_coverage"], 1)
        self.assertLessEqual(p["value"], 10000 * .2)
        self.assertLess(p["stop"], p["entry"])
        self.assertAlmostEqual(view["account"]["equity"], view["account"]["cash"] + p["value"])
        self.assertLess(view["account"]["equity"], 10000)
        self.assertGreater(view["account"]["fees"], 0)
        e.flatten()
        v = e.view()
        self.assertEqual(v["positions"], [])
        self.assertTrue(v["halted"])
        self.assertAlmostEqual(v["account"]["pnl"], v["trades"][0]["pnl"])

    def test_duplicate_round_and_restart_cannot_duplicate_order(self):
        e = self.engine
        self.assertTrue(e.cognize())
        self.assertFalse(e.cognize())
        cash = e.state["cash"]
        e.close()
        self.engine = Engine(self.path, BuyCognition())
        self.assertFalse(self.engine.cognize())
        self.assertEqual(self.engine.state["trade_count"], 1)
        self.assertAlmostEqual(self.engine.state["cash"], cash)
        self.assertFalse(self.engine.state["running"])
        self.assertIsNone(self.engine.view()["health"]["snapshot_age"])

    def test_stale_snapshot_blocks_entry(self):
        e = self.engine
        e.state["last_tick_wall"] = time.time() - 40
        e.cognize()
        self.assertEqual(e.state["positions"], {})
        self.assertIn("过期", e.state["rounds"][-1]["outcomes"][0]["reason"])

    def test_gap_stop_fills_at_open_with_slippage(self):
        e = self.engine
        e.cognize()
        position = e.state["positions"]["BTC"]
        gap_open = position["stop"] * .85
        e.state["bars"]["BTC"][-1].update(open=gap_open, low=gap_open*.99, close=gap_open, high=gap_open*1.01)
        e._risk_tick()
        self.assertNotIn("BTC", e.state["positions"])
        trade = e.state["trades"][-1]
        self.assertAlmostEqual(trade["price"], gap_open * (1-SLIPPAGE))
        self.assertAlmostEqual(trade["fee"], trade["price"]*trade["quantity"]*FEE)
        self.assertEqual(trade["reason"], "止损触发")

    def test_drawdown_ladder_and_halt(self):
        e = self.engine
        for cash, scale in [(10000,1),(9600,.5),(9400,.25),(9100,0)]:
            e.state["cash"] = cash
            self.assertEqual(e.risk_scale(), scale)
        e._risk_tick()
        self.assertTrue(e.state["halted"])
        e.cognize()
        self.assertEqual(e.state["positions"], {})
        with self.assertRaises(ValueError):
            e.set_running(True)

    def test_critic_veto_and_model_failure_are_fail_closed(self):
        e = self.engine
        e.provider.review = lambda *_: {"verdict":"veto", "reason":"测试否决"}
        e.cognize()
        self.assertEqual(e.state["trade_count"], 0)
        e.advance()
        def fail(_):
            raise RuntimeError("secret-do-not-log")
        e.provider.plan = fail
        e.cognize()
        self.assertEqual(e.state["trade_count"], 0)
        self.assertIn("RuntimeError", e.state["last_error"])
        self.assertNotIn("secret-do-not-log", json.dumps(e.audit()))

    def test_slow_cognition_does_not_block_risk_and_flatten_wins(self):
        e = self.engine
        started, release = threading.Event(), threading.Event()
        original = e.provider.plan
        def slow(snapshot):
            started.set()
            release.wait(3)
            return original(snapshot)
        e.provider.plan = slow
        worker = threading.Thread(target=e.cognize)
        worker.start()
        self.assertTrue(started.wait(1))
        try:
            e.advance()
            self.assertEqual(e.state["risk_ticks"], 1)
            e.flatten()
        finally:
            release.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(e.state["positions"], {})

    def test_research_cannot_activate_or_change_capital(self):
        e = self.engine
        before = e.state["cash"]
        result = e.run_research()
        self.assertIn(result["status"], {"Trial", "Rejected"})
        self.assertFalse(result["capital_enabled"])
        self.assertEqual(e.state["cash"], before)
        e.run_research()
        self.assertEqual(len(e.state["research"]), 1)

    def test_extended_replay_accounting_and_constraints(self):
        e = self.engine
        e.provider = RuleCognition()
        for i in range(240):
            e.advance()
            if i % 4 == 0:
                e.cognize()
            view = e.view()
            a = view["account"]
            self.assertTrue(math.isfinite(a["equity"]))
            self.assertGreaterEqual(a["cash"], 0)
            self.assertAlmostEqual(a["equity"], a["cash"] + sum(p["value"] for p in view["positions"]))
            self.assertTrue(all(p["stop"] > 0 and p["quantity"] > 0 for p in view["positions"]))
        trades = [entry["trade"] for entry in e.audit(10000) if entry["kind"] == "fill"]
        self.assertGreater(len(trades), 0)
        self.assertEqual(len({t["client_order_id"] for t in trades}), len(trades))
        expected_cash = 10000 + sum((1 if t["side"] == "sell" else -1)*t["quantity"]*t["price"] - t["fee"] for t in trades)
        self.assertAlmostEqual(e.state["cash"], expected_cash)


class ContractTests(unittest.TestCase):
    def test_invalid_model_actions_and_scales(self):
        base = {"regime":"trend", "risk_scale":.5,"thesis":"test", "actions":[]}
        for scale in (float("nan"),float("inf"),-1,1.1,True,"1"):
            with self.subTest(scale=scale), self.assertRaises(ContractError):
                validate_proposal({**base,"risk_scale":scale},set(SYMBOLS))
        for actions in ([{"symbol":"DOGE","side":"buy"}], [{"symbol":"BTC","side":"short"}], [{"symbol":"BTC","side":"buy"}]*2):
            with self.assertRaises(ContractError):
                validate_proposal({**base,"actions":actions},set(SYMBOLS))

    def test_train_metrics_do_not_read_holdout(self):
        bars = [{"close":100 + i*.05 + math.sin(i)} for i in range(512)]
        split = int(len(bars)*.7)
        original = evaluate(bars,16,32,split-4)
        perturbed = copy.deepcopy(bars)
        for bar in perturbed[split:]:
            bar["close"] *= 10
        self.assertEqual(original, evaluate(perturbed,16,32,split-4))
        self.assertEqual(ranks([2,1,2]), [1.5,0,1.5])
        self.assertFalse(research(bars, 512)["capital_enabled"])


if __name__ == "__main__":
    unittest.main()
