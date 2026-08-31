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

- [ ] **CC-8 — Backend: research further live-caption latency reduction
  (needs scoping).** Not started — this is a research item, not a
  ready-to-implement fix. Real-tuner testing after CC-3 shipped (2026-08-30)
  measured live-caption lag at **3-7s** behind dialogue — much better than
  the pre-CC-3 10-20s (that figure was inflated by the hang/restart bug
  CC-3 fixed, not a true latency measurement), but still perceptible and
  reported as "not quite synced" for both web and Android. Context and
  constraints carried over from CC-3's investigation, so a future session
  doesn't have to re-derive them:
  - **Root cause, confirmed:** ffmpeg's WebVTT muxer can't flush a cue
    until the CEA-608/708 roll-up decoder's internal buffer advances (i.e.
    until the *next* line of dialogue starts pushing the current one up) —
    this is how `media_cache.py`'s `movie`/`subcc` lavfi filter chain works
    today (`_run_live_caption_process_once`,
    `_generate_captions_vtt_uncached`). It's inherent to roll-up mode
    captioning in general, not specific to ffmpeg — real broadcast CC
    decoders (cable boxes, TVs) show comparable lag on roll-up captions, so
    part of this research is confirming how much of the 3-7s is actually
    reducible versus a property of the caption format itself.
  - **Why this needs research, not just a fix:** closing the gap further
    likely means not using ffmpeg's built-in CC decoder at all — e.g. a
    custom real-time CEA-608/708 decoder (parsing caption byte pairs
    directly off the transport stream) that emits partial/in-progress
    roll-up lines instead of waiting for a complete flush, or evaluating
    whether a different tool (e.g. `ccextractor`, which has its own
    real-time modes) has lower end-to-end latency than ffmpeg's `movie`
    filter approach. Either direction is a substantially bigger effort
    than CC-3's resiliency work and needs its own scoping/design pass
    before implementation.
  - **Testing constraint:** like CC-3, this cannot be meaningfully
    evaluated without a live tuner — the lag is a property of real
    broadcast caption timing, not something the existing fake-process test
    scaffolding in `test_media_cache.py` can reproduce.
  - Related, already fixed (see CC-3): the `\h` control-artifact leak found
    during this same real-tuner session was a separate correctness bug,
    not a latency contributor — don't re-open it here.

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

- [ ] **CC-5 follow-up — Scheduled Tasks admin UI page.** Build the admin
  UI on top of the `/api/admin/jobs` API above. No separate admin route
  exists in the frontend today — admin-only sections are folded into
  `frontend/src/routes/settings/+page.svelte` behind `{#if
  $user?.role === 'admin'}`, composed from
  `frontend/src/lib/components/settings/*Section.svelte` — a
  `JobsSection.svelte` there is the natural fit, not a new route.

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
