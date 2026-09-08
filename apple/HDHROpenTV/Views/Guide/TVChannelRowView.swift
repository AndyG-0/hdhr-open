import HDHROpenKit
import SwiftUI

public struct TVChannelRowView: View {
    let channel: HDHomeRunChannel
    let airings: [HDHomeRunGuideEntry]
    let isFavorite: Bool
    let onSelectAiring: (HDHomeRunGuideEntry) -> Void
    let onTuneChannel: () -> Void
    let onToggleFavorite: () -> Void

    @FocusState private var isChannelHeaderFocused: Bool

    public init(
        channel: HDHomeRunChannel,
        airings: [HDHomeRunGuideEntry],
        isFavorite: Bool,
        onSelectAiring: @escaping (HDHomeRunGuideEntry) -> Void,
        onTuneChannel: @escaping () -> Void,
        onToggleFavorite: @escaping () -> Void
    ) {
        self.channel = channel
        self.airings = airings
        self.isFavorite = isFavorite
        self.onSelectAiring = onSelectAiring
        self.onTuneChannel = onTuneChannel
        self.onToggleFavorite = onToggleFavorite
    }

    public var body: some View {
        HStack(alignment: .center, spacing: 16) {
            // Channel Header Pill
            Button(action: onTuneChannel) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(channel.channelNumber)
                            .font(.system(size: 24, weight: .bold, design: .rounded))
                            .foregroundColor(Theme.textPrimary)

                        if isFavorite {
                            Image(systemName: "star.fill")
                                .foregroundColor(.yellow)
                                .font(.caption)
                        }

                        if channel.isHD {
                            Text("HD")
                                .font(.system(size: 10, weight: .bold))
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(3)
                        }
                    }

                    Text(channel.name)
                        .font(.caption)
                        .foregroundColor(Theme.textSecondary)
                        .lineLimit(1)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .frame(width: 180, height: 140)
                .background(Theme.appSurface)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(isChannelHeaderFocused ? Theme.textPrimary : Color.clear, lineWidth: 4)
                )
                .scaleEffect(isChannelHeaderFocused ? 1.05 : 1.0)
            }
            .buttonStyle(.plain)
            .focused($isChannelHeaderFocused)
            .contextMenu {
                Button(action: onToggleFavorite) {
                    Label(isFavorite ? "Remove from Favorites" : "Add to Favorites", systemImage: isFavorite ? "star.slash" : "star")
                }
                Button(action: onTuneChannel) {
                    Label("Watch Live", systemImage: "play.fill")
                }
            }

            // Airings Horizontal Scroll
            ScrollViewReader { proxy in
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 14) {
                        if airings.isEmpty {
                            Text("No schedule information")
                                .font(.callout)
                                .foregroundColor(.secondary)
                                .frame(width: 240, height: 140)
                        } else {
                            ForEach(airings) { airing in
                                TVProgramCardView(airing: airing, isFavorite: isFavorite) {
                                    onSelectAiring(airing)
                                }
                                .id(airing.id)
                            }
                        }
                    }
                    .padding(.vertical, 8)
                }
                .onAppear { scrollToNow(proxy: proxy) }
                .onReceive(Timer.publish(every: 30, on: .main, in: .common).autoconnect()) { _ in
                    scrollToNow(proxy: proxy)
                }
            }
        }
    }

    /// Scrolls the row so the currently-airing program (or, if none is airing
    /// right now, the nearest upcoming one) sits at the leading edge. Without
    /// this the row's natural sort order leaves up to ~6h of already-ended
    /// airings (an intentional server-side lookback, matched by the web
    /// grid's own scroll-back range) sitting to the left of "now".
    private func scrollToNow(proxy: ScrollViewProxy) {
        guard !airings.isEmpty else { return }
        let now = Date().timeIntervalSince1970
        let target = airings.first(where: { $0.isCurrentlyAiring(at: now) })
            ?? airings.first(where: { ($0.start ?? .greatestFiniteMagnitude) > now })
        guard let target else { return }
        withAnimation(.none) {
            proxy.scrollTo(target.id, anchor: .leading)
        }
    }
}
