from __future__ import annotations

import datetime as dt
import json
from typing import Any
from urllib.parse import urlencode

import requests

BUS_COLS_TEXT = (
    "StopPointName,StopID,Towards,StopPointIndicator,StopPointState,Latitude,Longitude,"
    "VisitNumber,LineID,LineName,DirectionID,DestinationName,VehicleID,TripID,"
    "RegistrationNumber,EstimatedTime,ExpireTime"
)


def _time_sort_key(entry: list[Any], col_estimated_time: int) -> int:
    value = entry[col_estimated_time]
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _plural_minutes(value: float) -> str:
    rounded = round(value * 2) / 2
    suffix = "" if round(rounded) == 1 else "s"
    return f"in {rounded} minute{suffix}"


def fetch_bus_payload(line: str) -> dict[str, Any]:
    cols = ["ReturnType"] + BUS_COLS_TEXT.split(",")
    col = {name: idx for idx, name in enumerate(cols)}

    params = {"ReturnList": BUS_COLS_TEXT}
    route = line.strip()
    if len(route) == 7 and "," not in route:
        params["RegistrationNumber"] = route
    else:
        params["LineName"] = route

    url = (
        "http://countdown.api.tfl.gov.uk/interfaces/ura/instant_V1?" + urlencode(params)
    )
    response = requests.get(url, timeout=20)
    response.raise_for_status()

    rows: list[list[Any]] = []
    for raw in response.text.splitlines():
        if not raw.strip():
            continue
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            continue
        rows.append(parsed)

    stops: dict[str, dict[str, Any]] = {}
    vehicles: dict[str, list[list[Any]]] = {}

    for row in rows:
        if row[col["ReturnType"]] != 1:
            continue
        if row[col["StopPointState"]] in (2, 3):
            continue

        stop_id = str(row[col["StopID"]])
        if stop_id not in stops:
            name = str(row[col["StopPointName"]])
            indicator = row[col["StopPointIndicator"]]
            towards = row[col["Towards"]]
            if indicator:
                name += f" ({indicator})"
            if towards:
                name += f"<br>towards {towards}"

            point = [float(row[col["Latitude"]]), float(row[col["Longitude"]])]
            if point == [0.0, 0.0] and name == "Summit Close<br>towards Queensbury":
                point = [51.606065, -0.276948]
            if name == "Whitgift Centre (WJ)<br>towards Selsdon, Shirley or Wallington":
                point = [51.3769688, -0.0987477]
            if point == [0.0, 0.0]:
                continue
            stops[stop_id] = {"point": point, "name": name}

        vehicle_id = str(row[col["VehicleID"]])
        vehicles.setdefault(vehicle_id, []).append(row)

    route_prior: dict[str, list[str]] = {}
    for predictions in vehicles.values():
        predictions.sort(key=lambda x: _time_sort_key(x, col["EstimatedTime"]))
        prior: str | None = None
        for prediction in predictions:
            stop_id = str(prediction[col["StopID"]])
            route_prior.setdefault(stop_id, [])
            if prior and prior not in route_prior[stop_id]:
                route_prior[stop_id].append(prior)
            prior = stop_id

    buses: list[dict[str, Any]] = []
    now = dt.datetime.now(tz=dt.timezone.utc).timestamp()

    for predictions in vehicles.values():
        predictions.sort(key=lambda x: _time_sort_key(x, col["EstimatedTime"]))
        first = predictions[0]

        registration = str(first[col["RegistrationNumber"]])
        title = (
            f"{first[col['LineName']]} to {first[col['DestinationName']]} "
            f"({registration}, id {first[col['VehicleID']]})"
        )

        next_stops: list[dict[str, Any]] = []
        for prediction in predictions:
            mins = (int(prediction[col["EstimatedTime"]]) / 1000 - now) / 60
            stop_name = str(prediction[col["StopPointName"]])
            point = [
                float(prediction[col["Latitude"]]),
                float(prediction[col["Longitude"]]),
            ]
            if point == [0.0, 0.0] and stop_name == "Summit Close":
                point = [51.606065, -0.276948]

            next_stops.append(
                {
                    "dexp": _plural_minutes(mins),
                    "mins": mins,
                    "name": stop_name,
                    "point": point,
                }
            )

        first_stop_id = str(first[col["StopID"]])
        priors = route_prior.get(first_stop_id, [])
        if priors:
            prior = priors[0]
            if len(predictions) > 1:
                second = str(predictions[1][col["StopID"]])
                for candidate in priors:
                    if candidate != second:
                        prior = candidate
                        break
            point = stops.get(prior, {}).get(
                "point",
                [float(first[col["Latitude"]]), float(first[col["Longitude"]])],
            )
        else:
            point = [float(first[col["Latitude"]]), float(first[col["Longitude"]])]

        buses.append(
            {
                "id": registration,
                "title": title,
                "next": next_stops,
                "left": "",
                "point": point,
            }
        )

    return {
        "lastupdate": dt.datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z"),
        "station": "",
        "trains": buses,
        "polylines": [],
        "stations": list(stops.values()),
    }


def empty_bus_payload() -> dict[str, Any]:
    return {
        "lastupdate": dt.datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z"),
        "station": "",
        "trains": [],
        "polylines": [],
        "stations": [],
    }
