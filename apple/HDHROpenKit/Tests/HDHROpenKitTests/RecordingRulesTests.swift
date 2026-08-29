import XCTest
@testable import HDHROpenKit

final class RecordingRulesTests: XCTestCase {
    func testFindMatchingSeriesRule() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "rule_1",
            seriesId: "series_100",
            title: "Nature Documentary",
            channelOnly: nil
        )

        let airing = HDHomeRunGuideEntry(
            seriesId: "series_100",
            title: "Nature Documentary",
            start: 1700000000,
            end: 1700003600,
            channelNumber: "5.1"
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "5.1", airing: airing)
        XCTAssertNotNil(match)
        XCTAssertEqual(match?.recordingRuleId, "rule_1")
    }

    func testFindMatchingEpisodeRule() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "rule_2",
            seriesId: "auto",
            title: "Special Live Event",
            channelOnly: "7.1",
            dateTimeOnly: 1700000000
        )

        let airing = HDHomeRunGuideEntry(
            seriesId: "series_200",
            title: "Special Live Event",
            start: 1700000000,
            end: 1700003600,
            channelNumber: "7.1"
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "7.1", airing: airing)
        XCTAssertNotNil(match)
        XCTAssertEqual(match?.recordingRuleId, "rule_2")

        // Non-matching channel
        let noMatch = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "9.1", airing: airing)
        XCTAssertNil(noMatch)
    }
}
