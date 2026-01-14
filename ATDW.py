from __future__ import annotations

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

    if "map_uirev" not in st.session_state:
        st.session_state["map_uirev"] = 0

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

    # --- Special case: Creature Limbs (only show description; never the category) ---
    if table_name == "creature_limbs":
        val = row.get("description", "")
        if pd.isna(val):
            return ""
        return str(val).strip()

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

        # --- Special case: Guardians & Known Threats (stat-block style output) ---
    if table_name in {"guardian", "known_threat"}:
        def fmt(v):
            if pd.isna(v):
                return ""
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v)

        def pretty_damage(expr: str) -> str:
            s = str(expr).strip()
            if not s or s.lower() == "nan":
                return ""
            s = s.replace(" ", "").upper()
            m = re.match(r"^(\d*)D(\d+)(.*)$", s)
            if not m:
                return str(expr).strip()
            n = m.group(1)
            die = m.group(2)
            tail = m.group(3) or ""
            dice = f"{n}D{die}" if n and n != "1" else f"D{die}"
            return f"({dice}){tail}"

        def split_abilities_text(raw: str) -> list[str]:
            raw = str(raw or "").strip()
            if not raw or raw.lower() == "nan":
                return []

            raw = re.sub(r"\s+", " ", raw)

            # Split on explicit separators first
            chunks = [c.strip() for c in re.split(r"[|;\n]+", raw) if c.strip()]

            parts: list[str] = []
            for ch in chunks:
                # Split before glued-on “note starters”
                for piece in re.split(r"(?<!^)(?=(?:Can|Immune)\b)", ch):
                    piece = piece.strip()
                    if not piece:
                        continue
                    # Split on “AbilityName The <creature> …”
                    parts.extend(re.split(r"(?<!^)(?=(?:[A-Z][A-Za-z0-9'’\-]+)\s+The\s)", piece))

            parts = [p.strip() for p in parts if p.strip()]

            # Pretty up "Aim The Arash..." -> "Aim — The Arash..."
            pretty: list[str] = []
            for p in parts:
                p = p.lstrip("-• ").strip()
                m = re.match(r"^([A-Z][A-Za-z0-9'’\-]+)\s+(The\b.*)$", p)
                if m:
                    pretty.append(f"{m.group(1)} — {m.group(2)}")
                else:
                    pretty.append(p)

            # De-dupe, preserve order
            out: list[str] = []
            seen = set()
            for p in pretty:
                key = p.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(p)
            return out

        # Header line
        name = ""
        if "guardian" in row.index:
            name = str(row.get("guardian", "") or "").strip()
        elif "name" in row.index:
            name = str(row.get("name", "") or "").strip()
        else:
            for c in row.index:
                if pd.notna(row[c]):
                    name = str(row[c]).strip()
                    break

        role = str(row.get("role", "") or "").strip()
        diff = str(row.get("difficulty", "") or "").strip()

        if role and diff:
            header = f"{name} — {role} ({diff})"
        elif role:
            header = f"{name} — {role}"
        elif diff:
            header = f"{name} ({diff})"
        else:
            header = name

        lines: list[str] = [header, ""]

        # Stats (6 columns)
        stat_keys = ["str", "dex", "con", "wil", "int", "cha"]
        stats = [fmt(row.get(k, "")) for k in stat_keys]
        lines.append("| STR | DEX | CON | WIL | INT | CHA |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        lines.append("| " + " | ".join(stats) + " |")
        lines.append("")

        # Derived
        derived_keys = ["wounds", "awareness", "armor", "defense"]
        derived = [fmt(row.get(k, "")) for k in derived_keys]
        lines.append("| Wounds | Awareness | Armor | Defense |")
        lines.append("| --- | --- | --- | --- |")
        lines.append("| " + " | ".join(derived) + " |")
        lines.append("")

        # Attacks (main + optional alt)
        atk_main = row.get("attack_skill", "")
        atk_alt = row.get("attack_skill_alt", "")
        dmg = pretty_damage(row.get("damage", ""))

        role_low = role.lower()
        main_label = "Ranged Attack" if role_low == "ranged" else "Melee Attack"
        alt_label = "Melee Attack" if main_label == "Ranged Attack" else "Ranged Attack"

        if fmt(atk_main) or dmg:
            lines.append(f"- **{main_label}:** Attack Skill +{fmt(atk_main)}, Damage {dmg}")

        if pd.notna(atk_alt) and str(atk_alt).strip().lower() not in ("", "nan"):
            cond = str(row.get("attack_skill_alt_condition", "") or "").strip()
            if cond.lower() == "nan":
                cond = ""
            suffix = f" ({cond})" if cond else ""
            lines.append(f"- **{alt_label}:** Attack Skill +{fmt(atk_alt)}, Damage {dmg}{suffix}")

        # Abilities + notes (one bullet each)
        abilities = split_abilities_text(row.get("abilities", ""))
        notes = split_abilities_text(row.get("notes", ""))

        abilities = [a for a in abilities if a.lower() != "no additional abilities at this tier"]

        if abilities or notes:
            lines.append("")
            lines.append("**Abilities:**")
            for a in abilities:
                lines.append(f"- {a}")
            for n in notes:
                lines.append(f"- {n}")

        return "\n".join(lines)

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

    # --- Special case: Guardian (pretty stat block output like Full Antagonist) ---
    if table_name == "guardian":
        def fmt(v):
            if pd.isna(v):
                return ""
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v)

        def nice_dice(expr):
            s = str(expr).strip()
            if not s or s.lower() == "nan":
                return ""
            m = re.match(r'^(\d*)D(\d+)([+-]\d+)?$', s, re.IGNORECASE)
            if not m:
                return s
            n = m.group(1)
            die = m.group(2)
            mod = m.group(3) or ""
            dice = f"{n}D{die}" if n and n != "1" else f"D{die}"
            return f"({dice}){mod}" if mod else f"({dice})"

        name = str(row.get("guardian", "") or "").strip()
        role = str(row.get("role", "") or "").strip()
        diff = str(row.get("difficulty", "") or "").strip()

        lines: list[str] = []

        header = []
        if name:
            header.append(name)
        if role:
            header.append(f"— {role}")
        if diff:
            header.append(f"({diff})")

        if header:
            lines.append(" ".join(header).strip())
            lines.append("")

        # ---------------- Core stats (split into 2 tables so it doesn’t wrap in narrow containers) ----------------
        stat_keys = ["str", "dex", "con", "wil", "int", "cha"]
        stats = [fmt(row.get(k, "")) for k in stat_keys]

        lines.append("| STR | DEX | CON |")
        lines.append("| --- | --- | --- |")
        lines.append("| " + " | ".join(stats[:3]) + " |")
        lines.append("")

        lines.append("| WIL | INT | CHA |")
        lines.append("| --- | --- | --- |")
        lines.append("| " + " | ".join(stats[3:]) + " |")
        lines.append("")

        # Derived stats
        derived_keys = ["wounds", "awareness", "armor", "defense"]
        derived = [fmt(row.get(k, "")) for k in derived_keys]

        lines.append("| Wounds | Awareness | Armor | Defense |")
        lines.append("| --- | --- | --- | --- |")
        lines.append("| " + " | ".join(derived) + " |")
        lines.append("")

        # Attacks
        atk_main = row.get("attack_skill")
        atk_alt = row.get("attack_skill_alt")
        raw_alt_cond = row.get("attack_skill_alt_condition", "")
        alt_cond = "" if (raw_alt_cond is None or (isinstance(raw_alt_cond, float) and pd.isna(raw_alt_cond))) else str(raw_alt_cond).strip()
        if alt_cond.lower() == "nan":
            alt_cond = ""

        dmg_main = nice_dice(row.get("damage", ""))
        dmg_alt_raw = row.get("damage_alt", row.get("damage", ""))  # optional future column
        dmg_alt = nice_dice(dmg_alt_raw)

        rng_main = row.get("range", "")
        rng_alt = row.get("range_alt", "")

        abilities_text = str(row.get("abilities", "") or "").strip()
        notes_text = str(row.get("notes", "") or "").strip()

        # Decide if the alt attack is ranged (handles Arash + Anansi cleanly)
        sniff = " ".join([role.lower(), abilities_text.lower(), notes_text.lower(), alt_cond.lower()])
        alt_is_ranged = False
        if role.strip().lower() == "ranged":
            alt_is_ranged = True
        if pd.isna(atk_main) and pd.notna(atk_alt):
            alt_is_ranged = True
        if any(k in sniff for k in ["shoot", "dart", "spit", "projectile", "ranged", "beam", "spray", "rifle", "bow"]):
            alt_is_ranged = True
        if str(rng_alt).strip() not in ("", "nan"):
            alt_is_ranged = True

        attack_lines = []

        if pd.notna(atk_main) and dmg_main:
            line = f"- **Melee Attack:** Attack Skill +{fmt(atk_main)}, Damage {dmg_main}"
            if str(rng_main).strip() not in ("", "nan"):
                line += f", Range {nice_dice(rng_main)}"
            attack_lines.append(line)

        if pd.notna(atk_alt) and dmg_alt:
            label = "Ranged Attack" if alt_is_ranged else "Alternate Melee"
            line = f"- **{label}:** Attack Skill +{fmt(atk_alt)}, Damage {dmg_alt}"
            if alt_cond:
                line += f" ({alt_cond})"
            if str(rng_alt).strip() not in ("", "nan"):
                line += f", Range {nice_dice(rng_alt)}"
            attack_lines.append(line)

        if attack_lines:
            lines.extend(attack_lines)

        # Abilities / notes
        if abilities_text and abilities_text.lower() not in {"no special abilities", "no additional abilities at this tier"}:
            lines.append("")
            lines.append("**Abilities:**")
            parts = [p.strip() for p in re.split(r"[|;]\s*", abilities_text) if p.strip()]
            if len(parts) <= 1:
                lines.append(f"- {abilities_text}")
            else:
                lines.extend([f"- {p}" for p in parts])

        if notes_text and notes_text.lower() != "nan":
            lines.append("")
            lines.append("**Notes:**")
            lines.append(f"- {notes_text}")

        return "\n".join(lines).strip()

    # --- Special case: Guardians & Known Threats (stat-block style output) ---
    if table_name in {"guardian", "known_threat"}:
        def fmt(v):
            if pd.isna(v):
                return ""
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v)

        def split_abilities(raw) -> list[str]:
            if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                return []
            s = str(raw).strip()
            if not s:
                return []

            # Treat common "none" phrases as empty
            if s.lower().startswith("no special") or s.lower().startswith("no additional"):
                return []

            # Normalize whitespace
            s = s.replace("\r", "\n")
            s = re.sub(r"[ \t]+", " ", s).strip()

            # First, split on obvious separators if present
            parts = [p.strip() for p in re.split(r"(?:\n+|\s*\|\s*|;\s*)", s) if p.strip()]

            # If it's still one blob, split on patterns like "Aim The ..." / "Explosive The ..."
            if len(parts) == 1:
                blob = parts[0]
                chunks = re.split(r"(?<!^)(?=(?:[A-Z][A-Za-z0-9'’\-]+)\s+The\s)", blob)
                # Also split before "Can ..." (often the last appended clause)
                parts2 = []
                for ch in chunks:
                    parts2.extend(re.split(r"(?<!^)(?=Can\s)", ch))
                parts = [p.strip() for p in parts2 if p.strip()]

            # Pretty up: "Aim The Arash..." -> "Aim — The Arash..."
            pretty = []
            for p in parts:
                p = p.lstrip("-• ").strip()
                m = re.match(r"^([A-Z][A-Za-z0-9'’\-]+)\s+(The\s+.+)$", p)
                if m:
                    pretty.append(f"{m.group(1)} — {m.group(2)}")
                else:
                    pretty.append(p)
            return pretty

        # Header line
        name_key = "guardian" if table_name == "guardian" else None
        name = row.get(name_key) if name_key and name_key in row.index else row.get("name", "")
        if not name:
            # fallback: first non-empty cell
            for c in row.index:
                if pd.notna(row[c]):
                    name = row[c]
                    break

        role = str(row.get("role", "") or "").strip()
        diff = str(row.get("difficulty", "") or "").strip()
        header = f"{name} — {role} ({diff})".strip(" —()")

        lines: list[str] = [header, ""]

        # --- Stats: split into two 3-column tables so it won't wrap inside st.success ---
        stats1 = [fmt(row.get("str", "")), fmt(row.get("dex", "")), fmt(row.get("con", ""))]
        stats2 = [fmt(row.get("wil", "")), fmt(row.get("int", "")), fmt(row.get("cha", ""))]

        lines.append("| STR | DEX | CON |")
        lines.append("| --- | --- | --- |")
        lines.append("| " + " | ".join(stats1) + " |")
        lines.append("")
        lines.append("| WIL | INT | CHA |")
        lines.append("| --- | --- | --- |")
        lines.append("| " + " | ".join(stats2) + " |")
        lines.append("")

        # --- Derived ---
        derived = [fmt(row.get("wounds", "")), fmt(row.get("awareness", "")), fmt(row.get("armor", "")), fmt(row.get("defense", ""))]
        lines.append("| Wounds | Awareness | Armor | Defense |")
        lines.append("| --- | --- | --- | --- |")
        lines.append("| " + " | ".join(derived) + " |")
        lines.append("")

        # --- Attacks ---
        melee_skill = row.get("attack_skill", None)
        ranged_skill = row.get("attack_skill_alt", None)
        ranged_cond = str(row.get("attack_skill_alt_condition", "") or "").strip()
        dmg = fmt(row.get("damage", ""))

        if pd.notna(melee_skill):
            lines.append(f"- **Melee Attack:** Attack Skill +{fmt(melee_skill)}, Damage {dmg}")

        if pd.notna(ranged_skill):
            line = f"- **Ranged Attack:** Attack Skill +{fmt(ranged_skill)}, Damage {dmg}"
            if ranged_cond:
                line += f" ({ranged_cond})"
            lines.append(line)

        # --- Abilities (split into separate bullets) ---
        abil_list = split_abilities(row.get("abilities", None))
        if abil_list:
            lines.append("")
            lines.append("**Abilities:**")
            for a in abil_list:
                lines.append(f"- {a}")

        # Optional notes
        notes = str(row.get("notes", "") or "").strip()
        if notes:
            lines.append("")
            lines.append(f"**Notes:** {notes}")

        return "\n".join(lines)
    
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

            # Swarm rule: only the largest swarms (Size 19–20) attack everyone at once
            if role_label == "Swarm" and st.session_state.get("swarm_all_targets", False):
                role_lines.append("- Swarm: attacks all characters in reach each round")

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

def _pick_article(word: str) -> str:
    w = (word or "").strip().lower()
    if not w:
        return "a"
    return "an" if w[0] in "aeiou" else "a"


def _clean_piece(s: str) -> str:
    """Trim and remove any extra '— category' cruft if it sneaks in."""
    if s is None:
        return ""
    s = str(s).strip()
    # If you ever get things like "Sexapedal – number", keep left side.
    for sep in ["—", "–", "-"]:
        if sep in s:
            left = s.split(sep, 1)[0].strip()
            # only take left side if it looks like the real value
            if left:
                s = left
    return s.strip()


def _roll_nonempty(table_name: str, option=None, max_tries: int = 30) -> str:
    """Roll until we get a real value (avoids NaN/blank rows in some CSVs)."""
    for _ in range(max_tries):
        val = roll_table(table_name, group=None, log=False, option=option)
        val = _clean_piece(val)

        bad = (
            not val
            or val.lower() in ("nan", "none")
            or val.startswith("[ERROR]")
            or val.lower() == table_name.lower()
        )
        if not bad:
            return val
    return ""

def _limbs_phrase(limbs: str, locomotion: str) -> str:
    l = _clean_piece(limbs)
    ll = l.lower()
    loc = (locomotion or "").lower()

    # Terrestrial style
    if not loc.startswith("aquatic"):
        if "sexapedal" in ll:
            return "six legs"
        if "quadrupedal" in ll:
            return "four legs"
        if "bipedal" in ll:
            # keep “upright” flavor if present
            return "two legs" + (" and stands mostly upright" if "upright" in ll else "")
        return ll  # fallback: whatever text you rolled

    # Aquatic style
    if ll:
        # e.g. "Tentacles" / "Flippers"
        return f"{ll.lower()} for locomotion"
    return ""


def _mouth_phrase(mouth: str) -> str:
    m = _clean_piece(mouth)
    ml = m.lower()
    if not ml:
        return ""
    if ml == "mouth":
        return "a simple mouth"
    if ml == "tentacles":
        return "a nest of feeding tentacles in place of a mouth"
    return f"a {ml} for a mouth"


def _eyes_phrase(eyes_number: str, eyes_detail: str) -> str:
    n = _clean_piece(eyes_number).lower()
    d = _clean_piece(eyes_detail).lower()

    if not n:
        return ""

    # singular tweak
    eye_word = "eye" if n == "one" else "eyes"

    if not d:
        return f"{n} {eye_word}"

    if d == "eyestalks":
        return f"{n} {eye_word} on eyestalks"

    # front-facing / side-facing / compound, etc.
    return f"{n} {d} {eye_word}"


def _feature_phrase(feature: str) -> str:
    f = _clean_piece(feature).lower()
    if not f:
        return ""
    if f in ("tail", "mane"):
        return f"a {f}"
    # "horns", "wings", "tendrils", "bright colors", etc.
    return f


def build_appearance_description(locomotion_choice: str) -> str:
    """
    Rolls creature appearance parts and returns ONE nice sentence.
    Uses locomotion_choice ("Terrestrial" / "Aquatic") to shape the limbs phrasing.
    """
    appearance = _roll_nonempty("creature_appearance")
    cover = _roll_nonempty("creature_cover")
    feature = _roll_nonempty("creature_unique_feature")
    limbs = _roll_nonempty("creature_limbs", option=locomotion_choice)
    mouth = _roll_nonempty("creature_mouth")
    eyes_n = _roll_nonempty("creature_eyes_number")
    eyes_d = _roll_nonempty("creature_eyes")

    ap = appearance.lower() if appearance else "creature"
    art = _pick_article(ap)

    intro = f"The creature is {art} {ap}"
    if (locomotion_choice or "").lower().startswith("aquatic"):
        intro += " adapted for aquatic life"

    parts = []
    if cover:
        parts.append(f"{cover.lower()} covering its body")
    lp = _limbs_phrase(limbs, locomotion_choice)
    if lp:
        parts.append(lp)
    mp = _mouth_phrase(mouth)
    if mp:
        parts.append(mp)
    ep = _eyes_phrase(eyes_n, eyes_d)
    if ep:
        parts.append(ep)
    fp = _feature_phrase(feature)
    if fp:
        parts.append(fp)

    if not parts:
        return intro + "."

    if len(parts) == 1:
        return intro + " with " + parts[0] + "."

    return intro + " with " + ", ".join(parts[:-1]) + f", and {parts[-1]}."

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

        # CREATURE LIMBS: locomotion drives which limb-set we roll from
        elif table_name == "creature_limbs" and "category" in df.columns:
            opt_low = opt_str.strip().lower()

            # Map your locomotion dropdown into the correct limbs category
            if opt_low.startswith("aquatic"):
                wanted = "aquatic"
            else:
                # Terrestrial (or anything else) => roll only leg-count rows
                wanted = "number"

            df = df[df["category"].astype(str).str.lower() == wanted]

            # Also drop blank/NaN descriptions (some tables have spacer rows)
            if "description" in df.columns:
                df = df[df["description"].notna() & (df["description"].astype(str).str.strip() != "")]

        elif table_name == "known_threat" and "name" in df.columns:
            df = df[df["name"].astype(str).str.lower() == opt_str.lower()]
        
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

    if table_name == "size":
        # Store this as the current flat damage modifier
        try:
            st.session_state["damage_flat_modifier"] = int(row.get("modifier", 0) or 0)
        except (TypeError, ValueError):
            st.session_state["damage_flat_modifier"] = 0

        # Try to infer which Size-table roll this row represents (for Swarm 19–20 logic)
        size_roll = None

        # Preferred: explicit roll column if your CSV has it
        for col in ("d20", "roll", "result", "range"):
            if col in row.index and pd.notna(row[col]):
                raw = str(row[col]).strip()
                m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", raw)  # accepts "19-20" or "19–20"
                if m:
                    size_roll = int(m.group(2))  # take the high end
                else:
                    try:
                        size_roll = int(raw)
                    except ValueError:
                        size_roll = None
                if size_roll is not None:
                    break

        # Fallback: if size.csv is a 20-row D20 table in order, use row position as the roll
        if size_roll is None:
            try:
                pos = df.index.get_loc(row.name)  # 0-based position
                if len(df) == 20:
                    size_roll = pos + 1
            except Exception:
                size_roll = None

        st.session_state["size_roll"] = size_roll
  
    if table_name == "creature_intelligence" and "value" in row.index:
        st.session_state["int_stat_override"] = roll_int_from_expression(row["value"])

    # Format for display (unique_trait should return description only, if you added that special case)
    result = format_row_for_display(table_name, row)

    # If we just rolled an enemy role, capture its modifiers for later stat blocks
    if table_name == "enemy_role":
        set_role_modifiers_from_text(result)

    if table_name == "size":
        # Save the displayed size text too (handy for debugging)
        st.session_state["current_size_text"] = result

        # Swarm rule: only “all targets” when Size-table roll is 19–20
        st.session_state["swarm_all_targets"] = bool(st.session_state.get("size_roll") in (19, 20))

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

import json

MAP_HEX_COUNT = 96
MAP_COLS = 10  # 10x10 layout (easy starting point)

def ensure_map_state():
    # Always normalize/repair the map (important when MAP_HEX_COUNT changes)
    default_hex = {
        "name": "",
        "biome": "",
        "terrain": "",
        "visited": False,
        "party": False,
        "site": False,
        "special": False,
        "notes": "",
        "last": ""
    }

    hm = st.session_state.get("hex_map", {}) or {}

    # Clean + prune to 1..MAP_HEX_COUNT (also handles string keys from JSON)
    cleaned = {}
    for k, v in hm.items():
        try:
            kk = int(k)
        except Exception:
            continue
        if 1 <= kk <= MAP_HEX_COUNT and isinstance(v, dict):
            cleaned[kk] = {**default_hex, **v}

    # Fill any missing hexes
    for i in range(1, MAP_HEX_COUNT + 1):
        cleaned.setdefault(i, default_hex.copy())

    st.session_state["hex_map"] = cleaned

    # Clamp selected hex so the app doesn't crash if it was 97–100 before
    try:
        sel = int(st.session_state.get("selected_hex", 1))
    except Exception:
        sel = 1
    if sel < 1 or sel > MAP_HEX_COUNT:
        sel = 1
    st.session_state["selected_hex"] = sel

    # Remember the last biome you selected in the map editor (used as default for new/unset hexes)
    if "map_default_biome" not in st.session_state:
        st.session_state["map_default_biome"] = ""

    # Remember the last terrain type you selected in the map editor
    if "map_default_terrain" not in st.session_state:
        st.session_state["map_default_terrain"] = "Landing"

def render_hex_plotly_map(hex_map: dict, selected_hex: int, zoom_level: float = 1.0, height_px: int | None = None):
    """
    Plotly-based hex map with real fill/border colors.

    Color rules:
      - visited  -> green fill
      - party    -> thick blue border
      - site     -> dashed border (drawn as Plotly shape)
      - special  -> purple inset ring
      - selected -> thick red outline (no fill)

    Click-to-select works on newer Streamlit (st.plotly_chart on_select).
    Returns: selected hex int if a click selection happened, else None.
    """
    import math
    import plotly.graph_objects as go
    # Keep Plotly component stable across reruns; bumping map_uirev resets UI state.
    uirev = st.session_state.get("map_uirev", 0)
    # --- Display scaling (user-controlled) ---
    zl = max(0.6, min(float(zoom_level or 1.0), 2.5))  # clamp
    marker_size = max(18, int(46 * zl))
    font_size = max(8, int(11 * zl))

    # --- Tighter hex grid spacing + correct last row (97-100) ---
    # --- Wider hex grid + correct last row (97-100) ---
    # 12 rows cover 1..96 because each 2-row pair contains 16 hexes (8 + 8) => 6 pairs => 96
    MAIN_ROWS = 12
    x_step = 1.05           # tighten horizontally (try 0.92–1.05)
    y_step = 0.92           # tighten vertically  (try 0.80–0.92)

    pos = {}
    render_order = []

    # Rows 0..11 => hexes 1..96 (8 per row, staggered)
    for r in range(MAIN_ROWS):
        pair = r // 2
        base = pair * 16  # 16 hexes per 2-row pair

        if r % 2 == 0:
            nums = [base + i for i in range(1, 16, 2)]   # 1,3,5,...,15  (8 hexes)
            x_offset = 0.0
        else:
            nums = [base + i for i in range(2, 17, 2)]   # 2,4,6,...,16  (8 hexes)
            x_offset = 0.5  # stagger

        y = -r * y_step
        for i, n in enumerate(nums):
            if 1 <= n <= 96:
                pos[n] = ((x_offset + i) * x_step, y)
                render_order.append(n)

    def marks_for(n: int) -> str:
        d = hex_map.get(n, {})
        marks = []
        if d.get("party"):
            marks.append("P")
        if d.get("site"):
            marks.append("S")
        if d.get("special"):
            marks.append("★")
        return " ".join(marks)

    xs, ys, labels = [], [], []
    party_x, party_y = [], []
    sel_x, sel_y = [], []
    fill_colors, line_colors, line_widths = [], [], []
    customdata = []

    for n in render_order:
        d = hex_map.get(n, {})
        x, y = pos[n]
        xs.append(x)
        ys.append(y)

        mk = marks_for(n)
        labels.append(f"{n}<br>{mk}" if mk else f"{n}")

        visited = bool(d.get("visited"))
        party = bool(d.get("party"))
        is_sel = (n == selected_hex)
        if is_sel:
            sel_x.append(x); sel_y.append(y)
        elif party:
            party_x.append(x); party_y.append(y)

        fill_colors.append("#d9f2d9" if visited else "#f2f2f2")

        line_colors.append("#666666")
        line_widths.append(2)

        customdata.append(n)

    fig = go.Figure()

    # Main filled hexes
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=labels,
            textposition="middle center",
            textfont=dict(size=font_size, color="#111"),
            customdata=customdata,
            hovertemplate="<b>Hex %{customdata}</b><extra></extra>",
            marker=dict(
                symbol="hexagon",
                size=marker_size,
                color=fill_colors,
                line=dict(color=line_colors, width=line_widths),
            ),
            showlegend=False,
        )
    )

    # Party ring (inner): draw a slightly smaller open-hex on top
    if party_x:
        fig.add_trace(
            go.Scatter(
                x=party_x,
                y=party_y,
                mode="markers",
                marker=dict(
                    symbol="hexagon-open",
                    size=40,  # smaller than 46 so it sits inside
                    line=dict(color="#2b59ff", width=5),
                ),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Selected ring (inner): smaller open-hex on top
    if sel_x:
        fig.add_trace(
            go.Scatter(
                x=sel_x,
                y=sel_y,
                mode="markers",
                marker=dict(
                    symbol="hexagon-open",
                    size=38,
                    line=dict(color="#d40000", width=6),
                ),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    
    # Special ring (purple inset)
    spec_x, spec_y = [], []
    for n in render_order:
        if hex_map.get(n, {}).get("special"):
            x, y = pos[n]
            spec_x.append(x)
            spec_y.append(y)

    if spec_x:
        fig.add_trace(
            go.Scatter(
                x=spec_x,
                y=spec_y,
                mode="markers",
            marker=dict(
                symbol="hexagon-open",
                size=40,
                line=dict(color="rgba(176,0,255,0.55)", width=3),
            ),
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Site dashed border (layout shapes)
    shapes = []
    rx = 0.58 * x_step
    ry = 0.58 * y_step

    for n in render_order:
        if not hex_map.get(n, {}).get("site"):
            continue

        x0, y0 = pos[n]
        pts = []
        for k in range(6):  # flat-top-ish hex outline
            ang = math.radians(60 * k)
            pts.append((x0 + rx * math.cos(ang), y0 + ry * math.sin(ang)))
        path = "M " + " L ".join([f"{px},{py}" for px, py in pts]) + " Z"

        is_sel = (n == selected_hex)
        party = bool(hex_map.get(n, {}).get("party"))

        if is_sel:
            line_color = "#d40000"
            line_width = 5
            dash = "solid"
        elif party:
            line_color = "#2b59ff"
            line_width = 4
            dash = "dash"
        else:
            line_color = "#666666"
            line_width = 3
            dash = "dash"

        shapes.append(
            dict(
                type="path",
                path=path,
                line=dict(color=line_color, width=line_width, dash=dash),
                fillcolor="rgba(0,0,0,0)",
                layer="above",
            )
        )

    # --- Zoom-out factor: bigger = tighter spacing (hexes closer together) ---
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)

    zoom = 1.35 / zl  # higher zl => smaller range => zoom in
    xc = (xmin + xmax) / 2
    yc = (ymin + ymax) / 2

    xr = (xmax - xmin) * zoom
    yr = (ymax - ymin) * zoom

    x_range = [xc - xr / 2, xc + xr / 2]
    y_range = [yc - yr / 2, yc + yr / 2]
    
    fig.update_layout(
        uirevision=uirev,
        shapes=shapes,
        margin=dict(l=0, r=0, t=0, b=0),
        height=int(height_px) if height_px else int((MAIN_ROWS + 3) * 90 * zl),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False, fixedrange=True, range=x_range),
        yaxis=dict(visible=False, fixedrange=True, range=y_range, scaleanchor="x", scaleratio=1),
    )

    # Render + capture selection (newer Streamlit). Older Streamlit will just render.
    selected = None
    try:
        uirev = st.session_state.get("map_uirev", 0)

        chart_state = st.plotly_chart(
            fig,
            use_container_width=True,
            on_select="rerun",
            selection_mode="points",
            key="hexmap_plotly",
        )

        sel = None
        if chart_state is None:
            sel = None
        elif isinstance(chart_state, dict):
            sel = chart_state.get("selection")
        else:
            sel = getattr(chart_state, "selection", None)

        points = None
        if isinstance(sel, dict):
            points = sel.get("points")
        else:
            points = getattr(sel, "points", None) if sel is not None else None

        if points:
            p0 = points[0]
            cd = p0.get("customdata") if isinstance(p0, dict) else None
            if isinstance(cd, (list, tuple)) and cd:
                cd = cd[0]
            if cd is None and isinstance(p0, dict):
                pi = p0.get("point_index")
                if isinstance(pi, int) and 0 <= pi < len(customdata):
                    cd = customdata[pi]
            if cd is not None:
                selected = int(cd)

    except TypeError:
        # Old Streamlit: no on_select/selection_mode support
        uirev = st.session_state.get("map_uirev", 0)

        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
            key="hexmap_plotly_static",
        )

    return selected

def render_hex_button_map(hex_map: dict, selected_hex: int):
    """
    Tight staggered layout:
    - Uses 4 hex columns plus a big "tail" spacer column so the row DOESN'T stretch across the page
    - Odd rows get a small left indent spacer
    - Last row renders 97 98 99 100 on the SAME row (no dangling)
    """
    def _draw_hex(n: int, col):
        d = hex_map.get(n, {})
        visited = bool(d.get("visited"))
        party = bool(d.get("party"))
        site = bool(d.get("site"))
        special = bool(d.get("special"))
        is_sel = (n == selected_hex)

        marks = []
        if party: marks.append("P")
        if site: marks.append("S")
        if special: marks.append("★")

        label = f"{n} {' '.join(marks)}".strip()

        tooltip = (
            f"HEXMAP|hex={n}|visited={int(visited)}|party={int(party)}|"
            f"site={int(site)}|special={int(special)}|selected={int(is_sel)}"
        )

        if col.button(
            label,
            key=f"hexbtn_{n}",
            help=tooltip,
            type="secondary",
            use_container_width=True
        ):
            st.session_state["selected_hex"] = n
            st.rerun()

    # Tuning knobs (these control "tightness")
    TAIL = 12.0    # bigger tail = tighter cluster on the left
    INDENT = 0.55  # odd-row indent spacer

    # --- 24 rows cover 1..96 (12 pairs * 8 = 96) ---
    for r in range(24):
        pair = r // 2
        base = pair * 8

        if r % 2 == 0:
            nums = [base + 1, base + 3, base + 5, base + 7]
            cols = st.columns([1, 1, 1, 1, TAIL], gap="small")  # 4 hex cols + tail spacer
            for i, n in enumerate(nums):
                _draw_hex(n, cols[i])
        else:
            nums = [base + 2, base + 4, base + 6, base + 8]
            cols = st.columns([INDENT, 1, 1, 1, 1, TAIL], gap="small")  # indent + 4 hex cols + tail
            for i, n in enumerate(nums):
                _draw_hex(n, cols[i + 1])

    # --- final row 97..100 (single row, aligned) ---
    final_nums = [97, 98, 99, 100]
    cols = st.columns([1, 1, 1, 1, TAIL], gap="small")
    for i, n in enumerate(final_nums):
        _draw_hex(n, cols[i])

def _get_query_hex():
    # Works across Streamlit versions
    try:
        val = st.query_params.get("hex", None)
        if isinstance(val, list):
            val = val[0] if val else None
    except Exception:
        qp = st.experimental_get_query_params()
        val = (qp.get("hex", [None]) or [None])[0]

    try:
        n = int(val) if val is not None else None
        if n and 1 <= n <= MAP_HEX_COUNT:
            return n
    except Exception:
        pass
    return None

def build_hexmap_html(selected_hex: int, hex_map: dict[int, dict], cols: int = MAP_COLS):
    # Layout: 10 rows of 10 hexes (row-major numbering). Odd rows are indented.
    rows = []
    rcount = (MAP_HEX_COUNT + cols - 1) // cols

    for r in range(rcount):
        start = r * cols + 1
        end = min(MAP_HEX_COUNT, start + cols - 1)
        row_nums = list(range(start, end + 1))

        row_class = "row odd" if (r % 2 == 1) else "row"
        tiles = []
        for n in row_nums:
            d = hex_map.get(n, {})
            classes = ["hex"]
            if d.get("visited"):
                classes.append("visited")
            if n == selected_hex:
                classes.append("selected")

            tooltip = f"Hex {n}"
            if d.get("name"):
                tooltip += f" — {d['name']}"
            if d.get("biome"):
                tooltip += f" ({d['biome']})"

            tiles.append(
                f'<a class="{" ".join(classes)}" href="?hex={n}" title="{tooltip}">{n}</a>'
            )

        rows.append(f'<div class="{row_class}">' + "".join(tiles) + "</div>")

    css = """
<style>
.atdw-hexmap { user-select: none; }
.atdw-hexmap .row { display:flex; gap:8px; margin:6px 0; }
.atdw-hexmap .row.odd { margin-left:26px; } /* half-hex-ish indent */

.atdw-hexmap .hex{
  width:46px; height:40px;
  display:flex; align-items:center; justify-content:center;
  text-decoration:none;
  font-size:12px; font-weight:600;
  color:#111;
  background:#f2f2f2;
  border:1px solid #666;
  clip-path: polygon(25% 6%, 75% 6%, 100% 50%, 75% 94%, 25% 94%, 0% 50%);
  box-shadow: 0 1px 0 rgba(0,0,0,0.15);
}
.atdw-hexmap .hex:hover{ transform: translateY(-1px); }

.atdw-hexmap .hex.visited{
  background:#d9f2d9;
  border-color:#3c7a3c;
}

.atdw-hexmap .hex.selected{
  outline: 3px solid #ffb000;
  border-color:#222;
}
</style>
"""
    return css + '<div class="atdw-hexmap">' + "".join(rows) + "</div>"


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
    "Planet", "NPC", "Antagonist", "Return to Base", "Log", "Map"
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

    /* Tighten the layout ONLY around our hex buttons */
    :where(
      div[data-testid="stHorizontalBlock"]:has(button[title^="HEXMAP|"], button[aria-label^="HEXMAP|"], button[data-tooltip^="HEXMAP|"]),
      div[data-testid="stHorizontalBlock"]:has(div[title^="HEXMAP|"] button, div[aria-label^="HEXMAP|"] button, div[data-tooltip^="HEXMAP|"] button),
      div[data-testid="stHorizontalBlock"]:has(span[title^="HEXMAP|"] button, span[aria-label^="HEXMAP|"] button, span[data-tooltip^="HEXMAP|"] button)
    ){
      gap: 0px !important;
      margin-top: -10px !important;  /* pulls rows closer (tweak -8 to -12 if needed) */
    }

    :where(
      div[data-testid="stHorizontalBlock"]:has(button[title^="HEXMAP|"], button[aria-label^="HEXMAP|"], button[data-tooltip^="HEXMAP|"])
    ) > div[data-testid="column"]{
      padding-left: 0px !important;
      padding-right: 0px !important;
    }

    :where(
    div[data-testid="stHorizontalBlock"]:has(button[title^="HEXMAP|"], button[aria-label^="HEXMAP|"], button[data-tooltip^="HEXMAP|"])
    ) button {
    display: block !important;
    margin: 0 auto !important;
    }

    :where(
      div[data-testid="stHorizontalBlock"]:has(button[title^="HEXMAP|"], button[aria-label^="HEXMAP|"], button[data-tooltip^="HEXMAP|"])
    ){
      justify-content: center !important;
    }

    :where(
      div[data-testid="stHorizontalBlock"]:has(button[title^="HEXMAP|"], button[aria-label^="HEXMAP|"], button[data-tooltip^="HEXMAP|"])
    ) > div[data-testid="column"]{
      flex: 0 0 60px !important;
      width: 60px !important;
      max-width: 60px !important;
      padding-left: 0 !important;
      padding-right: 0 !important;
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
            event_type = roll_table("random_travel_event_type", log=False).strip()

            type_to_table = {
                "Social": "social_travel_event",
                "Ship Malfunction": "ship_malfunction_travel_event",
                "Space Anomaly": "space_anomaly_travel_event",
                "Mental or Physical Issue": "mental_physical_travel_event",
            }

            subtable = type_to_table.get(event_type)

            # Fuzzy fallback (if wording ever changes)
            if subtable is None:
                et_lower = event_type.lower()
                for k, v in type_to_table.items():
                    if k.lower() in et_lower:
                        subtable = v
                        break

            # Last-resort fallback
            if subtable is None:
                subtable = random.choice(list(type_to_table.values()))

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
        - For the Stat Block (and Guardian blocks), keep label on its own line so Markdown tables render.
        - For everything else, keep label and value on a single line to save space.
        """
        if "Stat Block" in label or label == "Guardian":
            # Markdown tables need a blank line after the label
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
    # SECTION 7 — FULL ANTAGONIST (Combined 16)
    # Chains all the core tables into one creature and logs a single summary.
    # --------------------------------------------------
    st.markdown("---")
    st.markdown("### Full Antagonist")

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

        # Make sure old psychic lines can’t “stick”
        remove_persistent_items(5, startswith_any=["Psychic Template", "Psychic Ability"])

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

        # Stat block now sees Size + Role + Unique Trait modifiers in session_state
        stat_block = roll_table("stat_block", log=False, option=diff_choice)
        
        # Enemy abilities (roll count depends on difficulty; skip if suppressed by unique trait)
        enemy_abilities = []
        if not st.session_state.get("suppress_enemy_ability", False):
            n_ability = {"Easy": 1, "Standard": 1, "Elite": 2, "Overwhelming": 3}.get(diff_choice, 1)
            for _ in range(n_ability):
                enemy_abilities.append(roll_table("enemy_ability", log=False))

        # Psychic ability ONLY if the rolled role is Psychic (role flag)
        psychic_ability = None
        role_mods = st.session_state.get("role_mods") or {}
        if bool(role_mods.get("use_psychic_ability_table")):
            psychic_ability = roll_table("psychic_ability", log=False)

        # Appearance & anatomy (combined into one description)
        appearance_desc = build_appearance_description(limb_env_choice)

        # ----- Persist entries (Unique Trait NOT persisted) -----
        persist_antagonist("Creature Name", creature_name)
        persist_antagonist("Size", size)
        persist_antagonist(f"{diff_choice} Stat Block", stat_block)
        persist_antagonist("Drive", drive)
        persist_antagonist("Intelligence", intelligence)
        persist_antagonist("Enemy Role", enemy_role)

        if enemy_abilities:
            if len(enemy_abilities) == 1:
                persist_antagonist("Enemy Ability", enemy_abilities[0])
            else:
                for i, ab in enumerate(enemy_abilities, 1):
                    persist_antagonist(f"Enemy Ability {i}", ab)

        if psychic_ability is not None:
            persist_antagonist("Psychic Ability", psychic_ability)

        persist_antagonist("Appearance", appearance_desc)

        # ----- Build a stat-block-style summary -----
        psychic_line = f"- **Psychic Ability:** {psychic_ability}  " if psychic_ability else ""

        enemy_abilities_md = ""
        if enemy_abilities:
            if len(enemy_abilities) == 1:
                enemy_abilities_md = f"- **Enemy Ability:** {enemy_abilities[0]}  "
            else:
                enemy_abilities_md = "\n".join(
                    [f"- **Enemy Ability {i}:** {ab}  " for i, ab in enumerate(enemy_abilities, 1)]
                )
        
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
{enemy_abilities_md}  
{psychic_line}

**Appearance**  
- {appearance_desc}  

"""

        st.success(summary)
        add_to_log(summary)

    # --------------------------------------------------
    # SECTION 5 — GUARDIANS & KNOWN THREATS
    # guardian, known_threat, plus behavior tables for the named threats
    # --------------------------------------------------

    # One “preview/output” area for whatever you rolled most recently in this section
    if "section5_preview" not in st.session_state:
        st.session_state["section5_preview"] = ""

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
                # IMPORTANT: group=None so it DOES NOT auto-add to Persistent 5
                result = roll_table("guardian", group=None, log=True, option=guardian_diff)
                persist_antagonist("Guardian", result)  # This is the ONLY persistence
                st.session_state["section5_preview"] = result

        with threat_col:
            threat_choice = st.selectbox(
                "Known Threat",
                ["Spitter", "Clobber", "Taker", "Psybane", "Bomber", "Cecaelia"],
                key="known_threat_choice"
            )

            if st.button("Roll Known Threat", key="btn_known_threat"):
                # IMPORTANT: group=None so it DOES NOT auto-add to Persistent 5
                result = roll_table("known_threat", group=None, log=True, option=threat_choice)
                persist_antagonist("Known Threat", result)  # Only persistence
                st.session_state["section5_preview"] = result

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
                    st.session_state["section5_preview"] = result
                else:
                    st.error("No behavior table found for that threat.")

    # FULL-WIDTH output BELOW the section box (and keeps your green success background)
    if st.session_state.get("section5_preview"):
        st.success(st.session_state["section5_preview"])

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
                ensure_state()
                st.session_state["role_mods"] = None
                st.session_state["current_enemy_role"] = None
    
                # If the last thing you rolled was Psychic, don’t let it “stick”
                remove_persistent_items(5, startswith_any=["Psychic Template", "Psychic Ability"])
    
                result = roll_table("enemy_role", group=5, log=True, option=diff_choice)
                persist_antagonist("Enemy Role", result)
    
                role_mods = st.session_state.get("role_mods") or {}
                if bool(role_mods.get("use_psychic_ability_table")):
                    psychic_ability = roll_table("psychic_ability", group=5, log=True)
                    persist_antagonist("Psychic Ability", psychic_ability)
                    st.info("Psychic role rolled → Psychic Ability added.")

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
            st.markdown("##### Combat Behavior (optional)")

            behavior_role = st.selectbox(
                "Role for behavior",
                ["Brute", "Lurker", "Ranged", "Swarm", "Psychic"],
                key="behavior_role_select"
            )

            if st.button("Roll Combat Behavior", key="btn_combat_behavior"):
                role_key = behavior_role.lower()

                # These are the filenames/table names we will try.
                # Keep the first one that exists.
                candidates = [
                    role_key,                       # brute.csv, lurker.csv, etc.
                    f"{role_key}_behavior",         # brute_behavior.csv
                    f"combat_behavior_{role_key}"   # combat_behavior_brute.csv
                ]

                table_name = None
                for t in candidates:
                    try:
                        _ = load_table_df(t)   # just testing if file exists
                        table_name = t
                        break
                    except FileNotFoundError:
                        continue
    
                if table_name is None:
                    st.error(
                        f"No behavior CSV found for {behavior_role}. "
                        f"Tried: {', '.join(candidates)}"
                    )
                else:
                    result = roll_table(table_name, group=5, log=True)
                    persist_antagonist(f"Combat Behavior ({behavior_role})", result)
                    st.success(result)

            st.markdown("##### Psychic Ability (Psychic role only)")
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

# ---------- TAB: RETURN TO BASE ----------
with tabs[7]:

    st.header("Return to Base (RTB)")
    ensure_state()

    col_left, col_right = st.columns(2)

    # Artifact Value (p.153)
    with col_left.container(border=True):
        st.markdown("### Artifact Value")
        if st.button("Roll Artifact Value", key="btn_rtb_artifact_value"):
            st.success(roll_table("artifact_value", log=True))

    # Red Astroid Event (p.346)
    with col_right.container(border=True):
        st.markdown("### Red Astroid Event")
        if st.button("Roll Red Astroid Event", key="btn_rtb_red_astroid_event"):
            st.success(roll_table("red_astroid_event", log=True))

    # Carousing (p.334–335)  ✅ FIXED: uses "carousing" to match carousing.csv
    with col_left.container(border=True):
        st.markdown("### Carousing")
        if st.button("Roll Carousing", key="btn_rtb_carousing"):
            st.success(roll_table("carousing", log=True))

    # Colorful Locals (p.347)
    with col_right.container(border=True):
        st.markdown("### Colorful Locals")
        if st.button("Roll Colorful Locals", key="btn_rtb_colorful_locals"):
            st.success(roll_table("colorful_locals", log=True))

    # Corporate News & Rumors (p.348–349)
    with col_left.container(border=True):
        st.markdown("### Corporate News & Rumors")
        if st.button("Roll Corporate News / Rumor", key="btn_rtb_corporate_news_rumors"):
            st.success(roll_table("corporate_news_rumors", log=True))

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

            # ROW: icon button + entry text + delete button
            row_left, row_mid, row_del = st.columns([1, 12, 3])

            # ---------- LEFT COLUMN: Notepad icon ----------
            with row_left:
                if st.button("📝", key=f"note_icon_{idx}", help="Add/Edit Note"):
                    st.session_state["active_note"] = idx

            # ---------- MIDDLE COLUMN: Log text with inline note ----------
            if note:
                row_mid.markdown(f"{text}  \n📝 *{note}*")
            else:
                row_mid.markdown(text)

            # ---------- RIGHT COLUMN: Delete button (far right) ----------
            with row_del:
                if st.button("🗑️ Delete", key=f"delete_log_{idx}", help="Delete this log entry"):
                    st.session_state["log"].pop(idx)

                    # keep the note editor stable if something earlier gets deleted
                    active = st.session_state.get("active_note")
                    if active is not None:
                        if active == idx:
                            del st.session_state["active_note"]
                        elif active > idx:
                            st.session_state["active_note"] = active - 1
        
                    st.rerun()

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

# ---------- TAB: Map ----------
with tabs[9]:
    st.markdown("## Map")
    ensure_map_state()

    # Helper: append a block of text to this hex's notes (SAFE with Streamlit widgets)
    if "force_notes_refresh_for" not in st.session_state:
        st.session_state["force_notes_refresh_for"] = None

    def append_to_hex_notes(hex_id: int, text_block: str):
        hex_map_local = st.session_state["hex_map"]

        current = (hex_map_local[hex_id].get("notes") or "").rstrip()
        new_notes = (current + "\n\n" + text_block).strip() if current else text_block.strip()

        hex_map_local[hex_id]["notes"] = new_notes
        st.session_state["hex_map"] = hex_map_local

        # Tell the UI to refresh the notes widget value on the NEXT rerun
        st.session_state["force_notes_refresh_for"] = hex_id

    col_map, col_info = st.columns([3, 1], gap="large")

    # -----------------------
    # RIGHT FIRST: Hex editor (so changes apply BEFORE drawing the map)
    # -----------------------
    with col_info:
        selected_hex = st.session_state["selected_hex"]
        hex_map = st.session_state["hex_map"]
        d = hex_map[selected_hex]

        st.subheader(f"Hex {selected_hex}")

        visited = st.checkbox("Visited", value=bool(d.get("visited")), key=f"map_v_{selected_hex}")
        party_here = st.checkbox("Party Here", value=bool(d.get("party")), key=f"map_party_{selected_hex}")
        site_present = st.checkbox("Site Present", value=bool(d.get("site")), key=f"map_site_{selected_hex}")
        special_flag = st.checkbox("Special (flag this hex)", value=bool(d.get("special")), key=f"map_special_{selected_hex}")

        name = st.text_input("Name / Label", value=d.get("name",""), key=f"map_name_{selected_hex}")

        biome_list = ["", "Barren","Exotic","Frozen","Irradiated","Lush","Scorched","Toxic","Urban","Volcanic","Water"]

        # If this hex doesn't have a biome yet, default to the last biome you picked.
        stored_biome = (d.get("biome", "") or "").strip()
        default_biome = (st.session_state.get("map_default_biome", "") or "").strip()
        initial_biome = stored_biome or default_biome

        def _on_map_biome_change(hex_id: int):
            st.session_state["map_default_biome"] = st.session_state.get(f"map_biome_{hex_id}", "")

        biome = st.selectbox(
            "Biome (for hazard rolls)",
            biome_list,
            index=biome_list.index(initial_biome) if initial_biome in biome_list else 0,
            key=f"map_biome_{selected_hex}",
            on_change=_on_map_biome_change,
            args=(selected_hex,),
        )

        # -----------------------
        # TERRAIN DIFFICULTY (Map tab)
        # -----------------------
        st.markdown("### Terrain Difficulty")

        with st.container(border=True):

            # Build dropdown options from terrain_difficulty.csv (uses 'previous_hex', including 'Landing')
            try:
                td_df = load_table_df("terrain_difficulty")
                raw_opts = td_df["previous_hex"].dropna().astype(str).tolist()
                terrain_options = list(dict.fromkeys(raw_opts))  # unique, preserve file order
            except Exception:
                terrain_options = ["Landing", "Hazardous", "Convoluted", "Inhabited", "Biome-Dependent", "Easy Going"]

            # Put Landing first so the dropdown starts there on a fresh session
            if "Landing" in terrain_options:
                terrain_options = ["Landing"] + [o for o in terrain_options if o != "Landing"]

            stored_terrain = (d.get("terrain", "") or "").strip()
            default_terrain = (st.session_state.get("map_default_terrain", "Landing") or "Landing").strip()
            initial_terrain = stored_terrain or default_terrain or "Landing"

            def _on_map_terrain_change(hex_id: int):
                st.session_state["map_default_terrain"] = st.session_state.get(f"map_terrain_{hex_id}", "Landing")

            terrain = st.selectbox(
                "Select Terrain Type:",
                terrain_options,
                index=terrain_options.index(initial_terrain) if initial_terrain in terrain_options else 0,
                key=f"map_terrain_{selected_hex}",
                on_change=_on_map_terrain_change,
                args=(selected_hex,),
            )

            if st.button("Roll Terrain Difficulty", key=f"btn_map_td_{selected_hex}"):
                td_result = roll_table("terrain_difficulty", option=terrain, log=True)
                add_to_persistent(4, f"Hex {selected_hex} — Terrain ({terrain}): {td_result}")
                add_to_log(f"Hex {selected_hex} — Terrain ({terrain}): {td_result}")
                append_to_hex_notes(selected_hex, f"Terrain ({terrain}): {td_result}")
                st.success(td_result)

        st.markdown("### Biome-Dependent Terrain")

        with st.container(border=True):
            biome_list_td = [
                "Barren","Exotic","Frozen","Irradiated",
                "Lush","Scorched","Toxic","Urban",
                "Volcanic","Water"
            ]

            # Default to this hex's biome if set; otherwise fall back to the last map biome or Barren
            biome_td_initial = (biome or (st.session_state.get("map_default_biome") or "") or "Barren").strip()
            if biome_td_initial not in biome_list_td:
                biome_td_initial = "Barren"

            biome_td_choice = st.selectbox(
                "Biome:",
                biome_list_td,
                index=biome_list_td.index(biome_td_initial),
                key=f"map_biome_dep_{selected_hex}",
            )

            if st.button("Roll Biome-Dependent Terrain", key=f"btn_map_bdt_{selected_hex}"):
                df = load_table_df("biome_dependent_terrain")
                row = df[df["biome"] == biome_td_choice].sample(1).iloc[0]
                bd_result = f"{row['result']}: {row['description']}"
                add_to_persistent(4, f"Hex {selected_hex} — Biome-Dependent Terrain ({biome_td_choice}): {bd_result}")
                add_to_log(f"Hex {selected_hex} — Biome-Dependent Terrain ({biome_td_choice}): {bd_result}")
                append_to_hex_notes(selected_hex, f"Biome-Dependent Terrain ({biome_td_choice}): {bd_result}")
                st.success(bd_result)

        notes_key = f"map_notes_{selected_hex}"

        st.markdown("### Planetside Exploration (from this hex)")
        if st.button("ROLL FULL EXPLORATION (this hex)", key=f"btn_hex_explore_{selected_hex}"):

            biome_choice = biome or (st.session_state.get("map_default_biome") or "") or "Barren"
            exploration_result = roll_table("planetside_exploration", log=True)

            add_to_persistent(4, f"Hex {selected_hex} — Planetside Exploration: {exploration_result}")
            add_to_log(f"Hex {selected_hex} — Planetside Exploration: {exploration_result}")

            note_lines = [f"Planetside Exploration: {exploration_result}"]
            hex_map[selected_hex]["last"] = exploration_result

            if "findings" in exploration_result.lower():
                findings_result = roll_table("findings", log=True)
                add_to_persistent(4, f"Hex {selected_hex} — Findings: {findings_result}")
                add_to_log(f"Hex {selected_hex} — Findings: {findings_result}")
                note_lines.append(f"Findings: {findings_result}")

            elif "hazard" in exploration_result.lower():
                hazard_table = f"{biome_choice.lower()}_hazards"
                hazard_result = roll_table(hazard_table, log=True)
                add_to_persistent(4, f"Hex {selected_hex} — Hazard ({biome_choice}): {hazard_result}")
                add_to_log(f"Hex {selected_hex} — Hazard ({biome_choice}): {hazard_result}")
                note_lines.append(f"Hazard ({biome_choice}): {hazard_result}")

            elif "site" in exploration_result.lower():
                hex_map[selected_hex]["site"] = True
                add_to_log(f"Hex {selected_hex} — Found an Àrsaidh Site. Roll full site in Mission tab.")
                add_to_persistent(4, f"Hex {selected_hex} — Site Found: Roll full site in Mission tab.")
                note_lines.append("Site Found: Àrsaidh Site (roll full site in Mission tab)")

            elif "nothing" in exploration_result.lower():
                add_to_persistent(4, f"Hex {selected_hex} — Exploration: Nothing found.")
                note_lines.append("Nothing found.")

            else:
                note_lines.append("Result not recognized (check CSV formatting).")

            # Auto-append FULL results block into Notes
            append_to_hex_notes(selected_hex, "\n".join(note_lines))

            st.session_state["hex_map"] = hex_map


        # Initialize the widget state the first time this hex is selected
        if notes_key not in st.session_state:
            st.session_state[notes_key] = d.get("notes", "")

        # If exploration appended notes for this hex, refresh BEFORE the widget is created
        if st.session_state.get("force_notes_refresh_for") == selected_hex:
            st.session_state[notes_key] = d.get("notes", "")
            st.session_state["force_notes_refresh_for"] = None

        with st.expander("Notes (Special opens this automatically)", expanded=bool(special_flag)):
            notes = st.text_area("Notes", key=notes_key, height=200)

        # Party is unique: only one hex can have party=True
        if party_here:
            for k in hex_map.keys():
                if k != selected_hex and hex_map[k].get("party"):
                    hex_map[k]["party"] = False

        # Sync current editor state into the map EVERY run (so the map colors update immediately)
        hex_map[selected_hex] = {
            **d,
            "visited": visited,
            "party": party_here,
            "site": site_present,
            "special": special_flag,
            "name": name,
            "biome": biome,
            "terrain": terrain,
            "notes": notes,
        }
        st.session_state["hex_map"] = hex_map

        cA, cB = st.columns(2)
        with cA:
            if st.button("Save Hex", key=f"btn_save_hex_{selected_hex}"):
                st.success("Saved.")
        with cB:
            if st.button("Add Hex Summary to Log", key=f"btn_log_hex_{selected_hex}"):
                add_to_log(
                    f"Hex {selected_hex}: {name or '(unnamed)'} | "
                    f"Biome: {biome or '(unset)'} | Terrain: {terrain or '(unset)'} | Visited: {visited} | "
                    f"Party: {party_here} | Site: {site_present} | Special: {special_flag}"
                )
                st.success("Logged.")

    # -----------------------
    # LEFT: Map + Import/Export
    # -----------------------
    with col_map:
        st.caption("Click a hex to select it (Visited=green fill, Party=blue border, Site=dashed, Special=purple ring, Selected=red outline).")

        # Map display controls
        with st.expander("Map display", expanded=False):
            map_zoom_level = st.slider("Zoom", 0.6, 2.5, 1.0, 0.05, key="map_zoom_level")
            default_h = int((12 + 3) * 90)
            map_height_px = st.slider("Map height (px)", 450, 2000, default_h, 50, key="map_height_px")
        
        # --- Plotly click selection ---
        picked = render_hex_plotly_map(
            st.session_state["hex_map"],
            st.session_state["selected_hex"],
            zoom_level=map_zoom_level,
            height_px=map_height_px,
        )

        if picked is not None and picked != st.session_state["selected_hex"]:
            st.session_state["selected_hex"] = picked

            # Keep the fallback dropdown in sync with what you clicked
            st.session_state["map_hex_dropdown_fallback"] = picked

            st.rerun()

        # --- Fallback dropdown (ONLY changes selection when the dropdown changes) ---
        def _on_hex_dropdown_change():
            st.session_state["selected_hex"] = st.session_state["map_hex_dropdown_fallback"]
            st.rerun()

        with st.expander("If clicking doesn’t select a hex, use this dropdown instead"):
            # Initialize once; do NOT force it on every rerun
            if "map_hex_dropdown_fallback" not in st.session_state:
                st.session_state["map_hex_dropdown_fallback"] = st.session_state["selected_hex"]

            st.selectbox(
                "Select hex",
                list(range(1, MAP_HEX_COUNT + 1)),
                key="map_hex_dropdown_fallback",
                on_change=_on_hex_dropdown_change,
            )

        st.markdown("---")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Visited", sum(1 for v in st.session_state["hex_map"].values() if v.get("visited")))
        with c2:
            st.metric("Named", sum(1 for v in st.session_state["hex_map"].values() if (v.get("name") or "").strip()))
        with c3:
            st.metric("Biome set", sum(1 for v in st.session_state["hex_map"].values() if (v.get("biome") or "").strip()))

        export_blob = json.dumps(st.session_state["hex_map"], indent=2)
        st.download_button(
            "Download Map JSON",
            data=export_blob,
            file_name="atdw_hex_map.json",
            mime="application/json",
            key="dl_map_json"
        )

        up = st.file_uploader("Import Map JSON", type=["json"], key="ul_map_json")
        if up is not None:
            try:
                loaded = json.load(up)
                cleaned = {}

                for k, v in loaded.items():
                    kk = int(k)
                    if 1 <= kk <= MAP_HEX_COUNT and isinstance(v, dict):
                        v.setdefault("visited", False)
                        v.setdefault("party", False)
                        v.setdefault("site", False)
                        v.setdefault("special", False)
                        v.setdefault("name", "")
                        v.setdefault("biome", "")
                        v.setdefault("terrain", "")
                        v.setdefault("notes", "")
                        v.setdefault("last", "")
                        cleaned[kk] = v

                for i in range(1, MAP_HEX_COUNT + 1):
                    cleaned.setdefault(i, {
                        "name": "",
                        "biome": "",
                        "terrain": "",
                        "visited": False,
                        "party": False,
                        "site": False,
                        "special": False,
                        "notes": "",
                        "last": ""
                    })

                st.session_state["hex_map"] = cleaned

                # Keep selection + dropdown safe after import
                if st.session_state.get("selected_hex", 1) > MAP_HEX_COUNT:
                    st.session_state["selected_hex"] = 1
                st.session_state["map_hex_dropdown_fallback"] = st.session_state["selected_hex"]
    
                st.success("Map imported.")
                st.rerun()

            except Exception as e:
                st.error(f"Could not import JSON: {e}")

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
