"""US reading scopes and social provenance must not invent market impact or authorship."""
import tempfile
import unittest
from pathlib import Path

from trader.intelligence.processing import normalize, build_digest
from trader.intelligence.service import IntelligenceHub
from trader.intelligence.sources import Source, parse_x

NOW = 1788960000.0


def report(title, key="1", url="https://example.org/news"):
    return {"external_id": key, "title": title, "text": title, "url": url, "published_at": NOW - 30}


class USIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.media = Source(id="news", name="News", kind="rss", url="https://example.org/rss", tier="T2", reliability=.8)
        self.trump = Source(id="trump", name="Trump X", kind="x", query="from:realDonaldTrump -is:retweet",
                            account="realDonaldTrump", person="trump", tier="T1.5", reliability=.65)
        self.hub = IntelligenceHub(Path(self.temp.name) / "intel.sqlite3", [self.media, self.trump])

    def tearDown(self):
        self.hub.close()
        self.temp.cleanup()

    def test_us_scope_filters_crypto_and_keeps_company_and_policy_reports(self):
        self.hub.ingest(self.media, [report("Nvidia announced quarterly earnings", "nvda"),
                                   report("Trump plans 25% tariffs", "policy"),
                                   report("Bitcoin ETF approved", "crypto"),
                                   report("Trump attends birthday party", "noise")], NOW)
        result = self.hub.feed(NOW, market="us", mode="timeline")
        self.assertEqual(result["feed"]["matched_total"], 2)
        self.assertIn("NVDA", result["context"]["watchlist"])
        self.assertNotIn("BTC", result["context"]["watchlist"])
        categories = {e["category"] for e in result["events"]}
        self.assertEqual(categories, {"earnings", "policy"})
        self.assertEqual(self.hub.feed(NOW, market="all", mode="timeline")["feed"]["matched_total"], 3)

    def test_trump_is_not_automatically_trump_media_stock(self):
        item = normalize(report("Trump announced tariffs on imports"), self.media, NOW)
        self.assertNotIn("DJT", item["assets"])
        self.assertEqual(item["focus"]["people"], ["trump"])
        company = normalize(report("Trump Media announced quarterly earnings"), self.media, NOW)
        self.assertIn("DJT", company["assets"])

    def test_ambiguous_words_are_not_stock_tickers(self):
        item=normalize(report("A spy discusses meta analysis of tariffs"), self.media, NOW)
        self.assertNotIn("SPY",item["assets"])
        self.assertNotIn("META",item["assets"])
        stocks=normalize(report("SPY and META earnings report"), self.media, NOW)
        self.assertIn("SPY",stocks["assets"])
        self.assertIn("META",stocks["assets"])

    def test_account_author_required_and_retelling_not_merged_into_original(self):
        title = "Nvidia will face export controls"
        posts = parse_x({"data": [{"id": "123", "text": title, "author_id": "user1", "created_at": "2026-09-09T12:00:00Z"}],
                         "includes": {"users": [{"id": "user1", "username": "realDonaldTrump"}]}})
        posts[0]["published_at"] = NOW - 30
        self.hub.ingest(self.trump, posts, NOW)
        self.hub.ingest(self.media, [report(title)], NOW)
        original = self.hub.feed(NOW, market="us", person="trump", origin="account_post", mode="timeline")
        self.assertEqual(original["feed"]["matched_total"], 1)
        self.assertEqual(original["events"][0]["verification"], "unverified")
        self.assertEqual(original["events"][0]["evidence_count"], 1)
        self.assertEqual(self.hub.feed(NOW, market="us", origin="report", mode="timeline")["feed"]["matched_total"], 1)
        missing_author = normalize(report(title, url="https://x.com/i/web/status/123"), self.trump, NOW)
        self.assertEqual(missing_author["focus"]["attribution"], "social_unverified")
        self.assertNotIn("trump", missing_author["focus"]["people"])

    def test_media_mentions_and_imports_cannot_become_verified_originals(self):
        self.hub.ingest(self.media, [report("Trump says Tesla tariffs will change")], NOW)
        self.assertEqual(self.hub.feed(NOW, person="trump", origin="report", mode="timeline")["feed"]["matched_total"], 1)
        self.assertEqual(self.hub.feed(NOW, person="trump", origin="account_post", mode="timeline")["events"], [])
        imported = Source(id="truth", name="Truth import", kind="jsonl", person="trump", account="realDonaldTrump")
        item = normalize(report("New tariffs announced", url="https://truthsocial.com/@realDonaldTrump/posts/123"), imported, NOW)
        self.assertEqual(item["focus"]["attribution"], "imported_post")
        self.assertEqual(item["focus"]["people"], ["trump"])
        wrong = normalize(report("New tariffs announced", url="https://truthsocial.com/@someone/posts/123"), imported, NOW)
        self.assertEqual(wrong["focus"]["people"], [])

    def test_person_filter_before_pagination_and_no_future_information(self):
        rows = [report(f"Trump announced tariffs of {n}%", str(n)) for n in range(35)]
        self.hub.ingest(self.media, rows + [report("Tesla earnings announced", "other")], NOW)
        first = self.hub.feed(NOW, market="us", person="trump", mode="timeline", limit=20)
        self.hub.ingest(self.media, [report("Trump announced new Nvidia tariffs", "future")], NOW+1)
        second = self.hub.feed(NOW, market="us", person="trump", mode="timeline", offset=first["feed"]["next_offset"], limit=20)
        self.assertEqual(first["feed"]["counts"]["timeline"], 35)
        self.assertEqual(len(second["events"]), 15)
        self.assertFalse({e["id"] for e in first["events"]} & {e["id"] for e in second["events"]})
        for kwargs in ({"market": "invalid"}, {"person": "other"}, {"origin": "verified"}):
            with self.assertRaises(ValueError):
                self.hub.feed(NOW, **kwargs)


if __name__ == "__main__":
    unittest.main()
