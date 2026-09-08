import CoreGraphics
import Foundation

/// Pure layout math mirroring the web guide grid (frontend/src/lib/components/details/HDHomeRunGuideGrid.svelte)
/// and Android client (android/app/src/main/kotlin/org/hdhropen/app/ui/screens/guide/GuideGridView.kt).
public enum GuideGridMath {
    public static let pxPerSecond: CGFloat = 4.0 / 60.0
    public static let minCellWidth: CGFloat = 90
    public static let hourSeconds: TimeInterval = 3600
    public static let daySeconds: TimeInterval = 86400

    public static func windowBounds(
        nowSeconds: TimeInterval,
        fullGuide: [HDHomeRunFullGuideChannel]
    ) -> (start: TimeInterval, end: TimeInterval) {
        var minStart = nowSeconds - 2 * hourSeconds
        var maxEnd = nowSeconds + 4 * hourSeconds
        let earliestAllowed = nowSeconds - 6 * hourSeconds
        let latestAllowed = nowSeconds + 48 * hourSeconds

        for entry in fullGuide {
            for airing in entry.airings {
                if let start = airing.start {
                    minStart = min(minStart, start)
                }
                if let end = airing.end {
                    maxEnd = max(maxEnd, end)
                }
            }
        }

        minStart = max(minStart, earliestAllowed)
        maxEnd = min(maxEnd, latestAllowed)
        let start = (minStart / 1800).rounded(.down) * 1800
        return (start, maxEnd)
    }

    /// Computes the horizontal scroll offset in points so "now" is offset by `leadingPadding`
    /// from the leading edge of the timeline track. Clamped to >= 0.
    /// Mirrors web `Math.max(nowLeft - 60, 0)` and Android `(nowLeft - 60.dp).coerceAtLeast(0)`.
    public static func targetScrollOffset(
        nowSeconds: TimeInterval,
        windowStart: TimeInterval,
        leadingPadding: CGFloat = 60
    ) -> CGFloat {
        let nowLeft = CGFloat(nowSeconds - windowStart) * pxPerSecond
        return max(nowLeft - leadingPadding, 0)
    }

    public struct CellLayout: Identifiable, Sendable {
        public var id: String {
            airing.id
        }

        public let airing: HDHomeRunGuideEntry
        public let left: CGFloat
        public let width: CGFloat

        public init(airing: HDHomeRunGuideEntry, left: CGFloat, width: CGFloat) {
            self.airing = airing
            self.left = left
            self.width = width
        }
    }

    public static func cellLayouts(
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

    public struct HourMark: Identifiable, Sendable {
        public var id: TimeInterval {
            seconds
        }

        public let seconds: TimeInterval
        public let left: CGFloat
        public let label: String

        public init(seconds: TimeInterval, left: CGFloat, label: String) {
            self.seconds = seconds
            self.left = left
            self.label = label
        }
    }

    public struct DayMark: Identifiable, Sendable {
        public var id: TimeInterval {
            start
        }

        public let start: TimeInterval
        public let left: CGFloat
        public let width: CGFloat
        public let label: String

        public init(start: TimeInterval, left: CGFloat, width: CGFloat, label: String) {
            self.start = start
            self.left = left
            self.width = width
            self.label = label
        }
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

    public static func hourMarks(windowStart: TimeInterval, windowEnd: TimeInterval) -> [HourMark] {
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

    public static func dayMarks(windowStart: TimeInterval, windowEnd: TimeInterval) -> [DayMark] {
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
                let label: String = if calendar.isDate(dayStart, inSameDayAs: today) {
                    "Today"
                } else if let tomorrow = calendar.date(byAdding: .day, value: 1, to: today),
                          calendar.isDate(dayStart, inSameDayAs: tomorrow)
                {
                    "Tomorrow"
                } else {
                    weekdayFormatter.string(from: dayStart)
                }
                marks.append(DayMark(start: dayStart.timeIntervalSince1970, left: left, width: width, label: label))
            }
            dayStart = dayEnd
        }
        return marks
    }
}
