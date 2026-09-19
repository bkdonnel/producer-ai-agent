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

- [x] Install an existing Ableton MCP server: used
      [`ableton-mcp-extended`](https://github.com/uisato/ableton-mcp-extended)
      (cloned as a sibling repo, not part of this one, at
      `~/Documents/GitHub/ableton-mcp-extended`). It uses its **own**
      Remote Script ("AbletonMCP", TCP port 9877) — separate from
      AbletonOSC (Phase 0), not built on top of it. Both Remote Scripts
      now coexist in `~/Music/Ableton/User Library/Remote Scripts/`
      without conflict. Had to patch the local clone: `pyproject.toml`
      referenced a nonexistent `AbletonMCP_UDP` package path (removed —
      we don't need the UDP variant), and pinned `mcp[cli]<2` since the
      code targets the v1 `FastMCP` API, which v2 renamed.
- [x] Connect it to an AI assistant: Claude Desktop isn't installed on
      this machine, so registered with **Claude Code** instead via
      `claude mcp add -s user ableton-mcp -- <venv>/bin/python
      <repo>/MCP_Server/server.py`. Confirmed `claude mcp list` shows it
      Connected.
- [x] Select "AbletonMCP" in Live's Settings → Tempo & MIDI → an empty
      Control Surface slot (Input/Output: None) — separate slot from
      AbletonOSC. Confirmed "AbletonMCP: Listening for commands on port
      9877" in Live's status bar.
- [x] Confirmed end-to-end from a new Claude Code session: asked Claude
      about the current Ableton track and got a real answer back.
- [x] First real usability finding: browsing the user's own sample
      library (`/Users/bryandonnelly/Ableton Sounds/Samples` and
      `.../Loops`, added as Places in Live's browser) initially failed —
      `ableton-mcp-extended`'s browser-tree code couldn't traverse
      `Browser.user_folders` (how Live exposes Places) because it's a
      list-like sequence, not a single item like the other categories.
      Patched the local clone to fix it (see `CLAUDE.md`); confirmed
      `user_folders/Samples` and `user_folders/Loops` now list real
      subfolders. Note for later phases: user-added library folders live
      under `user_folders/<place name>/...`, not under `Samples` or
      `User_library`.
- [x] Used it for real, on an actual track: built a kick pattern (4-bar
      four-on-the-floor, `EvoSounds - Kick - StraightHouse.wav` via
      Simpler) and an off-beat bassline (`EvoSounds Minimal House - Bass
      Shot Moog Sub 37 13 - C.wav`, alternating root/octave), both
      placed on the Arrangement timeline. Note what's clunky below.
- [x] What's clunky / findings from real use:
      - **Arrangement model reconsidered**: switched from Session-View
        primary to Arrangement-View primary mid-Phase-1 (see `CLAUDE.md`)
        — wanting to see the actual MIDI on a timeline while it's built
        is a real workflow need, not just a nice-to-have.
      - `ableton-mcp-extended` needed a fourth local patch:
        `_find_browser_item_by_uri` (used by `load_instrument_or_effect`
        to actually load a sample/device by URI, not just browse it)
        only searched `instruments`/`sounds`/`drums`/`audio_effects`/
        `midi_effects`/`plugins` — never `samples`, `user_library`, or
        `user_folders`. So even after the browsing fix, loading a
        user-library sample by URI still failed until this was patched
        too. See `CLAUDE.md` for the fix.
      - `ableton-mcp-extended` has no exposed tool for adding MIDI notes
        directly to an Arrangement clip — only to a Session clip slot
        (`add_notes_to_clip`), even though the Remote Script itself
        implements `add_notes_to_arrangement_clip` under the hood, just
        never wrapped as an MCP tool. Workaround used: build the clip +
        notes in a Session slot, then `duplicate_clip_to_arrangement`.
        Works fine, just an extra step every time — worth exposing
        directly in Phase 3's own orchestrator.
      - Restarting Live discards any unsaved session state (new tracks,
        clips) — lost a build once this way. Save the Live Set before any
        restart needed to reload a patched Remote Script.
      - Sample selection is a real bottleneck: 593 kick one-shots and 175
        bass one-shots in the library with no way to search/filter — had
        to ask the user to pick by name every time. This is exactly the
        problem Phase 2's sample indexer is meant to solve.

**Decision point — resolved**: Phase 1 usage confirmed the core loop is
worth building on (real track content was built end-to-end), while also
surfacing concrete, specific gaps (sample selection, arrangement-clip
note-adding, the several `ableton-mcp-extended` bugs) that justify
Phase 2 and the custom Phase 3 orchestrator rather than continuing to
rely on the off-the-shelf MCP server. Proceeding to Phase 2.

## Phase 2 — Two cheap, high-value, independent pieces

- [ ] **Sample indexer**: script that walks the sample library, parses
      filenames/folders into tags, runs `librosa` for basic features
      (spectral centroid, RMS/crest, low-end ratio, duration, BPM/pitch
      where applicable), writes to SQLite. Skip embeddings for now —
      validate tag+feature filtering before adding semantic search.
      - [x] Built `scripts/index_samples.py` + `data/samples.db` schema
            (see `CLAUDE.md`). Added `librosa`/`numpy`/`soundfile` to
            `requirements.txt` and installed into the repo `.venv`.
      - [x] Validated on test subsets: 15 Kick one-shots (sane duration/
            spectral-centroid/low-end-ratio spread — e.g. a sub-heavy kick
            at 193 Hz centroid vs. a clicky one at 4946 Hz) and 20 Bass
            one-shots (pitch detection cross-checks cleanly against
            filename-parsed root notes, and correctly recovered a pitch —
            E1 — for one file whose filename tag was unparseable due to a
            stray character). Confirms the tag+feature approach works
            before spending time on a full run.
      - [ ] Run the full index (~12,381 files under `Samples`/`Loops`) —
            paused intentionally; not yet kicked off as of this writing.
      - [ ] Known rough edge: `detected_pitch_confidence` reads low
            (~0.01–0.09) even on correct detections, since it's pyin's
            mean voiced-probability over a whole one-shot including its
            unvoiced attack transient. Usable as a rough signal only;
            revisit if it causes bad filtering decisions later.
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
