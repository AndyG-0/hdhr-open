# TODO

Forward-looking roadmap, broken into single-session/feature-sized iterations.
Each item names the files it touches so a future session can pick it up and
go without re-deriving context. Earlier completed review/hardening passes
are documented in the commit history (see `f856635`, `22c3767`, `13600a9`,
and the backend/frontend/architecture cleanup sessions from 2026-08-23/24)
rather than repeated here.

## Closed Captioning

Captioning is inconsistent or broken across every client. The backend
already has a full CEA-608/708 extraction subsystem
(`backend/app/dvr/media_cache.py`) producing WebVTT for recordings and
in-progress "watch sessions," served via `GET /api/dvr/recording-captions.vtt`.
Each client wires it up differently and incompletely — see below.

- [x] **CC-3 — Backend: diagnose/harden live caption extraction
  reliability.** Latency root cause confirmed closed, not a tuning problem:
  live captions lag real dialogue by 10-15s (sometimes 20s+) because a cue
  isn't emitted by ffmpeg's WebVTT muxer until the CEA-608/708 roll-up
  decoder's buffer advances — inherent to the format, not fixable without
  abandoning ffmpeg's `movie`/`subcc` filter. Don't re-investigate this
  without a live tuner attached. Remaining scope was resiliency, and two
  gaps got fixed in `media_cache.py`'s `_run_live_caption_process_once`/
  `_run_live_caption_loop`: (1) a cue-silence watchdog
  (`_LIVE_CAPTION_CUE_SILENCE_SECONDS`) that trips when the ffmpeg process
  keeps producing bytes but completes no cue for 180s — the pre-existing
  stdout-silence watchdog couldn't catch a wedged muxer that keeps
  dribbling output; (2) escalating backoff (2s → 4s → 8s → ... capped at
  120s) plus a circuit breaker that gives up after 8 consecutive quick
  failures, adding the recording to `_live_caption_disabled` so a source
  with persistently corrupt CC data stops hot-looping full restarts forever
  (`ensure_live_captions` no-ops once disabled; `stop_live_captions` clears
  the flag). Live TV viewing and in-progress DVR recordings share this same
  mechanism (`ActiveCapture`, live viewing is just an `is_temporary=True`
  capture — see `backend/app/dvr/builtin/watch.py`), so this hardening also
  covers rewinding live TV. Tests in `backend/tests/test_media_cache.py`.
  **Real-tuner follow-up (2026-08-30):** verified on real hardware; also
  found and fixed a correctness bug in the same pipeline — ffmpeg's
  CEA-608 decoder renders the "transparent space" special character as the
  literal text `\h` (or `\h\h`), which the webvtt muxer passed through
  unchanged into displayed captions on both web and Android.
  `_strip_cc_control_artifacts()` in `media_cache.py` now cleans it from
  both the live-cue path (`_parse_vtt_block`) and the finished-recording
  generation path (`_generate_captions_vtt_uncached`); tests in
  `test_media_cache.py`. The residual live-caption lag observed on that
  same hardware is tracked separately as CC-8.

- [x] **CC-1 — Android: wire captions into live playback.** Done. Caption
  fetch now polls every 1.5s while a recording is in progress (both the
  live-channel watch-session path and DVR items still recording when opened
  from the recordings list), with cue timestamps aligned to the player's own
  clock and live-cue stretching so already-lagged cues still display instead
  of silently expiring (`PlayerViewModel.kt`: `fetchCaptionsOnce`,
  `startCaptionPolling`, `alignLiveCues`). Remaining visible lag is CC-3's
  server-side extraction latency, not a client bug. Tests added in
  `CaptionControllerTest.kt`.

- [x] **CC-4 — Backend: eager caption extraction on recording completion.**
  `generate_captions_vtt()` ran lazily on first
  `GET /api/dvr/recording-captions.vtt`, which could block that request up
  to several minutes for a long recording. `capture.py`'s `stop_capture()`
  now schedules it eagerly via the existing `run_in_background()`
  fire-and-forget helper as soon as the finished file's probe reports
  `has_captions`, alongside the existing poster-backfill trigger. This
  introduced a real race: a client's on-request fetch could now run
  concurrently with the new eager trigger, both invoking ffmpeg against the
  same file. Fixed by coalescing concurrent callers in `media_cache.py`
  onto a single in-flight task per `recording_id`
  (`_generate_captions_inflight`, mirroring the existing
  `_live_caption_tasks` dict pattern). Tests in
  `backend/tests/test_dvr_capture.py` and `test_media_cache.py`.

- [x] **CC-6 — Android: resync captions on seek/scrub/FF/rewind.**
  `PlayerScreen.kt`'s scrub bar and skip buttons called `PlayerEngine.seek`/
  `skipForward`/`skipBackward` directly, bypassing `PlayerViewModel`
  entirely — so `alignLiveCues`'s live-cue positioning went stale after any
  scrub, FF, or rewind (including rewinding live TV, which is just an
  in-progress watch-session recording under the hood) until the next 1.5s
  poll happened to catch up. Fixed by adding `seek`/`skipForward`/
  `skipBackward` wrappers to `PlayerViewModel.kt` that delegate to
  `playerEngine` and then immediately re-run `alignLiveCues` against the
  new position via a new `resyncCaptionsAfterSeek()`; `PlayerScreen.kt`'s
  three call sites now go through the view model. Deliberately does **not**
  call `resetCueStretch()` — `stretchedCueDisplay`'s windows are absolute-
  time and cue-id-keyed, so `alignLiveCues` recomputes display coordinates
  fresh on every call without needing the map cleared. Clearing it would
  make nearly every previously-stretched cue look "newly arrived"
  simultaneously (Android re-fetches the full caption history each poll,
  unlike web's incremental append), replaying the whole caption history in
  back-to-back stretch slots right after a seek. Tests in new
  `PlayerViewModelSeekResyncTest.kt`. Like CC-2, on-device verification
  (real tuner) that scrubbing/rewinding live TV and an in-progress
  recording don't produce misaligned or replayed captions, and that a
  just-finished recording's captions show up promptly (CC-4) rather than
  after a long delay, can't be confirmed from code alone.

- [x] **CC-7 — iOS/tvOS: full caption parity (live polling + alignment +
  seek resync).** Ported Android's CC-1 + CC-6 caption pipeline to
  `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/PlayerViewModel.swift`
  one-for-one: the old single-shot captions fetch inside
  `loadRecordingMetadata` is now `fetchCaptionsOnce` followed by
  `startCaptionPolling`, which re-polls `recording-captions.vtt` every 1.5s
  while a recording is in progress (one final fetch after it stops, to
  catch the completed VTT); `alignLiveCues` remaps cue timestamps from
  capture-wall-clock onto the player's own clock and "stretches" already-
  expired-on-arrival cues into a synthetic display window, memoized per-
  cue-id in `stretchedCueDisplay`/`nextStretchSlotAbsolute` so repeated
  polls/seeks don't re-stretch or flicker; new `seek`/`skipForward`/
  `skipBackward` wrappers delegate to `playerEngine` and then immediately
  call `resyncCaptionsAfterSeek()` to re-run alignment against the new
  position from cached `lastRawCues`, instead of waiting on the next poll
  tick — deliberately **not** clearing `stretchedCueDisplay` on seek, the
  same CC-6 lesson (windows are absolute-time/cue-id keyed and alignment
  recomputes display coordinates fresh every call; clearing it would replay
  the whole caption history in back-to-back stretch slots after a seek,
  since both platforms do a full-VTT-refetch-and-replace per poll rather
  than incremental append). `iOSPlayerView.swift`'s and `TVPlayerView.swift`'s
  scrub-bar/skip-button call sites were repointed from
  `playerViewModel.playerEngine.seek/skipForward/skipBackward` to the new
  `playerViewModel` wrappers. One deliberate deviation from a literal port:
  unlike Android's synchronous ExoPlayer-wrapper `currentTime` update,
  `AVPlayer.seek` is asynchronous, so `PlayerEngine.seek` now sets
  `currentTime` optimistically before the async seek completes, so the
  resync logic reads the new position immediately rather than duplicating
  `PlayerEngine`'s clamping logic in the view model. Tests in new
  `CaptionControllerTests.swift` (6 cases, mirroring
  `CaptionControllerTest.kt`) and `PlayerViewModelSeekResyncTests.swift` (4
  cases, mirroring `PlayerViewModelSeekResyncTest.kt`, including the CC-6
  regression case that a second seek doesn't re-stretch or move an already-
  stretched cue's window). `swift test --package-path apple/HDHROpenKit`
  (22/22 passing) and `xcodebuild` for both the `HDHROpeniOS` and
  `HDHROpenTV` schemes were used to verify; like CC-2/CC-6, on-device
  verification of live caption polling/alignment/seek-resync behavior on a
  real tuner can't be confirmed from code alone in this environment.

- [x] **CC-2 — full fix: real (temporary) DVR capture backs the busy-tuner
  direct-HLS fallback, on all three platforms.** The gap ran deeper than
  originally scoped: `POST /api/streaming/hls/{channel_number}` (the
  fallback iOS/tvOS/Android all take when a watch session can't start) had
  no `recording_id` at all — a bare ffmpeg→raw-URL→HLS pipe — so there was
  nothing for any client's `loadRecordingMetadata()` to load. Fixed at the
  root instead of papering over it client-side. Backend
  (`backend/app/dvr/builtin/watch.py`): extracted `_build_capture_for_channel`
  out of `start_watch`'s capture-creation closure and added
  `start_fallback_capture`/`release_fallback_capture`, which call
  `capture_pipeline.get_or_start_capture` directly — deliberately bypassing
  `tuner_allocator`'s admission gate (that's this fallback's whole reason to
  exist), then best-effort-registering the tuner token afterwards so the
  allocator's bookkeeping stays accurate when possible without reintroducing
  the rejection this path is meant to avoid. `backend/app/hls_streaming.py`
  gained a generic `on_teardown` hook on `HLSSession`/`create_session` (the
  only teardown signal this idle-timeout-reaped path ever gets), and
  `backend/app/api/streaming.py`'s `stream_channel_hls` now mints a real
  capture, pumps it into ffmpeg via `pump_tail_follow` exactly like
  `dvr.py`'s `stream_recording_hls`, and releases it via `on_teardown` —
  falling back to the original raw-URL pipe only if even the unmanaged
  capture can't start. The response always carries a `title` (channel name
  as a placeholder when there's no capture) since every client decodes it as
  recording metadata regardless of which path was taken. iOS/tvOS
  (`PlayerViewModel.swift`, `Recording.swift`, `APIClient.swift`) and Android
  (`PlayerViewModel.kt`, `Recording.kt`, `APIClient.kt`): added
  `playlistUrl`/`playlist_url` to the shared recording model,
  `createChannelHLSSession` now returns the full recording type instead of a
  bare `{session_id, playlist_url}` struct, and `playChannel`'s fallback
  branch calls `loadRecordingMetadata` whenever the response carries a
  `recording_id` — same captions/thumbnails/detail wiring the primary
  watch-session path already had, automatically covering both iOS and tvOS
  via the shared `PlayerViewModel`. Also dropped iOS's dead `WatchResponse`
  struct while touching that file (unused — `startWatch` already decoded
  straight into the shared recording type). Tests: 6 new backend cases in
  `test_api_streaming.py`/`test_hls_streaming.py` (498/498 backend suite
  passing); 2 new iOS cases in `PlayerViewModelChannelFallbackTests.swift`
  using a `URLProtocol`-based mock (24/24 `swift test` passing); 2 new
  Android cases in `PlayerViewModelChannelFallbackTest.kt` using `mockk`
  (full `:core:test` suite passing). No live-tuner access in this
  environment — real concurrent-viewer tuner-exhaustion behavior and
  confirming the best-effort `tuner_allocator` token degrades gracefully
  (doesn't wedge a later `start_watch` call) when it fails to acquire still
  need on-device verification.

- [x] **CC-8 — Backend: swap live captions to `ccextractor`'s real-time
  stream mode; custom decoder not needed.** Research + a feasibility spike
  (2026-08-31, see `backend/scripts/cc8_realtime_caption_spike.py`) found a
  much better fix than expected. Prior sessions couldn't test this without a
  live tuner; that constraint is gone — `backend/recordings/MLB_Baseball_1788116400_661a1195.ts`
  is a real local recording with genuine embedded CEA-608 captions, good
  enough to measure actual flush latency end-to-end.
  - **Root cause, confirmed and reproduced locally:** ffmpeg's
    `movie`/`subcc` lavfi chain (`_run_live_caption_process_once`,
    `_generate_captions_vtt_uncached`) can't flush a WebVTT cue until the
    roll-up buffer advances — i.e. until the *next* line of dialogue starts
    pushing the current one up. Confirmed byte-for-byte against the local
    recording and, more importantly, measured with the actual pipeline
    **paced to real time** (`ffmpeg -re`, not just replayed as fast as
    possible): reading ffmpeg's output incrementally and timestamping the
    wall-clock moment each cue is actually written to the pipe (not the
    timestamp embedded in the cue text) gives the number that matters for a
    live client. Result over 49 matched lines: **avg 1.96s of avoidable
    lag, up to 7.7s** on longer pauses between lines — this is on top of
    normal roll-up-format lag, and it's the part that's fixable.
  - **`ccextractor`'s live/growing-file mode (`-s`) already fixes almost
    all of it — no custom decoder needed.** Piping the same recording into
    `ccextractor --stdin -s <timeout> -out=srt -stdout`, real-time-paced
    the same way, and measuring with the same methodology: **avg delta
    ~0.0s vs. a byte-level real-time reference decoder** (min -0.41s, max
    +1.05s — noise-level), vs. ffmpeg's 1.96s avg / 7.7s worst-case over the
    same window. `ccextractor` reads the raw CEA-608/708 byte pairs and
    emits a completed line the instant its own carriage-return code is
    seen, rather than waiting for the *next* line — exactly the behavior a
    custom decoder (see below) would have had to be built to get. This was
    the single biggest surprise of this research: the "large effort, custom
    decoder" option turned out to be unnecessary.
  - **Implemented (2026-09-01):** `_run_live_caption_process_once` in
    `media_cache.py` now spawns `ccextractor --stdin -s 999999999 -out=srt
    -stdout -o /dev/null --quiet` instead of ffmpeg, fed via the same
    `pump_tail_follow` → stdin source as before. New `_parse_srt_block`
    parses ccextractor's SRT output (including the `\r\n` line-ending
    normalization and `<font>`-tag-based CEA-708-track filtering the spike
    needed), reusing `_strip_cc_control_artifacts` for cleanup. Output is
    still written as WebVTT via the unchanged `_append_live_cues`, so
    `live_captions_path`'s `.live.vtt` file and everything downstream of it
    (every client) is unaffected by this swap — no client-side changes were
    needed for the decode-source change itself. `--quiet` (verified: empties
    stderr entirely without hiding real errors, unlike `--no-progress-bar`
    alone which leaves ccextractor's banner/config dump/stats-summary in
    place) keeps `_drain_stderr_logging`'s "anything here is worth
    surfacing" invariant intact. The finished-recording path
    (`_generate_captions_vtt_uncached`) is unchanged — it stays on ffmpeg,
    since a one-shot decode of a complete file has no latency requirement.
    Tests in `backend/tests/test_media_cache.py` updated to push
    SRT-formatted fake stdout; full suite (527 tests) passes.
  - **Now deployable — see CC-9,** which packaged `ccextractor` into
    `backend/Dockerfile`'s production base image (previously it wasn't
    there and the circuit breaker,
    `_LIVE_CAPTION_MAX_CONSECUTIVE_QUICK_FAILURES`, would have quietly
    disabled live captions for every capture after ~6 minutes of failed
    process spawns).
  - Scoped as backend + web client only, matching how CC-1/CC-6 (Android)
    shipped before CC-7 ported to Apple — Android/iOS/tvOS parity is a
    separate follow-up (see CC-10/CC-11/CC-12 below for the specific piece
    that now matters: simplifying client-side lag-compensation logic that's
    no longer doing as much work).
  - **Custom real-time CEA-608 decoder (reading raw ATSC A53 frame
    side-data directly, bypassing ffmpeg entirely) — no longer recommended
    as the primary path**, now that `ccextractor` measures at parity with
    it. Every video frame in the test recording carries this side-data
    (confirmed via `ffprobe -show_frames -show_entries side_data_list`,
    type `ATSC A53 Part 4 Closed Captions`) and PyAV can read it
    frame-by-frame, so the option is still technically available if
    `ccextractor` turns out to have gaps (CC3/708-only content, extended
    character sets, licensing) — but building and maintaining a decoder
    from scratch isn't justified when an existing, actively-maintained tool
    already gets the same result.
  - **Push-based delivery (SSE instead of client polling)** is still worth
    doing regardless of which decode path is used — it trims the client's
    *own* added delay (currently up to ~1-1.5s from polling intervals) on
    top of whatever the backend now delivers — but it's a separate,
    smaller change, not a substitute for the decode-side fix above.
  - Once live captions no longer arrive late in batches, the client-side
    compensation logic built specifically to cope with that can likely be
    simplified — see CC-10/CC-11/CC-12 below, one per client. Out of scope
    for this backend change itself, and shouldn't be attempted before the
    backend swap is verified against a real tuner (next bullet).
  - **Testing constraint, updated:** local recording testing (above) is
    sufficient to validate the *decode/latency* approach without a tuner.
    Final verification of the shipped implementation — particularly
    `ccextractor`'s behavior against a genuinely live, still-growing file
    over hours of real broadcast (not a static recording) — still needs a
    real tuner, consistent with every prior CC-3/CC-8 note.
  - Related, already fixed (see CC-3): the `\h` control-artifact leak found
    during that session's real-tuner testing was a separate correctness
    bug, not a latency contributor — don't re-open it here.

- [x] **CC-9 — Backend: package `ccextractor` into `backend/Dockerfile`
  (blocks CC-8 from actually running in production).** `ccextractor` isn't
  in Debian bookworm's apt repos (only bullseye/oldoldstable and
  sid/unstable), and has no official prebuilt arm64/aarch64 Linux binary
  (only x86_64 AppImage/.deb/tar.gz and Windows) — `backend/Dockerfile`
  explicitly supports arm64 (Raspberry Pi) as a production target, so this
  needed a from-source multi-stage build. Added a `ccextractor-builder`
  stage to `backend/Dockerfile`, pinned to release tag `v0.96.6` (not
  `master`, for reproducibility) rather than the Debian package, following
  ccextractor's own reference recipe (`docker/Dockerfile` in the
  ccextractor repo): apt build deps, Rust via rustup, GPAC v2.4.0 built
  from source, ccextractor's Rust component via cargo, then its hand-
  crafted final `gcc` link step with `BUILD_TYPE=minimal` (no OCR/hardsubx
  — only stream-mode CEA-608/708 byte decode is used here). The runtime
  stage copies the compiled `ccextractor` binary and `libgpac.so*` in,
  alongside the matching runtime shared-lib deps (`libpng16-16`,
  `libjpeg62-turbo`, `zlib1g`, `libssl3`, `libcurl4`), before the existing
  `USER hdhropen` switch.
  - **Verified on both target architectures.** Built the `ccextractor-
    builder` stage standalone for both `linux/arm64` (native on this
    Apple Silicon host) and `linux/amd64` (via podman machine's qemu
    emulation), then ran the compiled binary against a real chunk of
    `backend/recordings/MLB_Baseball_1788116400_661a1195.ts` (the same
    file CC-8's own spike validated against) on each — both correctly
    decode real CEA-608 caption text to SRT, not ccextractor's crash-
    report banner (the exact failure mode CC-14's research caught once
    with the `-12` flag). `--version` on the amd64 build reports internal
    version string `0.96.5`, but its reported Git commit
    (`185631dcb0217b4ad09d43009cb69f0593996a5d`) matches the `v0.96.6` tag
    exactly, confirmed via `git ls-remote --tags` — the built binary is
    genuinely v0.96.6; ccextractor's own embedded version string just
    lags one release behind their git tags (an upstream quirk, not a
    build issue here).
  - **Known gap, unrelated to this change: the *full* image build
    currently fails.** `podman build -f backend/Dockerfile .` (no
    `--target`) fails at the pre-existing `COPY --from=ghcr.io/astral-sh/
    uv:latest` line with a 403 Forbidden pulling that base image from
    ghcr.io — reproduced directly via `podman pull ghcr.io/astral-sh/
    uv:latest`. That `COPY` line predates this session's changes and is
    an environment/registry-access issue (anonymous pull rate-limiting or
    similar), not something introduced by the ccextractor stage. Building
    just the new `ccextractor-builder` target (`--target
    ccextractor-builder`) sidesteps it entirely, which is how both
    verifications above were done. Whoever builds the full production
    image next may need registry auth (`podman login ghcr.io`) or to
    retry once any rate limit clears.
  - Still true, unchanged from CC-8: final verification against a
    genuinely live, growing capture over real broadcast hours still needs
    a real tuner, not a static recording file.

- [ ] **CC-10 — Web: simplify live-caption lag-compensation logic once
  CC-8/CC-9 are verified on real hardware.** `caption-controller.ts` and
  `HDHomeRunPlayer.svelte` currently stretch/align live cues
  (`LIVE_CUE_MIN_DISPLAY_SECONDS`, `alignLiveCues`, `baseOffsetSeconds` drift
  correction) specifically to paper over cues arriving several seconds late
  in batches. CC-8's ccextractor swap should make that arrival pattern
  mostly go away — once verified against a real tuner (CC-8's testing
  constraint), revisit whether this logic can be trimmed down or removed.
  Don't start this before that real-tuner verification, since the whole
  premise depends on it.

- [x] **CC-11 — Android: fix the same permanent live-caption freeze CC-13
  found and fixed on web.** Scope note: the ticket originally envisioned
  "simplify lag-compensation logic once CC-8/CC-9 are verified on real
  hardware" — that broader simplification is **still blocked** on real-tuner
  verification and was **not** attempted here (same precondition as CC-10,
  unchanged below). What actually shipped instead: `PlayerViewModel.kt`'s
  `alignLiveCues` (`~line 453`) had the exact same bug CC-13 found on web —
  `nextStretchSlotAbsolute` advanced by `LIVE_CUE_STRETCH_SECONDS` per
  stretched cue but was never reset to "now" at the top of each call, so it
  drifted monotonically ahead of real time across *separate* polls and
  pinned every later cue behind an unreachable backlog. This is a live,
  reproducible bug independent of CC-8/CC-9's real-tuner caveat (CC-13
  verified its web fix the same way, with a two-separate-polls unit test),
  so it's fixed now rather than left to wait on hardware that isn't the
  actual blocker. Fix: reset the cursor to "now" at the top of every
  `alignLiveCues` call, plus a new `LIVE_CUE_MAX_CATCHUP_SECONDS` (20s,
  mirroring web's constant) cap so a large backlog burst is left unstretched
  past that point instead of queuing arbitrarily far into the future.
  Regression tests added mirroring CC-13's shape (two stale cues delivered
  on two separate poll-equivalent calls; a 20s+ backlog burst). Full
  `./gradlew :core:test` suite green.

- [x] **CC-12 — iOS/tvOS: fix the same permanent live-caption freeze CC-13
  found and fixed on web.** Same scope note as CC-11: the broader "simplify
  lag-compensation" work this ticket originally envisioned is still blocked
  on CC-8/CC-9's real-tuner verification and wasn't attempted — this ported
  CC-11's Android freeze-bug fix 1:1 to `apple/HDHROpenKit/Sources/
  HDHROpenKit/ViewModels/PlayerViewModel.swift`'s `alignLiveCues`
  (structural parity with Android maintained since CC-7): reset
  `nextStretchSlotAbsolute` to "now" at the top of every call, plus a
  `liveCueMaxCatchupSeconds` (20.0) cap. Two new regression tests in
  `PlayerViewModelSeekResyncTests.swift` mirror CC-11/CC-13's shape
  (`testStretchCursorReAnchorsToNowEachCallInsteadOfDriftingAcrossSeparatePolls`,
  `testStaleCuesBeyondTheMaxCatchupCapAreLeftUnstretchedInsteadOfQueuedForever`).
  Full `swift test --package-path apple/HDHROpenKit` suite green (36/36).

- [x] **CC-13 — Web: fix permanent live-caption freeze; Backend: fix a
  second CC track leaking into the primary caption text.** Two bugs found
  from a real user report ("shows the first caption, then stops") and
  diagnosed from two real production logs (backend healthy throughout both:
  no `ccextractor` restarts, no circuit-breaker trips, per-cue lag a steady
  2.3-4.9s) plus the user's own dev-tools observation that `captionCues`
  kept growing while the on-screen line never advanced — which pointed the
  bug at client-side rendering, not the network/polling layer.
  - **Root cause (web):** `caption-controller.ts`'s `appendCaptionCues`
    "stretches" a live cue that arrives already past its natural end onto a
    reserved display slot (`nextStretchSlotAbsolute`), advancing it by
    `LIVE_CUE_MIN_DISPLAY_SECONDS` (4s) per cue. That cursor persisted
    across *separate polls*, not just within one poll's batch — but real
    cue cadence (~2.85s average, bursts as tight as 0.4-0.6s apart) is
    faster than that 4s window, so the reserved slot drifted further ahead
    of real time on every cue, got pinned near the 20s `LIVE_CUE_MAX_
    CATCHUP_SECONDS` cap, and every cue after that queued behind an
    unreachable backlog — a permanent freeze, not the self-correcting
    bounded lag it initially looked like from static code reading alone.
  - **Fix (web):** reset `nextStretchSlotAbsolute` to "now" at the top of
    every `appendCaptionCues` call made with `allowStretch: true` (i.e.
    every live poll), leaving the same-poll staggering behavior (for a
    burst of several stale cues delivered together) untouched. New
    regression test in `HDHomeRunPlayer.test.ts` (`'re-anchors each poll to
    now instead of drifting forward across separate polls'`) delivers two
    stale cues on two *separate* polls rather than one batch; confirmed to
    fail pre-fix (second cue stuck 4s behind instead of alongside the
    first) and pass with the fix. Full suite green (276/276).
  - **Root cause (backend), found only after the freeze fix let captions
    render continuously:** `_run_live_caption_ccextractor_process` in
    `media_cache.py` never restricted which caption channel `ccextractor`
    decodes. Per `ccextractor --help`'s own notes, its default behavior
    extracts **both** CEA-608 and CEA-708 and interleaves them into one
    stdout stream; `_parse_srt_block`'s `<font>`-tag check (meant to filter
    out the 708 track) is a heuristic, not a real separator — confirmed
    against a real local recording that many 708 lines carry no `<font>`
    wrapping at all (output size roughly doubles without a channel
    restriction, and only a fraction of the extra lines are tagged), so
    second-track content slipped through disguised as primary captions.
    Previously invisible because the freeze bug meant only the very first
    cue ever rendered.
  - **Fix (backend):** added `-1` to the `ccextractor` argv, restricting
    decode to CEA-608 field 1/channel 1 (the primary broadcast language)
    only, instead of relying on the `<font>`-tag heuristic. `test_media_
    cache.py`'s caption suite green (42/42); comments on `_SRT_FONT_TAG_RE`
    updated to describe it as a defensive fallback rather than the primary
    guard.
  - The local `MLB_Baseball_1788116400_661a1195.ts` recording used to
    verify this has no genuine secondary-language (CC2/CC3) content — its
    "second track" was CEA-708 duplicating the same English text, not
    Spanish — so this fix is verified against the *leak* (content appearing
    that shouldn't) but not against a real dual-language broadcast. See
    CC-14 for the follow-up that actually needs one.

- [x] **CC-14 — Backend + Web: let the user pick a CC track when a
  recording/live channel has more than one.** Follow-up to CC-13: some
  broadcasts (sports especially) genuinely carry a second CEA-608 channel
  ("usually Spanish" per `ccextractor --help`) worth exposing instead of
  just discarding it. Landed the recommended lazy/on-demand approach from
  this ticket's own spike notes, **scoped to in-progress (live) recordings
  only** — a deliberate, disclosed cut, not an oversight (see gap below).
  - **Backend** (`backend/app/dvr/media_cache.py`): threaded a
    `channel: int = 1` parameter through the existing live-caption
    pipeline instead of duplicating it — `_live_caption_tasks` and
    `_live_caption_disabled` are now keyed by `(recording_id, channel)`
    tuples so channel 1/2 supervision loops for the same recording don't
    collide; `_run_live_caption_process_once`'s hardcoded `-1` argv flag
    became `f"-{channel}"`. New channel-2-specific detection: since an
    absent second track isn't a crash (process stays alive, emits zero
    cues), a `_LIVE_CAPTION_TRACK2_GRACE_SECONDS` (20.0) timer treats
    "still alive, zero cues, grace period elapsed" as `"unavailable"`
    rather than restarting forever — reuses the existing
    `_live_caption_disabled` set/idempotency check rather than adding a new
    state store. New `live_caption_track2_status()` accessor for the API
    layer.
  - **API** (`backend/app/api/dvr.py`): `GET /api/dvr/recording-
    captions.vtt` takes `?track=1|2` (400 for anything else); `recording-
    detail` gained `secondary_captions: "unknown"|"available"|
    "unavailable"|null` (`null` = finished recording or never requested).
  - **Finished-recording gap, named as a follow-up, not silently
    unsupported:** finished recordings still decode via ffmpeg's
    `movie`/`subcc` filter, which has no verified way to select CEA-608
    channel 2 in this ffmpeg build, and piping a finished recording through
    ccextractor instead would mean fetching its (possibly remote) URL to a
    local byte stream first — bigger than this ticket's scope. A finished
    recording's `?track=2` request returns an explicit 404 ("Secondary
    caption track not available for finished recordings") rather than
    pretending to support it.
  - **Web** (`frontend/src/lib/api.ts`, `caption-controller.ts`,
    `HDHomeRunPlayer.svelte`): `hdhomerunRecordingCaptionsUrl` takes an
    optional `track` option; new `switchCaptionTrack()` on the caption
    controller resets `captionCues`/the stretch cursor and clears the
    native TextTrack before the caller re-fetches on the new track. Track
    picker mirrors the existing `currentAudioIndex` audio-track popover —
    shown only when `secondary_captions !== null` (i.e., an in-progress
    recording where a second track is at least conceivable); Track 2
    renders disabled (not hidden) when `secondary_captions ===
    'unavailable'`, so the user sees it was checked rather than just
    missing.
  - **Testing caveat, consistent with every other CC ticket's real-hardware
    note:** verified with fakes (the same way CC-8/CC-13's own suites fake
    ccextractor's stdout), not against a real dual-language broadcast — no
    such fixture exists locally (confirmed: `ccextractor -2` produces zero
    output on both local sample recordings, per CC-14's original spike
    notes). Backend suite green (547/547), frontend suite green (281/281,
    including new track-picker/track-switch/disabled-when-unavailable
    tests in `HDHomeRunPlayer.test.ts`).

- [x] **CC-5 — Scheduled Tasks admin, backend primitives.** Backend
  job-registry + runner + status/history API landed; the admin UI page is
  deliberately deferred (see follow-up below) — this was scoped as its own
  multi-part iteration and the backend half is the larger, harder-to-get-wrong
  piece. `backend/app/jobs.py` is a thin wrapper around the existing
  `backend/app/scheduler.py` `AsyncIOScheduler` singleton: `register_scheduled_job`
  wraps an interval-triggered callable so every firing writes a `job_runs`
  history row (status/started_at/finished_at/error) before/after running,
  and `register_event_job` + `run_tracked_in_background` do the same for
  jobs that aren't on a scheduler trigger at all — fired ad hoc via
  `asyncio.create_task`, same as the pre-existing `run_in_background`
  helper, just with history tracking layered on. New `job_runs` table via
  `backend/app/storage/db/connection.py`'s migration convention
  (`_MIGRATION_5`), queried through a new `backend/app/storage/db/jobs.py`.
  Registered the two named jobs: (1) recording-completion caption
  extraction (`backend/app/dvr/builtin/capture.py`'s `stop_capture()`) —
  still event-driven off recording completion, not interval-scheduled, just
  routed through `jobs.run_tracked_in_background` instead of the bare
  `run_in_background` call; (2) HLS idle-session reap + orphaned-directory
  sweep (`backend/app/hls_streaming.py`'s `register()`) — already
  interval-scheduled, just routed through `jobs.register_scheduled_job`
  instead of calling `scheduler.add_job` directly. New
  `backend/app/api/admin_jobs.py` (`GET /api/admin/jobs`, prefix
  `/api/admin/jobs`, gated the same way as `admin.py` via
  `Depends(get_current_admin)`) lists every registered job definition with
  its 10 most recent runs. Tests: `backend/tests/test_jobs.py` (registry
  wrapper writes success/failure history rows, both jobs show up as
  registered after a real app-lifespan boot) and
  `backend/tests/test_api_admin_jobs.py` (auth gating, run history in the
  response shape). Full backend suite green (508 passed).

- [x] **CC-5 follow-up — Scheduled Tasks admin UI page.** Built on top of
  the `/api/admin/jobs` API above, as a new
  `frontend/src/lib/components/settings/JobsSection.svelte` composed into
  `settings/+page.svelte` behind the existing `{#if $user?.role ===
  'admin'}` block — same pattern as every other admin-only
  `*Section.svelte` (e.g. `HouseholdMembersSection.svelte`), including its
  own `loadOnceWhen(() => $user?.role === 'admin', ...)` gate. Lists every
  registered job with its trigger badge (`Scheduled` vs `Event-driven`)
  and its 10 most recent runs (status/started/duration, plus the error
  text on a failed run); interval jobs get a "Run now" button, event jobs
  don't (nothing to nudge — they're not on a scheduler trigger). Backend
  gained the endpoint this button needed:
  `POST /api/admin/jobs/{job_id}/run` (`backend/app/api/admin_jobs.py`)
  calls new `jobs.trigger_job_now()`, which nudges the job's
  `next_run_time` via the scheduler itself (not calling its func
  directly) so `max_instances`/`coalesce` guards stay in effect; 404s for
  an unknown or event-driven job id, since neither is registered with the
  scheduler. `frontend/src/lib/api.ts` gained the matching `AdminJob`/
  `JobRun` types and `listJobs`/`triggerJob` calls. Also reworked
  `settings/+page.svelte`'s layout to CSS multi-column
  (`column-width`/`column-span: all` on group titles and the full-width
  `ChannelLineupSection`) so the extra section doesn't make the page
  unreasonably tall. Tests: `backend/tests/test_jobs.py` and
  `test_api_admin_jobs.py` (trigger success/404/auth-gating; full backend
  suite 513/513 passing) and new
  `frontend/.../settings/JobsSection.test.ts` (load/render, no-runs-yet,
  interval-only "Run now", failed-run error text, trigger-and-reload,
  load/trigger failure messaging — full `vitest run` shows no new
  failures beyond two pre-existing, unrelated ones in `theme.test.ts`/
  `routes/page.test.ts`).

## Native Client CI

`.github/workflows/ci.yml` currently only has `backend` and `frontend` jobs
— no coverage for `apple/` or `android/` at all.

- [x] **CI-1 — Android GitHub Actions job.** Added an `android` job to
  `.github/workflows/ci.yml`: `actions/setup-java@v4` (temurin, JDK 17) then
  `./gradlew :core:test`, matching the `backend`/`frontend` jobs'
  `defaults.run.working-directory` style. No ktlint/detekt config exists in
  the repo, so no separate lint step. Unverified until pushed (GitHub
  Actions can't be dry-run locally) — YAML syntax checked with Ruby's
  built-in `Psych` parser.

- [x] **CI-2 — Apple GitHub Actions job.** Added an `apple` job to
  `.github/workflows/ci.yml`: `swift test --package-path apple/HDHROpenKit`
  on `macos-15` (pinned rather than `macos-latest`, so the preinstalled
  Xcode version — and its iOS/tvOS 17 SDK support — doesn't silently shift
  over time). Unverified until pushed, same caveat as CI-1.

## Sideload Build Artifacts

Neither client has release signing configured today (Apple:
`CODE_SIGN_STYLE = Automatic`, no team ID committed; Android: no
keystore/signingConfig, `assembleRelease` would emit an unsigned APK). No
App Store / TestFlight plans currently — builds are for side-loading only.
Decided artifact venue: **GitHub Releases**.

- [x] **BUILD-1 — Android signed release APK via CI → GitHub Releases
  (wiring only — no keystore generated yet).** Wired everything except the
  actual release keystore, which needs the user directly in the loop (see
  below) — the code/workflow/docs are all in place and dry-run-verified.
  `android/app/build.gradle.kts` reads `storeFile`/`storePassword`/
  `keyAlias`/`keyPassword` from a local (gitignored) `keystore.properties`
  via `rootProject.file(...)`, falling back to `ANDROID_KEYSTORE_*` env vars
  so CI can supply them from secrets; when neither is present,
  `releaseStoreFile` stays `null` and the `release` build type gets no
  `signingConfig` at all, so a bare `./gradlew :app:assembleRelease`
  still produces an unsigned APK exactly as before this change (verified).
  `versionCode`/`versionName` are now overridable via
  `-PversionCode=/-PversionName=` (falling back to the old hardcoded
  `1`/`"1.0.0"`), so a release build isn't stuck re-shipping the same
  version. New `.github/workflows/android-release.yml`: manual
  `workflow_dispatch` (takes a `version_name` input), decodes an
  `ANDROID_KEYSTORE_BASE64` secret to a temp `.jks`, builds with
  `-PversionCode=${{ github.run_number }}` (monotonically increasing, no
  separate counter to maintain), deletes the temp keystore file
  unconditionally after, and publishes the signed APK to a GitHub Release
  via `softprops/action-gh-release@v2`. Added `keystore.properties`/`*.jks`/
  `*.keystore` to `.gitignore`. Documented both the local-dev
  `keystore.properties` flow and the CI secrets flow in `android/README.md`
  under a new "Installing a Release Build" section, plus sideload/install
  steps for the resulting APK. **Dry-run verified**: generated a
  throwaway, non-committed local keystore, confirmed
  `./gradlew :app:assembleRelease -PversionName=1.1.0-dryrun
  -PversionCode=999` produces a signed APK with those exact version values
  (`validateSigningRelease`/`writeReleaseSigningConfigVersions` tasks ran,
  which only happens when a `signingConfig` is actually attached), then
  deleted the throwaway keystore and `keystore.properties` — nothing
  keystore-related was ever staged or committed. YAML validated with
  Ruby's Psych parser (same approach as CI-1/CI-2, since this environment
  has no `pyyaml`/`actionlint`).
  **Update**: with the user's explicit go-ahead, the real release keystore
  now exists — `keytool -genkeypair`, alias `hdhropen-release`, PKCS12,
  10000-day validity (until 2054), stored outside the repo at
  `~/hdhr-open-android-release-key/` (never committed) with its password
  and SHA-256 cert fingerprint recorded in a `CREDENTIALS.txt` alongside
  it, which the user still needs to back up externally (password
  manager/encrypted storage) — this machine is not a durable store.
  Verified end-to-end: built and `apksigner verify --print-certs`-checked
  a real signed release APK against this keystore (cert DN and SHA-256
  fingerprint matched), then cleaned up the build output and the local
  `keystore.properties` used for the check.
  **Still not done**: adding the four `ANDROID_KEYSTORE_*` GitHub Actions
  secrets — this repo has no GitHub remote configured at all
  (`git remote -v` is empty), so there's nowhere to add them yet. Once a
  remote exists, run `base64 -i android-release.jks | pbcopy` on the file
  above and `gh secret set` the four values (all in `CREDENTIALS.txt`).

- [x] **BUILD-2 — Apple sideload docs (free-tier) + future paid-account
  plan.** Added a `## Sideloading` section to `apple/README.md` (after
  `## Running & Testing`): step-by-step Personal Team build+install
  (Xcode account sign-in, per-target Team selection under Signing &
  Capabilities, device UDID registration, trusting the developer cert on
  the device) plus a called-out limitations list (7-day profile expiry
  with no workaround short of a paid account, the 3-app free-tier cap,
  per-device manual registration, no CI/distributable-artifact
  involvement). Separately documented the paid Developer Program path as
  not-yet-wired-up notes for a future session: switching
  `CODE_SIGN_STYLE`, storing cert/profile/team ID as GitHub secrets, a CI
  job archiving + exporting a signed `.ipa` alongside the existing `apple`
  CI test job, publishing to GitHub Releases the same way BUILD-1's
  Android release workflow would. Docs only, no code changes.

## Native Client Recording & Rule Parity

Recent web client features introduced keyword / contains-match recording rules,
title-based series matching without requiring a series ID, multi-channel selection,
rich recording options (start/end padding, new-only filtering, retention limits,
server selection), standalone keyword rule creation, in-player recording menus,
and detailed rules management. Core serialization and rule matchers in `HDHROpenKit`
and Android `:core` have been updated, but the UI layers, ViewModels, and recording
flows in iOS, tvOS, and Android still need to be brought to full parity.

- [x] **REC-1 — Shared Native ViewModels & Networking API Parity (iOS/tvOS & Android core).**
  Brought `apple/HDHROpenKit` and `android/core` to parity with the web client's
  recording capabilities:
  - `RecordingRuleOptions` gained a `channel: String?` field on both platforms
    (`RecordingRule.swift`, `RecordingRule.kt`) — the wire payload type already
    supported it, only the options struct used to build that payload didn't.
  - `GuideViewModel.recordEpisode`/`recordSeries` (both platforms) now forward
    `title`, `titleMatchMode`, `keywordQuery`, and `channel` into
    `AddRecordingRulePayload` instead of silently dropping them; `channel` now
    lets `options.channel` override the airing's own channel (needed for "any
    channel" / custom multi-channel scope). `recordSeries` now defaults an
    absent *or empty* `seriesId` to `"auto"` (matching web's `seriesId ||
    'auto'`) — previously only `recordEpisode` defaulted `nil`, and neither
    handled empty string.
  - `RecordingsViewModel` gained `addRecordingRule(payload:)` (thin wrapper over
    the already-complete `APIClient.addRecordingRule`) and
    `createKeywordRule(title:options:)` on both platforms, so the
    recordings/rules view can create standalone rules directly without going
    through a guide entry. Keyword/contains-match rules are implicitly
    `server: builtin` client-side (server-side `dvr.py` also enforces this).
  - Read-side `RecordingRuleMatcher` (both platforms) already handled
    pipe-delimited multi-channel and keyword/contains matching correctly —
    confirmed during scouting, no changes needed.
  - Tests: `apple/HDHROpenKit/Tests/HDHROpenKitTests/ModelsSerializationTests.swift`
    and new `android/core/src/test/kotlin/org/hdhropen/kit/RecordingRulePayloadTest.kt`
    both cover exact title, contains title, keyword query, multi-channel scope
    (`"4.1|5.1"`), retention limit, and server target payload serialization.
    `swift test --package-path apple/HDHROpenKit` (34/34) and
    `./gradlew :core:test` both green.

- [x] **REC-2 — iOS: Recording Options Sheet, Keyword Rules, and Rules Management.**
  Brought the iOS client (`apple/HDHROpeniOS`) to recording feature parity,
  building on REC-1 and ported from REC-4's Android implementation (same
  Svelte source of truth) as idiomatic SwiftUI rather than a Kotlin transliteration:
  - New `iOSRecordingOptionsSheet.swift` (`Form`/`Section` sheet, matching the
    `iOSSettingsView.swift` idiom): title match mode, keyword query field with a
    "+ Use episode title as keyword" chip, channel scope (current/any/custom
    multi-select pipe-joined as `"4.1|5.1"`), start/end padding steppers
    (minutes converted to seconds), "New episodes only" toggle, retention
    (Unlimited vs Keep Last N, hidden when `isOfficialDvrTarget`), and a DVR
    server picker (Default/Built-in/HDHomeRun). Mirrors the same business rules
    as REC-4: `isKeywordActive = !keywordQuery.trimmed.isEmpty || titleMatchMode
    == "contains"` forces `server = "builtin"`; `isOfficialDvrTarget =
    !isKeywordActive && (server == "hdhomerun" || (server == "default" &&
    officialDvrActive))`, with `officialDvrActive` read from
    `RecordingsViewModel.dvrInfo?.isBuiltin == false`. Supports both "create new
    rule" and "cancel existing rule" modes via an `existingRule` parameter.
  - New `iOSRecordingRulesSheet.swift`: lists all scheduled rules with badges
    (keyword, contains-match, "New only", retention count, start/end padding,
    provider), swipe-to-delete via `RecordingsViewModel.deleteRule(ruleId:)`,
    and a toolbar "Add Keyword Rule" button opening the next item.
  - New `iOSKeywordRuleSheet.swift`: standalone standing-rule creation (title,
    title match mode, keyword query, channel mode, padding, recentOnly,
    retention) via `RecordingsViewModel.createKeywordRule`. No server field —
    keyword rules are always implicitly builtin-DVR, enforced server-side too.
  - `iOSProgramDetailSheet.swift`: "Record Series" is now always shown (no
    longer gated on `airing.seriesId` being non-empty) — relies on REC-1's
    empty/nil→`"auto"` defaulting for title-based series matching. Added a
    "Recording Options…" button opening `iOSRecordingOptionsSheet`, and loads
    `RecordingsViewModel.dvrInfo` on appear if not already loaded.
  - `iOSRecordingsView.swift`: added a toolbar button opening
    `iOSRecordingRulesSheet`.
  - Unlike Android's explicit `channels`/`dvrInfo` parameter-passing, the new
    iOS sheets read `GuideViewModel`/`RecordingsViewModel` via
    `@EnvironmentObject` — both are already injected once at `RootiOSView.swift`
    and propagate automatically through `.sheet()` presentation, so no
    constructor plumbing was needed for REC-2 beyond the two edits above.
  - The three new files aren't SwiftPM sources, so they also had to be added to
    `apple/HDHROpen.xcodeproj/project.pbxproj` (file references, build files,
    group membership, and the `HDHROpeniOS` target's Sources build phase) by
    hand — this project doesn't use Xcode 16's filesystem-synchronized groups.
  - **Verification**: unlike REC-4's Android ceiling, an iOS Simulator toolchain
    was available here. `xcodebuild -project apple/HDHROpen.xcodeproj -scheme
    HDHROpeniOS -destination 'platform=iOS Simulator,...,name=iPhone 16e' build`
    → **BUILD SUCCEEDED** (compiles and links the real app target, not just the
    SwiftPM library). `swift test --package-path apple/HDHROpenKit` — 34/34
    green, confirming REC-1's ViewModel layer is untouched and still correct.
    Matches this codebase's existing convention (no SwiftUI view-level tests
    anywhere) — not manually exercised in a running simulator/device.

- [x] **REC-3 — tvOS: Recording Options & Rich Rules Management for 10-Foot UI.**
  Brought the Apple TV client (`apple/HDHROpenTV`) to recording feature parity,
  building on REC-1 and ported from REC-2's iOS sheets (same business rules,
  adapted for D-pad focus navigation rather than iOS's `NavigationStack`/`Form`):
  - New `TVRecordingOptionsModal.swift`: a full-screen `.fullScreenCover` modal
    (no `Form`/`.toolbar` — tvOS has no navigation-bar concept identical to
    iOS's, so this uses the same explicit-header-button pattern as the existing
    `TVProgramDetailModal.swift`/`TVRecordingRulesView.swift`). DVR server,
    title match mode, and channel scope pickers are hand-rolled button groups
    (matching `TVSettingsView.swift`'s theme-mode selector) rather than
    `Picker(.segmented)`, which doesn't render usably on tvOS. Padding uses a
    hand-rolled +/- row: **`Stepper` is unavailable on tvOS entirely** (a real
    build error, not just a style mismatch — `'Stepper' is unavailable in
    tvOS`), so both this file and `TVKeywordRuleModal.swift` implement their
    own minute-stepper row instead. `Toggle` compiles fine on tvOS and is used
    as-is for "New episodes only". Same business rules as REC-2/REC-4:
    `isKeywordActive = !keywordQuery.trimmed.isEmpty || titleMatchMode ==
    "contains"` forces `server = "builtin"`; `isOfficialDvrTarget =
    !isKeywordActive && (server == "hdhomerun" || (server == "default" &&
    officialDvrActive))`, retention hidden when `isOfficialDvrTarget`. Supports
    both "create new rule" and "cancel existing rule" modes via `existingRule`.
  - New `TVKeywordRuleModal.swift`: standalone standing-rule creation, mirroring
    `iOSKeywordRuleSheet.swift`. **Keyword text entry is viable on tvOS** — the
    only precedent search found in this app is `TVServerConnectionFields.swift`,
    which already uses a plain `TextField` relying on tvOS's native on-screen
    remote keyboard with no special wrapper — so this uses the same plain
    `TextField`, not a documented gap.
  - `TVRecordingRulesView.swift`: rule cards now show the same badge set as
    iOS/Android (keyword query, contains-match, "New only", retention count,
    start/end padding, provider), and gained an "Add Keyword Rule" header
    button opening `TVKeywordRuleModal`.
  - `TVProgramDetailModal.swift`: "Record Series" is now always shown (no
    longer gated on `airing.seriesId` being non-empty) — relies on REC-1's
    empty/nil→`"auto"` defaulting. `TVGuideView.swift`'s `onRecordSeries`
    closure had its own separate `guard let seriesId = ... else { return }`
    that would have silently no-op'd the fallback even after the modal's own
    gate was removed — updated to pass `selection.airing.seriesId ?? ""`
    too. Added an "Options…" button opening `TVRecordingOptionsModal`, and
    loads `RecordingsViewModel.dvrInfo` on appear if not already loaded (same
    fix REC-2 made in `iOSProgramDetailSheet.swift`).
  - Like iOS, the new tvOS modals read `GuideViewModel`/`RecordingsViewModel`
    via `@EnvironmentObject` (injected once at `HDHROpenTVApp.swift` and
    already propagating through `.fullScreenCover`) rather than constructor
    parameters, even though the pre-existing `TVProgramDetailModal.swift`/
    `TVRecordingRulesView.swift` use closure-based callback props — the two
    patterns coexist in those two files without conflict.
  - The two new files aren't SwiftPM sources, so they also had to be added to
    `apple/HDHROpen.xcodeproj/project.pbxproj` (file references, build files,
    group membership, and the `HDHROpenTV` target's Sources build phase) by
    hand, same as REC-2.
  - **Verification**: unlike REC-4's Android ceiling, a tvOS Simulator
    toolchain was available here. `xcodebuild -project apple/HDHROpen.xcodeproj
    -scheme HDHROpenTV -destination 'platform=tvOS Simulator,...,name=Apple TV'
    build` → **BUILD SUCCEEDED** (compiles and links the real app target; this
    run is what caught the `Stepper`-unavailable-on-tvOS error above).
    `swift test --package-path apple/HDHROpenKit` — 34/34 green, confirming
    REC-1's ViewModel layer is untouched and still correct. Matches this
    codebase's existing convention (no SwiftUI view-level tests anywhere) —
    not manually exercised in a running simulator/device.

- [x] **REC-4 — Android: Recording Options Bottom Sheet & Standalone Keyword Rules Dialog.**
  Brought the Android Compose client (`android/app`) to recording feature parity,
  building on REC-1:
  - `ProgramDetailBottomSheet.kt`: "Record Series" is now always shown (no longer
    gated on `!seriesId.isNullOrEmpty()`) — relies on REC-1's empty/nil→`"auto"`
    defaulting for title-based series matching. Added a "Recording Options…"
    button opening a new `RecordingOptionsBottomSheet.kt`, which mirrors
    `HDHomeRunRecordingOptionsDialog.svelte`'s full field set (mode, title match
    mode, keyword query, channel scope, start/end padding, new-only, retention,
    DVR server) and its exact business rules: keyword/contains-match forces
    `server="builtin"`, and retention is hidden + nulled when the target is the
    official HDHomeRun DVR (`isOfficialDvrTarget`, computed the same way as web's
    `officialDvrActive = dvrInfo?.is_builtin === false`, threaded down from
    `GuideScreen.kt`'s newly-added `RecordingsViewModel.dvrInfo` load).
  - `RecordingRulesDialog.kt`: added a `RuleBadgesRow` composable rendering
    keyword query, contains-match, "New only", retention count, start/end
    padding (minutes), and provider badges on each rule card (capped at 4).
  - New `KeywordRuleDialog.kt`, opened from a new "Add Keyword Rule" toolbar
    action in `RecordingsScreen.kt`, mirroring `HDHomeRunKeywordRuleDialog.svelte`
    — creates standalone standing rules (title, keyword, channel filter,
    padding, retention) via REC-1's `RecordingsViewModel.createKeywordRule`.
    No server field: keyword rules are always implicitly builtin-DVR, enforced
    server-side too.
  - `GuideScreen.kt`/`RootMobileScreen.kt`: threaded `RecordingsViewModel`
    into `GuideScreen` (for `dvrInfo`) and `GuideViewModel` into
    `RecordingsScreen` (for the channel lineup used by both new sheets).
  - **Verification ceiling** (matches CC-2/CC-6/CC-7's documented limitation):
    no Android emulator is attached in this environment, and this codebase's
    existing convention is ViewModel-only unit tests, no Compose view-level
    tests. Verified via `./gradlew :app:compileDebugKotlin :core:test` —
    BUILD SUCCESSFUL, all core tests green. Not manually exercised in an
    emulator/device.

- [x] **REC-5 — Native In-Player Recording Controls Parity (iOS, tvOS, Android).**
  Provide rich recording controls directly from the video player overlay across all native apps,
  matching the web player's `HDHomeRunPlayerRecordMenu.svelte`:
  - Android (`PlayerScreen.kt`): currently has no in-player recording button or menu. Add a
    recording action button in the player overlay controls that opens a bottom sheet or menu
    with quick actions: "Record Episode", "Record Series", "Recording Options..." (opening
    `RecordingOptionsBottomSheet`), or stream promotion for live watch sessions.
  - iOS (`iOSPlayerView.swift`) & tvOS (`TVPlaybackControlsView.swift`): the player record
    button currently only executes single-click live watch session promotion. Expand it into
    a menu (or long-press / options popup on tvOS) offering "Record Episode", "Record Series",
    "Recording Options...", and "Cancel Recording" alongside watch session promotion.
  - Every platform mirrors the same state machine: a scheduled rule for the current
    channel/airing collapses the menu to just "Cancel Recording"; otherwise it offers
    "Save Current Recording" (this app's own promote-buffering-watch-session action, kept
    alongside the web's rule-creation actions since it has no web equivalent), "Record
    Episode", "Record Series" (gated on series id or title), and "Recording Options…"
    (opening the REC-2/REC-3/REC-4 options sheet/modal). Android: `PlayerScreen.kt`'s
    record button is now a `DropdownMenu`. iOS: `iOSPlayerView.swift`'s record button is
    now a native `Menu`, opening `iOSRecordingOptionsSheet` via `.sheet`. tvOS: adds
    `showRecordMenu` to the shared `PlayerViewModel` and a new focus-scoped
    `TVPlayerRecordMenuOverlay.swift` (matching the existing `TVPlayerSettingsOverlay`
    convention rather than a native `Menu`, which this app doesn't use for in-player
    popups), opening `TVRecordingOptionsModal` via `.fullScreenCover`; registered the new
    file in `project.pbxproj`'s HDHROpenTV target.
  - **Verification**: Android — `./gradlew :app:compileDebugKotlin :core:test` **BUILD
    SUCCESSFUL**; no emulator attached in this environment, so not manually exercised
    (matches REC-4's documented limitation). iOS — real Simulator
    `xcodebuild -scheme HDHROpeniOS -destination 'platform=iOS Simulator,name=iPhone 17'
    build` → **BUILD SUCCEEDED**. tvOS — real Simulator
    `xcodebuild -scheme HDHROpenTV -destination 'platform=tvOS Simulator,name=Apple TV'
    build` → **BUILD SUCCEEDED**. `swift test --package-path apple/HDHROpenKit` — 34/34
    green, confirming the new `PlayerViewModel.showRecordMenu` field introduced no
    regressions. No SwiftUI/Compose view-level tests exist in this codebase (existing
    convention) — UI is verified by these real builds, not automated view tests.

## Tuner & Network Intelligence

When the official HDHomeRun app (iOS, iPadOS, tvOS, Android) streams Live TV on a
network with an active HDHomeRun RECORD server / NAS, it buffers the live stream
through the RECORD engine (port 50000) rather than tuning the hardware directly.
This causes the physical tuner unit to report the NAS's IP as its `TargetIP`,
masking the actual client device (e.g. iPhone, Apple TV) using the tuner.

- [x] **TUNER-1 — Remote HDHomeRun RECORD engine SSH client monitoring & stream disambiguation.**
  Enable HDHR Open to inspect active downstream clients connected to the official
  `hdhomerun_record` service on a remote NAS/server via SSH and correlate them to physical tuners.
  - **SSH Configuration in Network Settings**: added optional SSH fields (`dvr_ssh_enabled`,
    `dvr_ssh_host`, `dvr_ssh_port`, `dvr_ssh_username`, `dvr_ssh_key`, `dvr_ssh_password`) to the
    `hdhomerun` network integration's defaults, masked at rest via `NETWORK_INTEGRATION_SECRET_KEYS`
    (`settings.py`), plus a `POST /hdhomerun/test-ssh-connection` endpoint and a gated "SSH
    monitoring (optional)" section in `HDHomeRunNetworkSection.svelte` with a Test Connection button,
    following the existing tuner/DVR test-connection and write-only-secret UI precedents exactly.
  - **Judgment call**: used `asyncssh` (new dependency, `>=2.21.1`) rather than shelling out to a
    system `ssh` binary, per the plan's own call, to match this codebase's async-first pattern
    (`httpx`, raw `asyncio` sockets elsewhere in `hdhomerun_client.py`).
  - **Remote Socket Inspection** (`hdhomerun_client.py`): `fetch_dvr_ssh_clients` opens a short-lived
    `asyncssh` connection and tries `ss -tnp '( sport = :PORT )'` → `lsof -n -P -i :PORT` →
    `netstat -tnp | grep :PORT` in order, falling through only on a non-zero exit status (a
    zero-exit command that finds no active connections is treated as a final, legitimate answer,
    not a reason to try the next tool). A single generic regex parser
    (`_parse_ssh_socket_clients`) extracts the peer IP from all three tools' differing output
    shapes by picking whichever of the two `IP:PORT` pairs on a line isn't the target port, rather
    than parsing each tool's columns separately. Results are cached 10s via the shared `TTLCache`
    (`storage/cache.py`), separate from the existing 300s DNS-resolution cache reused for
    reverse-hostname lookups.
  - **Tuner Stream Disambiguation** (`tuner.py`): `_enrich_tuner_status`'s `is_dvr_server` branch
    now attributes SSH-discovered client IP(s)/hostname(s) to the tuner's `client`/`warning` display
    when SSH is configured and returns results (`Client: iPhone, Apple TV via HDHomeRun RECORD
    engine (<ip>)`). Implemented only the single/aggregated-client-list disambiguation the plan
    scoped as achievable without hardware; did not implement the `recorded_files.json`
    scheduled-recording correlation or per-PID `lsof -F n` buffer-descriptor inspection the plan
    described as further refinement — those need a real multi-stream DVR to design against
    meaningfully and are natural follow-ups if this proves useful in practice.
  - **Graceful fallback, verified by test, not just by inspection**: falls back to the pre-existing
    plain `HDHomeRun RECORD (<NAS IP>)` display whenever SSH is unconfigured, the connection fails,
    or the client fetch returns nothing —
    `test_get_status_dvr_proxy_client_ssh_configured_but_no_clients_keeps_plain_fallback` asserts
    the original name/warning/empty-viewers persist even with SSH configured, so this is additive
    and doesn't regress the existing behavior.
  - **Tests**: 9 new cases in `test_hdhomerun_client.py` (ss/lsof/netstat formats, fallback
    ordering, connection-error swallowing, `test_dvr_ssh_connection` success/misconfigured/
    unreachable) and 2 in `test_api_tuner.py` (SSH clients present, SSH configured but none found),
    all mocking `asyncssh.connect`. Full backend suite: 539 passed. Frontend: new
    `HDHomeRunNetworkSection.test.ts` cases for the gated SSH fields, blank-secret-omission on
    save, and the Test Connection button; full frontend suite 278 passed, `svelte-check` clean.
  - **Verification ceiling**: no real SSH-accessible HDHomeRun RECORD server/NAS was available in
    this environment, so `ss`/`lsof`/`netstat` output parsing, fallback ordering, and the live
    `asyncssh` connection path are verified only against mocked SSH output/errors, not real
    hardware — same caveat CC-8/CC-9 flagged for real-tuner testing.

## Cast & AirPlay Support

Wireless playback handoff from the player across web, Apple (iOS/tvOS), and Android devices.
Because external devices (Apple TV via AirPlay 2, Chromecast / Google Cast receivers) cannot
directly consume raw `mpegts.js` Media Source Extension (MSE) buffer pipes, Google Cast and
Android re-route to real per-session HLS (there is no static manifest URL — HLS is inherently
session-based: `POST /api/streaming/hls/{channel_number}` or `POST /api/dvr/recording-stream-hls`
spins up ffmpeg and returns a dynamic `playlist_url` to `GET`). Apple's native AirPlay doesn't need
this at all — it relays the sender's own already-authenticated `AVPlayer`, not an independent
device fetch.

- [x] **CAST-1 — Web: AirPlay (Safari) & Google Cast Web Sender SDK Player Integration.**
  Done. AirPlay: `x-webkit-airplay="allow"` on the `<video>` element in `HDHomeRunPlayer.svelte`, a
  feature-detected `webkitplaybacktargetavailabilitychanged` listener toggling the button, and
  `webkitShowPlaybackTargetPicker()` on click — no source swap needed, since AirPlay mirrors
  whatever the `<video>` element is currently rendering (mpegts.js keeps decoding locally via MSE
  and its output is relayed as-is); that's unlike Cast, where the *receiver device* itself has to
  fetch the stream. Google Cast: new `frontend/src/lib/cast/cast-loader.ts` (lazy Cast Sender SDK
  load, `CastContext`/`RemotePlayer` wrappers) and `frontend/src/lib/components/player/CastButton.svelte`,
  wired into the player's header controls. New `api.createChannelHlsSessionForCast`/
  `createRecordingHlsSessionForCast`/`stopHlsSession` in `api.ts` call the backend's HLS session
  endpoints with `for_cast: true` and resolve the returned (API-relative) `playlist_url` to an
  absolute URL — the Cast receiver fetches it directly over the LAN, not through the page, so it
  can't be page-relative. **Tests**: `HDHomeRunPlayer.test.ts` — AirPlay button visibility/picker
  invocation, Cast button visibility and loading a `for_cast` session onto a faked receiver
  session; 284/284 passing, `svelte-check` clean. **Verification ceiling**: real Safari AirPlay
  picker/route relay and real Chromecast receiver playback of the `for_cast` HLS stream (segment
  fetch through the new cast-token auth path, `DEFAULT_MEDIA_RECEIVER_APP_ID`'s default receiver
  handling this content) were not verified against real hardware in this environment.
  Add wireless casting and AirPlay handoff to the web player (`HDHomeRunPlayer.svelte`):
  - **AirPlay (WebKit / Safari)**:
    - Add `x-webkit-airplay="allow"` and `webkit-playsinline` to the `<video>` element.
    - Track `window.WebKitPlaybackTargetAvailabilityEvent` (`webkitplaybacktargetavailabilitychanged`)
      to conditionally show the AirPlay button in the player control bar.
    - Wire button click to `videoElement.webkitShowPlaybackTargetPicker()`.
    - Handle `webkitcurrentplaybacktargetiswireless`: dynamically switch the video element source
      from the `mpegts.js` MSE stream to the direct HLS stream URL (`/api/streaming/hls/...`
      or `/api/dvr/recordings/.../master.m3u8`) with the current viewer's session/token query
      parameters so the AirPlay receiver can decode and play the native stream seamlessly.
  - **Google Cast Web Sender SDK**:
    - Load Cast Framework script (`https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1`)
      lazily in `frontend/src/lib/cast/cast-loader.ts`.
    - Initialize `cast.framework.CastContext.getInstance().setOptions({ receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID, autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED })`.
    - Add a Cast launcher button (using `<google-cast-launcher>` or custom Svelte reactive state
      via `cast.framework.CastContextEventType.CAST_STATE_CHANGED`).
    - On session start, create `chrome.cast.media.MediaInfo` pointing to the full absolute HLS
      manifest URL (MIME `application/x-mpegurl`), populating metadata (show title, channel name/number,
      poster art, and live/vod stream type).
    - Synchronize remote player state (play, pause, seek, volume, progress) with `cast.framework.RemotePlayerController`.
  - **Files**:
    - `frontend/src/lib/cast/cast-loader.ts` (NEW: Cast SDK loader and session management)
    - `frontend/src/lib/components/player/CastButton.svelte` (NEW: Cast / AirPlay button UI)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: video attributes, HLS stream swap, controls)
    - `frontend/src/lib/api.ts` (MODIFY: full absolute HLS URL builder helper for external receivers)

- [x] **CAST-2 — iOS/tvOS: Native AirPlay Route Picker & AVPlayer AudioSession Configuration.**
  Done. `PlayerEngine.swift`: `allowsExternalPlayback`/`usesExternalPlaybackWhileExternalScreenIsActive`
  set explicitly in `init()`; `AVAudioSession` configured (`.playback`/`.moviePlayback`, previously
  entirely absent from the codebase) — `.longFormVideo` policy on iOS only, since that enum case
  doesn't exist on tvOS; new `@Published var isExternalPlaybackActive` driven by a Combine
  `.publisher(for: \.isExternalPlaybackActive)` observer. New shared
  `apple/HDHROpenKit/Sources/HDHROpenKit/Playback/AirPlayRoutePickerView.swift`
  (`UIViewRepresentable` wrapping `AVRoutePickerView`, following `PlayerLayerView.swift`'s bridge
  pattern) — lives in the Kit package, not iOS-only, since tvOS needs it too. iOS: route picker in
  the player's top nav bar icon group. tvOS: placed inside `TVPlayerSettingsOverlay` (a new
  `.airplay` case) rather than the always-visible control bar, since `AVRoutePickerView` is itself
  focusable and this codebase deliberately keeps AVKit's own chrome from competing with the
  hand-rolled Siri Remote focus handling (see `PlayerLayerView.swift`'s doc comment). Also fixed a
  real bug found during planning: both `HDHROpeniOSApp.swift` and `HDHROpenTVApp.swift` called
  `closePlayer()` unconditionally on `scenePhase == .background`, which would kill an active
  AirPlay session the instant the app backgrounds — both now skip that teardown specifically when
  `isExternalPlaybackActive` is true. **Tests**: new `PlayerEngineExternalPlaybackTests.swift`
  (external-playback flags post-`init()`); `swift test --package-path apple/HDHROpenKit` 36/36,
  `xcodebuild` clean on both iOS and tvOS simulator targets. **Verification ceiling**: real AirPlay
  route negotiation, `isExternalPlaybackActive` toggling from actual hardware, and audio surviving
  backgrounding with the new `AVAudioSession` config were not verified against a real AirPlay
  receiver.

- [x] **CAST-3 — Android: Google Cast Framework & Media3 CastPlayer Integration.**
  Done. Added `media3-cast`, `play-services-cast-framework`, and `androidx.mediarouter` (needed for
  `MediaRouteButton`/`CastButtonFactory`, not in the original scope) to
  `android/{app,core}/build.gradle.kts`; new `CastOptionsProvider.kt` + manifest
  `OPTIONS_PROVIDER_CLASS_NAME` meta-data. `PlayerEngine.kt`: a `Player`-typed `CastPlayer` field
  (not the concrete `CastPlayer` class — its static initializer touches an unmocked Android stub,
  which broke this module's plain-JUnit/mockk unit tests; every call site only needs the common
  `Player` interface anyway), `isCasting: StateFlow<Boolean>` via `SessionManagerListener`, a
  computed `activePlayer` all playback calls route through, real `MediaMetadata` on every
  `MediaItem`, and a Cast-specific `loadMedia` path that hands the receiver the server's
  `for_cast=true` `playlist_url` directly (via the new `StreamURLBuilder.resolve()`, never
  reconstructing the cast-token path from `sessionId` alone). `forCast` threaded through
  `APIClient`/`APIEndpoints` and all three `PlayerViewModel.kt` HLS-session call sites.
  `PlayerScreen.kt`: `MediaRouteButton` + "Casting to TV" status text. **Tests**: new
  `PlayerEngineCastTest.kt`/`PlayerViewModelCastTest.kt` (activePlayer routing, `forCast=true`
  threading, `MediaMetadata` population), mocking `CastContext`/`CastSession` rather than
  instantiating real GMS Cast objects; `:core:test` (debug+release) and `:app:test` green, 46/46 in
  `:core:testDebugUnitTest`, no regressions. **Verification ceiling**: real Chromecast route
  discovery/negotiation, `SessionManagerListener` callbacks from a live session, and
  `CastOptionsProvider` resolution were not verified against real hardware.

## Synchronized Playback & SyncPlay (Watch Parties)

Investigation and implementation of synchronized co-watching solutions across platforms,
enabling shared streaming, room management, and monotonic clock synchronization.

- [ ] **SYNC-1 — Backend: SyncPlay WebSocket Room Coordinator, Monotonic Clock Sync, & State Broadcasting.**
  Build a high-performance, lightweight SyncPlay hub in FastAPI:
  - **Room Lifecycle Management** (`backend/app/api/syncplay.py`, `backend/app/syncplay/room_manager.py`):
    - `POST /api/syncplay/rooms`: Create a watch room with a shareable 6-character code and optional password.
    - `GET /api/syncplay/rooms`: List active public/household rooms.
    - `GET /api/syncplay/rooms/{room_id}`: Room details, current stream media reference (channel number, recording ID, or play URL), and participant list.
  - **WebSocket Real-Time Synchronization Engine** (`WS /api/syncplay/ws/{room_id}`):
    - Centralized room state broadcasting player actions (`play`, `pause`, `seek`, `change_media`, `buffering_state`) with server-side monotonic timestamps (`monotonic_ns`).
    - Periodic ping/pong heartbeat to measure Round-Trip Time (RTT) and calculate individual client clock offsets.
    - Smooth drift correction protocol: Clients adjust playback rate (`playbackRate = 1.02` or `0.98`) for minor clock drifts (<1s) or perform hard seeks for large discrepancies (>2s).
  - **Files**:
    - `backend/app/syncplay/__init__.py` (NEW)
    - `backend/app/syncplay/room_manager.py` (NEW: in-memory / redis room coordinator)
    - `backend/app/api/syncplay.py` (NEW: FastAPI WebSocket and REST router)
    - `backend/app/main.py` (MODIFY: mount syncplay router)
    - `backend/tests/test_syncplay.py` (NEW: unit & WebSocket integration tests)

- [ ] **SYNC-2 — Web: Jellyfin SyncPlay Client Integration, Top-Bar Button, & Watch Party Room Modal.**
  Implement the full SyncPlay client experience in the web player matching the Jellyfin design:
  - **Top-Bar SyncPlay Button & Status Indicator**:
    - Add SyncPlay button (group / two-person icon matching Jellyfin screenshot) in `PlayerHeader.svelte`.
    - Badge showing current room participant count and synchronization health (green/yellow/red dot).
  - **Watch Party Modal / Drawer (`SyncPlayModal.svelte`)**:
    - Create Room or Join by code / invite link.
    - Active participant list with usernames, playback status (playing/paused), buffer readiness, and ping.
    - "Ready to watch" toggle and host control options (lock controls to host only).
  - **Client Synchronization Logic (`syncplay-client.ts`)**:
    - WebSocket connection management, automatic reconnection with backoff.
    - Monotonic clock calibration using NTP-style ping/pong filter.
    - Dynamic video element speed adjustment (`playbackRate` micro-nudges) and hard seek snapping.
    - Non-intrusive in-player toast alerts ("Alice paused playback", "Bob seeked to 18:45").
  - **Files**:
    - `frontend/src/lib/syncplay-client.ts` (NEW)
    - `frontend/src/lib/components/player/SyncPlayButton.svelte` (NEW)
    - `frontend/src/lib/components/player/SyncPlayModal.svelte` (NEW)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: integrate syncplay client)
    - `frontend/src/lib/components/HDHomeRunPlayer.test.ts` (MODIFY: test syncplay integration)

- [ ] **SYNC-3 — Native Clients: Cross-Platform SyncPlay Parity for iOS/tvOS & Android.**
  Enable cross-platform SyncPlay on Apple and Android apps so all devices can join the same co-watching rooms:
  - **Apple (`HDHROpenKit`)**:
    - Add `SyncPlayCoordinator.swift` managing the WebSocket connection and state synchronization with `PlayerEngine.swift`.
    - `iOSSyncPlayModal.swift` and `TVSyncPlayModal.swift` for room creation, joining, and participant roster.
  - **Android (`:core` & `app`)**:
    - Add `SyncPlayCoordinator.kt` in `:core` and `SyncPlayDialog.kt` in Jetpack Compose.
    - Bind room events to `PlayerEngine.kt`'s ExoPlayer instance (`setPlaybackSpeed`, `seekTo`).
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/SyncPlay/SyncPlayCoordinator.swift` (NEW)
    - `apple/HDHROpeniOS/Views/Player/iOSSyncPlayModal.swift` (NEW)
    - `apple/HDHROpenTV/Views/Player/TVSyncPlayModal.swift` (NEW)
    - `android/core/src/main/kotlin/org/hdhropen/kit/syncplay/SyncPlayCoordinator.kt` (NEW)
    - `android/app/src/main/kotlin/org/hdhropen/app/ui/screens/player/SyncPlayDialog.kt` (NEW)

- [ ] **SHARE-1 — Apple Platforms: Native SharePlay via GroupActivities & AVPlayerPlaybackCoordinator.**
  Implement native Apple SharePlay for iOS, iPadOS, and tvOS clients:
  - **Feasibility & Platform Support**:
    - SharePlay is an Apple-proprietary framework built on `GroupActivities` and `AVFoundation`,
      integrated directly into FaceTime and iMessage on iOS 15.1+, tvOS 15.1+, and macOS 12.1+.
    - **Native Apple Apps**: Fully supported out of the box via `AVPlayerPlaybackCoordinator`.
  - **Implementation**:
    - Define `WatchProgramActivity` struct conforming to `GroupActivity`:
      ```swift
      struct WatchProgramActivity: GroupActivity {
          static let activityIdentifier = "org.hdhropen.watch-program"
          let channelNumber: String?
          let recordingId: String?
          let title: String
          var metadata: GroupActivityMetadata { ... }
      }
      ```
    - Add `com.apple.developer.group-session` entitlement in `apple/HDHROpeniOS` and `apple/HDHROpenTV`.
    - In `PlayerEngine.swift`, listen for incoming `GroupSession<WatchProgramActivity>` sessions.
    - Attach `avPlayer.playbackCoordinator.coordinateWithSession(groupSession)` — `AVPlayer`
      automatically synchronizes time, playback rate, seek events, and buffer state across peers.
    - Add SharePlay trigger button in `iOSPlayerView.swift` and `TVPlayerView.swift` using
      `GroupActivitySharingController` / SwiftUI `.sheet`.
  - **Network & Access Considerations**:
    - All FaceTime participants must be able to reach the stream URL (e.g. within the same LAN,
      via Tailscale/VPN, or through a configured public HTTPS reverse proxy).
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Playback/SharePlayActivity.swift` (NEW: GroupActivity definitions)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Playback/PlayerEngine.swift` (MODIFY: playbackCoordinator session hookup)
    - `apple/HDHROpeniOS/Views/Player/iOSPlayerView.swift` (MODIFY: SharePlay UI triggers)
    - `apple/HDHROpenTV/Views/Player/TVPlayerView.swift` (MODIFY: tvOS SharePlay coordination)

## Jellyfin Video Player UI/UX Parity & Controls

Redesign the HDHR Open video player to achieve full visual and functional parity with the modern
Jellyfin media player (as shown in reference screenshot), modularize player components, and provide
fluid auto-hiding controls, responsive scrub bar, rich settings, and fullscreen controls.

- [x] **PLAYER-1 — Web: Jellyfin-Style Modern Player Header, Footer Controls, & Auto-Hiding Overlay.**
  Transform `HDHomeRunPlayer.svelte` into a polished, responsive player interface matching Jellyfin:
  - **Auto-Hiding Controls Overlay**:
    - Smoothly fades out header and footer controls after 3.5 seconds of mouse/touch inactivity during playback.
    - Instantly reappears on mouse movement, touch, or keyboard navigation.
    - Remains visible when playback is paused or when any popover/modal menu is open.
  - **Top Header Bar (`PlayerHeader.svelte`)**:
    - Left: Back / Exit button (`←`), title display (Show Title, Season/Episode if present, or Channel Name/Number).
    - Right: SyncPlay Watch Party launcher (`👥`), Google Cast launcher (`📺`), AirPlay launcher (`⛶`), and Record action menu.
    - Semi-transparent gradient backdrop (`rgba(0, 0, 0, 0.75)` with `backdrop-filter: blur(8px)`).
  - **Bottom Footer Controls Bar (`PlayerFooter.svelte`)**:
    - **Tier 1 (Timeline / Scrub Bar)**:
      - Left timestamp: Current playback position (`0:06` / `1:23:45`).
      - Center track: Interactive scrub bar with buffered ranges track, blue progress fill, circular scrubber thumb knob, and hover thumbnail preview.
      - Right timestamp: Remaining time (`-4:14:53`), clickable to toggle between negative remaining time and total duration.
    - **Tier 2 (Action Buttons)**:
      - Left controls: Skip back 10s (`⏮`), Play/Pause toggle (`▶`/`⏸`), Skip forward 10s (`⏭`), and dynamic **"Ends at hh:mm AM/PM"** estimated completion time based on current wall-clock time plus remaining duration (or "LIVE" indicator for non-seekable live channels).
      - Right controls: Favorite heart toggle (`♡`/`♥`), Picture-in-Picture (`⧉`), Audio stream selector (`♪`), Volume speaker icon with expandable horizontal volume slider, Bookmark ribbon (`🔖`), Settings gear (`⚙`), Closed Caption toggle (`CC`), and Fullscreen toggle (`⛶`).
  - **Gesture & Keyboard Controls**:
    - Single-click video canvas toggles Play/Pause with center ripple indicator; double-click toggles Fullscreen.
    - Keybindings: Space (`Play/Pause`), `f` (`Fullscreen`), `m` (`Mute`), `p` (`PiP`), `c` (`Captions`), `j`/`Left` (`Rewind 10s`), `l`/`Right` (`Fast Forward 10s`), `Up`/`Down` (`Volume ±5%`), `Esc` (`Close Menu / Exit`).
  - **Files**:
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: refactor layout and state management)
    - `frontend/src/lib/components/player/PlayerHeader.svelte` (NEW: top header component)
    - `frontend/src/lib/components/player/PlayerFooter.svelte` (NEW: bottom footer controls component)
    - `frontend/src/lib/components/player/PlayerScrubBar.svelte` (NEW: modular scrub bar component)
    - `frontend/src/lib/i18n/locales/en.json` (MODIFY: player localization strings)
    - `frontend/src/lib/components/HDHomeRunPlayer.test.ts` (MODIFY: comprehensive component unit tests)

- [x] **PLAYER-2 — Web: Jellyfin Iconography, Volume Slider, Playback Speed, Aspect Ratio, & Settings Menu.**
  Replace legacy text/emoji icons with clean SVG icons and integrate rich playback settings:
  - **Material / Jellyfin SVG Icon Set**:
    - Create dedicated SVG icon components for Play, Pause, Skip Back, Skip Forward, Volume High/Med/Low/Mute, Favorite, PiP, Audio Note, Bookmark, Settings Gear, CC, and Fullscreen.
  - **Interactive Volume Control (`PlayerVolumeControl.svelte`)**:
    - Speaker icon toggles mute state; hovering or interacting reveals a horizontal slider with blue accent fill and thumb knob.
    - Persists volume and muted state in `localStorage`.
  - **Playback Settings Menu (`PlayerSettingsMenu.svelte`)**:
    - Playback Speed selector: `0.5x`, `0.75x`, `1.0x`, `1.25x`, `1.5x`, `2.0x`.
    - Aspect Ratio selector: `Auto (Default)`, `Cover (Fill Screen)`, `Contain`, `16:9`, `4:3`.
    - Audio stream selector & Closed caption track selector.
    - Playback Info / Stats for Nerds modal (video codec, resolution, fps, audio layout, transcode hardware).
  - **Files**:
    - `frontend/src/lib/components/player/PlayerSettingsMenu.svelte` (NEW)
    - `frontend/src/lib/components/player/PlayerVolumeControl.svelte` (NEW)
    - `frontend/src/lib/components/player/icons/*.svelte` (NEW: SVG icon set)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY)

- [x] **PLAYER-3 — Web & Native: Fullscreen Mode & Immersive Experience.**
  Implement seamless fullscreen support across web browsers and native apps:
  - **Web Fullscreen API**:
    - Wire fullscreen button and `f` shortcut to `container.requestFullscreen()` and `document.exitFullscreen()`.
    - Safari / WebKit prefix support (`webkitRequestFullscreen`, `webkitEnterFullscreen` on iOS video element).
    - Listen for `fullscreenchange` / `webkitfullscreenchange` to update the icon state (`fullscreen` vs `fullscreen_exit`).
    - Adapt CSS layout for true full-bleed borderless playback with safe-area insets.
  - **Android & Apple Immersive Fullscreen**:
    - Android (`PlayerScreen.kt`): Enforce `WindowInsetsControllerCompat.hide(WindowInsetsCompat.Type.systemBars())` with `BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE`.
    - iOS/tvOS (`iOSPlayerView.swift`): Auto-hide status bars and home indicator (`.persistentSystemOverlays(.hidden)`).
  - **Files**:
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY)
    - `frontend/src/lib/fullscreen-controller.ts` (NEW: cross-browser fullscreen helper)
    - `android/app/src/main/kotlin/org/hdhropen/app/ui/screens/player/PlayerScreen.kt` (MODIFY)
    - `apple/HDHROpeniOS/Views/Player/iOSPlayerView.swift` (MODIFY)

## AI Intelligence & Natural Language Assistant

Integrate generative AI capabilities into HDHR Open to provide intelligent TV guide querying,
conversational recommendations, smart scheduling, and automated DVR management with support for
all major AI providers.

- [ ] **AI-1 — Backend: Multi-Provider LLM Integration Layer & Encrypted Settings.**
  Build a unified async LLM client abstraction supporting all major AI providers:
  - **Supported Providers**:
    - **OpenAI**: GPT-4o, GPT-4o-mini (`https://api.openai.com/v1`)
    - **Anthropic Claude**: Claude 3.5 Sonnet, Claude 3.5 Haiku (`https://api.anthropic.com/v1`)
    - **Google Gemini**: Gemini 1.5 Flash, Gemini 1.5 Pro, Gemini 2.0 Flash (`https://generativelanguage.googleapis.com/v1beta`)
    - **Ollama / Local LLMs / Custom OpenAI-Compatible**: Configurable `base_url` and `model`
      (supports self-hosted Ollama, vLLM, LM Studio, OpenRouter, DeepSeek).
  - **Lightweight Implementation**:
    - Implemented with pure `httpx` async calls matching existing codebase patterns (no heavy
      proprietary SDK bloat).
    - Normalized function/tool calling schema across OpenAI function format, Anthropic tool use,
      and Gemini function declarations.
  - **Settings & Security**:
    - Add `ai` to `KNOWN_INTEGRATION_TYPES` in `backend/app/api/network_settings.py`.
    - Store `api_key` encrypted at rest via `app.crypto` (write-only / masked).
    - Fields: `provider`, `api_key`, `base_url`, `model`, `system_prompt_custom`, `temperature`,
      `enable_recording_tools` (permission gate for mutating DVR actions).
    - Add `POST /api/ai/test-connection` endpoint to validate provider credentials and model availability.
  - **Files**:
    - `backend/app/integrations/ai/__init__.py` (NEW: provider factory and base class)
    - `backend/app/integrations/ai/openai_client.py` (NEW: OpenAI & OpenAI-compatible client)
    - `backend/app/integrations/ai/anthropic_client.py` (NEW: Anthropic Claude client)
    - `backend/app/integrations/ai/gemini_client.py` (NEW: Google Gemini client)
    - `backend/app/api/network_settings.py` (MODIFY: add `ai` integration type & defaults)
    - `backend/app/storage/db/settings.py` (MODIFY: add `api_key` to secret keys)

- [ ] **AI-2 — Backend: Guide & Recording Tool Calling Registry.**
  Define and implement structured tools for the LLM to interact with the guide and DVR subsystems:
  - **Guide Intelligence Tools** (`backend/app/ai/tools/guide.py`):
    - `search_guide(query: str, category: str | None, is_new: bool | None, start_after: int | None, end_before: int | None, limit: int = 10)`:
      Queries cached `guide_programs` for matching titles, synopses, and genre categories.
    - `get_now_playing(favorites_only: bool = False)`:
      Returns currently airing shows across all channels or favorites with start/end progress.
    - `get_program_details(series_id: str | None, title: str | None)`:
      Retrieves rich synopsis, episode numbers, original airdate, and upcoming broadcast schedule.
    - `get_channel_lineup()`:
      Returns configured channel numbers, station names, and tuner availability.
  - **DVR Recording Tools** (`backend/app/ai/tools/recording.py`):
    - `schedule_recording(title: str, series_id: str = "auto", channel: str | None = None, start_padding_minutes: int = 0, end_padding_minutes: int = 0, recent_only: bool = False, max_episodes: int | None = None, server: str = "builtin", title_match_mode: str = "exact", keyword_query: str | None = None)`:
      Creates one-off, series, or keyword recording rules with natural language parameters.
    - `list_recording_rules()`:
      Queries all active recording rules and their configuration.
    - `cancel_recording_rule(rule_id: str)`:
      Deletes an active recording rule.
    - `list_recordings(filter: str | None = None, limit: int = 20)`:
      Lists completed and in-progress DVR recordings from disk/DB.
    - `delete_recording(recording_id: str)`:
      Removes a recorded file and updates DB state.
    - `check_recording_conflicts(start_ts: int, end_ts: int)`:
      Checks overlapping scheduled recordings against tuner count to warn about potential tuner contention.
  - **Tool Registry & Execution Engine** (`backend/app/ai/tools/registry.py`):
    - Central registry converting tool signatures to JSON schemas and dispatching tool calls safely
      with permission checks (`enable_recording_tools`).
  - **Files**:
    - `backend/app/ai/tools/registry.py` (NEW)
    - `backend/app/ai/tools/guide.py` (NEW)
    - `backend/app/ai/tools/recording.py` (NEW)

- [ ] **AI-3 — Backend: Conversational Assistant Orchestration & Streaming API.**
  Create the conversational API endpoint with tool calling loops:
  - **Endpoint**: `POST /api/ai/chat` (accepts conversation history, user query, and optional context
    such as current time, timezone, and selected channel).
  - **Tool Loop Orchestration**:
    - Iterates model responses, detects tool call requests, executes authorized tools against
      the local database/DVR engine, feeds tool results back to the LLM, and produces the final answer.
    - Supports Server-Sent Events (SSE) streaming (`text/event-stream`) to stream response tokens,
      tool execution statuses ("Searching TV guide…", "Checking recording schedule…"), and structured
      action preview cards.
  - **Files**:
    - `backend/app/api/ai.py` (NEW: FastAPI router for AI chat & tool execution)
    - `backend/app/main.py` (MODIFY: mount AI router)

- [ ] **AI-4 — Frontend: AI Assistant Drawer, Natural Language Search, & Admin Settings UI.**
  Build user-facing AI interfaces in SvelteKit:
  - **Admin Settings (`AISettingsSection.svelte`)**:
    - Added to `frontend/src/routes/settings/+page.svelte` under Integrations.
    - Fields: Provider selector (OpenAI, Anthropic, Gemini, Ollama/Custom), API Key input (with
      write-only masked toggle), Base URL (for Ollama/local), Model selector / custom model input,
      Temperature slider, Recording Tools permission toggle.
    - "Test Connection" button with live status feedback.
  - **AI Assistant Drawer / Modal (`AIAssistantDrawer.svelte`)**:
    - Global accessible assistant launcher in the navigation bar and Guide page ("Ask AI" / ✨ icon).
    - Conversational chat interface with markdown formatting, code/time chips, and show cards.
    - **Interactive Action Confirmation Cards**: When the AI proposes scheduling or canceling a
      recording rule, render an interactive preview card with show details, airtime, and "[Confirm Recording]" /
      "[Cancel]" buttons so mutating actions are always user-approved.
  - **Files**:
    - `frontend/src/lib/components/settings/AISettingsSection.svelte` (NEW)
    - `frontend/src/lib/components/ai/AIAssistantDrawer.svelte` (NEW)
    - `frontend/src/lib/components/ai/AIAssistantMessage.svelte` (NEW)
    - `frontend/src/routes/settings/+page.svelte` (MODIFY: add AI settings section)
    - `frontend/src/routes/+layout.svelte` (MODIFY: assistant trigger button and drawer host)
    - `frontend/src/lib/api.ts` (MODIFY: AI client endpoints and types)

- [ ] **AI-5 — Native Clients: AI Assistant Feature Parity (iOS/tvOS & Android).**
  Expose AI assistant capabilities in native client apps:
  - **Shared Core (`HDHROpenKit` & `:core`)**:
    - Add AI models and networking methods (`APIClient.sendAIChat`, `APIClient.testAIConnection`).
  - **iOS (`HDHROpeniOS`)**:
    - SwiftUI `iOSAIAssistantSheet.swift` with conversational interface, quick suggestion chips
      ("What's on tonight?", "Upcoming live sports"), and recording confirmation dialogs.
  - **tvOS (`HDHROpenTV`)**:
    - 10-foot Siri Remote optimized voice/text AI guide search modal.
  - **Android (`android/app`)**:
    - Jetpack Compose `AIAssistantBottomSheet.kt` with chat feed and action cards.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Networking/APIClient+AI.swift` (NEW)
    - `apple/HDHROpeniOS/Views/AI/iOSAIAssistantSheet.swift` (NEW)
    - `apple/HDHROpenTV/Views/AI/TVAIAssistantModal.swift` (NEW)
    - `android/core/src/main/kotlin/org/hdhropen/kit/networking/APIClient+AI.kt` (NEW)
    - `android/app/src/main/kotlin/org/hdhropen/app/ui/screens/ai/AIAssistantBottomSheet.kt` (NEW)

## Picture-in-Picture (PiP) & Popout Player

Multitasking and detached viewing options across web browsers and native mobile/desktop platforms.

- [x] **PIP-1 — Web: HTML5 Video Picture-in-Picture & Document Picture-in-Picture API.**
  Integrate native browser Picture-in-Picture (PiP) and the modern Document PiP API into the web player:
  - **Standard HTML5 Video PiP**:
    - Feature detection via `document.pictureInPictureEnabled && !videoElement.disablePictureInPicture`.
    - Add a dedicated PiP button in `PlayerFooter.svelte` / `HDHomeRunPlayer.svelte` and map shortcut key `p`.
    - Wire button to `videoElement.requestPictureInPicture()` and `document.exitPictureInPicture()`.
    - Track PiP state via `enterpictureinpicture` / `leavepictureinpicture` events.
    - **Captions in PiP**: When entering video PiP, switch `capTextTrack.mode` in `caption-controller.ts`
      from `'hidden'` to `'showing'` so WebVTT cues render in the floating OS PiP window; restore to
      `'hidden'` when returning to in-page overlay rendering on PiP exit.
    - **Media Session API**: Configure `navigator.mediaSession.metadata` (title, channel name, episode subtitle,
      artwork) and bind action handlers (`play`, `pause`, `seekbackward`, `seekforward`) so floating PiP controls
      and keyboard media keys operate playback.
  - **Document Picture-in-Picture (Chromium 111+)**:
    - Detect `window.documentPictureInPicture?.requestWindow`.
    - Support opening a floating DOM window holding the video player container, preserving custom styled caption
      overlays, scrub bar, and channel badges.
    - Copy styles / link stylesheets into the PiP document; smoothly restore the player DOM to the main page
      on `pagehide` without interrupting the active `mpegts.js` / HLS stream buffer.
  - **Files**:
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: PiP button, keybinding, PiP event handlers)
    - `frontend/src/lib/components/player/PlayerFooter.svelte` (MODIFY: PiP control button)
    - `frontend/src/lib/caption-controller.ts` (MODIFY: PiP text track display mode hook)
    - `frontend/src/lib/i18n/locales/en.json` (MODIFY: translation strings for PiP)
    - `frontend/src/lib/components/HDHomeRunPlayer.test.ts` (MODIFY: unit tests for PiP toggle & events)

- [ ] **PIP-2 — Web: Standalone Popout Player Route & Window Handoff.**
  Add a dedicated frameless popout player window and route for detached desktop viewing:
  - **Dedicated Popout Route (`/player`)**:
    - Create `frontend/src/routes/player/+page.svelte` that renders `HDHomeRunPlayer.svelte` full-bleed (100vw/100vh).
    - `+layout.svelte`: suppress the top navigation bar (`.app-nav`) when navigating to `/player`.
    - Accepts URL params: `?channel={number}` or `?recording={id}` or `?play_url={url}`.
    - Manages its own watch-session lifecycle (auto-start capture, `api.heartbeatWatch` interval, `api.stopWatch` on `pagehide`)
      so closing the popup window immediately releases tuners and terminates backend ffmpeg processes.
  - **Popout Launcher & Handoff**:
    - Add a "Popout" button (↗) to `PlayerHeader.svelte` and Guide/Recording action menus.
    - Triggers `window.open('/player?...', 'hdhr_popout_player', 'width=960,height=540,menubar=no,toolbar=no,location=no,status=no,resizable=yes')`.
    - Automatically closes or pauses the in-page player when transferring an active watch session to prevent duplicate tuner consumption.
  - **Files**:
    - `frontend/src/routes/player/+page.svelte` (NEW: standalone player route)
    - `frontend/src/routes/+layout.svelte` (MODIFY: hide navigation on `/player`)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: popout button & handoff logic)
    - `frontend/src/lib/i18n/locales/en.json` (MODIFY: translation strings for popout)

- [ ] **PIP-3 — Android: Native Picture-in-Picture (PiP) with Auto-Enter & Playback Remote Actions.**
  Bring native system PiP support to Android (`android/app`):
  - **Manifest & Activity Lifecycle**:
    - Add `android:supportsPictureInPicture="true"` and `android:configChanges="screenSize|smallestScreenSize|screenLayout|orientation"` to `MainActivity` in `AndroidManifest.xml`.
    - Implement `enterPictureInPictureMode(params)` in `MainActivity.kt` and `PlayerScreen.kt`.
    - Android 12+ (API 31+): Configure `setSourceRectHint` and `setAutoEnterEnabled(true)` on `PictureInPictureParams.Builder` so swiping home smoothly transitions directly into PiP.
  - **Playback Remote Actions**:
    - Register `RemoteAction` entries for Play/Pause, Rewind 10s, and Forward 10s with `PendingIntent` broadcasts to `PlayerEngine.kt`.
    - Update `PictureInPictureParams` actions dynamically when playback pauses or resumes.
  - **Files**:
    - `android/app/src/main/AndroidManifest.xml` (MODIFY: PiP activity flags)
    - `android/app/src/main/kotlin/org/hdhropen/app/MainActivity.kt` (MODIFY: PiP lifecycle & broadcast receiver)
    - `android/app/src/main/kotlin/org/hdhropen/app/ui/screens/player/PlayerScreen.kt` (MODIFY: PiP button & remote action state)

- [ ] **PIP-4 — iOS/iPadOS/macOS: Native AVPictureInPictureController Integration & Background Playback.**
  Bring native PiP support to Apple platforms (`apple/HDHROpenKit` & `apple/HDHROpeniOS`):
  - **AVPictureInPictureController & AudioSession**:
    - Integrate `AVPictureInPictureController` in `PlayerEngine.swift` / `PlayerLayerView.swift` with `isPictureInPictureSupported()` guard.
    - Set `AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)` and configure `canStartPictureInPictureAutomaticallyFromInline = true` (iOS 14.2+).
    - Implement `AVPictureInPictureControllerDelegate` to handle lifecycle transitions (`willStart`, `didStop`, `restoreUserInterfaceForPictureInPictureStop`).
  - **UI Integration**:
    - Add PiP action button in `iOSPlayerView.swift` toolbar.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Playback/PlayerEngine.swift` (MODIFY: PiP controller and delegate)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Playback/PlayerLayerView.swift` (MODIFY: AVPlayerLayer PiP hookup)
    - `apple/HDHROpeniOS/Views/Player/iOSPlayerView.swift` (MODIFY: PiP toggle button)

