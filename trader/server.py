"""Loopback-only HTTP API and independent market/cognition workers."""
from __future__ import annotations

import argparse
import csv
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .cognition import ModelCognition, RuleCognition
from .engine import Engine
from .intelligence.service import DEFAULT_CONFIG, IntelligenceHub
from .intelligence.sources import timestamp

WEB = Path(__file__).resolve().parent / "web"


class Runtime:
    def __init__(self, engine, interval=3):
        self.engine = engine
        self.interval = interval
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.threads = [threading.Thread(target=self.market_loop, daemon=True), threading.Thread(target=self.cognition_loop, daemon=True)]

    def start(self):
        for thread in self.threads:
            thread.start()

    def market_loop(self):
        while not self.stop.wait(self.interval):
            try:
                with self.engine.lock:
                    if not self.engine.state["running"]:
                        continue
                    self.engine.advance()
                    tick = self.engine.state["tick"]
                if tick % 4 == 0:
                    self.wake.set()
                if tick % 672 == 0:
                    self.engine.run_research()
            except Exception as exc:
                self.engine.report_error(exc)

    def cognition_loop(self):
        while not self.stop.is_set():
            if self.wake.wait(0.5):
                self.wake.clear()
                try:
                    self.engine.cognize()
                except Exception as exc:
                    self.engine.report_error(exc)


def handler_for(engine, runtime):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, content, mime="application/json; charset=utf-8"):
            data = content if isinstance(content, bytes) else json.dumps(content, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def valid_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {"error": "Invalid host"})
            path = urlparse(self.path).path
            if path.startswith("/api/intelligence"):
                hub=engine.intelligence
                if hub is None:
                    return self.send(503,{"error":"Intelligence subsystem is disabled"})
                query=parse_qs(urlparse(self.path).query)
                focus=query.get("assets",[""])[0]
                if len(focus)>100:
                    return self.send(400,{"error":"assets exceeds 100 characters"})
                context={"watchlist":[s.strip().upper() for s in focus.split(",") if s.strip()]}
                if not focus:
                    with engine.lock:
                        context={"holdings":list(engine.state["positions"]),"watchlist":list(engine.state["bars"])}
                if path=="/api/intelligence":
                    return self.send(200,{"status":hub.status(),"digest":hub.digest(context=context),"notifications":hub.notifications(),"recent":hub.recent_evidence()})
                if path=="/api/intelligence/feed":
                    at=query.get("as_of",[None])[0]
                    cutoff=timestamp(at) if at is not None else None
                    if at is not None and cutoff is None:
                        return self.send(400,{"error":"as_of requires an ISO-8601 timestamp with timezone"})
                    if cutoff is not None and not focus:
                        context={}
                    # Explicit context keeps pagination at the same cutoff and scoring assumptions.
                    if "holdings" in query:
                        holdings=query["holdings"][0]
                        if len(holdings)>100:
                            return self.send(400,{"error":"holdings exceeds 100 characters"})
                        context["holdings"]=[s.strip().upper() for s in holdings.split(",") if s.strip()]
                    try:
                        result=hub.feed(cutoff,context,mode=query.get("mode",["selected"])[0],category=query.get("category",[""])[0],
                                        source_id=query.get("source",[""])[0],query=query.get("q",[""])[0],window=query.get("window",["24h"])[0],
                                        offset=int(query.get("offset",["0"])[0]),limit=int(query.get("limit",["30"])[0]))
                        return self.send(200,result)
                    except ValueError:
                        return self.send(400,{"error":"Invalid feed filters or pagination"})
                if path=="/api/intelligence/digest":
                    query=parse_qs(urlparse(self.path).query)
                    at=query.get("as_of",[None])[0]
                    cutoff=timestamp(at) if at is not None else None
                    if at is not None and cutoff is None:
                        return self.send(400,{"error":"as_of requires an ISO-8601 timestamp with timezone"})
                    # Historical account holdings are not available here. Never inject today's holdings into replay.
                    if cutoff is not None and not focus:
                        context={}
                    return self.send(200,hub.digest(cutoff,context=context))
                if path.startswith("/api/intelligence/evidence/"):
                    item=hub.evidence(path.rsplit("/",1)[-1])
                    return self.send(200,item) if item else self.send(404,{"error":"Evidence not found"})
                return self.send(404,{"error":"Not found"})
            if path == "/api/state":
                return self.send(200, engine.view())
            if path == "/api/audit":
                return self.send(200, engine.audit())
            if path == "/api/trades.csv":
                buffer = io.StringIO(newline="")
                fields = ["id", "time", "symbol", "side", "quantity", "price", "fee", "pnl", "reason", "client_order_id"]
                writer = csv.DictWriter(buffer, fields, extrasaction="ignore")
                writer.writeheader()
                # Export complete history, not the dashboard's bounded window.
                with engine.lock:
                    for row in engine.db.execute("SELECT payload FROM audit ORDER BY id"):
                        event = json.loads(row[0])
                        if event["kind"] == "fill":
                            writer.writerow(event["trade"])
                return self.send(200, buffer.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8")
            static = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css"),
                      "/intelligence.js": ("intelligence.js", "text/javascript"), "/intelligence.css": ("intelligence.css", "text/css")}
            if path in static:
                name, mime = static[path]
                return self.send(200, (WEB / name).read_bytes(), mime + "; charset=utf-8")
            return self.send(404, {"error": "Not found"})

        def do_POST(self):
            if not self.valid_host() or self.headers.get("Origin", f"http://{self.headers.get('Host')}") != f"http://{self.headers.get('Host')}":
                return self.send(403, {"error": "Only same-origin local commands are accepted"})
            if self.headers.get("Content-Type") != "application/json":
                return self.send(415, {"error": "Use application/json"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 4096:
                    return self.send(413, {"error": "Payload too large"})
                body = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
                path = urlparse(self.path).path
                if path == "/api/intelligence/collect":
                    if engine.intelligence is None:
                        return self.send(503,{"error":"Intelligence subsystem is disabled"})
                    engine.intelligence.request_collection()
                elif path == "/api/start":
                    engine.set_running(True)
                elif path == "/api/pause":
                    engine.set_running(False)
                elif path == "/api/step":
                    if engine.view()["running"]:
                        raise ValueError("请先暂停自动模拟，再手动推进。")
                    engine.advance(4)
                    runtime.wake.set()
                elif path == "/api/cognize":
                    runtime.wake.set()
                elif path == "/api/research":
                    engine.run_research()
                elif path == "/api/flatten":
                    engine.flatten()
                else:
                    return self.send(404, {"error": "Not found"})
                self.send(200, {"ok": True})
            except (ValueError, TypeError):
                self.send(400, {"error": "操作无效：请检查账户是否熔断、是否已暂停，以及 JSON 格式。"})
            except Exception as exc:
                engine.report_error(exc)
                self.send(500, {"error": "运行失败，系统已暂停；请查看系统日志。"})
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local paper-only Trader reproduction")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", default="data/trader.sqlite3")
    parser.add_argument("--interval", type=float, default=3, help="Wall seconds per simulated 15-minute bar")
    parser.add_argument("--llm", action="store_true", help="Explicitly enable model API calls; provider billing may apply")
    parser.add_argument("--no-demo", action="store_true", help="Start without the 48-bar paper replay")
    parser.add_argument("--intel-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--intel-db", type=Path, default=Path("data/intelligence.sqlite3"))
    parser.add_argument("--no-intelligence", action="store_true", help="Disable public-feed collection")
    parser.add_argument("--enable-x-api", action="store_true", help="Explicitly enable configured X requests, potentially billable")
    args = parser.parse_args()
    if args.interval < 0.1:
        parser.error("--interval must be at least 0.1 seconds")
    provider = ModelCognition() if args.llm else RuleCognition()
    path = Path(args.db).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not args.no_intelligence and path==args.intel_db.resolve():
        parser.error("Trading and intelligence require separate database files")
    hub = None if args.no_intelligence else IntelligenceHub.from_config(args.intel_db.resolve(),args.intel_config.resolve(),args.enable_x_api)
    engine = Engine(path, provider, hub)
    if engine.fresh and not args.no_demo and not args.llm:
        for _ in range(12):
            engine.advance(4)
            engine.cognize()
        engine.run_research()
    runtime = Runtime(engine, args.interval)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(engine, runtime))
    runtime.start()
    if hub:
        hub.start()
    print(f"Trader paper mode: http://127.0.0.1:{args.port} | provider={provider.name} | feed=synthetic", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop.set()
        for thread in runtime.threads:
            thread.join(timeout=55)
        server.server_close()
        engine.close()
        if hub:
            hub.close()


if __name__ == "__main__":
    main()
