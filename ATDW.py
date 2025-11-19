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
    Temporary hacking handler. Right now we just describe the flags and
    log the event; later we can implement the full dice procedure.
    """
    ensure_state()
    if flags:
        flag_text = ", ".join(flags)
    else:
        flag_text = "none"

    text = f"Hacking attempt (flags: {flag_text})"
    add_to_log(text)
    return text

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

    # Each tuple: (CSV filename, Label, persistent-group, log_flag, special_behavior)
    encounter_tables = [
        ("diffuculty_modifiers", "Difficulty Modifiers", None, False, None),  # filename intentionally misspelled
        ("placement", "Placement", None, False, None),
        ("surprise", "Surprise", None, False, None),
        ("encounter_activity", "Encounter Activity", None, False, None),
        ("combat_stance", "Combat Stance", None, False, None),
        ("targeting", "Targeting", None, False, None),
        ("recovery_status", "Recovery Status", None, False, None),
        ("hit_locations", "Hit Locations", None, False, "hitloc"),
        ("random_direction", "Random Direction", None, False, None),
        ("critical_miss_melee", "Critical Miss – Melee", None, False, None),
        ("critical_miss_ranged", "Critical Miss – Ranged", None, False, None),
        ("random_combat_event", "Random Combat Event", None, False, None),
        ("hacking", "Hacking", None, True, "hacking"),
        ("encounter_difficulty", "Encounter Difficulty", 7, True, None),
        ("variable_encounter_difficulty", "Variable Encounter Difficulty", 7, True, None),
        ("one_crew_encounter", "One-Crew Encounter", 7, True, "crew1"),
        ("three_crew_encounter", "Three-Crew Encounter", 7, True, "crew3"),
        ("five_crew_encounter", "Five-Crew Encounter", 7, True, "crew5"),
        ("experimental_malfunction", "Experimental Gear Malfunction", None, True, None),
    ]

    # 2 columns for the buttons
    col_left, col_right = st.columns(2)

    # ------------------------------------------------
    # RENDER EACH TABLE WITH ITS OPTIONS + BUTTON
    # ------------------------------------------------
    for idx, (key, label, group_id, log_flag, special) in enumerate(encounter_tables):

        col = col_left if idx % 2 == 0 else col_right

        with col:
            st.subheader(label)

            # -----------------------------------------
            # Special UI controls ABOVE each button
            # -----------------------------------------
            option = None  # default

            # Hit Locations → Creature Type
            if special == "hitloc":
                option = st.selectbox(
                    "Creature Shape",
                    ["Humanoid", "Quadruped", "Sextuped", "Serpentine"],
                    key=f"{key}_opt"
                )

            # One-Crew Difficulty Selector
            elif special == "crew1":
                option = st.selectbox(
                    "Select Difficulty",
                    ["Easy", "Standard", "Elite", "Overwhelming"],
                    key=f"{key}_opt"
                )

            # Three-Crew Difficulty Selector
            elif special == "crew3":
                option = st.selectbox(
                    "Select Difficulty",
                    ["Easy", "Standard", "Elite", "Overwhelming"],
                    key=f"{key}_opt"
                )

            # Five-Crew Difficulty Selector
            elif special == "crew5":
                option = st.selectbox(
                    "Select Difficulty",
                    ["Easy", "Standard", "Elite", "Overwhelming"],
                    key=f"{key}_opt"
                )

            # HACKING FLAGS
            elif special == "hacking":
                c1, c2, c3 = st.columns(3)
                with c1:
                    hack_cypher = st.checkbox("Cypher", key=f"{key}_cypher")
                with c2:
                    hack_black = st.checkbox("Black Cypher", key=f"{key}_black")
                with c3:
                    hack_success = st.checkbox("Successful Tech Roll", key=f"{key}_success")

                hacking_flags = []
                if hack_cypher:
                    hacking_flags.append("Cypher")
                if hack_black:
                    hacking_flags.append("BlackCypher")
                if hack_success:
                    hacking_flags.append("SuccessfulRoll")

            # -----------------------------------------
            # ROLL BUTTON
            # -----------------------------------------
            if st.button(f"Roll {label}", key=f"btn_{key}"):

                # Hacking uses its own function
                if special == "hacking":
                    result = roll_hacking(hacking_flags)

                else:
                    # Everything else uses roll_table
                    result = roll_table(
                        key,
                        group=group_id,
                        log=log_flag,
                        option=option,
                    )

                st.success(result)

    # ------------------------------------------------
    # IMPORTANT — we REMOVED the extra persistent data block here
    # Persistent data now ONLY appears in the left sidebar (as you want)
    # ------------------------------------------------

# ---------- TAB: HEALTH ----------
with tabs[1]:
    st.header("Health and Trauma")
    if st.button("Roll Injury Event"):
        st.success(roll_table("Injury Event", group=2, log=True))
    if st.button("Roll Madness Effect"):
        st.success(roll_table("Madness Effect", group=2))

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


