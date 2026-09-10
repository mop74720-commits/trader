"""Paper exchange, risk daemon, persistent state, and auditable decision rounds."""
from __future__ import annotations

import copy
import json
import math
import sqlite3
import threading
import time
from pathlib import Path

from .cognition import RuleCognition, validate_proposal
from .market import BAR_SECONDS, SYMBOLS, features, iso, make_bar
from .research import research

FEE = 0.0006
SLIPPAGE = 0.0005
MAX_POSITION = 0.20
MAX_EXPOSURE = 0.60
RISK_PER_TRADE = 0.005
MAX_SNAPSHOT_AGE = 30


class Engine:
    def __init__(self, path: str | Path, cognition=None, intelligence=None):
        self.lock = threading.RLock()
        self.cognition_lock = threading.Lock()
        self.provider = cognition or RuleCognition()
        self.intelligence = intelligence
        self.busy = False
        self.pending: list[dict] = []
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, wall_time REAL NOT NULL, payload TEXT NOT NULL)")
        row = self.db.execute("SELECT payload FROM state WHERE id=1").fetchone()
        self.fresh = row is None
        if row:
            self.state = json.loads(row[0])
            if self.state.get("version") != 1:
                raise ValueError("Unsupported database format; choose a new --db path")
            self.saved = row[0]
            # A restart cannot make persisted prices fresh. Require the next feed tick.
            self.state["last_tick_wall"] = 0
            self.state["running"] = False
            self._event("system", "服务重新启动，已暂停；等待新的市场快照。")
            self._save()
        else:
            start = math.floor(time.time() / BAR_SECONDS) * BAR_SECONDS - 560 * BAR_SECONDS
            bars = {symbol: [] for symbol in SYMBOLS}
            for tick in range(512):
                for symbol, initial in SYMBOLS.items():
                    previous = bars[symbol][-1]["close"] if bars[symbol] else initial
                    bars[symbol].append(make_bar(symbol, previous, tick, start))
            self.state = {
                "version": 1, "tick": 511, "start": start, "cash": 10000.0, "principal": 10000.0,
                "peak_equity": 10000.0, "max_drawdown": 0.0, "fees": 0.0,
                "positions": {}, "bars": bars, "rounds": [], "trades": [], "curve": [], "research": [],
                "events": [], "running": False, "halted": False, "last_tick_wall": time.time(),
                "risk_ticks": 0, "round_count": 0, "trade_count": 0, "last_error": None,
            }
            self.saved = json.dumps(self.state)
            self._event("system", "模拟账户初始化：10,000 USDC；使用合成行情。")
            self._mark_curve()
            self._save()

    def close(self):
        with self.lock:
            self.db.close()

    def _event(self, kind: str, message: str, **extra):
        event = {"kind": kind, "message": message, "time": iso(self.sim_time), "wall_time": time.time(), **extra}
        self.pending.append(event)
        self.state["events"].append(event)
        self.state["events"] = self.state["events"][-120:]

    def _save(self):
        payload = json.dumps(self.state, ensure_ascii=False, allow_nan=False)
        try:
            with self.db:
                self.db.execute("INSERT INTO state VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (payload,))
                self.db.executemany("INSERT INTO audit(wall_time,payload) VALUES (?,?)", [(e["wall_time"], json.dumps(e, ensure_ascii=False)) for e in self.pending])
        except Exception:
            self.state = json.loads(self.saved)
            self.pending.clear()
            raise
        self.saved = payload
        self.pending.clear()

    @property
    def sim_time(self):
        return self.state["start"] + self.state["tick"] * BAR_SECONDS

    def equity(self):
        return self.state["cash"] + sum(p["quantity"] * self.state["bars"][s][-1]["close"] for s, p in self.state["positions"].items())

    def drawdown(self):
        return max(0, 1 - self.equity() / self.state["peak_equity"])

    def risk_scale(self):
        dd = self.drawdown()
        return 0 if self.state["halted"] or dd >= 0.08 else 0.25 if dd >= 0.05 else 0.5 if dd >= 0.03 else 1.0

    def _mark_curve(self):
        equity = self.equity()
        self.state["peak_equity"] = max(self.state["peak_equity"], equity)
        self.state["max_drawdown"] = max(self.state["max_drawdown"], self.drawdown())
        point = {"time": iso(self.sim_time), "equity": equity, "drawdown": self.drawdown()}
        if self.state["curve"] and self.state["curve"][-1]["time"] == point["time"]:
            self.state["curve"][-1] = point
        else:
            self.state["curve"].append(point)
        self.state["curve"] = self.state["curve"][-600:]

    def _sell(self, symbol: str, reference: float, reason: str, key: str):
        position = self.state["positions"].pop(symbol, None)
        if position is None:
            return None
        fill = reference * (1 - SLIPPAGE)
        notional = position["quantity"] * fill
        fee = notional * FEE
        self.state["cash"] += notional - fee
        self.state["fees"] += fee
        pnl = notional - fee - position["cost"]
        return self._trade(symbol, "sell", position["quantity"], fill, fee, pnl, reason, key)

    def _trade(self, symbol, side, quantity, fill, fee, pnl, reason, key):
        self.state["trade_count"] += 1
        trade = {"id": self.state["trade_count"], "client_order_id": key, "time": iso(self.sim_time), "symbol": symbol,
                 "side": side, "quantity": quantity, "price": fill, "fee": fee, "pnl": pnl, "reason": reason, "status": "filled"}
        self.state["trades"].append(trade)
        self.state["trades"] = self.state["trades"][-300:]
        self._event("fill", f"{symbol} {'买入' if side == 'buy' else '卖出'} · {reason}", trade=trade)
        return trade

    def _risk_tick(self):
        # Existing stops are checked before any new cognition, including while paused.
        for symbol, position in list(self.state["positions"].items()):
            bar = self.state["bars"][symbol][-1]
            if bar["low"] <= position["stop"]:
                self._sell(symbol, min(bar["open"], position["stop"]), "止损触发", f"stop-{self.state['tick']}-{symbol}")
        self._mark_curve()
        if self.drawdown() >= 0.08 and not self.state["halted"]:
            self.state["halted"] = True
            self.state["running"] = False
            for symbol in list(self.state["positions"]):
                self._sell(symbol, self.state["bars"][symbol][-1]["close"], "回撤熔断", f"halt-{self.state['tick']}-{symbol}")
            self._event("risk", "回撤达到 8%，清仓并锁定新开仓。")
        self.state["risk_ticks"] += 1
        self._mark_curve()

    def advance(self, count=1):
        with self.lock:
            for _ in range(count):
                self.state["tick"] += 1
                for symbol in SYMBOLS:
                    history = self.state["bars"][symbol]
                    history.append(make_bar(symbol, history[-1]["close"], self.state["tick"], self.state["start"]))
                    self.state["bars"][symbol] = history[-1024:]
                self.state["last_tick_wall"] = time.time()
                self._risk_tick()
            self._save()

    def set_running(self, running: bool):
        with self.lock:
            if running and self.state["halted"]:
                raise ValueError("账户已熔断，请使用新的数据库开始独立实验。")
            self.state["running"] = running
            self._event("system", "自动模拟已启动。" if running else "已暂停自动模拟。")
            self._save()

    def flatten(self):
        with self.lock:
            self.state["running"] = False
            self.state["halted"] = True
            for symbol in list(self.state["positions"]):
                self._sell(symbol, self.state["bars"][symbol][-1]["close"], "手动停止并清仓", f"manual-{self.state['tick']}-{symbol}")
            self._event("risk", "已停止并锁定账户；全部模拟仓位已平仓。")
            self._mark_curve()
            self._save()

    def snapshot(self):
        with self.lock:
            cutoff = min(self.sim_time, time.time())
            snapshot = {"tick": self.state["tick"], "time": iso(self.sim_time), "captured_at": self.state["last_tick_wall"],
                    "market": {s: features(b) for s, b in self.state["bars"].items()},
                    "positions": copy.deepcopy(self.state["positions"]), "equity": self.equity(),
                    "drawdown": self.drawdown(), "intelligence": [], "source": "synthetic"}
        # No trading lock is held while querying the separate information subsystem.
        if self.intelligence is not None:
            try:
                digest = self.intelligence.digest(cutoff,context={"holdings":list(snapshot["positions"]),"watchlist":list(snapshot["market"])})
                snapshot["intelligence"] = digest["events"]
                snapshot["intelligence_context"] = {k:v for k,v in digest.items() if k != "events"}
                snapshot["intelligence_context"]["usage"] = "context_only_with_synthetic_prices"
            except Exception as exc:
                snapshot["intelligence_context"] = {"health":"unavailable", "error":type(exc).__name__, "as_of":cutoff}
        return snapshot

    def _apply_action(self, action: dict, proposal: dict, snapshot: dict, key: str):
        symbol = action["symbol"]
        price = self.state["bars"][symbol][-1]["close"]
        if action["side"] == "sell":
            trade = self._sell(symbol, price, "策略退出", key)
            return {"symbol": symbol, "status": "filled" if trade else "blocked", "reason": "策略退出" if trade else "没有可卖出仓位"}
        if self.state["halted"] or self.risk_scale() == 0:
            return {"symbol": symbol, "status": "blocked", "reason": "账户熔断"}
        if time.time() - snapshot["captured_at"] > MAX_SNAPSHOT_AGE or time.time() - self.state["last_tick_wall"] > MAX_SNAPSHOT_AGE:
            return {"symbol": symbol, "status": "blocked", "reason": "市场快照已过期"}
        if abs(price / snapshot["market"][symbol]["price"] - 1) > 0.01:
            return {"symbol": symbol, "status": "blocked", "reason": "价格偏离决策快照超过 1%"}
        if symbol in self.state["positions"]:
            return {"symbol": symbol, "status": "blocked", "reason": "已有仓位，禁止重复加仓"}
        current = features(self.state["bars"][symbol])
        stop_distance = max(0.02, min(0.08, current["volatility"] * 1.5))
        equity = self.equity()
        exposure = equity - self.state["cash"]
        scale = proposal["risk_scale"] * self.risk_scale()
        budget = min(equity * MAX_POSITION * scale, equity * RISK_PER_TRADE * scale / stop_distance,
                     max(0, equity * MAX_EXPOSURE - exposure), self.state["cash"] / (1 + FEE))
        if budget < 10:
            return {"symbol": symbol, "status": "blocked", "reason": "可用风险预算不足 10 USDC"}
        fill = price * (1 + SLIPPAGE)
        quantity = budget / fill
        fee = budget * FEE
        self.state["cash"] -= budget + fee
        self.state["fees"] += fee
        self.state["positions"][symbol] = {"quantity": quantity, "entry": fill, "cost": budget + fee,
                                           "stop": fill * (1 - stop_distance), "opened_at": iso(self.sim_time)}
        self._trade(symbol, "buy", quantity, fill, fee, None, "风控批准", key)
        return {"symbol": symbol, "status": "filled", "reason": "仓位与止损由风控计算"}

    def cognize(self):
        if not self.cognition_lock.acquire(blocking=False):
            return False
        self.busy = True
        try:
            snapshot = self.snapshot()
            # One round per snapshot tick, persisted across restarts.
            with self.lock:
                if self.state["rounds"] and self.state["rounds"][-1]["snapshot_tick"] == snapshot["tick"]:
                    return False
            error = None
            try:
                proposal = validate_proposal(self.provider.plan(snapshot), set(SYMBOLS))
                review = self.provider.review(snapshot, proposal)
                if review.get("verdict") not in {"approve", "veto"} or not isinstance(review.get("reason"), str):
                    raise ValueError("Invalid review")
            except Exception as exc:
                # Exception bodies may contain API secrets or third-party response text.
                error = f"认知失败（{type(exc).__name__}），本轮不执行订单。"
                proposal = {"regime": "uncertain", "risk_scale": 0, "thesis": error, "actions": []}
                review = {"verdict": "veto", "reason": error}
            with self.lock:
                self.state["round_count"] += 1
                round_id = self.state["round_count"]
                outcomes = []
                if review["verdict"] == "approve":
                    # Execute exits first; each subsequent entry sees updated available capital.
                    for action in sorted(proposal["actions"], key=lambda a: a["side"] == "buy"):
                        outcomes.append(self._apply_action(action, proposal, snapshot, f"round-{round_id}-{action['symbol']}"))
                record = {"id": round_id, "time": iso(self.sim_time), "snapshot_tick": snapshot["tick"],
                          "snapshot_time": snapshot["time"], "snapshot": snapshot, "provider": self.provider.name,
                          "planner_model": self.provider.planner_model, "critic_model": self.provider.critic_model,
                          "proposal": proposal, "review": review, "outcomes": outcomes, "error": error}
                self.state["rounds"].append(record)
                self.state["rounds"] = self.state["rounds"][-100:]
                self.state["last_error"] = error
                self._event("decision", f"认知轮 #{round_id} · {review['verdict']}", round=record)
                self._mark_curve()
                self._save()
            return True
        finally:
            self.busy = False
            self.cognition_lock.release()

    def run_research(self):
        with self.lock:
            tick = self.state["tick"]
            if self.state["research"] and self.state["research"][-1]["tick"] == tick:
                return self.state["research"][-1]
            result = research(self.state["bars"]["BTC"], tick)
            self.state["research"].append(result)
            self.state["research"] = self.state["research"][-60:]
            self._event("research", f"{result['name']} → {result['status']}", result=result)
            self._save()
            return result

    def report_error(self, exc):
        with self.lock:
            self.state["running"] = False
            self.state["last_error"] = f"运行异常（{type(exc).__name__}），已暂停。"
            self._event("error", self.state["last_error"])
            self._save()

    def audit(self, limit=200):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM audit ORDER BY id DESC LIMIT ?", (limit,))]

    def view(self):
        with self.lock:
            state = self.state
            equity = self.equity()
            markets = {s: features(b) for s, b in state["bars"].items()}
            positions = [{"symbol": s, **p, "price": markets[s]["price"], "value": p["quantity"] * markets[s]["price"],
                          "unrealized": p["quantity"] * markets[s]["price"] - p["cost"]} for s, p in state["positions"].items()]
            closed = [t for t in state["trades"] if t["side"] == "sell"]
            return copy.deepcopy({
                "mode": "paper", "feed": "synthetic", "provider": self.provider.name, "time": iso(self.sim_time),
                "running": state["running"], "halted": state["halted"], "busy": self.busy,
                "account": {"equity": equity, "cash": state["cash"], "principal": state["principal"],
                            "pnl": equity - state["principal"], "return": equity / state["principal"] - 1,
                            "drawdown": self.drawdown(), "max_drawdown": state["max_drawdown"], "fees": state["fees"],
                            "exposure": (equity - state["cash"]) / equity if equity else 0,
                            "win_rate": sum(t["pnl"] > 0 for t in closed) / len(closed) if closed else None},
                "health": {"risk_ticks": state["risk_ticks"], "round_count": state["round_count"], "trade_count": state["trade_count"],
                           "snapshot_age": max(0, time.time() - state["last_tick_wall"]) if state["last_tick_wall"] else None,
                           "stop_coverage": sum(p["stop"] > 0 for p in positions) / len(positions) if positions else None,
                           "risk_scale": self.risk_scale(), "last_error": state["last_error"], "news": "collector_connected" if self.intelligence else "not_connected"},
                "models": {"planner": self.provider.planner_model, "critic": self.provider.critic_model, "researcher": "统计研究器"},
                "positions": positions, "market": markets, "curve": state["curve"], "rounds": list(reversed(state["rounds"])),
                "trades": list(reversed(state["trades"])), "research": list(reversed(state["research"])),
                "events": list(reversed(state["events"])),
                "risk": {"max_position": MAX_POSITION, "max_exposure": MAX_EXPOSURE, "risk_per_trade": RISK_PER_TRADE,
                         "fee": FEE, "slippage": SLIPPAGE, "stale_seconds": MAX_SNAPSHOT_AGE},
            })
