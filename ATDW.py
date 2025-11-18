import streamlit as st
import pandas as pd
import random
import os

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

def roll_table(table_name, group=None, log=False):
    """Temporary placeholder for table roll logic."""
    result = f"Rolled on **{table_name}** → (Random result placeholder)"
    if group:
        add_to_persistent(group, result)
    if log:
        add_to_log(result)
    return result

# ---------- DEFINE PRIMARY TABS ----------
tab_labels = [
    "Encounter", "Health", "Mission", "Exploration",
    "Planet", "NPC", "Antagonist", "Return to Base", "Log"
]

tabs = st.tabs(tab_labels)

# ---------- TAB: ENCOUNTER ----------
with tabs[0]:
    st.header("Encounter Tables")

    # Metadata: rulebook order, plus persistent/log info and any inputs
    encounter_tables = [
        {
            "key": "difficulty_modifiers",
            "label": "Difficulty Modifiers",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "placement",
            "label": "Placement",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "surprise",
            "label": "Surprise",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "encounter_activity",
            "label": "Encounter Activity",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "combat_stance",
            "label": "Combat Stance",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "targeting",
            "label": "Targeting",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "recovery_status",
            "label": "Recovery Status",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "hit_locations",
            "label": "Hit Locations",
            "group": None,
            "log": False,
            "input": {
                "type": "select",
                "label": "Creature Shape",
                "options": ["Humanoid", "Quadruped", "Sextuped", "Serpentine"],
            },
        },
        {
            "key": "random_direction",
            "label": "Random Direction",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "critical_miss_melee",
            "label": "Critical Miss – Melee",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "critical_miss_ranged",
            "label": "Critical Miss – Ranged",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "random_combat_event",
            "label": "Random Combat Event",
            "group": None,
            "log": False,
            "input": None,
        },
        {
            "key": "hacking",
            "label": "Hacking",
            "group": None,
            "log": True,   # goes to mission log
            "input": {
                "type": "hacking_flags"
            },
        },
        {
            "key": "encounter_difficulty",
            "label": "Encounter Difficulty",
            "group": 7,    # persistent pool 7
            "log": True,
            "input": None,
        },
        {
            "key": "variable_encounter_difficulty",
            "label": "Variable Encounter Difficulty",
            "group": 7,
            "log": True,
            "input": None,
        },
        {
            "key": "one_crew_encounter",
            "label": "One-Crew Encounter",
            "group": 7,
            "log": True,
            "input": {
                "type": "select",
                "label": "Difficulty",
                "options": ["Easy", "Standard", "Elite", "Overwhelming"],
            },
        },
        {
            "key": "three_crew_encounter",
            "label": "Three-Crew Encounter",
            "group": 7,
            "log": True,
            "input": {
                "type": "select",
                "label": "Difficulty",
                "options": ["Easy", "Standard", "Elite", "Overwhelming"],
            },
        },
        {
            "key": "five_crew_encounter",
            "label": "Five-Crew Encounter",
            "group": 7,
            "log": True,
            "input": {
                "type": "select",
                "label": "Difficulty",
                "options": ["Easy", "Standard", "Elite", "Overwhelming"],
            },
        },
        {
            "key": "experimental_malfunction",
            "label": "Experimental Gear Malfunction",
            "group": None,
            "log": True,
            "input": None,
        },
    ]

    col_left, col_right = st.columns(2)

    # render buttons in two columns, rulebook order
    for idx, meta in enumerate(encounter_tables):
        col = col_left if idx % 2 == 0 else col_right
        key = meta["key"]
        label = meta["label"]
        group_id = meta.get("group", None)
        log_flag = meta.get("log", False)
        input_cfg = meta.get("input", None)

        with col:
            st.subheader(label)

            extra_note = ""
            # handle select inputs (hit locations, crew encounters)
            if input_cfg and input_cfg.get("type") == "select":
                opt = st.selectbox(
                    input_cfg["label"],
                    input_cfg["options"],
                    key=f"{key}_select"
                )
                extra_note = f" | Option: {opt}"

            # handle hacking flags
            hacking_flags = None
            if input_cfg and input_cfg.get("type") == "hacking_flags":
                c1, c2, c3 = st.columns(3)
                with c1:
                    cypher = st.checkbox("Cypher", key="hack_cypher")
                with c2:
                    black = st.checkbox("Black Cypher", key="hack_black")
                with c3:
                    suc = st.checkbox("Successful Roll", key="hack_success")
                flags = []
                if cypher:
                    flags.append("Cypher")
                if black:
                    flags.append("BlackCypher")
                if suc:
                    flags.append("SuccessfulRoll")
                hacking_flags = flags
                if flags:
                    extra_note = " | Flags: " + ", ".join(flags)
                else:
                    extra_note = " | Flags: None"

            # button itself
            if st.button(f"Roll {label}", key=f"btn_{key}"):
                # for now we just tack input information onto the table name;
                # later the real rolling logic can parse/use it.
                full_name = key + extra_note

                # Hacking could eventually use its own function; for now we
                # still go through roll_table so logging/persistence behave.
                result = roll_table(
                    full_name,
                    group=group_id,
                    log=log_flag
                )
                st.success(result)

    # ---------------------------
    # Encounter Persistent Section
    # ---------------------------
    st.subheader("Persistent Encounter Data")

    if 7 in st.session_state["persistent"] and st.session_state["persistent"][7]:
        for entry in st.session_state["persistent"][7]:
            st.write(f"- {entry}")
    else:
        st.info("No persistent encounter data yet.")

    if st.button("Clear Encounter Persistent Data"):
        if 7 in st.session_state["persistent"]:
            st.session_state["persistent"][7] = []
        st.experimental_rerun()

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
        st.experimental_rerun()

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
            st.experimental_rerun()

