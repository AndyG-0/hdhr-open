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

## Cast & AirPlay Support

- [ ] **CAST-4 — Web: Persist AirPlay/Cast Sessions Across SPA Navigation, User-Selectable.**
  Today, navigating away from the player page in the web app kills an active AirPlay session:
  AirPlay is bound to the specific `<video>` DOM element (not tab/window-scoped like Google Cast's
  `CastContext`), and `HDHomeRunPlayer.svelte`'s `destroy()` explicitly tears down
  `airplaySessionId`/stops the backend HLS session on unmount — mirroring what Safari would do
  anyway once that element leaves the DOM. Google Cast already *does* survive SPA navigation today
  (`cast-loader.ts`'s module-level `activeBackendSessionId` singleton — `CastContext` lives at the
  tab/window level, independent of any DOM element), so this ticket is really about closing the gap
  for AirPlay and then giving the user an explicit choice for both:
  - Making AirPlay survive navigation requires the same `<video>` element (not just component state)
    to persist across routes — e.g. hoisting playback into a persistent layout-level "mini
    player"/PiP-style component that stays mounted while the user browses elsewhere, rather than
    living inside the per-page component that unmounts today. This is a real architecture change to
    where/how the player is composed, not a small patch.
  - Once that's in place, expose a convenient UX toggle (e.g. "keep playing when I navigate away" /
    a persistent mini-player affordance) so the user can opt in or out per-session rather than it
    being all-or-nothing — should work the same way for both AirPlay and Google Cast so the two
    don't have inconsistent navigation behavior.
  - Needs product/UX thought on where that toggle lives and what the mini-player looks like while
    AirPlaying/casting and the user is elsewhere in the app, not just the plumbing.
  - **Files**:
    - `frontend/src/routes/+layout.svelte` (MODIFY: persistent player or mini-player host)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: decouple teardown from page unmount)
    - `frontend/src/lib/components/player/MiniPlayer.svelte` (NEW: docked/floating mini-player UI)
    - `frontend/src/lib/stores/playback.ts` (NEW: persistent playback state store)

## Apple SharePlay

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

## AI Intelligence & Natural Language Assistant

- [ ] **AI-5 — Native Clients: AI Assistant Feature Parity (iOS/tvOS & Android).**
  Expose AI assistant capabilities in native client apps, leveraging the backend AI chat endpoint (`POST /api/ai/chat`) and tool orchestration:
  - **Shared Core (`HDHROpenKit` & `:core`)**:
    - Add AI models and networking methods (`APIClient.sendAIChat`, `APIClient.testAIConnection`).
  - **iOS (`HDHROpeniOS`)**:
    - SwiftUI `iOSAIAssistantSheet.swift` with conversational interface, quick suggestion chips
      ("What's on tonight?", "Upcoming live sports"), and recording confirmation dialogs.
  - **tvOS (`HDHROpenTV`)**:
    - 10-foot Siri Remote optimized voice/text AI guide search modal `TVAIAssistantModal.swift`.
  - **Android (`android/app`)**:
    - Jetpack Compose `AIAssistantBottomSheet.kt` with chat feed and action cards.
  - **Files**:
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Networking/APIClient+AI.swift` (NEW)
    - `apple/HDHROpenKit/Sources/HDHROpenKit/Models/AIModels.swift` (NEW)
    - `apple/HDHROpeniOS/Views/AI/iOSAIAssistantSheet.swift` (NEW)
    - `apple/HDHROpenTV/Views/AI/TVAIAssistantModal.swift` (NEW)
    - `android/core/src/main/kotlin/org/hdhropen/kit/networking/APIClient+AI.kt` (NEW)
    - `android/core/src/main/kotlin/org/hdhropen/kit/models/AIModels.kt` (NEW)
    - `android/app/src/main/kotlin/org/hdhropen/app/ui/screens/ai/AIAssistantBottomSheet.kt` (NEW)

## Picture-in-Picture (PiP) & Popout Player

- [x] **PIP-2 — Web: Standalone Popout Player Route & Window Handoff.**
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

## Video Player Experience & Contextualization

- [ ] **PLYR-2 — In-Player Quick Channel Switcher (Live TV).**
  Add a quick slide-up or overlay channel lineup switcher during Live TV playback:
  - Overlay or drawer listing enabled channels with current airing title without leaving full-screen playback.
  - Allows seamless zap-style channel changing directly from the player.
  - **Files**:
    - `frontend/src/lib/components/player/PlayerChannelDrawer.svelte` (NEW)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: drawer integration)

- [ ] **PLYR-3 — Commercial Skip & Chapter Markers (Recorded Media).**
  Support EDL / comskip chapter markers on recorded DVR media:
  - Backend: Detect and read `.edl` or comskip cutlists alongside `.ts`/`.mp4` recordings in `backend/app/dvr/` and expose chapter markers via the recording detail endpoint (`GET /api/dvr/recordings/{id}`).
  - Frontend: Render chapter / commercial segments on `PlayerScrubBar.svelte`.
  - Add quick "Skip Commercial" action prompt when playback enters a detected commercial block.
  - **Files**:
    - `backend/app/api/dvr.py` (MODIFY: expose markers in recording detail)
    - `frontend/src/lib/components/player/PlayerScrubBar.svelte` (MODIFY: marker tier)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: commercial skip controller)
