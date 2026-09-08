import HDHROpenKit
import SwiftUI

/// iOS EPG grid: channels as rows with a fixed leading channel column, a horizontally scrollable
/// per-channel track of time-positioned program cells, a shared hour/day ruler, and a live "now" line.
/// Mirrors the web grid's layout math (see GuideGridMath); tap-to-select is used throughout
/// instead of tvOS focus navigation (see `airingCell` for why `.contextMenu` was dropped there).
///
/// The ruler does not scroll in lockstep with the program track: keeping them in sync was prototyped
/// using a `GeometryReader`/`PreferenceKey` pair, but that reproduced a continuous-CPU-pegging bug
/// seen elsewhere in this view. Instead, the ruler synchronizes horizontally via `scrollOffsetX` tracked
/// by `onScrollGeometryChange`. Auto-scroll-to-"now" on initial load (and on reload) is implemented
/// via iOS 18's native `ScrollPosition` (`.scrollPosition($scrollPosition)`), positioning "now" with a
/// 60pt leading inset to match the web and Android clients.
public struct iOSGuideGridView: View {
    let channels: [HDHomeRunChannel]
    let onSelectAiring: (HDHomeRunChannel, HDHomeRunGuideEntry) -> Void
    let onTuneChannel: (HDHomeRunChannel) -> Void

    @EnvironmentObject private var guideViewModel: GuideViewModel

    @State private var nowSeconds: TimeInterval = Date().timeIntervalSince1970
    @State private var scrollPosition = ScrollPosition()
    @State private var hasAutoScrolledToNow = false
    @State private var scrollOffsetX: CGFloat = 0

    private let channelColumnWidth: CGFloat = 92
    private let rowHeight: CGFloat = 64
    private let dayRowHeight: CGFloat = 20
    private let hourRowHeight: CGFloat = 22
    private var rulerHeight: CGFloat {
        dayRowHeight + hourRowHeight
    }

    private let nowTimer = Timer.publish(every: 30, on: .main, in: .common).autoconnect()

    public init(
        channels: [HDHomeRunChannel],
        onSelectAiring: @escaping (HDHomeRunChannel, HDHomeRunGuideEntry) -> Void,
        onTuneChannel: @escaping (HDHomeRunChannel) -> Void
    ) {
        self.channels = channels
        self.onSelectAiring = onSelectAiring
        self.onTuneChannel = onTuneChannel
    }

    /// Cached, not recomputed per-row: scanning the full guide to find the window bounds is O(all
    /// airings across all channels), and this is shared/global across every row in the grid, so it
    /// must only be recomputed when its inputs actually change (not on every SwiftUI render pass).
    @State private var windowBounds: (start: TimeInterval, end: TimeInterval) = (
        Date().timeIntervalSince1970 - 2 * GuideGridMath.hourSeconds,
        Date().timeIntervalSince1970 + 4 * GuideGridMath.hourSeconds
    )

    private var totalWidth: CGFloat {
        max(CGFloat(windowBounds.end - windowBounds.start) * GuideGridMath.pxPerSecond, 1)
    }

    private var nowLeft: CGFloat {
        CGFloat(nowSeconds - windowBounds.start) * GuideGridMath.pxPerSecond
    }

    private func recomputeWindowBounds() {
        windowBounds = GuideGridMath.windowBounds(nowSeconds: nowSeconds, fullGuide: guideViewModel.fullGuide)
        maybeScrollToNow()
    }

    /// One-shot per load: once real guide data has settled, scroll the horizontal track to "now"
    /// so the live indicator sits 60pt in from the left edge of the visible track.
    /// Mirrors the web client's `scrollEl.scrollLeft = nowLeft - 60` (HDHomeRunGuideGrid.svelte)
    /// and Android client's `horizontalScrollState.scrollTo(targetPx)` (GuideGridView.kt).
    private func maybeScrollToNow() {
        guard !hasAutoScrolledToNow, !guideViewModel.isLoading, !guideViewModel.fullGuide.isEmpty else { return }
        hasAutoScrolledToNow = true

        let targetX = GuideGridMath.targetScrollOffset(
            nowSeconds: nowSeconds,
            windowStart: windowBounds.start
        )
        scrollPosition.scrollTo(x: targetX)

        Task { @MainActor in
            // Allow SwiftUI a layout pass to settle updated content width, then re-apply
            // in case the initial attempt clamped against pre-load content size.
            try? await Task.sleep(nanoseconds: 50_000_000)
            scrollPosition.scrollTo(x: targetX)
        }
    }

    public var body: some View {
        GeometryReader { geo in
            VStack(spacing: 0) {
                rulerHeader(availableWidth: geo.size.width)
                Divider()
                channelRows(availableWidth: geo.size.width)
            }
        }
        .onAppear {
            nowSeconds = Date().timeIntervalSince1970
            recomputeWindowBounds()
        }
        .onReceive(nowTimer) { _ in
            nowSeconds = Date().timeIntervalSince1970
            recomputeWindowBounds()
        }
        .onChange(of: guideViewModel.isLoading) { _, newValue in
            if newValue {
                hasAutoScrolledToNow = false
            }
            nowSeconds = Date().timeIntervalSince1970
            recomputeWindowBounds()
        }
        .onChange(of: guideViewModel.fullGuide.isEmpty) { _, isEmpty in
            if !isEmpty {
                nowSeconds = Date().timeIntervalSince1970
                recomputeWindowBounds()
            }
        }
    }

    // MARK: - Ruler

    /// `availableWidth` (read once via a top-level `GeometryReader`, not tied to scroll position) bounds
    /// the track's width so the outer vertical `ScrollView` never sees content wider than the screen --
    /// without it, SwiftUI centers/clips the oversized content instead of pinning it to the leading edge.
    ///
    /// The ruler itself is not a `ScrollView` -- it's a static, clipped window onto the full timeline.
    /// Without correcting for that, it would always show `windowBounds.start` regardless of where the
    /// program track has scrolled to (e.g. after `maybeScrollToNow` auto-scrolls the track to "now" on
    /// load), which is exactly the "header time doesn't match the programs" bug this offset fixes. It
    /// reuses `scrollOffsetX` -- already tracked via `onScrollGeometryChange` for the sticky cell-title
    /// offset below -- rather than a `ScrollViewReader`/`PreferenceKey` sync, which previously reproduced
    /// the CPU-pegging bug described in the doc comment above `iOSGuideGridView`.
    private func rulerHeader(availableWidth: CGFloat) -> some View {
        let bounds = windowBounds
        let dayMarks = GuideGridMath.dayMarks(windowStart: bounds.start, windowEnd: bounds.end)
        let hourMarks = GuideGridMath.hourMarks(windowStart: bounds.start, windowEnd: bounds.end)
        let width = totalWidth
        let trackWidth = max(availableWidth - channelColumnWidth, 0)

        return HStack(spacing: 0) {
            Color(uiColor: .systemBackground)
                .frame(width: channelColumnWidth, height: rulerHeight)

            ZStack(alignment: .topLeading) {
                VStack(alignment: .leading, spacing: 0) {
                    ZStack(alignment: .topLeading) {
                        ForEach(dayMarks) { mark in
                            Text(mark.label)
                                .font(.caption2.bold())
                                .foregroundColor(.secondary)
                                .padding(.leading, 4)
                                .offset(x: mark.left)
                        }
                    }
                    .frame(width: width, height: dayRowHeight, alignment: .leading)

                    ZStack(alignment: .topLeading) {
                        ForEach(hourMarks) { mark in
                            Text(mark.label)
                                .font(.caption2)
                                .foregroundColor(.secondary)
                                .offset(x: mark.left + 4)
                        }
                    }
                    .frame(width: width, height: hourRowHeight, alignment: .leading)
                }
                .offset(x: -scrollOffsetX)
            }
            .frame(width: trackWidth, height: rulerHeight, alignment: .topLeading)
            .clipped()
        }
    }

    // MARK: - Rows

    private func channelRows(availableWidth: CGFloat) -> some View {
        let trackWidth = max(availableWidth - channelColumnWidth, 0)

        return ScrollView(.vertical, showsIndicators: true) {
            HStack(alignment: .top, spacing: 0) {
                LazyVStack(spacing: 0) {
                    ForEach(channels) { channel in
                        channelCell(channel)
                            .frame(width: channelColumnWidth, height: rowHeight)
                    }
                }
                .frame(width: channelColumnWidth)

                ScrollView(.horizontal, showsIndicators: false) {
                    LazyVStack(spacing: 0) {
                        ForEach(channels) { channel in
                            trackRow(channel)
                                .frame(width: totalWidth, height: rowHeight)
                        }
                    }
                }
                .frame(width: trackWidth)
                .scrollPosition($scrollPosition)
                .onScrollGeometryChange(for: CGFloat.self) { geometry in
                    geometry.contentOffset.x
                } action: { _, newValue in
                    scrollOffsetX = newValue
                }
            }
        }
    }

    private func channelCell(_ channel: HDHomeRunChannel) -> some View {
        let isFav = guideViewModel.favoriteChannels.contains(channel.channelNumber)
        return Button {
            onTuneChannel(channel)
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(channel.channelNumber)
                        .font(.caption.bold())
                        .foregroundColor(.blue)
                    if isFav {
                        Image(systemName: "star.fill")
                            .font(.system(size: 9))
                            .foregroundColor(.yellow)
                    }
                    if channel.isHD {
                        Text("HD")
                            .font(.system(size: 8, weight: .bold))
                            .padding(.horizontal, 3)
                            .padding(.vertical, 1)
                            .background(Color.blue.opacity(0.8))
                            .foregroundColor(.white)
                            .cornerRadius(3)
                    }
                }
                Text(channel.name)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
            .padding(.horizontal, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)
        .background(Color(uiColor: .systemBackground))
        .contextMenu {
            Button {
                Task { await guideViewModel.toggleFavorite(channelNumber: channel.channelNumber) }
            } label: {
                Label(isFav ? "Unfavorite" : "Favorite", systemImage: isFav ? "star.slash" : "star")
            }
        }
    }

    private func trackRow(_ channel: HDHomeRunChannel) -> some View {
        let airings = guideViewModel.getAirings(for: channel.channelNumber)
        let bounds = windowBounds
        let layouts = GuideGridMath.cellLayouts(airings: airings, windowStart: bounds.start, windowEnd: bounds.end)
        let showNowLine = nowSeconds >= bounds.start && nowSeconds <= bounds.end

        return ZStack(alignment: .topLeading) {
            Rectangle()
                .fill(Color(uiColor: .secondarySystemBackground))

            ForEach(layouts) { layout in
                airingCell(channel: channel, layout: layout)
                    .offset(x: layout.left)
            }

            if showNowLine {
                Rectangle()
                    .fill(Color.red)
                    .frame(width: 2)
                    .offset(x: nowLeft)
            }
        }
        .clipped()
    }

    /// No `.contextMenu` here: attaching native context menus to the many concurrently-visible
    /// airing cells inside this nested horizontal/vertical `ScrollView` pair triggers a continuous
    /// SwiftUI relayout loop that pegs the CPU (confirmed by bisection while debugging this view).
    /// The menu's only action duplicated the tap handler anyway, so it was dropped rather than kept
    /// behind a workaround -- tap-to-select (`onSelectAiring`) remains the only affordance here.
    ///
    /// Title and time range are built as ONE concatenated `Text` (via `+`) rather than two sibling
    /// `Text` views in a `VStack`: bisection also showed that 2+ sibling `Text` views repeated across
    /// the many concurrently-rendered cells here independently pegs the CPU, while a single `Text`
    /// (even concatenated from styled segments) does not. A trailing `Image` badge alongside that one
    /// `Text` is unaffected, so the live/record indicators are rendered as `Image`, not `Text`.
    ///
    /// The title/time block is offset by `stickyOffset` -- derived from `scrollOffsetX` (via
    /// `onScrollGeometryChange` on the horizontal track, iOS 18+) -- so it follows the visible left
    /// edge of the cell as the row scrolls, matching the web client's `position: sticky` cell-title/
    /// cell-time (HDHomeRunGuideGrid.svelte). Without this, a long-running show whose start has
    /// scrolled off-screen renders as a blank cell, since its title is anchored at the show's start,
    /// which may be hours to the left of the current viewport. The offset is clamped to the cell's own
    /// bounds and kept inside a `ZStack` (not a sibling `Text`) so it doesn't reintroduce the
    /// sibling-Text CPU-pegging bug above. Badges are NOT offset, matching the web client, where they
    /// scroll with the cell body.
    private func airingCell(channel: HDHomeRunChannel, layout: GuideGridMath.CellLayout) -> some View {
        let airing = layout.airing
        let isLive = airing.isCurrentlyAiring(at: nowSeconds)
        let hasRule = guideViewModel.findRule(for: channel.channelNumber, airing: airing) != nil
        let timeRange = TimeFormatting.formatTimeRange(start: airing.start, end: airing.end)

        let titleAndTime = Text(airing.title).font(.caption.bold()).foregroundColor(.primary)
            + Text("\n")
            + Text(timeRange).font(.caption2).foregroundColor(.secondary)

        let maxStickyOffset = max(layout.width - 96, 0)
        let stickyOffset = min(max(scrollOffsetX - layout.left, 0), maxStickyOffset)

        return Button {
            onSelectAiring(channel, airing)
        } label: {
            ZStack(alignment: .topLeading) {
                titleAndTime
                    .lineLimit(2)
                    .padding(6)
                    .offset(x: stickyOffset)

                if isLive || hasRule {
                    HStack(spacing: 4) {
                        if isLive {
                            Image(systemName: "dot.radiowaves.left.and.right")
                                .font(.system(size: 10))
                                .foregroundColor(.red)
                        }
                        if hasRule {
                            Image(systemName: "record.circle.fill")
                                .font(.system(size: 10))
                                .foregroundColor(.red)
                        }
                    }
                    .padding(6)
                    .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
            .frame(width: layout.width, height: rowHeight, alignment: .topLeading)
            .clipped()
        }
        .buttonStyle(.plain)
        .background(Color(uiColor: .secondarySystemGroupedBackground))
        .overlay(Rectangle().stroke(Color(uiColor: .separator), lineWidth: 0.5))
    }
}
