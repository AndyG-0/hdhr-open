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

- [ ] **CC-1 — Android: wire captions into live playback.** Caption fetch
  currently only happens in `PlayerViewModel.loadRecordingMetadata()`
  (`android/core/src/main/kotlin/org/hdhropen/kit/viewmodels/PlayerViewModel.kt`),
  called only from the two recording-playback call sites. Live-channel
  playback via `PlayerEngine.loadMedia()` never fetches captions at all —
  almost certainly why captions "don't work on Android." Extend the fetch to
  fire for live/watch-session playback too, using the same `recording_id`-backed
  watch-session model the web client relies on. Add a `CaptionController`
  sync/timing test (`android/core/src/test/kotlin/org/hdhropen/kit/`
  currently only has `VTTParserTest.kt`).

- [ ] **CC-2 — iOS/tvOS: fix the direct-HLS-fallback caption gap.** In
  `apple/HDHROpenKit/Sources/HDHROpenKit/ViewModels/PlayerViewModel.swift`,
  `playChannel`'s fallback path (used when a watch session can't start — busy
  tuner / no DVR session, ~lines 148-164) skips `loadRecordingMetadata()`
  entirely, so captions silently disappear whenever that fallback is taken.
  Call it on both paths whenever a `recording_id` backing exists. Verify
  on-device (real tuner) that the overlay renders correctly through this
  path — can't be confirmed from code alone.

- [ ] **CC-3 — Backend: diagnose/harden live caption extraction
  reliability.** Investigate why captions are "spotty" on web despite
  correct client wiring — likely the live CEA-608/708 `subcc` ffmpeg pipe in
  `media_cache.py` (`_run_live_caption_loop` / watchdog / restart logic).
  Needs live-tuner testing to reproduce; document findings and fix or add
  resiliency (tighter restart/backoff, logging around cue gaps).

- [ ] **CC-4 — Backend: eager caption extraction on recording completion.**
  Confirm whether `generate_captions_vtt()` in `media_cache.py` currently
  runs eagerly at recording-finish or lazily on first
  `GET /api/dvr/recording-captions.vtt`. If lazy, add a background-task
  trigger at recording completion (in `backend/app/dvr/builtin/capture.py`
  or wherever recording-finish is handled) so the VTT is pre-generated and
  ready to serve immediately.

- [ ] **CC-5 — Scheduled Tasks admin (web-admin only).** New, standalone
  feature, larger than CC-1..CC-4 — plan as its own multi-part iteration. A
  minimal job-registry + runner + status/history API and admin UI page
  generalizing background maintenance work. Register the recording-completion
  caption extraction (from CC-4) and an HLS temp-file/cache cleanup pass
  (audit existing lifecycle handling in `backend/app/hls_streaming.py` /
  `backend/app/dvr/builtin/retention.py`) as the first two jobs. Start with
  the backend job-runner primitives before building the admin UI.

## Native Client CI

`.github/workflows/ci.yml` currently only has `backend` and `frontend` jobs
— no coverage for `apple/` or `android/` at all.

- [ ] **CI-1 — Android GitHub Actions job.** Add an `android` job to
  `.github/workflows/ci.yml`: setup JDK 17 + Gradle, run
  `./gradlew :core:test` (5 existing test files under
  `android/core/src/test/`) and lint. No signing needed for this job.

- [ ] **CI-2 — Apple GitHub Actions job.** Add an `apple` job on a
  `macos-latest` runner: run `swift test --package-path apple/HDHROpenKit`
  (12 existing tests across `HDHROpenKitTests`), matching the command
  already documented in `apple/README.md`.

## Sideload Build Artifacts

Neither client has release signing configured today (Apple:
`CODE_SIGN_STYLE = Automatic`, no team ID committed; Android: no
keystore/signingConfig, `assembleRelease` would emit an unsigned APK). No
App Store / TestFlight plans currently — builds are for side-loading only.
Decided artifact venue: **GitHub Releases**.

- [ ] **BUILD-1 — Android signed release APK via CI → GitHub Releases.**
  Generate a release keystore (stored as GitHub Actions secrets, not
  committed), wire a `signingConfig` into `android/app/build.gradle.kts`,
  add a workflow (manual `workflow_dispatch` or on version tag) that runs
  `./gradlew :app:assembleRelease` and publishes the signed APK to a GitHub
  Release. Document install steps ("unknown sources" / install-from-APK) in
  `android/README.md`.

- [ ] **BUILD-2 — Apple sideload docs (free-tier) + future paid-account
  plan.** No paid Apple Developer account exists yet, so this is
  documentation-only for now: add a section to `apple/README.md` covering
  local Xcode "Personal Team" build+install for iOS and tvOS (free-tier
  signing, 7-day resign expiry, device UDID registration, periodic
  reinstall via Xcode). Separately document what changes if a paid
  Developer Program account is added later (ad-hoc export options plist,
  `DEVELOPMENT_TEAM`/cert/profile as GitHub secrets, a CI job producing a
  durable `.ipa` published to GitHub Releases like BUILD-1) so that upgrade
  path doesn't require re-planning.
