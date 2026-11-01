#!/usr/bin/env python3
"""Catalog reusable production-technique presets (Ableton Rack presets saved
to the User Library, e.g. the kick/bass sidechain chain) in a SQLite table.

Phase 2 "technique presets" per IMPLEMENTATION.md / CLAUDE.md: presets
themselves are built and saved to the User Library by hand in Live (and any
third-party plugin params mapped to Rack Macros there) — this script only
catalogs the result (path, category, tags) so they're findable later, the
same way data/samples.db catalogs samples. Reuses that same DB file.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "samples.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT UNIQUE NOT NULL,     -- .adg/.adv path in the User Library
    category TEXT NOT NULL,        -- e.g. 'sidechain', 'glue-bus', 'send-fx'
    tags TEXT,                     -- JSON list of free-text tags
    notes TEXT,                    -- what it does / how to use it / macro layout
    added_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_presets_category ON presets(category);
"""


def add_preset(
    conn: sqlite3.Connection,
    *,
    name: str,
    path: str,
    category: str,
    tags: list[str] | None = None,
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO presets (name, path, category, tags, notes, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            tags = excluded.tags,
            notes = excluded.notes
        """,
        (
            name,
            path,
            category,
            json.dumps(tags or []),
            notes,
            time.strftime("%Y-%m-%dT%H:%M:%S"),
        ),
    )
    conn.commit()


def list_presets(
    conn: sqlite3.Connection, *, category: str | None = None, tag: str | None = None
) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    clauses, params = [], []
    if category:
        clauses.append("category = ? COLLATE NOCASE")
        params.append(category)
    if tag:
        clauses.append("tags LIKE ?")
        params.append(f'%"{tag}"%')
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return conn.execute(f"SELECT * FROM presets {where} ORDER BY name", params).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", help="Register a preset already saved to the User Library.")
    add_p.add_argument("--name", required=True)
    add_p.add_argument("--path", required=True, help="Path to the .adg/.adv file.")
    add_p.add_argument("--category", required=True)
    add_p.add_argument("--tags", nargs="*", default=[])
    add_p.add_argument("--notes")

    list_p = sub.add_parser("list", help="List cataloged presets.")
    list_p.add_argument("--category")
    list_p.add_argument("--tag")

    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)

    if args.command == "add":
        add_preset(
            conn,
            name=args.name,
            path=args.path,
            category=args.category,
            tags=args.tags,
            notes=args.notes,
        )
        print(f"Cataloged: {args.name} ({args.category})")
    elif args.command == "list":
        rows = list_presets(conn, category=args.category, tag=args.tag)
        if not rows:
            print("No presets cataloged yet.")
        for row in rows:
            tags = ", ".join(json.loads(row["tags"] or "[]"))
            print(f"{row['name']}  [{row['category']}]  tags: {tags}\n    {row['path']}")
        if rows:
            print(f"\n{len(rows)} preset(s).")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
