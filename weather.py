"""
weather.py - weather and rain alerts for Peeking Cat (Open-Meteo, no API key needed)
=====================================================================================
* Tray > Weather > "Set my city..." once (for example: Dhaka).
* Every 30 minutes the cat checks the forecast in the background.
* When rain is likely in the next 3 hours, the cat pops up: "Rain likely around 15:00 (80%).
  Take an umbrella!" and Windows shows a notification too (good for deaf users).
* While it rains (or rain is less than an hour away) the cat holds a little umbrella.
* Only the city's latitude/longitude is sent to open-meteo.com. Nothing else.
"""
import json
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QInputDialog, QMessageBox

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
REFRESH_MINUTES = 30
HTTP_TIMEOUT = 15
RAIN_LOOKAHEAD_HOURS = 3       # warn about rain this far ahead
RAIN_PROBABILITY = 60          # % chance that counts as "rain likely"
RAIN_MM = 0.3                  # or this much rain (mm in one hour) with at least 40% chance
UMBRELLA_AHEAD_MINUTES = 60    # the cat already holds the umbrella when rain is this close
ALERT_COOLDOWN_HOURS = 3       # at most one rain alert in this many hours
PREVIEW_SECONDS = 12
CURRENT_MAX_AGE = 75 * 60      # "raining now" from a check older than this is not trusted
FORECAST_MAX_AGE = 3 * 3600    # a forecast older than this is not used at all (offline for hours)

# WMO weather codes -> words
CODES = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "fog", 48: "fog",
         51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
         61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
         71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "rain showers",
         81: "rain showers", 82: "heavy rain showers", 85: "snow showers", 86: "snow showers",
         95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}
RAIN_CODES = set(range(51, 68)) | {80, 81, 82, 95, 96, 99}


def describe_code(code):
    try:
        return CODES.get(int(code), "weather code %s" % code)
    except (TypeError, ValueError):
        return "unknown"


def _get_json(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": "PeekingCat/1.0"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def city_now(offset=None):
    """The clock time in the city right now. Open-Meteo gives the hours in the CITY's time
    (timezone=auto), which is not always the time zone of this PC."""
    if isinstance(offset, (int, float)) and not isinstance(offset, bool):
        return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=offset)
    return datetime.now()


def parse_forecast(data, now=None):
    """Turn an Open-Meteo answer into {"temp", "feels", "code", "precip", "hours": [...]}.
    hours = upcoming hours: {"time": datetime, "prob": int, "mm": float, "code": int}."""
    cur = data.get("current") or {}
    offset = data.get("utc_offset_seconds")
    out = {"temp": cur.get("temperature_2m"), "feels": cur.get("apparent_temperature"),
           "code": cur.get("weather_code"), "precip": cur.get("precipitation") or 0.0, "hours": [],
           "offset": offset if isinstance(offset, (int, float)) and not isinstance(offset, bool) else None}
    if now is None:
        if out["offset"] is not None:
            now = city_now(out["offset"])
        else:
            try:
                now = datetime.fromisoformat(str(cur.get("time")))
            except ValueError:
                now = datetime.now()
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    probs = hourly.get("precipitation_probability") or []
    mms = hourly.get("precipitation") or []
    codes = hourly.get("weather_code") or []
    start = now.replace(minute=0, second=0, microsecond=0)
    for i, t in enumerate(times):
        try:
            when = datetime.fromisoformat(t)
        except ValueError:
            continue
        if when < start or when > now + timedelta(hours=12):
            continue
        out["hours"].append({"time": when,
                             "prob": int(probs[i]) if i < len(probs) and probs[i] is not None else 0,
                             "mm": float(mms[i]) if i < len(mms) and mms[i] is not None else 0.0,
                             "code": int(codes[i]) if i < len(codes) and codes[i] is not None else 0})
    out["now"] = now
    return out


def raining_now(fc):
    try:
        code = int(fc.get("code"))
    except (TypeError, ValueError):
        code = 0
    return code in RAIN_CODES or (fc.get("precip") or 0.0) >= 0.1


def next_rain(fc, hours=RAIN_LOOKAHEAD_HOURS, now=None):
    """The first upcoming hour where rain is likely (dict) or None.
    now = the city's time now (default: the time of the check)."""
    now = now or fc.get("now") or datetime.now()
    for h in fc.get("hours", []):
        if h["time"] + timedelta(minutes=59) < now or h["time"] > now + timedelta(hours=hours):
            continue
        if (h["prob"] >= RAIN_PROBABILITY or (h["mm"] >= RAIN_MM and h["prob"] >= 40)
                or (h["code"] in RAIN_CODES and h["prob"] >= 50)):
            return h
    return None


class WeatherService(QObject):
    """Main_file.pyw creates one. cat must have: saved (dict), save_settings(), notify(), wake(),
    features (for the speech bubble, may be None) and assistant.dnd."""
    _fetched = Signal(object, str)          # forecast dict, error
    _found = Signal(object, str)            # list of places, error

    def __init__(self, cat):
        super().__init__()
        self.cat = cat
        self.fc = None
        self.fc_at = 0.0                # when self.fc was fetched (time.time())
        self.error = ""
        self.last_fetch = 0.0
        self._fetch_for = None          # (lat, lon) of the check that is running
        self.preview_until = 0.0
        self.fetching = False
        self.status_action = None
        self._fetched.connect(self._on_fetched)
        self._found.connect(self._on_found)
        self.timer = QTimer(cat)
        self.timer.setInterval(60 * 1000)
        self.timer.timeout.connect(self._maybe_refresh)
        self.timer.start()
        QTimer.singleShot(6000, self.refresh)

    # -- settings -------------------------------------------------------------
    def opt(self, key, default):
        return self.cat.saved.get(key, default)

    def set_opt(self, key, value):
        self.cat.saved[key] = value
        self.cat.save_settings()

    def city(self):
        c = self.opt("weather_city", None)
        if isinstance(c, dict) and isinstance(c.get("lat"), (int, float)) and isinstance(c.get("lon"), (int, float)):
            return c
        return None

    # -- fetching -------------------------------------------------------------
    def _maybe_refresh(self):
        if time.time() - self.last_fetch >= REFRESH_MINUTES * 60:
            self.refresh()

    def refresh(self):
        c = self.city()
        if c is None or self.fetching:
            self.update_menu()
            return
        self.fetching = True
        self.last_fetch = time.time()
        self._fetch_for = (c["lat"], c["lon"])
        threading.Thread(target=self._fetch_worker, args=(c["lat"], c["lon"]), daemon=True).start()

    def _fetch_worker(self, lat, lon):
        try:
            data = _get_json(FORECAST_URL, {
                "latitude": "%.4f" % lat, "longitude": "%.4f" % lon,
                "current": "temperature_2m,apparent_temperature,precipitation,weather_code",
                "hourly": "precipitation_probability,precipitation,weather_code",
                "forecast_days": 2, "timezone": "auto"})
            self._fetched.emit(parse_forecast(data), "")
        except Exception as err:
            self._fetched.emit(None, "Could not get the weather (%s)." % err.__class__.__name__)

    def _on_fetched(self, fc, err):
        self.fetching = False
        c = self.city()
        if c is None or self._fetch_for != (c["lat"], c["lon"]):
            self.refresh()          # the city was changed while this check ran: ask again for the new one
            return
        if fc is None:
            self.error = err
            self.last_fetch = time.time() - (REFRESH_MINUTES - 5) * 60      # try again in 5 minutes
        else:
            self.fc, self.fc_at, self.error = fc, time.time(), ""
            self._check_alert()
        self.update_menu()

    def _fresh(self, max_age=FORECAST_MAX_AGE):
        """The forecast, or None when there is none or it is too old to trust."""
        if self.fc is None or time.time() - self.fc_at > max_age:
            return None
        return self.fc

    def _raining(self, fc):
        """Raining now? Uses the 'current' weather only while it is recent."""
        if time.time() - self.fc_at <= CURRENT_MAX_AGE:
            return raining_now(fc)
        h = next_rain(fc, hours=0, now=city_now(fc.get("offset")))     # older: use the forecast hour
        return h is not None

    # -- what the cat shows ---------------------------------------------------
    def umbrella(self):
        """True while the cat should hold its umbrella."""
        if time.time() < self.preview_until:
            return True
        fc = self._fresh()
        if fc is None or not self.opt("weather_umbrella", True):
            return False
        if self._raining(fc):
            return True
        now = city_now(fc.get("offset"))
        h = next_rain(fc, hours=2, now=now)
        return h is not None and h["time"] <= now + timedelta(minutes=UMBRELLA_AHEAD_MINUTES)

    def rain_drops(self):
        """True while rain drops should fall around the cat."""
        if time.time() < self.preview_until:
            return True
        fc = self._fresh()
        return fc is not None and bool(self.opt("weather_umbrella", True)) and self._raining(fc)

    def preview(self):
        self.preview_until = time.time() + PREVIEW_SECONDS
        self.cat.wake()
        self.say("Like this! I hold my umbrella when it rains.", 5.0)

    def say(self, text, seconds=6.0, mood=None):
        f = getattr(self.cat, "features", None)
        if f is not None:
            f.react(text, mood, seconds, "mew", "WEATHER", None)
        else:
            self.cat.wake()

    def summary(self):
        c = self.city()
        if c is None:
            return "Tell me your city first: Weather > Set my city..."
        if self.fc is None:
            return self.error or "Getting the weather for %s..." % c["name"]
        fc = self.fc
        age_min = int((time.time() - self.fc_at) // 60)
        lines = ["%s now: %s\u00b0C (feels %s\u00b0C), %s." % (
            c["name"], _num(fc["temp"]), _num(fc["feels"]), describe_code(fc["code"]))]
        if age_min >= 60:
            lines[0] = lines[0].replace(" now:", " (checked %d min ago):" % age_min)
        h = next_rain(fc, hours=6, now=city_now(fc.get("offset")))
        if self._raining(fc):
            lines.append("It is raining now. Take an umbrella!")
        elif h is not None:
            lines.append("Rain likely around %s (%d%%)." % (h["time"].strftime("%H:%M"), h["prob"]))
        else:
            lines.append("No rain expected in the next 6 hours.")
        return "\n".join(lines)

    def show_now(self):
        if self.city() is None:
            self.ask_city()
            return
        if self.fc is None or time.time() - self.last_fetch > 10 * 60:
            self.refresh()
        self.say(self.summary(), 8.0, "happy")

    def _check_alert(self):
        if not self.opt("weather_alerts", True) or self.fc is None:
            return
        now = time.time()
        last = float(self.opt("weather_alert_at", 0) or 0)
        if now - last < ALERT_COOLDOWN_HOURS * 3600:
            return
        if self._raining(self.fc):
            text = "It is raining now! Stay dry. \u2614"
        else:
            h = next_rain(self.fc, now=city_now(self.fc.get("offset")))
            if h is None:
                return
            text = "Rain likely around %s (%d%%). Take an umbrella! \u2614" % (h["time"].strftime("%H:%M"), h["prob"])
        if getattr(self.cat.assistant, "dnd", False):
            return                      # Do not disturb: keep the alert for later (do not use up the cooldown)
        self.set_opt("weather_alert_at", now)
        self.cat.notify("Peeking Cat - weather", text)
        self.say(text, 8.0, "surprised")

    # -- city -------------------------------------------------------------------
    def ask_city(self):
        c = self.city()
        name, ok = QInputDialog.getText(None, "Weather", "Your city (for example: Dhaka):",
                                        text=c["name"] if c else "")
        if not ok or not name.strip():
            return
        threading.Thread(target=self._geocode_worker, args=(name.strip(),), daemon=True).start()

    def _geocode_worker(self, name):
        try:
            data = _get_json(GEOCODE_URL, {"name": name, "count": 8, "language": "en", "format": "json"})
            self._found.emit(data.get("results") or [], "")
        except Exception as err:
            self._found.emit(None, "Could not search for the city (%s). Are you online?" % err.__class__.__name__)

    def _on_found(self, results, err):
        if results is None:
            QMessageBox.information(None, "Weather", err)
            return
        if not results:
            QMessageBox.information(None, "Weather", "I could not find that city. Check the spelling.")
            return
        results = [r for r in results if isinstance(r.get("latitude"), (int, float))
                   and isinstance(r.get("longitude"), (int, float))]
        if not results:
            QMessageBox.information(None, "Weather", "I could not find that city. Check the spelling.")
            return
        labels = []
        for r in results:
            parts = [r.get("name", "")] + [r.get(k) for k in ("admin1", "country") if r.get(k)]
            label = ", ".join(p for p in parts if p)
            if label in labels:                  # two places with the same name: tell them apart
                label += "  (%.2f, %.2f)" % (r["latitude"], r["longitude"])
            labels.append(label)
        if len(results) == 1:
            pick = 0
        else:
            label, ok = QInputDialog.getItem(None, "Weather", "Which one?", labels, 0, False)
            if not ok:
                return
            pick = labels.index(label)
        r = results[pick]
        self.set_opt("weather_city", {"name": r.get("name", "?"), "lat": float(r["latitude"]),
                                      "lon": float(r["longitude"])})
        self.set_opt("weather_alert_at", 0)
        self.fc, self.fc_at, self.error = None, 0.0, ""
        self.last_fetch = 0.0
        self.refresh()
        self.say("Okay! I will watch the weather in %s for you." % r.get("name", "your city"), 5.0, "happy")

    # -- tray menu --------------------------------------------------------------
    def add_menu(self, menu, add):
        wm = menu.addMenu("Weather")
        self.status_action = wm.addAction("")
        self.status_action.setEnabled(False)
        add(wm, "Weather now", self.show_now)
        add(wm, "Set my city...", self.ask_city)
        add(wm, "Check again", self.refresh)
        wm.addSeparator()
        for text, key in (("Rain alerts", "weather_alerts"), ("Umbrella when it rains", "weather_umbrella")):
            act = wm.addAction(text)
            act.setCheckable(True)
            act.setChecked(bool(self.opt(key, True)))
            act.toggled.connect(lambda value, k=key: self.set_opt(k, bool(value)))
        add(wm, "Show me the umbrella", self.preview)
        wm.aboutToShow.connect(self.update_menu)
        self.update_menu()
        return wm

    def update_menu(self):
        if self.status_action is None:
            return
        c = self.city()
        if c is None:
            text = "No city set yet"
        elif self.fc is None:
            text = self.error or "%s: checking..." % c["name"]
        else:
            text = "%s: %s\u00b0C, %s" % (c["name"], _num(self.fc["temp"]), describe_code(self.fc["code"]))
        self.status_action.setText(text)


def _num(v):
    try:
        return "%d" % round(float(v))
    except (TypeError, ValueError):
        return "?"
