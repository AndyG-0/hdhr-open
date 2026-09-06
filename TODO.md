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
