import streamlit as st
import pandas as pd
import random
import os
import re
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

    # Flat damage modifier from Size (and later other effects)
    if "damage_flat_modifier" not in st.session_state:
        st.session_state["damage_flat_modifier"] = 0

    # INT override from creature_intelligence
    if "int_stat_override" not in st.session_state:
        st.session_state["int_stat_override"] = None

    # Enemy role modifiers (from roles.csv)
    if "role_mods" not in st.session_state:
        st.session_state["role_mods"] = None
    if "current_enemy_role" not in st.session_state:
        st.session_state["current_enemy_role"] = None

    # Unique Trait modifiers (from unique_trait.csv)
    if "unique_trait_mods" not in st.session_state:
        st.session_state["unique_trait_mods"] = {}
    if "unique_trait_desc" not in st.session_state:
        st.session_state["unique_trait_desc"] = None
    if "suppress_enemy_ability" not in st.session_state:
        st.session_state["suppress_enemy_ability"] = False

    # Track last rolled stat block row so we can re-render it after modifiers change
    if "last_stat_block_row" not in st.session_state:
        st.session_state["last_stat_block_row"] = None
    if "last_stat_block_label" not in st.session_state:
        st.session_state["last_stat_block_label"] = None

def parse_randomize_reactions(text: str):
    """
    Split '[Bloodied] A OR B; [Cornered] C OR D; ...'
    into bullet lines, picking ONE option per status.
    Returns a list of markdown strings like '- **[Bloodied]** Attempts to flee'.
    """
    if not isinstance(text, str) or not text.strip():
        return []

    # Split into segments like "[Bloodied] +2 Damage OR Attempts to flee"
    segments = [seg.strip() for seg in text.split(";") if seg.strip()]
    out = []

    for seg in segments:
        # Grab the status in [brackets] and the rest of the line
        m = re.match(r"\[(.*?)\]\s*(.*)", seg)
        if not m:
            continue
        status = m.group(1).strip()
        rest = m.group(2).strip()
        if not rest:
            continue

        # Split "A OR B" into options, pick one
        options = [opt.strip() for opt in rest.split(" OR ") if opt.strip()]
        choice = random.choice(options) if options else rest
        out.append(f"- **[{status}]** {choice}")

    return out

def roll_int_from_expression(expr: str) -> int:
    """
    Roll expressions like '6-1D4' or '6+1D8' into a single INT value.
    If parsing fails, returns 0.
    """
    s = str(expr).strip().upper()
    if not s:
        return 0

    # Match things like '6-1D4' or '6+1D8'
    m = re.match(r'^(\d+)\s*([+-])\s*(\d+)D(\d+)$', s)
    if m:
        base = int(m.group(1))
        sign = 1 if m.group(2) == "+" else -1
        num_dice = int(m.group(3))
        die_size = int(m.group(4))

        total = base
        for _ in range(num_dice):
            total += sign * random.randint(1, die_size)
        return total

    # Fallback: plain integer
    try:
        return int(s)
    except ValueError:
        return 0

def set_role_modifiers_from_text(role_text: str):
    """
    Look up the matching row in roles.csv for the given enemy role text
    and store its modifiers in st.session_state["role_mods"].
    Matching is case-insensitive against the 'role' column.
    """
    ensure_state()

    try:
        df = load_table_df("roles")
    except FileNotFoundError:
        # If the roles.csv file isn't present, just clear any old mods.
        st.session_state["role_mods"] = None
        return

    text = str(role_text).lower().strip()
    if not text:
        st.session_state["role_mods"] = None
        return

    # Try to find a keyword like "brute", "lurker", "ranged", "swarm", "psychic"
    candidates = [str(r).lower() for r in df["role"].dropna().unique()]
    found_key = None
    for key in candidates:
        if key in text:
            found_key = key
            break

    if not found_key:
        st.session_state["role_mods"] = None
        return

    role_row = df[df["role"].str.lower() == found_key].iloc[0]
    st.session_state["role_mods"] = role_row.to_dict()
    st.session_state["current_enemy_role"] = role_text

def add_to_persistent(group_id, text):
    """Store a text entry in a numbered persistent pool."""
    if group_id is None:
        return
    ensure_state()
    if group_id not in st.session_state["persistent"]:
        st.session_state["persistent"][group_id] = []
    st.session_state["persistent"][group_id].append(text)

def clear_persistent(group_id):
    """Clear one persistent data pool."""
    ensure_state()
    if group_id in st.session_state["persistent"]:
        st.session_state["persistent"][group_id] = []

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
    Cleaner formatter + special case handling for several tables.
    """

    # --- SPECIAL CASE: planet_designation ---
    if table_name == "planet_designation":
        try:
            return f"{row['letter']} - {row['noun']} - {row['number']}"
        except KeyError:
            vals = [v for k, v in row.items() if k != row.index.name]
            return " - ".join(str(v) for v in vals)

    # --- Special case: NPC first names ---
    if table_name == "npc_name":
        if "name" in row.index:
            return str(row["name"])
        for c in row.index:
            val = row[c]
            if pd.notna(val):
                return str(val)
        return "Unknown Name"

    # --- Special case: Random Site Name ---
    if table_name == "random_site_name":
        first = str(row.get("first_syllable", "")).strip()
        second = str(row.get("second_syllable", "")).strip()
        number = str(row.get("numeric", "")).strip()
        combined = f"{first}{second}-{number}"
        return combined

    # --- Special case: Size (hide modifier; we apply it to damage instead) ---
    if table_name == "size":
        ignore_cols = {"modifier"}
        parts = [
            str(row[c])
            for c in row.index
            if c not in ignore_cols and pd.notna(row[c])
        ]
        return " – ".join(parts) if parts else ""

    # --- Special case: Creature Intelligence (hide numeric value) ---
    if table_name == "creature_intelligence":
        desc = str(row.get("description", "")).strip()
        return desc

    # --- Special case: Unique Trait (show description only; mods apply in background) ---
    if table_name == "unique_trait":
        return str(row.get("description", "")).strip()

    # --- Special case: Creature Name (combine syllables, no hyphens) ---
    if table_name == "creature_name":
        ignore_cols = {"difficulty", "creature_type", "category"}
        syllables = [
            str(row[c])
            for c in row.index
            if c not in ignore_cols and pd.notna(row[c])
        ]
        raw = "".join(syllables)
        name = raw.replace(" ", "").replace("-", "").strip()
        if not name:
            return ""
        name = name.lower()
        return name[0].upper() + name[1:]

    # --- Special case: Stat Block (nice, labeled combat output) ---
    if table_name == "stat_block":
        def fmt(v):
            if pd.isna(v):
                return ""
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v)

        ensure_state()

        # From Size (already set when size table is rolled)
        size_flat_mod = st.session_state.get("damage_flat_modifier", 0) or 0
        # From creature_intelligence
        int_override = st.session_state.get("int_stat_override", None)
        # From enemy role (roles.csv)
        role_mods = st.session_state.get("role_mods") or {}
        # From unique trait (unique_trait.csv)
        trait_mods = st.session_state.get("unique_trait_mods", {}) or {}

        # Total flat damage modifier = Size + Role + Unique Trait
        try:
            role_flat = int(role_mods.get("damage_flat_mod", 0) or 0)
        except (TypeError, ValueError):
            role_flat = 0
        try:
            trait_flat = int(trait_mods.get("damage_flat_mod", 0) or 0)
        except (TypeError, ValueError):
            trait_flat = 0

        flat_mod_total = size_flat_mod + role_flat + trait_flat

        # Damage dice modifier from role (e.g. "-1D10")
        raw_ddm = role_mods.get("damage_dice_mod", "")
        dice_mod_expr = str(raw_ddm).strip().upper() if pd.notna(raw_ddm) else ""

        def apply_damage_dice_modifier(base_expr: str, dice_mod_expr: str) -> str:
            base = str(base_expr).strip()
            dm = str(dice_mod_expr).strip()
            if not base or not dm:
                return base_expr

            m_base = re.match(r'^\(?(\d*)D(\d+)\)?(.*)$', base, re.IGNORECASE)
            m_mod = re.match(r'^([+-])\s*(\d*)D(\d+)$', dm, re.IGNORECASE)

            if not m_base or not m_mod:
                return base_expr

            num_str = m_base.group(1)
            num = int(num_str) if num_str else 1
            die = int(m_base.group(2))
            tail = m_base.group(3)

            sign = m_mod.group(1)
            mod_num_str = m_mod.group(2)
            mod_num = int(mod_num_str) if mod_num_str else 1
            mod_die = int(m_mod.group(3))

            if mod_die != die:
                return base_expr + f" {dice_mod_expr}"

            num_new = num - mod_num if sign == "-" else num + mod_num
            if num_new < 1:
                num_new = 1

            has_paren = base.lstrip().startswith("(")
            body = f"{num_new}D{die}"
            if has_paren:
                body = f"({body})"

            return f"{body}{tail}"

        def adjust_damage_str(val):
            """Take a damage string like '(D10)+5' and apply role/trait/size modifiers."""
            s = fmt(val)
            if not s:
                return s

            # Dice-count changes from role (e.g. '-1D10')
            if dice_mod_expr:
                s = apply_damage_dice_modifier(s, dice_mod_expr)

            # Flat damage modifiers from Size + Role + Unique Trait
            if not flat_mod_total:
                return s

            try:
                mod = int(flat_mod_total)
            except (TypeError, ValueError):
                return s

            s_clean = s.strip()

            # Look for trailing +N or -N
            m = re.search(r'([+-])(\d+)\s*$', s_clean)
            if m:
                sign = m.group(1)
                base_n = int(m.group(2))
                if sign == "-":
                    base_n = -base_n

                new_n = base_n + mod

                if new_n == 0:
                    tail = ""
                elif new_n > 0:
                    tail = f"+{new_n}"
                else:
                    tail = str(new_n)

                base = s_clean[:m.start()]
                return base + tail

            # No existing flat term -> append
            if mod > 0:
                return f"{s_clean}+{mod}"
            elif mod < 0:
                return f"{s_clean}{mod}"
            return s_clean

        def apply_numeric_mod(base_val, mod_key):
            """Return base_val + role_mods[mod_key] + trait_mods[mod_key] if numeric; else base_val."""
            if pd.isna(base_val):
                return base_val
            try:
                base_int = int(base_val)
            except (TypeError, ValueError):
                return base_val

            try:
                role_delta = int(role_mods.get(mod_key, 0) or 0)
            except (TypeError, ValueError):
                role_delta = 0

            try:
                trait_delta = int(trait_mods.get(mod_key, 0) or 0)
            except (TypeError, ValueError):
                trait_delta = 0

            return base_int + role_delta + trait_delta

        lines: list[str] = []

        # ---------------- Core attributes ----------------
        stat_keys = ["str", "dex", "con", "wil", "int", "cha"]
        effective_stats = []
        for key in stat_keys:
            base_val = row.get(key, "")

            # INT override from creature_intelligence first
            if key == "int" and int_override is not None:
                base_val = int_override

            # Apply role + trait mods (str_mod, dex_mod, etc.)
            base_val = apply_numeric_mod(base_val, f"{key}_mod")
            effective_stats.append(fmt(base_val))

        lines.append("| STR | DEX | CON | WIL | INT | CHA |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        lines.append("| " + " | ".join(effective_stats) + " |")
        lines.append("")

        # ---------------- Derived stats ----------------
        derived_effective = []
        for key in ["wounds", "awareness", "armor", "defense"]:
            base_val = row.get(key, "")
            mod_key = None

            if key == "wounds":
                mod_key = "wounds_mod"
            elif key == "awareness":
                mod_key = "awareness_mod"
            elif key == "armor":
                mod_key = "armor_mod"
            elif key == "defense":
                mod_key = "defense_mod"

            if mod_key:
                base_val = apply_numeric_mod(base_val, mod_key)

            derived_effective.append(fmt(base_val))

        lines.append("| Wounds | Awareness | Armor | Defense |")
        lines.append("| --- | --- | --- | --- |")
        lines.append("| " + " | ".join(derived_effective) + " |")
        lines.append("")

        # ---------------- Attacks ----------------
        atk1 = row.get("attack_skill_1")
        atk2 = row.get("attack_skill_2")

        def fmt_signed(v):
            """Return +N / -N formatting for attack skill values."""
            if pd.isna(v):
                return ""
            try:
                i = int(v)
            except (TypeError, ValueError):
                return str(v)
            return f"{i:+d}"

        def eff_attack(base_val, slot):
            """
            slot 1 = melee modifiers
            slot 2 = ranged modifiers
            """
            if pd.isna(base_val):
                return base_val
            try:
                base_int = int(base_val)
            except (TypeError, ValueError):
                return base_val

            # Base attack modifier plus melee/ranged bias from role
            try:
                atk_mod = int(role_mods.get("attack_skill_mod", 0) or 0)
            except (TypeError, ValueError):
                atk_mod = 0
            try:
                melee_mod = int(role_mods.get("melee_attack_skill_mod", 0) or 0)
            except (TypeError, ValueError):
                melee_mod = 0
            try:
                ranged_mod = int(role_mods.get("ranged_attack_skill_mod", 0) or 0)
            except (TypeError, ValueError):
                ranged_mod = 0

            # Unique Trait can also modify attack skill
            try:
                trait_atk_mod = int(trait_mods.get("attack_skill_mod", 0) or 0)
            except (TypeError, ValueError):
                trait_atk_mod = 0

            if slot == 1:
                delta = atk_mod + melee_mod + trait_atk_mod
            else:
                delta = atk_mod + ranged_mod + trait_atk_mod

            return base_int + delta

        # Pull damage/range
        dmg1 = row.get("damage_1")
        dmg2 = row.get("damage_2")
        rng = row.get("range")

        dmg1_text = adjust_damage_str(dmg1)
        dmg2_text = adjust_damage_str(dmg2)

        # Role rule: brutes (and others) can forbid ranged entirely
        no_ranged = bool(role_mods.get("no_ranged_attacks"))

        # Does this stat block have a usable range value?
        has_range = (pd.notna(rng) and str(rng).strip() != "") and (not no_ranged)

        # Is there a second attack profile in the row?
        has_two_profiles = (pd.notna(atk2) or pd.notna(dmg2))

        attack_lines = []

        # --- Melee profile is always the first profile ---
        if pd.notna(atk1) or pd.notna(dmg1):
            atk1_melee = eff_attack(atk1, 1)
        attack_lines.append(
            f"- **Melee Attack:** Attack Skill {fmt_signed(atk1_melee)}, Damage {dmg1_text}"
        )

        # --- If ranged is allowed and range exists, show a ranged profile ---
        if has_range:
            if has_two_profiles:
                # Profile 2 is the ranged profile
                atk2_ranged = eff_attack(atk2, 2)
                ranged_dmg = dmg2_text
                ranged_atk = atk2_ranged
            else:
                # Only one profile exists (Easy often looks like this):
                # ranged uses profile 1's damage, but ranged attack modifiers
                atk1_ranged = eff_attack(atk1, 2)
                ranged_dmg = dmg1_text
                ranged_atk = atk1_ranged

            attack_lines.append(
                f"- **Ranged Attack:** Attack Skill {fmt_signed(ranged_atk)}, Damage {ranged_dmg}, Range {fmt(rng)}"
            )

        else:
            # No ranged (either no range stat, or role forbids ranged).
            # If a 2nd profile exists, treat it as an alternate MELEE option (not “secondary attack”).
            if has_two_profiles:
                atk2_melee = eff_attack(atk2, 1)
            attack_lines.append(
                f"- **Alternate Melee:** Attack Skill {fmt_signed(atk2_melee)}, Damage {dmg2_text}"
            )

        if attack_lines:
            lines.extend(attack_lines)

        # ---------------- Recovery Reactions ----------------
        reactions = row.get("reactions")
        if pd.notna(reactions):
            lines.append("")
            rr_lines = parse_randomize_reactions(reactions)
            if rr_lines:
                lines.append("**Recovery Reactions:**")
                lines.extend(rr_lines)
            else:
                lines.append(f"**Recovery Reactions:** {reactions}")

        # ---------------- Role details block ----------------
        if role_mods:
            role_lines = []
            role_label = st.session_state.get("current_enemy_role")

            summary = str(role_mods.get("role_summary", "") or "").strip()
            if role_label:
                if summary:
                    role_lines.append(f"**Role:** {role_label} — {summary}")
                else:
                    role_lines.append(f"**Role:** {role_label}")
            elif summary:
                role_lines.append(f"**Role Summary:** {summary}")

            try:
                hl_mod = int(role_mods.get("hit_location_roll_mod", 0) or 0)
            except (TypeError, ValueError):
                hl_mod = 0
            if hl_mod != 0:
                sign = "+" if hl_mod > 0 else ""
                role_lines.append(f"- Hit Location roll {sign}{hl_mod}")

            if bool(role_mods.get("disable_hit_location_table_when_attacked")):
                role_lines.append("- Ignore Hit Location table when this creature is attacked")

            if bool(role_mods.get("move_twice_per_turn")):
                role_lines.append("- Moves twice per turn")
            if bool(role_mods.get("disengage_no_opportunity_attack")):
                role_lines.append("- Can disengage without provoking opportunity attacks")

            if bool(role_mods.get("no_ranged_attacks")):
                role_lines.append("- Cannot make ranged attacks")
            if bool(role_mods.get("swarm_attacks_all_targets")):
                role_lines.append("- Swarm: attacks all characters in reach each round")

            raw_swarm = role_mods.get("swarm_size_override", "")
            swarm_override = ""
            if isinstance(raw_swarm, str):
                swarm_override = raw_swarm.strip()
            elif not pd.isna(raw_swarm):
                swarm_override = str(raw_swarm).strip()

            if swarm_override:
                role_lines.append(f"- Swarm Size Override: {swarm_override}")

            try:
                dmg_taken_mod = int(role_mods.get("damage_taken_flat_mod", 0) or 0)
            except (TypeError, ValueError):
                dmg_taken_mod = 0
            if dmg_taken_mod != 0:
                sign = "+" if dmg_taken_mod > 0 else ""
                role_lines.append(f"- Incoming damage {sign}{dmg_taken_mod}")

            try:
                cond_bonus = int(role_mods.get("conditional_attack_skill_mod", 0) or 0)
            except (TypeError, ValueError):
                cond_bonus = 0
            cond_cond = str(role_mods.get("conditional_attack_skill_condition", "") or "").strip()
            if cond_bonus and cond_cond:
                sign = "+" if cond_bonus > 0 else ""
                role_lines.append(f"- Conditional Attack: {sign}{cond_bonus} Attack Skill {cond_cond}")

            if bool(role_mods.get("use_psychic_ability_table")):
                role_lines.append("- Uses the Psychic Ability table for primary attacks")

            favor = str(role_mods.get("favor_text", "") or "").strip()
            if favor:
                role_lines.append(f"- Favors: {favor}")

            if role_lines:
                lines.append("")
                lines.append("**Role Details:**")
                lines.extend(role_lines)

        return "\n".join(lines)

    # --- Generic "title: description" formatting if present ---
    if "title" in row and "description" in row:
        title = str(row["title"]) if pd.notna(row["title"]) else ""
        desc = str(row["description"]) if pd.notna(row["description"]) else ""
        if title and desc:
            return f"{title}: {desc}"
        elif title:
            return title
        elif desc:
            return desc

    # --- Fallback: ignore filter columns and join the rest ---
    ignore_cols = {"difficulty", "creature_type"}
    parts = [
        str(row[c])
        for c in row.index
        if c not in ignore_cols and pd.notna(row[c])
    ]

    return " – ".join(parts) if parts else table_name

def _safe_int(val, default: int = 0) -> int:
    """Best-effort int conversion. Blank/NaN/non-numeric -> default."""
    try:
        if pd.isna(val):
            return default
    except Exception:
        pass
    try:
        s = str(val).strip()
        if s == "":
            return default
        f = float(s)
        return int(f)
    except Exception:
        return default


def remove_persistent_items(group_id: int, contains_any=None, startswith_any=None) -> int:
    """
    Remove items from st.session_state['persistent'][group_id] that match.
    Returns count removed.
    """
    ensure_state()
    if group_id not in st.session_state["persistent"]:
        return 0

    contains_any = contains_any or []
    startswith_any = startswith_any or []

    before = st.session_state["persistent"][group_id]
    after = []

    for item in before:
        s = str(item)
        if any(tok in s for tok in contains_any):
            continue
        if any(s.startswith(tok) for tok in startswith_any):
            continue
        after.append(item)

    st.session_state["persistent"][group_id] = after
    return len(before) - len(after)


def update_last_stat_block_persistent(group_id: int = 5) -> bool:
    """
    If a stat block has been rolled, rebuild it using current modifiers and
    replace the most recent stat block entry in Persistent[group_id].
    Returns True if it updated something.
    """
    ensure_state()
    last_row = st.session_state.get("last_stat_block_row")
    if not last_row:
        return False

    # rebuild stat block text using current modifiers
    try:
        rebuilt = format_row_for_display("stat_block", pd.Series(last_row))
    except Exception:
        return False

    label = st.session_state.get("last_stat_block_label")

    pool = st.session_state["persistent"].get(group_id, [])
    if not pool:
        return False

    idx = None

    # Prefer to replace the last matching labeled block if possible
    if label:
        needle = f"**{label}:**"
        for i in range(len(pool) - 1, -1, -1):
            if str(pool[i]).startswith(needle):
                idx = i
                break

    # Fallback: last entry that looks like a stat block
    if idx is None:
        for i in range(len(pool) - 1, -1, -1):
            s = str(pool[i])
            if "Stat Block" in s and "| STR |" in s:
                idx = i
                break

    if idx is None:
        return False

    # Preserve existing header line, replace the stat block body
    parts = str(pool[idx]).split("\n\n", 1)
    if len(parts) == 2:
        pool[idx] = parts[0] + "\n\n" + rebuilt
    else:
        pool[idx] = str(pool[idx]) + "\n\n" + rebuilt

    st.session_state["persistent"][group_id] = pool
    return True


def set_unique_trait_modifiers_from_row(row: pd.Series):
    """
    Read a row from unique_trait.csv and store its numeric modifiers in session state.
    If ability == -1, suppress enemy_ability output and remove any already persisted.
    """
    ensure_state()

    desc = str(row.get("description", "")).strip()
    st.session_state["unique_trait_desc"] = desc

    armor = row.get("armor")
    defense = row.get("defense")
    attack_skill = row.get("attack_skill")
    damage = row.get("damage")
    strength = row.get("str")
    dexterity = row.get("dex")
    constitution = row.get("con")
    willpower = row.get("wil")
    wounds = row.get("wounds")

    # Your CSV has STR/DEX rows incorrectly stored under armor/defense columns.
    # Auto-correct those two rows without forcing you to edit the CSV.
    if (pd.isna(strength) and pd.isna(dexterity)
        and ("STR" in desc.upper() and "DEX" in desc.upper())
        and (pd.notna(armor) or pd.notna(defense))):
        strength = armor
        dexterity = defense
        armor = 0
        defense = 0

    mods = {
        "armor_mod": _safe_int(armor, 0),
        "defense_mod": _safe_int(defense, 0),
        "attack_skill_mod": _safe_int(attack_skill, 0),
        "damage_flat_mod": _safe_int(damage, 0),
        "str_mod": _safe_int(strength, 0),
        "dex_mod": _safe_int(dexterity, 0),
        "con_mod": _safe_int(constitution, 0),
        "wil_mod": _safe_int(willpower, 0),
        "wounds_mod": _safe_int(wounds, 0),
    }

    st.session_state["unique_trait_mods"] = mods

    ability_flag = _safe_int(row.get("ability"), 0)
    st.session_state["suppress_enemy_ability"] = (ability_flag == -1)

    # If this trait suppresses enemy abilities, remove any already-persisted Enemy Ability lines
    if st.session_state["suppress_enemy_ability"]:
        remove_persistent_items(
            group_id=5,
            contains_any=["<strong>Enemy Ability:</strong>", "**Enemy Ability:**", "Enemy Ability:"]
        )

    # Also remove any previously persisted "Unique Trait" lines (legacy behavior)
    remove_persistent_items(
        group_id=5,
        contains_any=["<strong>Unique Trait:</strong>", "**Unique Trait:**", "Unique Trait:"]
    )

    # If a Stat Block has already been rolled & persisted, rebuild it now with the new modifiers
    update_last_stat_block_persistent(group_id=5)

def roll_table(table_name: str, group=None, log=False, option=None) -> str:
    ensure_state()

    try:
        df = load_table_df(table_name)
    except FileNotFoundError:
        return f"[ERROR] CSV for '{table_name}' not found."

    # =====================================================
    # Apply option filters – now with table-specific logic
    # =====================================================
    if option is not None:
        opt_str = str(option)

        # helper for category names: ignore spaces + hyphens, case-insensitive
        def norm(s: str) -> str:
            return "".join(str(s).lower().replace("-", " ").split())

        # ---------- Table-specific handling ----------

        # STAT BLOCK: difficulty names like "Easy", "Standard", etc.
        if table_name == "stat_block" and "difficulty" in df.columns:
            df = df[df["difficulty"].str.lower() == opt_str.lower()]

        # CREATURE TYPE: category values like "offplanet" / "planetsurface"
        elif table_name == "creature_type" and "category" in df.columns:
            norm_opt = norm(opt_str)
            df = df[df["category"].apply(norm) == norm_opt]

        # CREATURE LIMBS: "Terrestrial" vs "Aquatic"
        elif table_name == "creature_limbs" and "category" in df.columns:
            opt_low = opt_str.lower()
            if opt_low.startswith("aquatic"):
                df = df[df["category"].str.lower() == "aquatic"]
            else:
                # Terrestrial (or anything else) -> no filter
                pass

        # ---------- Generic handling for all other tables ----------
        else:
            # 1. Terrain difficulty tables with previous_hex
            if "previous_hex" in df.columns:
                df = df[df["previous_hex"].str.lower() == opt_str.lower()]

            # 2. Creature type filters
            elif "creature_type" in df.columns:
                df = df[df["creature_type"].str.lower() == opt_str.lower()]

            # 3. Difficulty filters (used by hacking and others)
            elif "difficulty" in df.columns:
                df = df[df["difficulty"] == opt_str]

            # 4. Category-based filters (Situation Nouns, etc.)
            elif "category" in df.columns:
                df = df[df["category"].str.lower() == opt_str.lower()]

            # 5. Gender-based filters (npc_name)
            elif "gender" in df.columns:
                df = df[df["gender"].str.lower() == opt_str.lower()]

    # =====================================================
    # Handle empty dataframe
    # =====================================================
    if df.empty:
        return f"[ERROR] No rows found for '{table_name}' with option '{option}'."

    # =====================================================
    # Random row → side effects → formatted text
    # =====================================================
    row = df.sample(1).iloc[0]

    # --- Side effects BEFORE formatting ---
    if table_name == "stat_block":
        # Save the rolled row so later modifiers can re-render it
        st.session_state["last_stat_block_row"] = row.to_dict()
        st.session_state["last_stat_block_label"] = f"{option} Stat Block" if option is not None else "Stat Block"

    if table_name == "unique_trait":
        # Applies background modifiers + may suppress Enemy Ability + may rebuild existing stat block
        set_unique_trait_modifiers_from_row(row)

    if table_name == "size" and "modifier" in row.index:
        try:
            st.session_state["damage_flat_modifier"] = int(row["modifier"])
        except (TypeError, ValueError):
            st.session_state["damage_flat_modifier"] = 0

    if table_name == "creature_intelligence" and "value" in row.index:
        st.session_state["int_stat_override"] = roll_int_from_expression(row["value"])

    # Format for display (unique_trait should return description only, if you added that special case)
    result = format_row_for_display(table_name, row)

    # If we just rolled an enemy role, capture its modifiers for later stat blocks
    if table_name == "enemy_role":
        set_role_modifiers_from_text(result)

    # If modifiers changed AFTER we already rolled a stat block, update it in persistent output.
    # (This is the "run changes in the background" behavior.)
    if table_name in ("enemy_role", "size", "creature_intelligence"):
        update_last_stat_block_persistent(group_id=5)

    # =====================================================
    # Persistent storage
    # =====================================================
    # Never persist Unique Trait as its own entry; it’s “background modifiers”
    if group is not None and table_name != "unique_trait":
        add_to_persistent(group, result)

    # =====================================================
    # Logging
    # =====================================================
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

st.markdown("""
<style>

    /* Reduce spacing between each persistent pool line */
    [data-testid="stSidebar"] .markdown-text-container p {
        margin-top: -6px !important;
        margin-bottom: -6px !important;
        line-height: 0.9 !important;
        padding: 0 !important;
    }

    /* Reduce spacing for the subtitles ("Persistent 1" etc.) */
    [data-testid="stSidebar"] h3, 
    [data-testid="stSidebar"] h2 {
        margin-top: 4px !important;
        margin-bottom: 4px !important;
        padding: 0 !important;
    }

    /* Tighter paragraph + text spacing overall */
    [data-testid="stSidebar"] * {
        line-height: 1.0 !important;
    }

</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>

    /* Sidebar paragraphs – a bit tighter than default, but readable */
    section[data-testid="stSidebar"] p {
        margin-top: 0px !important;
        margin-bottom: 2px !important;
        line-height: 1.15 !important;
        padding: 0 !important;
    }

    /* Sidebar text blocks */
    section[data-testid="stSidebar"] .stText {
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.15 !important;
    }

</style>
""", unsafe_allow_html=True)

st.markdown(
    """
    <style>
        ul.persist-tight {
            margin: 0px !important;
            padding-left: 20px !important;
        }
        ul.persist-tight li {
            margin: 0 0 2px 0 !important;   /* small gap between lines */
            padding: 0px !important;
            line-height: 1.1em !important;  /* slightly taller lines */
        }
    </style>
    """,
    unsafe_allow_html=True
)

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

    with col_left:

        # Area Connector  (Persistent group 2, log=True)
        with st.container(border=True):
            if st.button("Roll Area Connector", key="btn_area_connector"):
                st.success(roll_table("area_connector", group=2, log=True))

        # Site Exploration  (Persistent group 2, log=True)
        with st.container(border=True):
            if st.button("Roll Site Exploration", key="btn_site_exploration"):
                st.success(roll_table("site_exploration", group=2, log=True))

        # Xenoanthropological Artifact  (log=True)
        with st.container(border=True):
            if st.button("Roll Xenoanthropological Artifact", key="btn_xeno_artifact"):
                st.success(roll_table("xenoanthropological_artifact", log=True))

        # Activating Artifact  (log=True)
        with st.container(border=True):
            if st.button("Roll Activating Artifact", key="btn_activating_artifact"):
                st.success(roll_table("activating_artifact", log=True))

        # Hazard Manifestation  (log=True)
        with st.container(border=True):
            if st.button("Roll Hazard Manifestation", key="btn_hazard_manifestation"):
                st.success(roll_table("hazard_manifestation", log=True))

        # ✅ MOVED DOOR TYPE
        with st.container(border=True):
            if st.button("Roll Door Type", key="btn_door_type"):
                st.success(roll_table("door_type", log=True))

        # ✅ MOVED BEHIND DOOR
        with st.container(border=True):
            if st.button("Roll Behind Door", key="btn_behind_door"):
                st.success(roll_table("behind_door", log=True))

    # =====================================
    # ========== RIGHT COLUMN =============
    # =====================================

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

    # ---------- SECURITY MEASURE & TELEPORT ----------
    with col_right.container(border=True):
        st.markdown("### Security Measure & Teleport")

        # Individual buttons (now inside this box)
        if st.button("Roll Automatic Security Measure", key="btn_security"):
            sec = roll_table("automatic_security_measure", log=True)
            st.success(sec)

        if st.button("Roll Teleport Effect", key="btn_teleport"):
            tele = roll_table("teleport", log=True)
            st.success(tele)

        # -------------- Combined Roll --------------
        if st.button("Roll Security + Teleport", key="btn_security_full"):

            results = []

            # Step 1 — roll the security measure
            sec = roll_table("automatic_security_measure", log=False)
            results.append(f"- **Security Measure:** {sec}")
            add_to_log(f"Security Measure: {sec}")

            # Normalize lookup form
            sec_lower = sec.lower()

            # Step 2 — ONLY roll teleport if applicable
            if "teleport" in sec_lower:
                tele = roll_table("teleport", log=False)
                results.append(f"- **Teleport Result:** {tele}")
                add_to_log(f"Teleport Result: {tele}")

            final = "\n".join(results)
            st.success(final)

    # ---------- OCCURRENCE & SURROUNDINGS ----------
    with col_right.container(border=True):
        st.markdown("### Occurrence & Surrounding Details")

        # ---- Situation Category Input ----
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

        # -------------------- FULL SITUATION BUTTON --------------------
        if st.button("Roll Full Situation", key="btn_situation_full_occ"):
            verb = roll_table("situation_verb", log=False)
            noun = roll_table("situation_noun", option=situation_choice, log=False)

            # --- FIX: remove category prefix from noun result ---
            if "–" in noun:
                left, right = noun.split("–", 1)
                if left.strip().lower() == situation_choice.lower():
                    noun = right.strip()

            combined = f"({situation_choice}) {verb} – {noun}"

            add_to_log(f"Situation: {combined}")
            st.success(combined)

        # -------------------- FULL OCCURRENCE SET --------------------
        st.markdown("### Full Occurrence Set")

        if st.button("Roll Full Occurrence Set", key="btn_occ_full"):

            results = []

            # Step 1 — Roll Occurrence
            occ = roll_table("occurrence", log=False)
            occ_lower = occ.lower()

            results.append(f"- **Occurrence:** {occ}")
            add_to_log(f"Occurrence: {occ}")

            # Step 2 — Conditional Subrolls
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
                verb = roll_table("situation_verb", log=False)
                noun = roll_table("situation_noun", option=situation_choice, log=False)

                # --- FIX: strip category prefix ---
                if "–" in noun:
                    left, right = noun.split("–", 1)
                    if left.strip().lower() == situation_choice.lower():
                        noun = right.strip()

                results.append(f"- **Situation:** ({situation_choice}) {verb} – {noun}")
                add_to_log(f"Situation: ({situation_choice}) {verb} – {noun}")

             # Final Output
            final = "\n".join(results)
            st.success(final)

# ---------- TAB: PLANET ----------
with tabs[4]:

    st.header("Planet Generator")
    ensure_state()

    # ============================================================
    #  PLANET FEATURES — Top block (Designation, Atmosphere, etc.)
    # ============================================================
    with st.container(border=True):

        st.subheader("Planet Features")

        colA, colB = st.columns(2)

        # ------------------------
        # LEFT COLUMN
        # ------------------------
        with colA:

            if st.button("Planet Designation", key="btn_planet_designation"):
                result = roll_table("planet_designation", group=None, log=True)
                add_to_persistent(3, f"Designation: {result}")
                st.success(result)

            if st.button("Planet Diameter", key="btn_planet_diameter"):
                result = roll_table("planet_diameter", group=None, log=True)
                add_to_persistent(3, f"Diameter: {result}")
                st.success(result)

            if st.button("Planet Atmosphere", key="btn_planet_atmosphere"):
                result = roll_table("planet_atmosphere", group=None, log=True)
                add_to_persistent(3, f"Atmosphere: {result}")
                st.success(result)

            if st.button("Planet Climate", key="btn_planet_climate"):
                result = roll_table("planet_climate", group=None, log=True)
                add_to_persistent(3, f"Climate: {result}")
                st.success(result)

        # ------------------------
        # RIGHT COLUMN
        # ------------------------
        with colB:

            if st.button("Biome Diversity", key="btn_planet_biome_diversity"):
                result = roll_table("planet_biome_diversity", group=None, log=True)
                add_to_persistent(3, f"Biome Diversity: {result}")
                st.success(result)

            if st.button("What's in the Sky?", key="btn_whats_in_sky"):
                result = roll_table("whats_in_sky", group=None, log=True)
                add_to_persistent(3, f"Sky: {result}")
                st.success(result)

            if st.button("Day/Night Cycle", key="btn_day_night_cycle"):
                result = roll_table("day_night_cycle", group=None, log=True)
                add_to_persistent(3, f"Day/Night Cycle: {result}")
                st.success(result)

        st.markdown("---")

        # ============================================================
        # FULL PLANET BUTTON
        # ============================================================
        st.subheader("Full Planet (ALL 7 Tables)")

        if st.button("ROLL FULL PLANET", key="btn_full_planet"):

            designation = roll_table("planet_designation", group=None, log=False)
            diameter = roll_table("planet_diameter", group=None, log=False)
            atmosphere = roll_table("planet_atmosphere", group=None, log=False)
            climate = roll_table("planet_climate", group=None, log=False)
            diversity = roll_table("planet_biome_diversity", group=None, log=False)
            sky = roll_table("whats_in_sky", group=None, log=False)
            cycle = roll_table("day_night_cycle", group=None, log=False)

            # persistent
            add_to_persistent(3, f"Designation: {designation}")
            add_to_persistent(3, f"Diameter: {diameter}")
            add_to_persistent(3, f"Atmosphere: {atmosphere}")
            add_to_persistent(3, f"Climate: {climate}")
            add_to_persistent(3, f"Biome Diversity: {diversity}")
            add_to_persistent(3, f"Sky: {sky}")
            add_to_persistent(3, f"Day/Night Cycle: {cycle}")

            display = f"""
• **Designation:** {designation}  
• **Diameter:** {diameter}  
• **Atmosphere:** {atmosphere}  
• **Climate:** {climate}  
• **Biome Diversity:** {diversity}  
• **Sky:** {sky}  
• **Day/Night Cycle:** {cycle}  
"""
            st.success(display)

            log_entry = f"""
### Planet Summary
- **Designation:** {designation}
- **Diameter:** {diameter}
- **Atmosphere:** {atmosphere}
- **Climate:** {climate}
- **Biome Diversity:** {diversity}
- **Sky:** {sky}
- **Day/Night Cycle:** {cycle}
"""
            add_to_log(log_entry)

    # ============================================================
    # BIOME DETAILS SECTION
    # ============================================================
    st.markdown("### Biome Details")

    with st.container(border=True):

        first_landing = st.checkbox(
            "This is the first biome hex of a NEW planet", 
            key="chk_first_landing"
        )

        colL, colR = st.columns(2)

        # ------------------------------------------
        # LEFT — Biome, Activity, Threats
        # ------------------------------------------
        with colL:

            if st.button("Planet Biome", key="btn_planet_biome"):
                biome = roll_table("planet_biome", log=False)

                if "same as current biome" in biome.lower():
                    if first_landing:
                        biome = "Error: Cannot use SAME-AS-CURRENT-BIOME on first landing."
                add_to_persistent(4, f"Biome: {biome}")
                st.success(biome)

            if st.button("Biome Activity", key="btn_biome_act"):
                act = roll_table("biome_activity", log=True)
                add_to_persistent(4, f"Activity: {act}")
                st.success(act)

            if st.button("Known Threats", key="btn_biome_threats"):
                thr = roll_table("known_threats", log=True)
                add_to_persistent(4, f"Threats: {thr}")
                st.success(thr)

        # ------------------------------------------
        # RIGHT — FULL BIOME ROLL
        # ------------------------------------------
        with colR:

            if st.button("ROLL FULL BIOME", key="btn_full_biome"):
                biome = roll_table("planet_biome", log=False)
                if "same as current biome" in biome.lower() and first_landing:
                    biome = "Error: Cannot use SAME-AS-CURRENT-BIOME on first landing."

                act = roll_table("biome_activity", log=False)
                thr = roll_table("known_threats", log=False)

                add_to_persistent(4, f"Biome: {biome}")
                add_to_persistent(4, f"Activity: {act}")
                add_to_persistent(4, f"Threats: {thr}")

                block = f"""
• **Biome:** {biome}  
• **Activity:** {act}  
• **Known Threats:** {thr}  
"""
                st.success(block)

                add_to_log(f"""
### Biome Summary
- **Biome:** {biome}
- **Activity:** {act}
- **Known Threats:** {thr}
""")

    # ============================================================
    # TERRAIN DIFFICULTY
    # ============================================================
    st.markdown("### Terrain Difficulty")

    with st.container(border=True):

        terrain_options = [
            "Hazardous", "Convoluted", "Inhabited",
            "Biome-Dependent", "Easy Going"
        ]

        # This dropdown is the one you asked for!
        terrain_choice = st.selectbox(
            "Select Terrain Type:",
            terrain_options,
            key="terrain_drop"
        )

        if st.button("Roll Terrain Difficulty", key="btn_terrain"):
            result = roll_table("terrain_difficulty", option=terrain_choice, log=True)
            add_to_persistent(4, f"Terrain ({terrain_choice}): {result}")
            st.success(result)

    # ============================================================
    # BIOME-DEPENDENT TERRAIN TABLE
    # ============================================================
    st.markdown("### Biome-Dependent Terrain")

    with st.container(border=True):

        biome_list = [
            "Barren","Exotic","Frozen","Irradiated",
            "Lush","Scorched","Toxic","Urban",
            "Volcanic","Water"
        ]

        biome_choice = st.selectbox(
            "Biome:",
            biome_list,
            key="biome_dep_dropdown"
        )

        if st.button("Roll Biome-Dependent Terrain", key="btn_biome_dep"):
            df = load_table_df("biome_dependent_terrain")
            row = df[df["biome"] == biome_choice].sample(1).iloc[0]
            result = f"{row['result']}: {row['description']}"
            add_to_persistent(4, f"Biome-Dependent ({biome_choice}): {result}")
            add_to_log(f"Biome-Dependent Terrain: {result}")
            st.success(result)

    # -------------------------------
    # PLANETSIDE EXPLORATION LOGIC
    # -------------------------------

    st.markdown("### Planetside Exploration")

    with st.container(border=True):

        # Which biome’s hazards to use?
        biome_choice = st.selectbox(
            "Biome for Hazard Rolls:",
            [
                "Barren","Exotic","Frozen","Irradiated",
                "Lush","Scorched","Toxic","Urban",
                "Volcanic","Water"
            ],
            key="pexp_biome_choice"
        )

        # FULL EXPLORATION BUTTON
        if st.button("ROLL FULL EXPLORATION", key="btn_full_explore"):

            # STEP 1 — Roll on Planetside Exploration table
            exploration_result = roll_table("planetside_exploration", log=True)

            # Persist & display
            add_to_persistent(4, f"Planetside Exploration: {exploration_result}")

            st.success(f"**Exploration Result:** {exploration_result}")

            # -------------------------------------
            # STEP 2 — Branching logic
            # -------------------------------------

            # === FINDINGS ===
            if "findings" in exploration_result.lower():
                findings_result = roll_table("findings", log=True)
                add_to_persistent(4, f"Findings: {findings_result}")
                st.success(f"**Findings:** {findings_result}")

            # === HAZARDS ===
            elif "hazard" in exploration_result.lower():
                hazard_table = f"{biome_choice.lower()}_hazards"
                hazard_result = roll_table(hazard_table, log=True)
                add_to_persistent(4, f"Hazard ({biome_choice}): {hazard_result}")
                st.success(f"**Hazard:** {hazard_result}")

            # === SITE ===
            elif "site" in exploration_result.lower():
                add_to_log("Exploration: Found an Àrsaidh Site.")
                add_to_persistent(4, "Site Found: Roll full site in Mission tab.")
                st.success("**Site Found!** Use the Site Generator to roll the full site.")

            # === NOTHING ===
            elif "nothing" in exploration_result.lower():
                st.info("Nothing found in this hex.")
                add_to_persistent(4, "Exploration: Nothing found.")
    
            # Safety fallback
            else:
                st.warning("Exploration result not recognized — check the CSV formatting.")

    # ============================================================
    # BIOME-SPECIFIC SIGHTS & HAZARDS
    # ============================================================
    st.markdown("### Biome-Specific Sights & Hazards")

    biome_cols = st.columns(3)

    biome_buttons = [
        ("Barren Sights","barren_sights"), ("Barren Hazards","barren_hazards"),
        ("Exotic Sights","exotic_sights"), ("Exotic Hazards","exotic_hazards"),
        ("Frozen Sights","frozen_sights"), ("Frozen Hazards","frozen_hazards"),
        ("Irradiated Sights","irradiated_sights"), ("Irradiated Hazards","irradiated_hazards"),
        ("Lush Sights","lush_sights"), ("Lush Hazards","lush_hazards"),
        ("Scorched Sights","scorched_sights"), ("Scorched Hazards","scorched_hazards"),
        ("Toxic Sights","toxic_sights"), ("Toxic Hazards","toxic_hazards"),
        ("Urban Sights","urban_sights"), ("Urban Hazards","urban_hazards"),
        ("Volcanic Sights","volcanic_sights"), ("Volcanic Hazards","volcanic_hazards"),
        ("Water Sights","water_sights"), ("Water Hazards","water_hazards"),
    ]

    for i, (label, table) in enumerate(biome_buttons):
        col = biome_cols[i % 3]
        with col.container(border=True):
            if st.button(label, key=f"btn_{table}"):
                st.success(roll_table(table, group=4, log=True))

# ---------- TAB: NPC ----------
with tabs[5]:

    st.header("NPC Generator")
    ensure_state()

    # Helper to map npc_how_feels → which emotion table
    def resolve_feeling_table(feeling_text: str):
        txt = feeling_text.lower()
        if "surpris" in txt:
            return "npc_surprised", "Surprised"
        if "disgust" in txt:
            return "npc_disgusted", "Disgusted"
        if "bad" in txt:
            return "npc_bad", "Bad"
        if "sad" in txt:
            return "npc_sad", "Sad"
        if "fear" in txt:
            return "npc_fearful", "Fearful"
        if "happ" in txt:
            return "npc_happy", "Happy"
        if "angr" in txt:
            return "npc_angry", "Angry"
        return None, None

        # Helper to map rolled npc_gender text → name-gender key in npc_name.csv
    def resolve_name_gender_key(gender_text: str):
        txt = gender_text.lower()
        if "male" in txt:
            return "male"
        if "female" in txt:
            return "female"
        if "andro" in txt:
            return "androgynous"
        # Fallback: no filter, use any name
        return None

    # Convenience: store a labeled line in Persistent 6
    def persist_npc(label: str, value: str):
        add_to_persistent(6, f"{label}: {value}")

    # =====================================================
    # SECTION 1 — NPC IDENTITY (Combined 13)
    # =====================================================
    with st.container(border=True):
        st.subheader("NPC Identity (Core Profile)")

        col_left, col_right = st.columns(2)

        # ---------- LEFT: Behavior, Attitude, Reaction, Gender, Age ----------
        with col_left:

            if st.button("Behavior", key="btn_npc_behavior"):
                result = roll_table("npc_behavior", log=True)
                persist_npc("Behavior", result)
                st.success(result)

            if st.button("Attitude", key="btn_npc_attitude"):
                attitude = roll_table("npc_attitude", log=True)
                persist_npc("Attitude", attitude)
                st.success(attitude)

            # Reaction is explicitly "at the table" / interaction-based
            if st.button("Reaction (On-the-spot)", key="btn_npc_reaction"):
                reaction = roll_table("npc_reactions", log=True)
                # You can keep or remove this from persistent;
                # leaving it in can be nice to remember how they responded
                persist_npc("Reaction", reaction)
                st.success(reaction)

            if st.button("Gender", key="btn_npc_gender"):
                result = roll_table("npc_gender", log=True)
                persist_npc("Gender", result)
                st.success(result)

            if st.button("Age", key="btn_npc_age"):
                result = roll_table("npc_age", log=True)
                persist_npc("Age", result)
                st.success(result)

        # ---------- RIGHT: Name, Descriptor, Nature, Quirks ----------
        with col_right:

            if st.button("First Name", key="btn_npc_name"):
                first = roll_table("npc_name", log=True)
                persist_npc("First Name", first)
                st.success(first)

            if st.button("Surname", key="btn_npc_surname"):
                last = roll_table("npc_surname", log=True)
                persist_npc("Surname", last)
                st.success(last)

            if st.button("Descriptor", key="btn_npc_descriptor"):
                result = roll_table("npc_descriptor", log=True)
                persist_npc("Descriptor", result)
                st.success(result)

            if st.button("Nature", key="btn_npc_nature"):
                result = roll_table("npc_nature", log=True)
                persist_npc("Nature", result)
                st.success(result)

            if st.button("Quirks", key="btn_npc_quirks"):
                result = roll_table("npc_quirks", log=True)
                persist_npc("Quirks", result)
                st.success(result)

        st.markdown("---")

        # ---------- FULL NPC IDENTITY BUTTON ----------
        st.markdown("### Full NPC Identity (Combined 13)")

        if st.button("ROLL FULL NPC IDENTITY", key="btn_full_npc_identity"):
            behavior = roll_table("npc_behavior", log=False)
            attitude = roll_table("npc_attitude", log=False)
            gender = roll_table("npc_gender", log=False)
            age = roll_table("npc_age", log=False)
            descriptor = roll_table("npc_descriptor", log=False)

            # Use gender result to choose appropriate first name
            gender_key = resolve_name_gender_key(gender)
            if gender_key:
                first = roll_table("npc_name", log=False, option=gender_key)
            else:
                first = roll_table("npc_name", log=False)

            last = roll_table("npc_surname", log=False)
            nature = roll_table("npc_nature", log=False)
            quirks = roll_table("npc_quirks", log=False)
            full_name = f"{first} {last}"

            # Persist with labels
            persist_npc("Name", full_name)
            persist_npc("Behavior", behavior)
            persist_npc("Attitude", attitude)
            persist_npc("Gender", gender)
            persist_npc("Age", age)
            persist_npc("Descriptor", descriptor)
            persist_npc("Nature", nature)
            persist_npc("Quirks", quirks)

            # Display nicely (name on top)
            identity_block = f"""
• **Name:** {full_name}  
• **Gender:** {gender}  
• **Age:** {age}  
• **Descriptor:** {descriptor}  
• **Behavior:** {behavior}  
• **Attitude:** {attitude}  
• **Nature:** {nature}  
• **Quirks:** {quirks}  
"""
            st.success(identity_block)

            # Log entry
            log_entry = f"""
### NPC Identity
- **Name:** {full_name}
- **Gender:** {gender}
- **Age:** {age}
- **Descriptor:** {descriptor}
- **Behavior:** {behavior}
- **Attitude:** {attitude}
- **Nature:** {nature}
- **Quirks:** {quirks}
"""
            add_to_log(log_entry)

    # =====================================================
    # SECTION 2 — EMOTIONAL STATE (Combined 14)
    # =====================================================
    with st.container(border=True):
        st.subheader("NPC Emotional State")

        emo_col_left, emo_col_right = st.columns(2)

        # ---------- LEFT: How Feels + Full Emotional State ----------
        with emo_col_left:

            # Base table: npc_how_feels
            if st.button("How Does the NPC Feel?", key="btn_npc_how_feels"):
                how_feels = roll_table("npc_how_feels", log=True)
                persist_npc("How Feels", how_feels)

                table, label = resolve_feeling_table(how_feels)
                if table:
                    detail = roll_table(table, log=True)
                    persist_npc(f"{label} Detail", detail)
                    st.success(f"{how_feels}\n\n{label} Detail: {detail}")
                else:
                    st.success(how_feels)

            # Full emotional state (how_feels + specific table)
            if st.button("ROLL FULL EMOTIONAL STATE", key="btn_full_emotional"):
                how_feels = roll_table("npc_how_feels", log=False)
                persist_npc("How Feels", how_feels)

                table, label = resolve_feeling_table(how_feels)
                if table:
                    detail = roll_table(table, log=False)
                    persist_npc(f"{label} Detail", detail)

                    block = f"""
• **How They Feel:** {how_feels}  
• **{label} Detail:** {detail}  
"""
                    st.success(block)

                    log_entry = f"""
### NPC Emotional State
- **How They Feel:** {how_feels}
- **{label} Detail:** {detail}
"""
                    add_to_log(log_entry)
                else:
                    st.success(f"How They Feel: {how_feels}")
                    add_to_log(f"NPC Emotional State: {how_feels}")

        # ---------- RIGHT: Individual feeling tables ----------
        with emo_col_right:

            if st.button("Surprised Detail", key="btn_npc_surprised"):
                result = roll_table("npc_surprised", log=True)
                persist_npc("Surprised Detail", result)
                st.success(result)

            if st.button("Disgusted Detail", key="btn_npc_disgusted"):
                result = roll_table("npc_disgusted", log=True)
                persist_npc("Disgusted Detail", result)
                st.success(result)

            if st.button("Bad Detail", key="btn_npc_bad"):
                result = roll_table("npc_bad", log=True)
                persist_npc("Bad Detail", result)
                st.success(result)

            if st.button("Sad Detail", key="btn_npc_sad"):
                result = roll_table("npc_sad", log=True)
                persist_npc("Sad Detail", result)
                st.success(result)

            if st.button("Fearful Detail", key="btn_npc_fearful"):
                result = roll_table("npc_fearful", log=True)
                persist_npc("Fearful Detail", result)
                st.success(result)

            if st.button("Happy Detail", key="btn_npc_happy"):
                result = roll_table("npc_happy", log=True)
                persist_npc("Happy Detail", result)
                st.success(result)

            if st.button("Angry Detail", key="btn_npc_angry"):
                result = roll_table("npc_angry", log=True)
                persist_npc("Angry Detail", result)
                st.success(result)

    # =====================================================
    # SECTION 3 — INFO, RELATIONS, CONVERSATION, TALENT
    # =====================================================
    with st.container(border=True):
        st.subheader("NPC Info, Relations, & Talent")

        info_col_left, info_col_right = st.columns(2)

        # ---------- LEFT: Info, Motivation, Relations, Talent ----------
        with info_col_left:

            # npc_information DOES NOT go to persistent (per CSV)
            if st.button("Information (Type / Topic)", key="btn_npc_information"):
                result = roll_table("npc_information", log=True)
                st.success(result)

            if st.button("Motivation", key="btn_npc_motivation"):
                result = roll_table("npc_motivation", log=True)
                persist_npc("Motivation", result)
                st.success(result)

            if st.button("Relations", key="btn_npc_relations"):
                result = roll_table("npc_relations", log=True)
                persist_npc("Relations", result)
                st.success(result)

            if st.button("Talent", key="btn_npc_talent"):
                result = roll_table("npc_talent", log=True)
                persist_npc("Talent", result)
                st.success(result)

        # ---------- RIGHT: Conversation & Demoralized ----------
        with info_col_right:

            # demoralized reaction DOES NOT go to persistent (per CSV)
            if st.button("Demoralized Reaction", key="btn_npc_demoralized"):
                result = roll_table("npc_demoralized_reaction", log=True)
                st.success(result)

            if st.button("Random Conversation", key="btn_npc_random_convo"):
                result = roll_table("npc_random_conversation", log=True)
                persist_npc("Random Conversation", result)
                st.success(result)

            if st.button("Conversation Topic", key="btn_npc_convo_topic"):
                result = roll_table("npc_conversation_topic", log=True)
                persist_npc("Conversation Topic", result)
                st.success(result)

    # =====================================================
    # SECTION 4 — FULL NPC (BIG BUTTON)
    # =====================================================
    with st.container(border=True):
        st.subheader("Full NPC (Identity + Emotion + Motivation & Talent)")

        if st.button("ROLL FULL NPC", key="btn_full_npc"):

            # ---------- Identity ----------
            behavior = roll_table("npc_behavior", log=False)
            attitude = roll_table("npc_attitude", log=False)
            gender = roll_table("npc_gender", log=False)
            age = roll_table("npc_age", log=False)
            descriptor = roll_table("npc_descriptor", log=False)

            gender_key = resolve_name_gender_key(gender)
            if gender_key:
                first = roll_table("npc_name", log=False, option=gender_key)
            else:
                first = roll_table("npc_name", log=False)

            last = roll_table("npc_surname", log=False)
            nature = roll_table("npc_nature", log=False)
            quirks = roll_table("npc_quirks", log=False)
            full_name = f"{first} {last}"

            persist_npc("Name", full_name)
            persist_npc("Behavior", behavior)
            persist_npc("Attitude", attitude)
            persist_npc("Gender", gender)
            persist_npc("Age", age)
            persist_npc("Descriptor", descriptor)
            persist_npc("Nature", nature)
            persist_npc("Quirks", quirks)

            # ---------- Emotional State ----------
            how_feels = roll_table("npc_how_feels", log=False)
            persist_npc("How Feels", how_feels)

            emo_table, emo_label = resolve_feeling_table(how_feels)
            emo_detail = None
            if emo_table:
                emo_detail = roll_table(emo_table, log=False)
                persist_npc(f"{emo_label} Detail", emo_detail)

            # ---------- Motivation & Talent ----------
            motivation = roll_table("npc_motivation", log=False)
            relations = roll_table("npc_relations", log=False)
            talent = roll_table("npc_talent", log=False)

            persist_npc("Motivation", motivation)
            persist_npc("Relations", relations)
            persist_npc("Talent", talent)

            # ---------- DISPLAY BLOCK ----------
            emo_section = (
                f"- **How They Feel:** {how_feels}\n"
                + (f"- **{emo_label} Detail:** {emo_detail}\n" if emo_detail else "")
            )

            summary = f"""
### NPC Summary

**Identity**
- **Name:** {full_name}
- **Gender:** {gender}
- **Age:** {age}
- **Descriptor:** {descriptor}
- **Behavior:** {behavior}
- **Attitude:** {attitude}
- **Nature:** {nature}
- **Quirks:** {quirks}

**Emotional State**
{emo_section}

**Motivation & Social**
- **Motivation:** {motivation}
- **Relations:** {relations}
- **Talent:** {talent}
"""

            st.success(summary)
            add_to_log(summary)

# ---------- TAB: ANTAGONIST ----------
with tabs[6]:

    st.header("Antagonist Generator")
    ensure_state()

    # Convenience: store labeled lines in Persistent 5
    def persist_antagonist(label: str, value: str):
        """Store Antagonist pieces in Persistent 5.
        - For the Stat Block, keep label on its own line so the Markdown table renders.
        - For everything else, keep label and value on a single line to save space.
        """
        if "Stat Block" in label:
            # Stat blocks include Markdown tables and need a blank line after the label
            add_to_persistent(5, f"**{label}:**\n\n{value}")
        else:
            # Use HTML <strong> so bold works inside the <ul> we render later
            add_to_persistent(5, f"<strong>{label}:</strong> {value}")

    # --------------------------------------------------
    # Global options that drive several tables
    # --------------------------------------------------
    with st.container(border=True):
        st.markdown("### Antagonist Options")

        opt_col1, opt_col2, opt_col3 = st.columns(3)

        with opt_col1:
            env_choice = st.selectbox(
                "Environment (for Creature Type)",
                ["Planet Surface", "Off-Planet"],
                index=0,
                help="Used to filter the creature_type table."
            )

        with opt_col2:
            diff_choice = st.selectbox(
                "Threat Level / Difficulty",
                ["Easy", "Standard", "Elite", "Overwhelming"],
                index=1,
                help="Used by stat_block, enemy_role, guardian, known threats, and unique traits."
            )

        with opt_col3:
            limb_env_choice = st.selectbox(
                "Locomotion (for Limbs)",
                ["Terrestrial", "Aquatic"],
                index=0,
                help="Used to filter the creature_limbs table."
            )

    # --------------------------------------------------
    # SECTION 1 — CREATURE BASICS & STAT BLOCK
    # creature_type, size, stat_block, drive, intelligence, enemy_role
    # --------------------------------------------------
    with st.container(border=True):
        st.markdown("### Creature Basics & Stat Block")

        basics_left, basics_right = st.columns(2)

        with basics_left:
            if st.button("Creature Type", key="btn_creature_type"):
                result = roll_table("creature_type", group=5, log=True, option=env_choice)
                persist_antagonist("Creature Type", result)
                st.success(result)

            if st.button("Size", key="btn_creature_size"):
                result = roll_table("size", group=5, log=True)
                persist_antagonist("Size", result)
                st.success(result)

            if st.button("Creature Drive", key="btn_creature_drive"):
                result = roll_table("creature_drive", group=5, log=True)
                persist_antagonist("Drive", result)
                st.success(result)

            if st.button("Creature Intelligence", key="btn_creature_intelligence"):
                result = roll_table("creature_intelligence", group=5, log=True)
                persist_antagonist("Intelligence", result)
                st.success(result)

        with basics_right:
            if st.button("Stat Block", key="btn_creature_stat_block"):
                result = roll_table("stat_block", group=5, log=True, option=diff_choice)
                persist_antagonist(f"{diff_choice} Stat Block", result)
                st.success(result)

            if st.button("Enemy Role", key="btn_enemy_role"):
                # enemy_role depends on the chosen difficulty / stat block
                result = roll_table("enemy_role", group=5, log=True, option=diff_choice)
                persist_antagonist("Enemy Role", result)
                st.success(result)

    # --------------------------------------------------
    # SECTION 2 — TRAITS, ABILITIES, PSYCHIC POWERS
    # unique_trait, enemy_ability, psychic, psychic_ability
    # --------------------------------------------------
    with st.container(border=True):
        st.markdown("### Traits, Abilities & Psychic Powers")

        traits_left, traits_right = st.columns(2)

        # Easy vs Other for unique trait is driven by difficulty
        trait_option = "Easy" if diff_choice == "Easy" else "Other"

        with traits_left:
            if st.button("Unique Trait", key="btn_unique_trait"):
                # Roll it (shows description), but treat it as background modifiers
                result = roll_table("unique_trait", group=None, log=True, option=trait_option)
                st.success(result if result else "Unique Trait applied.")

                if st.session_state.get("suppress_enemy_ability", False):
                    st.warning("Enemy Ability suppressed by this Unique Trait (-1 Ability). Any existing Enemy Ability entry was removed.")

                # If a stat block is already in Persistent, refresh it
                if update_last_stat_block_persistent(group_id=5):
                    st.info("Stat Block updated with Unique Trait modifiers.")

            if st.button("Enemy Ability", key="btn_enemy_ability"):
                if st.session_state.get("suppress_enemy_ability", False):
                    st.warning("Enemy Ability suppressed by Unique Trait (-1 Ability).")
                else:
                    result = roll_table("enemy_ability", group=5, log=True)
                    persist_antagonist("Enemy Ability", result)
                    st.success(result)

        with traits_right:
            if st.button("Psychic Template", key="btn_psychic_template"):
                # This is the general psychic creature table (Combined 18)
                result = roll_table("psychic", group=5, log=True)
                persist_antagonist("Psychic Template", result)
                st.success(result)

            if st.button("Psychic Ability", key="btn_psychic_ability"):
                result = roll_table("psychic_ability", group=5, log=True)
                persist_antagonist("Psychic Ability", result)
                st.success(result)

    # --------------------------------------------------
    # SECTION 3 — APPEARANCE & ANATOMY
    # creature_appearance, cover, unique_feature, limbs, mouth, eyes_number, eyes
    # --------------------------------------------------
    with st.container(border=True):
        st.markdown("### Appearance & Anatomy")

        app_left, app_right = st.columns(2)

        with app_left:
            if st.button("Overall Appearance", key="btn_creature_appearance"):
                result = roll_table("creature_appearance", group=5, log=True)
                persist_antagonist("Appearance", result)
                st.success(result)

            if st.button("Cover / Natural Armor", key="btn_creature_cover"):
                result = roll_table("creature_cover", group=5, log=True)
                persist_antagonist("Cover", result)
                st.success(result)

            if st.button("Unique Feature", key="btn_creature_unique_feature"):
                result = roll_table("creature_unique_feature", group=5, log=True)
                persist_antagonist("Unique Feature", result)
                st.success(result)

        with app_right:
            if st.button("Limbs", key="btn_creature_limbs"):
                result = roll_table("creature_limbs", group=5, log=True, option=limb_env_choice)
                persist_antagonist("Limbs", result)
                st.success(result)

            if st.button("Mouth", key="btn_creature_mouth"):
                result = roll_table("creature_mouth", group=5, log=True)
                persist_antagonist("Mouth", result)
                st.success(result)

            if st.button("Eyes (Number + Detail)", key="btn_creature_eyes"):
                eyes_number = roll_table("creature_eyes_number", group=5, log=True)
                eyes_detail = roll_table("creature_eyes", group=5, log=True, option=eyes_number)
                persist_antagonist("Eyes", f"{eyes_number} — {eyes_detail}")
                st.success(f"{eyes_number} — {eyes_detail}")

    # --------------------------------------------------
    # SECTION 4 — NAMES
    # creature_name_syllables, creature_name
    # --------------------------------------------------
    with st.container(border=True):
        st.markdown("### Creature Names")

        name_left, name_right = st.columns(2)

        with name_left:
            if st.button("Random Creature Name", key="btn_creature_name"):
                result = roll_table("creature_name", group=5, log=True)
                persist_antagonist("Name", result)
                st.success(result)

        with name_right:
            if st.button("Name Syllables (DIY)", key="btn_creature_name_syllables"):
                # For GMs who want to assemble their own names
                result = roll_table("creature_name_syllables", group=5, log=True)
                st.success(result)

    # --------------------------------------------------
    # SECTION 5 — GUARDIANS & KNOWN THREATS
    # guardian, known_threat, plus behavior tables for the named threats
    # --------------------------------------------------
    with st.container(border=True):
        st.markdown("### Guardians & Known Threats")

        guard_col, threat_col = st.columns(2)

        with guard_col:
            guardian_diff = st.selectbox(
                "Guardian Difficulty",
                ["Easy", "Standard", "Elite", "Overwhelming"],
                index=1,
                key="guardian_diff"
            )
            if st.button("Roll Guardian", key="btn_guardian"):
                result = roll_table("guardian", group=5, log=True, option=guardian_diff)
                persist_antagonist("Guardian", result)
                st.success(result)

        with threat_col:
            threat_choice = st.selectbox(
                "Known Threat",
                ["Spitter", "Clobber", "Taker", "Psybane", "Bomber", "Cecaelia"],
                key="known_threat_choice"
            )
            if st.button("Roll Known Threat", key="btn_known_threat"):
                result = roll_table("known_threat", group=5, log=True, option=threat_choice)
                persist_antagonist("Known Threat", result)
                st.success(result)

            # Optional: specific behavior tables for each named threat
            if st.button("Threat Behavior", key="btn_threat_behavior"):
                behavior_table_map = {
                    "Spitter": "spitter_behavior",
                    "Clobber": "clobber_behavior",
                    "Taker": "taker_behavior",
                    "Psybane": "psybane_behavior",
                    "Bomber": "bomber_behavior",
                    "Cecaelia": "cecaelia_behavior",
                }
                table_name = behavior_table_map.get(threat_choice)
                if table_name:
                    result = roll_table(table_name, group=None, log=False)
                    st.success(result)
                else:
                    st.error("No behavior table found for that threat.")

    # --------------------------------------------------
    # SECTION 6 — DEMORALIZED REACTIONS
    # demoralized_reaction_humanoid, demoralized_reaction_other
    # (no persistent storage or logging)
    # --------------------------------------------------
    with st.container(border=True):
        st.markdown("### Demoralized Reactions")

        demo_h, demo_o = st.columns(2)

        with demo_h:
            if st.button("Humanoid", key="btn_demo_humanoid"):
                result = roll_table("demoralized_reaction_humanoid", log=False)
                st.success(result)

        with demo_o:
            if st.button("Other Creature", key="btn_demo_other"):
                result = roll_table("demoralized_reaction_other", log=False)
                st.success(result)

    # --------------------------------------------------
    # SECTION 7 — FULL ANTAGONIST (Combined 16)
    # Chains all the core tables into one creature and logs a single summary.
    # --------------------------------------------------
    st.markdown("---")
    st.markdown("### Full Antagonist (Combined 16)")

    if st.button("ROLL FULL ANTAGONIST", key="btn_full_antagonist"):
        
        ensure_state()
        # Reset per-creature overrides
        st.session_state["int_stat_override"] = None
        st.session_state["damage_flat_modifier"] = 0
        st.session_state["role_mods"] = None
        st.session_state["current_enemy_role"] = None

        # Reset unique-trait + stat-block tracking
        st.session_state["unique_trait_mods"] = {}
        st.session_state["unique_trait_desc"] = None
        st.session_state["suppress_enemy_ability"] = False
        st.session_state["last_stat_block_row"] = None
        st.session_state["last_stat_block_label"] = None

        # ----- Core identity & stats -----
        creature_name = roll_table("creature_name", log=False) or "Unknown Creature"
        size = roll_table("size", log=False)  # sets damage_flat_modifier (Size)
        creature_type = roll_table("creature_type", log=False, option=env_choice)
        drive = roll_table("creature_drive", log=False)
        intelligence = roll_table("creature_intelligence", log=False)

        # Roll role BEFORE trait/stat block so its modifiers are applied
        enemy_role = roll_table("enemy_role", log=False, option=diff_choice)

        # Traits first (unique_trait sets background modifiers and may suppress enemy ability)
        trait_option = "Easy" if diff_choice == "Easy" else "Other"
        _ = roll_table("unique_trait", log=False, option=trait_option)  # applies modifiers in background
        unique_trait_desc = st.session_state.get("unique_trait_desc")

        # Stat block now sees Size + Role + Unique Trait modifiers in session_state
        stat_block = roll_table("stat_block", log=False, option=diff_choice)

        # Enemy ability (skip if suppressed by unique trait)
        enemy_ability = None
        if not st.session_state.get("suppress_enemy_ability", False):
            enemy_ability = roll_table("enemy_ability", log=False)

        psychic_template = roll_table("psychic", log=False)
        psychic_ability = roll_table("psychic_ability", log=False)

        # Appearance & anatomy
        appearance = roll_table("creature_appearance", log=False)
        cover = roll_table("cover", log=False)
        unique_feature = roll_table("unique_feature", log=False)
        limbs = roll_table("limbs", log=False)
        mouth = roll_table("mouth", log=False)
        eyes_number = roll_table("eyes_number", log=False)
        eyes_detail = roll_table("eyes_detail", log=False)

        # ----- Persist entries (Unique Trait NOT persisted) -----
        persist_antagonist("Creature Name", creature_name)
        persist_antagonist("Size", size)
        persist_antagonist(f"{diff_choice} Stat Block", stat_block)
        persist_antagonist("Drive", drive)
        persist_antagonist("Intelligence", intelligence)
        persist_antagonist("Enemy Role", enemy_role)

        if enemy_ability is not None:
            persist_antagonist("Enemy Ability", enemy_ability)

        persist_antagonist("Psychic Template", psychic_template)
        persist_antagonist("Psychic Ability", psychic_ability)
        persist_antagonist("Appearance", appearance)
        persist_antagonist("Cover", cover)
        persist_antagonist("Unique Feature", unique_feature)
        persist_antagonist("Limbs", limbs)
        persist_antagonist("Mouth", mouth)
        persist_antagonist("Eyes", f"{eyes_number} — {eyes_detail}")

        # ----- Build a stat-block-style summary -----
        summary = f"""
### {creature_name.upper()}

**Creature Type:** {creature_type}  
**Size:** {size}  

**Drive:** {drive}  
**Intelligence:** {intelligence}  
**Enemy Role:** {enemy_role}  

**Stat Block — {diff_choice}**  
{stat_block}

**Traits & Abilities**  
{f'- **Enemy Ability:** {enemy_ability}  ' if enemy_ability else ''}  
- **Psychic Template:** {psychic_template}  
- **Psychic Ability:** {psychic_ability}  

**Appearance**  
- **Overall Appearance:** {appearance}  
- **Cover / Natural Armor:** {cover}  
- **Unique Feature:** {unique_feature}  
- **Limbs:** {limbs}  
- **Mouth:** {mouth}  
- **Eyes:** {eyes_number} — {eyes_detail}  
"""

        st.success(summary)
        add_to_log(summary)

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

        # Break the list into "inline" chunks and "block" items.
        # Inline items stay in a tight <ul>, multi-line items (like stat blocks)
        # are rendered as full Markdown blocks so tables etc. work.
        chunks = []
        current_inline = []

        for item in values:
            text = str(item)
            if "\n" in text:
                # flush any accumulated inline items
                if current_inline:
                    chunks.append(("inline", current_inline))
                    current_inline = []
                chunks.append(("block", text))
            else:
                current_inline.append(text)

        if current_inline:
            chunks.append(("inline", current_inline))

        # Render each chunk in order, preserving original sequence
        for kind, content in chunks:
            if kind == "inline":
                html_items = "".join([f"<li>{it}</li>" for it in content])
                st.sidebar.markdown(
                    f"""
                    <ul class="persist-tight">
                        {html_items}
                    </ul>
                    """,
                    unsafe_allow_html=True
                )
            else:  # "block"
                st.sidebar.markdown(content)

        if st.sidebar.button(f"Clear Persistent {group_id}"):
            clear_persistent(group_id)
            st.rerun()
