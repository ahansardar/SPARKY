import webbrowser
from urllib.parse import quote_plus

import requests


WMO_WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _detect_city_from_ip() -> str | None:
    providers = [
        "https://ipapi.co/json/",
        "https://ipinfo.io/json",
    ]
    for url in providers:
        try:
            r = requests.get(url, timeout=4)
            if r.ok:
                data = r.json()
                city = (data.get("city") or "").strip()
                if city:
                    return city
        except Exception:
            continue
    return None


def _resolve_city_coordinates(city: str) -> tuple[float, float, str] | None:
    try:
        r = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=8,
        )
        if not r.ok:
            return None
        data = r.json()
        results = data.get("results") or []
        if not results:
            return None
        item = results[0]
        lat = item.get("latitude")
        lon = item.get("longitude")
        name = (item.get("name") or city).strip()
        country = (item.get("country") or "").strip()
        label = f"{name}, {country}".strip(", ")
        if lat is None or lon is None:
            return None
        return float(lat), float(lon), label
    except Exception:
        return None


def _fetch_current_weather(city: str) -> str | None:
    try:
        resolved = _resolve_city_coordinates(city)
        if not resolved:
            return None
        lat, lon, label = resolved
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            },
            timeout=8,
        )
        if not r.ok:
            return None
        data = r.json()
        current = data.get("current") or {}
        code = current.get("weather_code")
        desc = WMO_WEATHER_CODES.get(int(code), "current conditions unavailable") if code is not None else ""
        temp_c = current.get("temperature_2m")
        feels_c = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind_kmph = current.get("wind_speed_10m")
        pieces = [f"Current weather in {label}"]
        if desc:
            pieces.append(desc)
        if temp_c is not None:
            pieces.append(f"{temp_c} degrees Celsius")
        if feels_c is not None:
            pieces.append(f"feels like {feels_c}")
        if humidity is not None:
            pieces.append(f"humidity {humidity}%")
        if wind_kmph is not None:
            pieces.append(f"wind {wind_kmph} km/h")
        return ", ".join(pieces) + "."
    except Exception:
        return None


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None
):
    city = (parameters.get("city") or "").strip()
    time = (parameters.get("time") or "now").strip()
    open_in_browser = bool(parameters.get("open_browser", False))

    if not city:
        city = _detect_city_from_ip() or ""

    if not city:
        msg = "I could not detect your location. Please tell me your city for weather."
        _speak_and_log(msg, player)
        return msg

    current = _fetch_current_weather(city)
    if current:
        msg = current
    else:
        msg = f"I could not fetch live weather right now. Opening weather search for {city}."

    if open_in_browser or not current:
        search_query = f"weather in {city} {time}"
        encoded_query = quote_plus(search_query)
        url = f"https://www.google.com/search?q={encoded_query}"
        try:
            webbrowser.open(url)
        except Exception:
            pass

    _speak_and_log(msg, player)

    if session_memory:
        try:
            session_memory.set_last_search(
                query=f"weather in {city} {time}",
                response=msg
            )
        except Exception:
            pass

    return msg


def _speak_and_log(message: str, player=None):
    if player:
        try:
            player.write_log(f"SPARKY: {message}")
        except Exception:
            pass
