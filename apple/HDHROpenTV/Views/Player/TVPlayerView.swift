import SwiftUI
import AVKit
import HDHROpenKit

public struct TVPlayerView: View {
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel

    @State private var showControls: Bool = true
    @State private var controlsTimer: Task<Void, Never>?
    // SwiftUI doesn't automatically retarget focus onto the ZStack just
    // because `.focusable(!showControls)` makes it newly eligible the
    // instant `TVPlaybackControlsView` (and its own focused button) leaves
    // the tree - focus was landing on nothing, so arrow presses had no
    // responder to deliver to and `.onMoveCommand`/`.onExitCommand` never
    // fired. Explicitly pushing focus here every time controls hide is what
    // actually claims it, mirroring the same pattern `TVPlaybackControlsView`
    // already uses to claim focus for a button when controls appear.
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
            if case .failed(let message) = playerViewModel.playerEngine.state {
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
                ProgressView()
                    .scaleEffect(2.0)
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
                                playerViewModel.playerEngine.seek(to: target)
                            }
                        )

                        TVPlaybackControlsView(
                            playerViewModel: playerViewModel,
                            onTogglePlayPause: {
                                playerViewModel.playerEngine.togglePlayPause()
                                resetControlsTimer()
                            },
                            onSkipBackward: {
                                playerViewModel.playerEngine.skipBackward(seconds: 10)
                                resetControlsTimer()
                            },
                            onSkipForward: {
                                playerViewModel.playerEngine.skipForward(seconds: 10)
                                resetControlsTimer()
                            },
                            onClose: {
                                playerViewModel.closePlayer()
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
                // These controls stay mounted (not removed from the tree)
                // while the channel switcher / audio menu overlays are open,
                // so without this their buttons keep focus and swallow arrow
                // presses meant for the overlay on top of them - the overlay
                // views can claim focus onAppear, but the focus engine still
                // considers these disabled buttons unless they're explicitly
                // excluded.
                .disabled(playerViewModel.showChannelSwitcher || playerViewModel.showAudioMenu)
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
