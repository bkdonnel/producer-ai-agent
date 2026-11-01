#!/usr/bin/env python3
"""Query the Phase 2 sample index (data/samples.db) by tag/feature filters.

Phase 2 "wire the index into something that queries it" per IMPLEMENTATION.md.
Plain SQL filtering over the columns index_samples.py already populates — no
new infrastructure. Importable as `query_samples()` for later reuse (e.g. as
a Phase 3 agent tool), and runnable directly for ad-hoc lookups.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "samples.db"

# (column, cli flag, help text, sql comparison)
RANGE_FILTERS = [
    ("duration_sec", "duration", "clip duration, seconds"),
    ("spectral_centroid_hz", "centroid", "spectral centroid, Hz"),
    ("low_end_ratio", "low-end-ratio", "fraction of spectral power below 150 Hz (0-1)"),
    ("rms", "rms", "RMS level"),
    ("crest_factor", "crest", "peak / RMS"),
    ("bpm", "bpm", "detected tempo, loops only"),
]


def query_samples(
    conn: sqlite3.Connection,
    *,
    category: str | None = None,
    library_root: str | None = None,
    vendor: str | None = None,
    tag: str | None = None,
    filename_contains: str | None = None,
    detected_pitch: str | None = None,
    ranges: dict[str, tuple[float | None, float | None]] | None = None,
    order_by: str = "filename",
    limit: int = 50,
) -> list[sqlite3.Row]:
    """Filter the sample index. `ranges` maps column name -> (min, max), either
    side optional. Returns up to `limit` rows, each accessible by column name.
    """
    clauses: list[str] = []
    params: list = []

    if category:
        clauses.append("category = ? COLLATE NOCASE")
        params.append(category)
    if library_root:
        clauses.append("library_root = ? COLLATE NOCASE")
        params.append(library_root)
    if vendor:
        clauses.append("vendor LIKE ? COLLATE NOCASE")
        params.append(f"%{vendor}%")
    if tag:
        clauses.append("tags LIKE ?")
        params.append(f'%"{tag}"%')
    if filename_contains:
        clauses.append("filename LIKE ? COLLATE NOCASE")
        params.append(f"%{filename_contains}%")
    if detected_pitch:
        clauses.append("detected_pitch = ? COLLATE NOCASE")
        params.append(detected_pitch)

    for column, lo_hi in (ranges or {}).items():
        lo, hi = lo_hi
        if lo is not None:
            clauses.append(f"{column} >= ?")
            params.append(lo)
        if hi is not None:
            clauses.append(f"{column} <= ?")
            params.append(hi)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM samples {where} ORDER BY {order_by} LIMIT ?"
    params.append(limit)

    conn.row_factory = sqlite3.Row
    return conn.execute(sql, params).fetchall()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--category", help="e.g. Kick, Bass (matches immediate parent folder)")
    parser.add_argument("--library-root", choices=["Samples", "Loops"])
    parser.add_argument("--vendor", help="substring match on filename prefix before ' - '")
    parser.add_argument("--tag", help="exact match on one filename token")
    parser.add_argument("--filename-contains", help="substring match on filename")
    parser.add_argument("--pitch", help="e.g. C1 (pitched categories only)")
    parser.add_argument("--order-by", default="filename")
    parser.add_argument("--limit", type=int, default=50)

    for column, flag, help_text in RANGE_FILTERS:
        parser.add_argument(f"--min-{flag}", type=float, help=f"minimum {help_text}")
        parser.add_argument(f"--max-{flag}", type=float, help=f"maximum {help_text}")

    args = parser.parse_args()

    ranges = {}
    for column, flag, _ in RANGE_FILTERS:
        attr = flag.replace("-", "_")
        lo = getattr(args, f"min_{attr}")
        hi = getattr(args, f"max_{attr}")
        if lo is not None or hi is not None:
            ranges[column] = (lo, hi)

    conn = sqlite3.connect(args.db)
    rows = query_samples(
        conn,
        category=args.category,
        library_root=args.library_root,
        vendor=args.vendor,
        tag=args.tag,
        filename_contains=args.filename_contains,
        detected_pitch=args.pitch,
        ranges=ranges,
        order_by=args.order_by,
        limit=args.limit,
    )
    conn.close()

    if not rows:
        print("No matches.")
        return 0

    for row in rows:
        centroid = row["spectral_centroid_hz"]
        centroid_str = f"{centroid:.0f}Hz" if centroid is not None else "n/a"
        print(f"{row['path']}\n    category={row['category']} centroid={centroid_str}")
    print(f"\n{len(rows)} result(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
