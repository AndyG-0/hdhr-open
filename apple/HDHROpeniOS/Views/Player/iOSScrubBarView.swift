import HDHROpenKit
import SwiftUI

public struct iOSScrubBarView: View {
    let currentTime: Double
    let duration: Double
    let isLive: Bool
    let isSeekable: Bool
    let thumbnailCues: [ThumbnailCue]
    let spriteURL: URL?
    let onScrubbingChanged: ((Bool) -> Void)?
    let onSeek: (Double) -> Void

    @State private var isDragging = false
    @State private var dragProgress: Double = 0

    public init(
        currentTime: Double,
        duration: Double,
        isLive: Bool,
        isSeekable: Bool,
        thumbnailCues: [ThumbnailCue] = [],
        spriteURL: URL? = nil,
        onScrubbingChanged: ((Bool) -> Void)? = nil,
        onSeek: @escaping (Double) -> Void
    ) {
        self.currentTime = currentTime
        self.duration = duration
        self.isLive = isLive
        self.isSeekable = isSeekable
        self.thumbnailCues = thumbnailCues
        self.spriteURL = spriteURL
        self.onScrubbingChanged = onScrubbingChanged
        self.onSeek = onSeek
    }

    private var currentProgress: Double {
        if isDragging {
            return dragProgress
        }
        guard duration > 0 else { return 0 }
        return min(1.0, max(0.0, currentTime / duration))
    }

    private var activeTime: Double {
        if isDragging {
            return dragProgress * duration
        }
        return currentTime
    }

    public var body: some View {
        VStack(spacing: 6) {
            // Drag Thumbnail / Time Preview
            if isDragging {
                VStack(spacing: 4) {
                    if let cue = thumbnailCues.first(where: { $0.contains(time: activeTime) }),
                       let url = spriteURL
                    {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        } placeholder: {
                            Color.black
                        }
                        .frame(width: CGFloat(cue.width), height: CGFloat(cue.height))
                        .clipped()
                        .cornerRadius(6)
                        .overlay(
                            RoundedRectangle(cornerRadius: 6)
                                .stroke(Color.white, lineWidth: 1.5)
                        )
                    }

                    Text(TimeFormatting.formatDuration(seconds: activeTime))
                        .font(.caption2.bold())
                        .foregroundColor(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.black.opacity(0.8))
                        .cornerRadius(4)
                }
            }

            // Slider Track
            GeometryReader { geo in
                let knobDiameter: CGFloat = isDragging ? 18 : 14
                let knobX = min(
                    max(0, geo.size.width * CGFloat(currentProgress) - knobDiameter / 2),
                    max(0, geo.size.width - knobDiameter)
                )

                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(Color.clear)
                        .frame(height: 44)

                    Capsule()
                        .fill(Color.white.opacity(0.3))
                        .frame(height: 6)

                    Capsule()
                        .fill(isLive ? Color.red : Color.blue)
                        .frame(width: max(0, geo.size.width * CGFloat(currentProgress)), height: 6)

                    if isSeekable, duration > 0 {
                        Circle()
                            .fill(Color.white)
                            .shadow(color: Color.black.opacity(0.4), radius: 3, x: 0, y: 1)
                            .frame(width: knobDiameter, height: knobDiameter)
                            .offset(x: knobX)
                            .animation(.interactiveSpring(response: 0.2, dampingFraction: 0.8), value: isDragging)
                    }
                }
                .frame(height: 44)
                .contentShape(Rectangle())
                .highPriorityGesture(
                    DragGesture(minimumDistance: 0)
                        .onChanged { value in
                            guard isSeekable, duration > 0 else { return }
                            if !isDragging {
                                isDragging = true
                                onScrubbingChanged?(true)
                            }
                            let progress = max(0.0, min(1.0, value.location.x / geo.size.width))
                            dragProgress = progress
                        }
                        .onEnded { value in
                            guard isSeekable, duration > 0 else { return }
                            let progress = max(0.0, min(1.0, value.location.x / geo.size.width))
                            isDragging = false
                            onScrubbingChanged?(false)
                            onSeek(progress * duration)
                        }
                )
            }
            .frame(height: 44)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Playback position")
            .accessibilityValue(TimeFormatting.formatDuration(seconds: activeTime))
            .accessibilityAdjustableAction { direction in
                guard isSeekable, duration > 0 else { return }
                let step: Double = 10
                switch direction {
                case .increment:
                    onSeek(min(duration, currentTime + step))
                case .decrement:
                    onSeek(max(0, currentTime - step))
                @unknown default:
                    break
                }
            }

            // Timestamps
            HStack {
                Text(TimeFormatting.formatDuration(seconds: activeTime))
                    .font(.caption2.monospacedDigit())
                    .foregroundColor(.white.opacity(0.8))

                Spacer()

                if isLive {
                    HStack(spacing: 4) {
                        Circle().fill(Color.red).frame(width: 6, height: 6)
                        Text("LIVE").font(.caption2.bold()).foregroundColor(.white)
                    }
                } else if duration > 0 {
                    Text(TimeFormatting.formatDuration(seconds: duration))
                        .font(.caption2.monospacedDigit())
                        .foregroundColor(.white.opacity(0.8))
                }
            }
        }
    }
}
