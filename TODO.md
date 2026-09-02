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

- [ ] **CC-11 — Android: simplify live-caption lag-compensation logic once
  CC-8/CC-9 are verified on real hardware.** Same follow-up as CC-10, for
  Android's equivalent logic (`LIVE_CUE_STRETCH_SECONDS`, `alignLiveCues`,
  `stretchedCueDisplay` in `PlayerViewModel.kt`), built during CC-1/CC-6 to
  cope with the same late-batch-arrival pattern CC-8 addresses server-side.

- [ ] **CC-12 — iOS/tvOS: simplify live-caption lag-compensation logic once
  CC-8/CC-9 are verified on real hardware.** Same follow-up as CC-10/CC-11,
  for the Swift port of the same logic in
  `apple/HDHROpenKit/.../PlayerViewModel.swift`, built during CC-7 to match
  Android's CC-6 behavior.

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

- [ ] **CC-14 — Backend + Web: let the user pick a CC track when a
  recording/live channel has more than one.** Follow-up to CC-13: now that
  the primary track leak is fixed, some broadcasts (sports especially)
  genuinely do carry a second CEA-608 channel (CC3, "usually Spanish" per
  `ccextractor --help`) or a second CEA-708 service worth exposing, instead
  of just discarding it. Scoped as backend + web only for the first pass,
  matching how CC-8 and CC-1/CC-6→CC-7 landed backend/one-client first —
  native parity (mirroring CC-10/CC-11/CC-12's per-platform follow-up
  pattern) is a separate future ticket once this is verified on web.
  - **Open question this needs a spike to answer, not a blind
    implementation:** how to detect a second track exists without paying
    full decode cost on every capture. Unlike audio tracks (enumerable
    cheaply from stream probe metadata, already surfaced via
    `recording-detail`'s `audio: []`), CEA-608/708 channel occupancy isn't
    visible without actually decoding — `ffprobe`'s `ATSC A53 Part 4 Closed
    Captions` side-data (see CC-8's spike) just says *some* CC data is
    present, not which of CC1-4/708 services carry real content.
  - **`-12` (combined-channel) ccextractor flag is not a safe shortcut as
    tested**: piping the same local sample recording through `ccextractor
    -stdin -12 -out=srt -stdout --quiet` produced ccextractor's own
    crash-report banner ("Issues? Open a ticket...") straight onto stdout —
    the exact stream `_parse_srt_block` parses — instead of clean SRT.
    `-1` and `-2` run separately (each ccextractor's own already-proven
    single-channel path from CC-8/CC-13) is the safer starting point;
    `-2` against the same local sample produced zero cues, confirming that
    recording has no real secondary-channel content and can't validate a
    picker on its own — this needs either a live tuner capture of a
    genuinely dual-language broadcast, or synthetic/crafted CC2 test data.
  - **Recommended approach to spike first:** run the secondary-channel
    `ccextractor -2` decode lazily/on-demand (started only when a client
    asks for track availability or selects the second track) rather than
    unconditionally for every capture, since running it always-on doubles
    per-capture caption-decode CPU for the common single-track case — a
    real cost on the Raspberry Pi arm64 target called out in CC-9, not yet
    measured. If a lazy secondary decode produces no cues within a grace
    period, the client should treat that track as unavailable rather than
    showing a permanently blank caption option.
  - **Backend, once the detection approach is settled**
    (`backend/app/dvr/media_cache.py`): a second long-lived `ccextractor
    -2` process per active capture (mirroring `_run_live_caption_
    ccextractor_process`'s existing `-1` supervision/restart/circuit-
    breaker logic), writing to its own sidecar file (e.g.
    `{recording_id}.cc2.live.vtt`) rather than appending to the existing
    `.live.vtt`. New API surface to expose which tracks exist and let a
    client select one — likely a query param on
    `GET /api/dvr/recording-captions.vtt` (e.g. `?track=2`) plus a track-
    list field on `recording-detail`, mirroring the existing `audio: []`
    array's shape.
  - **Web** (`frontend/src/lib/caption-controller.ts`,
    `HDHomeRunPlayer.svelte`): a track picker mirroring the existing
    `currentAudioIndex` audio-track selector pattern — only shown when
    `recording-detail` reports more than one caption track, switching
    `pollLiveCaptions()`/`loadCaptions()`'s target URL and resetting
    `captionCues`/the stretch cursor on switch.
  - Tests: backend coverage in `test_media_cache.py` for the second
    supervised process (mirroring the existing `-1` process's tests) and
    track-selection query param; frontend coverage in
    `HDHomeRunPlayer.test.ts` for the picker UI and track-switch reset
    behavior.

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

- [ ] **REC-5 — Native In-Player Recording Controls Parity (iOS, tvOS, Android).**
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

## Tuner & Network Intelligence

When the official HDHomeRun app (iOS, iPadOS, tvOS, Android) streams Live TV on a
network with an active HDHomeRun RECORD server / NAS, it buffers the live stream
through the RECORD engine (port 50000) rather than tuning the hardware directly.
This causes the physical tuner unit to report the NAS's IP as its `TargetIP`,
masking the actual client device (e.g. iPhone, Apple TV) using the tuner.

- [ ] **TUNER-1 — Remote HDHomeRun RECORD engine SSH client monitoring & stream disambiguation.**
  Enable HDHR Open to inspect active downstream clients connected to the official
  `hdhomerun_record` service on a remote NAS/server via SSH and correlate them to physical tuners:
  - **SSH Configuration in Network Settings** (`backend/app/integrations/hdhomerun_client.py`,
    `backend/app/api/network_settings.py`, `frontend/src/lib/components/settings/HDHomeRunNetworkSection.svelte`):
    Add optional SSH connection fields to the `hdhomerun` network integration (`dvr_ssh_enabled`,
    `dvr_ssh_host`, `dvr_ssh_port`, `dvr_ssh_username`, `dvr_ssh_key`, `dvr_ssh_password`)
    with a "Test SSH Connection" action in the admin UI.
  - **Remote Socket & Process Inspection** (`backend/app/integrations/hdhomerun_ssh.py` or
    `hdhomerun_client.py`):
    Execute non-blocking async socket inspection on the NAS (`ss -tnp '( sport = :50000 )'`
    with fallbacks to `lsof -n -P -i :50000` / `netstat -tnp | grep :50000`) with a 2-second
    timeout and a 10-second cache TTL to extract active remote client IPs and process PIDs.
  - **Tuner Stream Disambiguation** (`backend/app/api/tuner.py`):
    - *Single stream*: 1:1 match between active physical tuner and the connected client IP,
      resolving the client's friendly reverse-DNS hostname.
    - *Scheduled recording + Live TV*: Correlate active recording channels against
      `recorded_files.json` to identify scheduled recordings, and attribute remaining
      tuners to active live buffer client connections.
    - *Multiple concurrent live streams*: Inspect open file descriptors (`lsof -n -P -p <pid> -F n`)
      for buffer file descriptors, or present aggregated client lists (`Client: iPhone, Apple TV via RECORD Engine`).
    - *Graceful fallback*: Seamlessly falls back to `HDHomeRun RECORD (<NAS IP>)` when SSH is
      unconfigured or fails.
  - **Tests**: Unit tests in `backend/tests/test_api_tuner.py` and `backend/tests/test_hdhomerun_client.py`
    with mocked SSH command outputs across Linux (`ss`), BSD/macOS (`lsof`), and fallback (`netstat`) formats.


