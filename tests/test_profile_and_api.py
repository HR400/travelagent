"""Tests for profile management, dynamic budget limits, and API utilities."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from engine import BudgetObserver, get_system_prompt
from serve import get_profile, save_profile, PROFILE_PATH


class TestProfileManagement(unittest.TestCase):
    def setUp(self):
        self.original_content = PROFILE_PATH.read_text(encoding="utf-8") if PROFILE_PATH.exists() else None

    def tearDown(self):
        if self.original_content:
            PROFILE_PATH.write_text(self.original_content, encoding="utf-8")

    def test_get_profile_structure(self):
        profile = get_profile()
        self.assertIn("traveler", profile)
        self.assertIn("trip", profile)
        self.assertIn("budget", profile)
        self.assertIn("preferences", profile)

    def test_save_and_retrieve_custom_profile(self):
        custom_data = {
            "traveler": {"name": "Test Traveler", "origin": "Boston, MA", "party_size": 2},
            "trip": {"destination": "Rome, Italy", "start_date": "2026-09-01", "end_date": "2026-09-07", "nights": 6},
            "budget": {"currency": "USD", "hard_cap": 1500, "rule": "Total <= 1500"},
            "preferences": {
                "pace": "fast-paced",
                "lodging": "boutique hotel",
                "interests": ["art", "history"],
                "dietary": ["gluten-free"],
                "avoid": ["buses"],
            },
        }
        saved = save_profile(custom_data)
        self.assertEqual(saved["traveler"]["name"], "Test Traveler")
        self.assertEqual(saved["budget"]["hard_cap"], 1500.0)
        self.assertEqual(saved["trip"]["destination"], "Rome, Italy")

        reloaded = get_profile()
        self.assertEqual(reloaded["traveler"]["name"], "Test Traveler")
        self.assertEqual(reloaded["budget"]["hard_cap"], 1500.0)


class TestDynamicBudgetObserver(unittest.TestCase):
    def test_custom_hard_cap_approval(self):
        observer = BudgetObserver(hard_cap=1200.0)
        result = observer.note_calculate_result("600 + 400 + 150", "1150")
        self.assertIn("[BUDGET OK]", result)
        self.assertIn("1150.00 is within the $1200.00 cap", result)
        self.assertEqual(len(observer.violations), 0)

    def test_custom_hard_cap_rejection(self):
        observer = BudgetObserver(hard_cap=1200.0)
        result = observer.note_calculate_result("800 + 500", "1300")
        self.assertIn("[BUDGET VIOLATION]", result)
        self.assertIn("exceeds hard cap of $1200.00", result)
        self.assertEqual(len(observer.violations), 1)

    def test_custom_system_prompt(self):
        prompt = get_system_prompt(1500.0)
        self.assertIn("$1500.00", prompt)
        self.assertNotIn("$800.00", prompt)


if __name__ == "__main__":
    unittest.main()
