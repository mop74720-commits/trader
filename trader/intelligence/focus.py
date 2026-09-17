"""Reading scopes and attribution rules, independent of the paper trading universe."""
import re
from urllib.parse import urlsplit

US_ASSETS = {
    "SPY": r"(?-i:\bSPY\b)|\bs&p\s*500\b|标普",
    "QQQ": r"\b(?:qqq|nasdaq(?:\s*100)?)\b|纳斯达克|纳指",
    "DIA": r"\b(?:dow jones|dow industrials|dow 30)\b|道琼斯|道指|\$DIA\b",
    "IWM": r"\b(?:iwm|russell\s*2000)\b|罗素",
    "AAPL": r"\b(?:aapl|apple)\b|苹果公司",
    "MSFT": r"\b(?:msft|microsoft)\b|微软",
    "NVDA": r"\b(?:nvda|nvidia)\b|英伟达",
    "AMZN": r"\b(?:amzn|amazon)\b|亚马逊",
    "GOOGL": r"\b(?:googl?|alphabet|google)\b|谷歌",
    "META": r"\b(?:meta platforms|facebook)\b|(?-i:\bMETA\b)",
    "TSLA": r"\b(?:tsla|tesla)\b|特斯拉",
    "DJT": r"\b(?:djt|trump media)\b|特朗普媒体",
    "AMD": r"\bamd\b|advanced micro devices|超威半导体",
    "INTC": r"\b(?:intc|intel)\b|英特尔",
}
US_WATCHLIST = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "DJT"]
PEOPLE = {"trump": r"\b(?:trump|realdonaldtrump|potus)\b|特朗普|川普",
          "musk": r"\b(?:musk|elonmusk)\b|马斯克",
          "powell": r"\b(?:powell)\b|鲍威尔"}
US_MACRO = (r"\b(?:tariffs?|trade war|trade deal|export controls?|sanctions?|treasur(?:y|ies)|"
            r"fomc|federal reserve|fed|interest rates?|rate cuts?|rate hikes?|inflation|cpi|payrolls?|"
            r"wall street|u\.?s\.? stocks?|u\.?s\.? econom\w*|stock market|equities|earnings)\b"
            r"|美股|关税|贸易战|出口管制|制裁|美联储|美债|降息|加息|非农|财报")


def reading_tags(text, assets, source_person="", source_kind="", author="", account="", url=""):
    people = {key for key, pattern in PEOPLE.items() if re.search(pattern, text, re.I)}
    attribution = "report"
    platform = ""
    parsed = urlsplit(url)
    if source_kind == "x":
        platform = "X"
        attribution = "social_unverified"
        if account and author.casefold() == account.casefold() and parsed.hostname == "x.com":
            attribution = "account_post"
            if source_person:
                people.add(source_person)
    elif source_kind == "jsonl" and parsed.hostname == "truthsocial.com":
        platform = "Truth Social"
        attribution = "imported_post"
        if account and parsed.path.casefold().startswith("/@" + account.casefold() + "/posts/"):
            if source_person:
                people.add(source_person)
    return {"people": sorted(people), "market_scope": "us" if set(assets) & set(US_ASSETS) or re.search(US_MACRO, text, re.I) else "other",
            "attribution": attribution, "platform": platform, "author": author}
