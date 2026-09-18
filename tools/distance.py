"""Spatial engine: Haversine distance calculation and travel time estimation."""

from __future__ import annotations

import math
from typing import TypedDict, Optional

# Earth radius in kilometers (WGS-84 mean radius)
EARTH_RADIUS_KM = 6371.0088


class CoordinateDict(TypedDict):
    lat: float
    lng: float


def haversine_distance_km(
    coord1: CoordinateDict | tuple[float, float] | dict[str, float],
    coord2: CoordinateDict | tuple[float, float] | dict[str, float],
) -> float:
    """Calculate the great-circle distance between two points on the Earth using the Haversine formula.

    Accepts dict with 'lat' and 'lng' keys, or (lat, lng) tuple.
    Returns distance in kilometers rounded to 2 decimal places.
    """
    if isinstance(coord1, (tuple, list)):
        lat1, lon1 = float(coord1[0]), float(coord1[1])
    else:
        lat1, lon1 = float(coord1["lat"]), float(coord1["lng"])

    if isinstance(coord2, (tuple, list)):
        lat2, lon2 = float(coord2[0]), float(coord2[1])
    else:
        lat2, lon2 = float(coord2["lat"]), float(coord2["lng"])

    # Convert decimal degrees to radians
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp to avoid domain errors with float inaccuracies
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance = EARTH_RADIUS_KM * c
    return round(distance, 2)


def estimate_travel_time_mins(
    distance_km: float, transport_mode: str = "walking"
) -> int:
    """Estimate travel time in minutes based on distance and transport mode.

    Modes:
      - 'walking': ~4.8 km/h (~12.5 mins/km) + 2 min buffer
      - 'transit' / 'public_transit': ~20 km/h + 5 min wait buffer
      - 'driving' / 'taxi': ~30 km/h + 3 min buffer
    """
    mode = (transport_mode or "walking").lower()
    if distance_km <= 0:
        return 0

    if "walk" in mode:
        speed_kmh = 4.8
        base_mins = (distance_km / speed_kmh) * 60.0
        return max(1, int(round(base_mins)))
    elif "transit" in mode or "bus" in mode or "metro" in mode:
        speed_kmh = 22.0
        wait_buffer = 5
        base_mins = (distance_km / speed_kmh) * 60.0 + wait_buffer
        return max(5, int(round(base_mins)))
    elif "drive" in mode or "taxi" in mode or "car" in mode:
        speed_kmh = 32.0
        wait_buffer = 3
        base_mins = (distance_km / speed_kmh) * 60.0 + wait_buffer
        return max(3, int(round(base_mins)))
    else:
        # Default walking
        speed_kmh = 5.0
        base_mins = (distance_km / speed_kmh) * 60.0
        return max(1, int(round(base_mins)))


def format_edge_label(distance_km: float, travel_time_mins: int, transport_mode: str = "walking") -> str:
    """Format human-readable edge label like '1.8 km (22 min walk)'."""
    mode_str = "walk" if "walk" in transport_mode.lower() else transport_mode
    return f"{distance_km:.1f} km ({travel_time_mins} min {mode_str})"


def calculate_spatial_context(
    node_coord: dict[str, float],
    hotel_coord: Optional[dict[str, float]] = None,
    prev_node_coord: Optional[dict[str, float]] = None,
    prev_node_id: Optional[str] = None,
) -> dict:
    """Calculate spatial context dictionary for a node:

    {
      "distance_from_hotel_km": float,
      "distance_from_prev_node_km": float,
      "prev_node_id": str | None
    }
    """
    dist_hotel = 0.0
    if hotel_coord:
        dist_hotel = haversine_distance_km(node_coord, hotel_coord)

    dist_prev = 0.0
    if prev_node_coord:
        dist_prev = haversine_distance_km(node_coord, prev_node_coord)
    elif hotel_coord:
        # Fallback to hotel if no previous node
        dist_prev = dist_hotel

    return {
        "distance_from_hotel_km": dist_hotel,
        "distance_from_prev_node_km": dist_prev,
        "prev_node_id": prev_node_id,
    }
