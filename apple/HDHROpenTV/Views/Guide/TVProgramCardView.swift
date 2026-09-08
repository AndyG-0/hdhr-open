import HDHROpenKit
import SwiftUI

public struct TVProgramCardView: View {
    let airing: HDHomeRunGuideEntry
    let isFavorite: Bool
    let isScheduled: Bool
    let onSelect: () -> Void

    @FocusState private var isFocused: Bool

    public init(
        airing: HDHomeRunGuideEntry,
        isFavorite: Bool = false,
        isScheduled: Bool = false,
        onSelect: @escaping () -> Void
    ) {
        self.airing = airing
        self.isFavorite = isFavorite
        self.isScheduled = isScheduled
        self.onSelect = onSelect
    }

    public var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .top) {
                    Text(airing.title)
                        .font(.headline)
                        .foregroundColor(Theme.textPrimary)
                        .lineLimit(1)

                    Spacer()

                    if isScheduled {
                        Image(systemName: "record.circle.fill")
                            .foregroundColor(.red)
                    }
                }

                if let ep = airing.episodeTitle, !ep.isEmpty {
                    Text(ep)
                        .font(.subheadline)
                        .foregroundColor(Theme.textSecondary)
                        .lineLimit(1)
                }

                Spacer()

                HStack {
                    Text(TimeFormatting.formatTimeRange(start: airing.start, end: airing.end))
                        .font(.caption2)
                        .foregroundColor(.secondary)

                    Spacer()

                    if airing.isCurrentlyAiring() {
                        Text("LIVE")
                            .font(.system(size: 10, weight: .bold))
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.red.opacity(0.8))
                            .foregroundColor(.white)
                            .cornerRadius(4)
                    }
                }
            }
            .padding(14)
            .frame(width: cardWidth, height: 140)
            .background(cardBackground)
            .cornerRadius(12)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isFocused ? Theme.textPrimary : Theme.appBorder, lineWidth: isFocused ? 4 : 1)
            )
            .scaleEffect(isFocused ? 1.05 : 1.0)
            .animation(.easeInOut(duration: 0.15), value: isFocused)
        }
        .buttonStyle(.plain)
        .focused($isFocused)
    }

    private var cardWidth: CGFloat {
        guard let dur = airing.durationSeconds else { return 240 }
        let minutes = dur / 60.0
        // Width proportional to airing duration (e.g. 30 mins = 220pt, 60 mins = 380pt)
        return max(200, min(CGFloat(minutes) * 6.5, 600))
    }

    private var cardBackground: some View {
        ZStack {
            Theme.appSurface
            if airing.isCurrentlyAiring() {
                GeometryReader { geo in
                    Rectangle()
                        .fill(Theme.accentSubtle)
                        .frame(width: geo.size.width * airing.progress)
                }
            }
        }
    }
}
