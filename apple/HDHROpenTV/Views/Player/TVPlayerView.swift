import AVKit
import HDHROpenKit
import SwiftUI

public struct TVPlayerView: View {
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @EnvironmentObject private var multiPlayerViewModel: MultiPlayerViewModel

    @State private var showControls = true
    @State private var controlsTimer: Task<Void, Never>?
    @State private var showRecordingOptionsSheet = false
    @State private var loadingQuip: String = LoadingQuips.random()
    /// SwiftUI doesn't automatically retarget focus onto the ZStack just
    /// because `.focusable(!showControls)` makes it newly eligible the
    /// instant `TVPlaybackControlsView` (and its own focused button) leaves
    /// the tree - focus was landing on nothing, so arrow presses had no
    /// responder to deliver to and `.onMoveCommand`/`.onExitCommand` never
    /// fired. Explicitly pushing focus here every time controls hide is what
    /// actually claims it, mirroring the same pattern `TVPlaybackControlsView`
    /// already uses to claim focus for a button when controls appear.
    @FocusState private var isFallbackFocused: Bool

    public init() {}

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            // Video Player Layer
            if let avPlayer = playerViewModel.playerEngine.avPlayer {
                PlayerLayerView(player: avPlayer)
                    .ignoresSafeArea()
            }

            // Closed Captions Overlay
            if let captionText = playerViewModel.captionController.activeCueText {
                VStack {
                    Spacer()
                    Text(captionText)
                        .font(.title2.bold())
                        .foregroundColor(.yellow)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                        .padding(.vertical, 8)
                        .background(Color.black.opacity(0.75))
                        .cornerRadius(8)
                        .padding(.bottom, showControls ? 180 : 60)
                }
            }

            // Status / Error Banner
            if case let .failed(message) = playerViewModel.playerEngine.state {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 64))
                        .foregroundColor(.yellow)
                    Text("Playback Error")
                        .font(.title2.bold())
                    Text(message)
                        .font(.body)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Close") {
                        playerViewModel.closePlayer()
                    }
                }
                .padding(40)
                .background(Theme.appSurface)
                .cornerRadius(16)
            } else if playerViewModel.playerEngine.state == .loading || playerViewModel.playerEngine.state == .buffering {
                VStack(spacing: 24) {
                    ProgressView()
                        .scaleEffect(2.0)
                    Text(loadingQuip)
                        .font(.headline)
                        .foregroundColor(.white.opacity(0.9))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 48)
                        .id(loadingQuip)
                }
                .padding(32)
            }

            // Controls Overlay
            if showControls {
                VStack {
                    // Top Info Bar
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(playerViewModel.mediaTitle)
                                .font(.title.bold())
                                .foregroundColor(.white)

                            if let subtitle = playerViewModel.mediaSubtitle {
                                Text(subtitle)
                                    .font(.headline)
                                    .foregroundColor(.gray)
                            }
                        }

                        Spacer()

                        Button(action: { playerViewModel.showChannelSwitcher.toggle() }) {
                            Label("Channels", systemImage: "list.bullet")
                        }
                    }
                    .padding(.horizontal, 48)
                    .padding(.top, 40)

                    Spacer()

                    // Bottom Controls & Scrub Bar
                    VStack(spacing: 20) {
                        TVScrubBarView(
                            currentTime: playerViewModel.playerEngine.currentTime,
                            duration: playerViewModel.playerEngine.duration,
                            isLive: playerViewModel.playerEngine.isLive,
                            isSeekable: playerViewModel.playerEngine.isSeekable,
                            thumbnailCues: playerViewModel.thumbnailCues,
                            spriteURL: playerViewModel.thumbnailSpriteURL,
                            onSeek: { target in
                                playerViewModel.seek(to: target)
                            }
                        )

                        TVPlaybackControlsView(
                            playerViewModel: playerViewModel,
                            onTogglePlayPause: {
                                playerViewModel.togglePlayPause()
                                resetControlsTimer()
                            },
                            onSkipBackward: {
                                playerViewModel.skipBackward(seconds: 10)
                                resetControlsTimer()
                            },
                            onSkipForward: {
                                playerViewModel.skipForward(seconds: 10)
                                resetControlsTimer()
                            },
                            onClose: {
                                playerViewModel.closePlayer()
                            },
                            onAddToMultiView: {
                                if let ch = playerViewModel.activeChannel {
                                    let airing = playerViewModel.activeAiring
                                    // Reserve the slot synchronously before closing the single-player
                                    // screen, so RootTVView switches straight to multi-view instead of
                                    // flashing back to the Guide while the stream negotiates.
                                    if let slotId = try? multiPlayerViewModel.beginAddFeed(channel: ch, airing: airing) {
                                        playerViewModel.closePlayer()
                                        Task {
                                            try? await multiPlayerViewModel.finishAddFeed(slotId: slotId)
                                        }
                                    }
                                }
                            }
                        )
                    }
                    .padding(.horizontal, 48)
                    .padding(.bottom, 40)
                }
                .background(
                    LinearGradient(
                        colors: [Color.black.opacity(0.8), Color.clear, Color.black.opacity(0.85)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .ignoresSafeArea()
                )
                .transition(.opacity)
                .disabled(playerViewModel.showChannelSwitcher || playerViewModel.showAudioMenu || playerViewModel.showRecordMenu || playerViewModel
                    .showSyncPlaySheet)
            }

            // Channel Switcher Bottom Drawer
            if playerViewModel.showChannelSwitcher {
                VStack {
                    Spacer()
                    TVChannelSwitcherOverlay(
                        channels: guideViewModel.displayedChannels,
                        currentChannel: playerViewModel.activeChannel,
                        onSelectChannel: { ch in
                            playerViewModel.showChannelSwitcher = false
                            Task {
                                await playerViewModel.playChannel(channel: ch)
                            }
                        },
                        onDismiss: {
                            playerViewModel.showChannelSwitcher = false
                        }
                    )
                }
                .transition(.move(edge: .bottom))
            }

            // Audio & Stream Settings Overlay
            if playerViewModel.showAudioMenu {
                TVPlayerSettingsOverlay(
                    playerViewModel: playerViewModel,
                    onDismiss: { playerViewModel.showAudioMenu = false }
                )
                .transition(.opacity)
            }

            // SyncPlay Overlay
            if playerViewModel.showSyncPlaySheet {
                TVSyncPlayOverlay(
                    playerViewModel: playerViewModel,
                    onDismiss: { playerViewModel.showSyncPlaySheet = false }
                )
                .transition(.opacity)
            }

            // Record Menu Overlay
            if playerViewModel.showRecordMenu {
                let existingRule = guideViewModel.findRule(for: playerViewModel.activeChannel?.channelNumber, airing: playerViewModel.activeAiring)
                let canRecordSeries = !(playerViewModel.activeAiring?.seriesId?.isEmpty ?? true) || !(playerViewModel.activeAiring?.title.isEmpty ?? true)

                TVPlayerRecordMenuOverlay(
                    existingRule: existingRule,
                    canRecordSeries: canRecordSeries,
                    isPromoted: playerViewModel.isPromoted,
                    isPromoting: playerViewModel.isPromoting,
                    onSaveCurrentRecording: {
                        playerViewModel.showRecordMenu = false
                        Task { await playerViewModel.promoteToRecording() }
                    },
                    onRecordEpisode: {
                        playerViewModel.showRecordMenu = false
                        Task {
                            try? await guideViewModel.recordEpisode(
                                seriesId: playerViewModel.activeAiring?.seriesId,
                                channelNumber: playerViewModel.activeChannel?.channelNumber,
                                start: playerViewModel.activeAiring?.start
                            )
                        }
                    },
                    onRecordSeries: {
                        playerViewModel.showRecordMenu = false
                        Task {
                            try? await guideViewModel.recordSeries(
                                seriesId: playerViewModel.activeAiring?.seriesId ?? "",
                                channelNumber: playerViewModel.activeChannel?.channelNumber
                            )
                        }
                    },
                    onCancelRule: {
                        playerViewModel.showRecordMenu = false
                        if let rule = existingRule {
                            Task { try? await guideViewModel.cancelRule(ruleId: rule.recordingRuleId) }
                        }
                    },
                    onOptions: {
                        playerViewModel.showRecordMenu = false
                        showRecordingOptionsSheet = true
                    },
                    onDismiss: { playerViewModel.showRecordMenu = false }
                )
                .transition(.opacity)
            }

            // Fallback focus target + reveal-on-press handler, present ONLY
            // while controls are hidden. Confirmed via live device logs that
            // `.onMoveCommand` attached anywhere in this ZStack's modifier
            // chain intercepts every single directional press (100% of
            // presses logged, regardless of `.focusable` state) rather than
            // only falling back when the focus engine can't find a
            // navigable sibling - so it can never sit alongside
            // `TVPlaybackControlsView`'s buttons in the tree, not even as an
            // unfocusable modifier. Making it a genuinely conditional ZStack
            // CHILD (like the overlays above), rather than a conditional
            // modifier on the whole ZStack, means it's fully absent from the
            // responder chain when controls are visible - it can't compete.
            if !showControls {
                // `.onExitCommand` for this state is handled by the single
                // instance attached to the outer ZStack below (it only needs
                // focus to be somewhere in the subtree, which this view
                // satisfies) - attaching a second one here would fire
                // `closePlayer()` twice per Menu press.
                Color.clear
                    .focusable(true)
                    .focused($isFallbackFocused)
                    .onMoveCommand { _ in
                        withAnimation { showControls = true }
                        resetControlsTimer()
                    }
            }
        }
        .task {
            if recordingsViewModel.dvrInfo == nil {
                await recordingsViewModel.loadDvrInfo()
            }
        }
        .task(id: playerViewModel.playerEngine.state) {
            if playerViewModel.playerEngine.state == .loading || playerViewModel.playerEngine.state == .buffering {
                loadingQuip = LoadingQuips.random(excluding: loadingQuip)
                while !Task.isCancelled {
                    try? await Task.sleep(nanoseconds: 2_800_000_000)
                    if !Task.isCancelled {
                        withAnimation(.easeInOut(duration: 0.35)) {
                            loadingQuip = LoadingQuips.random(excluding: loadingQuip)
                        }
                    }
                }
            }
        }
        .fullScreenCover(isPresented: $showRecordingOptionsSheet) {
            if let channel = playerViewModel.activeChannel, let airing = playerViewModel.activeAiring {
                let existingRule = guideViewModel.findRule(for: channel.channelNumber, airing: airing)
                TVRecordingOptionsModal(
                    channel: channel,
                    airing: airing,
                    canRecordSeries: !(airing.seriesId?.isEmpty ?? true) || !airing.title.isEmpty,
                    existingRule: existingRule,
                    onConfirm: { recordSeries, options in
                        showRecordingOptionsSheet = false
                        Task {
                            if let rule = existingRule {
                                try? await guideViewModel.updateRule(
                                    ruleId: rule.recordingRuleId,
                                    isSeries: recordSeries,
                                    options: options,
                                    seriesId: airing.seriesId,
                                    start: airing.start,
                                    channelNumber: channel.channelNumber
                                )
                            } else if recordSeries {
                                try? await guideViewModel.recordSeries(
                                    seriesId: airing.seriesId ?? "",
                                    channelNumber: channel.channelNumber,
                                    options: options
                                )
                            } else {
                                try? await guideViewModel.recordEpisode(
                                    seriesId: airing.seriesId,
                                    channelNumber: channel.channelNumber,
                                    start: airing.start,
                                    options: options
                                )
                            }
                        }
                    },
                    onCancelRule: existingRule.map { rule in
                        {
                            showRecordingOptionsSheet = false
                            Task { try? await guideViewModel.cancelRule(ruleId: rule.recordingRuleId) }
                        }
                    }
                )
            }
        }
        .onChange(of: playerViewModel.playerEngine.state) { _, newState in
            // The auto-hide countdown must only run once there's actually
            // something playing to hide controls over. Starting it on
            // `onAppear` (as before) meant it was already ticking during
            // session negotiation + startup, which now regularly takes
            // longer than the 7s countdown - controls were auto-hidden
            // before playback ever began, leaving nothing but the video.
            if newState == .playing {
                resetControlsTimer()
            } else {
                controlsTimer?.cancel()
            }
        }
        .onTapGesture {
            withAnimation {
                showControls.toggle()
            }
            if showControls {
                resetControlsTimer()
            } else {
                isFallbackFocused = true
            }
        }
        // Menu press while controls ARE visible still needs to close the
        // player, and `.onExitCommand` only requires focus to be somewhere
        // in this subtree (not on the ZStack itself) - so this one modifier
        // covers both button-focused and fallback-focused cases. It doesn't
        // exhibit the same "intercept everything" behavior `.onMoveCommand`
        // does, so it's safe to leave unconditionally attached here.
        .onExitCommand {
            playerViewModel.closePlayer()
        }
        .alert("Error", isPresented: Binding(
            get: { guideViewModel.error != nil },
            set: {
                if !$0 {
                    guideViewModel.dismissError()
                }
            }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(guideViewModel.error ?? "")
        }
        .alert("Error", isPresented: Binding(
            get: { playerViewModel.error != nil },
            set: {
                if !$0 {
                    playerViewModel.dismissError()
                }
            }
        )) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(playerViewModel.error ?? "")
        }
    }

    private func resetControlsTimer() {
        controlsTimer?.cancel()
        controlsTimer = Task {
            try? await Task.sleep(nanoseconds: 7_000_000_000) // 7s auto hide
            if !Task.isCancelled {
                withAnimation {
                    showControls = false
                }
                isFallbackFocused = true
            }
        }
    }
}
