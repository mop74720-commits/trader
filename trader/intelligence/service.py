"""Collector daemon, append-only evidence versions, source health, and replayable digests."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .processing import build_digest, fingerprint, normalize
from .sources import Batch, FetchError, Source, collect, load_sources

DEFAULT_CONFIG=Path(__file__).resolve().parents[2]/"config"/"intelligence.sources.json"


class IntelligenceHub:
    def __init__(self, path: Path, sources: list[Source], config_dir: Path | None = None, allow_x=False, fetcher=collect):
        self.sources=sources
        self.config_dir=(config_dir or DEFAULT_CONFIG.parent).resolve()
        self.allow_x=allow_x
        self.fetcher=fetcher
        self.lock=threading.RLock()
        self.collect_lock=threading.Lock()
        self.stop_event=threading.Event()
        self.poll_event=threading.Event()
        self.thread=None
        self.last_error=None
        self.db=sqlite3.connect(str(path),check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        # Separate new database: the trading account schema is not changed.
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS intel_meta(version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence(
                seq INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
                source_id TEXT NOT NULL, external_id TEXT NOT NULL,
                observed_at REAL NOT NULL, content_hash TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS evidence_asof ON evidence(source_id,external_id,observed_at DESC);
            CREATE TABLE IF NOT EXISTS observations(evidence_id TEXT NOT NULL,observed_at REAL NOT NULL,PRIMARY KEY(evidence_id,observed_at));
            CREATE TABLE IF NOT EXISTS source_state(source_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS polls(seq INTEGER PRIMARY KEY,source_id TEXT NOT NULL,observed_at REAL NOT NULL,payload TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS polls_asof ON polls(source_id,observed_at DESC);
            CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,observed_at REAL NOT NULL,payload TEXT NOT NULL);
        ''')
        row=self.db.execute("SELECT version FROM intel_meta").fetchone()
        if row is None:
            self.db.execute("INSERT INTO intel_meta VALUES (1)")
            self.db.commit()
        elif row[0]!=1:
            self.db.close()
            raise ValueError("Unsupported intelligence database version")

    @classmethod
    def from_config(cls, path: Path, config: Path=DEFAULT_CONFIG, allow_x=False):
        path.parent.mkdir(parents=True,exist_ok=True)
        return cls(path,load_sources(config),config.parent,allow_x)

    def _state(self, source_id):
        row=self.db.execute("SELECT payload FROM source_state WHERE source_id=?",(source_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def _save_source(self, source, state, now):
        payload=json.dumps(state,ensure_ascii=False,allow_nan=False)
        self.db.execute("INSERT INTO source_state VALUES (?,?) ON CONFLICT(source_id) DO UPDATE SET payload=excluded.payload",(source.id,payload))
        self.db.execute("INSERT INTO polls(source_id,observed_at,payload) VALUES (?,?,?)",(source.id,now,payload))

    def ingest(self, source: Source, raw_items: list[dict], observed_at: float | None=None, batch: Batch | None=None):
        now=time.time() if observed_at is None else observed_at
        items=[]
        rejected=0
        for raw in raw_items:
            try:
                items.append(normalize(raw,source,now))
            except (ValueError,TypeError,AttributeError,KeyError,OverflowError):
                rejected+=1
        if raw_items and not items:
            raise FetchError("all_items_invalid")
        added=0
        with self.lock,self.db:
            for item in items:
                row=self.db.execute("SELECT payload FROM evidence WHERE source_id=? AND external_id=? ORDER BY seq DESC LIMIT 1",(source.id,item["external_id"])).fetchone()
                previous=json.loads(row[0]) if row else None
                if previous and previous["content_hash"]==item["content_hash"]:
                    self.db.execute("INSERT OR IGNORE INTO observations VALUES (?,?)",(previous["id"],now))
                    continue
                if previous and now<previous["observed_at"]:
                    raise ValueError("Observation time cannot move backwards for one source item")
                item["revision"]=previous["revision"]+1 if previous else 1
                item["first_observed_at"]=previous["first_observed_at"] if previous else now
                item["id"]=fingerprint({"source":source.id,"external":item["external_id"],"hash":item["content_hash"],"revision":item["revision"],"observed_at":now})[:24]
                self.db.execute("INSERT INTO evidence(id,source_id,external_id,observed_at,content_hash,payload) VALUES (?,?,?,?,?,?)",
                                (item["id"],source.id,item["external_id"],now,item["content_hash"],json.dumps(item,ensure_ascii=False,allow_nan=False)))
                self.db.execute("INSERT INTO observations VALUES (?,?)",(item["id"],now))
                added+=1
                eligible=build_digest([item],now)["events"]
                material=True
                reason="new_item" if previous is None else "content_revision"
                change=None
                baseline=None
                if item["kind"]=="prediction_market":
                    # The last notified observation is the durable baseline, not the last tiny edit.
                    row=self.db.execute('''SELECT e.payload FROM notifications n JOIN evidence e
                        ON e.id=json_extract(n.payload,'$.evidence_id')
                        WHERE e.source_id=? AND e.external_id=? AND n.observed_at<=?
                        ORDER BY n.observed_at DESC,e.seq DESC LIMIT 1''',(source.id,item["external_id"],now)).fetchone()
                    baseline=json.loads(row[0]) if row else None
                    reason="first_quote"
                    if baseline:
                        old={q["outcome"]:q["price"] for q in baseline["metrics"].get("outcomes",[])}
                        new={q["outcome"]:q["price"] for q in item["metrics"].get("outcomes",[])}
                        if old.keys()!=new.keys():
                            reason="quote_outcomes_changed"
                        elif (item["title"],item["metrics"].get("end_at"))!=(baseline["title"],baseline["metrics"].get("end_at")):
                            reason="quote_terms_changed"
                        else:
                            change=max((abs(new[k]-old[k]) for k in new),default=0)
                            reason="quote_price_change"
                            material=change+1e-9>=.05
                if eligible and material:
                    # Exact reposts across sources do not generate another notification.
                    notice_id=fingerprint({"evidence":item["id"]} if item["kind"]=="prediction_market" else {"content":item["content_hash"],"day":int(now//86400)})[:24]
                    notice={"id":notice_id,"evidence_id":item["id"],"title":item["title"],"kind":"new_event" if previous is None else "revision",
                            "observed_at":now,"source_id":source.id,"priority":eligible[0]["priority"],"execution_authority":False,
                            "reason":reason,"max_price_change":change,"baseline_evidence_id":baseline["id"] if baseline else None}
                    self.db.execute("INSERT OR IGNORE INTO notifications VALUES (?,?,?)",(notice_id,now,json.dumps(notice,ensure_ascii=False)))
            state=self._state(source.id)
            state.update({"last_attempt":now,"last_success":now,"failures":0,"error":None,"next_poll":now+source.interval_seconds,
                          "fetched_items":len(raw_items),"new_versions":added,"invalid_items":rejected})
            if batch:
                state.update(cursor=batch.cursor,etag=batch.etag,last_modified=batch.last_modified,coverage=batch.coverage)
                if batch.cursor.get("next_token"):
                    state["next_poll"]=now+30
            self._save_source(source,state,now)
        return added

    def record_failure(self, source, code, observed_at=None, retry_after=0):
        now=time.time() if observed_at is None else observed_at
        with self.lock,self.db:
            state=self._state(source.id)
            failures=state.get("failures",0)+1
            # Bounded exponential backoff, survives restarts; no sleeping inside the worker.
            delay=max(retry_after,min(3600,source.interval_seconds*(2**min(failures,6))))
            state.update(last_attempt=now,failures=failures,error=code,next_poll=now+delay)
            self._save_source(source,state,now)

    def collect_once(self, force=False):
        if not self.collect_lock.acquire(blocking=False):
            return self.status()
        try:
            now=time.time()
            with self.lock:
                due=[(s,self._state(s.id)) for s in self.sources if s.enabled and (force or self._state(s.id).get("next_poll",0)<=now)]
            # Separate sources may fetch concurrently; persistence is serialized after each response.
            with ThreadPoolExecutor(max_workers=4,thread_name_prefix="intel-source") as pool:
                futures={pool.submit(self.fetcher,s,state,now,self.config_dir,self.allow_x):s for s,state in due}
                for future in as_completed(futures):
                    source=futures[future]
                    try:
                        batch=future.result()
                        self.ingest(source,batch.items,time.time(),batch)
                    except FetchError as exc:
                        self.record_failure(source,exc.code,retry_after=exc.retry_after)
                    except Exception as exc:
                        self.record_failure(source,type(exc).__name__)
            self.last_error=None
        finally:
            self.collect_lock.release()
        return self.status()

    def _latest(self, as_of, limit=2000):
        # Select a version available then, not the latest edit with an old publication date.
        rows=self.db.execute('''
            SELECT payload,COALESCE((SELECT MAX(o.observed_at) FROM observations o WHERE o.evidence_id=latest.id AND o.observed_at<=?),observed_at) FROM (
                SELECT seq,id,payload,observed_at,ROW_NUMBER() OVER (
                    PARTITION BY source_id,external_id ORDER BY observed_at DESC,seq DESC
                ) AS n FROM evidence WHERE observed_at<=?
            ) AS latest WHERE n=1 ORDER BY observed_at DESC LIMIT ?
        ''',(as_of,as_of,limit))
        return [{**json.loads(row[0]),"last_observed_at":row[1]} for row in rows]

    def digest(self, as_of: float | None=None, context=None, include_candidates=False):
        now=time.time() if as_of is None else as_of
        with self.lock:
            enabled={s.id for s in self.sources if s.enabled}
            items=[i for i in self._latest(now) if i["source_id"] in enabled]
            tiers={s.id:s.tier for s in self.sources}
            for item in items:
                if "source_tier" not in item:
                    item["source_tier"]=tiers.get(item["source_id"],"unrated")
                    item["tier_basis"]="current_config_fallback"
            # Health uses the most recent poll available by the same cutoff, never future polls.
            coverage=[]
            for s in self.sources:
                if not s.enabled:
                    continue
                row=self.db.execute("SELECT payload FROM polls WHERE source_id=? AND observed_at<=? ORDER BY observed_at DESC,seq DESC LIMIT 1",(s.id,now)).fetchone()
                p=json.loads(row[0]) if row else {}
                coverage.append({"source_id":s.id,"last_success":p.get("last_success"),"error":p.get("error"),
                                 "coverage":p.get("coverage","not_collected"),"stale":not p.get("last_success") or now-p["last_success"]>max(120,s.interval_seconds*3)})
        # CPU processing works on detached evidence; collectors can keep committing observations.
        result=build_digest(items,now,context=context,include_candidates=include_candidates)
        result["sources"]=coverage
        result["health"]="disabled" if not coverage else "degraded" if any(p["stale"] or p["error"] for p in coverage) else "healthy"
        result["candidate_limit"]=2000
        result["replay_policy"]="historical_evidence_current_processor_and_enabled_sources"
        return result

    def feed(self, as_of=None, context=None, mode="selected", category="", source_id="", query="", window="24h", offset=0, limit=30):
        """Filter the complete bounded candidate pool before pagination, never just the digest's top 12."""
        if mode not in {"selected","timeline","quotes"} or window not in {"24h","7d"}:
            raise ValueError("Invalid feed mode or window")
        if category not in {"","security","monetary_policy","regulation","exchange","derivatives","market"}:
            raise ValueError("Invalid feed category")
        if not 0<=offset<=2000 or not 1<=limit<=100 or len(query)>200:
            raise ValueError("Invalid feed bounds")
        result=self.digest(as_of,context,include_candidates=True)
        cutoff=result["as_of"]
        start=cutoff-(86400 if window=="24h" else 7*86400)
        candidates=[]
        for event in result.pop("candidates"):
            at=event["last_observed_at"] if event["kind"]=="prediction_market" else event["timeline_at"]
            if not start<=at<=cutoff or (category and event["category"]!=category):
                continue
            if source_id and source_id not in event["source_ids"]:
                continue
            haystack=" ".join([event["title"],event["summary"],*event["assets"],*[p["quote"] for p in event.get("related_evidence",[])]])
            if query.strip().casefold() not in haystack.casefold():
                continue
            candidates.append(event)
        counts={"selected":sum(e["editorial"]["selected"] for e in candidates),
                "timeline":sum(e["kind"]=="report" for e in candidates),
                "quotes":sum(e["kind"]=="prediction_market" for e in candidates)}
        events=[e for e in candidates if (e["editorial"]["selected"] if mode=="selected" else e["kind"]==("prediction_market" if mode=="quotes" else "report"))]
        events.sort(key=lambda e:(e["last_observed_at"] if mode=="quotes" else e["timeline_at"],e["id"]),reverse=True)
        result["events"]=events[offset:offset+limit]
        result["feed"]={"mode":mode,"window":window,"from":start,"to":cutoff,"category":category,"source_id":source_id,"query":query,
                        "matched_total":len(events),"counts":counts,"offset":offset,"limit":limit,
                        "next_offset":offset+limit if offset+limit<len(events) else None,
                        "time_basis":"publisher_time_or_first_observation; quotes_last_observation"}
        result["id"]=fingerprint({"digest":result["id"],"feed":result["feed"],"events":result["events"]})[:24]
        return result

    def status(self, as_of=None):
        now=time.time() if as_of is None else as_of
        with self.lock:
            sources=[]
            for source in self.sources:
                state=self._state(source.id)
                # Pagination cursors can contain provider-internal information; omit them from UI.
                public={k:v for k,v in state.items() if k not in {"cursor","etag","last_modified"}}
                health="disabled" if not source.enabled else "pending" if not state.get("last_attempt") else "error" if state.get("error") else "stale" if now-state.get("last_success",0)>max(120,source.interval_seconds*3) else "healthy"
                sources.append({**source.public(),**public,"health":health})
            enabled=[s for s in sources if s["enabled"]]
            latest=self._latest(now)
            version_counts=dict(self.db.execute("SELECT json_extract(payload,'$.kind'),count(*) FROM evidence GROUP BY json_extract(payload,'$.kind')"))
            return {"health":"disabled" if not enabled else "healthy" if all(s["health"]=="healthy" for s in enabled) else "degraded",
                    "sources":sources,"collecting":self.collect_lock.locked(),"last_error":self.last_error,
                    "versions":self.db.execute("SELECT count(*) FROM evidence").fetchone()[0],"items":len(latest),
                    "report_versions":version_counts.get("report",0),"quote_versions":version_counts.get("prediction_market",0),
                    "observations":self.db.execute("SELECT count(*) FROM observations").fetchone()[0],
                    "quarantined":sum(i["quarantined"] for i in latest),"filtered":sum(not i["relevant"] for i in latest),
                    "as_of":now,"retention":"append_only","item_window_limit":2000}

    def evidence(self, identifier):
        with self.lock:
            row=self.db.execute("SELECT payload FROM evidence WHERE id=?",(identifier,)).fetchone()
            return json.loads(row[0]) if row else None

    def recent_evidence(self, limit=100):
        with self.lock:
            return self._latest(time.time(),limit)

    def notifications(self, limit=30):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute("SELECT payload FROM notifications ORDER BY observed_at DESC LIMIT ?",(limit,))]

    def request_collection(self):
        # UI requests a scheduler pass. Backoff and source polling intervals still apply.
        self.poll_event.set()

    def start(self):
        if self.thread:
            return
        self.thread=threading.Thread(target=self._loop,name="intelligence-collector",daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.collect_once()
            except Exception as exc:
                self.last_error=type(exc).__name__
            self.poll_event.wait(5)
            self.poll_event.clear()

    def close(self):
        self.stop_event.set()
        self.poll_event.set()
        if self.thread:
            self.thread.join(timeout=55)
            if self.thread.is_alive():
                raise RuntimeError("Collector still running; database not closed")
        with self.lock:
            self.db.close()
