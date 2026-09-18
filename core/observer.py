"""Core Observer: Programmatic budget verification and 3-Step Waterfall Re-allocation Protocol."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from state_manager import NodeJSON, TripState

# Budget hard cap default invariant
DEFAULT_HARD_CAP = 800.00

# Cheaper substitution heuristics for Lisbon & urban travel
BUDGET_SUBSTITUTIONS = {
    "food_high": {
        "title": "Mercado da Ribeira / Street Food Stall",
        "intro": "Casual gourmet petiscos and local sandwiches at a fraction of sit-down tavern prices.",
        "cost": 10.00,
    },
    "food_mid": {
        "title": "Neighborhood Tasca (Prato do Dia)",
        "intro": "Generous daily lunch special featuring grilled fish, soup, bread, and espresso.",
        "cost": 8.50,
    },
    "activity_high": {
        "title": "Free Walking Route & Miradouros",
        "intro": "Panoramic self-guided walking route covering historic viewpoints and street art without admission fees.",
        "cost": 0.00,
    },
    "activity_mid": {
        "title": "Municipal Cultural Center & Public Gardens",
        "intro": "Free public access botanical grounds and open sculpture garden.",
        "cost": 0.00,
    },
}


@dataclass
class MutationRecord:
    action: str  # "mutated" | "pruned"
    day: int
    node_id: str
    original_title: str
    original_cost: float
    new_title: Optional[str] = None
    new_cost: float = 0.0
    saved_amount: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "day": self.day,
            "node_id": self.node_id,
            "original_title": self.original_title,
            "original_cost": round(self.original_cost, 2),
            "new_title": self.new_title,
            "new_cost": round(self.new_cost, 2),
            "saved_amount": round(self.saved_amount, 2),
        }


@dataclass
class WaterfallResult:
    success: bool
    status_flag: str  # "BALANCED" | "RE-ALLOCATING" | "BUDGET EXCEEDED"
    injected_node_id: str
    target_day: int
    original_spend: float
    projected_spend: float
    final_spend: float
    deficit: float
    absorbed_amount: float
    mutations: List[MutationRecord] = field(default_factory=list)
    warning: Optional[str] = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status_flag": self.status_flag,
            "injected_node_id": self.injected_node_id,
            "target_day": self.target_day,
            "original_spend": round(self.original_spend, 2),
            "projected_spend": round(self.projected_spend, 2),
            "final_spend": round(self.final_spend, 2),
            "deficit": round(self.deficit, 2),
            "absorbed_amount": round(self.absorbed_amount, 2),
            "mutations": [m.to_dict() for m in self.mutations],
            "warning": self.warning,
            "message": self.message,
        }


class WaterfallEngine:
    """Implements the 3-step Waterfall Protocol for dynamic budget re-allocation."""

    def __init__(self, budget_cap: float = DEFAULT_HARD_CAP):
        self.budget_cap = float(budget_cap)

    def execute(
        self,
        trip_state: TripState,
        new_node: NodeJSON,
        target_day: Optional[int] = None,
    ) -> Tuple[TripState, WaterfallResult]:
        """Execute the Waterfall Re-allocation protocol when a user injects a new node."""
        if target_day is not None:
            new_node.day = target_day
        else:
            target_day = new_node.day

        new_node.is_user_added = True

        original_spend = trip_state.update_total_spend()
        projected_spend = original_spend + new_node.cost

        # Case 1: Invariant satisfied immediately
        if projected_spend <= self.budget_cap:
            trip_state.add_node(new_node, recompute_edges=True)
            result = WaterfallResult(
                success=True,
                status_flag="BALANCED",
                injected_node_id=new_node.id,
                target_day=target_day,
                original_spend=original_spend,
                projected_spend=projected_spend,
                final_spend=trip_state.current_total_spend,
                deficit=0.0,
                absorbed_amount=0.0,
                message=f"Node '{new_node.title}' accepted into Day {target_day}. Budget is balanced at ${trip_state.current_total_spend:.2f} <= ${self.budget_cap:.2f}.",
            )
            return trip_state, result

        # Case 2: Invariant violated -> Trigger Waterfall
        initial_deficit = projected_spend - self.budget_cap
        remaining_deficit = initial_deficit
        mutations: List[MutationRecord] = []

        # Temporarily add node so day graph has full context
        trip_state.add_node(new_node, recompute_edges=False)

        # -------------------------------------------------------------
        # STEP 1: LOCAL DAY PRUNING
        # Search Day K for non-essential, AI-generated nodes
        # Mutate high-cost items to cheaper alternatives
        # -------------------------------------------------------------
        day_nodes = [
            n
            for n in trip_state.get_nodes_for_day(target_day)
            if not n.is_user_added and n.type != "hotel" and n.id != new_node.id
        ]
        # Sort by cost descending (prune/mutate largest expenses first)
        day_nodes.sort(key=lambda x: x.cost, reverse=True)

        for candidate in day_nodes:
            if remaining_deficit <= 0.01:
                break

            saved = self._attempt_mutate_or_prune(trip_state, candidate, remaining_deficit, mutations)
            remaining_deficit -= saved

        # -------------------------------------------------------------
        # STEP 2: GLOBAL CASCADE PRUNING
        # If Day K cannot absorb the deficit, cascade to Days K+1 ... N
        # -------------------------------------------------------------
        if remaining_deficit > 0.01:
            all_days = sorted({n.day for n in trip_state.nodes if n.day > target_day})
            for future_day in all_days:
                if remaining_deficit <= 0.01:
                    break

                future_candidates = [
                    n
                    for n in trip_state.get_nodes_for_day(future_day)
                    if not n.is_user_added and n.type != "hotel" and n.id != new_node.id
                ]
                future_candidates.sort(key=lambda x: x.cost, reverse=True)

                for candidate in future_candidates:
                    if remaining_deficit <= 0.01:
                        break
                    saved = self._attempt_mutate_or_prune(trip_state, candidate, remaining_deficit, mutations)
                    remaining_deficit -= saved

        # Also check earlier days if later days didn't fully absorb it
        if remaining_deficit > 0.01:
            earlier_days = sorted({n.day for n in trip_state.nodes if n.day < target_day}, reverse=True)
            for prev_day in earlier_days:
                if remaining_deficit <= 0.01:
                    break
                prev_candidates = [
                    n
                    for n in trip_state.get_nodes_for_day(prev_day)
                    if not n.is_user_added and n.type != "hotel" and n.id != new_node.id
                ]
                prev_candidates.sort(key=lambda x: x.cost, reverse=True)
                for candidate in prev_candidates:
                    if remaining_deficit <= 0.01:
                        break
                    saved = self._attempt_mutate_or_prune(trip_state, candidate, remaining_deficit, mutations)
                    remaining_deficit -= saved

        trip_state.recalculate_all_spatial_metrics()
        final_spend = trip_state.update_total_spend()
        absorbed_total = initial_deficit - max(0.0, remaining_deficit)

        # -------------------------------------------------------------
        # STEP 3: HARD BOUNDARY FALLBACK
        # If budget optimization fails to absorb deficit without violating
        # user preferences, flag with visual warning
        # -------------------------------------------------------------
        if remaining_deficit > 0.01:
            warning_msg = f"Exceeds hard budget cap by ${remaining_deficit:.2f}. Remove another activity to finalize."
            new_node.intro = f"[WARNING: {warning_msg}] " + new_node.intro

            result = WaterfallResult(
                success=False,
                status_flag="BUDGET EXCEEDED",
                injected_node_id=new_node.id,
                target_day=target_day,
                original_spend=original_spend,
                projected_spend=projected_spend,
                final_spend=final_spend,
                deficit=initial_deficit,
                absorbed_amount=absorbed_total,
                mutations=mutations,
                warning=warning_msg,
                message=f"Waterfall protocol could not absorb full deficit. {warning_msg}",
            )
            return trip_state, result

        # Re-allocation succeeded
        result = WaterfallResult(
            success=True,
            status_flag="BALANCED",
            injected_node_id=new_node.id,
            target_day=target_day,
            original_spend=original_spend,
            projected_spend=projected_spend,
            final_spend=final_spend,
            deficit=initial_deficit,
            absorbed_amount=absorbed_total,
            mutations=mutations,
            message=f"Waterfall successfully re-allocated ${absorbed_total:.2f} across {len(mutations)} item(s). Budget is balanced at ${final_spend:.2f}.",
        )
        return trip_state, result

    def _attempt_mutate_or_prune(
        self,
        trip_state: TripState,
        candidate: NodeJSON,
        deficit_needed: float,
        mutations: List[MutationRecord],
    ) -> float:
        """Attempt to replace candidate with a cheaper alternative, or prune it if mutation is insufficient."""
        orig_cost = candidate.cost
        orig_title = candidate.title

        # Check if we can substitute
        sub = None
        if candidate.type == "food":
            sub = BUDGET_SUBSTITUTIONS["food_high"] if orig_cost > 20 else BUDGET_SUBSTITUTIONS["food_mid"]
        elif candidate.type == "activity":
            sub = BUDGET_SUBSTITUTIONS["activity_high"] if orig_cost > 15 else BUDGET_SUBSTITUTIONS["activity_mid"]

        if sub and sub["cost"] < orig_cost:
            potential_saving = orig_cost - sub["cost"]
            # If substitution helps
            if potential_saving > 0:
                candidate.title = f"{sub['title']} (Budget Alt)"
                candidate.intro = sub["intro"]
                candidate.cost = sub["cost"]
                mutations.append(
                    MutationRecord(
                        action="mutated",
                        day=candidate.day,
                        node_id=candidate.id,
                        original_title=orig_title,
                        original_cost=orig_cost,
                        new_title=candidate.title,
                        new_cost=candidate.cost,
                        saved_amount=potential_saving,
                    )
                )
                return potential_saving

        # If substitution was not available or didn't save enough and candidate is an activity, prune it
        if candidate.type == "activity" and orig_cost > 0:
            trip_state.remove_node(candidate.id, recompute_edges=False)
            mutations.append(
                MutationRecord(
                    action="pruned",
                    day=candidate.day,
                    node_id=candidate.id,
                    original_title=orig_title,
                    original_cost=orig_cost,
                    new_title=None,
                    new_cost=0.0,
                    saved_amount=orig_cost,
                )
            )
            return orig_cost

        return 0.0


# Interceptor facade adhering to core observer contract
class BudgetObserverInterceptor:
    """Observer Interceptor coordinating state updates with the Waterfall Protocol."""

    def __init__(self, hard_cap: float = DEFAULT_HARD_CAP):
        self.hard_cap = hard_cap
        self.waterfall = WaterfallEngine(budget_cap=hard_cap)

    def on_user_node_injected(
        self, trip_state: TripState, node: NodeJSON | dict, target_day: Optional[int] = None
    ) -> Tuple[TripState, WaterfallResult]:
        """Triggered whenever a user injects a custom destination into the itinerary graph."""
        if isinstance(node, dict):
            node_obj = NodeJSON.from_dict(node)
        else:
            node_obj = node
        return self.waterfall.execute(trip_state, node_obj, target_day=target_day)
