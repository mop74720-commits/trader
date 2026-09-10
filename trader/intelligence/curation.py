"""Transparent rule scoring followed by deterministic editorial selection.

Inspired by AIHOT's separation of assessment and policy, not its unpublished rubric.
No model calls, inferred translations, paid services, or truth probabilities.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

DEFAULT_POLICY=Path(__file__).resolve().parents[2]/"config"/"intelligence.curation.json"
TIERS={"T1":3,"T1.5":2,"T2":1,"unrated":0}
CATEGORIES=("security","monetary_policy","regulation","exchange","derivatives","market")
DIMENSIONS=("relevance","materiality","specificity","freshness","source_quality")
MACRO=r"\b(?:fomc|interest rates?|inflation|cpi|payroll|monetary policy|rate cut|rate hike)\b|降息|加息|通胀|非农|货币政策"
MATERIAL=r"\b(?:approved|approval|launch(?:ed)?|hack(?:ed)?|exploit|stolen|suspend(?:ed)?|halt(?:ed)?|list(?:ing)?|delist(?:ed)?|withdrawals?|rates?|etf|inflows?|outflows?|funding|liquidation|depeg|upgrade|outage)\b|批准|被盗|暂停|上线|下架|提现|利率|资金费率|升级|故障"


def load_policy(path=DEFAULT_POLICY):
    policy=json.loads(Path(path).read_text(encoding="utf-8-sig"))
    def bounded(values,keys,low,high):
        return isinstance(values,dict) and set(values)==set(keys) and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and low<=v<=high for v in values.values())
    if not isinstance(policy,dict) or not isinstance(policy.get("version"),str) or not policy["version"]:
        raise ValueError("Invalid curation version")
    if not bounded(policy.get("weights"),DIMENSIONS,0,1) or not math.isclose(sum(policy["weights"].values()),1):
        raise ValueError("Curation weights must sum to one")
    if not bounded(policy.get("thresholds"),CATEGORIES,0,100) or not bounded(policy.get("tier_discount"),TIERS,0,100):
        raise ValueError("Invalid curation thresholds")
    penalty=policy.get("uncertainty_penalty")
    if not isinstance(penalty,(int,float)) or isinstance(penalty,bool) or not math.isfinite(penalty) or not 0<=penalty<=100:
        raise ValueError("Invalid uncertainty penalty")
    return policy


POLICY=load_policy()


def policy_id(policy):
    return hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()[:16]


def market_relevant(item):
    """An official institution's name alone does not make an administrative post useful."""
    if not item["relevant"]:
        return False
    if item["assets"] or set(item["topics"])&{"security","exchange","derivatives","market"}:
        return True
    return bool(re.search(MACRO+ r"|\b(?:crypto|digital assets?|stablecoins?|bitcoin|ethereum)\b|加密|数字资产|稳定币",item["title"]+" "+item["text"],re.I))


def assess(item, relevance, freshness):
    """Five bounded, inspectable proxies. An assessment is not a selection decision."""
    title=item["title"]
    material=bool(re.search(MATERIAL,title,re.I))
    category=next((c for c in CATEGORIES if c in item["topics"]),"market")
    # Distinguish genuine monetary policy titles from general Fed institutional news.
    if re.search(MACRO,title,re.I):
        category="monetary_policy"
    dimensions={"relevance":round(relevance*100,2),"materiality":85 if material else 40,
                "specificity":min(100,35+25*bool(item["url"])+20*bool(re.search(r"\d",title))+20*(item["published_at"] is not None)),
                "freshness":round(freshness*100,2),"source_quality":round(item["reliability"]*100,2)}
    reasons=[]
    if relevance>=.75:reasons.append("asset_or_macro_match")
    if material:reasons.append("material_event_terms")
    if item.get("source_tier") in {"T1","T1.5"}:reasons.append("first_party_source")
    if not reasons:reasons.append("market_background")
    return {"method":"rules-v1","dimensions":dimensions,"category":category,"reasons":reasons}


def select(assessment, tier, status, kind, policy=None):
    policy=policy or POLICY
    contributions={key:round(assessment["dimensions"][key]*policy["weights"][key],3) for key in DIMENSIONS}
    penalty=policy["uncertainty_penalty"] if status=="uncertain" else 0
    score=round(max(0,min(100,sum(contributions.values())-penalty)),2)
    threshold=max(0,policy["thresholds"][assessment["category"]]-policy["tier_discount"].get(tier,0))
    selected=kind=="report" and score>=threshold
    return {"selected":selected,"score":score,"threshold":threshold,"contributions":contributions,
            "penalty":penalty,"reason":"market_quote" if kind=="prediction_market" else "passed" if selected else "below_threshold",
            "policy_version":policy["version"],"policy_id":policy_id(policy)}
