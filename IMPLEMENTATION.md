# Implementation Plan

Build order is deliberately front-loaded with de-risking: prove the core
loop with existing, off-the-shelf tools before writing any custom
infrastructure (sample index, style profiles, M4L device). Check off items
as they're completed and keep this file as the source of truth for
current phase.

## Phase 0 — Get Ableton actually listening

- [x] Install [AbletonOSC](https://github.com/ideoforms/AbletonOSC) into
      Live's Remote Scripts folder. Cloned into
      `~/Music/Ableton/User Library/Remote Scripts/AbletonOSC` (works for
      both the Live 11 and Live 12 installs on this machine).
- [x] Select "AbletonOSC" under Settings → Tempo & MIDI → Control Surface
      (Live 12 renamed "Preferences" to "Settings"). Input/Output left as
      None — AbletonOSC uses network ports, not MIDI.
- [x] Sanity-check with `scripts/verify_osc_connection.py` (`python-osc`,
      installed in a repo-local `.venv`): reads tempo, nudges it +1 BPM,
      confirms the change, restores it. Confirmed working.

## Phase 1 — Talk to Live via an existing agent, no custom code yet

- [ ] Install an existing Ableton MCP server (`ableton-mcp-extended` is
      the actively maintained fork as of this writing — re-check current
      state before installing, this space moves fast).
- [ ] Connect it to Claude Desktop per its README.
- [ ] Use it for real, on an actual track: build a kick pattern, add a
      bassline, load a sample, create scenes for verse/drop.
- [ ] Note what's clunky, what commands get repeated, whether "build a
      32-bar chorus" produces something usable with stock tools alone.
      This phase's purpose is information, not infrastructure — don't
      write custom code yet.

**Decision point**: only proceed past this phase once Phase 1 usage
confirms the core loop is worth building on. It costs almost nothing and
tells you the most.

## Phase 2 — Two cheap, high-value, independent pieces

- [ ] **Sample indexer**: script that walks the sample library, parses
      filenames/folders into tags, runs `librosa` for basic features
      (spectral centroid, RMS/crest, low-end ratio, duration, BPM/pitch
      where applicable), writes to SQLite. Skip embeddings for now —
      validate tag+feature filtering before adding semantic search.
- [ ] **Technique presets**: save go-to production chains (e.g. the
      kick/bass sidechain compressor setup) as Ableton device/rack
      presets in the User Library, named clearly. Catalog them (path,
      category, tags) — a SQLite table is fine, reuse the sample DB.

These two have no dependency on each other or on Phase 3 — can happen in
either order or in parallel.

## Phase 3 — Build the real orchestrator

- [ ] Replace the off-the-shelf MCP-server-in-Claude-Desktop setup with a
      custom Python process: Claude API tool-use loop + AbletonOSC client
      + tools wrapping the sample index and preset catalog from Phase 2.
- [ ] This is the point the system stops being "someone else's MCP demo"
      and starts being the actual product.

## Phase 4 — The Max for Live interaction device

- [ ] Build the text-only M4L device: `textedit` input → OSC (port 11002)
      → orchestrator → OSC reply (port 11003) → display object. See
      `CLAUDE.md` for why this is text-first, not voice.
- [ ] Wire it to the Phase 3 orchestrator, not the Phase 1 off-the-shelf
      setup.
- [ ] Validate with an echo test (orchestrator just echoes text back)
      before wiring in the real agent call — confirms transport
      separately from agent logic.

## Later, additive, not blocking anything above

- [ ] Style profiles: analyze reference tracks into JSON profiles
      (tempo, section-energy curve, spectral balance, density) as
      generation constraints.
- [ ] Semantic sample search: add CLAP-style audio-text embeddings on top
      of the Phase 2 index once plain tag/feature filtering hits its
      ceiling.
- [ ] Status feedback in the M4L UI for long-running multi-tool-call
      turns (may motivate moving the OSC transport to Node for Max).
- [ ] MIDI-pad mapping for the M4L device's controls, once the text flow
      is solid.
- [ ] Voice input — only if a real hands-off-keyboard need shows up in
      practice, per `CLAUDE.md`.
- [ ] Render-and-analyze feedback loop (bounce a section, extract
      features, compare against a style profile, iterate) if generation
      quality plateaus without it.
