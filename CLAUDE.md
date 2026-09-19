# CLAUDE.md

Guidance for Claude Code sessions working in this repo.

## What this project is

A personal (non-bootcamp) project: an AI agent that connects to Ableton
Live over OSC to help build EDM (house/techno) track sections
conversationally, using the user's own sample library, presets, and
production techniques. See `README.md` for the architecture summary and
`IMPLEMENTATION.md` for the phased build plan and current status —
**check `IMPLEMENTATION.md`'s checkboxes before assuming what phase we're
in.**

This is unrelated to the user's Databricks AI data engineering bootcamp
capstone (`databricks-final-project`, a separate repo). Don't import that
repo's conventions or assume Databricks/Lakebase are in play here — this
project is deliberately local-first and has no Databricks dependency.

## Architecture decisions already made — don't re-litigate these

These were decided across an earlier design conversation. Revisit only if
the user explicitly asks to reconsider one; otherwise treat them as
settled:

- **Ableton bridge**: AbletonOSC (Remote Script exposing the Live Object
  Model over OSC), default ports 11000 (send to Live) / 11001 (Live's
  replies). Not raw MIDI, not a from-scratch Remote Script. This is what
  the Phase 3 custom orchestrator will be built on. `AbletonMCP` (see
  below) is a **different, temporary** bridge used only to validate the
  concept in Phase 1 — don't conflate the two or assume AbletonMCP is
  permanent.
- **Arrangement model**: Session View, scene-per-section (scene 1 =
  intro, scene 2 = verse, etc.). Arrangement View automation is more
  awkward via the API and is not the primary approach.
- **Orchestrator**: a single local Python process is the actual "brain."
  It runs the Claude API tool-use loop, holds an OSC client to AbletonOSC
  for Live control, and is a separate OSC server/client for the M4L
  device's chat channel — on its **own** port pair (e.g. 11002/11003),
  never reusing AbletonOSC's ports. Long-running agent turns must not
  block the OSC server thread (background thread per request).
- **Interaction surface**: a Max for Live device, **text input first**
  (a `textedit` box + OSC to the orchestrator + a display object for
  replies). Voice/push-to-talk was deliberately deferred — it only pays
  off when the user's hands are off the keyboard (e.g. on a MIDI
  controller), and adds real scope (mic capture, local Whisper, WAV
  handling). Do not build voice input unless the user asks for it.
- **Plugins/synths**: stock devices and third-party VST/VST3/AU plugins
  are both controllable via the same generic device-parameter API.
  Third-party FX-section/mod-matrix parameters often need a one-time
  manual "Configure"/Automate step inside Live before they're
  automatable — that's a manual per-plugin setup step for the user, not
  something to try to automate away.
- **Production techniques** (e.g. the user's kick/bass sidechain chain):
  saved as reusable Ableton device/rack presets in the User Library, not
  reconstructed parameter-by-parameter each time. Third-party plugin
  controls should be mapped to Rack Macros for a consistent, named
  surface.
- **Sound design** (e.g. a Serum bass patch): start from the user's own
  saved patches and tweak exposed macro/synthesis parameters, rather than
  generating a patch from scratch — the agent has no audio feedback loop
  by default, so from-scratch sound design is unreliable.
- **Sample understanding**: the agent cannot listen to audio. Retrieval
  is index-based: filename/folder tags (weak, cheap) → `librosa`/
  `essentia` signal features (objective, e.g. spectral centroid, RMS/
  crest, low-end ratio, onset shape) → CLAP-style audio-text embeddings
  for semantic search (later addition, not MVP). An audio-in LLM pass is
  reserved for final picks on a short shortlist only, never the full
  library, for cost/latency reasons.
- **Style matching**: reference tracks are analyzed into a JSON "style
  profile" (tempo, section-length/energy curve, spectral balance,
  density) and used as generation constraints. This is descriptive
  parameters, never literal audio copying/sampling of the reference.
- **Data storage**: local-first, deliberately not a hosted database or
  Databricks-style platform.
  - SQLite for sample metadata/features and the preset/technique catalog.
  - A numpy array or FAISS index (keyed by the same sample IDs as
    SQLite) for embeddings — no vector DB server needed at this scale.
  - Git-tracked JSON/YAML for style profiles and section-recipe
    templates (small, human-edited, benefits from diffs).
  - Raw audio files and Ableton presets stay on disk untouched; the DB
    only ever stores paths plus derived data.
  - If backup automation comes up: Litestream → S3/B2, not a bigger
    database.
  - Only reach for a hosted option (Turso, Supabase/Neon) if genuine
    multi-machine concurrent access becomes a real need — not by
    default.

## Local environment state (this machine, as of Phase 1)

Not architecture decisions — just what's physically installed and
running, so a future session doesn't have to rediscover it:

- **Ableton**: both Live 11 Suite and Live 12 Suite are installed. Live
  12 renamed "Preferences" to "Settings"; the relevant tab is
  "Tempo & MIDI".
- **Remote Scripts installed** in
  `~/Music/Ableton/User Library/Remote Scripts/` (this location works
  for both Live versions without per-version copies — preferred over any
  per-version `~/Library/Preferences/Ableton/Live [x]/User Remote
  Scripts/` path):
  - `AbletonOSC/` — Phase 0, verified working, selected as one Control
    Surface slot. This is the permanent bridge (see above).
  - `AbletonMCP/` — Phase 1 only, from the sibling repo below, TCP port
    9877, selected as a separate Control Surface slot. Both scripts run
    as independent slots simultaneously with no conflict.
- **`ableton-mcp-extended`**: cloned as a *sibling* repo, not part of
  this one, at `~/Documents/GitHub/ableton-mcp-extended` — used only for
  Phase 1 validation via Claude Code, not something this repo depends on
  going forward. Its local clone (not upstream) has three fixes applied
  that aren't in this repo and would need reapplying if the clone is
  ever deleted and re-cloned:
  - `pyproject.toml`'s `packages` list referenced a nonexistent
    `AbletonMCP_UDP` path at the repo root (it actually lives under
    `Ableton-MCP_hybrid-server/`) — removed, since the UDP variant isn't
    used here.
  - `mcp[cli]` was unpinned and resolved to v2, which renamed `FastMCP`
    to `MCPServer` and broke the v1-API code in `MCP_Server/server.py` —
    pinned to `mcp[cli]>=1.3.0,<2`.
  - `AbletonMCP_Remote_Script/__init__.py`'s browser-tree code
    (`get_browser_tree`, `get_browser_items_at_path`,
    `_resolve_browser_root_category`) assumed every `Live.Browser`
    category is a single item with `.name`/`.children`. `user_folders`
    (Live's "Places" — the mechanism for reaching sample folders outside
    Live's built-in library, e.g. this machine's
    `/Users/bryandonnelly/Ableton Sounds/Samples` and `.../Loops`) is
    actually one of Live's own tuple-like sequences, not a single item,
    so it was silently skipped — the agent could never see user-added
    sample folders, only Live's built-in `Samples`/`User_library`. Fixed
    by wrapping any such sequence-valued category (`_wrap_browser_root`,
    `_BrowserListWrapper`) so it's traversable like the others. Browse
    with paths like `user_folders/<place name>/...`, e.g.
    `user_folders/Samples/Kick`.
  - **Deployment gotcha**: the Remote Script Live actually loads
    (`~/Music/Ableton/User Library/Remote Scripts/AbletonMCP/`) is a
    **plain copy** of `ableton-mcp-extended/AbletonMCP_Remote_Script/`,
    not a symlink. Any future edit to the sibling repo's Remote Script
    must be manually `cp`'d over to that path (and its `__pycache__`
    cleared) before restarting Live, or Live keeps running the old code.
- **Claude Desktop is not installed** on this machine. Phase 1 used
  Claude Code instead — the MCP server is registered at **user scope**
  (`claude mcp add -s user ableton-mcp -- ...`, config in
  `~/.claude.json`, not in any repo), so it's available in any Claude
  Code session on this machine, in any directory, not just this repo.
- **This repo's own `.venv/`** (gitignored) has `python-osc` installed,
  used by `scripts/verify_osc_connection.py`. Separate from
  `ableton-mcp-extended`'s own `.venv/` in its sibling repo.

## Working conventions

- Keep this file in sync as phases in `IMPLEMENTATION.md` complete —
  future sessions read this file first.
- Prefer the simplest thing that works at solo-producer scale over
  "proper" infra (no need for message queues, container orchestration,
  or a hosted DB for a single local user).
- When adding a new external dependency (a library, a model, an MCP
  server fork), note it here if it's a real architectural choice, not
  just an implementation detail.
