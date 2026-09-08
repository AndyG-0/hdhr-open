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
