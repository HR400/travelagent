"""Interactive Node-Graph and Budget Re-allocation Canvas powered by Streamlit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is in sys.path regardless of execution directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from core.observer import BudgetObserverInterceptor, WaterfallResult
from state_manager import Coordinates, NodeJSON, TripState, seed_default_trip
from tools.distance import haversine_distance_km

st.set_page_config(
    page_title="Travel Agent — Dynamic Graph & Budget Canvas",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

STATE_FILE = Path(__file__).resolve().parent.parent / "trip_state.json"

# Initialize Session State
if "trip_state" not in st.session_state:
    st.session_state.trip_state = TripState.load_from_file(STATE_FILE)

if "selected_node_id" not in st.session_state:
    st.session_state.selected_node_id = None

if "last_waterfall_result" not in st.session_state:
    st.session_state.last_waterfall_result = None

trip: TripState = st.session_state.trip_state
trip.update_total_spend()


# Custom styling for rich modern aesthetic
st.markdown(
    """
<style>
    .main { background-color: #0b0f19; color: #f3f4f6; }
    .sticky-header {
        position: sticky;
        top: 0;
        z-index: 999;
        background: rgba(17, 24, 39, 0.95);
        backdrop-filter: blur(12px);
        padding: 1rem 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        margin-bottom: 1.5rem;
    }
    .badge {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .badge-green { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    .badge-yellow { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
    .badge-user { background: rgba(139, 92, 246, 0.25); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.6); }
    .badge-hotel { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }

    .node-card {
        background: #1e293b;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 0.85rem;
        margin-bottom: 0.75rem;
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .node-card:hover {
        transform: translateY(-2px);
        border-color: #6366f1;
    }
    .node-selected {
        border: 2px solid #818cf8 !important;
        background: #1e1b4b !important;
    }
    .edge-connector {
        display: flex;
        align-items: center;
        justify-content: center;
        color: #94a3b8;
        font-size: 0.75rem;
        font-family: monospace;
        margin: 0.25rem 0;
        padding: 0.2rem 0.5rem;
        background: rgba(255, 255, 255, 0.03);
        border-radius: 6px;
        border-left: 2px dashed #475569;
    }
</style>
""",
    unsafe_allow_html=True,
)


# ==============================================================================
# 4.1 GLOBAL BUDGET SUMMARY BANNER
# ==============================================================================
spend_ratio = min(1.0, trip.current_total_spend / trip.budget_cap) if trip.budget_cap > 0 else 0.0
pct = int(spend_ratio * 100)

status_flag = trip.get_status_flag()
if st.session_state.last_waterfall_result:
    status_flag = st.session_state.last_waterfall_result.status_flag

if status_flag == "BALANCED":
    badge_html = '<span class="badge badge-green">● BALANCED</span>'
    progress_color = "#10b981"
elif status_flag == "RE-ALLOCATING":
    badge_html = '<span class="badge badge-yellow">▲ RE-ALLOCATING</span>'
    progress_color = "#f59e0b"
else:
    badge_html = '<span class="badge badge-red">■ BUDGET EXCEEDED</span>'
    progress_color = "#ef4444"

breakdowns = trip.get_daily_breakdown()
badges_html = " ".join(
    [
        f'<span style="background: rgba(255,255,255,0.06); padding: 0.2rem 0.6rem; border-radius: 6px; font-size: 0.8rem; margin-right: 0.5rem;">'
        f'<b>Day {d}:</b> ${amt:.1f}</span>'
        for d, amt in breakdowns.items()
    ]
)

st.markdown(
    f"""
<div class="sticky-header">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
        <div>
            <span style="font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em;">🗺️ {trip.trip_name}</span>
            <span style="margin-left: 0.75rem;">{badge_html}</span>
        </div>
        <div style="font-size: 1.1rem; font-weight: 600;">
            Spend: <span style="color: {progress_color};">${trip.current_total_spend:.2f}</span> 
            <span style="color: #64748b;">/ ${trip.budget_cap:.2f} ({pct}%)</span>
        </div>
    </div>
    <div style="width: 100%; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; margin-bottom: 0.6rem;">
        <div style="width: {pct}%; height: 100%; background: {progress_color}; transition: width 0.3s ease;"></div>
    </div>
    <div style="display: flex; align-items: center; overflow-x: auto;">
        <span style="color: #94a3b8; font-size: 0.8rem; margin-right: 0.5rem; text-transform: uppercase; font-weight: 600;">Daily Spend:</span>
        {badges_html}
    </div>
</div>
""",
    unsafe_allow_html=True,
)

# Render feedback from last waterfall run
if st.session_state.last_waterfall_result:
    res: WaterfallResult = st.session_state.last_waterfall_result
    if res.status_flag == "BALANCED":
        st.success(f"✅ {res.message}")
        if res.mutations:
            with st.expander(f"Waterfall Mutations ({len(res.mutations)} item(s) adjusted)", expanded=False):
                for m in res.mutations:
                    if m.action == "mutated":
                        st.write(f"🔄 **Day {m.day}**: Mutated `{m.original_title}` (${m.original_cost:.2f}) ➔ `{m.new_title}` (${m.new_cost:.2f}) [Saved ${m.saved_amount:.2f}]")
                    else:
                        st.write(f"✂️ **Day {m.day}**: Pruned non-essential activity `{m.original_title}` [Saved ${m.saved_amount:.2f}]")
    else:
        st.error(f"⚠️ {res.warning or res.message}")


# ==============================================================================
# 4.2 INTERACTIVE NODE-GRAPH CANVAS (DAY CLUSTERED)
# ==============================================================================
col_canvas, col_drawer = st.columns([2.6, 1.4], gap="large")

with col_canvas:
    st.subheader("Interactive Day-Clustered Topology")
    st.caption("Chronological itinerary graph with spatial-temporal edge travel metrics. Click any node to open the inspector drawer.")

    days = sorted(list({n.day for n in trip.nodes}))
    if not days:
        days = [1]

    day_cols = st.columns(len(days), gap="medium")

    for idx, day_num in enumerate(days):
        with day_cols[idx]:
            day_spend = breakdowns.get(day_num, 0.0)
            st.markdown(
                f"""
            <div style="background: rgba(255,255,255,0.04); padding: 0.5rem 0.75rem; border-radius: 8px; text-align: center; margin-bottom: 0.75rem; border-top: 3px solid #6366f1;">
                <div style="font-weight: 700; font-size: 1rem;">Day {day_num}</div>
                <div style="font-size: 0.8rem; color: #94a3b8;">${day_spend:.2f}</div>
            </div>
            """,
                unsafe_allow_html=True,
            )

            day_nodes = trip.get_nodes_for_day(day_num)
            for n_idx, node in enumerate(day_nodes):
                is_selected = st.session_state.selected_node_id == node.id

                # Badge markup
                if node.is_user_added:
                    type_badge = '<span class="badge badge-user">User Injected</span>'
                elif node.type == "hotel":
                    type_badge = '<span class="badge badge-hotel">Basecamp Hotel</span>'
                elif node.type == "food":
                    type_badge = '<span class="badge" style="background:#065f46; color:#6ee7b7;">Food</span>'
                else:
                    type_badge = '<span class="badge" style="background:#3730a3; color:#a5b4fc;">Activity</span>'

                # Button to select node
                card_label = f"{'⭐ ' if node.is_user_added else ''}{node.title} (${node.cost:.2f})"
                btn_type = "primary" if is_selected else "secondary"

                if st.button(card_label, key=f"btn_node_{node.id}", type=btn_type, use_container_width=True):
                    st.session_state.selected_node_id = node.id
                    st.rerun()

                # Edge annotation to next node if available
                if n_idx < len(day_nodes) - 1:
                    next_node = day_nodes[n_idx + 1]
                    edge = next((e for e in trip.edges if e.source == node.id and e.target == next_node.id), None)
                    label_text = edge.label if edge else "➔ connected"
                    st.markdown(f'<div class="edge-connector">⬇ {label_text}</div>', unsafe_allow_html=True)


# ==============================================================================
# 4.3 NODE DEEP-DIVE DRAWER & RE-ALLOCATION FORM
# ==============================================================================
with col_drawer:
    selected_node = trip.get_node(st.session_state.selected_node_id) if st.session_state.selected_node_id else None

    if selected_node:
        st.markdown(
            f"""
        <div style="background: #111827; border: 1px solid #374151; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                <span class="badge {'badge-user' if selected_node.is_user_added else 'badge-hotel' if selected_node.type == 'hotel' else 'badge-green'}">
                    {'USER CUSTOM' if selected_node.is_user_added else selected_node.type.upper()}
                </span>
                <span style="font-size: 1.2rem; font-weight: 700; color: #38bdf8;">${selected_node.cost:.2f}</span>
            </div>
            <h3 style="margin: 0.2rem 0; font-size: 1.15rem;">{selected_node.title}</h3>
            <p style="color: #94a3b8; font-size: 0.85rem; line-height: 1.4; margin-top: 0.4rem;">{selected_node.intro}</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

        st.subheader("Spatial Metrics")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric(
                label="D_hotel (To Basecamp)",
                value=f"{selected_node.spatial_context.distance_from_hotel_km:.2f} km",
            )
        with col_m2:
            st.metric(
                label="D_prev (Previous Stop)",
                value=f"{selected_node.spatial_context.distance_from_prev_node_km:.2f} km",
            )

        st.markdown("---")
        st.subheader("Edit Node")
        with st.form(key=f"edit_node_form_{selected_node.id}"):
            new_title = st.text_input("Title", value=selected_node.title)
            new_intro = st.text_area("Location Description", value=selected_node.intro, height=70)
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                new_cost = st.number_input("Cost ($)", value=float(selected_node.cost), min_value=0.0, step=1.0)
            with col_e2:
                new_day = st.number_input("Day", value=int(selected_node.day), min_value=1, max_value=7, step=1)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                submit_edit = st.form_submit_button("💾 Save Changes", use_container_width=True)

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("🗑️ Delete Node", key=f"del_{selected_node.id}", use_container_width=True):
                trip.remove_node(selected_node.id)
                trip.save_to_file(STATE_FILE)
                st.session_state.selected_node_id = None
                st.session_state.last_waterfall_result = None
                st.success("Node deleted.")
                st.rerun()

        with col_act2:
            if st.button("🔄 Re-plan Day", key=f"replan_{selected_node.id}", use_container_width=True):
                trip.recalculate_day_spatial_metrics(selected_node.day)
                trip.save_to_file(STATE_FILE)
                st.info(f"Re-aligned spatial path for Day {selected_node.day}.")
                st.rerun()

        if submit_edit:
            trip.update_node(
                selected_node.id,
                {"title": new_title, "intro": new_intro, "cost": new_cost, "day": new_day},
            )
            trip.save_to_file(STATE_FILE)
            st.success("Node updated successfully.")
            st.rerun()

    else:
        st.info("👈 Select any node on the left to view spatial metrics, edit costs, or delete.")

    # -------------------------------------------------------------
    # 5. DYNAMIC BUDGET INJECTION FORM
    # -------------------------------------------------------------
    st.markdown("---")
    st.subheader("➕ Inject Custom Destination")
    st.caption("Manually inject a custom destination. Triggers the automated 3-Step Waterfall Re-allocation protocol.")

    with st.form(key="inject_custom_node_form"):
        inj_title = st.text_input("Destination Title", value="Miradouro da Senhora do Monte")
        inj_intro = st.text_input("Description", value="Highest panoramic lookout point in Lisbon with sunset view.")
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            inj_cost = st.number_input("Cost ($)", value=25.0, min_value=0.0, step=5.0)
        with col_i2:
            inj_day = st.number_input("Target Day", value=2, min_value=1, max_value=5, step=1)

        # Coordinate presets or custom inputs
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            inj_lat = st.number_input("Latitude", value=38.7191, format="%.4f")
        with col_c2:
            inj_lng = st.number_input("Longitude", value=-9.1328, format="%.4f")

        submit_inject = st.form_submit_button("🚀 Inject Destination (Waterfall Engine)", use_container_width=True)

        if submit_inject:
            new_id = f"custom_day{inj_day}_{len(trip.nodes) + 1}"
            custom_node = NodeJSON(
                id=new_id,
                day=inj_day,
                type="custom",
                title=inj_title,
                intro=inj_intro,
                cost=inj_cost,
                coordinates=Coordinates(inj_lat, inj_lng),
                is_user_added=True,
            )

            observer = BudgetObserverInterceptor(hard_cap=trip.budget_cap)
            mutated_state, wf_result = observer.on_user_node_injected(trip, custom_node, target_day=inj_day)

            st.session_state.trip_state = mutated_state
            st.session_state.last_waterfall_result = wf_result
            st.session_state.selected_node_id = custom_node.id
            mutated_state.save_to_file(STATE_FILE)
            st.rerun()

    # Reset option
    st.markdown("---")
    if st.button("🔄 Reset to Default Lisbon Trip State", use_container_width=True):
        st.session_state.trip_state = seed_default_trip()
        st.session_state.trip_state.save_to_file(STATE_FILE)
        st.session_state.selected_node_id = None
        st.session_state.last_waterfall_result = None
        st.rerun()
