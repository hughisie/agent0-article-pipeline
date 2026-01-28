"""Profile management for multi-profile article processing system."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agent0_gui.db import get_conn


# All available LLM prompt keys (matching keys used in resolve_prompt calls)
PROMPT_KEYS = [
    "PROMPT_TRANSLATION_SYSTEM",
    "PROMPT_TRANSLATION_USER",
    "PROMPT_PRIMARY_SYSTEM",
    "PROMPT_PRIMARY_USER",
    "PROMPT_ARTICLE_SYSTEM",
    "PROMPT_ARTICLE_USER",
    "PROMPT_RELATED_SYSTEM",
    "PROMPT_RELATED_USER",
    "PROMPT_HEADLINE_SYSTEM",
    "PROMPT_HEADLINE_USER",
    "PROMPT_YOAST_SYSTEM",
    "PROMPT_YOAST_USER",
    "PROMPT_TAG_GEN_SYSTEM",
    "PROMPT_TAG_GEN_USER",
    "PROMPT_TAXONOMY_SYSTEM",
    "PROMPT_TAXONOMY_USER",
]


def get_active_profile() -> Optional[dict]:
    """Get the currently active profile."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return dict(row)


def get_profile_by_id(profile_id: int) -> Optional[dict]:
    """Get a profile by ID."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)


def get_all_profiles() -> list[dict]:
    """Get all profiles."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM profiles ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def create_profile(
    name: str,
    input_dir: str,
    output_dir: str,
    description: str = ""
) -> dict:
    """Create a new profile."""
    now = datetime.now(timezone.utc).isoformat()

    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO profiles (name, input_dir, output_dir, created_at, is_active, description)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (name, input_dir, output_dir, now, description)
        )
        conn.commit()
        profile_id = cursor.lastrowid

    return get_profile_by_id(profile_id)


def update_profile(
    profile_id: int,
    name: Optional[str] = None,
    input_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
    description: Optional[str] = None
) -> dict:
    """Update a profile."""
    profile = get_profile_by_id(profile_id)
    if not profile:
        raise ValueError(f"Profile {profile_id} not found")

    # Build update query dynamically
    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if input_dir is not None:
        updates.append("input_dir = ?")
        params.append(input_dir)
    if output_dir is not None:
        updates.append("output_dir = ?")
        params.append(output_dir)
    if description is not None:
        updates.append("description = ?")
        params.append(description)

    if updates:
        params.append(profile_id)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE profiles SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()

    return get_profile_by_id(profile_id)


def delete_profile(profile_id: int) -> bool:
    """Delete a profile. Cannot delete active profile."""
    profile = get_profile_by_id(profile_id)
    if not profile:
        return False

    if profile["is_active"]:
        raise ValueError("Cannot delete active profile. Switch to another profile first.")

    with get_conn() as conn:
        conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        conn.commit()

    return True


def set_active_profile(profile_id: int) -> dict:
    """Set a profile as active (deactivates all others)."""
    profile = get_profile_by_id(profile_id)
    if not profile:
        raise ValueError(f"Profile {profile_id} not found")

    with get_conn() as conn:
        # Deactivate all profiles
        conn.execute("UPDATE profiles SET is_active = 0")
        # Activate the selected one
        conn.execute("UPDATE profiles SET is_active = 1 WHERE id = ?", (profile_id,))
        conn.commit()

    return get_profile_by_id(profile_id)


def get_profile_prompt(profile_id: int, prompt_key: str) -> Optional[str]:
    """Get a specific prompt for a profile. Returns None if not customized."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT prompt_value FROM profile_prompts WHERE profile_id = ? AND prompt_key = ?",
            (profile_id, prompt_key)
        ).fetchone()
        if not row:
            return None
        return row["prompt_value"]


def get_all_profile_prompts(profile_id: int) -> dict[str, dict]:
    """Get all prompts for a profile. Returns only customized ones with their model preferences."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT prompt_key, prompt_value, model_preference FROM profile_prompts WHERE profile_id = ?",
            (profile_id,)
        ).fetchall()
        return {
            row["prompt_key"]: {
                "value": row["prompt_value"],
                "model": row["model_preference"] or "gemini-2.0-flash-exp"
            }
            for row in rows
        }


def set_profile_prompt(profile_id: int, prompt_key: str, prompt_value: str, model_preference: str = None) -> None:
    """Set/update a prompt for a profile with optional model preference."""
    if prompt_key not in PROMPT_KEYS:
        raise ValueError(f"Invalid prompt key: {prompt_key}. Must be one of: {PROMPT_KEYS}")

    with get_conn() as conn:
        if model_preference:
            conn.execute(
                """
                INSERT INTO profile_prompts (profile_id, prompt_key, prompt_value, model_preference)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_id, prompt_key) DO UPDATE SET 
                    prompt_value = excluded.prompt_value,
                    model_preference = excluded.model_preference
                """,
                (profile_id, prompt_key, prompt_value, model_preference)
            )
        else:
            conn.execute(
                """
                INSERT INTO profile_prompts (profile_id, prompt_key, prompt_value)
                VALUES (?, ?, ?)
                ON CONFLICT(profile_id, prompt_key) DO UPDATE SET prompt_value = excluded.prompt_value
                """,
                (profile_id, prompt_key, prompt_value)
            )
        conn.commit()


def delete_profile_prompt(profile_id: int, prompt_key: str) -> None:
    """Delete a custom prompt (will fall back to default)."""
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM profile_prompts WHERE profile_id = ? AND prompt_key = ?",
            (profile_id, prompt_key)
        )
        conn.commit()


def get_profile_directories(profile_id: Optional[int] = None) -> dict[str, Path]:
    """Get input and output directories for a profile. Uses active profile if not specified."""
    if profile_id is None:
        profile = get_active_profile()
    else:
        profile = get_profile_by_id(profile_id)

    if not profile:
        # Fallback to defaults
        base_dir = Path(__file__).resolve().parent.parent
        return {
            "input_dir": base_dir / "current",
            "output_dir": base_dir / "output"
        }

    base_dir = Path(__file__).resolve().parent.parent

    # Resolve directory paths
    input_dir = base_dir / profile["input_dir"]
    output_dir = base_dir / profile["output_dir"]

    # Create directories if they don't exist
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    return {
        "input_dir": input_dir,
        "output_dir": output_dir
    }
