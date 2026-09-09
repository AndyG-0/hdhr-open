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

- [x] **MULTI-4 — Web Browser Multi-View & Multi-Feed Playback (`frontend`).**
  Implement browser-based multi-stream playback matching Apple TV / tvOS capabilities:
  - **Screen Size & Browser Feasibility**:
    - **Desktop & Laptop Displays (Primary Target)**: 1080p, 1440p, 4K, and ultrawide displays support 2-up (50/50 split), 3-up (1 large hero + 2 stacked side tiles), and 4-up (2x2 quad box) grids using hardware-accelerated MSE video decoding.
    - **Mobile Viewports (< 768px)**: Provide graceful fallback or 2-up vertical stack with responsive warnings.
  - **Hardware & Tuner Orchestration**:
    - Check `/api/tuner/status` before allocating a slot; display slot warning when physical tuners are exhausted.
    - Independent watch session heartbeats (`/api/watch/:id/heartbeat`) and cleanup (`/api/watch/:id/stop` with `keepalive: true` on tab close/navigation).
    - Audio routing: exactly one `<video>` unmuted at a time with instant switching on click, hover, or number keys (`1`-`4`).
  - **Grid UI & Tile Controls**:
    - CSS Grid layouts for 2-up (50/50 split), 3-up (1 large hero + 2 stacked side tiles), and 4-up (2x2 quad box).
    - Slot overlay with channel badge, airing title, live badge, audio focus indicator, "Make Hero" swap button, fullscreen expand, channel changer drawer, and close button.
    - Multi-view top toolbar with layout switcher, tuner indicator, and add feed button.
  - **Files**:
    - `frontend/src/lib/stores/multiview.ts` (NEW: multi-view slot orchestration, audio routing, watch session heartbeat tracking)
    - `frontend/src/lib/stores/multiview.test.ts` (NEW: slot lifecycle, audio focus, layout adaptation unit tests)
    - `frontend/src/lib/components/player/multiview/MultiViewPlayer.svelte` (NEW: multi-tile container, top toolbar, keyboard shortcuts)
    - `frontend/src/lib/components/player/multiview/MultiViewSlotTile.svelte` (NEW: video tile, mpegts player, slot hover controls)
    - `frontend/src/lib/components/player/multiview/MultiViewEmptyTile.svelte` (NEW: placeholder add slot tile)
    - `frontend/src/lib/components/player/PlayerHeader.svelte` (MODIFY: add multi-view transition button)
    - `frontend/src/lib/components/player/PlayerFooter.svelte` (MODIFY: add multi-view transition button)
    - `frontend/src/lib/components/details/HDHomeRunGuideCellMenu.svelte` (MODIFY: add "Add to Multi-View" option)
    - `frontend/src/routes/player/+page.svelte` (MODIFY: support popout multi-view via query params)
    - `frontend/src/routes/+layout.svelte` (MODIFY: render MultiViewPlayer when multi-view active)
    - `frontend/src/lib/i18n/locales/en.json` (MODIFY: multi-view localization strings)

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

## Code Review — Frontend

Findings from a full read-through of the SvelteKit/TS frontend, focused on
the player component tree, API client, and stores. Existing accessibility
work (scrub bar `role="slider"`, guide grid row virtualization) was checked
and found solid — not itemized below.

- [x] **REV-FE-1 — [High] `multiview.ts` currently fails lint — will break CI as-is.**
  `stopAllHeartbeats()` (`src/lib/stores/multiview.ts:87`) does
  `for (const [slotId, handle] of heartbeatHandles.entries())` and never
  uses `slotId`. Verified via `npx eslint`: `error 'slotId' is assigned a
  value but never used @typescript-eslint/no-unused-vars`. This file is
  currently untracked/new, so it hasn't hit CI yet, but `npm run lint` will
  fail on it as written.
  - **Files**:
    - `frontend/src/lib/stores/multiview.ts` (MODIFY: `for (const handle of heartbeatHandles.values())`)

- [x] **REV-FE-2 — [High] `HDHomeRunPlayer.svelte` (1842 lines) mixes five distinct responsibilities.**
  Owns recording-rule CRUD (~130 lines), media lifecycle/switching, AirPlay
  session negotiation (~130 lines of platform-quirk-heavy logic), keyboard
  shortcut dispatch, and top-level layout — all in one component. It already
  delegates captions/mpegts/syncplay to controller modules; the same pattern
  should apply to recording-rule actions and AirPlay.
  - **Files**:
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: extract `recording-actions.ts` and `airplay-controller.ts` controllers)

- [x] **REV-FE-3 — [Medium] Action-error state is set on failure but never cleared on success — stale error banners persist.**
  Every `catch` block in `recordings/+page.svelte` and
  `HDHomeRunPlayer.svelte` sets `error`/`errorMessage`, but no success path
  ever resets it to `null`. Once any recording-rule action fails once, the
  error banner stays visible indefinitely across all later successful
  actions on the page.
  - **Files**:
    - `frontend/src/routes/recordings/+page.svelte` (MODIFY: clear error at the start of each action handler)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: same pattern)

- [x] **REV-FE-4 — [Medium] No fetch timeouts anywhere in `api.ts`.**
  None of the 9 `fetch()` call sites (`getJSON`/`postJSON`/`putJSON`/
  `patchJSON`/`deleteJSON`) use `AbortController`/`signal` or any timeout. A
  hung backend request leaves `await` pending forever with the UI stuck in
  a loading state and no recovery short of a full page reload.
  - **Files**:
    - `frontend/src/lib/api.ts` (MODIFY: add a shared `AbortSignal.timeout(...)` wrapper in the common request helpers)

- [x] **REV-FE-5 — [Medium] SyncPlay WebSocket has no reconnect-on-drop logic.**
  `ws.onclose` (`syncplay-controller.ts:151-158`) only rejects the initial
  connect promise if unresolved; if the socket drops mid-session, `status`
  silently flips to `'disconnected'` with no automatic reconnect attempt —
  a live watch-party participant quietly falls out of sync.
  - **Files**:
    - `frontend/src/lib/syncplay-controller.ts` (MODIFY: add bounded exponential-backoff reconnect reusing `room_code`)

- [x] **REV-FE-6 — [Medium] `recordings/+page.svelte` (1463 lines) duplicates category-filtering markup four times.**
  The four `{#if typeFilter === ...}` branches each re-render essentially
  the same `RecordingCard` loop with only the source array and empty-state
  string differing — should collapse to one parameterized loop. The
  ~85-line inline tuner-status popover and the sports/movies keyword-matching
  heuristic are both self-contained enough to extract.
  - **Files**:
    - `frontend/src/routes/recordings/+page.svelte` (MODIFY: parameterize the filter loop; extract `TunerStatusPopover.svelte` and `lib/recording-category.ts`)

- [x] **REV-FE-7 — [Medium] Twelve component/store files have no test coverage.**
  `PlayerFooter.svelte`, `PlayerHeader.svelte`, `PlayerScrubBar.svelte`,
  `PlayerSettingsMenu.svelte`, `PlayerVolumeControl.svelte`, `CastButton.svelte`,
  `MiniPlayer.svelte`, `HDHomeRunGuideGrid.svelte`, `HDHomeRunGuideCellMenu.svelte`,
  `HDHomeRunCancelRuleModal.svelte`, `HDHomeRunFallbackConfirmModal.svelte`,
  `HDHomeRunKeywordRuleDialog.svelte`. Most concerning: `PlayerScrubBar.svelte`
  owns nontrivial pointer/drag/keyboard seek math with zero coverage, and
  `HDHomeRunGuideGrid.svelte` owns virtualization math, search matching, and
  long-press-vs-click disambiguation, also untested.
  - **Files**:
    - `frontend/src/lib/components/player/PlayerScrubBar.svelte` (NEW: test seek math, drag, keyboard interaction)
    - `frontend/src/lib/components/details/HDHomeRunGuideGrid.svelte` (NEW: test virtualization, search, long-press)
    - (remaining files listed above; lower priority)

- [x] **REV-FE-8 — [Low] i18n: `player.keep_playing_label` missing from `de`/`es`/`fr` locales.**
  Confirmed via a full top-level-key diff — this is the only key that
  differs across all four locale files. Non-English users see a raw key or
  English fallback wherever the "keep playing on navigate" toggle renders.
  - **Files**:
    - `frontend/src/lib/i18n/locales/de.json` (MODIFY: add translated key)
    - `frontend/src/lib/i18n/locales/es.json` (MODIFY: add translated key)
    - `frontend/src/lib/i18n/locales/fr.json` (MODIFY: add translated key)

- [x] **REV-FE-9 — [Low] AirPlay session-swap logic has no test coverage and encodes fragile, hardware-verified assumptions inline.**
  `HDHomeRunPlayer.svelte:1106-1231` documents behavior "confirmed against
  real Safari/Apple TV hardware" (audio-only negotiation, CORS
  credential/wildcard-origin conflict, crossorigin toggling) — exactly the
  kind of platform-quirk logic that regresses silently on refactor, yet
  it's untestable in its current form. Depends on REV-FE-2's extraction.
  - **Files**:
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: extract to testable `airplay-controller.ts`)

- [x] **REV-FE-10 — [Low] Guide search re-scans all channels/airings on every keystroke with no debounce.**
  `searchResults` in `HDHomeRunGuideGrid.svelte` is a `$derived.by` that
  iterates every channel × every airing on each keystroke with no debounce.
  Not currently a measured problem, but worth a cheap debounce guard if
  guide sizes grow.
  - **Files**:
    - `frontend/src/lib/components/details/HDHomeRunGuideGrid.svelte` (MODIFY: debounce `searchQuery` before recomputing `searchResults`)

- [x] **REV-FE-11 — [Low] Recording-rule payload construction duplicated near-verbatim across two files.**
  `HDHomeRunPlayer.svelte` and `recordings/+page.svelte` independently build
  the same `api.addHDHomeRunRecordingRule(...)`/`updateHDHomeRunRecordingRule(...)`
  payload shape and fallback-notice detection logic — drift risk if a
  backend field is renamed and only fixed in one call site.
  - **Files**:
    - `frontend/src/lib/recording-rule-actions.ts` (NEW: shared options→payload mapping + fallback-detection helper)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: use shared helper)
    - `frontend/src/routes/recordings/+page.svelte` (MODIFY: use shared helper)

- [x] **REV-FE-12 — [Low] `PlaybackContext` page-ownership pattern is a hand-rolled, copy-pasted protocol.**
  Pages that "own" the persistent player's closures must remember to add an
  `$effect` that calls `get(playback)` (not `$playback`) and compares
  `originPath` against the current path before republishing — documented at
  the call site but repeated per page rather than enforced in one place.
  - **Files**:
    - `frontend/src/lib/stores/playback.ts` (MODIFY: add a shared `useOwnedPlaybackContext(pathname, buildContext)` helper)

## Code Review — Android

Findings from a full read-through of `PlayerViewModel.kt`, `PlayerScreen.kt`,
`PlayerEngine.kt`, and `APIClient.kt`. Seek/resync and channel-fallback test
coverage is genuinely strong (including drift re-anchoring and max-catchup
edge cases) — not itemized below.

- [x] **REV-AND-1 — [High] AI Assistant chat state machine lives entirely inside a Composable, not a ViewModel.**
  `AIAssistantBottomSheet` takes a raw `APIClient` and implements the full
  streaming-chat protocol inline (SSE event dispatch, action confirm/cancel)
  using `rememberCoroutineScope()`. Every other screen routes network calls
  through a `*ViewModel`; this one doesn't, so it's only testable via
  Compose UI tests, not fast unit tests, and its state can't be hoisted or
  reused.
  - **Files**:
    - `android/core/src/main/kotlin/org/hdhropen/kit/viewmodels/AIAssistantViewModel.kt` (NEW: extract `turns`/`isSending`/`errorText` state and `sendPrompt`/`confirmAction`/`cancelAction`)
    - `android/app/src/main/kotlin/org/hdhropen/app/ui/screens/ai/AIAssistantBottomSheet.kt` (MODIFY: consume the new ViewModel)

- [x] **REV-AND-2 — [High] Errors are silently swallowed in `promoteToRecording()` and `selectAudioTrack()` — no user-facing surface.**
  Both catch blocks (`PlayerViewModel.kt:449-453`, `:528-532`) only log; the
  `_isPromoting`/`_isSwitchingAudioTrack` flags flip back to `false` with
  nothing telling the user the action failed, unlike `playChannel`/
  `playRecording` which correctly call `setPlaybackError`. Not caught by
  tests either — existing coverage only exercises the happy path.
  - **Files**:
    - `android/core/src/main/kotlin/org/hdhropen/kit/viewmodels/PlayerViewModel.kt` (MODIFY: surface a transient error/snackbar state for both flows)

- [x] **REV-AND-3 — [Medium] `startWatch()` failure is silently downgraded to direct-HLS fallback with only a log line.**
  `APIClient.startWatch()` swallows all exceptions and returns `null`
  (losing "no watch capability" vs. "server error"); `PlayerViewModel.playChannel`
  then falls back to plain HLS with zero user indication that live-pause/
  DVR-buffer functionality isn't available for this session.
  - **Files**:
    - `android/core/src/main/kotlin/org/hdhropen/kit/viewmodels/PlayerViewModel.kt` (MODIFY: surface a one-time toast/banner on watch-session fallback)
    - `android/core/src/main/kotlin/org/hdhropen/kit/networking/APIClient.kt` (MODIFY: distinguish "unsupported" from "server error")

- [x] **REV-AND-4 — [Medium] Duplicated HTTP-status-to-user-message mapping between `PlayerViewModel` and `PlayerEngine`.**
  Both independently hardcode the same status codes (401, 404, 429/502) into
  slightly different message strings — one for `APIError`, one for
  `PlaybackException`. Already drifted: 503/504 handling only exists in the
  `PlayerEngine` copy.
  - **Files**:
    - `android/core/src/main/kotlin/org/hdhropen/kit/playback/PlaybackErrorMapper.kt` (NEW: consolidate status→message mapping)
    - `android/core/src/main/kotlin/org/hdhropen/kit/viewmodels/PlayerViewModel.kt` (MODIFY: use shared mapper)
    - `android/core/src/main/kotlin/org/hdhropen/kit/playback/PlayerEngine.kt` (MODIFY: use shared mapper)

- [x] **REV-AND-5 — [Medium] `PlayerViewModel.kt` (871 lines) mixes four distinct responsibilities.**
  Combines playback-session orchestration, SyncPlay wiring, a self-contained
  live-caption re-alignment algorithm (`alignLiveCues`/`resyncCaptionsAfterSeek`,
  lines ~734-842, with its own state), and recording metadata/thumbnail
  fetching. The caption-alignment logic is already tested somewhat
  independently via reflection into private state — a sign it wants to be
  its own class.
  - **Files**:
    - `android/core/src/main/kotlin/org/hdhropen/kit/playback/LiveCaptionAligner.kt` (NEW: extract caption re-alignment state machine)
    - `android/core/src/main/kotlin/org/hdhropen/kit/viewmodels/PlayerViewModel.kt` (MODIFY: delegate to extracted class)

- [x] **REV-AND-6 — [Medium] `PlayerScreen.kt` (759 lines) is a single monolithic Composable with no internal decomposition.**
  The whole overlay-controls tree is one function body with no extraction
  into `PlayerTopBar`/`PlayerCenterControls`/`PlayerBottomBar`/etc. Every
  recomposition of any single piece of collected state (e.g. bitrate
  updating every ~1s) recomposes the entire 700-line tree.
  - **Files**:
    - `android/app/src/main/kotlin/org/hdhropen/app/ui/screens/player/PlayerScreen.kt` (MODIFY: split into scoped sub-composables)

- [x] **REV-AND-7 — [Medium] Thin test coverage for the exception-swallowing branches (REV-AND-2, REV-AND-3).**
  `CoreViewModelsComprehensiveTest.kt` only exercises happy paths for
  `selectAudioTrack`/`promoteToRecording`; no test asserts behavior when
  `watchSessionManager.promoteWatch()` throws or when a mid-session HLS
  session call throws during audio-track switch.
  - **Files**:
    - `android/core/src/test/kotlin/org/hdhropen/kit/CoreViewModelsComprehensiveTest.kt` (MODIFY: add failure-path tests once REV-AND-2/3 land)

- [x] **REV-AND-8 — [Low] Dead public API: `PlayerEngine.skipForward`/`skipBackward` duplicate `PlayerViewModel`'s and are never called in production code.**
  Every real call site goes through `PlayerViewModel.skipForward/skipBackward`
  (which also broadcasts to SyncPlay and resyncs captions). A future
  contributor calling `playerEngine.skipForward()` directly would silently
  desync SyncPlay and captions with no warning.
  - **Files**:
    - `android/core/src/main/kotlin/org/hdhropen/kit/playback/PlayerEngine.kt` (MODIFY: delete the duplicate methods or make them `internal`)

- [x] **REV-AND-9 — [Low] Dead/unused `showAudioMenu`/`showSettingsOverlay` `StateFlow`s break the ViewModel's own encapsulation convention.**
  Declared as raw public `MutableStateFlow<Boolean>` (unlike every other
  piece of state in the class), and referenced nowhere else —
  `PlayerScreen.kt` has its own unrelated local state for `showAudioMenu`.
  - **Files**:
    - `android/core/src/main/kotlin/org/hdhropen/kit/viewmodels/PlayerViewModel.kt` (MODIFY: remove both)

- [x] **REV-AND-10 — [Low] No detekt/ktlint — only AGP Lint is configured.**
  Findings REV-AND-4, REV-AND-8, and REV-AND-9 (duplication, dead code) are
  exactly the class of issue a static analyzer would flag automatically;
  none of them are caught by the current CI gate.
  - **Files**:
    - `android/build.gradle.kts` (MODIFY: add detekt plugin + baseline config)
    - `.github/workflows/ci.yml` (MODIFY: run detekt as part of `qualityCheck`)

- [x] **REV-AND-11 — [Low] `ViewModel` subclasses are hand-instantiated app-singletons, not obtained via `ViewModelProvider` — `onCleared()` is dead code.**
  `AppEnvironment` directly constructs `PlayerViewModel`/`GuideViewModel`/
  `TunerViewModel` as plain fields, so `ViewModel.onCleared()` never fires.
  Confirmed concretely: `TunerViewModel.onCleared() { stopPolling() }` is
  unreachable — real cleanup happens via screen-level `startPolling`/
  `stopPolling` calls instead.
  - **Files**:
    - `android/core/src/main/kotlin/org/hdhropen/kit/viewmodels/TunerViewModel.kt` (MODIFY: remove misleading `onCleared` override or document the pattern prominently)

- [x] **REV-AND-12 — [Low] `GuideGridMath` (pure, testable layout arithmetic) lives in the `app` module's UI file instead of `core`.**
  Already factored into a standalone object with no Compose dependencies,
  but its location in `GuideGridView.kt` rather than `core/utilities` makes
  it harder to discover/reuse and muddies the module boundary.
  - **Files**:
    - `android/app/src/main/kotlin/org/hdhropen/app/ui/screens/guide/GuideGridView.kt` (MODIFY: move `GuideGridMath` to `core`)

## Code Review — Apple

Findings from a full read-through of `HDHROpenKit`'s player subsystem,
`HDHROpeniOS`'s player views, and `HDHROpenTV`'s player/multi-view views.
State-ownership conventions (`@Published`/`ObservableObject`/`@MainActor`)
are consistent across every ViewModel checked, and `iOSScrubBarView.swift`
already gets accessibility/hit-target sizing right — not itemized below.

- [x] **REV-APL-1 — [High] `PlayerViewModel.swift` (804 lines, largest file in the repo) mixes five unrelated concerns.**
  Covers HLS session negotiation, a nontrivial live-caption timestamp-remapping
  algorithm, recording promotion, SyncPlay/SharePlay wiring, and UI overlay
  flags. None depend on each other's internals. Recommend a
  `StreamSessionCoordinator`, a `LiveCaptionAligner`, and a
  `CrossDeviceSyncCoordinator`, leaving `PlayerViewModel` as a thin façade.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/PlayerViewModel.swift` (MODIFY: extract the three coordinators above)

- [x] **REV-APL-2 — [High] Stream-session-negotiation logic is copy-pasted three times and has already drifted.**
  `PlayerViewModel.playChannel`, `MultiPlayerViewModel.finishAddFeed`, and
  `MultiPlayerViewModel.replaceFeed` all implement "try watch session →
  build recording HLS session → fall back to direct channel HLS session"
  nearly verbatim. Only the multi-view paths do a tuner-exhaustion
  pre-check, and error-handling/logging differs between all three.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/ChannelStreamNegotiator.swift` (NEW: `startStream(channel:) -> StreamResult`)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/PlayerViewModel.swift` (MODIFY: use shared negotiator)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/MultiPlayerViewModel.swift` (MODIFY: use shared negotiator in `finishAddFeed`/`replaceFeed`)

- [x] **REV-APL-3 — [High] No cancellation/generation guard around async stream-session negotiation — leaks backend sessions on rapid channel-switch or slot-close.**
  Unlike `seek()` (which stores and cancels `serverSeekTask`), `playChannel`/
  `playRecording` have no task handle: rapid channel switching can let a
  stale call overwrite `activeChannel`/`activeHLSSessionId` after finishing,
  with its own newly-created backend session never recorded anywhere to be
  stopped. The multi-view equivalent is worse: `MultiPlayerViewModel.finishAddFeed`
  only guards its *initial* index lookup — if a slot is removed (TV grid's
  "Close Slot" context menu, or Menu-press → `closeAll()`) while negotiation
  is still in flight, it creates a real server-side session, then silently
  returns at the final `guard`, never recording the session ID for teardown.
  This is directly reachable via the TV app's rapid open/close interactions.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/PlayerViewModel.swift` (MODIFY: add a stored, cancellable `Task` for `playChannel`/`playRecording`, mirroring `serverSeekTask`)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/MultiPlayerViewModel.swift` (MODIFY: guard `finishAddFeed` against the slot being removed mid-negotiation and tear down any session created after the fact)

- [x] **REV-APL-4 — [High] "Add to Multi-View" from the TV Guide reintroduces the flash-back bug the Player path explicitly fixed.**
  `TVPlayerView`'s handler deliberately calls `beginAddFeed(...)` synchronously
  before dismissing, with a comment explaining this avoids a flash back to
  the previous screen while the stream negotiates. `TVGuideView`'s "Add to
  Multi-View" (via `TVProgramDetailModal`) instead dismisses immediately and
  fires the combined `addFeed(...)` in an unstructured `Task`, so `slots`
  stays empty for at least a frame after dismissal.
  - **Files**:
    - `apple/HDHROpenTV/Views/Guide/TVGuideView.swift` (MODIFY: route through `beginAddFeed`/`finishAddFeed` like `TVPlayerView`)
    - `apple/HDHROpenTV/Views/Guide/TVProgramDetailModal.swift` (MODIFY: same)

- [x] **REV-APL-5 — [High] Focus index and audio routing desync from the multi-view grid after slot removal/swap.**
  `focusedSlotIndex` is tracked as a raw array index in TV-local `@State`;
  `MultiPlayerViewModel.removeFeed`/`swapSlots` shift/exchange the
  underlying `slots` array with no notification back to that index. The
  focus ring and the `onChange(of: focusedSlotIndex)`-triggered audio
  routing only fire on an actual index *value* change, so after a
  removal/swap the visually-focused tile and the live-audio tile can point
  at different content than expected.
  - **Files**:
    - `apple/HDHROpenTV/Views/Player/MultiView/TVMultiPlayerView.swift` (MODIFY: explicitly re-push focus/audio state after `removeFeed`/`swapSlots`, mirroring the existing `closeEditBar()` round-trip-through-nil pattern)
    - `apple/HDHROpenTV/Views/Player/MultiView/TVMultiViewGrid.swift` (MODIFY: same)

- [x] **REV-APL-6 — [Medium] Secondary-action failures are silently swallowed with `try?`, and `PlayerViewModel`/`MultiPlayerViewModel` have no error-surfacing property.**
  All recording-rule actions in `iOSPlayerView.swift`'s Record menu use
  `try? await guideViewModel.recordX(...)` — on failure, the menu just
  closes as if it succeeded. `promoteToRecording()` only logs on failure.
  Unlike `GuideViewModel`/`AuthViewModel` (both expose `error: String?`),
  playback ViewModels only surface *fatal* errors via `playerEngine.state`,
  with no channel for secondary-action failures.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/PlayerViewModel.swift` (MODIFY: add an `error: String?` property matching `GuideViewModel`'s convention)
    - `apple/HDHROpeniOS/Views/Player/iOSPlayerView.swift` (MODIFY: route Record-menu actions through it instead of `try?`)

- [x] **REV-APL-7 — [Medium] `loadRecordingMetadata`'s background `Task` is never cancelled on `closePlayer()`.**
  `closePlayer()` correctly cancels `serverSeekTask` and `captionPollTask`,
  but the metadata-fetch task is fire-and-forget with no stored handle. If
  the player closes mid-fetch, this task can still complete afterward and
  silently repopulate `thumbnailCues`/`thumbnailSpriteURL` on a
  just-reset engine for a session the user already left.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/PlayerViewModel.swift` (MODIFY: store and cancel this `Task` in `closePlayer()`)

- [x] **REV-APL-8 — [Medium] Server-side seek resumes playback even if the player was paused.**
  `loadMedia` (`PlayerEngine.swift`) unconditionally calls `avPlayer?.play()`
  at the end regardless of pre-seek state. A paused user who scrubs to an
  unbuffered position (triggering the server-seek path) will have playback
  silently resume.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Playback/PlayerEngine.swift` (MODIFY: accept/respect an autoplay-intent parameter instead of always playing)

- [x] **REV-APL-9 — [Medium] Icon-only transport buttons lack accessibility labels and adequate hit targets.**
  Captions/info/PiP/skip buttons in `iOSPlayerView.swift` have no
  `.accessibilityLabel` (VoiceOver reads raw SF Symbol names like
  "gobackward.10") and no explicit `.frame(minWidth: 44, minHeight: 44)`,
  falling under Apple's HIG minimum. `iOSScrubBarView.swift` already gets
  this right — apply the same pattern.
  - **Files**:
    - `apple/HDHROpeniOS/Views/Player/iOSPlayerView.swift` (MODIFY: add accessibility labels and 44×44pt hit targets to transport buttons)

- [x] **REV-APL-10 — [Medium] No test exercises cancellation or race conditions in `PlayerViewModel`, despite that being most of its real complexity.**
  Grepping all `PlayerViewModel*Tests.swift`/`MultiPlayerViewModelTests.swift`
  for "cancel" returns zero matches. No coverage proves a superseded seek
  stops its stale HLS session, that double-tapping a channel doesn't leak a
  session (REV-APL-3), or that closing the player mid-metadata-fetch
  doesn't repopulate stale state (REV-APL-7).
  - **Files**:
    - `apple/HDHROpenKit/Tests/HDHROpenKitTests/` (NEW: cancellation/race-condition regression tests, added alongside REV-APL-3/REV-APL-7 fixes)

- [x] **REV-APL-11 — [Medium] tvOS tests exercise the view tree, not the focus engine.**
  Every ViewInspector-based test in `TVMultiPlayerViewTests.swift`/
  `TVPlayerViewTests.swift`/`TVAIAssistantModalTests.swift` asserts static
  structure, never `@FocusState` transitions or the two-way
  `focusedSlotIndex`/`slotFocus` sync in `TVMultiViewGrid`. Given how much
  of this codebase's bug history lives in focus behavior (per extensive
  inline comments), this is the risk area with the least regression
  coverage — a bug like REV-APL-5 would not be caught by the current suite.
  - **Files**:
    - `apple/HDHROpenTVTests/TVMultiPlayerViewTests.swift` (MODIFY: add focus-transition and audio-routing-sync assertions)

- [x] **REV-APL-12 — [Medium] Tuner-exhaustion warning in multi-view is easy to miss and never refreshed.**
  Rendered at 11pt in the bottom corner of a quad-grid tile — effectively
  unreadable at 10-foot viewing distance. Computed once at `finishAddFeed`
  time and never re-evaluated as tuners free up or become further exhausted
  while the slot is playing. TODO.md's original multi-view spec specifically
  calls for a "graceful slot-level warning" — this undersells it both
  visually and temporally.
  - **Files**:
    - `apple/HDHROpenTV/Views/Player/MultiView/TVMultiViewSlotOverlay.swift` (MODIFY: larger/more prominent warning treatment, re-evaluated periodically)

- [x] **REV-APL-13 — [Medium] Slot "Close" and "Make Primary" are only reachable via an undiscoverable long-press context menu.**
  These actions exist only inside `.contextMenu` on each tile, requiring a
  long click-and-hold Siri Remote press, with no on-screen hint anywhere
  that a tile supports this. In a 10-foot UX with no cursor/hover affordance
  to reveal it incidentally, a first-time user has no way to discover this
  short of trial-and-error or documentation.
  - **Files**:
    - `apple/HDHROpenTV/Views/Player/MultiView/TVMultiViewGrid.swift` (MODIFY: add a visible hint/icon indicating long-press actions)

- [x] **REV-APL-14 — [Low] `WatchSessionManager` carries two parallel, permanently-coexisting APIs.**
  The multi-session API (`startSession`/`stopSession`/`promoteSession`) and
  a "Single-Session Backward Compatibility" wrapper (`startWatch`/
  `promoteWatch`/`stopWatch`) both stay permanently live — `PlayerViewModel`
  uses the compat wrapper while `MultiPlayerViewModel` uses the multi-session
  API directly, sharing mutable state (`activeSessionId`) in ways that are
  easy to get subtly wrong.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Networking/WatchSessionManager.swift` (MODIFY: have `PlayerViewModel` adopt the multi-session API with its own session-id property)

- [x] **REV-APL-15 — [Low] `MultiPlayerViewModel` keeps up to 4 concurrent `AVPlayer` instances decoding simultaneously.**
  Only audio-muted, not paused, unless `pauseBackgroundSlots` is explicitly
  invoked — worth a performance/battery gut-check on iPad multi-view
  specifically (in addition to whatever tvOS hardware constraints apply).
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/MultiPlayerViewModel.swift` (MODIFY: consider pausing/reducing decode work for unfocused slots by default)

- [x] **REV-APL-16 — [Low] `TVAIAssistantModal` doesn't explicitly claim initial focus.**
  Every other TV overlay/modal (`TVPlayerSettingsOverlay`, `TVSyncPlayOverlay`,
  `TVPlayerRecordMenuOverlay`, `TVChannelSwitcherOverlay`, the multi-view
  edit bar) has an explicit `@FocusState` + `.onAppear` claim with a comment
  explaining tvOS won't auto-retarget focus onto a newly appeared subtree.
  `TVAIAssistantModal` has neither, looking like an oversight rather than a
  considered exception.
  - **Files**:
    - `apple/HDHROpenTV/Views/AI/TVAIAssistantModal.swift` (MODIFY: add `@FocusState` + `.onAppear` default-focus claim matching the rest of the codebase)

- [x] **REV-APL-17 — [Low] `APIClient` swallows non-JSON error bodies; SyncPlay WebSocket URL puts the bearer token in a plain query string.**
  `extractErrorDetail` only parses `{"detail": "string"}`, discarding any
  other error body shape into a generic "Request failed with status code N".
  Separately, `syncPlayWsUrl` encodes the bearer token directly into the
  `wss://` URL query string — worth confirming no log statement captures
  the full URL for this specific case (other HLS-session logs do log full
  playlist URLs, but those don't carry this token).
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Networking/APIClient.swift` (MODIFY: broaden error-detail extraction; audit logging around `syncPlayWsUrl`)

- [x] **REV-APL-18 — [Low] `.onMoveCommand`'s "intercepts everything" workaround has no regression test.**
  A long comment in `TVPlayerView.swift:264-289` explains a hard-won,
  non-obvious platform behavior (an `.onMoveCommand` anywhere in the ZStack's
  modifier chain intercepts 100% of directional presses on-device) and
  structures a conditional fallback focus target to work around it — exactly
  the kind of quirk that regresses silently if "simplified" back into a
  modifier during a refactor, with no test asserting the fallback behavior.
  - **Files**:
    - `apple/HDHROpenTVTests/TVPlayerViewTests.swift` (NEW: assert fallback-focus-then-reveal-controls behavior via move commands)

- [x] **REV-APL-19 — [Low] `apple/check.sh`'s combined coverage gate fails: 78.54% vs. the 80% threshold.**
  Discovered by running `check.sh` to completion for the first time (it had
  previously always stopped earlier, at the SwiftFormat stage, before any
  REV-APL-1..18 session ran it this far). SwiftLint, SwiftFormat, and every
  `HDHROpenKit`/`HDHROpeniOS`/`HDHROpenTV` test suite now pass; only the
  coverage threshold does not. The shortfall is concentrated in large,
  mostly pre-existing view/coordinator files largely untouched by the
  REV-APL-1..18 fixes: `TVMultiPlayerView.swift` (14.5%),
  `SharePlayCoordinator.swift` (30.2%), `iOSAIAssistantSheet.swift` (35.5%),
  `TVAIAssistantModal.swift` (36.8%). Treated as separate, pre-existing repo
  debt rather than part of the REV-APL-1..18 scope.
  - **Files**:
    - `apple/HDHROpenTV/Views/Player/MultiView/TVMultiPlayerView.swift` (NEW/MODIFY tests)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Playback/SharePlayCoordinator.swift` (NEW/MODIFY tests)
    - `apple/HDHROpeniOS/Views/AI/iOSAIAssistantSheet.swift` (NEW/MODIFY tests)
    - `apple/HDHROpenTV/Views/AI/TVAIAssistantModal.swift` (NEW/MODIFY tests)

