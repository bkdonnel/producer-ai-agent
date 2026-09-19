#!/usr/bin/env python3
"""Walk the sample library, parse filename/folder tags, compute basic audio
features with librosa, and write everything to a local SQLite index.

Phase 2 "sample indexer" per IMPLEMENTATION.md: tag/feature filtering only,
no embeddings yet. See CLAUDE.md's "Sample understanding" decision.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import traceback
from pathlib import Path

import librosa
import numpy as np

DEFAULT_LIBRARY_ROOTS = [
    Path.home() / "Ableton Sounds" / "Samples",
    Path.home() / "Ableton Sounds" / "Loops",
]
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "samples.db"

AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".mp3", ".flac"}

# Folder categories where a root-note guess / pitch detection is meaningful.
# Everything else (Kick, Snare, Clap, Hat, ...) is percussive/unpitched.
PITCHED_CATEGORIES = {"bass", "chord", "synth", "vocal"}

LOW_END_CUTOFF_HZ = 150.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    library_root TEXT NOT NULL,        -- 'Samples' or 'Loops'
    category TEXT,                     -- immediate parent folder, e.g. 'Kick'
    subpath TEXT,                      -- folder path relative to library root
    vendor TEXT,                       -- filename prefix before ' - ', if any
    tags TEXT,                         -- JSON list of filename tokens
    filename_root_note TEXT,           -- weak signal parsed from filename
    duration_sec REAL,
    sample_rate INTEGER,
    spectral_centroid_hz REAL,
    rms REAL,
    crest_factor REAL,
    low_end_ratio REAL,
    bpm REAL,                          -- loops only
    detected_pitch TEXT,               -- pitched categories only
    detected_pitch_confidence REAL,
    file_mtime REAL NOT NULL,
    indexed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples_category ON samples(category);
CREATE INDEX IF NOT EXISTS idx_samples_library_root ON samples(library_root);
"""


def parse_filename_tags(stem: str) -> dict:
    """Weak, cheap tag extraction from a filename (no audio analysis)."""
    vendor = stem.split(" - ", 1)[0].strip() if " - " in stem else None
    tokens = [t for t in re.split(r"[ _\-]+", stem) if t]

    root_note = None
    for tok in reversed(tokens):
        cleaned = tok.strip(".")
        if re.fullmatch(r"v\d+", cleaned, re.IGNORECASE):
            continue
        if re.fullmatch(r"[A-G](#|b)?", cleaned):
            root_note = cleaned
        break

    return {"vendor": vendor, "tokens": tokens, "filename_root_note": root_note}


def compute_audio_features(path: Path, library_root: str, category: str | None) -> dict:
    y, sr = librosa.load(str(path), sr=None, mono=True)
    duration_sec = float(len(y) / sr) if sr else 0.0

    features = {
        "duration_sec": duration_sec,
        "sample_rate": int(sr) if sr else None,
        "spectral_centroid_hz": None,
        "rms": None,
        "crest_factor": None,
        "low_end_ratio": None,
        "bpm": None,
        "detected_pitch": None,
        "detected_pitch_confidence": None,
    }

    if len(y) == 0:
        return features

    rms = float(np.sqrt(np.mean(y**2)))
    peak = float(np.max(np.abs(y)))
    features["rms"] = rms
    features["crest_factor"] = (peak / rms) if rms > 1e-9 else None

    stft = np.abs(librosa.stft(y))
    freqs = librosa.fft_frequencies(sr=sr)
    features["spectral_centroid_hz"] = float(
        np.mean(librosa.feature.spectral_centroid(S=stft, sr=sr))
    )
    power = (stft**2).sum(axis=1)
    total_power = power.sum()
    if total_power > 0:
        low_mask = freqs < LOW_END_CUTOFF_HZ
        features["low_end_ratio"] = float(power[low_mask].sum() / total_power)

    if library_root == "Loops" and duration_sec > 1.0:
        try:
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            tempo = float(np.asarray(tempo).reshape(-1)[0])
            features["bpm"] = tempo if tempo > 0 else None
        except Exception:
            pass

    if (category or "").lower() in PITCHED_CATEGORIES and duration_sec > 0.05:
        try:
            f0, voiced_flag, voiced_prob = librosa.pyin(
                y,
                fmin=librosa.note_to_hz("C1"),
                fmax=librosa.note_to_hz("C6"),
                sr=sr,
            )
            voiced_f0 = f0[voiced_flag] if voiced_flag is not None else np.array([])
            if voiced_f0.size > 0:
                median_f0 = float(np.median(voiced_f0))
                features["detected_pitch"] = librosa.hz_to_note(median_f0)
                features["detected_pitch_confidence"] = float(
                    np.mean(voiced_prob[voiced_flag])
                )
        except Exception:
            pass

    return features


def iter_audio_files(roots: list[Path], category_filter: str | None):
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            relative = path.relative_to(root)
            category = relative.parts[0] if len(relative.parts) > 1 else None
            if category_filter and (category or "").lower() != category_filter.lower():
                continue
            yield root, path, category


def get_existing_mtime(conn: sqlite3.Connection, path: str) -> float | None:
    row = conn.execute(
        "SELECT file_mtime FROM samples WHERE path = ?", (path,)
    ).fetchone()
    return row[0] if row else None


def upsert_sample(conn: sqlite3.Connection, record: dict) -> None:
    columns = list(record.keys())
    placeholders = ", ".join("?" for _ in columns)
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "path")
    sql = (
        f"INSERT INTO samples ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(path) DO UPDATE SET {update_clause}"
    )
    conn.execute(sql, [record[c] for c in columns])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roots",
        nargs="+",
        type=Path,
        default=DEFAULT_LIBRARY_ROOTS,
        help="Library root folders to walk (default: ~/Ableton Sounds/{Samples,Loops}).",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite DB path.")
    parser.add_argument(
        "--category",
        help="Only index files whose immediate parent folder matches this name "
        "(e.g. 'Kick'). Useful for quick test runs.",
    )
    parser.add_argument("--limit", type=int, help="Stop after N files (testing).")
    parser.add_argument(
        "--force", action="store_true", help="Recompute features even if file_mtime is unchanged."
    )
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)

    processed = skipped = failed = 0
    start = time.time()

    for root, path, category in iter_audio_files(args.roots, args.category):
        if args.limit and processed >= args.limit:
            break

        file_mtime = path.stat().st_mtime
        if not args.force:
            existing_mtime = get_existing_mtime(conn, str(path))
            if existing_mtime is not None and existing_mtime == file_mtime:
                skipped += 1
                continue

        try:
            tags = parse_filename_tags(path.stem)
            features = compute_audio_features(path, root.name, category)
        except Exception as exc:
            failed += 1
            print(f"  FAILED: {path} ({exc})", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            continue

        record = {
            "path": str(path),
            "filename": path.name,
            "library_root": root.name,
            "category": category,
            "subpath": str(path.relative_to(root).parent),
            "vendor": tags["vendor"],
            "tags": json.dumps(tags["tokens"]),
            "filename_root_note": tags["filename_root_note"],
            "file_mtime": file_mtime,
            "indexed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **features,
        }
        upsert_sample(conn, record)
        processed += 1

        if processed % 100 == 0:
            conn.commit()
            elapsed = time.time() - start
            print(f"  ...{processed} indexed, {skipped} skipped, {failed} failed ({elapsed:.0f}s)")

    conn.commit()
    conn.close()

    elapsed = time.time() - start
    print(
        f"Done in {elapsed:.0f}s: {processed} indexed, {skipped} skipped (unchanged), "
        f"{failed} failed. DB: {args.db}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
