import streamlit as st
import pandas as pd
import random
import os
from pathlib import Path

# Folder that holds ALL your CSV tables, like:
# data/diffuculty_modifiers.csv, data/one_crew_encounter.csv, etc.
DATA_DIR = Path(".")


def ensure_state():
    """Make sure persistent + log structures exist."""
    if "persistent" not in st.session_state:
        st.session_state["persistent"] = {}
    if "log" not in st.session_state:
        st.session_state["log"] = []


def add_to_persistent(group_id, text):
    """Store a text entry in a numbered persistent pool."""
    if group_id is None:
        return
    ensure_state()
    if group_id not in st.session_state["persistent"]:
        st.session_state["persistent"][group_id] = []
    st.session_state["persistent"][group_id].append(text)


def add_to_log(text):
    """Append a line to the global mission log."""
    ensure_state()
    st.session_state["log"].append(text)


def load_table_df(table_name: str) -> pd.DataFrame:
    """Load a CSV for a given table name."""
    path = DATA_DIR / f"{table_name}.csv"
    return pd.read_csv(path)


def format_row_for_display(table_name: str, row: pd.Series) -> str:
    """
    Turn a CSV row into a nice human-readable string.

    We ignore 'difficulty' and 'creature_type' (used for filtering)
    and combine the remaining columns.
    """
    ignore_cols = {"difficulty", "creature_type"}
    cols = [c for c in row.index if c not in ignore_cols]

    parts = []

    # Safely gather existing columns
    for col in cols:
        if col in row:
            value = row[col]
            if pd.notna(value):
                parts.append(str(value))

    if parts:
        return " – ".join(parts)

    # Fallback: show the entire row if formatting fails
    return " – ".join(
        str(v) for v in row.values 
        if pd.notna(v)
    )

def roll_table(table_name: str, group=None, log=False, option=None) -> str:
    ensure_state()

    try:
        df = load_table_df(table_name)
    except FileNotFoundError:
        result = f"[ERROR] CSV for '{table_name}' not found."
        return result

    # Apply option filters
    if option is not None:
        if "difficulty" in df.columns:
            df = df[df["difficulty"] == option]
        elif "creature_type" in df.columns:
            df = df[df["creature_type"] == option]

    if df.empty:
        result = f"[ERROR] No rows found for '{table_name}' with option '{option}'."
    else:
        row = df.sample(1).iloc[0]
        text = format_row_for_display(table_name, row)
        result = text

    if group is not None:
        add_to_persistent(group, result)
    if log:
        add_to_log(f"{table_name}: {result}")

    return result

def roll_hacking(flags: list[str]) -> str:
    """
    Implements full hacking mechanics (auto-rolled difficulty).
    Difficulty = random 1–6.
    Flags:
        - "SuccessfulRoll" → 1 reroll
        - "Cypher" → 1 reroll
        - "BlackCypher" → 2 rerolls
    Hacking succeeds if after using rerolls no dice are a 1.
    """

    ensure_state()

    import random

    # ---------------------------------------
    # 1) Auto-roll the system's difficulty (1 to 6)
    # ---------------------------------------
    difficulty = random.randint(1, 6)

    # ---------------------------------------
    # 2) Roll difficulty number of d6
    # ---------------------------------------
    rolls = [random.randint(1, 6) for _ in range(difficulty)]

    # ---------------------------------------
    # 3) Determine rerolls from flags
    # ---------------------------------------
    rerolls = 0
    if "SuccessfulRoll" in flags:
        rerolls += 1
    if "Cypher" in flags:
        rerolls += 1
    if "BlackCypher" in flags:
        rerolls += 2

    original_rolls = rolls.copy()

    # ---------------------------------------
    # 4) Apply rerolls to any 1’s
    # ---------------------------------------
    for i in range(len(rolls)):
        if rolls[i] == 1 and rerolls > 0:
            rolls[i] = random.randint(1, 6)
            rerolls -= 1

    # ---------------------------------------
    # 5) Determine success or failure
    # ---------------------------------------
    success = all(r != 1 for r in rolls)

    # ---------------------------------------
    # 6) Build summary text
    # ---------------------------------------
    text = []
    text.append(f"Hacking Difficulty: **{difficulty}**")
    text.append(f"Original Rolls: {original_rolls}")
    text.append(f"Final Rolls: {rolls}")

    spent = sum(1 for r in original_rolls if r == 1) - sum(1 for r in rolls if r == 1)
    if spent < 0: spent = 0  # safety

    text.append(f"Rerolls Used: **{spent}**")

    if success:
        text.append("🟢 **Success! System unlocked.**")
    else:
        text.append("🔴 **Failure! System locks.**")

    text.append(f"Time Required: **{difficulty} rounds**")

    result = "\n".join(text)

    # ---------------------------------------
    # Log result (mission log)
    # ---------------------------------------
    add_to_log(result)

    return result

# ---------- CONFIG ----------
st.set_page_config(page_title="Across a Thousand Dead Worlds – Generator", layout="wide")

# ---------- SESSION STATE SETUP ----------
if "persistent" not in st.session_state:
    st.session_state["persistent"] = {}  # stores temporary results by group number

if "log" not in st.session_state:
    st.session_state["log"] = []  # stores mission log entries

# ---------- BASIC UTILITIES ----------
def add_to_persistent(group_id, result):
    """Add generated data to a persistent pool (kept between tab switches)."""
    if group_id not in st.session_state["persistent"]:
        st.session_state["persistent"][group_id] = []
    st.session_state["persistent"][group_id].append(result)

def add_to_log(result):
    """Add generated data to the mission log."""
    st.session_state["log"].append(result)

def clear_persistent(group_id):
    """Clear one persistent data pool."""
    if group_id in st.session_state["persistent"]:
        st.session_state["persistent"][group_id] = []

# ---------- DEFINE PRIMARY TABS ----------
tab_labels = [
    "Encounter", "Health", "Mission", "Exploration",
    "Planet", "NPC", "Antagonist", "Return to Base", "Log"
]

tabs = st.tabs(tab_labels)

# ---------- TAB: ENCOUNTER ----------
with tabs[0]:

    st.header("Encounter Tables")

    ensure_state()

    # LEFT / RIGHT COLUMN SETUP
    col_left, col_right = st.columns(2)

    # ======= LEFT COLUMN BOXES =======

    # Difficulty Modifiers
    with col_left.container(border=True):
        if st.button("Roll Difficulty Modifiers", key="btn_diffmod"):
            st.success(roll_table("diffuculty_modifiers"))

    # Surprise
    with col_left.container(border=True):
        if st.button("Roll Surprise", key="btn_surprise"):
            st.success(roll_table("surprise"))

    # Encounter Activity
    with col_left.container(border=True):
        if st.button("Roll Encounter Activity", key="btn_enc_act"):
            st.success(roll_table("encounter_activity"))

    # Combat Stance
    with col_left.container(border=True):
        if st.button("Roll Combat Stance", key="btn_cstance"):
            st.success(roll_table("combat_stance"))

    # Hit Locations — Boxed with Creature Shape selector
    with col_left.container(border=True):
        st.markdown("### Hit Locations")
        hitloc_opt = st.selectbox(
            "Creature Shape",
            ["Humanoid", "Quadruped", "Sextuped", "Serpentine"],
            key="hitloc_type",
        )
        if st.button("Roll Hit Locations", key="btn_hitloc"):
            st.success(roll_table("hit_locations", option=hitloc_opt))

    # Random Direction
    with col_left.container(border=True):
        if st.button("Roll Random Direction", key="btn_randir"):
            st.success(roll_table("random_direction"))

    # Critical Miss – Melee
    with col_left.container(border=True):
        if st.button("Roll Critical Miss – Melee", key="btn_cmm"):
            st.success(roll_table("critical_miss_melee"))

    # ======= RIGHT COLUMN BOXES =======

    # Targeting
    with col_right.container(border=True):
        if st.button("Roll Targeting", key="btn_targeting"):
            st.success(roll_table("targeting"))

    # Critical Miss – Ranged
    with col_right.container(border=True):
        if st.button("Roll Critical Miss – Ranged", key="btn_cmr"):
            st.success(roll_table("critical_miss_ranged"))

    # Random Combat Event
    with col_right.container(border=True):
        if st.button("Roll Random Combat Event", key="btn_rce"):
            st.success(roll_table("random_combat_event"))

    # Hacking — Boxed with checkboxes
    with col_right.container(border=True):
        st.markdown("### Hacking")
        c1, c2, c3 = st.columns(3)
        with c1:
            hack_cypher = st.checkbox("Cypher", key="hack_cypher")
        with c2:
            hack_black = st.checkbox("Black Cypher", key="hack_black")
        with c3:
            hack_success = st.checkbox("Successful Tech Roll", key="hack_success")

        flags = []
        if hack_cypher: flags.append("Cypher")
        if hack_black: flags.append("BlackCypher")
        if hack_success: flags.append("SuccessfulRoll")

        if st.button("Roll Hacking", key="btn_hacking"):
            st.success(roll_hacking(flags))

    # Encounter Difficulty (D20)
    with col_right.container(border=True):
        if st.button("Roll Encounter Difficulty", key="btn_encdif"):
            st.success(roll_table("encounter_difficulty", group=7, log=True))

    # Variable Encounter Difficulty (D10)
    with col_right.container(border=True):
        if st.button("Roll Variable Encounter Difficulty", key="btn_varenc"):
            st.success(roll_table("variable_encounter_difficulty", group=7, log=True))

    # One-Crew Encounter — Boxed with difficulty menu
    with col_right.container(border=True):
        st.markdown("### One-Crew Encounter")
        crew1_opt = st.selectbox(
            "Select Difficulty",
            ["Easy", "Standard", "Elite", "Overwhelming"],
            key="crew1_diff",
        )
        if st.button("Roll One-Crew Encounter", key="btn_onecrew"):
            st.success(roll_table("one_crew_encounter", option=crew1_opt, group=7, log=True))

    # Three-Crew Encounter — Boxed with difficulty menu
    with col_right.container(border=True):
        st.markdown("### Three-Crew Encounter")
        crew3_opt = st.selectbox(
            "Select Difficulty",
            ["Easy", "Standard", "Elite", "Overwhelming"],
            key="crew3_diff",
        )
        if st.button("Roll Three-Crew Encounter", key="btn_threecrew"):
            st.success(roll_table("three_crew_encounter", option=crew3_opt, group=7, log=True))

    # Five-Crew Encounter — Boxed with difficulty menu
    with col_right.container(border=True):
        st.markdown("### Five-Crew Encounter")
        crew5_opt = st.selectbox(
            "Select Difficulty",
            ["Easy", "Standard", "Elite", "Overwhelming"],
            key="crew5_diff",
        )
        if st.button("Roll Five-Crew Encounter", key="btn_fivecrew"):
            st.success(roll_table("five_crew_encounter", option=crew5_opt, group=7, log=True))

    # Experimental Gear Malfunction
    with col_right.container(border=True):
        if st.button("Roll Experimental Gear Malfunction", key="btn_expmal"):
            st.success(roll_table("experimental_malfunction", log=True))

# ---------- TAB: HEALTH ----------
with tabs[1]:
    st.header("Health & Trauma")

    # All Health tables (table_key, display_label)
    health_tables = [
        ("injuries", "Injuries"),
        ("critical_injuries", "Critical Injuries"),
        ("parasite_attack", "Parasite Attack"),
        ("poison_potency", "Poison Potency"),
        ("stress_others", "Stress (While With Others)"),
        ("stress_alone", "Stress (Alone)"),
        ("obsessions", "Obsessions"),
        ("trauma", "Trauma"),
        ("negative_trait", "Negative Trait"),
    ]

    # Two-column layout (matching Encounter tab)
    col_left, col_right = st.columns(2)

    # Loop through each health table and place buttons in alternating columns
    for idx, (key, label) in enumerate(health_tables):
        col = col_left if idx % 2 == 0 else col_right

        with col.container(border=True):
            st.markdown(f"### {label}")
            
            if st.button(f"Roll {label}", key=f"btn_health_{key}"):
                # Health tab requires logging but no persistence
                result = roll_table(key, group=None, log=True, option=None)
                st.success(result)

    # ---- Health Log Viewer ----
    st.subheader("Health Log")

    ensure_state()

    if st.session_state["log"]:
        for entry in st.session_state["log"]:
            st.write(f"- {entry}")
    else:
        st.info("No health log entries yet.")

    if st.button("Clear Health Log", key="clear_health_log"):
        st.session_state["log"] = []
        st.rerun()

# ---------- TAB: MISSION ----------
with tabs[2]:
    st.header("Mission Generator")
    if st.button("Generate Mission Seed"):
        st.success(roll_table("Mission Seed", log=True))
    if st.button("Generate Mission Obstacle"):
        st.success(roll_table("Mission Obstacle", log=True))

# ---------- TAB: EXPLORATION ----------
with tabs[3]:
    st.header("Exploration and Travel")
    if st.button("Generate Travel Event"):
        st.success(roll_table("Random Travel Event", group=3, log=True))
    if st.button("Generate Space Anomaly"):
        st.success(roll_table("Space Anomaly", group=3))

# ---------- TAB: PLANET ----------
with tabs[4]:
    st.header("Planet Generation")
    if st.button("Generate Planet Type"):
        st.success(roll_table("Planet Type", group=4, log=True))
    if st.button("Generate Planet Resources"):
        st.success(roll_table("Planet Resources", group=4))

# ---------- TAB: NPC ----------
with tabs[5]:
    st.header("NPC Generator")
    if st.button("Generate Civilian NPC"):
        st.success(roll_table("Civilian NPC", group=5, log=True))
    if st.button("Generate Crew Member"):
        st.success(roll_table("Crew Member", group=5))

# ---------- TAB: ANTAGONIST ----------
with tabs[6]:
    st.header("Antagonist Generator")
    if st.button("Generate Antagonist"):
        st.success(roll_table("Antagonist", group=6, log=True))
    if st.button("Generate Stat Block"):
        st.success(roll_table("Stat Block", group=6))

# ---------- TAB: RETURN TO BASE ----------
with tabs[7]:
    st.header("Return to Base (RTB)")
    if st.button("Generate Post-Mission Event"):
        st.success(roll_table("RTB Event", group=7, log=True))
    if st.button("Generate Complication"):
        st.success(roll_table("RTB Complication", group=7))

# ---------- TAB: LOG ----------
with tabs[8]:
    st.header("Mission Log")
    if st.session_state["log"]:
        for entry in st.session_state["log"]:
            st.markdown(f"- {entry}")
    else:
        st.info("No log entries yet.")
    
    if st.button("Clear Mission Log"):
        st.session_state["log"] = []
        st.rerun()

# ---------- SIDEBAR: PERSISTENT POOLS ----------
st.sidebar.header("Persistent Data Pools")
if not st.session_state["persistent"]:
    st.sidebar.info("No persistent data yet.")
else:
    for group_id, values in st.session_state["persistent"].items():
        st.sidebar.subheader(f"Persistent {group_id}")
        for item in values:
            st.sidebar.text(f"- {item}")
        if st.sidebar.button(f"Clear Persistent {group_id}"):
            clear_persistent(group_id)
            st.rerun()


