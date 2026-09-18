"""Tests for Dynamic Graph & Budget Re-allocation Architecture."""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from core.observer import BudgetObserverInterceptor, WaterfallEngine
from state_manager import (
    Coordinates,
    EdgeJSON,
    NodeJSON,
    SpatialContext,
    TripState,
    seed_default_trip,
)
from tools.distance import (
    calculate_spatial_context,
    estimate_travel_time_mins,
    haversine_distance_km,
)


def test_haversine_distance():
    # Rossio Square to Belém Tower (~7.09 km)
    rossio = {"lat": 38.7138, "lng": -9.1394}
    belem = {"lat": 38.6916, "lng": -9.2160}
    dist = haversine_distance_km(rossio, belem)
    assert 6.8 <= dist <= 7.3

    # Zero distance between identical coordinates
    assert haversine_distance_km(rossio, rossio) == 0.0

    # Tuple coordinate support
    dist_tuple = haversine_distance_km((38.7138, -9.1394), (38.6916, -9.2160))
    assert dist_tuple == dist


def test_estimate_travel_time_mins():
    # Walking 1.8 km at ~4.8 km/h ~ 22.5 mins -> 23 mins
    mins_walk = estimate_travel_time_mins(1.8, transport_mode="walking")
    assert 20 <= mins_walk <= 25

    # Transit for 7.0 km ~ 7/22*60 + 5 min buffer ~ 24 mins
    mins_transit = estimate_travel_time_mins(7.0, transport_mode="transit")
    assert 20 <= mins_transit <= 30

    # Zero distance
    assert estimate_travel_time_mins(0.0) == 0


def test_spatial_context_generation():
    hotel_coord = {"lat": 38.7138, "lng": -9.1394}
    node1_coord = {"lat": 38.7139, "lng": -9.1335}
    node2_coord = {"lat": 38.7118, "lng": -9.1302}

    ctx = calculate_spatial_context(
        node_coord=node2_coord,
        hotel_coord=hotel_coord,
        prev_node_coord=node1_coord,
        prev_node_id="node_1",
    )
    assert ctx["prev_node_id"] == "node_1"
    assert ctx["distance_from_hotel_km"] > 0
    assert ctx["distance_from_prev_node_km"] > 0


def test_state_manager_lifecycle_and_serialization():
    trip = seed_default_trip(budget_cap=800.0)
    assert len(trip.nodes) >= 10
    assert len(trip.edges) >= 5
    assert trip.current_total_spend <= 800.0
    assert trip.get_status_flag() == "BALANCED"

    # Add custom node
    new_node = NodeJSON(
        id="custom_node_test",
        day=1,
        type="activity",
        title="Custom Walking Tour",
        intro="Guided tour of historic quarters",
        cost=20.0,
        coordinates=Coordinates(lat=38.715, lng=-9.135),
        is_user_added=True,
    )
    added = trip.add_node(new_node)
    assert added.id == "custom_node_test"
    assert trip.get_node("custom_node_test") is not None

    # Test file round-trip
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        trip.save_to_file(tmp_path)
        loaded = TripState.load_from_file(tmp_path)
        assert loaded.trip_name == trip.trip_name
        assert len(loaded.nodes) == len(trip.nodes)
        assert loaded.current_total_spend == trip.current_total_spend
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_waterfall_immediate_pass():
    # Adding a node when spend is well below budget cap ($800)
    trip = seed_default_trip(budget_cap=800.0)
    initial_spend = trip.current_total_spend
    assert initial_spend < 600.0

    new_node = NodeJSON(
        id="cheap_cafe",
        day=2,
        type="food",
        title="Boutique Espresso",
        intro="Specialty coffee and pastry",
        cost=15.0,
        coordinates=Coordinates(lat=38.71, lng=-9.14),
    )
    observer = BudgetObserverInterceptor(hard_cap=800.0)
    state, res = observer.on_user_node_injected(trip, new_node, target_day=2)

    assert res.success is True
    assert res.status_flag == "BALANCED"
    assert len(res.mutations) == 0
    assert state.current_total_spend == initial_spend + 15.0


def test_waterfall_step1_local_day_pruning():
    # Configure tight cap so Day 2 addition triggers local Day 2 pruning
    trip = seed_default_trip(budget_cap=420.0)
    initial_spend = trip.current_total_spend  # ~409.0

    # Injected node costs $25. Deficit will be ~14.0
    new_node = NodeJSON(
        id="scenic_tuk_tuk",
        day=2,
        type="activity",
        title="Belém Tuk Tuk Adventure",
        intro="Private motorized tour along the coastline",
        cost=25.0,
        coordinates=Coordinates(lat=38.695, lng=-9.21),
    )
    observer = BudgetObserverInterceptor(hard_cap=420.0)
    state, res = observer.on_user_node_injected(trip, new_node, target_day=2)

    assert res.status_flag == "BALANCED"
    assert state.current_total_spend <= 420.0
    # Day 2 had Time Out Market ($24) or Jeronimos ($12) which should be mutated/pruned
    assert any(m.day == 2 for m in res.mutations)


def test_waterfall_step2_global_cascade_pruning():
    # Tight cap where Day 2 cannot absorb the entire deficit alone
    trip = seed_default_trip(budget_cap=420.0)
    # Inject large node of $70 into Day 2
    new_node = NodeJSON(
        id="luxury_sailing",
        day=2,
        type="activity",
        title="Sunset Champagne Catamaran",
        intro="2-hour private river cruise with appetizers",
        cost=70.0,
        coordinates=Coordinates(lat=38.69, lng=-9.20),
    )
    observer = BudgetObserverInterceptor(hard_cap=420.0)
    state, res = observer.on_user_node_injected(trip, new_node, target_day=2)

    assert res.status_flag == "BALANCED"
    assert state.current_total_spend <= 420.0
    # Waterfall must have cascaded to other days (Day 3 or Day 4)
    mutation_days = {m.day for m in res.mutations}
    assert len(mutation_days) >= 2


def test_waterfall_step3_hard_boundary_fallback():
    # Impossibly small cap where even trimming all flexible nodes exceeds cap
    trip = seed_default_trip(budget_cap=200.0)  # Hotel alone is $180!
    new_node = NodeJSON(
        id="mega_helicopter",
        day=1,
        type="activity",
        title="Helicopter Tour of Sintra & Cascais",
        intro="VIP helicopter excursion",
        cost=350.0,
        coordinates=Coordinates(lat=38.71, lng=-9.13),
    )
    observer = BudgetObserverInterceptor(hard_cap=200.0)
    state, res = observer.on_user_node_injected(trip, new_node, target_day=1)

    # Invariant cannot be satisfied without violating essential constraints
    assert res.success is False
    assert res.status_flag == "BUDGET EXCEEDED"
    assert res.warning is not None
    assert "Exceeds hard budget cap" in res.warning
    assert "[WARNING:" in new_node.intro
