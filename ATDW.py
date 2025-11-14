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
    st.header("Encounter Generator")

    st.markdown("Use these tools to generate combat-related and encounter-related results. "
                "All buttons below correspond directly to table files in your Encounter data folder.")

    # Dictionary mapping table names to their metadata
    encounter_tables = {
        "diffuculty_modifiers":      {"group": None, "log": False, "inputs": None},
        "placement":                 {"group": None, "log": False, "inputs": None},
        "surprise":                  {"group": None, "log": False, "inputs": None},
        "encounter_activity":        {"group": None, "log": False, "inputs": None},
        "combat_stance":             {"group": None, "log": False, "inputs": None},
        "targeting":                 {"group": None, "log": False, "inputs": None},
        "recovery_status":           {"group": None, "log": False, "inputs": None},
        "hit_locations":             {"group": None, "log": False,
                                      "inputs": ["Humanoid", "Quadruped", "Sextuped", "Serpentine"]},
        "random_direction":          {"group": None, "log": False, "inputs": None},
        "critical_miss_melee":       {"group": None, "log": False, "inputs": None},
        "critical_miss_ranged":      {"group": None, "log": False, "inputs": None},
        "random_combat_event":       {"group": None, "log": False, "inputs": None},

        # Hacking includes three checkboxes
        "hacking":                   {"group": None, "log": True,
                                      "checkboxes": ["Cypher", "BlackCypher", "SuccessfulRoll"]},

        # These belong to persistent group 7
        "encounter_difficulty":      {"group": 7, "log": True},
        "variable_encounter_difficulty": {"group": 7, "log": True},
        "one_crew_encounter":        {"group": 7, "log": True,
                                      "inputs": ["Easy", "Standard", "Elite", "Overwhelming"]},
        "three_crew_encounter":      {"group": 7, "log": True,
                                      "inputs": ["Easy", "Standard", "Elite", "Overwhelming"]},
        "five_crew_encounter":       {"group": 7, "log": True,
                                      "inputs": ["Easy", "Standard", "Elite", "Overwhelming"]},

        "experimental_malfunction":  {"group": None, "log": True},
    }

    st.subheader("Encounter Tables")

    # Render a button for each table
    for table_name, meta in encounter_tables.items():

        # Build the UI row for this table
        col1, col2 = st.columns([0.4, 0.6])

        with col1:
            st.markdown(f"**{table_name.replace('_', ' ').title()}**")

        with col2:

            # Handle dropdown inputs
            selected_input = None
            if "inputs" in meta and meta["inputs"] is not None:
                selected_input = st.selectbox(
                    f"Select option for {table_name}",
                    meta["inputs"],
                    key=f"{table_name}_input"
                )

            # Handle hacking checkboxes
            check_states = None
            if "checkboxes" in meta:
                check_states = {}
                st.write("Options:")
                cb1, cb2, cb3 = st.columns(3)
                for i, opt in enumerate(meta["checkboxes"]):
                    box_col = [cb1, cb2, cb3][i]
                    with box_col:
                        check_states[opt] = st.checkbox(
                            opt, key=f"{table_name}_cb_{opt}"
                        )

            # Roll button
            roll_button = st.button(f"Roll {table_name}", key=f"btn_{table_name}")

            if roll_button:
                # Construct roll description string
                input_note = ""
                if selected_input:
                    input_note = f" | Option: {selected_input}"
                if check_states:
                    enabled = [k for k, v in check_states.items() if v]
                    input_note = f" | Flags: {', '.join(enabled) if enabled else 'None'}"

                result = roll_table(
                    table_name + input_note,
                    group=meta.get("group", None),
                    log=meta.get("log", False)
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

