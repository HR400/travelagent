# DESIGN.md: Dynamic Graph & Budget Re-allocation Architecture

## 1. System Overview
The `travelagent` application combines an interactive visual node-graph interface with a bare-metal ReAct execution engine and a programmatic budget observer. The UI visualizes daily itineraries as connected spatial-temporal nodes, allowing users to inspect location metrics, calculate relative distances, and manually inject custom destinations. Any manual insertion triggers an automated budget re-allocation waterfall managed by the Python state observer.

---

## 2. Technical Stack & Component Mapping

| Layer | Technology | Primary Function |
| --- | --- | --- |
| **Frontend Canvas** | Streamlit + `streamlit-agraph` (or `@xyflow/react`) | Node-graph rendering, day clustering, click event handlers, and inspector drawer. |
| **Spatial Engine** | Python `geopy` (Haversine formula in `tools/distance.py`) | Calculates node-to-hotel and node-to-node relative distances. |
| **ReAct Engine** | `engine.py` (Custom ReAct loop) | Multi-step reasoning, query mutation, and fallback tool dispatching. |
| **Budget Observer** | `core/observer.py` / `state_manager.py` | Programmatic verification enforcing the $800 total budget invariant. |

---

## 3. Data Schemas

### 3.1 Node Object (`NodeJSON`)
```json
{
  "id": "node_day2_act1",
  "day": 2,
  "type": "activity",
  "title": "Park Güell",
  "intro": "Iconic park system featuring colorful mosaics and architectural works by Antoni Gaudí.",
  "cost": 18.00,
  "coordinates": {"lat": 41.4145, "lng": 2.1527},
  "spatial_context": {
    "distance_from_hotel_km": 4.2,
    "distance_from_prev_node_km": 1.8,
    "prev_node_id": "node_day2_lunch"
  },
  "is_user_added": false
}
```

### 3.2 Edge Object (`EdgeJSON`)
```json
{
  "id": "edge_day2_lunch_to_act1",
  "source": "node_day2_lunch",
  "target": "node_day2_act1",
  "label": "1.8 km (22 min walk)",
  "travel_time_mins": 22,
  "transport_mode": "walking"
}
```

### 3.3 Trip State (`TripStateJSON`)
```json
{
  "trip_name": "Lisbon Exploration",
  "budget_cap": 800.00,
  "current_total_spend": 640.50,
  "nodes": [],
  "edges": []
}
```

---

## 4. Visual UI & User Interactions

### 4.1 Global Budget Summary Banner
- **Sticky Top Progress Bar**: Visualizes `current_total_spend` vs `budget_cap` ($800.00).
- **Daily Breakdown Badges**: Displays individual daily spend metrics (e.g., Day 1: $180, Day 2: $210, Day 3: $150, Day 4: $100).
- **Status Badge**: Renders state flags: `BALANCED` (Green), `RE-ALLOCATING` (Yellow), or `BUDGET EXCEEDED` (Red).

### 4.2 Interactive Node-Graph Canvas
- **Day-Clustered Layout**: Nodes organized chronologically from left to right grouped by Day columns.
- **Node Types**:
  - **Anchor Node (Hotel)**: Visual base camp for each day.
  - **Standard Node (Activity/Food)**: Scheduled items with price tags and time slots.
  - **Custom Node (User Inserted)**: Distinctly styled visual badge (`User Injected`).
- **Directional Edges**: Arrows showing travel paths between sequential activities, annotated with distance in kilometers.

### 4.3 Node Deep-Dive Drawer (On Click Event)
Clicking any graph node opens an interactive detail pane displaying:
- **Location Description**: Brief summary of the place.
- **Spatial Metrics**:
  - Distance to Hotel: $D_{hotel} = \text{Haversine}(\text{Node}, \text{Hotel})$
  - Distance to Previous Location: $D_{prev} = \text{Haversine}(\text{Node}, \text{Node}_{prev})$
- **Cost & Category Editor**: Editable input box allowing manual adjustments to item cost.
- **Action Triggers**: Delete Node or Re-plan Day around this Node.

---

## 5. Dynamic Budget Re-Allocation Protocol
When a user manually injects a new destination $N_{new}$ with cost $C_{new}$ into Day $K$:

```
┌────────────────────────────────────────────────────────┐
│             USER ADDS NODE (Name, Cost, Day)            │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│            STATE OBSERVER INVARIANT CHECK              │
│       New_Spend = Current_Spend + C_new <= $800        │
└───────────────┬────────────────────────┬───────────────┘
                │                        │
       [PASS: New_Spend <= $800]  [FAIL: New_Spend > $800]
                │                        │
                ▼                        ▼
┌───────────────────────────┐  ┌─────────────────────────┐
│ Accept Node & Re-calculate│  │ TRIGGER WATERFALL       │
│ Spatial Distances         │  │ RE-ALLOCATION ENGINE    │
└───────────────────────────┘  └─────────┬───────────────┘
                                         │
                                         ▼
                               ┌───────────────────┐
                               │ STEP 1: PRUNE DAY │
                               └─────────┬─────────┘
                                         │
                                         ▼
                               ┌───────────────────┐
                               │ STEP 2: CASCADE   │
                               └─────────┬─────────┘
                                         │
                                         ▼
                               ┌───────────────────┐
                               │ STEP 3: FALLBACK  │
                               └───────────────────┘
```

### Waterfall Resolution Steps:
1. **Step 1: Local Day Pruning**
   Search Day $K$ for non-essential, AI-generated nodes. Mutate high-cost items to cheaper alternatives (e.g., replace a $60 dinner with a $20 local market).
2. **Step 2: Global Cascade Pruning**
   If Day $K$ cannot absorb the deficit $\Delta = New\_Spend - 800$, iterate forward through Days $K+1\dots N$ to replace or trim flexible activities.
3. **Step 3: Hard Boundary Fallback**
   If budget optimization fails to absorb $\Delta$ without violating user preferences, flag $N_{new}$ with a visual warning: *"Exceeds hard budget cap by $X. Remove another activity to finalize."*

---

## 6. Development Checklist for Antigravity Agent
- [x] State Manager (`state_manager.py`): Implement `TripState` class with JSON load/save operations.
- [x] Distance Calculator (`tools/distance.py`): Implement Haversine distance calculations between node coordinate pairs.
- [x] Observer Interceptor (`core/observer.py`): Update calculation handler to execute the Waterfall protocol on state updates.
- [x] Graph UI (`app/graph_ui.py`): Implement Streamlit node canvas with click event state integration.
