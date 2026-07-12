from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote
import xml.etree.ElementTree as ET

import requests

_STOP_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,8}$")

STOPS: list[tuple[str, str]] = [
    ("ACT", "Acton Town"),
    ("ALE", "Aldgate East"),
    ("BKG", "Barking"),
    ("BCT", "Barons Court"),
    ("BEC", "Becontree"),
    ("BLF", "Blackfriars"),
    ("BWR", "Bow Road"),
    ("BBB", "Bromley-by-Bow"),
    ("CST", "Cannon Street"),
    ("CHP", "Chiswick Park"),
    ("DGE", "Dagenham East"),
    ("EBY", "Ealing Broadway"),
    ("ECM", "Ealing Common"),
    ("ECT", "Earls Court"),
    ("EHM", "East Ham"),
    ("EPY", "East Putney"),
    ("ERD", "Edgware Road (H & C)"),
    ("EPK", "Elm Park"),
    ("EMB", "Embankment"),
    ("FBY", "Fulham Broadway"),
    ("GRD", "Gloucester Road"),
    ("GUN", "Gunnersbury"),
    ("HMD", "Hammersmith (District and Picc)"),
    ("HST", "High Street Kensington"),
    ("HCH", "Hornchurch"),
    ("KEW", "Kew Gardens"),
    ("MAN", "Mansion House"),
    ("MLE", "Mile End"),
    ("MON", "Monument"),
    ("OLY", "Olympia"),
    ("PADc", "Paddington Circle"),
    ("PGR", "Parsons Green"),
    ("PLW", "Plaistow"),
    ("PUT", "Putney Bridge"),
    ("RCP", "Ravenscourt Park"),
    ("RMD", "Richmond"),
    ("SSQ", "Sloane Square"),
    ("SKN", "South Kensington"),
    ("SFS", "Southfields"),
    ("SJP", "St. James's Park"),
    ("STB", "Stamford Brook"),
    ("STG", "Stepney Green"),
    ("TEM", "Temple"),
    ("THL", "Tower Hill"),
    ("TGR", "Turnham Green"),
    ("UPM", "Upminster"),
    ("UPB", "Upminster Bridge"),
    ("UPY", "Upney"),
    ("UPK", "Upton Park"),
    ("VIC", "Victoria"),
    ("WBT", "West Brompton"),
    ("WHM", "West Ham"),
    ("WKN", "West Kensington"),
    ("WMS", "Westminster"),
    ("WCL", "Whitechapel"),
    ("WDN", "Wimbledon"),
    ("WMP", "Wimbledon Park"),
]


def pretty_time(value: str) -> str:
    value = value.replace(":00", " min")
    value = value.replace("0:30", "1/2 min")
    value = value.replace(":30", "1/2 min")
    value = value.replace("-", "Now")
    return value


def fetch_accessible_predictions(stop: str) -> dict[str, Any]:
    if not _STOP_CODE_RE.match(stop):
        raise ValueError("invalid stop code")
    encoded = quote(stop, safe="")
    url = f"http://cloud.tfl.gov.uk/TrackerNet/PredictionDetailed/D/{encoded}"
    response = requests.get(url, timeout=20)
    response.raise_for_status()

    root = ET.fromstring(response.text)

    station_name = ""
    platforms: list[dict[str, Any]] = []

    for station in root.findall("S"):
        station_name = station.attrib.get("N", "")
        for platform in station.findall("P"):
            platform_data = {
                "name": platform.attrib.get("N", ""),
                "rows": [],
            }
            for train in platform.findall("T"):
                lcid = train.attrib.get("LCID", "")
                platform_data["rows"].append(
                    {
                        "due": pretty_time(train.attrib.get("TimeTo", "")),
                        "destination": train.attrib.get("Destination", ""),
                        "id": lcid,
                        "location": train.attrib.get("Location", ""),
                        "is_non": not lcid.startswith("2"),
                    }
                )
            platforms.append(platform_data)

    return {
        "station_name": station_name,
        "platforms": platforms,
    }
