import SwiftUI
import HDHROpenKit

public struct TVScrubBarView: View {
    let currentTime: Double
    let duration: Double
    let isLive: Bool
    let isSeekable: Bool
    let thumbnailCues: [ThumbnailCue]
    let spriteURL: URL?
    let onSeek: (Double) -> Void

    @State private var scrubTime: Double?

    public init(
        currentTime: Double,
        duration: Double,
        isLive: Bool,
        isSeekable: Bool,
        thumbnailCues: [ThumbnailCue] = [],
        spriteURL: URL? = nil,
        onSeek: @escaping (Double) -> Void
    ) {
        self.currentTime = currentTime
        self.duration = duration
        self.isLive = isLive
        self.isSeekable = isSeekable
        self.thumbnailCues = thumbnailCues
        self.spriteURL = spriteURL
        self.onSeek = onSeek
    }

    private var activeTime: Double {
        scrubTime ?? currentTime
    }

    private var progress: Double {
        guard duration > 0 else { return 0 }
        return min(1.0, max(0.0, activeTime / duration))
    }

    public var body: some View {
        VStack(spacing: 8) {
            // Thumbnail preview box when scrubbing
            if let targetTime = scrubTime, let cue = thumbnailCues.first(where: { $0.contains(time: targetTime) }) {
                VStack(spacing: 4) {
                    if let url = spriteURL {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        } placeholder: {
                            Color.black
                        }
                        .frame(width: CGFloat(cue.width), height: CGFloat(cue.height))
                        .clipped()
                        .cornerRadius(8)
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.white, lineWidth: 2)
                        )
                    }

                    Text(TimeFormatting.formatDuration(seconds: targetTime))
                        .font(.caption2.bold())
                        .foregroundColor(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.black.opacity(0.8))
                        .cornerRadius(4)
                }
                .transition(.opacity)
            }

            // Timeline bar
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    // Background track
                    Capsule()
                        .fill(Color.white.opacity(0.25))
                        .frame(height: 10)

                    // Fill progress
                    Capsule()
                        .fill(isLive ? Color.red : Color.blue)
                        .frame(width: max(0, geo.size.width * CGFloat(progress)), height: 10)
                }
            }
            .frame(height: 10)

            // Time labels
            HStack {
                Text(TimeFormatting.formatDuration(seconds: activeTime))
                    .font(.caption.monospacedDigit())
                    .foregroundColor(.white.opacity(0.8))

                Spacer()

                if isLive {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(Color.red)
                            .frame(width: 8, height: 8)
                        Text("LIVE")
                            .font(.caption.bold())
                            .foregroundColor(.white)
                    }
                } else if duration > 0 {
                    Text(TimeFormatting.formatDuration(seconds: duration))
                        .font(.caption.monospacedDigit())
                        .foregroundColor(.white.opacity(0.8))
                }
            }
        }
    }
}
