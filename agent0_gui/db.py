import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "agent0_gui.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed (
                fingerprint TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS headline_cache (
                file_path TEXT PRIMARY KEY,
                headline_en_gb TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_uuid TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                summary_json TEXT,
                log_text TEXT,
                worker_log_path TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL,
                wp_post_id INTEGER,
                wp_link TEXT,
                link_report TEXT,
                errors TEXT,
                duration_s REAL,
                FOREIGN KEY(run_id) REFERENCES runs(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT NOT NULL,
                scanned_at TEXT NOT NULL,
                item_count INTEGER NOT NULL,
                scan_mode TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS published_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                headline TEXT NOT NULL,
                wp_post_id INTEGER NOT NULL,
                wp_url TEXT NOT NULL,
                published_at TEXT NOT NULL,
                fingerprint TEXT,
                meta_title TEXT,
                primary_keyword TEXT,
                UNIQUE(file_path, wp_post_id)
            )
            """
        )
        run_columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        if "run_uuid" not in run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN run_uuid TEXT")
        if "finished_at" not in run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN finished_at TEXT")
        if "summary_json" not in run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN summary_json TEXT")
        if "log_text" not in run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN log_text TEXT")
        if "worker_log_path" not in run_columns:
            conn.execute("ALTER TABLE runs ADD COLUMN worker_log_path TEXT")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(run_items)").fetchall()}
        if "link_report" not in columns:
            conn.execute("ALTER TABLE run_items ADD COLUMN link_report TEXT")

        # Profiles table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                input_dir TEXT NOT NULL,
                output_dir TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 0,
                description TEXT
            )
            """
        )

        # Profile prompts table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                prompt_key TEXT NOT NULL,
                prompt_value TEXT NOT NULL,
                model_preference TEXT DEFAULT 'gemini-2.0-flash-exp',
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
                UNIQUE(profile_id, prompt_key)
            )
            """
        )
        
        # Add model_preference column if it doesn't exist
        prompt_columns = {row["name"] for row in conn.execute("PRAGMA table_info(profile_prompts)").fetchall()}
        if "model_preference" not in prompt_columns:
            conn.execute("ALTER TABLE profile_prompts ADD COLUMN model_preference TEXT DEFAULT 'gemini-2.0-flash-exp'")

        # Migrate profiles table to add multi-platform support columns
        profile_columns = {row["name"] for row in conn.execute("PRAGMA table_info(profiles)").fetchall()}
        if "publishing_platform" not in profile_columns:
            conn.execute("ALTER TABLE profiles ADD COLUMN publishing_platform TEXT DEFAULT 'wordpress'")
        if "platform_config" not in profile_columns:
            conn.execute("ALTER TABLE profiles ADD COLUMN platform_config TEXT")
        
        # Add llm_model column to published_articles to track which LLM was used
        published_columns = {row["name"] for row in conn.execute("PRAGMA table_info(published_articles)").fetchall()}
        if "llm_model" not in published_columns:
            conn.execute("ALTER TABLE published_articles ADD COLUMN llm_model TEXT")
        if "english_headline" not in published_columns:
            conn.execute("ALTER TABLE published_articles ADD COLUMN english_headline TEXT")

        # Create default profile if none exists
        existing_profiles = conn.execute("SELECT COUNT(*) as cnt FROM profiles").fetchone()
        if existing_profiles["cnt"] == 0:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO profiles (name, input_dir, output_dir, created_at, is_active, description)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                ("Default", "current", "output", now, "Default profile for general articles")
            )
            conn.commit()
