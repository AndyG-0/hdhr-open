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
            start: 1_700_000_000,
            end: 1_700_003_600,
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
            dateTimeOnly: 1_700_000_000
        )

        let airing = HDHomeRunGuideEntry(
            seriesId: "series_200",
            title: "Special Live Event",
            start: 1_700_000_000,
            end: 1_700_003_600,
            channelNumber: "7.1"
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "7.1", airing: airing)
        XCTAssertNotNil(match)
        XCTAssertEqual(match?.recordingRuleId, "rule_2")

        // Non-matching channel
        let noMatch = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "9.1", airing: airing)
        XCTAssertNil(noMatch)
    }

    func testFindMatchingSeriesRuleByTitleWithoutSeriesId() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "rule_xmltv",
            seriesId: "auto",
            title: "Evening News",
            channelOnly: nil
        )

        let airing = HDHomeRunGuideEntry(
            seriesId: nil,
            title: "Evening News",
            start: 1_700_000_000,
            end: 1_700_003_600,
            channelNumber: "4.1"
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "4.1", airing: airing)
        XCTAssertNotNil(match)
        XCTAssertEqual(match?.recordingRuleId, "rule_xmltv")
    }

    func testFindMatchingMultiChannelRule() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "rule_multi",
            seriesId: "auto",
            title: "Local News",
            channelOnly: "4.1|4.2"
        )

        let airing1 = HDHomeRunGuideEntry(
            title: "Local News",
            channelNumber: "4.1"
        )
        let airing2 = HDHomeRunGuideEntry(
            title: "Local News",
            channelNumber: "4.2"
        )
        let airing3 = HDHomeRunGuideEntry(
            title: "Local News",
            channelNumber: "5.1"
        )

        XCTAssertNotNil(RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "4.1", airing: airing1))
        XCTAssertNotNil(RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "4.2", airing: airing2))
        XCTAssertNil(RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "5.1", airing: airing3))
    }
}
