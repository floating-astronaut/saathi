"""Weather — the single most-asked question an assistant gets.

Open-Meteo needs no key and no attribution burden, which matters: a capability
that depends on a paid key is a capability that silently stops working when the
card expires.

Location comes from the user's stored `city` fact rather than being asked every
time. If we do not know where they live, we say so and offer to remember it —
that is a better answer than a wrong city, and it teaches the product something.
"""
from __future__ import annotations

import logging

import httpx

from .. import net_policy
from .base import Answer, register

log = logging.getLogger("saathi.lookup.weather")

GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"

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

    async def lookup(self, query: str, **ctx) -> Answer | None:
        city = (ctx.get("city") or query or "").strip()
        if not city:
            return None
        async with httpx.AsyncClient(timeout=15) as http:
            g_url = f"{GEOCODE}?name={city}&count=1&language=en&format=json"
            net_policy.assert_safe_url(g_url)
            g = (await http.get(g_url)).json()
            hits = g.get("results") or []
            if not hits:
                return None
            place = hits[0]
            f_url = (f"{FORECAST}?latitude={place['latitude']}&longitude={place['longitude']}"
                     "&current=temperature_2m,weather_code,relative_humidity_2m"
                     "&daily=temperature_2m_max,temperature_2m_min"
                     "&timezone=auto&forecast_days=1")
            net_policy.assert_safe_url(f_url)
            f = (await http.get(f_url)).json()

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
