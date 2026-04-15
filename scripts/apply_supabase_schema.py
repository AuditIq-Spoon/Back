#!/usr/bin/env python3
"""
Apply ../supabase/schema.sql to the hosted Supabase Postgres database.

Loads backend/.env. Provide either:
  - DATABASE_URL=postgresql://postgres:...@db.<project-ref>.supabase.co:5432/postgres
    (copy from Supabase Dashboard → Project Settings → Database → Connection string → URI)
  - SUPABASE_DB_PASSWORD=<database password> together with existing SUPABASE_URL
    (same password you set for the postgres user; not the anon/service API key)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
SCHEMA_PATH = REPO_ROOT / "supabase" / "schema.sql"


def _resolve_dsn() -> str:
    import os

    explicit = (os.environ.get("DATABASE_URL") or "").strip()
    if explicit:
        return explicit

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    password = (os.environ.get("SUPABASE_DB_PASSWORD") or "").strip()
    if not password:
        print(
            "Missing database credentials.\n"
            "Add one of the following to backend/.env, then re-run this script:\n"
            "  DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.<ref>.supabase.co:5432/postgres\n"
            "    (from Supabase → Project Settings → Database → Connection string → URI)\n"
            "  or\n"
            "  SUPABASE_DB_PASSWORD=<your database password>\n"
            "    (with SUPABASE_URL already set — this is the Postgres password, not SUPABASE_KEY).",
            file=sys.stderr,
        )
        sys.exit(1)

    if not url or "supabase.co" not in url:
        print("SUPABASE_URL must be set to apply schema using SUPABASE_DB_PASSWORD.", file=sys.stderr)
        sys.exit(1)

    parsed = urlparse(url)
    host = parsed.hostname or ""
    m = re.match(r"^([^.]+)\.supabase\.co$", host)
    if not m:
        print(f"Unexpected SUPABASE_URL host {host!r}; expected <ref>.supabase.co", file=sys.stderr)
        sys.exit(1)

    project_ref = m.group(1)
    user = quote_plus("postgres")
    pw = quote_plus(password)
    return f"postgresql://{user}:{pw}@db.{project_ref}.supabase.co:5432/postgres"


def main() -> None:
    load_dotenv(BACKEND_DIR / ".env")

    if not SCHEMA_PATH.is_file():
        print(f"Schema file not found: {SCHEMA_PATH}", file=sys.stderr)
        sys.exit(1)

    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    dsn = _resolve_dsn()

    try:
        import psycopg
    except ImportError:
        print("Install dependencies: pip install -r requirements.txt", file=sys.stderr)
        raise

    conn = psycopg.connect(dsn, connect_timeout=30)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
    finally:
        conn.close()

    print(f"Applied {SCHEMA_PATH.relative_to(REPO_ROOT)} to Supabase Postgres.")


if __name__ == "__main__":
    main()
