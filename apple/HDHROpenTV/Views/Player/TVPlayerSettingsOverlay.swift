import HDHROpenKit
import SwiftUI

public struct TVPlayerSettingsOverlay: View {
    @ObservedObject var playerViewModel: PlayerViewModel
    let onDismiss: () -> Void

    @FocusState private var focusedElement: SettingsFocus?

    private var playerEngine: PlayerEngine {
        playerViewModel.playerEngine
    }

    private enum SettingsFocus: Hashable {
        case close
        case track(Int)
        case airplay
    }

    public init(playerViewModel: PlayerViewModel, onDismiss: @escaping () -> Void) {
        self.playerViewModel = playerViewModel
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.8).ignoresSafeArea()

            VStack(alignment: .leading, spacing: 24) {
                HStack {
                    Text("Audio & Stream Options")
                        .font(.title2.bold())
                        .foregroundColor(Theme.textPrimary)
                    Spacer()
                    Button("Close", action: onDismiss)
                        .focused($focusedElement, equals: .close)
                }

                Divider().background(Theme.appBorder)

                // Audio Tracks
                VStack(alignment: .leading, spacing: 12) {
                    Text("Audio Tracks")
                        .font(.headline)
                        .foregroundColor(.secondary)

                    if playerEngine.availableAudioTracks.isEmpty {
                        Text("Default Audio Track")
                            .font(.subheadline)
                            .foregroundColor(Theme.textSecondary)
                    } else {
                        ForEach(playerEngine.availableAudioTracks) { track in
                            let isSelected = playerEngine.currentAudioTrack?.index == track.index
                            Button(action: {
                                Task { await playerViewModel.selectAudioTrack(track) }
                            }) {
                                HStack {
                                    Text(track.displayLabel)
                                        .font(.body)
                                    Spacer()
                                    if isSelected {
                                        Image(systemName: "checkmark")
                                            .foregroundColor(.blue)
                                    }
                                }
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .background(isSelected ? Theme.accentSubtle : Theme.appSurfaceVariant)
                                .cornerRadius(8)
                            }
                            .focused($focusedElement, equals: .track(track.index))
                        }
                    }
                }

                // AirPlay - placed inside this settings overlay rather than the
                // always-visible control bar, since AVRoutePickerView is itself
                // focusable and this codebase deliberately avoids AVKit's own
                // focusable chrome competing with this view's hand-rolled
                // Siri Remote focus handling (see PlayerLayerView's doc comment).
                VStack(alignment: .leading, spacing: 8) {
                    Text("AirPlay")
                        .font(.headline)
                        .foregroundColor(.secondary)

                    AirPlayRoutePickerView(tintColor: .white)
                        .frame(width: 44, height: 44)
                        .focused($focusedElement, equals: .airplay)
                }

                // Playback Mode
                VStack(alignment: .leading, spacing: 8) {
                    Text("Playback")
                        .font(.headline)
                        .foregroundColor(.secondary)

                    Label(playerViewModel.playbackModeLabel, systemImage: playerViewModel.playbackMode == .direct ? "bolt.fill" : "server.rack")
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)

                    if let bitrate = playerEngine.observedBitrate {
                        Label(String(format: "%.1f Mbps", bitrate / 1_000_000), systemImage: "speedometer")
                            .font(.subheadline)
                            .foregroundColor(Theme.textSecondary)
                    }
                }

                // Video Specs
                if let specs = playerEngine.videoSpecs {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Stream Details")
                            .font(.headline)
                            .foregroundColor(.secondary)

                        HStack(spacing: 24) {
                            if let w = specs.width, let h = specs.height {
                                Label("\(w)x\(h)", systemImage: "aspectratio")
                            }
                            if let fps = specs.fps {
                                Label(String(format: "%.0f fps", fps), systemImage: "speedometer")
                            }
                            if let cod = specs.codec {
                                Label(cod.uppercased(), systemImage: "film")
                            }
                        }
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)
                    }
                }
            }
            .padding(40)
            .frame(maxWidth: 700)
            .background(Theme.appSurface)
            .cornerRadius(20)
        }
        // Mirrors TVPlaybackControlsView's onAppear focus claim - this overlay
        // is added as a ZStack sibling on top of the still-mounted player
        // controls (not a replacement for them), so nothing moves focus onto
        // it automatically; without this, focus (and arrow-key navigation)
        // stays on whichever control button was focused before the overlay
        // appeared.
        .onAppear {
            if let current = playerEngine.currentAudioTrack {
                focusedElement = .track(current.index)
            } else if let first = playerEngine.availableAudioTracks.first {
                focusedElement = .track(first.index)
            } else {
                focusedElement = .close
            }
        }
    }
}
