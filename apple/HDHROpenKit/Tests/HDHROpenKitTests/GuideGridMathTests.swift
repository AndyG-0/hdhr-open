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
}
