"""Transparent name-only research screens for captured Alpaca US equities.

Alpaca's ``us_equity`` class and ``tradable`` flag do NOT certify common shares.
These labels are heuristics based on stored symbols/names, not asset types,
fundamental analysis, or a basis for investment recommendations.
"""

import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

SecurityLabel = Literal[
    "warrant_or_right", "unit", "preferred", "fund_or_etp", "depositary",
    "common_name_evidence", "unclassified", "missing_name",
]
ResearchProfile = Literal["all", "exclude-obvious-complex", "common-name-evidence"]
PROFILES: tuple[ResearchProfile, ...] = (
    "all", "exclude-obvious-complex", "common-name-evidence"
)
LABELS: tuple[SecurityLabel, ...] = (
    "common_name_evidence", "unclassified", "missing_name", "warrant_or_right",
    "unit", "preferred", "fund_or_etp", "depositary",
)
SCREENER_VERSION = "name-screen-v1"

# Avoid guessing from a terminal W or U alone. Named instruments and explicit
# delimited ticker suffixes are useful *signals*, never definitive evidence.
_WARRANT = re.compile(
    r"\b(?:warrants?|wts|rights?|rts|contingent value rights?|cvr)\b",
    re.IGNORECASE,
)
_UNIT = re.compile(r"\bunits?\b", re.IGNORECASE)
_PREFERRED = re.compile(r"\b(?:preferred|preference shares?|prefs?)\b", re.IGNORECASE)
_FUND = re.compile(
    r"\b(?:ETF|ETN|exchange[- ]traded|index fund|mutual fund|closed[- ]end fund|"
    r"iShares|ProShares|Direxion)\b",
    re.IGNORECASE,
)
_DEPOSITARY = re.compile(
    r"\b(?:american depositary|depositary (?:receipts?|shares?)|sponsored adr|ADR)\b",
    re.IGNORECASE,
)
_COMMON = re.compile(r"\b(?:common stocks?|common shares?|ordinary shares?)\b", re.IGNORECASE)
_WARRANT_SUFFIX = re.compile(r"(?:[.-](?:WS|WTS|WT|W|RT|R))\Z", re.IGNORECASE)
_UNIT_SUFFIX = re.compile(r"(?:[.-](?:U|UN))\Z", re.IGNORECASE)


@dataclass(frozen=True)
class ClassifiedAsset:
    symbol: str
    name: str
    label: SecurityLabel


def classify_security(symbol: str, name: str) -> SecurityLabel:
    """Conservative descriptive label; do not call this a verified security type."""
    if not name.strip():
        return "missing_name"
    if _WARRANT.search(name) or _WARRANT_SUFFIX.search(symbol):
        return "warrant_or_right"
    if _UNIT.search(name) or _UNIT_SUFFIX.search(symbol):
        return "unit"
    if _PREFERRED.search(name):
        return "preferred"
    if _FUND.search(name):
        return "fund_or_etp"
    if _DEPOSITARY.search(name):
        return "depositary"
    if _COMMON.search(name):
        return "common_name_evidence"
    return "unclassified"


def profile_includes(label: SecurityLabel, profile: ResearchProfile) -> bool:
    """Only positive common wording enters the strict profile."""
    if profile == "all":
        return True
    if profile == "common-name-evidence":
        return label == "common_name_evidence"
    if profile == "exclude-obvious-complex":
        return label in ("common_name_evidence", "unclassified")
    raise ValueError("Unknown research profile.")


def choose_profile_symbols(
    assets: Iterable[ClassifiedAsset], *, profile: ResearchProfile
) -> list[str]:
    """For filtered profiles, exclude conflicting/reused same-ticker identities.

    'all' intentionally maintains the existing sorted/deduplicated symbol list
    for users already resuming its historical offsets.
    """
    by_symbol: dict[str, list[SecurityLabel]] = {}
    for asset in assets:
        by_symbol.setdefault(asset.symbol, []).append(asset.label)
    if profile == "all":
        return sorted(by_symbol)
    return sorted(
        symbol for symbol, labels in by_symbol.items()
        if len(labels) == 1 and profile_includes(labels[0], profile)
    )


def profile_fingerprint(
    *, captured_on: date, profile: ResearchProfile, symbols: Sequence[str]
) -> str:
    """Stable per-date/profile/order marker to prevent wrong-offset resumes."""
    input_text = "\n".join(
        (SCREENER_VERSION, captured_on.isoformat(), profile, *symbols)
    )
    return hashlib.sha256(input_text.encode("utf-8")).hexdigest()[:16]


def label_counts(assets: Iterable[ClassifiedAsset]) -> Counter[str]:
    return Counter(asset.label for asset in assets)
