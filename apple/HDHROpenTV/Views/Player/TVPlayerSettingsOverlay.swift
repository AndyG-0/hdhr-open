import SwiftUI
import HDHROpenKit

public struct TVPlayerSettingsOverlay: View {
    @ObservedObject var playerEngine: PlayerEngine
    let onDismiss: () -> Void

    @FocusState private var focusedElement: SettingsFocus?

    private enum SettingsFocus: Hashable {
        case close
        case track(Int)
    }

    public init(playerEngine: PlayerEngine, onDismiss: @escaping () -> Void) {
        self.playerEngine = playerEngine
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.8).ignoresSafeArea()

            VStack(alignment: .leading, spacing: 24) {
                HStack {
                    Text("Audio & Stream Options")
                        .font(.title2.bold())
                        .foregroundColor(.white)
                    Spacer()
                    Button("Close", action: onDismiss)
                        .focused($focusedElement, equals: .close)
                }

                Divider().background(Color.gray)

                // Audio Tracks
                VStack(alignment: .leading, spacing: 12) {
                    Text("Audio Tracks")
                        .font(.headline)
                        .foregroundColor(.secondary)

                    if playerEngine.availableAudioTracks.isEmpty {
                        Text("Default Audio Track")
                            .font(.subheadline)
                            .foregroundColor(.gray)
                    } else {
                        ForEach(playerEngine.availableAudioTracks) { track in
                            let isSelected = playerEngine.currentAudioTrack?.index == track.index
                            Button(action: {
                                playerEngine.selectAudioTrack(track)
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
                                .background(isSelected ? Color.blue.opacity(0.2) : Color.white.opacity(0.05))
                                .cornerRadius(8)
                            }
                            .focused($focusedElement, equals: .track(track.index))
                        }
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
                        .foregroundColor(.white.opacity(0.8))
                    }
                }
            }
            .padding(40)
            .frame(maxWidth: 700)
            .background(Color(white: 0.12))
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
