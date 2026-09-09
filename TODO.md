# TODO

Forward-looking roadmap, broken into single-session/feature-sized iterations.
Each item names the files it touches so a future session can pick it up and
go without re-deriving context. Earlier completed review/hardening passes
and shipped features are documented in the commit history rather than repeated here.

## Closed Captioning

- [ ] **CC-10 — Web: simplify live-caption lag-compensation logic once CC-8/CC-9 are verified on real hardware.**
  `caption-controller.ts` and `HDHomeRunPlayer.svelte` currently stretch/align live cues
  (`LIVE_CUE_MIN_DISPLAY_SECONDS`, `alignLiveCues`, `baseOffsetSeconds` drift
  correction) specifically to paper over cues arriving several seconds late
  in batches. CC-8's `ccextractor` swap should make that arrival pattern
  mostly go away — once verified against a real physical tuner (CC-8's testing
  constraint), revisit whether this logic can be trimmed down or removed.
  Don't start this before that real-tuner verification, since the whole
  premise depends on it.
  - **Files**:
    - `frontend/src/lib/caption-controller.ts` (MODIFY: simplify or remove artificial stretch slots & drift correction)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: update caption event bindings)

## Multi-Feed / Multi-View Playback

- [x] **MULTI-1 — Multi-Feed Core Engine & Session Orchestration (`HDHROpenKit`).**
  Build the underlying multi-stream management layer supporting up to 4 concurrent feeds:
  - **Screen Size & Platform Feasibility**:
    - **tvOS (Primary Target)**: 10-foot television experience (55"+, 4K/1080p displays) is ideal for multi-game sports and breaking news watching (e.g. Quad-Box / 2x2 grid, 1-hero + 2-side, 2-up split).
    - **iPadOS & macOS (Secondary Target)**: Supported on large screen real estate / regular horizontal size classes (`horizontalSizeClass == .regular`).
    - **iOS iPhone (Excluded)**: Compact screens (~6" mobile displays) make multi-video playback illegible; iPhone remains single player with PiP.
  - **Hardware & Tuner Constraints**:
    - Each active live stream claims 1 physical HDHomeRun tuner and server-side transcode pipeline.
    - Check `TunerStatus` / available tuners from backend before allocating a slot; present a graceful slot-level warning if physical tuners are exhausted.
    - Audio routing: exactly one audio stream unmuted at a time (`AVPlayer.isMuted = false` for focused slot, `isMuted = true` for unfocused slots) to prevent audio chaos.
  - **Implementation**:
    - Define `MultiViewLayout` enum (`.sideBySide`, `.threeBox`, `.quad`) and `MultiViewSlot` state model.
    - Create `MultiPlayerViewModel`:
      ```swift
      @MainActor
      public final class MultiPlayerViewModel: ObservableObject {
          @Published public private(set) var slots: [MultiViewSlot] = []
          @Published public var activeSlotIndex: Int = 0
          @Published public var layout: MultiViewLayout = .sideBySide
          
          public func addFeed(channel: HDHomeRunChannel) async throws { ... }
          public func removeFeed(at index: Int) { ... }
          public func setAudioSlot(index: Int) { ... }
          public func swapSlots(from: Int, to: Int) { ... }
      }
      ```
    - Extend `WatchSessionManager` to manage a dictionary of active watch sessions (`[String: Task<Void, Never>]`) so multiple slots maintain independent heartbeats and tear down cleanly.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Models/MultiViewModels.swift` (NEW: MultiViewLayout, MultiViewSlot models)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Networking/WatchSessionManager.swift` (MODIFY: multi-session heartbeat tracking)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/MultiPlayerViewModel.swift` (NEW: multi-stream state, audio focus, tuner-aware slot orchestration)
    - `apple/HDHROpenKit/Tests/HDHROpenKitTests/MultiPlayerViewModelTests.swift` (NEW: slot lifecycle and audio focus tests)

- [x] **MULTI-2 — tvOS Native Quad-Box & Multi-View UI with Focus Engine (`HDHROpenTV`).**
  Implement the Apple TV 10-foot multi-view playback interface:
  - **Focus & Siri Remote Interaction**:
    - Each video tile in the grid acts as a `@FocusState` target with an active highlight border and channel badge.
    - Moving focus dynamically switches audio to that tile without interrupting playback.
    - Click (Select) opens in-player transport controls / quick channel switcher drawer for that slot.
    - Long-press / Menu action allows expanding tile to full-screen or closing the slot.
  - **Layout Grids**:
    - Render `TVMultiViewGrid` with smooth transitions between 2-up (50/50 split), 3-up (1 large hero + 2 stacked side tiles), and 4-up (2x2 quad box).
    - Render video using existing non-interactive `PlayerLayerView(player:)` to keep tvOS focus hierarchy clean.
  - **Entry Points**:
    - Add "Add to Multi-View" action in `TVPlayerView` transport controls and `TVChannelRowView` / `TVProgramDetailModal`.
  - **Files**:
    - `apple/HDHROpenTV/Views/Player/MultiView/TVMultiPlayerView.swift` (NEW: tvOS multi-view container & overlays)
    - `apple/HDHROpenTV/Views/Player/MultiView/TVMultiViewGrid.swift` (NEW: 2-up, 3-up, and 4-up grid layouts)
    - `apple/HDHROpenTV/Views/Player/MultiView/TVMultiViewSlotOverlay.swift` (NEW: slot badge, channel info, audio indicator)
    - `apple/HDHROpenTV/Views/Player/TVPlaybackControlsView.swift` (MODIFY: add multi-view transition button)
    - `apple/HDHROpenTV/App/RootTVView.swift` (MODIFY: route to TVMultiPlayerView when multi-view active)

- [x] **MULTI-3 — iPadOS / macOS Regular Size-Class Adaptation (`HDHROpeniOS`).**
  Adapt multi-view playback for iPad and Mac windowed environments:
  - Conditionally present multi-view when `horizontalSizeClass == .regular`.
  - Tap-to-focus audio routing and touch drag-and-drop / long-press tile swap.
  - **Files**:
    - `apple/HDHROpeniOS/Views/Player/MultiView/iOSMultiPlayerView.swift` (NEW: iPadOS / regular size class multi-view grid)
    - `apple/HDHROpeniOS/Views/Player/iOSPlayerView.swift` (MODIFY: multi-view button when size class is regular)
    - `apple/HDHROpeniOS/App/RootiOSView.swift` (MODIFY: route to iOSMultiPlayerView when active)

## Code Review — Backend

Findings from a full read-through of the FastAPI backend (`backend/app/`),
focused on architecture, security, performance, and quality-gate gaps not
already caught by ruff/pytest in CI. SQL-injection defense, blocking-call
offloading, and external HTTP timeout discipline were all checked and found
solid — not itemized below.

- [x] **REV-BE-1 — [High] SyncPlay API and WebSocket have no authentication.**
  `app/api/syncplay.py`'s router has no `dependencies=[Depends(get_current_user)]`,
  unlike every sibling router (`dvr.py`, `streaming.py`, `watch.py`). An
  anonymous caller can create rooms, enumerate all active rooms and their
  content metadata (`GET /api/syncplay/rooms`), join any room by its 6-char
  code, and — if elected host — issue `change_content`/`transfer_host`
  commands. The WebSocket handler resolves a user identity from a
  cookie/token only to pick a display name, not to gate access. Add router-level
  auth matching the rest of the API; `tests/test_api_syncplay.py` has no
  auth assertions, suggesting this was missed rather than deliberate.
  - **Files**:
    - `backend/app/api/syncplay.py` (MODIFY: add `dependencies=[Depends(get_current_user)]` to router and WS handler)
    - `backend/tests/test_api_syncplay.py` (MODIFY: add auth-required test cases)

- [x] **REV-BE-2 — [Medium] Decompose `app/api/dvr.py` (1397 lines) god file.**
  Mixes HTTP routing, provider-fallback business logic (builtin vs.
  HDHomeRun DVR), and streaming orchestration (ffmpeg subprocess spawning,
  in-memory probe/EDL caches) in one file. `create_recording_rule`/
  `update_recording_rule` (lines ~601-853) embed deep provider-fallback
  logic directly in route handlers with no service-layer boundary, making it
  hard to unit test independent of FastAPI. Well covered by tests
  (`test_api_dvr_builtin.py`) so this is a maintainability risk, not a
  correctness one — split provider-fallback logic and streaming
  orchestration into separate service modules the route handlers delegate to.
  - **Files**:
    - `backend/app/api/dvr.py` (MODIFY: extract provider-fallback and streaming-orchestration logic into service modules)

- [x] **REV-BE-3 — [Medium] Decompose `app/dvr/media_cache.py` (991 lines) — three unrelated subsystems in one module.**
  Bundles captions VTT generation/coalescing, a ~550-line live closed-caption
  supervisor (its own backoff/circuit-breaker/watchdog state machine, lines
  ~179-732), and thumbnail-sprite/poster generation. The live-caption
  subsystem is a self-contained state machine that would be easier to reason
  about and test in isolation. Test coverage is genuinely good here
  (`test_media_cache.py`) — this is purely a structure complaint.
  - **Files**:
    - `backend/app/dvr/media_cache.py` (MODIFY: extract live-caption supervisor into its own module)

- [x] **REV-BE-4 — [Medium] No static type checker (mypy/pyright) despite widespread untyped dict plumbing.**
  CI runs `ruff check` + `pytest` only — no type-checking step. Config
  (`effective_settings()` in `app/config.py`) and transcoding/hwaccel preset
  settings flow through the codebase as raw `dict[str, Any]` rather than a
  `TypedDict`/dataclass. A typo'd or renamed settings key would only surface
  at runtime via `KeyError`/a silently-`None` `.get()`, not at review or CI
  time. Adding even a narrow mypy pass over `app/transcoding.py` and
  `app/config.py` would catch a real class of bugs ruff cannot.
  - **Files**:
    - `backend/pyproject.toml` (MODIFY: add mypy config, at least for `app/transcoding.py` and `app/config.py`)
    - `.github/workflows/ci.yml` (MODIFY: add a type-check step to the backend job)

- [x] **REV-BE-5 — [Low] No `PRAGMA busy_timeout` or advisory lock around concurrent DB startup/migrations.**
  `_connect()` (`app/storage/db/connection.py:243-262`) sets WAL mode but
  never sets `busy_timeout`, relying only on sqlite3's default 5s lock-wait.
  `_apply_migrations()` has no lock around the whole startup sequence. A
  non-issue for the normal single-instance LAN-DVR deployment, but if ever
  run with multiple workers/replicas sharing one `DB_PATH`, two processes
  starting simultaneously could race to apply the same migration.
  - **Files**:
    - `backend/app/storage/db/connection.py` (MODIFY: set explicit `busy_timeout` pragma; consider an advisory lock around migration startup)

- [x] **REV-BE-6 — [Low] `crypto.decrypt()` silently returns `""` on `InvalidToken` instead of distinguishing failure from "unconfigured".**
  Callers using this for secrets (Schedules Direct password, HDHomeRun DVR
  key) can't tell "no secret configured" from "secret exists but the
  encryption key changed/rotated and decryption failed" — both return an
  empty string. A decrypt failure on an existing value (e.g. key file
  replaced with a different valid key) would silently degrade a configured
  integration to "unconfigured" with only a log line as a clue.
  - **Files**:
    - `backend/app/crypto.py` (MODIFY: raise or return a distinct sentinel on `InvalidToken` rather than `""`)

- [x] **REV-BE-7 — [Low] SyncPlay room state is in-memory only, with no reconnection/recovery path on backend restart.**
  `SyncPlayHub` is a module-level singleton (`app/api/syncplay.py:270`).
  Unlike `dvr/builtin/watch.py`'s sessions (explicitly documented as fine to
  lose on restart), SyncPlay rooms represent a multi-user real-time feature
  where a routine redeploy silently disconnects every active watch party
  with no visible reconnection path.
  - **Files**:
    - `backend/app/api/syncplay.py` (MODIFY: consider persisting room state or at least surfacing a clear "session ended, rejoin" signal to clients on reconnect)

- [x] **REV-BE-8 — [Low] `app/api/dvr.py` in-memory probe/EDL caches have no invalidation on underlying file changes.**
  `_probe_cache`/`_edl_cache` (lines ~70-132) are capped `OrderedDict`s with
  manual LRU eviction, keyed by recording, but never invalidated except by
  eviction. If a recording file is regenerated at the same path (e.g. a
  re-encode job) while still cached, stale probe/EDL data could be served
  until it ages out.
  - **Files**:
    - `backend/app/api/dvr.py` (MODIFY: add explicit cache invalidation hook if re-encode/replace flows exist or are planned)

- [x] **REV-BE-9 — [Low] No rate limiting on bearer-token/session-cookie auth resolution beyond PIN lockout.**
  `app/auth.py`'s lockout is scoped specifically to PIN verification
  (sliding 60s window, max 5 attempts); `_resolve_bearer_token` and session
  cookie lookups have no equivalent throttling. Token/session IDs are
  CSPRNG-strength (`secrets.token_urlsafe`) so brute-force isn't practical,
  but this is a defense-in-depth gap worth closing for consistency.
  - **Files**:
    - `backend/app/auth.py` (MODIFY: consider a general request-rate guard on auth resolution paths)

- [x] **REV-BE-10 — [Low] HDHomeRun SSH client disables host-key verification.**
  `_dvr_ssh_connect()` (`app/integrations/hdhomerun_client.py:487-499`) uses
  `known_hosts=None`, accepting any host key with no pinning. Consistent
  with the broader LAN-trust model used elsewhere in this module (plain
  HTTP), but SSH is a protocol users might reasonably expect to be
  verified — worth a one-line deployment-docs note if not already present.
  - **Files**:
    - `backend/app/integrations/hdhomerun_client.py` (MODIFY or document: note the accepted trust model for the SSH host-key bypass)

