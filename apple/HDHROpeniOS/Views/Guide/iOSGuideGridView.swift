import SwiftUI
import HDHROpenKit

/// Pure layout math mirroring the web guide grid (frontend/src/lib/components/details/HDHomeRunGuideGrid.svelte).
/// Kept free of any HDHROpenKit changes -- this is view-layer-only logic.
enum GuideGridMath {
    static let pxPerSecond: CGFloat = 4.0 / 60.0
    static let minCellWidth: CGFloat = 90
    static let hourSeconds: TimeInterval = 3600
    static let daySeconds: TimeInterval = 86400

    static func windowBounds(
        nowSeconds: TimeInterval,
        fullGuide: [HDHomeRunFullGuideChannel]
    ) -> (start: TimeInterval, end: TimeInterval) {
        var minStart = nowSeconds - 2 * hourSeconds
        var maxEnd = nowSeconds + 4 * hourSeconds
        let earliestAllowed = nowSeconds - 6 * hourSeconds
        let latestAllowed = nowSeconds + 48 * hourSeconds

        for entry in fullGuide {
            for airing in entry.airings {
                if let start = airing.start { minStart = min(minStart, start) }
                if let end = airing.end { maxEnd = max(maxEnd, end) }
            }
        }

        minStart = max(minStart, earliestAllowed)
        maxEnd = min(maxEnd, latestAllowed)
        let start = (minStart / 1800).rounded(.down) * 1800
        return (start, maxEnd)
    }

    struct CellLayout: Identifiable {
        var id: String { airing.id }
        let airing: HDHomeRunGuideEntry
        let left: CGFloat
        let width: CGFloat
    }

    static func cellLayouts(
        airings: [HDHomeRunGuideEntry],
        windowStart: TimeInterval,
        windowEnd: TimeInterval
    ) -> [CellLayout] {
        var layouts: [CellLayout] = []
        for airing in airings {
            guard let airingStart = airing.start, let airingEnd = airing.end else { continue }
            let start = max(airingStart, windowStart)
            let end = min(airingEnd, windowEnd)
            guard end > start else { continue }
            let left = CGFloat(start - windowStart) * pxPerSecond
            let width = max(CGFloat(end - start) * pxPerSecond, minCellWidth)
            layouts.append(CellLayout(airing: airing, left: left, width: width))
        }
        return layouts
    }

    struct HourMark: Identifiable {
        var id: TimeInterval { seconds }
        let seconds: TimeInterval
        let left: CGFloat
        let label: String
    }

    struct DayMark: Identifiable {
        var id: TimeInterval { start }
        let start: TimeInterval
        let left: CGFloat
        let width: CGFloat
        let label: String
    }

    private static let hourFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h a"
        return f
    }()

    private static let weekdayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEEE"
        return f
    }()

    static func hourMarks(windowStart: TimeInterval, windowEnd: TimeInterval) -> [HourMark] {
        var marks: [HourMark] = []
        let calendar = Calendar.current
        let startDate = Date(timeIntervalSince1970: windowStart)
        let endDate = Date(timeIntervalSince1970: windowEnd)
        guard var cursor = calendar.dateInterval(of: .hour, for: startDate)?.start else { return marks }

        while cursor < endDate {
            let seconds = cursor.timeIntervalSince1970
            if seconds >= windowStart {
                let left = CGFloat(seconds - windowStart) * pxPerSecond
                marks.append(HourMark(seconds: seconds, left: left, label: hourFormatter.string(from: cursor)))
            }
            guard let next = calendar.date(byAdding: .hour, value: 1, to: cursor) else { break }
            cursor = next
        }
        return marks
    }

    static func dayMarks(windowStart: TimeInterval, windowEnd: TimeInterval) -> [DayMark] {
        var marks: [DayMark] = []
        let calendar = Calendar.current
        let endDate = Date(timeIntervalSince1970: windowEnd)
        guard var dayStart = calendar.dateInterval(of: .day, for: Date(timeIntervalSince1970: windowStart))?.start else {
            return marks
        }
        let today = calendar.startOfDay(for: Date())

        while dayStart < endDate {
            guard let dayEnd = calendar.date(byAdding: .day, value: 1, to: dayStart) else { break }
            let segStart = max(dayStart.timeIntervalSince1970, windowStart)
            let segEnd = min(dayEnd.timeIntervalSince1970, windowEnd)
            if segEnd > segStart {
                let left = CGFloat(segStart - windowStart) * pxPerSecond
                let width = CGFloat(segEnd - segStart) * pxPerSecond
                let label: String
                if calendar.isDate(dayStart, inSameDayAs: today) {
                    label = "Today"
                } else if let tomorrow = calendar.date(byAdding: .day, value: 1, to: today),
                          calendar.isDate(dayStart, inSameDayAs: tomorrow) {
                    label = "Tomorrow"
                } else {
                    label = weekdayFormatter.string(from: dayStart)
                }
                marks.append(DayMark(start: dayStart.timeIntervalSince1970, left: left, width: width, label: label))
            }
            dayStart = dayEnd
        }
        return marks
    }
}

/// iOS EPG grid: channels as rows with a fixed leading channel column, a horizontally scrollable
/// per-channel track of time-positioned program cells, a shared hour/day ruler, and a live "now" line.
/// Mirrors the web grid's layout math (see GuideGridMath); tap-to-select is used throughout
/// instead of tvOS focus navigation (see `airingCell` for why `.contextMenu` was dropped there).
///
/// The ruler does not scroll in lockstep with the program track: keeping them in sync was prototyped
/// using a `GeometryReader`/`PreferenceKey` pair, but that reproduced a continuous-CPU-pegging bug
/// seen elsewhere in this view. Dropped rather than worked around; the ruler still shows the correct
/// initial window, and users can scroll horizontally manually. Auto-scroll-to-"now" on initial load
/// (and on every reload) IS implemented, but via `.defaultScrollAnchor` rather than `ScrollViewReader`,
/// which was also prototyped for this and independently reproduced the same CPU-pegging bug.
public struct iOSGuideGridView: View {
    let channels: [HDHomeRunChannel]
    let onSelectAiring: (HDHomeRunChannel, HDHomeRunGuideEntry) -> Void
    let onTuneChannel: (HDHomeRunChannel) -> Void

    @EnvironmentObject private var guideViewModel: GuideViewModel

    @State private var nowSeconds: TimeInterval = Date().timeIntervalSince1970
    @State private var scrollAnchor: UnitPoint = .leading
    @State private var hasAutoScrolledToNow = false
    @State private var scrollOffsetX: CGFloat = 0

    private let channelColumnWidth: CGFloat = 92
    private let rowHeight: CGFloat = 64
    private let dayRowHeight: CGFloat = 20
    private let hourRowHeight: CGFloat = 22
    private var rulerHeight: CGFloat { dayRowHeight + hourRowHeight }

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

    /// One-shot: the first time real guide data has settled after a load, bias `defaultScrollAnchor`
    /// so the horizontal track's initial layout centers near "now" instead of the leading edge
    /// (~now-6h). Mirrors the web client's one-time `scrollEl.scrollLeft = nowLeft - 60`
    /// (HDHomeRunGuideGrid.svelte), but via `.defaultScrollAnchor` instead of `ScrollViewReader`,
    /// which this view cannot use -- see the doc comment above `iOSGuideGridView`.
    ///
    /// The anchor is reset back to `.leading` shortly after the jump takes effect so later,
    /// unrelated content-size changes (e.g. the 30s timer nudging `windowBounds`) don't re-consult
    /// a stale "now" fraction and fight any manual scrolling the user has since done.
    private func maybeScrollToNow() {
        guard !hasAutoScrolledToNow, !guideViewModel.isLoading, !guideViewModel.fullGuide.isEmpty else { return }
        hasAutoScrolledToNow = true

        let span = windowBounds.end - windowBounds.start
        guard span > 0 else { return }
        let fraction = min(max((nowSeconds - windowBounds.start) / span, 0), 1)
        scrollAnchor = UnitPoint(x: fraction, y: 0)

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 500_000_000)
            scrollAnchor = .leading
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
            if newValue { hasAutoScrolledToNow = false }
            nowSeconds = Date().timeIntervalSince1970
            recomputeWindowBounds()
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
                .defaultScrollAnchor(scrollAnchor)
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
