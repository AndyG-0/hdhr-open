import HDHROpenKit
import SwiftUI

public struct iOSPlaybackInfoOverlay: View {
    @ObservedObject var playerViewModel: PlayerViewModel
    let onDismiss: () -> Void

    private var playerEngine: PlayerEngine {
        playerViewModel.playerEngine
    }

    public init(playerViewModel: PlayerViewModel, onDismiss: @escaping () -> Void) {
        self.playerViewModel = playerViewModel
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.6).ignoresSafeArea()
                .onTapGesture(perform: onDismiss)

            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Playback Info")
                        .font(.headline.bold())
                        .foregroundColor(.white)
                    Spacer()
                    Button(action: onDismiss) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title3)
                            .foregroundColor(.white.opacity(0.8))
                    }
                }

                infoRow(label: "Playback", value: playerViewModel.playbackModeLabel)

                if let specs = playerEngine.videoSpecs {
                    sectionHeading("Video")
                    if let codec = specs.codec {
                        infoRow(label: "Codec", value: codec.uppercased())
                    }
                    if let w = specs.width, let h = specs.height {
                        infoRow(label: "Resolution", value: "\(w)×\(h)")
                    }
                    if let fps = specs.fps {
                        infoRow(label: "Framerate", value: String(format: "%.0f fps", fps))
                    }
                }

                if !playerEngine.availableAudioTracks.isEmpty {
                    sectionHeading("Audio")
                    ForEach(playerEngine.availableAudioTracks) { track in
                        infoRow(
                            label: "Track \(track.index + 1)",
                            value: "\((track.codec ?? "?").uppercased()) · \(track.channels.map(String.init) ?? "?")ch"
                        )
                    }
                }

                if let bitrate = playerEngine.observedBitrate {
                    sectionHeading("Network")
                    infoRow(label: "Bitrate", value: String(format: "%.1f Mbps", bitrate / 1_000_000))
                }
            }
            .padding(20)
            .frame(maxWidth: 340)
            .background(Color(white: 0.12))
            .cornerRadius(16)
            .padding(32)
        }
    }

    private func sectionHeading(_ text: String) -> some View {
        Text(text)
            .font(.caption.bold())
            .foregroundColor(.white.opacity(0.6))
            .padding(.top, 4)
    }

    private func infoRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.7))
            Spacer()
            Text(value)
                .font(.subheadline)
                .foregroundColor(.white)
        }
    }
}
