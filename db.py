"""MongoDB database layer with graceful fallback to local JSON files.

Provides CRUD operations for:
- Travel profiles (travelers, trips, preferences)
- Generated itineraries (with budget audit results)
- Execution traces (full ReAct step logs)
- Destination knowledge base (seasonal prices, attractions)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logging_config import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
PROFILE_PATH = PROJECT_ROOT / "travel_profile.json"

# ---------------------------------------------------------------------------
# MongoDB Connection Management
# ---------------------------------------------------------------------------

_client = None
_db = None
_mongo_available: bool | None = None


def _get_mongo_config() -> tuple[str, str, int]:
    """Read MongoDB settings from environment (avoids circular import with config.py)."""
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", "travelagent")
    timeout = int(os.environ.get("MONGO_TIMEOUT_MS", "2000"))
    return uri, db_name, timeout


def get_db():
    """Get or create MongoDB database connection. Returns None if unavailable."""
    global _client, _db, _mongo_available

    if _mongo_available is False:
        return None

    if _db is not None:
        return _db

    try:
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

        uri, db_name, timeout = _get_mongo_config()
        _client = MongoClient(uri, serverSelectionTimeoutMS=timeout)
        # Verify connection with a fast ping
        _client.admin.command("ping")
        _db = _client[db_name]
        _mongo_available = True
        logger.info(f"Connected to MongoDB: {db_name} at {uri}")
        _ensure_indexes()
        return _db
    except Exception as exc:
        _mongo_available = False
        _client = None
        _db = None
        logger.warning(f"MongoDB unavailable, falling back to local JSON: {exc}")
        return None


def is_mongo_connected() -> bool:
    """Check if MongoDB is currently connected."""
    return _mongo_available is True and _db is not None


def reset_db() -> None:
    """Reset the database connection (useful for testing)."""
    global _client, _db, _mongo_available
    if _client:
        try:
            _client.close()
        except Exception:
            pass
    _client = None
    _db = None
    _mongo_available = None


def _ensure_indexes() -> None:
    """Create indexes for efficient queries."""
    if _db is None:
        return
    try:
        _db.travel_profiles.create_index("profile_id", unique=True)
        _db.itineraries.create_index([("created_at", -1)])
        _db.itineraries.create_index("profile_id")
        _db.execution_traces.create_index("session_id")
        _db.execution_traces.create_index([("created_at", -1)])
        _db.destinations.create_index("name", unique=True)
        _db.destinations.create_index([("country", 1)])
    except Exception as exc:
        logger.warning(f"Failed to create indexes: {exc}")


# ---------------------------------------------------------------------------
# Travel Profiles
# ---------------------------------------------------------------------------

def save_profile(profile_data: dict, profile_id: str | None = None) -> dict:
    """Save a travel profile to MongoDB (with JSON file sync)."""
    if profile_id is None:
        profile_id = "default"

    # Always sync to local JSON file as backup
    _save_profile_json(profile_data)

    db = get_db()
    if db is not None:
        try:
            doc = {
                **profile_data,
                "profile_id": profile_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            db.travel_profiles.replace_one(
                {"profile_id": profile_id}, doc, upsert=True
            )
            logger.info(f"Profile '{profile_id}' saved to MongoDB")
        except Exception as exc:
            logger.warning(f"Failed to save profile to MongoDB: {exc}")

    return profile_data


def get_profile(profile_id: str | None = None) -> dict:
    """Load a travel profile from MongoDB, falling back to local JSON."""
    if profile_id is None:
        profile_id = "default"

    db = get_db()
    if db is not None:
        try:
            doc = db.travel_profiles.find_one(
                {"profile_id": profile_id}, {"_id": 0, "profile_id": 0, "updated_at": 0}
            )
            if doc:
                return doc
        except Exception as exc:
            logger.warning(f"Failed to read profile from MongoDB: {exc}")

    # Fallback to local JSON file
    return _load_profile_json()


def list_profiles(limit: int = 50) -> list[dict]:
    """List all saved profiles from MongoDB."""
    db = get_db()
    if db is None:
        return [_load_profile_json()]
    try:
        cursor = db.travel_profiles.find(
            {}, {"_id": 0}
        ).sort("updated_at", -1).limit(limit)
        return list(cursor)
    except Exception as exc:
        logger.warning(f"Failed to list profiles: {exc}")
        return [_load_profile_json()]


def _save_profile_json(profile_data: dict) -> None:
    """Sync profile to local JSON file."""
    try:
        PROFILE_PATH.write_text(
            json.dumps(profile_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning(f"Failed to write local profile JSON: {exc}")


def _load_profile_json() -> dict:
    """Load profile from local JSON file."""
    if PROFILE_PATH.is_file():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Failed to read local profile JSON: {exc}")
    return _default_profile()


def _default_profile() -> dict:
    """Return a sensible default profile."""
    return {
        "traveler": {
            "name": "Traveler",
            "origin": "City, Country",
            "party_size": 1,
        },
        "trip": {
            "destination": "Lisbon, Portugal",
            "start_date": "2026-10-12",
            "end_date": "2026-10-17",
            "nights": 5,
        },
        "budget": {
            "currency": "USD",
            "hard_cap": 800,
            "rule": "Total spend must be less than or equal to $800",
        },
        "preferences": {
            "pace": "walkable neighborhoods, one major outing per day",
            "lodging": "central guesthouse or 3-star hotel",
            "interests": ["food", "history", "viewpoints"],
            "dietary": [],
            "avoid": ["all-inclusive resorts", "overnight buses"],
        },
    }


# ---------------------------------------------------------------------------
# Itineraries
# ---------------------------------------------------------------------------

def save_itinerary(
    itinerary_text: str,
    *,
    profile_id: str = "default",
    goal: str = "",
    model: str = "",
    hard_cap: float = 800.0,
    approved: bool = True,
    total_cost: float | None = None,
    steps_count: int = 0,
) -> str | None:
    """Save a generated itinerary to MongoDB. Returns the itinerary_id or None."""
    db = get_db()
    if db is None:
        return None
    try:
        itinerary_id = str(uuid.uuid4())
        doc = {
            "itinerary_id": itinerary_id,
            "profile_id": profile_id,
            "goal": goal,
            "model": model,
            "hard_cap": hard_cap,
            "approved": approved,
            "total_cost": total_cost,
            "steps_count": steps_count,
            "itinerary_text": itinerary_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.itineraries.insert_one(doc)
        logger.info(f"Itinerary {itinerary_id} saved to MongoDB")
        return itinerary_id
    except Exception as exc:
        logger.warning(f"Failed to save itinerary: {exc}")
        return None


def list_itineraries(limit: int = 50, profile_id: str | None = None) -> list[dict]:
    """List past itineraries, newest first."""
    db = get_db()
    if db is None:
        return []
    try:
        query: dict[str, Any] = {}
        if profile_id:
            query["profile_id"] = profile_id
        cursor = db.itineraries.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit)
        return list(cursor)
    except Exception as exc:
        logger.warning(f"Failed to list itineraries: {exc}")
        return []


def get_itinerary(itinerary_id: str) -> dict | None:
    """Get a single itinerary by ID."""
    db = get_db()
    if db is None:
        return None
    try:
        return db.itineraries.find_one({"itinerary_id": itinerary_id}, {"_id": 0})
    except Exception as exc:
        logger.warning(f"Failed to get itinerary: {exc}")
        return None


# ---------------------------------------------------------------------------
# Execution Traces
# ---------------------------------------------------------------------------

def save_trace(
    session_id: str,
    step: int,
    *,
    thought: str | None = None,
    action: str | None = None,
    action_input: str | None = None,
    observation: str | None = None,
    is_final: bool = False,
    final_answer: str | None = None,
) -> None:
    """Record a single ReAct execution step in MongoDB."""
    db = get_db()
    if db is None:
        return
    try:
        doc = {
            "session_id": session_id,
            "step": step,
            "thought": thought,
            "action": action,
            "action_input": action_input,
            "observation": observation,
            "is_final": is_final,
            "final_answer": final_answer,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.execution_traces.insert_one(doc)
    except Exception as exc:
        logger.warning(f"Failed to save trace step {step}: {exc}")


def get_traces(session_id: str) -> list[dict]:
    """Get all trace steps for a session, ordered by step number."""
    db = get_db()
    if db is None:
        return []
    try:
        cursor = db.execution_traces.find(
            {"session_id": session_id}, {"_id": 0}
        ).sort("step", 1)
        return list(cursor)
    except Exception as exc:
        logger.warning(f"Failed to get traces: {exc}")
        return []


def list_sessions(limit: int = 50) -> list[dict]:
    """List recent unique session IDs with metadata."""
    db = get_db()
    if db is None:
        return []
    try:
        pipeline = [
            {"$sort": {"created_at": -1}},
            {"$group": {
                "_id": "$session_id",
                "steps_count": {"$sum": 1},
                "started_at": {"$min": "$created_at"},
                "ended_at": {"$max": "$created_at"},
                "has_final": {"$max": "$is_final"},
            }},
            {"$sort": {"started_at": -1}},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "session_id": "$_id",
                "steps_count": 1,
                "started_at": 1,
                "ended_at": 1,
                "has_final": 1,
            }},
        ]
        return list(db.execution_traces.aggregate(pipeline))
    except Exception as exc:
        logger.warning(f"Failed to list sessions: {exc}")
        return []


# ---------------------------------------------------------------------------
# Destination Knowledge Base
# ---------------------------------------------------------------------------

def query_destination(destination_name: str) -> dict | None:
    """Look up a destination from the knowledge base (case-insensitive)."""
    db = get_db()
    if db is None:
        return None
    try:
        doc = db.destinations.find_one(
            {"name": {"$regex": f"^{destination_name}$", "$options": "i"}},
            {"_id": 0},
        )
        return doc
    except Exception as exc:
        logger.warning(f"Failed to query destination: {exc}")
        return None


def upsert_destination(destination_data: dict) -> bool:
    """Insert or update a destination in the knowledge base."""
    db = get_db()
    if db is None:
        return False
    try:
        name = destination_data.get("name")
        if not name:
            return False
        destination_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        db.destinations.replace_one({"name": name}, destination_data, upsert=True)
        return True
    except Exception as exc:
        logger.warning(f"Failed to upsert destination: {exc}")
        return False


def seed_sample_destinations() -> int:
    """Seed the destination knowledge base with sample data. Returns count inserted."""
    db = get_db()
    if db is None:
        return 0

    sample_destinations = [
        {
            "name": "Lisbon, Portugal",
            "country": "Portugal",
            "continent": "Europe",
            "currency": "EUR",
            "avg_hotel_per_night": {"budget": 35, "mid": 75, "luxury": 180},
            "avg_meal_cost": {"budget": 8, "mid": 18, "fine_dining": 50},
            "avg_daily_transit": 8,
            "top_attractions": [
                {"name": "Belém Tower", "entry_fee": 8, "type": "history"},
                {"name": "Jerónimos Monastery", "entry_fee": 10, "type": "architecture"},
                {"name": "Alfama District", "entry_fee": 0, "type": "neighborhood"},
                {"name": "Time Out Market", "entry_fee": 0, "type": "food"},
                {"name": "Miradouro da Graça", "entry_fee": 0, "type": "viewpoint"},
            ],
            "best_months": ["March", "April", "May", "September", "October"],
            "avg_roundtrip_flight": {"from_US_east": 450, "from_US_west": 550, "from_UK": 120},
        },
        {
            "name": "Tokyo, Japan",
            "country": "Japan",
            "continent": "Asia",
            "currency": "JPY",
            "avg_hotel_per_night": {"budget": 40, "mid": 110, "luxury": 350},
            "avg_meal_cost": {"budget": 10, "mid": 25, "fine_dining": 80},
            "avg_daily_transit": 12,
            "top_attractions": [
                {"name": "Senso-ji Temple", "entry_fee": 0, "type": "history"},
                {"name": "Meiji Shrine", "entry_fee": 0, "type": "history"},
                {"name": "Tokyo Skytree", "entry_fee": 12, "type": "viewpoint"},
                {"name": "Shibuya Crossing", "entry_fee": 0, "type": "landmark"},
                {"name": "teamLab Borderless", "entry_fee": 20, "type": "art"},
            ],
            "best_months": ["March", "April", "October", "November"],
            "avg_roundtrip_flight": {"from_US_east": 750, "from_US_west": 550, "from_UK": 500},
        },
        {
            "name": "Paris, France",
            "country": "France",
            "continent": "Europe",
            "currency": "EUR",
            "avg_hotel_per_night": {"budget": 50, "mid": 120, "luxury": 400},
            "avg_meal_cost": {"budget": 12, "mid": 25, "fine_dining": 80},
            "avg_daily_transit": 10,
            "top_attractions": [
                {"name": "Eiffel Tower", "entry_fee": 18, "type": "landmark"},
                {"name": "Louvre Museum", "entry_fee": 17, "type": "art"},
                {"name": "Notre-Dame", "entry_fee": 0, "type": "architecture"},
                {"name": "Sacré-Cœur", "entry_fee": 0, "type": "viewpoint"},
                {"name": "Musée d'Orsay", "entry_fee": 16, "type": "art"},
            ],
            "best_months": ["April", "May", "June", "September", "October"],
            "avg_roundtrip_flight": {"from_US_east": 400, "from_US_west": 500, "from_UK": 80},
        },
        {
            "name": "Bangkok, Thailand",
            "country": "Thailand",
            "continent": "Asia",
            "currency": "THB",
            "avg_hotel_per_night": {"budget": 15, "mid": 45, "luxury": 150},
            "avg_meal_cost": {"budget": 3, "mid": 10, "fine_dining": 35},
            "avg_daily_transit": 5,
            "top_attractions": [
                {"name": "Grand Palace", "entry_fee": 15, "type": "history"},
                {"name": "Wat Pho", "entry_fee": 7, "type": "history"},
                {"name": "Chatuchak Market", "entry_fee": 0, "type": "shopping"},
                {"name": "Khao San Road", "entry_fee": 0, "type": "nightlife"},
                {"name": "Wat Arun", "entry_fee": 2, "type": "architecture"},
            ],
            "best_months": ["November", "December", "January", "February"],
            "avg_roundtrip_flight": {"from_US_east": 650, "from_US_west": 500, "from_UK": 400},
        },
        {
            "name": "Rome, Italy",
            "country": "Italy",
            "continent": "Europe",
            "currency": "EUR",
            "avg_hotel_per_night": {"budget": 40, "mid": 100, "luxury": 300},
            "avg_meal_cost": {"budget": 10, "mid": 20, "fine_dining": 60},
            "avg_daily_transit": 8,
            "top_attractions": [
                {"name": "Colosseum", "entry_fee": 16, "type": "history"},
                {"name": "Vatican Museums", "entry_fee": 17, "type": "art"},
                {"name": "Pantheon", "entry_fee": 5, "type": "architecture"},
                {"name": "Trevi Fountain", "entry_fee": 0, "type": "landmark"},
                {"name": "Roman Forum", "entry_fee": 16, "type": "history"},
            ],
            "best_months": ["April", "May", "September", "October"],
            "avg_roundtrip_flight": {"from_US_east": 420, "from_US_west": 520, "from_UK": 90},
        },
    ]

    count = 0
    for dest in sample_destinations:
        if upsert_destination(dest):
            count += 1
    if count:
        logger.info(f"Seeded {count} sample destinations into knowledge base")
    return count


# ---------------------------------------------------------------------------
# Database Status
# ---------------------------------------------------------------------------

def db_status() -> dict[str, Any]:
    """Return database connection status and collection counts."""
    connected = is_mongo_connected()
    result: dict[str, Any] = {
        "connected": connected,
        "backend": "mongodb" if connected else "local_json",
    }
    if connected and _db is not None:
        try:
            result["collections"] = {
                "travel_profiles": _db.travel_profiles.count_documents({}),
                "itineraries": _db.itineraries.count_documents({}),
                "execution_traces": _db.execution_traces.count_documents({}),
                "destinations": _db.destinations.count_documents({}),
            }
        except Exception as exc:
            result["collections_error"] = str(exc)
    return result
