"""Deterministic evidence processing. Scores prioritize reading; they do not prove truth."""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .sources import Source, Tree, timestamp
from .curation import POLICY, TIERS, assess, market_relevant, policy_id, select

PROCESSOR_VERSION="intel-v3"
ASSETS={
    "BTC":r"\b(?:btc|bitcoin)\b|比特币",
    "ETH":r"\b(?:eth|ethereum|ether)\b|以太坊",
    "SOL":r"\b(?:sol|solana)\b|索拉纳",
    "XRP":r"\b(?:xrp|ripple)\b|瑞波",
    "DOGE":r"\b(?:doge|dogecoin)\b|狗狗币",
    "ZEC":r"\b(?:zec|zcash)\b",
    "USDT":r"\b(?:usdt|tether)\b",
    "USDC":r"\b(?:usdc|circle)\b",
}
TOPICS={
    "monetary_policy":r"\b(?:fed|fomc|federal reserve|interest rate|inflation|cpi|payroll|ecb)\b|美联储|降息|加息|通胀|非农",
    "regulation":r"\b(?:sec|regulator|regulation|lawsuit|tax|etf|approval|approved)\b|监管|批准|税收|诉讼",
    "security":r"\b(?:hack|hacked|exploit|breach|stolen|depeg|insolvency)\b|黑客|被盗|漏洞|脱锚|破产",
    "exchange":r"\b(?:exchange|binance|coinbase|kraken|listing|list|delist|withdrawal|margin)\b|交易所|上线|下架|提现|保证金",
    "derivatives":r"\b(?:funding|futures|liquidation|open interest)\b|资金费率|期货|清算|爆仓|持仓量",
    "market":r"\b(?:crypto|bitcoin|ethereum|blockchain|stablecoin|defi)\b|加密|区块链|稳定币",
}
INJECTION_PATTERNS=[
    r"ignore\s+(?:all\s+)?(?:previous|prior|system|above)\s+instructions",
    r"(?:system|developer)\s*(?:prompt|message)\s*:",
    r"(?:reveal|print|send|exfiltrate)\s+(?:your\s+)?(?:api\s*key|secret|password|credentials)",
    r"(?:disable|bypass|override)\s+(?:the\s+)?(?:risk|stop.loss|safety|guardrail)",
    r"<\|(?:im_start|system|assistant|developer)",
    r"忽略.{0,10}(?:指令|提示|规则)|(?:关闭|绕过|取消).{0,8}(?:风控|止损)|泄露.{0,8}(?:密钥|密码)",
]
STOPWORDS=set("the a an is are was were of to on for and in by with at from as will be has have this that it its new says said news update".split())
NEGATION=r"\b(?:not|no|denied|reject(?:ed|ion)?|false|untrue|debunked)\b|未获|否认|驳回|不实|未批准|谣言"


def promotional(title):
    campaign=bool(re.search(r"trading tournament|token vouchers|yield arena|share.{0,35}rewards|limited.time offers|交易大赛|瓜分.{0,12}奖励|限时福利",title,re.I))
    material=bool(re.search(r"\b(?:hack|hacked|breach|delist|withdrawal|suspend|will list)\b|被盗|下架|暂停|停止提现",title,re.I))
    return campaign and not material


def fingerprint(value) -> str:
    data=value if isinstance(value,str) else json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def plain(value, limit=12000):
    if not isinstance(value,str):
        return ""
    tree=Tree()
    tree.feed(value[:50000])
    text=unicodedata.normalize("NFKC",tree.root.text())
    text="".join(c for c in text if unicodedata.category(c) not in {"Cf","Cc"} or c in "\n\t")
    text=re.sub(r"(?i)\b(api[_ -]?key|authorization|bearer|password)\s*[:=]\s*[^\s,;]+",r"\1: [redacted]",text)
    return re.sub(r"\s+"," ",text).strip()[:limit]


def canonical_url(value):
    if not isinstance(value,str) or len(value)>3000:
        return ""
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in {"https","http"} or not parsed.hostname or parsed.username or parsed.password:
            return ""
        query=[(k,v) for k,v in parse_qsl(parsed.query) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid","gclid","ref","source"}]
        if any(k.lower() in {"token","api_key","apikey","key","secret","signature","access_token"} for k,_ in query):
            return ""
        return urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path or "/",urlencode(sorted(query)),""))
    except ValueError:
        return ""


def terms(text):
    text=text.casefold()
    tokens=set(re.findall(r"[a-z0-9]{2,}",text))-STOPWORDS
    for phrase in re.findall(r"[\u4e00-\u9fff]+",text):
        tokens.update(phrase[i:i+2] for i in range(len(phrase)-1))
    return tokens


def similarity(a,b):
    return len(a&b)/len(a|b) if a and b else 0


def claim_status(title, kind):
    """Headline wording only. A reported occurrence is not a verified occurrence."""
    if kind=="prediction_market":
        return "market_quote"
    patterns=[
        ("denied",r"\b(?:denied|denies|rejected|false|untrue|debunked|not approved|no approval)\b|未获|否认|驳回|不实|未批准"),
        ("uncertain",r"\b(?:rumou?r|unconfirmed|may|might|could|reportedly)\b|传闻|据传|或将|可能|谣言|[?？]"),
        ("planned",r"\b(?:will|plans?|planned|expected|proposed|scheduled|seeks?)\b|计划|拟|预计|将于"),
        ("application",r"\b(?:application received|files?|filed|applies|submitted|filing)\b|提交申请|受理|申请中"),
        ("reported",r"\b(?:approved|confirmed|announced|launched|suspended|hacked|stolen|halted|resumed)\b|已批准|获批|确认|宣布|被盗|暂停|已恢复"),
    ]
    return next((state for state,pattern in patterns if re.search(pattern,title,re.I)),"unknown")


def reading_context(context=None):
    context=context or {}
    return {key:sorted({s.upper() for s in context.get(key,[]) if isinstance(s,str) and s.upper() in ASSETS})
            for key in ("holdings","watchlist")}


def numeric_signature(title):
    # Preserve lexical quantities/units; do not invent conversions or merge differing amounts.
    return re.findall(r"\d+(?:[.,]\d+)*(?:\s*(?:%|bps?\b|basis points?\b|million\b|billion\b|[kmb]\b|万|亿|基点))?",title.casefold())


def normalize(raw: dict, source: Source, observed_at: float) -> dict:
    title=plain(raw.get("title") or raw.get("text"),250)
    text=plain(raw.get("text") or title)
    if not title or not text:
        raise ValueError("Empty source item")
    published=timestamp(raw.get("published_at"))
    updated=timestamp(raw.get("updated_at"))
    kind="prediction_market" if raw.get("kind")=="prediction_market" else "report"
    url=canonical_url(raw.get("url"))
    flags=[]
    combined=title+" "+text
    if any(re.search(pattern,combined,re.I) for pattern in INJECTION_PATTERNS):
        flags.append("instruction_like_content")
    if published is not None and published>observed_at+300:
        flags.append("future_publication_time")
    assets=sorted(k for k,p in ASSETS.items() if re.search(p,combined,re.I))
    topics=sorted(k for k,p in TOPICS.items() if re.search(p,combined,re.I))
    relevant=bool(assets or topics)
    if source.keywords:
        relevant=relevant and any(k.casefold() in combined.casefold() for k in source.keywords)
    metrics={}
    if kind=="prediction_market":
        supplied=raw.get("metrics",{})
        for key in ("liquidity","volume24hr","end_at"):
            value=supplied.get(key)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
                metrics[key]=max(0,value)
        metrics["outcomes"]=[{"outcome":plain(q.get("outcome"),100),"price":round(q["price"],4)}
                             for q in supplied.get("outcomes",[])[:20] if isinstance(q,dict) and isinstance(q.get("price"),(int,float)) and not isinstance(q["price"],bool) and math.isfinite(q["price"]) and 0<=q["price"]<=1]
    # Provider timestamps do not establish availability. Every version is bounded by local observation.
    content_hash=fingerprint({"title":title,"text":text,"kind":kind,"metrics":metrics})
    external=str(raw.get("external_id") or url or content_hash)[:500]
    evidence_id=fingerprint(source.id+"\0"+external+"\0"+content_hash)[:24]
    return {"id":evidence_id,"source_id":source.id,"source_name":source.name,"source_group":source.group or source.id,"source_tier":source.tier,
            "external_id":external,"url":url,"title":title,"text":text,"content_hash":content_hash,
            "published_at":published,"updated_at":updated,"observed_at":observed_at,
            "time_quality":"publisher_time" if published is not None else "observed_only",
            "kind":kind,"metrics":metrics,"assets":assets,"topics":topics,"relevant":relevant,
            "flags":flags,"quarantined":bool(flags),"reliability":source.reliability,"ttl_seconds":source.ttl_seconds,
            "negative_claim":bool(re.search(NEGATION,title,re.I)),"processor":PROCESSOR_VERSION}


def build_digest(items: list[dict], as_of: float, limit=12, context=None, include_candidates=False, selection_policy=None) -> dict:
    context=reading_context(context)
    selection_policy=selection_policy or POLICY
    excluded={key:0 for key in ("future","expired","quarantined","irrelevant","promotional")}
    clusters=[]
    for stored in sorted(items,key=lambda x:(x["observed_at"],x["id"])):
        # Reprocess old payloads without rewriting archived evidence or its original processor version.
        item={**stored,"negative_claim":bool(re.search(NEGATION,stored["title"],re.I)),
              "claim_status":claim_status(stored["title"],stored["kind"])}
        anchor=item.get("last_observed_at",item["observed_at"]) if item["kind"]=="prediction_market" else item["published_at"] if item["published_at"] is not None else item["observed_at"]
        reason=("future" if item["observed_at"]>as_of or anchor>as_of else
                "quarantined" if item["quarantined"] else
                "irrelevant" if not market_relevant(item) else
                "promotional" if promotional(item["title"]) else
                "expired" if as_of-anchor>item["ttl_seconds"] or (item["kind"]=="prediction_market" and item["metrics"].get("end_at",as_of+1)<=as_of) else None)
        if reason:
            excluded[reason]+=1
            continue
        item["freshness_anchor"]=anchor
        tokens=terms(item["title"])
        match=None
        for cluster in clusters:
            head=cluster[0]
            if item["kind"]!=head["kind"] or item["negative_claim"]!=head["negative_claim"] or item["claim_status"]!=head["claim_status"] or abs(anchor-head["freshness_anchor"])>36*3600:
                continue
            # Separate prediction contracts even if their questions are almost identical.
            if item["kind"]=="prediction_market" and (item["source_id"],item["external_id"])!=(head["source_id"],head["external_id"]):
                continue
            if numeric_signature(item["title"])!=numeric_signature(head["title"]):
                continue
            if item["assets"] and head["assets"] and not set(item["assets"])&set(head["assets"]):
                continue
            if item["content_hash"]==head["content_hash"] or (similarity(tokens,terms(head["title"]))>=.58 and (set(item["assets"])&set(head["assets"]) or set(item["topics"])&set(head["topics"]))):
                match=cluster
                break
        if match is None:
            clusters.append([item])
        else:
            match.append(item)
    events=[]
    for cluster in clusters:
        cluster=sorted(cluster,key=lambda i:(TIERS.get(i.get("source_tier"),0),i["reliability"],i["observed_at"],i["id"]),reverse=True)
        head=cluster[0]
        anchor=head["freshness_anchor"]
        unique=[]
        for item in cluster:
            if all(item["source_group"]!=other["source_group"] and similarity(terms(item["text"]),terms(other["text"]))<.85 for other in unique):
                unique.append(item)
        freshness=max(0,1-(as_of-anchor)/head["ttl_seconds"])
        holdings=bool(set(head["assets"])&set(context["holdings"]))
        watched=bool(set(head["assets"])&set(context["watchlist"]))
        macro=bool(re.search(r"\b(?:fomc|interest rates?|inflation|cpi|payroll)\b|降息|加息|通胀|非农",head["title"],re.I))
        relevance=1 if holdings else .85 if watched else .75 if macro else .35 if context["holdings"] or context["watchlist"] else .65 if head["assets"] else .25
        urgent=head["claim_status"]=="reported" and bool(re.search(r"\b(?:hacked|stolen|breach|depeg|withdrawals? suspended|withdrawals? halted)\b|被盗|脱锚|暂停提现|停止提现",head["title"],re.I))
        urgency=1 if urgent else .25
        components={"source_weight":round(.25*head["reliability"],4),"freshness":round(.25*freshness,4),
                    "relevance":round(.4*relevance,4),"urgency":round(.1*urgency,4)}
        priority=round(sum(components.values()),3)
        assessment=assess(head,relevance,freshness)
        editorial=select(assessment,head.get("source_tier","unrated"),head["claim_status"],head["kind"],selection_policy)
        event_id=fingerprint({"kind":head["kind"],"members":sorted((i["source_id"],i["external_id"]) for i in cluster)})[:20]
        metrics=dict(head["metrics"])
        gaps=[]
        if head["published_at"] is None:
            gaps.append("publication_time_missing")
        if not head["url"]:
            gaps.append("source_link_missing")
        if head["kind"]=="prediction_market":
            gaps.extend(["orderbook_missing","resolution_rules_unchecked"])
            if "liquidity" not in metrics:
                gaps.append("liquidity_missing")
        else:
            gaps.append("primary_evidence_unchecked")
            if len(unique)<2:
                gaps.append("single_source_family")
            if head["claim_status"]=="unknown":
                gaps.append("event_status_unknown")
        events.append({"id":event_id,"title":head["title"],"summary":head["text"][:600],"kind":head["kind"],
                       "assets":head["assets"],"topics":head["topics"],"published_at":head["published_at"],
                       "observed_at":head["observed_at"],"last_observed_at":max(i.get("last_observed_at",i["observed_at"]) for i in cluster),"time_quality":head["time_quality"],
                       "priority":priority,"independent_reports":len(unique),"verification":"market_quote" if head["kind"]=="prediction_market" else "unverified",
                       "score_breakdown":components,"context_match":"holding" if holdings else "watchlist" if watched else "macro" if macro else "general",
                       "assessment":assessment,"editorial":editorial,"category":assessment["category"],"source_tier":head.get("source_tier","unrated"),
                       "source_ids":sorted({i["source_id"] for i in cluster}),
                       "timeline_at":head["published_at"] if head["published_at"] is not None else head.get("first_observed_at",head["observed_at"]),
                       "claim":{"status":head["claim_status"],"basis":"headline_rules","text":head["title"],"event_at":None,"impact_horizon":"unknown"},
                       "evidence_gaps":gaps,"age_seconds":max(0,as_of-anchor),
                       "summary_evidence_id":head["id"],"evidence_ids":[i["id"] for i in cluster],
                       "possible_conflict":False,"metrics":metrics,
                       "evidence":[{"id":i["id"],"source":i["source_name"],"source_id":i["source_id"],"group":i["source_group"],
                                    "url":i["url"],"quote":i["text"][:360],"published_at":i["published_at"],"observed_at":i["observed_at"],"tier":i.get("source_tier","unrated")} for i in cluster[:5]],
                       "evidence_count":len(cluster),"negative_claim":head["negative_claim"]})
        if include_candidates:
            events[-1]["related_evidence"]=[{"id":i["id"],"source":i["source_name"],"source_id":i["source_id"],"tier":i.get("source_tier","unrated"),
                                             "url":i["url"],"quote":i["text"][:360],"title":i["title"],"published_at":i["published_at"],
                                             "observed_at":i["observed_at"]} for i in cluster]
    for a in events:
        for b in events:
            if a["kind"]!="report" or b["kind"]!="report" or a["negative_claim"]==b["negative_claim"]:
                continue
            ta=terms(re.sub(NEGATION,"",a["title"],flags=re.I))
            tb=terms(re.sub(NEGATION,"",b["title"],flags=re.I))
            if similarity(ta,tb)>=.7:
                a["possible_conflict"]=True
    for event in events:
        if event["possible_conflict"]:
            event["evidence_gaps"].append("conflicting_claims")
        event["verification_request"]={"status":"not_performed","evidence_ids":event["evidence_ids"],
                                       "as_of":as_of,"checks":list(event["evidence_gaps"]),"execution_authority":False}
    events.sort(key=lambda e:(e["priority"],e["observed_at"]),reverse=True)
    selected=[]
    per_source={}
    quotes=0
    # Bound each publisher's contribution so one high-volume feed cannot fill the digest.
    for event in events:
        publisher=event["evidence"][0]["group"]
        if event["kind"]=="report" and not event["editorial"]["selected"]:
            continue
        if per_source.get(publisher,0)>=6 or (event["kind"]=="prediction_market" and quotes>=3):
            continue
        selected.append(event)
        quotes+=event["kind"]=="prediction_market"
        per_source[publisher]=per_source.get(publisher,0)+1
        if len(selected)>=limit:
            break
    represented=set(a for e in selected for a in e["assets"])
    quality={"input_items":len(items),"excluded":excluded,"unverified_reports":sum(e["kind"]=="report" for e in selected),
             "possible_conflicts":sum(e["possible_conflict"] for e in selected),"quote_events":quotes,
             "requested_assets_without_selected_evidence":sorted((set(context["holdings"])|set(context["watchlist"]))-represented),
             "scope":"selected_digest_not_global_coverage"}
    retained=sum(len(c) for c in clusters)
    funnel={"observed_items":len(items),"excluded":excluded,"eligible_items":retained,"clustered_events":len(events),
            "merged_reports":retained-len(events),"selected_reports":sum(e["editorial"]["selected"] for e in events),
            "below_threshold":sum(e["editorial"]["reason"]=="below_threshold" for e in events),
            "market_quotes":sum(e["kind"]=="prediction_market" for e in events),"digest_events":len(selected)}
    result={"id":fingerprint({"as_of":as_of,"events":selected,"context":context,"quality":quality,"processor":PROCESSOR_VERSION,"selection_policy":selection_policy})[:24],
            "as_of":as_of,"processor":PROCESSOR_VERSION,"events":selected,"eligible_events":len(events),"context":context,"quality":quality,
            "funnel":funnel,"curation_policy":{"version":selection_policy["version"],"id":policy_id(selection_policy),"method":"rules-v1"},
            "policy":{"trust":"untrusted_external_data","score":"reading_priority_not_truth_probability",
                      "cross_source":"heuristic_grouping_not_fact_checking","claim_status":"headline_wording_not_verified_event_state","execution_authority":False}}
    if include_candidates:
        result["candidates"]=events
    return result
