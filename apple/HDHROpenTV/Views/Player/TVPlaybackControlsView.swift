import SwiftUI
import HDHROpenKit

public struct TVPlaybackControlsView: View {
    @ObservedObject var playerViewModel: PlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel

    let onTogglePlayPause: () -> Void
    let onSkipBackward: () -> Void
    let onSkipForward: () -> Void
    let onClose: () -> Void

    @FocusState private var focusedControl: ControlFocus?

    private enum ControlFocus {
        case skipBack, playPause, skipForward, record, syncplay, shareplay, audio, captions, close
    }

    public init(
        playerViewModel: PlayerViewModel,
        onTogglePlayPause: @escaping () -> Void,
        onSkipBackward: @escaping () -> Void,
        onSkipForward: @escaping () -> Void,
        onClose: @escaping () -> Void
    ) {
        self.playerViewModel = playerViewModel
        self.onTogglePlayPause = onTogglePlayPause
        self.onSkipBackward = onSkipBackward
        self.onSkipForward = onSkipForward
        self.onClose = onClose
    }

    public var body: some View {
        HStack(spacing: 32) {
            // Skip 10s backward
            if playerViewModel.playerEngine.isSeekable {
                Button(action: onSkipBackward) {
                    Image(systemName: "gobackward.10")
                        .font(.title2)
                        .frame(width: 64, height: 64)
                }
                .buttonStyle(.plain)
                .focused($focusedControl, equals: .skipBack)
            }

            // Play / Pause
            Button(action: onTogglePlayPause) {
                Image(systemName: playerViewModel.isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: 36))
                    .frame(width: 80, height: 80)
                    .background(Color.white.opacity(0.2))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .focused($focusedControl, equals: .playPause)

            // Skip 10s forward
            if playerViewModel.playerEngine.isSeekable {
                Button(action: onSkipForward) {
                    Image(systemName: "goforward.10")
                        .font(.title2)
                        .frame(width: 64, height: 64)
                }
                .buttonStyle(.plain)
                .focused($focusedControl, equals: .skipForward)
            }

            Spacer()

            // Record Menu Button
            if playerViewModel.isWatchSession {
                let existingRule = guideViewModel.findRule(for: playerViewModel.activeChannel?.channelNumber, airing: playerViewModel.activeAiring)

                Button(action: {
                    playerViewModel.showRecordMenu.toggle()
                }) {
                    HStack(spacing: 8) {
                        Image(systemName: (existingRule != nil || playerViewModel.isPromoted) ? "checkmark.circle.fill" : "record.circle")
                            .foregroundColor((existingRule != nil || playerViewModel.isPromoted) ? .green : .red)
                        Text(existingRule != nil ? "Recording Scheduled" : (playerViewModel.isPromoted ? "Recording Saved" : "Record"))
                            .font(.callout.bold())
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)
                    .background(Color.black.opacity(0.6))
                    .cornerRadius(12)
                }
                .buttonStyle(.plain)
                .focused($focusedControl, equals: .record)
                .disabled(playerViewModel.isPromoting)
            }

            // SyncPlay Watch Party Button
            if !playerViewModel.sharePlayCoordinator.isSessionActive {
                Button(action: {
                    playerViewModel.showSyncPlaySheet.toggle()
                }) {
                    HStack(spacing: 6) {
                        Image(systemName: "person.2.fill")
                            .font(.title3)
                            .foregroundColor(playerViewModel.syncPlayClient.room != nil ? .cyan : .white)
                        if playerViewModel.syncPlayClient.room != nil && !playerViewModel.syncPlayClient.participants.isEmpty {
                            Text("\(playerViewModel.syncPlayClient.participants.count)")
                                .font(.callout.bold())
                                .foregroundColor(.cyan)
                        }
                    }
                    .frame(minWidth: 56, minHeight: 56)
                    .padding(.horizontal, 8)
                }
                .buttonStyle(.plain)
                .focused($focusedControl, equals: .syncplay)
            }

            // SharePlay Button
            if !playerViewModel.syncPlayClient.isConnected {
                Button(action: {
                    if playerViewModel.sharePlayCoordinator.isSessionActive {
                        playerViewModel.leaveSharePlaySession()
                    } else {
                        Task { await playerViewModel.startSharePlayOnTV() }
                    }
                }) {
                    HStack(spacing: 6) {
                        Image(systemName: "shareplay")
                            .font(.title3)
                            .foregroundColor(playerViewModel.sharePlayCoordinator.isSessionActive ? .cyan : .white)
                        if playerViewModel.sharePlayCoordinator.isSessionActive && playerViewModel.sharePlayCoordinator.participantCount > 0 {
                            Text("\(playerViewModel.sharePlayCoordinator.participantCount)")
                                .font(.callout.bold())
                                .foregroundColor(.cyan)
                        }
                    }
                    .frame(minWidth: 56, minHeight: 56)
                    .padding(.horizontal, 8)
                }
                .buttonStyle(.plain)
                .focused($focusedControl, equals: .shareplay)
            }

            // Audio Track Selector
            if !playerViewModel.playerEngine.availableAudioTracks.isEmpty {
                Button(action: {
                    playerViewModel.showAudioMenu.toggle()
                }) {
                    Image(systemName: "waveform.circle")
                        .font(.title3)
                        .frame(width: 56, height: 56)
                }
                .buttonStyle(.plain)
                .focused($focusedControl, equals: .audio)
            }

            // Captions Toggle
            Button(action: {
                playerViewModel.captionController.isEnabled.toggle()
            }) {
                Image(systemName: playerViewModel.captionController.isEnabled ? "captions.bubble.fill" : "captions.bubble")
                    .font(.title3)
                    .foregroundColor(playerViewModel.captionController.isEnabled ? .yellow : .white)
                    .frame(width: 56, height: 56)
            }
            .buttonStyle(.plain)
            .focused($focusedControl, equals: .captions)

            // Close Player
            Button(action: onClose) {
                Image(systemName: "xmark.circle.fill")
                    .font(.title2)
                    .frame(width: 56, height: 56)
            }
            .buttonStyle(.plain)
            .focused($focusedControl, equals: .close)
        }
        // This view only exists in the hierarchy while controls are shown
        // (mounted/unmounted by the parent's `if showControls`), so this
        // fires fresh every time they reappear. Needed because the parent
        // ZStack stops being focusable once controls are visible (see
        // TVPlayerView) - without explicitly claiming focus here, nothing
        // would, and arrow keys would have no focused control to move from.
        .onAppear {
            Log.player.debug("TVPlaybackControlsView appeared, claiming focus -> playPause")
            focusedControl = .playPause
        }
        .onChange(of: focusedControl) { _, newValue in
            Log.player.debug("focusedControl changed -> \(String(describing: newValue), privacy: .public)")
        }
    }
}
