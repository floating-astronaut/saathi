"""Commercial handoff helpers.

Saathi can assemble intent and hand the user to a provider surface. It cannot
buy, pay, reserve, log in, or carry account state. Keep this module pure: no
network, no cookies, no hidden browser automation.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlencode

_MAX_QUERY_CHARS = 180
_SECRETISH = re.compile(
    r"\b(otp|pin|password|passcode|cvv|card|upi|netbanking|bank|account)\b",
    re.IGNORECASE,
)
_LONG_DIGITS = re.compile(r"\d{4,}")
_CARDISH = re.compile(r"(?:\d[ -]?){12,19}")


@dataclass(frozen=True)
class ProviderLink:
    """A visible handoff URL. Opening it is the only action."""

    name: str
    kind: str
    url: str


@dataclass(frozen=True)
class CartHandoff:
    items: list[str]
    list: str
    query: str
    providers: list[ProviderLink]
    omitted_from_links: list[str]


def numbered_list(items: list[str]) -> str:
    return "\n".join(f"{n}. {item}" for n, item in enumerate(items, 1))


def _safe_query_part(text: str) -> str | None:
    clean = " ".join(text.strip().split())
    if not clean:
        return None
    if _SECRETISH.search(clean) or _LONG_DIGITS.search(clean) or _CARDISH.search(clean):
        return None
    return clean


def _query(items: list[str], note: str | None = None) -> tuple[str, list[str]]:
    parts, omitted = [], []
    for item in items:
        safe = _safe_query_part(item)
        if safe:
            parts.append(safe)
        else:
            omitted.append(item)
    if note:
        safe = _safe_query_part(note)
        if safe:
            parts.append(safe)
        else:
            omitted.append(note)
    query = " ".join(parts)[:_MAX_QUERY_CHARS].strip()
    return query, omitted


def _url(base: str, query_param: str, query: str) -> str:
    return f"{base}?{urlencode({query_param: query})}"


def _google_search(query: str, suffix: str = "") -> str:
    q = f"{query} {suffix}".strip()
    return "https://www.google.com/search?" + urlencode({"q": q})


def provider_links(query: str, kind: str = "grocery") -> list[ProviderLink]:
    """Return India-first provider handoffs for visible user intent.

    These are search/page links, not carts. A provider may open its app, but the
    user still sees and completes every step there.
    """
    q = query.strip()
    if not q:
        return []
    kind = (kind or "grocery").strip().lower()
    maps = ProviderLink(
        "Google Maps", "maps",
        "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": q}),
    )
    if kind in {"food", "restaurant", "restaurants", "meal"}:
        return [
            ProviderLink("Swiggy", "food", _url("https://www.swiggy.com/search", "query", q)),
            ProviderLink("Zomato", "food", _google_search(q, "site:zomato.com India")),
            maps,
        ]
    if kind in {"movie", "movies", "ticket", "tickets", "event", "events"}:
        return [
            ProviderLink("BookMyShow", "events", _google_search(q, "site:in.bookmyshow.com")),
            ProviderLink("District/Insider", "events", _google_search(q, "India tickets")),
            maps,
        ]
    if kind in {"travel", "flight", "train", "bus"}:
        return [
            ProviderLink("MakeMyTrip", "travel", _google_search(q, "site:makemytrip.com")),
            ProviderLink("Ixigo", "travel", _google_search(q, "site:ixigo.com")),
            ProviderLink("IRCTC", "travel", _google_search(q, "site:irctc.co.in")),
        ]
    return [
        ProviderLink("Blinkit", "grocery", _url("https://blinkit.com/s/", "q", q)),
        ProviderLink("Zepto", "grocery", _url("https://www.zeptonow.com/search", "query", q)),
        ProviderLink("BigBasket", "grocery", _url("https://www.bigbasket.com/ps/", "q", q)),
        ProviderLink("Swiggy Instamart", "grocery", _url("https://www.swiggy.com/instamart/search", "query", q)),
    ]


def build_cart_handoff(items: list[str], note: str | None = None,
                       kind: str = "grocery") -> CartHandoff:
    cleaned = [" ".join(str(i).strip().split()) for i in items if str(i).strip()]
    query, omitted = _query(cleaned, note)
    return CartHandoff(
        items=cleaned,
        list=numbered_list(cleaned),
        query=query,
        providers=provider_links(query, kind),
        omitted_from_links=omitted,
    )
