import XCTest
@testable import HDHROpenKit

final class TimeFormattingTests: XCTestCase {
    // MARK: - Reference formatters (mirror production formatting settings so

    // assertions stay correct regardless of the machine's locale/timezone)

    private var referenceTimeFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter
    }

    private var referenceDayFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEE, MMM d"
        return formatter
    }

    // MARK: - formatTime

    func testFormatTimeNilReturnsEmptyString() {
        XCTAssertEqual(TimeFormatting.formatTime(nil), "")
    }

    func testFormatTimeZeroReturnsEmptyString() {
        XCTAssertEqual(TimeFormatting.formatTime(0), "")
    }

    func testFormatTimeNegativeReturnsEmptyString() {
        XCTAssertEqual(TimeFormatting.formatTime(-100), "")
    }

    func testFormatTimeValidTimestamp() {
        let ts: TimeInterval = 1_700_000_000
        let expected = referenceTimeFormatter.string(from: Date(timeIntervalSince1970: ts))
        XCTAssertEqual(TimeFormatting.formatTime(ts), expected)
    }

    func testFormatTimeVerySmallPositiveTimestamp() {
        // Just above the ts > 0 boundary.
        let ts: TimeInterval = 0.5
        let expected = referenceTimeFormatter.string(from: Date(timeIntervalSince1970: ts))
        XCTAssertEqual(TimeFormatting.formatTime(ts), expected)
        XCTAssertNotEqual(TimeFormatting.formatTime(ts), "")
    }

    // MARK: - formatTimeRange

    func testFormatTimeRangeNilStartReturnsEmptyString() {
        XCTAssertEqual(TimeFormatting.formatTimeRange(start: nil, end: 1_700_000_000), "")
    }

    func testFormatTimeRangeNilStartAndNilEndReturnsEmptyString() {
        XCTAssertEqual(TimeFormatting.formatTimeRange(start: nil, end: nil), "")
    }

    func testFormatTimeRangeNilEndReturnsOnlyStart() {
        let start: TimeInterval = 1_700_000_000
        let expected = TimeFormatting.formatTime(start)
        XCTAssertEqual(TimeFormatting.formatTimeRange(start: start, end: nil), expected)
        XCTAssertFalse(expected.isEmpty)
    }

    func testFormatTimeRangeBothPresent() {
        let start: TimeInterval = 1_700_000_000
        let end: TimeInterval = 1_700_003_600
        let expected = "\(TimeFormatting.formatTime(start)) \u{2013} \(TimeFormatting.formatTime(end))"
        XCTAssertEqual(TimeFormatting.formatTimeRange(start: start, end: end), expected)
    }

    // MARK: - formatDayDate

    func testFormatDayDateNilReturnsEmptyString() {
        XCTAssertEqual(TimeFormatting.formatDayDate(nil), "")
    }

    func testFormatDayDateZeroReturnsEmptyString() {
        XCTAssertEqual(TimeFormatting.formatDayDate(0), "")
    }

    func testFormatDayDateNegativeReturnsEmptyString() {
        XCTAssertEqual(TimeFormatting.formatDayDate(-1), "")
    }

    func testFormatDayDateValidTimestamp() {
        let ts: TimeInterval = 1_700_000_000
        let expected = referenceDayFormatter.string(from: Date(timeIntervalSince1970: ts))
        XCTAssertEqual(TimeFormatting.formatDayDate(ts), expected)
    }

    // MARK: - formatDuration

    func testFormatDurationZero() {
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 0), "0:00")
    }

    func testFormatDurationUnderOneMinute() {
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 45), "0:45")
    }

    func testFormatDurationExactlyOneMinute() {
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 60), "1:00")
    }

    func testFormatDurationMinutesAndSeconds() {
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 125), "2:05")
    }

    func testFormatDurationJustUnderOneHour() {
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 3599), "59:59")
    }

    func testFormatDurationExactlyOneHour() {
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 3600), "1:00:00")
    }

    func testFormatDurationHoursMinutesSeconds() {
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 7325), "2:02:05")
    }

    func testFormatDurationMultiHour() {
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 36000), "10:00:00")
    }

    func testFormatDurationTruncatesFractionalSeconds() {
        // Int(seconds) truncates toward zero, so 90.9 -> 90 seconds -> 1:30
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: 90.9), "1:30")
    }

    func testFormatDurationNegativeSecondsDoesNotCrash() {
        // hours = Int(-30) / 3600 = 0, so the "no hours" branch is taken and the
        // raw negative values flow straight into the format string.
        XCTAssertEqual(TimeFormatting.formatDuration(seconds: -30), "0:-30")
    }
}
