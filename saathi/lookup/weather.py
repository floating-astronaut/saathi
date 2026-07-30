"""Weather — the single most-asked question an assistant gets.

Open-Meteo needs no key and no attribution burden, which matters: a capability
that depends on a paid key is a capability that silently stops working when the
card expires.

Location precedence: a place **named in the question wins** over the user's stored
home city. Someone in Mumbai asking "temp in Toronto" wants Toronto, not Mumbai —
and returning Mumbai silently is the wrong-city answer this product treats as worse
than "I don't know". The stored `city` is the fallback for a bare "aaj mausam?".
If we have neither, we say so and offer to remember their city.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote

import httpx

from .. import net_policy
from .base import Answer, register

log = logging.getLogger("saathi.lookup.weather")

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

# Filler around a place name: "temp in Toronto", "Toronto ka mausam",
# "what is the weather in New York". Stripping these lets a phrase geocode when
# the raw string ("temp in Toronto") returns no hits.
_FILLER = {
    "temp", "temperature", "weather", "forecast", "mausam", "tapman", "climate",
    "ka", "ki", "ke", "in", "at", "mein", "me", "of", "the", "is", "what", "whats",
    "hows", "how", "kaisa", "kaisi", "kaise", "hai", "aaj", "abhi", "now", "today",
    "kal", "barish", "baarish", "raining", "rain", "kya", "tell", "please",
    "batao", "bata", "do", "degree", "degrees",
}


def _strip_filler(q: str) -> str:
    """Drop weather/question words, leaving (hopefully) just the place name."""
    words = [w for w in re.split(r"\s+", q.strip()) if w]
    kept = [w for w in words if re.sub(r"[^a-z]", "", w.lower()) not in _FILLER]
    return " ".join(kept).strip(" ?.,!")


def _place_candidates(query: str | None, stored_city: str | None) -> list[str]:
    """Ordered places to try: a place named in the query first, home city last."""
    out: list[str] = []
    q = (query or "").strip()
    if q:
        out.append(q)                       # a clean "Toronto" / "New York" hits directly
        cleaned = _strip_filler(q)          # "temp in Toronto" -> "Toronto"
        if cleaned and cleaned.lower() != q.lower():
            out.append(cleaned)
    if stored_city and stored_city.strip():
        out.append(stored_city.strip())     # fallback for a bare "aaj mausam?"
    seen, res = set(), []
    for c in out:
        if c.lower() not in seen:
            seen.add(c.lower())
            res.append(c)
    return res

_CODES = {
    0: "saaf aasman", 1: "halka baadal", 2: "baadal", 3: "poora baadal",
    45: "kohra", 48: "kohra", 51: "halki boondabaandi", 53: "boondabaandi",
    55: "tez boondabaandi", 61: "halki baarish", 63: "baarish", 65: "tez baarish",
    71: "halki barf", 73: "barf", 75: "tez barf", 80: "baarish ke chhinte",
    81: "baarish", 82: "bahut tez baarish", 95: "aandhi-toofan",
    96: "aandhi-toofan", 99: "aandhi-toofan",
}


class Weather:
    name = "weather"

    def available(self) -> bool:
        return True                      # keyless

    async def _geocode(self, http: httpx.AsyncClient, name: str) -> dict | None:
        g_url = f"{GEOCODE}?name={quote(name)}&count=1&language=en&format=json"
        net_policy.assert_safe_url(g_url)
        hits = (await http.get(g_url)).json().get("results") or []
        return hits[0] if hits else None

    async def lookup(self, query: str, **ctx) -> Answer | None:
        candidates = _place_candidates(query, ctx.get("city"))
        if not candidates:
            return None
        async with httpx.AsyncClient(timeout=15) as http:
            place = None
            for cand in candidates:
                place = await self._geocode(http, cand)
                if place:
                    break
            if not place:
                return None
            f_url = (f"{FORECAST}?latitude={place['latitude']}&longitude={place['longitude']}"
                     "&current=temperature_2m,weather_code,relative_humidity_2m"
                     "&daily=temperature_2m_max,temperature_2m_min"
                     "&timezone=auto&forecast_days=1")
            net_policy.assert_safe_url(f_url)
            f = (await http.get(f_url)).json()

        city = query or ctx.get("city") or ""
        cur, daily = f.get("current", {}), f.get("daily", {})
        desc = _CODES.get(cur.get("weather_code"), "")
        lo = (daily.get("temperature_2m_min") or [None])[0]
        hi = (daily.get("temperature_2m_max") or [None])[0]
        name = place.get("name", city)
        text = (f"{name} mein abhi {round(cur.get('temperature_2m', 0))}°C hai"
                + (f", {desc}" if desc else "")
                + (f". Aaj {round(lo)}° se {round(hi)}° ke beech rahega." if lo is not None else "."))
        return Answer(text=text, source="Open-Meteo",
                      extra={"city": name, "temp_c": cur.get("temperature_2m")})


register(Weather())
