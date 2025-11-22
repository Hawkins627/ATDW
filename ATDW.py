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

def add_to_log(text: str):
    """Append a structured log entry (text + note)."""
    ensure_state()
    st.session_state["log"].append({
        "text": text,
        "note": ""
    })

def load_table_df(table_name: str) -> pd.DataFrame:
    """Load a CSV for a given table name."""
    path = DATA_DIR / f"{table_name}.csv"
    return pd.read_csv(path)

def format_row_for_display(table_name: str, row: pd.Series) -> str:
    """
    Cleaner formatter + special case handling for Random Site Name.
    """

    # --- Special case handling: Random Site Name ---
    if table_name == "random_site_name":
        first = str(row.get("first_syllable", "")).strip()
        second = str(row.get("second_syllable", "")).strip()
        number = str(row.get("numeric", "")).strip()
    
        # Build the final name:
        # Remove internal hyphen between syllables (you requested no hyphen)
        combined = f"{first}{second}-{number}"

        return combined

    # Preferred formatting if present
    if "title" in row and "description" in row:
        title = str(row["title"]) if pd.notna(row["title"]) else ""
        desc = str(row["description"]) if pd.notna(row["description"]) else ""
        if title and desc:
            return f"{title}: {desc}"
        elif title:
            return title
        elif desc:
            return desc

    # Fallback: ignore filter columns
    ignore_cols = {"difficulty", "creature_type"}
    parts = [
        str(row[c])
        for c in row.index
        if c not in ignore_cols and pd.notna(row[c])
    ]

    return " – ".join(parts) if parts else table_name

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

    # ADD THIS BACK
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

# ---------- SIDEBAR SIZE SELECTOR ----------
with st.sidebar:
    st.markdown("### Persistent Sidebar Width")
    width_choice = st.select_slider(
        "Sidebar Size",
        options=[250, 350, 500, 700, 900, 1100],
        value=500,
    )

# Apply CSS using the selected width
st.markdown(f"""
    <style>
        section[data-testid="stSidebar"] {{
            width: {width_choice}px !important;
            min-width: {width_choice}px !important;
        }}
        .main {{
            margin-left: {width_choice - 100}px !important;
        }}
    </style>
""", unsafe_allow_html=True)

# ---------- TAB: ENCOUNTER ----------
with tabs[0]:

    st.header("Encounter Tables")
    ensure_state()

    # LEFT / RIGHT COLUMN SETUP
    col_left, col_right = st.columns(2)

    # =====================================
    # ========== LEFT COLUMN ==============
    # =====================================

    # Difficulty Modifiers
    with col_left.container(border=True):
        if st.button("Roll Difficulty Modifiers", key="btn_diffmod"):
            st.success(roll_table("diffuculty_modifiers"))

    # Placement (NEW)
    with col_left.container(border=True):
        if st.button("Roll Placement", key="btn_place"):
            st.success(roll_table("placement"))

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

    # Recovery Status (NEW)
    with col_left.container(border=True):
        if st.button("Roll Recovery Status", key="btn_recovery"):
            st.success(roll_table("recovery_status"))

    # Critical Miss – Melee
    with col_left.container(border=True):
        if st.button("Roll Critical Miss – Melee", key="btn_cmm"):
            st.success(roll_table("critical_miss_melee"))

    # Encounter Difficulty (D20)
    with col_left.container(border=True):
        if st.button("Roll Encounter Difficulty", key="btn_encdif_left"):
            st.success(roll_table("encounter_difficulty", group=7, log=True))

    # Variable Encounter Difficulty (D10)
    with col_left.container(border=True):
        if st.button("Roll Variable Encounter Difficulty", key="btn_varenc_left"):
            st.success(roll_table("variable_encounter_difficulty", group=7, log=True))
 
    # =====================================
    # ========== RIGHT COLUMN =============
    # =====================================

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
    
    # ---------- HACKING (checkbox flag system) ----------
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
        if hack_cypher:
            flags.append("Cypher")
        if hack_black:
            flags.append("BlackCypher")
        if hack_success:
            flags.append("SuccessfulRoll")

        if st.button("Roll Hacking", key="btn_hacking"):
            st.success(roll_hacking(flags))

    # One-Crew Encounter
    with col_right.container(border=True):
        st.markdown("### One-Crew Encounter")
        crew1_opt = st.selectbox(
            "Select Difficulty", 
            ["Easy", "Standard", "Elite", "Overwhelming"], 
            key="crew1_diff"
        )
        if st.button("Roll One-Crew Encounter", key="btn_onecrew"):
            st.success(roll_table("one_crew_encounter", option=crew1_opt, group=7, log=True))

    # Three-Crew Encounter
    with col_right.container(border=True):
        st.markdown("### Three-Crew Encounter")
        crew3_opt = st.selectbox(
            "Select Difficulty", 
            ["Easy", "Standard", "Elite", "Overwhelming"], 
            key="crew3_diff"
        )
        if st.button("Roll Three-Crew Encounter", key="btn_threecrew"):
            st.success(roll_table("three_crew_encounter", option=crew3_opt, group=7, log=True))

    # Five-Crew Encounter
    with col_right.container(border=True):
        st.markdown("### Five-Crew Encounter")
        crew5_opt = st.selectbox(
            "Select Difficulty", 
            ["Easy", "Standard", "Elite", "Overwhelming"], 
            key="crew5_diff"
        )
        if st.button("Roll Five-Crew Encounter", key="btn_fivecrew"):
            st.success(roll_table("five_crew_encounter", option=crew5_opt, group=7, log=True))

    # Experimental Gear Malfunction
    with col_right.container(border=True):
        if st.button("Roll Experimental Gear Malfunction", key="btn_expmal"):
            st.success(roll_table("experimental_malfunction", log=True))

# ---------- TAB: HEALTH ----------
with tabs[1]:
    st.header("Health & Trauma Tables")

    # Two-column layout (same as Encounter)
    col_left, col_right = st.columns(2)

    # -----------------------------------------------------
    # LEFT COLUMN
    # -----------------------------------------------------
    with col_left:

        # Injuries
        with st.container(border=True):
            if st.button("Roll Injuries", key="btn_injuries"):
                st.success(roll_table("injuries", log=True))

        # Critical Injuries
        with st.container(border=True):
            if st.button("Roll Critical Injuries", key="btn_crit_injuries"):
                st.success(roll_table("critical_injuries", log=True))

        # Parasite Attack
        with st.container(border=True):
            if st.button("Roll Parasite Attack", key="btn_parasite_attack"):
                st.success(roll_table("parasite_attack", log=True))

        # Poison Potency
        with st.container(border=True):
            if st.button("Roll Poison Potency", key="btn_poison_potency"):
                st.success(roll_table("poison_potency", log=True))

    # -----------------------------------------------------
    # RIGHT COLUMN
    # -----------------------------------------------------
    with col_right:

        # Stress Reaction – Others
        with st.container(border=True):
            if st.button("Roll Stress (Others)", key="btn_stress_others"):
                st.success(roll_table("stress_others", log=True))

        # Stress Reaction – Alone
        with st.container(border=True):
            if st.button("Roll Stress (Alone)", key="btn_stress_alone"):
                st.success(roll_table("stress_alone", log=True))

        # Obsessions
        with st.container(border=True):
            if st.button("Roll Obsessions", key="btn_obsessions"):
                st.success(roll_table("obsessions", log=True))

        # Trauma
        with st.container(border=True):
            if st.button("Roll Trauma", key="btn_trauma"):
                st.success(roll_table("trauma", log=True))

        # Negative Traits
        with st.container(border=True):
            if st.button("Roll Negative Trait", key="btn_negative_trait"):
                st.success(roll_table("negative_trait", log=True))

# ---------- TAB: MISSION ----------
with tabs[2]:

    st.header("Mission Generator")
    ensure_state()
    import random

    # Persistent pool group for this section
    MISSION_GROUP = 1

    # =====================================================================
    # SHIP GENERATOR (Left Column)
    # =====================================================================
    col_left, col_right = st.columns(2)

    with col_left.container(border=True):
        st.markdown("### Ship Generator")

        if st.button("Roll Ship Name", key="btn_ship_name"):
            st.success(roll_table("spaceship_name", group=MISSION_GROUP, log=True))

        if st.button("Roll Ship Adjective", key="btn_ship_adj"):
            st.success(roll_table("spaceship_adjective", group=MISSION_GROUP, log=True))

        st.markdown("### Full Ship (Adjective + Name)")
        if st.button("ROLL FULL SHIP", key="btn_ship_full"):
            adj = roll_table("spaceship_adjective", log=False)
            name = roll_table("spaceship_name", log=False)
            combined = f"{adj} {name}"
            add_to_log(f"Ship: {combined}")
            add_to_persistent(MISSION_GROUP, combined)
            st.success(combined)

    # =====================================================================
    # TRAVEL EVENTS (Right Column)
    # =====================================================================
    with col_right.container(border=True):
        st.markdown("### Travel Events")

        if st.button("Roll Travel Event Type", key="btn_travel_type"):
            st.success(roll_table("random_travel_event_type", log=True))

        if st.button("Roll Social Travel Event", key="btn_social_travel"):
            st.success(roll_table("social_travel_event", log=True))

        if st.button("Roll Ship Malfunction", key="btn_ship_malf_travel"):
            st.success(roll_table("ship_malfunction_travel_event", log=True))

        if st.button("Roll Space Anomaly Event", key="btn_space_anom_travel"):
            st.success(roll_table("space_anomaly_travel_event", log=True))

        if st.button("Roll Mental/Physical Event", key="btn_mental_phys_travel"):
            st.success(roll_table("mental_physical_travel_event", log=True))

        st.markdown("### Full Travel Event (Type + Detail)")
        if st.button("ROLL FULL TRAVEL EVENT", key="btn_travel_full"):
            event_type = roll_table("random_travel_event_type", log=False)
            subtable = random.choice([
                "social_travel_event",
                "ship_malfunction_travel_event",
                "space_anomaly_travel_event",
                "mental_physical_travel_event",
            ])
            detail = roll_table(subtable, log=False)
            combined = f"{event_type} – {detail}"
            add_to_log("Travel Event: " + combined)
            st.success(combined)

    # =====================================================================
    # MISJUMP GENERATOR
    # =====================================================================
    with col_left.container(border=True):
        st.markdown("### Misjump Generator")

        if st.button("Roll Primary Misjump", key="btn_misjump_primary"):
            st.success(roll_table("misjump", log=True))

        if st.button("Roll Time Dilation", key="btn_time_dilation_misjump"):
            st.success(roll_table("time_dilation_misjump", log=True))

        if st.button("Roll Transit Dilation", key="btn_transit_dilation_misjump"):
            st.success(roll_table("transit_dilation_misjump", log=True))

        if st.button("Roll Secondary Effects", key="btn_secondary_misjump"):
            st.success(roll_table("secondary_misjump_effects", log=True))

        st.markdown("### Full Misjump (All Effects)")
        if st.button("ROLL FULL MISJUMP", key="btn_misjump_full"):
            primary = roll_table("misjump", log=False)
            dilation = roll_table(random.choice([
                "time_dilation_misjump",
                "transit_dilation_misjump"
            ]), log=False)
            secondary = roll_table("secondary_misjump_effects", log=False)

            combined = (
                f"**Primary:** {primary}\n"
                f"**Dilation:** {dilation}\n"
                f"**Secondary:** {secondary}"
            )

            add_to_log("Misjump:\n" + combined)
            st.success(combined)

    # =====================================================================
    # ARRIVAL TABLE
    # =====================================================================
    with col_left.container(border=True):
        st.markdown("### Arrival Table")

        if st.button("Roll Arrival Table", key="btn_arrival_table_moved"):
            st.success(roll_table("arrival_table", group=MISSION_GROUP, log=True))

    # =====================================================================
    # SITE GENERATOR — Full Width
    # =====================================================================
    st.markdown("### Site Generator")

    with st.container(border=True):

        include_planetary = st.checkbox(
            "Include Planetary Descriptor in Full Site",
            key="include_planet_desc",
            value=False
        )

        site_col1, site_col2 = st.columns(2)

        with site_col1:
            if st.button("Roll Random Site Name", key="btn_random_site_name"):
                st.success(roll_table("random_site_name", group=MISSION_GROUP, log=True))

            if st.button("Roll Site Original Purpose", key="btn_site_original_purpose"):
                st.success(roll_table("site_original_purpose", group=MISSION_GROUP, log=True))

            if st.button("Roll Site Story", key="btn_site_story"):
                st.success(roll_table("site_story", group=MISSION_GROUP, log=True))

            if st.button("Roll Overall Site Descriptor", key="btn_overall_site_desc"):
                st.success(roll_table("overall_site_descriptor", group=MISSION_GROUP, log=True))

        with site_col2:
            if st.button("Roll Planetary Site Descriptor", key="btn_planetary_site_desc"):
                st.success(roll_table("planetary_site_descriptor", group=MISSION_GROUP, log=True))

            if st.button("Roll Site Activity", key="btn_site_activity"):
                st.success(roll_table("site_activity", group=MISSION_GROUP, log=True))

            if st.button("Roll Known Threats", key="btn_known_threats"):
                st.success(roll_table("known_threats", group=MISSION_GROUP, log=True))

            if st.button("Roll Site Hazard", key="btn_site_hazard"):
                st.success(roll_table("site_hazard", group=MISSION_GROUP, log=True))

            if st.button("Roll Site Size", key="btn_site_size"):
                st.success(roll_table("site_size", group=MISSION_GROUP, log=True))

        st.markdown("### Full Site (ALL 10 Tables)")
        if st.button("ROLL FULL SITE", key="btn_site_full"):

            sections = []

            def add(label, tbl):
                txt = roll_table(tbl, log=False)
                sections.append(f"- **{label}:** {txt}")
                add_to_persistent(MISSION_GROUP, f"{label}: {txt}")

            add("Random Site Name", "random_site_name")
            add("Original Purpose", "site_original_purpose")
            add("Story", "site_story")
            add("Overall Descriptor", "overall_site_descriptor")
            add("Activity", "site_activity")
            add("Known Threats", "known_threats")
            add("Hazard", "site_hazard")
            add("Size", "site_size")

            if include_planetary:
                add("Planetary Descriptor", "planetary_site_descriptor")

            final_output = "\n".join(sections)
            add_to_log("Full Site:\n" + final_output)
            st.success(final_output)

    # =====================================================================
    # ACTION + THEME (Right Column)
    # =====================================================================
    with col_right.container(border=True):

        st.markdown("### Action & Theme")

        if st.button("Roll Action", key="btn_action_table"):
            st.success(roll_table("action"))

        if st.button("Roll Theme", key="btn_theme_table"):
            st.success(roll_table("theme"))

        st.markdown("### Action + Theme Pairing")
        if st.button("ROLL ACTION + THEME", key="btn_action_theme_full"):
            a = roll_table("action", log=False)
            t = roll_table("theme", log=False)
            combined = f"{a} – {t}"
            add_to_log("Action & Theme: " + combined)
            st.success(combined)

# ---------- TAB: EXPLORATION ----------
with tabs[3]:

    st.header("Exploration Tables")
    ensure_state()

    # Two-column layout to match Encounter / Health / Mission
    col_left, col_right = st.columns(2)

    # =====================================
    # ========== LEFT COLUMN ==============
    # =====================================

    # Area Connector  (Persistent group 2, log=True)
    with col_left.container(border=True):
        if st.button("Roll Area Connector", key="btn_area_connector"):
            st.success(roll_table("area_connector", group=2, log=True))

    # Site Exploration  (Persistent group 2, log=True)
    with col_left.container(border=True):
        if st.button("Roll Site Exploration", key="btn_site_exploration"):
            st.success(roll_table("site_exploration", group=2, log=True))

    # Xenoanthropological Artifact  (log=True)
    with col_left.container(border=True):
        if st.button("Roll Xenoanthropological Artifact", key="btn_xeno_artifact"):
            st.success(roll_table("xenoanthropological_artifact", log=True))

    # Activating Artifact  (log=True)
    with col_left.container(border=True):
        if st.button("Roll Activating Artifact", key="btn_activating_artifact"):
            st.success(roll_table("activating_artifact", log=True))

    # Hazard Manifestation  (log=True)
    with col_left.container(border=True):
        if st.button("Roll Hazard Manifestation", key="btn_hazard_manifestation"):
            st.success(roll_table("hazard_manifestation", log=True))

    # =====================================
    # ========== RIGHT COLUMN =============
    # =====================================

    # Door Type  (log=True)
    with col_right.container(border=True):
        if st.button("Roll Door Type", key="btn_door_type"):
            st.success(roll_table("door_type", log=True))

    # Behind Door  (log=True)
    with col_right.container(border=True):
        if st.button("Roll Behind Door", key="btn_behind_door"):
            st.success(roll_table("behind_door", log=True))

    # Automatic Security Measure  (log=True)
    with col_right.container(border=True):
        if st.button("Roll Automatic Security Measure", key="btn_auto_security"):
            st.success(roll_table("automatic_security_measure", log=True))

    # Teleport (for security measures)  (log=True)
    with col_right.container(border=True):
        if st.button("Roll Teleport Effect", key="btn_teleport"):
            st.success(roll_table("teleport", log=True))

    # Fixed Event  (log=True)
    with col_right.container(border=True):
        if st.button("Roll Fixed Event", key="btn_fixed_event"):
            st.success(roll_table("fixed_event", log=True))

    # =====================================
    # ========== SPECIAL SETS =============
    # =====================================

    # ----- Dread Event + Taints (Combined = 5) -----
    with col_left.container(border=True):
        st.markdown("### Dread Event")

        # Standalone Dread Event roll
        if st.button("Roll Dread Event", key="btn_dread_event"):
            result = roll_table("dread_event", log=True)
            st.success(result)

        # Standalone Taints roll
        if st.button("Roll Taints", key="btn_taints"):
            result = roll_table("taints", log=True)
            st.success(result)

        # ---- FULL DREAD EVENT (with conditional roll) ----
        st.markdown("### Full Dread Event (Auto Taint on 1)")

        if st.button("ROLL FULL DREAD EVENT", key="btn_full_dread"):
            # Roll the primary dread event
            dread_df = load_table_df("dread_event")
        
            # Sample and capture the ROW so we can read the index
            dread_row = dread_df.sample(1)
            dread_number = dread_row.index[0] + 1   # Convert to 1–20 numbering
            dread_text = format_row_for_display("dread_event", dread_row.iloc[0])

            final_output = f"**Dread Event ({dread_number}):** {dread_text}"

            # Log + persistent
            add_to_log(final_output)
            add_to_persistent(1, final_output)

            # If the result is 1 → auto-roll Taint
            if dread_number == 1:
                taint_result = roll_table("taints", log=False)
                full_taint_entry = f"**Taint:** {taint_result}"

                final_output += f"\n\n{full_taint_entry}"

                add_to_log(full_taint_entry)
                add_to_persistent(1, full_taint_entry)

            st.success(final_output)


    # ----- Automatic Security + Teleport (Combined = 6) -----
    with col_right.container(border=True):
        st.markdown("### Security Measure & Teleport")

        if st.button("Roll Security + Teleport", key="btn_security_full"):
            sec = roll_table("automatic_security_measure", log=False)
            tel = roll_table("teleport", log=False)
            combined = f"Security Measure: {sec}\nTeleport Effect: {tel}"
            add_to_log("Security Event:\n" + combined)
            st.success(combined)

    # ---------- OCCURRENCE & SURROUNDINGS ----------
    with col_right.container(border=True):
        st.markdown("### Occurrence & Surrounding Details")

        # ---- Situation Category Input (Used when needed) ----
        situation_categories = [
            "Aesthetic", "Communications", "Data Storage", "Entertainment",
            "Government", "Industrial", "Medical Research", "Military",
            "Power Center", "Prison", "Refinery", "Refuge",
            "Residential", "Spaceport", "Teaching", "Temple",
            "Tomb", "Vault", "Watchpost"
        ]

        situation_choice = st.selectbox(
            "Select Noun Category (for Situation rolls):",
            options=situation_categories,
            key="situation_category"
        )

        # -------------------- Roll Occurrence Only --------------------
        if st.button("Roll Occurrence", key="btn_occurrence"):
            occ = roll_table("occurrence", log=True)
            st.success(f"Occurrence: {occ}")

        # -------------------- Individual Sub-tables --------------------
        if st.button("Roll Discovery", key="btn_discovery"):
            st.success(roll_table("discovery", log=True))

        if st.button("Roll Danger", key="btn_danger"):
            st.success(roll_table("danger", log=True))

        if st.button("Roll Event", key="btn_event"):
            st.success(roll_table("event", log=True))

        # ---------- FULL OCCURRENCE SET ----------
        st.markdown("### Full Occurrence Set")

        if st.button("Roll Full Occurrence Set", key="btn_occ_full"):

            results = []

            # Step 1 — Roll Occurrence
            occ = roll_table("occurrence", log=False)
            results.append(f"- **Occurrence:** {occ}")
            add_to_log(f"Occurrence: {occ}")

            # Step 2 — Roll Subtable Based on Occurrence
            occ_lower = occ.lower()

            if occ_lower == "danger":
                sub = roll_table("danger", log=False)
                results.append(f"- **Danger:** {sub}")
                add_to_log(f"Danger: {sub}")

            elif occ_lower == "discovery":
                sub = roll_table("discovery", log=False)
                results.append(f"- **Discovery:** {sub}")
                add_to_log(f"Discovery: {sub}")

            elif occ_lower == "event":
                sub = roll_table("event", log=False)
                results.append(f"- **Event:** {sub}")
                add_to_log(f"Event: {sub}")

            elif occ_lower == "situation":
                # Roll verb + noun automatically!
                verb = roll_table("situation_verb", log=False)
                noun = roll_table("situation_noun", option=situation_choice, log=False)

                results.append(f"- **Situation Verb:** {verb}")
                results.append(f"- **Situation Noun ({situation_choice}):** {noun}")

                add_to_log(f"Situation Verb: {verb}")
                add_to_log(f"Situation Noun ({situation_choice}): {noun}")

            # Show final combined result
            final = "\n".join(results)
            st.success(final)

# ---------- SITUATION (MANUAL ROLLS) ----------
with col_right.container(border=True):
    st.markdown("### Situation (Verb & Noun)")

    if st.button("Roll Situation Verb", key="btn_situation_verb"):
        st.success(roll_table("situation_verb", log=True))

    if st.button("Roll Situation Noun", key="btn_situation_noun"):
        st.success(roll_table("situation_noun", option=situation_choice, log=True))

    if st.button("Roll Full Situation", key="btn_situation_full"):
        verb = roll_table("situation_verb", log=False)
        noun = roll_table("situation_noun", option=situation_choice, log=False)
        combined = f"Verb: {verb}\nNoun ({situation_choice}): {noun}"
        add_to_log("Situation:\n" + combined)
        st.success(combined)

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
    ensure_state()

    # Convert old plain-string entries → dict entries
    for i, entry in enumerate(st.session_state["log"]):
        if isinstance(entry, str):
            st.session_state["log"][i] = {"text": entry, "note": ""}

    log_list = st.session_state["log"]

    if not log_list:
        st.info("No log entries yet.")
    else:
        for idx, entry in enumerate(log_list):

            text = entry["text"]
            note = entry.get("note", "")

            # ROW: icon button + entry text
            row_left, row_right = st.columns([1, 12])

            # ---------- LEFT COLUMN: Notepad icon ----------
            with row_left:
                if st.button("📝", key=f"note_icon_{idx}", help="Add/Edit Note"):
                    st.session_state["active_note"] = idx

            # ---------- RIGHT COLUMN: Log text with inline note ----------
            if note:
                row_right.markdown(f"{text}  \n📝 *{note}*")
            else:
                row_right.markdown(text)

            # ---------- INLINE EDITOR BELOW THIS ENTRY ----------
            if st.session_state.get("active_note") == idx:
                st.markdown("### ✏️ Edit Note")

                new_note = st.text_area(
                    "Note text:",
                    value=note,
                    height=200,
                    key=f"note_area_{idx}"
                )

                c1, c2 = st.columns(2)

                with c1:
                    if st.button("💾 Save Note", key=f"save_note_{idx}"):
                        st.session_state["log"][idx]["note"] = new_note
                        del st.session_state["active_note"]
                        st.success("Saved!")
                        st.rerun()

                with c2:
                    if st.button("❌ Cancel", key=f"cancel_note_{idx}"):
                        del st.session_state["active_note"]
                        st.rerun()

            st.markdown("---")

    # Clear log button
    if st.button("Clear Mission Log"):
        st.session_state["log"] = []
        st.rerun()

    # Export button
    if log_list:
        export_lines = []
        for entry in log_list:
            export_lines.append(entry["text"])
            if entry.get("note"):
                export_lines.append(f"NOTE: {entry['note']}")
            export_lines.append("")
        export_text = "\n".join(export_lines)

        st.download_button(
            label="📄 Export Log as Text File",
            data=export_text,
            file_name="mission_log.txt",
            mime="text/plain"
        )

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
