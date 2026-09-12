# Producer AI Agent

A conversational AI agent that connects to Ableton Live to help build out
EDM tracks (house, techno) — talk to it while producing and it builds
sections (intro, verse, breakdown, drop, etc.) using samples, presets, and
techniques from your own library.

This is a personal project, independent of any bootcamp/coursework repo.

## What it does

- Controls Ableton Live directly (tracks, clips, scenes, MIDI, device
  parameters, sample/preset loading) via the Live Object Model.
- Picks samples from your own library based on a natural-language
  description, using a local index built from filenames, audio features,
  and (later) semantic audio embeddings — not by "listening" live.
- Applies your own production techniques (e.g. a specific kick/bass
  sidechain chain) via saved Ableton presets/racks rather than
  reconstructing settings from scratch each time.
- Optionally matches the feel of reference tracks via precomputed "style
  profiles" (tempo, section-energy curve, spectral balance) used as
  generation constraints.
- Lives inside Ableton as a Max for Live device (text chat first; voice
  is a possible later addition, not required for the MVP).

## Architecture

```
[M4L device, inside Live]  <--OSC-->  [Python orchestrator]  <--OSC-->  [AbletonOSC, inside Live]
   text box / display                   Claude API + tools               Live Object Model
                                         - Ableton control
                                         - sample index (SQLite)
                                         - preset/technique catalog
                                         - style profiles
```

The orchestrator is the only "brain" in the system. The M4L device is a
thin UI; AbletonOSC is a thin control surface. All real audio/sample/style
files stay on disk — the SQLite DB and any embedding index store paths and
derived features/vectors only, never copies of the audio.

## Status

Planning complete, no code yet. See `IMPLEMENTATION.md` for the build plan
and current phase, and `CLAUDE.md` for the architecture decisions a coding
session in this repo should already know.

## Stack (planned)

- **Ableton bridge**: [AbletonOSC](https://github.com/ideoforms/AbletonOSC) (Remote Script)
- **Orchestrator**: Python, `python-osc`, Claude API (Messages/tool use)
- **Interaction surface**: Max for Live device (text input first)
- **Sample index**: SQLite + `librosa`/`essentia` features; CLAP-style
  embeddings as a later addition
- **Config**: git-tracked JSON/YAML for style profiles and section recipes
- **Storage**: local-first (see `CLAUDE.md`) — no hosted database for the
  MVP
