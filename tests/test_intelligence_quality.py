"""Adversarial fixtures for information quality; not a real-world accuracy benchmark."""
import tempfile
import unittest
from pathlib import Path

from trader.intelligence.processing import build_digest, normalize
from trader.intelligence.service import IntelligenceHub
from trader.intelligence.sources import Source, parse_polymarket

NOW=1788960000.0


def source(name="news"):
    return Source(id=name,name=name,kind="rss",url="https://example.org/feed",group=name,reliability=.8)


def item(title, identifier="1", **values):
    return {"external_id":identifier,"title":title,"text":title,"published_at":NOW-60,**values}


def report(title, identifier="1", publisher="news", **values):
    return normalize(item(title,identifier,**values),source(publisher),NOW)


class QualityTests(unittest.TestCase):
    def test_event_lifecycle_does_not_merge_application_plan_rumor_and_report(self):
        titles=["Bitcoin ETF approval application received", "Bitcoin ETF approval expected tomorrow",
                "Rumor: Bitcoin ETF approval confirmed", "Bitcoin ETF approval confirmed"]
        events=build_digest([report(t,str(n)) for n,t in enumerate(titles)],NOW)["events"]
        self.assertEqual(len(events),4)
        self.assertEqual({e["claim"]["status"] for e in events},{"application","planned","uncertain","reported"})
        self.assertTrue(all(e["verification"]=="unverified" for e in events))

    def test_body_background_negation_does_not_reverse_headline(self):
        a=report("Bitcoin ETF approved",text="Bitcoin ETF approved. Last year the regulator did not approve another fund.")
        b=report("Bitcoin ETF approved",publisher="second")
        self.assertEqual(len(build_digest([a,b],NOW)["events"]),1)

    def test_numbers_and_assets_prevent_false_merges(self):
        for titles in [("Bitcoin ETF inflows reach $100 million", "Bitcoin ETF inflows reach $200 million"),
                       ("Bitcoin exchange withdrawals suspended after incident", "Ethereum exchange withdrawals suspended after incident")]:
            with self.subTest(titles=titles):
                events=build_digest([report(t,str(n)) for n,t in enumerate(titles)],NOW)["events"]
                self.assertEqual(len(events),2)

    def test_same_contract_ids_from_different_providers_are_not_merged(self):
        events=build_digest([report("Bitcoin above 100k?",publisher=p,kind="prediction_market") for p in ("a","b")],NOW)["events"]
        self.assertEqual(len(events),2)

    def test_holding_context_changes_ranking_and_digest_identity(self):
        items=[report("Bitcoin ETF trading update","btc"),report("Solana validator network update","sol")]
        btc=build_digest(items,NOW,context={"holdings":["BTC"]})
        sol=build_digest(items,NOW,context={"holdings":["SOL"]})
        self.assertIn("BTC",btc["events"][0]["assets"])
        self.assertIn("SOL",sol["events"][0]["assets"])
        self.assertNotEqual(btc["id"],sol["id"])
        self.assertIn("relevance",btc["events"][0]["score_breakdown"])

    def test_unknown_facts_and_quote_execution_gaps_are_explicit(self):
        event=build_digest([report("Bitcoin outlook",published_at=None,url="")],NOW)["events"][0]
        self.assertEqual(event["claim"]["status"],"unknown")
        self.assertIsNone(event["claim"]["event_at"])
        self.assertIn("publication_time_missing",event["evidence_gaps"])
        self.assertIn("source_link_missing",event["evidence_gaps"])
        self.assertEqual(event["verification_request"]["status"],"not_performed")
        quote=build_digest([report("Bitcoin above 100k?",kind="prediction_market")],NOW)["events"][0]
        self.assertIn("orderbook_missing",quote["evidence_gaps"])
        self.assertIn("resolution_rules_unchecked",quote["evidence_gaps"])

    def test_quote_cap_is_global_and_head_evidence_matches_summary(self):
        quotes=[report(f"Bitcoin above {100+n}k?",str(n),publisher=f"p{n}",kind="prediction_market") for n in range(5)]
        self.assertEqual(len(build_digest(quotes,NOW)["events"]),3)
        low=report("Bitcoin ETF approved",publisher="low",text="Bitcoin ETF approved: short report.")
        high=report("Bitcoin ETF approved",publisher="high",text="Bitcoin ETF approved: detailed report.")
        high["reliability"]=.99
        e=build_digest([low,high],NOW)["events"][0]
        self.assertEqual(e["evidence"][0]["source_id"],"high")
        self.assertEqual(e["summary_evidence_id"],high["id"])

    def test_fingerprint_covers_evidence_beyond_visible_citations(self):
        records=[report("Bitcoin ETF approved",publisher=f"p{n}") for n in range(7)]
        records[-1]["reliability"]=.1
        before=build_digest(records,NOW)
        self.assertEqual(len(before["events"][0]["evidence"]),5)
        records[-1]=report("Bitcoin ETF approved",publisher="p6",text="Bitcoin ETF approved with additional detail.")
        records[-1]["reliability"]=.1
        self.assertNotEqual(before["id"],build_digest(records,NOW)["id"])


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"intel.sqlite3"
        self.hub=IntelligenceHub(self.path,[source()])

    def tearDown(self):
        self.hub.close()
        self.temp.cleanup()

    def quote(self,price,second,identifier="contract",outcome="Yes",liquidity=1000):
        self.hub.ingest(source(),[item("Bitcoin above 100k?",identifier,kind="prediction_market",
                        metrics={"outcomes":[{"outcome":outcome,"price":price}],"liquidity":liquidity})],NOW+second)

    def test_cumulative_threshold_survives_restart_and_resets_after_notice(self):
        self.quote(.50,0)
        self.quote(.52,1)
        self.hub.close()
        self.hub=IntelligenceHub(self.path,[source()])
        self.quote(.54,2)
        self.assertEqual(len(self.hub.notifications()),1)
        self.quote(.55,3)
        self.assertEqual(len(self.hub.notifications()),2)
        latest=self.hub.notifications()[0]
        self.assertEqual(latest["reason"],"quote_price_change")
        self.assertAlmostEqual(latest["max_price_change"],.05)
        self.quote(.58,4)
        self.assertEqual(len(self.hub.notifications()),2)
        self.quote(.50,5)
        self.assertEqual(len(self.hub.notifications()),3)

    def test_volume_churn_silent_but_outcome_change_explicit(self):
        self.quote(.5,0)
        self.quote(.5,1,liquidity=2000)
        self.assertEqual(len(self.hub.notifications()),1)
        self.quote(.5,2,outcome="Above")
        self.assertEqual(len(self.hub.notifications()),2)
        self.assertEqual(self.hub.notifications()[0]["reason"],"quote_outcomes_changed")

    def test_identical_quotes_on_distinct_contracts_have_distinct_notices(self):
        self.quote(.5,0,identifier="a")
        self.quote(.5,1,identifier="b")
        self.assertEqual(len(self.hub.notifications()),2)

    def test_real_adapter_text_prices_do_not_bypass_cumulative_threshold(self):
        for n,price in enumerate([.5,.52,.54,.55]):
            raw=parse_polymarket([{"slug":"btc","markets":[{"id":"m","question":"Bitcoin above 100k?",
                    "active":True,"closed":False,"outcomes":["Yes","No"],"outcomePrices":[price,1-price]}]}],NOW+n)
            self.hub.ingest(source(),raw,NOW+n)
            self.assertEqual(len(self.hub.notifications()),2 if n==3 else 1)
        event=self.hub.digest(NOW+3)["events"][0]
        self.assertNotIn("liquidity",event["metrics"])
        self.assertIn("liquidity_missing",event["evidence_gaps"])

    def test_replay_context_and_quality_counts(self):
        self.hub.ingest(source(),[item("Bitcoin ETF approved")],NOW)
        self.hub.ingest(source(),[item("Bitcoin ETF approved")],NOW+10)
        digest=self.hub.digest(NOW+5,context={"holdings":["BTC"]})
        self.assertEqual(digest["context"]["holdings"],["BTC"])
        self.assertEqual(digest["events"][0]["last_observed_at"],NOW)
        self.assertEqual(digest["quality"]["unverified_reports"],1)
        status=self.hub.status(NOW+10)
        self.assertEqual(status["observations"],2)
        self.assertEqual(status["report_versions"],1)
        self.assertEqual(status["quote_versions"],0)


if __name__=="__main__":
    unittest.main()
