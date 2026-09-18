"""State Manager for dynamic graph itineraries, node-edge topology, and budget tracking."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.distance import (
    calculate_spatial_context,
    estimate_travel_time_mins,
    format_edge_label,
    haversine_distance_km,
)

DEFAULT_TRIP_FILE = Path(__file__).resolve().parent / "trip_state.json"


@dataclass
class Coordinates:
    lat: float
    lng: float

    def to_dict(self) -> dict[str, float]:
        return {"lat": float(self.lat), "lng": float(self.lng)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Coordinates:
        return cls(lat=float(data.get("lat", 0.0)), lng=float(data.get("lng", 0.0)))


@dataclass
class SpatialContext:
    distance_from_hotel_km: float = 0.0
    distance_from_prev_node_km: float = 0.0
    prev_node_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "distance_from_hotel_km": round(float(self.distance_from_hotel_km), 2),
            "distance_from_prev_node_km": round(float(self.distance_from_prev_node_km), 2),
            "prev_node_id": self.prev_node_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpatialContext:
        return cls(
            distance_from_hotel_km=float(data.get("distance_from_hotel_km", 0.0)),
            distance_from_prev_node_km=float(data.get("distance_from_prev_node_km", 0.0)),
            prev_node_id=data.get("prev_node_id"),
        )


@dataclass
class NodeJSON:
    id: str
    day: int
    type: str  # "hotel" | "activity" | "food" | "custom"
    title: str
    intro: str
    cost: float
    coordinates: Coordinates
    spatial_context: SpatialContext = field(default_factory=SpatialContext)
    is_user_added: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "day": self.day,
            "type": self.type,
            "title": self.title,
            "intro": self.intro,
            "cost": round(float(self.cost), 2),
            "coordinates": self.coordinates.to_dict(),
            "spatial_context": self.spatial_context.to_dict(),
            "is_user_added": self.is_user_added,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeJSON:
        raw_coords = data.get("coordinates", {})
        coords = Coordinates.from_dict(raw_coords) if isinstance(raw_coords, dict) else Coordinates(0.0, 0.0)

        raw_spatial = data.get("spatial_context", {})
        spatial = SpatialContext.from_dict(raw_spatial) if isinstance(raw_spatial, dict) else SpatialContext()

        return cls(
            id=str(data["id"]),
            day=int(data.get("day", 1)),
            type=str(data.get("type", "activity")),
            title=str(data.get("title", "")),
            intro=str(data.get("intro", "")),
            cost=float(data.get("cost", 0.0)),
            coordinates=coords,
            spatial_context=spatial,
            is_user_added=bool(data.get("is_user_added", False)),
        )


@dataclass
class EdgeJSON:
    id: str
    source: str
    target: str
    label: str
    travel_time_mins: int
    transport_mode: str = "walking"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "label": self.label,
            "travel_time_mins": self.travel_time_mins,
            "transport_mode": self.transport_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EdgeJSON:
        return cls(
            id=str(data["id"]),
            source=str(data["source"]),
            target=str(data["target"]),
            label=str(data.get("label", "")),
            travel_time_mins=int(data.get("travel_time_mins", 0)),
            transport_mode=str(data.get("transport_mode", "walking")),
        )


@dataclass
class TripState:
    trip_name: str = "Lisbon Exploration"
    budget_cap: float = 800.00
    current_total_spend: float = 0.0
    nodes: List[NodeJSON] = field(default_factory=list)
    edges: List[EdgeJSON] = field(default_factory=list)

    def __post_init__(self):
        self.update_total_spend()

    def update_total_spend(self) -> float:
        """Calculate and update current total spend across all nodes."""
        total = sum(node.cost for node in self.nodes)
        self.current_total_spend = round(total, 2)
        return self.current_total_spend

    def get_status_flag(self) -> str:
        """Return status badge string: BALANCED, RE-ALLOCATING, or BUDGET EXCEEDED."""
        self.update_total_spend()
        if self.current_total_spend > self.budget_cap:
            return "BUDGET EXCEEDED"
        return "BALANCED"

    def get_daily_breakdown(self) -> dict[int, float]:
        """Return dictionary mapping day number to total spend on that day."""
        breakdown: dict[int, float] = {}
        for node in self.nodes:
            breakdown[node.day] = round(breakdown.get(node.day, 0.0) + node.cost, 2)
        return dict(sorted(breakdown.items()))

    def get_node(self, node_id: str) -> Optional[NodeJSON]:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def get_nodes_for_day(self, day: int) -> List[NodeJSON]:
        return [node for node in self.nodes if node.day == day]

    def get_hotel_for_day(self, day: int) -> Optional[NodeJSON]:
        day_nodes = self.get_nodes_for_day(day)
        for node in day_nodes:
            if node.type == "hotel":
                return node
        # Fallback: find any hotel in the trip
        for node in self.nodes:
            if node.type == "hotel":
                return node
        return None

    def add_node(self, node: NodeJSON | dict[str, Any], recompute_edges: bool = True) -> NodeJSON:
        if isinstance(node, dict):
            node_obj = NodeJSON.from_dict(node)
        else:
            node_obj = node

        # Ensure unique id
        existing_ids = {n.id for n in self.nodes}
        if node_obj.id in existing_ids:
            node_obj.id = f"{node_obj.id}_{len(self.nodes) + 1}"

        self.nodes.append(node_obj)
        self.update_total_spend()

        if recompute_edges:
            self.recalculate_day_spatial_metrics(node_obj.day)

        return node_obj

    def remove_node(self, node_id: str, recompute_edges: bool = True) -> Optional[NodeJSON]:
        target = self.get_node(node_id)
        if not target:
            return None

        day = target.day
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [e for e in self.edges if e.source != node_id and e.target != node_id]
        self.update_total_spend()

        if recompute_edges:
            self.recalculate_day_spatial_metrics(day)

        return target

    def update_node(self, node_id: str, updates: dict[str, Any], recompute_edges: bool = True) -> Optional[NodeJSON]:
        node = self.get_node(node_id)
        if not node:
            return None

        if "cost" in updates:
            node.cost = float(updates["cost"])
        if "title" in updates:
            node.title = str(updates["title"])
        if "intro" in updates:
            node.intro = str(updates["intro"])
        if "type" in updates:
            node.type = str(updates["type"])
        if "coordinates" in updates and isinstance(updates["coordinates"], dict):
            node.coordinates = Coordinates.from_dict(updates["coordinates"])
        if "day" in updates:
            old_day = node.day
            node.day = int(updates["day"])
            if recompute_edges and old_day != node.day:
                self.recalculate_day_spatial_metrics(old_day)

        self.update_total_spend()
        if recompute_edges:
            self.recalculate_day_spatial_metrics(node.day)

        return node

    def recalculate_day_spatial_metrics(self, day: int) -> None:
        """Recalculate spatial context and edges for all nodes in a given day."""
        day_nodes = self.get_nodes_for_day(day)
        if not day_nodes:
            return

        hotel = self.get_hotel_for_day(day)
        hotel_coord = hotel.coordinates.to_dict() if hotel else None

        # Remove existing edges for this day
        day_node_ids = {n.id for n in day_nodes}
        self.edges = [
            e for e in self.edges if not (e.source in day_node_ids and e.target in day_node_ids)
        ]

        # Order nodes: hotel first, then activities/food/custom in arrival order
        hotel_nodes = [n for n in day_nodes if n.type == "hotel"]
        other_nodes = [n for n in day_nodes if n.type != "hotel"]
        ordered_nodes = hotel_nodes + other_nodes

        prev_node: Optional[NodeJSON] = None
        for i, node in enumerate(ordered_nodes):
            node_coord = node.coordinates.to_dict()
            prev_coord = prev_node.coordinates.to_dict() if prev_node else None
            prev_id = prev_node.id if prev_node else None

            ctx_dict = calculate_spatial_context(
                node_coord=node_coord,
                hotel_coord=hotel_coord,
                prev_node_coord=prev_coord,
                prev_node_id=prev_id,
            )
            node.spatial_context = SpatialContext.from_dict(ctx_dict)

            # Generate edge from previous node to this node
            if prev_node:
                dist = haversine_distance_km(prev_coord, node_coord)
                mode = "walking" if dist <= 3.0 else "transit"
                travel_time = estimate_travel_time_mins(dist, mode)
                label = format_edge_label(dist, travel_time, mode)

                edge = EdgeJSON(
                    id=f"edge_{prev_node.id}_to_{node.id}",
                    source=prev_node.id,
                    target=node.id,
                    label=label,
                    travel_time_mins=travel_time,
                    transport_mode=mode,
                )
                self.edges.append(edge)

            prev_node = node

    def recalculate_all_spatial_metrics(self) -> None:
        days = {n.day for n in self.nodes}
        for day in days:
            self.recalculate_day_spatial_metrics(day)
        self.update_total_spend()

    def to_dict(self) -> dict[str, Any]:
        self.update_total_spend()
        return {
            "trip_name": self.trip_name,
            "budget_cap": round(float(self.budget_cap), 2),
            "current_total_spend": round(float(self.current_total_spend), 2),
            "status_flag": self.get_status_flag(),
            "daily_breakdown": self.get_daily_breakdown(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TripState:
        raw_nodes = data.get("nodes", [])
        nodes = [NodeJSON.from_dict(n) for n in raw_nodes]
        raw_edges = data.get("edges", [])
        edges = [EdgeJSON.from_dict(e) for e in raw_edges]

        state = cls(
            trip_name=str(data.get("trip_name", "Lisbon Exploration")),
            budget_cap=float(data.get("budget_cap", 800.00)),
            current_total_spend=float(data.get("current_total_spend", 0.0)),
            nodes=nodes,
            edges=edges,
        )
        state.update_total_spend()
        return state

    @classmethod
    def from_json(cls, json_str: str) -> TripState:
        return cls.from_dict(json.loads(json_str))

    def save_to_file(self, filepath: Path | str = DEFAULT_TRIP_FILE) -> None:
        target = Path(filepath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load_from_file(cls, filepath: Path | str = DEFAULT_TRIP_FILE) -> TripState:
        target = Path(filepath)
        if not target.is_file():
            # Generate default seed state
            state = seed_default_trip()
            state.save_to_file(target)
            return state
        return cls.from_json(target.read_text(encoding="utf-8"))


def seed_default_trip(budget_cap: float = 800.00, trip_name: str = "Lisbon Exploration") -> TripState:
    """Create a realistic, day-clustered default trip state for Lisbon."""
    state = TripState(trip_name=trip_name, budget_cap=budget_cap)

    # Hotel anchor
    hotel_coord = Coordinates(lat=38.7138, lng=-9.1394)  # Rossio Square / Baixa
    hotel_node = NodeJSON(
        id="hotel_basecamp",
        day=1,
        type="hotel",
        title="Hub New Lisbon Hostel (Basecamp)",
        intro="Central budget accommodation in Baixa with rooftop terrace and shared kitchen.",
        cost=180.00,  # 5 nights total lodging apportioned
        coordinates=hotel_coord,
        is_user_added=False,
    )
    state.add_node(hotel_node, recompute_edges=False)

    # Day 1: Alfama & Historic Center
    day1_items = [
        NodeJSON(
            id="node_day1_act1",
            day=1,
            type="activity",
            title="São Jorge Castle",
            intro="Historic Moorish citadel perched atop Lisbon's highest hill with panoramic Tagus vistas.",
            cost=15.00,
            coordinates=Coordinates(lat=38.7139, lng=-9.1335),
        ),
        NodeJSON(
            id="node_day1_lunch",
            day=1,
            type="food",
            title="Traditional Alfama Tasca",
            intro="Authentic grilled sardines, caldo verde, and house wine in a cobbled alley.",
            cost=18.50,
            coordinates=Coordinates(lat=38.7118, lng=-9.1302),
        ),
        NodeJSON(
            id="node_day1_act2",
            day=1,
            type="activity",
            title="Miradouro de Santa Luzia",
            intro="Romantic bougainvillea-framed viewpoint overlooking red-tiled Alfama roofs and river.",
            cost=0.00,
            coordinates=Coordinates(lat=38.7116, lng=-9.1305),
        ),
        NodeJSON(
            id="node_day1_dinner",
            day=1,
            type="food",
            title="Fado Dinner in Mouraria",
            intro="Intimate local tavern with live Portuguese guitar and traditional bacalhau à brás.",
            cost=32.00,
            coordinates=Coordinates(lat=38.7161, lng=-9.1360),
        ),
    ]

    # Day 2: Belém & Maritime History
    day2_items = [
        NodeJSON(
            id="node_day2_act1",
            day=2,
            type="activity",
            title="Jerónimos Monastery",
            intro="UNESCO World Heritage masterpiece of Manueline architecture and Vasco da Gama's tomb.",
            cost=12.00,
            coordinates=Coordinates(lat=38.6979, lng=-9.2067),
        ),
        NodeJSON(
            id="node_day2_food1",
            day=2,
            type="food",
            title="Pastéis de Belém",
            intro="Original 1837 bakery serving warm custard tarts dusted with cinnamon and sugar.",
            cost=6.50,
            coordinates=Coordinates(lat=38.6975, lng=-9.2033),
        ),
        NodeJSON(
            id="node_day2_act2",
            day=2,
            type="activity",
            title="Belém Tower",
            intro="Iconic 16th-century fortified tower on the northern bank of the Tagus River.",
            cost=9.00,
            coordinates=Coordinates(lat=38.6916, lng=-9.2160),
        ),
        NodeJSON(
            id="node_day2_dinner",
            day=2,
            type="food",
            title="Time Out Market Lisbon",
            intro="Vibrant gourmet food hall featuring curated stalls from renowned Portuguese chefs.",
            cost=24.00,
            coordinates=Coordinates(lat=38.7071, lng=-9.1458),
        ),
    ]

    # Day 3: Sintra Day Excursion
    day3_items = [
        NodeJSON(
            id="node_day3_act1",
            day=3,
            type="activity",
            title="Pena National Palace (Sintra)",
            intro="Vivid yellow and red Romanticist castle nestled in the lush Sintra mountain pine forests.",
            cost=20.00,
            coordinates=Coordinates(lat=38.7876, lng=-9.3906),
        ),
        NodeJSON(
            id="node_day3_act2",
            day=3,
            type="activity",
            title="Quinta da Regaleira",
            intro="Mystical estate featuring Gothic towers, subterranean tunnels, and the famous Initiation Well.",
            cost=12.00,
            coordinates=Coordinates(lat=38.7963, lng=-9.3960),
        ),
        NodeJSON(
            id="node_day3_food",
            day=3,
            type="food",
            title="Piriquita Bakery & Lunch",
            intro="Famous Sintra pastry shop renowned for Travesseiros and Queijadas pastries.",
            cost=14.00,
            coordinates=Coordinates(lat=38.7966, lng=-9.3905),
        ),
    ]

    # Day 4: Modern Lisbon & Oceanarium
    day4_items = [
        NodeJSON(
            id="node_day4_act1",
            day=4,
            type="activity",
            title="Oceanário de Lisboa",
            intro="One of the world's largest public aquariums featuring a massive 5-million-liter central tank.",
            cost=22.00,
            coordinates=Coordinates(lat=38.7635, lng=-9.0937),
        ),
        NodeJSON(
            id="node_day4_act2",
            day=4,
            type="activity",
            title="Parque das Nações Telecabine",
            intro="Scenic cable car glide along the Tagus waterfront offering panoramic views of Vasco da Gama bridge.",
            cost=8.00,
            coordinates=Coordinates(lat=38.7661, lng=-9.0945),
        ),
        NodeJSON(
            id="node_day4_food",
            day=4,
            type="food",
            title="Waterfront Seafood Dinner",
            intro="Fresh catch of the day, arroz de marisco, and Vinho Verde at Doca dos Olivais.",
            cost=36.00,
            coordinates=Coordinates(lat=38.7628, lng=-9.0968),
        ),
    ]

    all_items = day1_items + day2_items + day3_items + day4_items
    for item in all_items:
        state.add_node(item, recompute_edges=False)

    state.recalculate_all_spatial_metrics()
    return state
