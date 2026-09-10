import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
import time

from trader.engine import Engine
from trader.server import Runtime, handler_for
from trader.intelligence.service import IntelligenceHub
from trader.intelligence.sources import Source


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = Engine(Path(self.temp.name)/"api.sqlite3")
        self.runtime = Runtime(self.engine)
        self.server = ThreadingHTTPServer(("127.0.0.1",0),handler_for(self.engine,self.runtime))
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.engine.close()
        self.temp.cleanup()

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request(self.url+path,body,headers or {})
        return urllib.request.urlopen(req,timeout=3)

    def test_state_assets_and_step(self):
        with self.request("/api/state") as response:
            self.assertEqual(json.load(response)["mode"],"paper")
        for path in ("/","/style.css","/app.js","/intelligence.js","/intelligence.css"):
            with self.request(path) as response:
                self.assertEqual(response.status,200)
        tick=self.engine.state["tick"]
        with self.request("/api/step",b"{}",{"Content-Type":"application/json"}) as response:
            self.assertTrue(json.load(response)["ok"])
        self.assertEqual(self.engine.state["tick"],tick+4)
        with self.request("/api/trades.csv") as response:
            self.assertIn("client_order_id",response.read().decode("utf-8-sig"))

    def test_cross_origin_and_invalid_payload_rejected(self):
        for headers, body, status in [
            ({"Content-Type":"application/json","Origin":"https://example.org"},b"{}",403),
            ({"Content-Type":"text/plain"},b"{}",415),
            ({"Content-Type":"application/json"},b"[]",400),
            ({"Content-Type":"application/json"},b"broken",400),
        ]:
            with self.subTest(status=status),self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/api/start",body,headers)
            self.assertEqual(error.exception.code,status)
        self.assertFalse(self.engine.state["running"])

    def test_intelligence_api_evidence_and_replay(self):
        s=Source(id="feed",name="feed",kind="rss",url="https://example.org/feed")
        hub=IntelligenceHub(Path(self.temp.name)/"intel.sqlite3",[s])
        self.engine.intelligence=hub
        try:
            now=time.time()
            hub.ingest(s,[{"external_id":"1","title":"Bitcoin ETF news","text":"Bitcoin ETF news","published_at":now-10}],now)
            with self.request("/api/intelligence") as response:
                data=json.load(response)
            self.assertEqual(len(data["digest"]["events"]),1)
            with self.request("/api/intelligence/feed?mode=timeline&assets=SOL&limit=1") as response:
                feed=json.load(response)
                self.assertEqual(feed["feed"]["matched_total"],1)
                self.assertEqual(feed["context"]["watchlist"],["SOL"])
            for query in ("mode=invalid","limit=0","offset=-1","category=other","as_of=bad","window=forever"):
                with self.subTest(query=query),self.assertRaises(urllib.error.HTTPError) as error:
                    self.request("/api/intelligence/feed?"+query)
                self.assertEqual(error.exception.code,400)
            self.assertEqual(data["digest"]["context"]["watchlist"],["BTC","ETH","SOL"])
            with self.request("/api/intelligence/digest?assets=SOL") as response:
                self.assertEqual(json.load(response)["context"]["watchlist"],["SOL"])
            identifier=data["recent"][0]["id"]
            with self.request("/api/intelligence/evidence/"+identifier) as response:
                self.assertEqual(json.load(response)["title"],"Bitcoin ETF news")
            with self.request("/api/intelligence/digest?as_of=2020-01-01T00:00:00Z") as response:
                replay=json.load(response)
                self.assertEqual(replay["events"],[])
                self.assertEqual(replay["context"],{"holdings":[],"watchlist":[]})
            with self.request("/api/intelligence/collect",b"{}",{"Content-Type":"application/json"}):
                self.assertTrue(hub.poll_event.is_set())
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/api/intelligence/digest?as_of=bad")
            self.assertEqual(error.exception.code,400)
        finally:
            hub.close()


if __name__ == "__main__":
    unittest.main()
