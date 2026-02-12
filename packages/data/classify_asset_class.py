from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Pattern

ASSET_CLASSES = {
    "us_equity",
    "global_equity",
    "korea_equity",
    "korea_treasury",
    "korea_credit",
    "korea_short",
    "reits",
    "gold",
    "unknown",
}


@dataclass(frozen=True)
class ClassificationRule:
    asset_class: str
    pattern: Pattern[str]


RULE_TABLE: list[ClassificationRule] = [
    ClassificationRule("gold", re.compile(r"(골드|금|gold)", re.IGNORECASE)),
    ClassificationRule("reits", re.compile(r"(리츠|reits?|부동산|인프라)", re.IGNORECASE)),
    ClassificationRule("korea_short", re.compile(r"(단기채|통안채|머니마켓|mmf|단기자금)", re.IGNORECASE)),
    ClassificationRule("korea_treasury", re.compile(r"(국고채|국채|국채선물|3년국채|10년국채|korea treasury)", re.IGNORECASE)),
    ClassificationRule("korea_credit", re.compile(r"(회사채|credit|corp(orat)?e bond|aa-|a-|bbb|ig)", re.IGNORECASE)),
    ClassificationRule("korea_equity", re.compile(r"(코스피|kospi|코스닥|kodex 200|tiger 200|korea equity)", re.IGNORECASE)),
    ClassificationRule("us_equity", re.compile(r"(s&p\s?500|나스닥|nasdaq|russell|미국\s?주식|us equity|dow)", re.IGNORECASE)),
    ClassificationRule("global_equity", re.compile(r"(acwi|all world|세계주식|전세계|선진국|emerging|신흥국|글로벌|msci world|eafe)", re.IGNORECASE)),
]


def classify_asset_class(name_kr: str | None) -> str:
    if not name_kr:
        return "unknown"
    text = str(name_kr).strip()
    if not text:
        return "unknown"

    for rule in RULE_TABLE:
        if rule.pattern.search(text):
            return rule.asset_class
    return "unknown"
