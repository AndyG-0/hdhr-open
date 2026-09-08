import XCTest
@testable import HDHROpenKit

final class GuideGridMathTests: XCTestCase {
    func testTargetScrollOffsetWithLeadingPadding() {
        let windowStart: TimeInterval = 1_000_000
        // 2 hours later = 7200 seconds later
        let nowSeconds: TimeInterval = windowStart + 7200
        // pxPerSecond = 4.0 / 60.0 = 1/15
        // nowLeft = 7200 * (4.0 / 60.0) = 480.0
        // With leadingPadding = 60: 480 - 60 = 420.0
        let offset = GuideGridMath.targetScrollOffset(
            nowSeconds: nowSeconds,
            windowStart: windowStart,
            leadingPadding: 60
        )
        XCTAssertEqual(offset, 420.0, accuracy: 0.001)
    }

    func testTargetScrollOffsetClampsToZero() {
        let windowStart: TimeInterval = 1_000_000
        // nowSeconds is only 300s (5 minutes) after windowStart
        // nowLeft = 300 * (4/60) = 20.0
        // 20.0 - 60.0 = -40.0 -> clamped to 0
        let offset = GuideGridMath.targetScrollOffset(
            nowSeconds: windowStart + 300,
            windowStart: windowStart,
            leadingPadding: 60
        )
        XCTAssertEqual(offset, 0)
    }

    func testWindowBoundsFallback() {
        let now: TimeInterval = 100_000
        let bounds = GuideGridMath.windowBounds(nowSeconds: now, fullGuide: [])
        // minStart = now - 2 * 3600 = 100_000 - 7200 = 92800
        // start rounded down to 1800: (92800 / 1800).rounded(.down) * 1800 = 51 * 1800 = 91800
        XCTAssertLessThanOrEqual(bounds.start, now - 2 * 3600)
        XCTAssertEqual(bounds.start.truncatingRemainder(dividingBy: 1800), 0)
        XCTAssertGreaterThanOrEqual(bounds.end, now + 4 * 3600)
    }

    func testWindowBoundsEarliestAllowedClamping() {
        let now: TimeInterval = 1_000_000
        let veryOldAiring = HDHomeRunGuideEntry(
            title: "Old Show",
            start: now - 100 * 3600, // 100 hours ago
            end: now - 99 * 3600
        )
        let channel = HDHomeRunFullGuideChannel(
            channelNumber: "1.1",
            channelName: "Channel 1",
            airings: [veryOldAiring]
        )
        let bounds = GuideGridMath.windowBounds(nowSeconds: now, fullGuide: [channel])
        // earliestAllowed = now - 6 * 3600
        // start should be clamped to at least earliestAllowed rounded down
        let earliestRounded = ((now - 6 * 3600) / 1800).rounded(.down) * 1800
        XCTAssertGreaterThanOrEqual(bounds.start, earliestRounded)
    }

    func testWindowBoundsLatestAllowedClamping() {
        let now: TimeInterval = 1_000_000
        let farFutureAiring = HDHomeRunGuideEntry(
            title: "Future Show",
            start: now + 100 * 3600,
            end: now + 101 * 3600
        )
        let channel = HDHomeRunFullGuideChannel(channelNumber: "1.1", channelName: "Channel 1", airings: [farFutureAiring])
        let bounds = GuideGridMath.windowBounds(nowSeconds: now, fullGuide: [channel])
        let latestAllowed = now + 48 * 3600
        XCTAssertLessThanOrEqual(bounds.end, latestAllowed)
    }

    func testCellLayoutsClipsToWindowAndEnforcesMinWidth() {
        let windowStart: TimeInterval = 0
        let windowEnd: TimeInterval = 7200
        let airings = [
            // Fully inside window, short duration -> clamped to minCellWidth.
            HDHomeRunGuideEntry(title: "Short", start: 0, end: 60),
            // Starts before window, ends inside -> clipped to windowStart.
            HDHomeRunGuideEntry(title: "ClippedStart", start: -3600, end: 1800),
            // Missing start/end -> skipped entirely.
            HDHomeRunGuideEntry(title: "NoTimes"),
            // Fully outside window -> skipped (end <= start after clamping).
            HDHomeRunGuideEntry(title: "OutOfRange", start: 10000, end: 11000)
        ]

        let layouts = GuideGridMath.cellLayouts(airings: airings, windowStart: windowStart, windowEnd: windowEnd)

        XCTAssertEqual(layouts.count, 2)
        XCTAssertEqual(layouts[0].airing.title, "Short")
        XCTAssertEqual(layouts[0].left, 0)
        XCTAssertEqual(layouts[0].width, GuideGridMath.minCellWidth)
        XCTAssertEqual(layouts[0].id, layouts[0].airing.id)

        XCTAssertEqual(layouts[1].airing.title, "ClippedStart")
        XCTAssertEqual(layouts[1].left, 0)
    }

    func testHourMarksSpanWindow() throws {
        let calendar = Calendar.current
        let windowStart = try XCTUnwrap(calendar.dateInterval(of: .hour, for: Date(timeIntervalSince1970: 1_700_000_000))?.start
            .timeIntervalSince1970)
        let windowEnd = windowStart + 3 * GuideGridMath.hourSeconds

        let marks = GuideGridMath.hourMarks(windowStart: windowStart, windowEnd: windowEnd)

        XCTAssertEqual(marks.count, 3)
        XCTAssertEqual(marks.first?.seconds, windowStart)
        XCTAssertEqual(marks.first?.id, marks.first?.seconds)
        XCTAssertFalse(marks[0].label.isEmpty)
        // Marks should be strictly increasing in left offset.
        XCTAssertLessThan(marks[0].left, marks[1].left)
        XCTAssertLessThan(marks[1].left, marks[2].left)
    }

    func testDayMarksLabelsTodayTomorrowAndWeekday() {
        let calendar = Calendar.current
        let todayStart = calendar.startOfDay(for: Date()).timeIntervalSince1970
        let windowStart = todayStart
        let windowEnd = todayStart + 3 * GuideGridMath.daySeconds

        let marks = GuideGridMath.dayMarks(windowStart: windowStart, windowEnd: windowEnd)

        XCTAssertEqual(marks.count, 3)
        XCTAssertEqual(marks[0].label, "Today")
        XCTAssertEqual(marks[1].label, "Tomorrow")
        XCTAssertFalse(marks[2].label.isEmpty)
        XCTAssertNotEqual(marks[2].label, "Today")
        XCTAssertNotEqual(marks[2].label, "Tomorrow")
        XCTAssertEqual(marks[0].id, marks[0].start)
        XCTAssertGreaterThan(marks[0].width, 0)
    }

    func testDayMarksClipsFirstAndLastSegmentToWindow() {
        let calendar = Calendar.current
        let todayStart = calendar.startOfDay(for: Date()).timeIntervalSince1970
        // Window starts 6 hours into today and ends 6 hours into tomorrow.
        let windowStart = todayStart + 6 * GuideGridMath.hourSeconds
        let windowEnd = todayStart + GuideGridMath.daySeconds + 6 * GuideGridMath.hourSeconds

        let marks = GuideGridMath.dayMarks(windowStart: windowStart, windowEnd: windowEnd)

        XCTAssertEqual(marks.count, 2)
        XCTAssertEqual(marks[0].left, 0)
        XCTAssertEqual(marks[0].width, 18 * GuideGridMath.hourSeconds * GuideGridMath.pxPerSecond, accuracy: 0.01)
    }
}
