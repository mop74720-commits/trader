"""Bounded public-feed adapters. No social posting, login sessions, or order APIs."""
from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlparse

MAX_BYTES = 3_000_000
MAX_ITEMS = 500


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    kind: str
    enabled: bool = True
    url: str = ""
    channel: str = ""
    query: str = ""
    path: str = ""
    tag_id: str = ""
    group: str = ""
    reliability: float = .5
    interval_seconds: int = 300
    ttl_seconds: int = 86400
    token_env: str = "TRADER_X_BEARER_TOKEN"
    limit: int = 50
    keywords: list[str] = field(default_factory=list)
    tier: str = "unrated"
    editorial_note: str = ""

    def __post_init__(self):
        if not re.fullmatch(r"[a-z0-9_-]{1,60}", self.id):
            raise ValueError("Source id must contain only lowercase letters, digits, _ or -")
        if self.kind not in {"rss", "telegram", "polymarket", "x", "jsonl"}:
            raise ValueError("Unknown source adapter")
        if not isinstance(self.enabled, bool) or not 0 <= self.reliability <= 1:
            raise ValueError("Invalid source policy")
        if self.tier not in {"T1","T1.5","T2","unrated"} or not isinstance(self.editorial_note,str) or len(self.editorial_note)>500:
            raise ValueError("Invalid source editorial policy")
        if not 30 <= self.interval_seconds <= 86400 or not 60 <= self.ttl_seconds <= 2592000 or not 1 <= self.limit <= 100:
            raise ValueError("Invalid source bounds")
        if self.kind == "rss":
            validate_url(self.url)
        if self.kind == "telegram" and not re.fullmatch(r"[a-zA-Z0-9_]{5,64}", self.channel):
            raise ValueError("Invalid public Telegram channel")
        if self.kind == "x" and (not self.query or len(self.query) > 512):
            raise ValueError("X adapter requires a bounded search query")
        if self.tag_id and not self.tag_id.isdigit():
            raise ValueError("Invalid Polymarket tag id")
        if not isinstance(self.keywords,list) or any(not isinstance(k,str) or len(k)>80 for k in self.keywords):
            raise ValueError("Invalid keyword filter")

    def public(self):
        # No credentials or local file paths in the dashboard.
        return {k:v for k,v in asdict(self).items() if k not in {"path", "token_env", "query"}}


def load_sources(path: Path) -> list[Source]:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if config.get("version") != 1 or not isinstance(config.get("sources"),list) or len(config["sources"]) > 20:
        raise ValueError("Invalid intelligence source configuration")
    sources = [Source(**s) for s in config["sources"]]
    if len({s.id for s in sources}) != len(sources):
        raise ValueError("Duplicate source id")
    return sources


def timestamp(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int,float)) and not isinstance(value,bool):
        return float(value) if math.isfinite(value) and 0 <= value < 32503680000 else None
    if not isinstance(value,str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(value)
        except (ValueError,TypeError,OverflowError):
            return None
    if dt.tzinfo is None:
        return None
    try:
        return timestamp(dt.timestamp())
    except (ValueError, OverflowError, OSError):
        return None


def validate_url(url: str):
    parsed=urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or any(c in url for c in "\r\n"):
        raise ValueError("Feed URLs must be HTTPS and must not contain credentials")
    return url


class FetchError(Exception):
    def __init__(self, code: str, retry_after: int = 0):
        super().__init__(code)
        self.code, self.retry_after = code, min(max(retry_after,0),86400)


def fetch(url: str, headers: dict | None = None) -> tuple[int, bytes, dict]:
    validate_url(url)
    request_headers={"User-Agent":"TraderLab-Intelligence/0.2 (public read-only research)","Accept-Encoding":"identity", **(headers or {})}
    credentialed="Authorization" in request_headers
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, response_headers, newurl):
            if credentialed:
                raise FetchError("credential_redirect_blocked")
            validate_url(newurl)
            return super().redirect_request(req,fp,code,msg,response_headers,newurl)
    try:
        with urllib.request.build_opener(Redirect).open(urllib.request.Request(url,headers=request_headers),timeout=12) as response:
            data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:
                raise FetchError("response_too_large")
            return response.status,data,dict(response.headers)
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return 304,b"",dict(exc.headers)
        retry=exc.headers.get("Retry-After", "0")
        raise FetchError(f"http_{exc.code}", int(retry) if retry.isdigit() else 0) from None
    except FetchError:
        raise
    except Exception as exc:
        # Never expose request URLs, headers, provider response bodies or tokens in errors.
        raise FetchError(type(exc).__name__) from None


def parse_feed(data: bytes) -> list[dict]:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("DTD/entity declarations are not supported")
    root=ET.fromstring(data)
    local=lambda tag: tag.rsplit("}",1)[-1]
    if local(root.tag) not in {"rss","feed","RDF"}:
        raise ValueError("Response is not an RSS or Atom feed")
    items=[]
    for entry in root.iter():
        if local(entry.tag) not in {"item","entry"}:
            continue
        fields={}
        link=""
        for child in entry:
            key=local(child.tag)
            fields[key]="".join(child.itertext())
            if key=="link" and child.attrib.get("rel","alternate")=="alternate":
                link=child.attrib.get("href",fields[key]).strip()
        title=fields.get("title","")
        text=fields.get("description") or fields.get("summary") or fields.get("encoded") or fields.get("content") or title
        items.append({"external_id":fields.get("guid") or fields.get("id") or link or title,
                      "title":title,"text":text,"url":link,
                      "published_at":timestamp(fields.get("pubDate") or fields.get("published") or fields.get("date")),
                      "updated_at":timestamp(fields.get("updated"))})
        if len(items)>=MAX_ITEMS:
            break
    return items


class Node:
    def __init__(self, tag="", attrs=None):
        self.tag,self.attrs,self.children=tag,dict(attrs or []),[]

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child,Node):
                yield from child.walk()

    def text(self):
        if self.tag in {"script","style","noscript"}:
            return ""
        return "".join(child.text() if isinstance(child,Node) else child for child in self.children)+("\n" if self.tag in {"br","p","div"} else "")


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root=Node()
        self.stack=[self.root]

    def handle_starttag(self,tag,attrs):
        node=Node(tag,attrs)
        self.stack[-1].children.append(node)
        if tag not in {"area","base","br","col","embed","hr","img","input","link","meta","param","source","track","wbr"}:
            if len(self.stack)>100:
                raise ValueError("HTML nesting limit exceeded")
            self.stack.append(node)

    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,0,-1):
            if self.stack[i].tag==tag:
                self.stack=self.stack[:i]
                break

    def handle_data(self,data):
        self.stack[-1].children.append(data)


def parse_telegram(html: str) -> list[dict]:
    tree=Tree()
    tree.feed(html)
    items=[]
    for node in tree.root.walk():
        post=node.attrs.get("data-post")
        if not post or not re.fullmatch(r"[A-Za-z0-9_]+/\d+",post):
            continue
        text=""
        published=None
        for child in node.walk():
            if "tgme_widget_message_text" in child.attrs.get("class","").split():
                text=child.text().strip()
            if child.tag=="time":
                published=timestamp(child.attrs.get("datetime"))
        if text:
            items.append({"external_id":post,"title":text.splitlines()[0][:250],"text":text,"url":"https://t.me/"+post,"published_at":published})
    if not items:
        raise ValueError("No readable public Telegram messages; channel may be unavailable")
    return items[-MAX_ITEMS:]


def parse_x(data: dict) -> list[dict]:
    if not isinstance(data,dict) or data.get("errors"):
        raise ValueError("X returned an error or partial response")
    result=[]
    for post in data.get("data",[]):
        if not isinstance(post,dict) or not re.fullmatch(r"\d+",str(post.get("id",""))):
            continue
        result.append({"external_id":str(post["id"]),"title":post.get("text","")[:250],"text":post.get("text",""),
                       "url":"https://x.com/i/web/status/"+str(post["id"]),"published_at":timestamp(post.get("created_at"))})
    return result


def parse_polymarket(data: list, now: float) -> list[dict]:
    if not isinstance(data,list):
        raise ValueError("Invalid Polymarket response")
    items=[]
    for event in data:
        for market in event.get("markets",[]):
            end=timestamp(market.get("endDate"))
            if market.get("closed") or not market.get("active") or (end is not None and end<=now):
                continue
            outcomes=market.get("outcomes",[])
            prices=market.get("outcomePrices",[])
            outcomes=json.loads(outcomes) if isinstance(outcomes,str) else outcomes
            prices=json.loads(prices) if isinstance(prices,str) else prices
            if not outcomes or len(outcomes)!=len(prices):
                continue
            prices=[float(p) for p in prices]
            if any(not math.isfinite(p) or not 0<=p<=1 for p in prices):
                continue
            liquidity=float(market["liquidity"]) if market.get("liquidity") not in (None,"") else None
            volume=float(market["volume24hr"]) if market.get("volume24hr") not in (None,"") else None
            if any(v is not None and (not math.isfinite(v) or v<0) for v in (liquidity,volume)):
                continue
            question=market.get("question",event.get("title",""))
            quotes=[{"outcome":str(o)[:100],"price":round(p,4)} for o,p in zip(outcomes,prices)]
            text="市场报价，非已发生事实："+question+"；"+" / ".join(f"{q['outcome']}: {q['price']:.1%}" for q in quotes)
            items.append({"external_id":str(market.get("id","")),"title":question,"text":text,
                          "url":"https://polymarket.com/event/"+event.get("slug",""),"published_at":None,
                          "updated_at":timestamp(market.get("updatedAt")),"kind":"prediction_market",
                          "metrics":{"outcomes":quotes,"liquidity":liquidity,"volume24hr":volume,"end_at":end}})
            if len(items)>=MAX_ITEMS:
                return items
    return items


@dataclass
class Batch:
    items: list[dict]
    cursor: dict = field(default_factory=dict)
    etag: str = ""
    last_modified: str = ""
    not_modified: bool = False
    coverage: str = "latest_window"


def collect(source: Source, state: dict, now: float, config_dir: Path, allow_x=False) -> Batch:
    if source.kind=="jsonl":
        path=(config_dir/source.path).resolve()
        # Files are explicitly configured local exports, never arbitrary paths from incoming posts.
        if not path.is_relative_to(config_dir.resolve()) or path.stat().st_size>MAX_BYTES:
            raise FetchError("invalid_import_path_or_size")
        items=[json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if len(items)>MAX_ITEMS or any(not isinstance(item,dict) for item in items):
            raise FetchError("import_limit_or_format")
        return Batch(items,coverage="configured_file")
    if source.kind=="x":
        if not allow_x:
            raise FetchError("x_api_not_enabled")
        token=os.environ.get(source.token_env,"")
        if not token:
            raise FetchError("missing_x_credentials")
        cursor=state.get("cursor",{})
        query={"query":source.query,"max_results":max(10,source.limit),"tweet.fields":"created_at", "sort_order":"recency"}
        if cursor.get("since_id"):
            query["since_id"]=cursor["since_id"]
        if cursor.get("next_token"):
            query["next_token"]=cursor["next_token"]
        _,body,_=fetch("https://api.x.com/2/tweets/search/recent?"+urlencode(query),{"Authorization":"Bearer "+token})
        data=json.loads(body)
        items=parse_x(data)
        meta=data.get("meta",{})
        ids=[str(i) for i in (cursor.get("newest_id"),meta.get("newest_id"),cursor.get("since_id")) if i and str(i).isdigit()]
        newest=max(ids,key=int) if ids else ""
        next_token=meta.get("next_token","")
        next_cursor={"since_id":cursor.get("since_id",""),"newest_id":newest,"next_token":next_token} if next_token else {"since_id":newest}
        return Batch(items,cursor=next_cursor,coverage="pagination_pending" if next_token else "recent_search_window")
    if source.kind=="polymarket":
        params={"active":"true","closed":"false","limit":source.limit,"order":"volume24hr","ascending":"false"}
        if source.tag_id:
            params["tag_id"]=source.tag_id
        _,body,_=fetch("https://gamma-api.polymarket.com/events?"+urlencode(params))
        return Batch(parse_polymarket(json.loads(body),now),coverage="top_volume_sample")
    headers={}
    if state.get("etag"):
        headers["If-None-Match"]=state["etag"]
    if state.get("last_modified"):
        headers["If-Modified-Since"]=state["last_modified"]
    url=source.url if source.kind=="rss" else "https://t.me/s/"+source.channel
    status,body,response_headers=fetch(url,headers)
    rh={k.lower():v for k,v in response_headers.items()}
    if status==304:
        return Batch([],not_modified=True,etag=state.get("etag",""),last_modified=state.get("last_modified",""))
    items=parse_feed(body) if source.kind=="rss" else parse_telegram(body.decode("utf-8"))
    return Batch(items[-MAX_ITEMS:],etag=rh.get("etag",""),last_modified=rh.get("last-modified",""))
