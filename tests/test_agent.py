"""Automated test suite for bare-metal ReAct travel agent and budget observer."""

from __future__ import annotations

import unittest
from engine import BudgetObserver, _field, _parse_react, _dispatch, HARD_CAP
from tools import calculate, read_file


class TestTools(unittest.TestCase):
    def test_calculate_basic(self):
        self.assertEqual(calculate("100 + 200"), "300")
        self.assertEqual(calculate("5 * 80 + 150"), "550")
        self.assertEqual(calculate("500 / 2"), "250")
        self.assertEqual(calculate("2 ** 3"), "8")

    def test_calculate_with_symbols(self):
        self.assertEqual(calculate("$120 + $450"), "570")
        self.assertEqual(calculate("5 * $90.50 + $45"), "497.5")
        self.assertEqual(calculate("1,200 - 450"), "750")

    def test_calculate_invalid_expression(self):
        res = calculate("import os; os.system('echo hi')")
        self.assertTrue(res.startswith("ERROR:"))

    def test_read_file_existing(self):
        res = read_file("travel_profile.json")
        self.assertIn("Alex Rivera", res)
        self.assertIn("Lisbon, Portugal", res)

    def test_read_file_nonexistent(self):
        res = read_file("does_not_exist.json")
        self.assertTrue(res.startswith("ERROR: file not found"))

    def test_read_file_security_traversal(self):
        res = read_file("../../etc/passwd")
        self.assertTrue(res.startswith("ERROR:"))


class TestBudgetObserver(unittest.TestCase):
    def setUp(self):
        self.observer = BudgetObserver(hard_cap=800.0)

    def test_calculate_under_budget(self):
        result = self.observer.note_calculate_result("5 * 90 + 100", "550")
        self.assertIn("[BUDGET OK]", result)
        self.assertIn("550.00 is within the $800.00 cap", result)
        self.assertEqual(len(self.observer.violations), 0)

    def test_calculate_exact_boundary(self):
        result_exact = self.observer.note_calculate_result("800", "800")
        self.assertIn("[BUDGET OK]", result_exact)
        self.assertEqual(len(self.observer.violations), 0)

        result_over = self.observer.note_calculate_result("800.01", "800.01")
        self.assertIn("[BUDGET VIOLATION]", result_over)
        self.assertEqual(len(self.observer.violations), 1)

    def test_calculate_over_budget_intercepted(self):
        result = self.observer.note_calculate_result("5 * 160 + 200", "1000")
        self.assertIn("[BUDGET VIOLATION]", result)
        self.assertIn("exceeds hard cap of $800.00", result)
        self.assertEqual(len(self.observer.violations), 1)

    def test_dispatch_calculate_intercept(self):
        obs = _dispatch("calculate", "5 * 200 + 300", self.observer)
        self.assertIn("1300", obs)
        self.assertIn("[BUDGET VIOLATION]", obs)
        self.assertEqual(len(self.observer.violations), 1)

    def test_observe_text_over_budget(self):
        text = "Here is the preliminary total: $950.00 for 5 nights."
        res = self.observer.observe_text(text)
        self.assertIn("[BUDGET VIOLATION]", res)
        self.assertIn("Reported total $950.00 exceeds hard cap", res)

    def test_observe_text_with_commas(self):
        text = "Grand Total: $1,250.00 for luxury stay."
        res = self.observer.observe_text(text)
        self.assertIn("[BUDGET VIOLATION]", res)
        self.assertIn("$1250.00", res)

    def test_validate_final_valid(self):
        final = "Day 1-5 Itinerary...\nTotal: $740.00"
        is_valid, report = self.observer.validate_final(final)
        self.assertTrue(is_valid)

    def test_validate_final_over_budget(self):
        final = "Day 1-5 Itinerary...\nTotal: $850.00"
        is_valid, report = self.observer.validate_final(final)
        self.assertFalse(is_valid)
        self.assertIn("exceeds hard cap", report)

    def test_validate_final_summed_items_without_total_line(self):
        final = "Lodging: $400\nFlights: $300\nFood: $80\nTransit: $15"
        is_valid, report = self.observer.validate_final(final)
        self.assertTrue(is_valid)
        self.assertIn("$795.00", report)

    def test_validate_final_summed_items_exceeding_cap(self):
        final = "Lodging: $500\nFlights: $400\nFood: $100"
        is_valid, report = self.observer.validate_final(final)
        self.assertFalse(is_valid)
        self.assertIn("$1000.00", report)

    def test_enforce_final_approval(self):
        final = "Day 1-5 Plan...\nTotal: $680.00"
        enforced = self.observer.enforce_final(final)
        self.assertIn("[BUDGET OBSERVER - APPROVED]", enforced)

    def test_enforce_final_rejection(self):
        final = "Day 1-5 Plan...\nTotal: $920.00"
        enforced = self.observer.enforce_final(final)
        self.assertIn("[BUDGET OBSERVER - REJECTED]", enforced)


class TestReActParser(unittest.TestCase):
    def test_plain_parsing(self):
        text = "Thought: I need to read the file.\nAction: read_file\nAction Input: travel_profile.json"
        thought, action, action_input = _parse_react(text)
        self.assertEqual(thought, "I need to read the file.")
        self.assertEqual(action, "read_file")
        self.assertEqual(action_input, "travel_profile.json")

    def test_markdown_parsing(self):
        text = "**Thought:** Need to search web.\n**Action:** tavily_search\n**Action Input:** Lisbon hotels 2026"
        thought, action, action_input = _parse_react(text)
        self.assertEqual(thought, "Need to search web.")
        self.assertEqual(action, "tavily_search")
        self.assertEqual(action_input, "Lisbon hotels 2026")

    def test_final_answer_detection(self):
        text = "Thought: I have calculated everything.\nFinal Answer: Complete itinerary with Total: $720.00"
        thought, action, action_input = _parse_react(text)
        self.assertEqual(action, None)
        self.assertEqual(action_input, None)
        self.assertEqual(_field(text, "Final Answer"), "Complete itinerary with Total: $720.00")


if __name__ == "__main__":
    unittest.main()
