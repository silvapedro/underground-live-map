#!/usr/bin/env python3
"""Generate data/london.json and data/london-text.json from the TfL Arrivals API.

The client-side code (js/trains.js) consumes london.json for live train positions
and the static station/polyline geography. pyapp/app.py runs this script as a
subprocess every 60 seconds.

Usage:
    python bin/fetch.py [--app-key KEY] [--debug]
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # python-dotenv is optional; the env var still works without it.
    _load_dotenv = None

try:
    import truststore
except ImportError:  # optional; only needed where TLS is intercepted (see build_opener)
    truststore = None

SCRIPT_DIR = Path(__file__).resolve().parent

# override=True so .env wins even if the shell already has a stale value set.
if _load_dotenv is not None:
    _load_dotenv(SCRIPT_DIR.parent / ".env", override=True)

log = logging.getLogger("fetch")

API_TEMPLATE = "https://api.tfl.gov.uk/Line/%s/Arrivals"
USER_AGENT = "Mozilla/5.0 (compatible; underground-live-map/1.0)"
HTTP_TIMEOUT = 10
CACHE_TTL = 100  # seconds; a cache file younger than this is reused as-is.

# A rate-limited line is retried, but only so many times: app.py awaits this script, so
# retrying forever would freeze the 60s refresh loop with no error and no new data.
MAX_FETCH_ATTEMPTS = 5
RATE_LIMIT_FALLBACK_DELAY = 10  # used when TfL's 429 body has no "Try again in N second"
MAX_RATE_LIMIT_DELAY = 60  # clamp, so a large value from TfL cannot stall the run

# TfL line identifiers (URL path segments) -> display names.
# London Overground was split into 6 named lines in 2024.
LINES = {
    "liberty": "Liberty",
    "lioness": "Lioness",
    "mildmay": "Mildmay",
    "suffragette": "Suffragette",
    "weaver": "Weaver",
    "windrush": "Windrush",
    "tram": "Tram",
    # "tfl-rail": "TfL Rail",
    "dlr": "DLR",
    "bakerloo": "Bakerloo",
    "central": "Central",
    "circle": "Circle",
    "district": "District",
    "elizabeth": "Elizabeth",
    "hammersmith-city": "Hammersmith & City",
    "jubilee": "Jubilee",
    "metropolitan": "Metropolitan",
    "northern": "Northern",
    "piccadilly": "Piccadilly",
    "victoria": "Victoria",
    "waterloo-city": "Waterloo & City",
}

# Single-letter line keys used in stations.json -> full line names.
LINE_ABBREVIATIONS = {
    "B": "bakerloo",
    "C": "central",
    "D": "district",
    "E": "elizabeth",
    "H": "hammersmith-city",
    "J": "jubilee",
    "M": "metropolitan",
    "N": "northern",
    "P": "piccadilly",
    "V": "victoria",
    "W": "waterloo-city",
}

# current_location values that are not on the running network, so cannot be plotted.
UNPLOTTABLE_LOCATIONS = (
    "Siding",
    "Depot",
    "Network Rail Track",
    "North Acton Junction",
    "Lord's Disused",
    "Road 21",  # stations.json has no location for this
)

Coord = tuple[float, float]
StationLocations = dict[str, dict[str, Coord]]


def build_opener() -> urllib.request.OpenerDirector:
    """Build the HTTP opener, verifying TLS against the OS trust store when possible.

    Python verifies TLS with OpenSSL, which loads every CA from the Windows cert store
    in one go and rejects the whole bundle if any single cert is malformed. That breaks
    HTTPS entirely on machines whose store contains such a cert -- and machines running
    TLS-intercepting antivirus (Avast, Zscaler, ...) also need the AV's private root,
    which certifi does not ship. truststore sidesteps both by delegating verification to
    the OS's native APIs. It is optional: without it we fall back to Python's default.
    """
    handlers = []
    if truststore is not None:
        handlers.append(urllib.request.HTTPSHandler(
            context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ))
    opener = urllib.request.build_opener(*handlers)
    opener.addheaders = [("User-Agent", USER_AGENT)]
    return opener


def canon_station_name(s: str, line: str) -> str:
    """Reword a station name from the TfL API to match the keys in stations.json."""
    s = s.strip()
    s = re.sub(r"^Heathrow$", "Heathrow Terminals 1, 2, 3", s)
    s = re.sub(r"^Olympia$", "Kensington (Olympia)", s)
    s = re.sub(r"^Warwick Ave$", "Warwick Avenue", s)
    s = re.sub(r"^Camden$", "Camden Town", s)
    s = re.sub(r"Notting Hill Ga$", "Notting Hill Gate", s)
    s = re.sub(r"High Street Kensingt$", "High Street Kensington", s)
    s = s.replace("Camden Town (20B-20A)", "Camden Town")
    s = s.replace("Camden Town at Point 20A", "Camden Town")
    s = re.sub(r"^Central$", "Finchley Central", s)  # "Between Central and East Finchley"
    s = re.sub(r"\s*Platform \d+$", "", s)

    if line == "tram":
        s = s + " Tram Stop"
    elif line in ("dlr", "london-overground", "elizabeth"):
        pass
    else:
        s = s + " Station"

    s = s.replace(" & ", " &amp; ")  # XXX
    s = s.replace("’", "'")

    s = (
        s.replace("(Bakerloo)", "Bakerloo")
        .replace("Earls", "Earl's")
        .replace(" fast ", " ")
        .replace("St ", "St. ")
        .replace("Warren St.", "Warren Street")
        .replace("Warren Station", "Warren Street Station")
        .replace("Elephant and Castle", "Elephant &amp; Castle")
        .replace("Elephant Station", "Elephant &amp; Castle Station")
        .replace("Lambeth Station", "Lambeth North Station")
        .replace("Castle and Lambeth North Station", "Lambeth North Station")
        .replace("Castle and Kennington Station", "Kennington Station")
        .replace("Kenntington", "Kennington")
        .replace("Willlesden Green", "Willesden Green")
        .replace("Chalfont Station", "Chalfont &amp; Latimer Station")
        .replace("Chalfont and Latimer Station", "Chalfont &amp; Latimer Station")
        .replace("West Brompon", "West Brompton")
        .replace("Picadilly Circus", "Piccadilly Circus")
        .replace("Queen's' Park", "Queen's Park")
        .replace("High Barent", "High Barnet")
        .replace("Highbury &amp; Isl ", "Highbury &amp; Islington ")
        .replace("Bartnet", "Barnet")
        .replace("Faringdon", "Farringdon")
        .replace("Turnham Greens", "Turnham Green")
        .replace("Ruilsip", "Ruislip")
        .replace("Dagemham", "Dagenham")
        .replace("Paddington H &amp; C", "Paddington")
        .replace("Paddington (H&C Line)-Underground Station", "Paddington Station")
        .replace("Paddington (Suburban)", "Paddington")
        .replace("Edgware Road (H &amp; C)", "Edgware Road Circle")
        .replace("Edgware Road Platform 1 and 2", "Edgware Road Circle")
        .replace("Hammersmith (Circle and H&amp;C)", "Hammersmith")
        .replace("Hammersmith (C&amp;H)", "Hammersmith")
        .replace("Shepherds Bush (Central Line)", "Shepherd's Bush")
        .replace("Shepherds Bush Market", "Shepherd's Bush Market")
        .replace("Terminals 123", "Terminals 1, 2, 3")
        .replace("Terminal 1,2,3", "Terminals 1, 2, 3")
        .replace("Woodford Junction", "Woodford")
        .replace("King's Cross Station", "King's Cross St. Pancras Station")
        .replace("Kings Cross St. P Station", "King's Cross St. Pancras Station")
        .replace("Kings Cross St. Pancras Station", "King's Cross St. Pancras Station")
        .replace("Kings Cross Station", "King's Cross St. Pancras Station")
        .replace("Central Finchley", "Finchley Central")
        .replace("District and Picc", "D &amp; P")
        .replace("Finchley Central on the Southbound road", "Finchley Central")
        .replace("South Fields", "Southfields")
        .replace("Regents Park", "Regent's Park")
        .replace("Bromley-by-Bow", "Bromley-By-Bow")
        .replace("Brent Oak", "Burnt Oak")
        .replace("St. Johns Wood", "St. John's Wood")
        .replace("St. John Wood", "St. John's Wood")
        .replace("Totteridge and Whetstone", "Totteridge &amp; Whetstone")
        .replace("Newbury Park Loop", "Newbury Park")
        .replace("ALperton", "Alperton")
        .replace("Moor park", "Moor Park")
        .replace("Harrow-on-the-Hill", "Harrow on the Hill")
        .replace("Harrow-On-The-Hill", "Harrow on the Hill")
    )

    if s == "Edgware Road Station":
        s = "Edgware Road Bakerloo Station" if line == "B" else "Edgware Road Circle Station"
    return s


def parse_time(s: str | int) -> int:
    """Convert 'MM:SS', 'HH:MM:SS', '-' or 'due' into seconds."""
    if isinstance(s, int):
        return s
    if s in ("-", "due"):
        return 0

    m = re.match(r"(\d+):(\d+):(\d+)$", s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))

    m = re.match(r"(\d+):(\d+)$", s)
    if not m:
        raise ValueError("Did not match time %s" % s)
    return int(m.group(1)) * 60 + int(m.group(2))


def load_station_locations(path: Path) -> StationLocations:
    """Load stations.json, normalising 'lng,lat' strings and expanding line abbreviations."""
    with open(path, encoding="utf-8") as fp:
        stations: dict[str, Any] = json.load(fp)

    for name, pts in stations.items():
        if isinstance(pts, str):
            lng, lat = pts.split(",")
            stations[name] = {"*": (float(lat), float(lng))}

        for abbrev, full in LINE_ABBREVIATIONS.items():
            if abbrev in stations[name]:
                stations[name][full] = stations[name][abbrev]
                if abbrev == "H":
                    stations[name]["circle"] = stations[name][abbrev]

    return stations


def lookup(stations: StationLocations, line: str, name: str) -> Coord:
    """Return (lat, lng) for a station on a line; (0, 0) if it cannot be resolved."""
    if name not in stations:
        return (0, 0)
    if line in stations[name]:
        return stations[name][line]
    if "*" in stations[name]:
        return stations[name]["*"]
    log.warning("Could not look up %s on line %s", name, line)
    return (0, 0)


def fetch_line(key: str, api: str, cache_dir: Path, ttl: int = CACHE_TTL) -> list[dict] | None:
    """Return the raw predictions for one line, from cache if fresh, else over HTTP.

    Returns None if the line should be skipped. Every failure mode here is per-line: a
    bad response, a corrupt cache entry or a rate limit must never abort the whole run,
    because that would lose the other 19 lines too.
    """
    cache_file = cache_dir / key

    try:
        if time.time() - cache_file.stat().st_mtime <= ttl:
            log.debug("Using cached data for %s", key)
            return json.loads(cache_file.read_bytes())
    # ValueError covers JSONDecodeError: a cache entry truncated by a killed process or
    # a full disk must be re-fetched, not raised. Left uncaught it would poison every
    # subsequent run too, since the bad file stays on disk.
    except (OSError, ValueError) as exc:
        if not isinstance(exc, FileNotFoundError):
            log.warning("Discarding unusable cache entry for %s: %s", key, exc)

    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            raw = urllib.request.urlopen(api % key, timeout=HTTP_TIMEOUT).read()
        # HTTPError MUST be caught before URLError: it is a subclass of it, so the
        # reverse order (as this script had previously) made the 429 retry unreachable.
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                delay = RATE_LIMIT_FALLBACK_DELAY
                try:
                    body = exc.read().decode("utf-8", "replace")
                    m = re.search(r"Try again in (\d+) second", body)
                    if m:
                        delay = min(int(m.group(1)), MAX_RATE_LIMIT_DELAY)
                except Exception:  # noqa: BLE001 - body is best-effort only
                    pass
                log.warning(
                    "Rate limited fetching %s; retrying in %ds (attempt %d/%d)",
                    key, delay, attempt, MAX_FETCH_ATTEMPTS,
                )
                time.sleep(delay)
                continue
            log.warning("HTTP %d fetching %s, skipping", exc.code, key)
            return None
        # OSError subsumes URLError, socket timeouts and ssl.SSLError, so one bad line
        # is skipped rather than aborting the whole run.
        except OSError as exc:
            log.warning("Network error fetching %s: %s", key, exc)
            return None

        # Parse before caching, so a non-JSON body (a maintenance page served with a 200,
        # a captive portal) is skipped rather than being written to the cache and
        # crashing this run and every later one.
        try:
            predictions = json.loads(raw)
        except ValueError as exc:
            log.warning("Malformed JSON fetching %s, skipping: %s", key, exc)
            return None

        cache_file.write_bytes(raw)
        log.debug("Fetched %s from the TfL API", key)
        return predictions

    # Rate limited on every attempt; give up on this line rather than blocking the
    # refresh loop forever (app.py awaits this subprocess).
    log.warning("Giving up on %s after %d rate-limited attempts", key, MAX_FETCH_ATTEMPTS)
    return None


class ParseState:
    """Accumulates parsed arrivals. Replaces the module-level globals this script had."""

    def __init__(self) -> None:
        # Best (lowest time_to_station) entry per (line, train_key).
        self.out: OrderedDict[str, OrderedDict[str, dict]] = OrderedDict()
        # Every entry per (line, train_key), used to build each train's 'next' stop list.
        self.out_next: dict[str, dict[str, list[dict]]] = {}
        # Reset per line; disambiguates trains that share a set_id.
        self.sub_id = 0
        self.sub_ids: dict[str, int] = {}

    def start_line(self) -> None:
        self.sub_id = 0
        self.sub_ids = {}

    def add_entry(
        self,
        time_to_station: str | int,
        set_id: str,
        dest_code: str,
        destination: str,
        current_location: str,
        station_name: str,
        key: str,
        platform_name: str,
    ) -> None:
        seconds = parse_time(time_to_station)
        train_key = "%s-%s" % (set_id, dest_code)

        ambiguous = (
            set_id in ("000", "477")
            or destination in ("Unknown", "Special", "Network Rail TOC")
            or dest_code == "0"
        )
        if ambiguous:
            marker = re.sub(r"\s*Platform \d+$", "", current_location)
            if current_location == "At Platform":
                marker = "At %s" % station_name
            if not self.sub_ids.get(marker):
                self.sub_ids[marker] = self.sub_id
                self.sub_id += 1
            train_key += "-%s" % self.sub_ids[marker]

        entry = {
            "station_name": canon_station_name(re.sub(r"\.$", "", station_name), key),
            "platform_name": platform_name,
            "current_location": current_location,
            "time_to_station": seconds,
            "destination": destination,
        }

        previous = self.out.get(key, {}).get(train_key, {}).get("time_to_station", 999999)
        if seconds < previous:
            self.out.setdefault(key, OrderedDict())[train_key] = entry
        self.out_next.setdefault(key, {}).setdefault(train_key, []).append(entry)

    def parse_predictions(self, live: list[dict], key: str) -> None:
        for prediction in live:
            station_name = prediction["stationName"].replace(" Underground Station", "")
            self.add_entry(
                prediction["timeToStation"],
                prediction["vehicleId"],
                prediction.get("destinationNaptanId", "0"),
                prediction["towards"],
                prediction.get("currentLocation", ""),
                station_name,
                key,
                prediction["platformName"],
            )


def deduplicate_trains(out: OrderedDict[str, OrderedDict[str, dict]]) -> None:
    """Drop trains sharing an ID across lines, keeping the lower time_to_station.

    The same physical train can be reported on two lines (e.g. shared track). Whichever
    copy is further away is the stale one.
    """
    for key, ids in list(out.items()):
        for train_id, arr in list(ids.items()):
            for key2, ids2 in list(out.items()):
                if key == key2:
                    continue
                for id2, arr2 in list(ids2.items()):
                    if train_id != id2:
                        continue
                    if arr["time_to_station"] < arr2["time_to_station"]:
                        if out[key].get(id2):
                            del out[key2][id2]
                    else:
                        if out[key].get(train_id):
                            del out[key][train_id]


def _interpolate(a: Coord, b: Coord, fraction: float) -> Coord:
    return (a[0] + fraction * (b[0] - a[0]), a[1] + fraction * (b[1] - a[1]))


def assign_locations(
    out: OrderedDict[str, OrderedDict[str, dict]], stations: StationLocations
) -> None:
    """Set arr['location'] for each train by interpolating from its currentLocation text.

    Trains whose location cannot be determined are left without a 'location' key and are
    omitted from the map output.
    """
    for line, ids in out.items():
        for arr in ids.values():
            current = arr["current_location"]
            if any(skip in current for skip in UNPLOTTABLE_LOCATIONS):
                continue

            station_name = arr["station_name"]
            seconds = arr["time_to_station"]

            # At the station itself.
            if current == "At Platform":
                arr["location"] = lookup(stations, line, station_name)

            # These lines report no location at all; place at the next station.
            if not current and line in ("dlr", "london-overground", "tram", "elizabeth"):
                arr["location"] = lookup(stations, line, station_name)

            # Departed a named station, heading to station_name.
            m = re.match(r"(?:South of|Leaving|Left) (.*?)(?:,? heading)?(?: (?:towards|to) .*)?$", current)
            if m:
                depart = lookup(stations, line, canon_station_name(m.group(1), line))
                arrive = lookup(stations, line, station_name)
                arr["location"] = _interpolate(depart, arrive, 30 / (seconds + 30))

            # Explicitly between two named stations.
            m = re.match(r"Between (.*?) and (.*)", current)
            if m:
                if line == "H" and station_name != canon_station_name(m.group(2), line):
                    continue
                depart = lookup(stations, line, canon_station_name(m.group(1), line))
                arrive = lookup(stations, line, canon_station_name(m.group(2), line))
                span = seconds + 30 if seconds > 150 else 180
                arr["location"] = _interpolate(depart, arrive, (span - seconds) / span)

            # We don't know where it came from, so snap to the station it is approaching.
            # Interpolating properly would need position history.
            m = re.match(r"Approaching (.*)", current)
            if m:
                arr["location"] = lookup(stations, line, canon_station_name(m.group(1), line))


def build_payload(state: ParseState, stations: StationLocations) -> tuple[dict, list]:
    """Return (london.json payload, london-text.json payload)."""
    out_map = {
        "station": "London Underground",
        "lastupdate": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "trains": [],
        "stations": [],
    }
    out_text: list[dict] = []

    for line, ids in state.out.items():
        for train_id, arr in ids.items():
            at_platform = arr["current_location"] == "At Platform"
            out_text.append({
                "id": train_id,
                "time": arr["time_to_station"],
                "line": LINES[line],
                "current": "At " + arr["station_name"] if at_platform else arr["current_location"],
            })

            if "location" not in arr:
                continue

            next_stops = []
            for n in sorted(state.out_next[line][train_id], key=lambda x: x["time_to_station"]):
                station = n["station_name"]
                point = lookup(stations, line, station)
                mins = n["time_to_station"] / 60
                mins_p = "%d" % mins if int(mins) == mins else "%.1f" % mins
                next_stops.append({
                    "point": [point[0], point[1]],
                    "name": station,
                    "mins": mins,
                    "dexp": "in %s minute%s" % (mins_p, "" if n["time_to_station"] == 60 else "s"),
                })

            out_map["trains"].append({
                "point": [arr["location"][0], arr["location"][1]],
                "next": next_stops,
                "left": "",
                "id": "%s-%s" % (line, train_id),
                "title": LINES[line] + " train to " + arr["destination"] + " [" + train_id + "]",
            })

    for name, points in sorted(stations.items()):
        _, coord = points.popitem()
        lat, lng = coord
        out_map["stations"].append({"point": [lat, lng], "name": name})

    return out_map, out_text


def write_outputs(out_map: dict, out_text: list, output_dir: Path, polylines_file: Path) -> None:
    """Write london.json (atomically) and london-text.json.

    london-lines.js is a raw JSON fragment ('"polylines": [...]') that is spliced into
    the serialised payload, rather than being parsed and re-serialised.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    body = json.dumps(out_map, indent=2)
    polylines = polylines_file.read_text(encoding="utf-8")
    body = body[:-2] + ",\n" + polylines + "}"

    tmp = output_dir / "london.jsonN"
    tmp.write_text(body, encoding="utf-8")
    # os.replace (not os.rename) so this is atomic and works on Windows.
    os.replace(tmp, output_dir / "london.json")

    with open(output_dir / "london-text.json", "w", encoding="utf-8") as fp:
        json.dump(out_text, fp)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-d", "--debug", action="store_true", help="verbose output")
    parser.add_argument("-s", "--stations", default="stations.json",
                        help="station location file, relative to this script")
    parser.add_argument("-o", "--output", default="../data",
                        help="output directory, relative to this script")
    parser.add_argument("-c", "--cache-dir", default="cache",
                        help="raw API response cache, relative to this script")
    parser.add_argument("-k", "--app-key", default=os.environ.get("TFL_APP_KEY", ""),
                        help="TfL API app key (or set TFL_APP_KEY)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if options.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    cache_dir = (SCRIPT_DIR / options.cache_dir).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir = (SCRIPT_DIR / options.output).resolve()

    api = API_TEMPLATE + (("?app_key=" + options.app_key) if options.app_key else "")
    if not options.app_key:
        log.warning("No TFL_APP_KEY set; the TfL API will heavily rate-limit anonymous requests")

    urllib.request.install_opener(build_opener())
    if truststore is None:
        log.debug("truststore not installed; using Python's default TLS verification")

    log.info("Loading station locations from %s", options.stations)
    stations = load_station_locations(SCRIPT_DIR / options.stations)

    state = ParseState()
    fetched = skipped = 0
    for key in LINES:
        state.start_line()
        live = fetch_line(key, api, cache_dir)
        if live is None:
            skipped += 1
            continue
        state.parse_predictions(live, key)
        fetched += 1

    if skipped:
        log.warning("Skipped %d of %d lines due to upstream errors", skipped, len(LINES))

    log.debug("Removing duplicate trains")
    deduplicate_trains(state.out)

    log.debug("Interpolating train positions")
    assign_locations(state.out, stations)

    log.debug("Building output payloads")
    out_map, out_text = build_payload(state, stations)

    write_outputs(out_map, out_text, output_dir, SCRIPT_DIR / "london-lines.js")
    log.info(
        "Wrote %d trains (%d lines fetched) to %s",
        len(out_map["trains"]), fetched, output_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
