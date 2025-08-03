import os
import random
from datetime import datetime
from typing import List, Tuple

import dotenv
import requests
from shapely.geometry import Point, Polygon, MultiPolygon

from traveltimepy import Client
from traveltimepy.requests.common import Coordinates, Location
from traveltimepy.requests.routes import (
    RoutesDepartureSearch,
    Property as RoutesProperty,
)
from traveltimepy.requests.time_map import (
    TimeMapDepartureSearch,
    TimeMapIntersection,
)
from traveltimepy.requests.transportation import (
    PublicTransport,
    Driving,
    Ferry,
    Walking,
    Cycling,
    DrivingTrain,
    CyclingPublicTransport,
)

dotenv.load_dotenv()
_client = Client(app_id=os.getenv("APP_ID"), api_key=os.getenv("API_KEY"))

Transport = {
    cls.__name__: cls
    for cls in (
        PublicTransport,
        Driving,
        Ferry,
        Walking,
        Cycling,
        DrivingTrain,
        CyclingPublicTransport,
    )
}


# -- single-origin reachability --
def reachable_shapes(
    center: Tuple[float, float],
    mode: str,
    minutes: int,
    depart_time: datetime,
):
    search = TimeMapDepartureSearch(
        id="area",
        coords=Coordinates(lat=center[0], lng=center[1]),
        transportation=Transport[mode](),
        departure_time=depart_time.isoformat(),
        travel_time=minutes * 60,
    )
    return _client.time_map(
        departure_searches=[search],
        arrival_searches=[],
        unions=[],
        intersections=[],
    ).results[0].shapes


# -- dual-origin intersection --
def intersection_shapes(
    a: tuple[float, float],
    b: tuple[float, float],
    mode: str,
    minutes: int,
    depart: datetime,
):
    """
    Get the polygons that can be reached from *both* start points
    within **minutes** using **mode** at **depart**.
    """
    searches = [
        TimeMapDepartureSearch(
            id="A",
            coords=Coordinates(lat=a[0], lng=a[1]),
            transportation=Transport[mode](),
            departure_time=depart.isoformat(),
            travel_time=minutes * 60,
        ),
        TimeMapDepartureSearch(
            id="B",
            coords=Coordinates(lat=b[0], lng=b[1]),
            transportation=Transport[mode](),
            departure_time=depart.isoformat(),
            travel_time=minutes * 60,
        ),
    ]

    inter = TimeMapIntersection(id="AB", search_ids=["A", "B"])

    res = _client.time_map(
        departure_searches=searches,
        intersections=[inter],
        unions=[],
        arrival_searches=[]
    )

    for r in res.results:
        if r.search_id == "AB":
            break

    return r.shapes


# -- POI helpers --
def _bbox(shell) -> Tuple[float, float, float, float]:
    lats = [p.lat for p in shell]
    lngs = [p.lng for p in shell]
    return min(lngs), min(lats), max(lngs), max(lats)  # W S E N


def _fetch_pois(bbox: Tuple[float, float, float, float]) -> List[Tuple[str, float, float]]:
    south, west, north, east = bbox[1], bbox[0], bbox[3], bbox[2]
    box = f"({south},{west},{north},{east})"
    query = f"""
    [out:json][timeout:25];
      (
        node   ["tourism"~"attraction|museum|viewpoint|monument|artwork"]{box};
        way    ["tourism"~"attraction|museum|viewpoint|monument|artwork"]{box};
        rel    ["tourism"~"attraction|museum|viewpoint|monument|artwork"]{box};
        node   ["historic"]{box};
        way    ["historic"]{box};
        rel    ["historic"]{box};
      );
    out center;
    """
    elements = requests.get("https://overpass-api.de/api/interpreter",
                            params={"data": query}).json().get("elements", [])
    out = []
    for el in elements:
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat and lon:
            out.append((el.get("tags", {}).get("name", "Unnamed"), lat, lon))
    return out


def pois_inside(shapes, max_count: int = 10):
    polys = [Polygon([(p.lng, p.lat) for p in s.shell]) for s in shapes]
    area  = MultiPolygon(polys)
    raw: list[tuple[str, float, float]] = []
    for sh in shapes:
        raw += _fetch_pois(_bbox(sh.shell))
    seen, keep = set(), []
    for n, lat, lon in raw:
        if (n, lat, lon) in seen:
            continue
        if area.contains(Point(lon, lat)):
            seen.add((n, lat, lon))
            keep.append((n, lat, lon))
    random.shuffle(keep)
    return keep[:max_count]


def common_pois(*args, **kwargs):
    shapes = intersection_shapes(*args, **kwargs)
    return pois_inside(shapes)


# -- routing --
def route_to(start: Tuple[float, float], dest: Tuple[float, float], mode: str):
    search = RoutesDepartureSearch(
        id="route",
        departure_location_id="start",
        arrival_location_ids=["poi"],
        transportation=Transport[mode](),
        departure_time=datetime.now().isoformat(),
        properties=[
            RoutesProperty.TRAVEL_TIME,
            RoutesProperty.DISTANCE,
            RoutesProperty.ROUTE,
        ],
    )
    res = _client.routes(
        locations=[
            Location(id="start", coords=Coordinates(lat=start[0], lng=start[1])),
            Location(id="poi",   coords=Coordinates(lat=dest[0], lng=dest[1])),
        ],
        departure_searches=[search],
        arrival_searches=[],
    )
    loc   = res.results[0].locations[0]
    parts = loc.properties[0].route.parts
    line  = [(c.lat, c.lng) for p in parts for c in p.coords]
    dirs  = [p.directions for p in parts if getattr(p, "directions", "")]
    sec   = loc.properties[0].travel_time
    km    = (
        loc.properties[0].distance / 1000
        if loc.properties[0].distance is not None
        else None
    )
    return line, dirs, sec, km
