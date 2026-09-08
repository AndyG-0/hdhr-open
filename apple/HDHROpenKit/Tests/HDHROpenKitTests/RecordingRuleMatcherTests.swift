import XCTest
@testable import HDHROpenKit

final class RecordingRuleMatcherTests: XCTestCase {
    // MARK: - Top-level guards

    func testNilAiringReturnsNil() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "r1", seriesId: "s1", title: "Show")
        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "4.1", airing: nil)
        XCTAssertNil(match)
    }

    func testEmptyRulesReturnsNil() {
        let airing = HDHomeRunGuideEntry(title: "Show", start: 1_700_000_000, end: 1_700_003_600)
        let match = RecordingRuleMatcher.findMatchingRule(rules: [], channelNumber: "4.1", airing: airing)
        XCTAssertNil(match)
    }

    // MARK: - Episode rule matching (DateTimeOnly == airing.start)

    func testEpisodeRule_MatchesViaSeriesIdWhenNoChannelFilter() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "episode-1",
            seriesId: "series_1",
            title: "Irrelevant Title",
            dateTimeOnly: 1_700_000_000
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_1",
            title: "Completely Different Title",
            start: 1_700_000_000,
            end: 1_700_003_600
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "episode-1")
    }

    func testEpisodeRule_FallsBackToCaseInsensitiveTitleWhenSeriesIdsDiffer() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "episode-2",
            seriesId: "auto",
            title: "Big Game",
            dateTimeOnly: 1_700_000_000
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "other_series",
            title: "BIG GAME",
            start: 1_700_000_000,
            end: 1_700_003_600
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "episode-2")
    }

    func testEpisodeRule_NoMatchWhenNeitherSeriesIdNorTitleMatch() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "episode-3",
            seriesId: "series_x",
            title: "Foo",
            dateTimeOnly: 1_700_000_000
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_y",
            title: "Bar",
            start: 1_700_000_000,
            end: 1_700_003_600
        )

        // Not a series rule (dateTimeOnly is set), so it's excluded from the
        // series-matching pass too; overall result should be nil.
        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }

    func testEpisodeRule_TimeToleranceJustUnder60SecondsMatches() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "episode-4",
            seriesId: "series_1",
            title: "Show",
            dateTimeOnly: 1_700_000_000
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_1",
            title: "Show",
            start: 1_700_000_059, // 59s later
            end: 1_700_003_600
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "episode-4")
    }

    func testEpisodeRule_TimeToleranceExactly60SecondsDoesNotMatch() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "episode-5",
            seriesId: "series_1",
            title: "Show",
            dateTimeOnly: 1_700_000_000
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_1",
            title: "Show",
            start: 1_700_000_060, // exactly 60s later, not < 60
            end: 1_700_003_600
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }

    func testEpisodeRule_ChannelFilterMatchesWhenChannelInList() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "episode-6",
            seriesId: "auto",
            title: "Special Live Event",
            channelOnly: "7.1|7.2",
            dateTimeOnly: 1_700_000_000
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_200",
            title: "Special Live Event",
            start: 1_700_000_000,
            end: 1_700_003_600,
            channelNumber: "7.2"
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "7.2", airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "episode-6")
    }

    func testEpisodeRule_ChannelFilterExcludesWhenChannelNotInList() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "episode-7",
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
            channelNumber: "9.1"
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "9.1", airing: airing)
        XCTAssertNil(match)
    }

    func testEpisodeRule_TakesPrecedenceOverSeriesRuleMatch() {
        // A series rule that would also match sits first in the array, but
        // the exact-time episode rule check should still win because it is
        // evaluated as a separate, earlier pass.
        let seriesRule = HDHomeRunRecordingRule(
            recordingRuleId: "series-rule",
            seriesId: "series_1",
            title: "Show"
        )
        let episodeRule = HDHomeRunRecordingRule(
            recordingRuleId: "episode-rule",
            seriesId: "series_1",
            title: "Show",
            dateTimeOnly: 1_700_000_000
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_1",
            title: "Show",
            start: 1_700_000_000,
            end: 1_700_003_600
        )

        let match = RecordingRuleMatcher.findMatchingRule(
            rules: [seriesRule, episodeRule],
            channelNumber: nil,
            airing: airing
        )
        XCTAssertEqual(match?.recordingRuleId, "episode-rule")
    }

    // MARK: - Series rule matching

    func testSeriesRule_MatchesBySeriesId() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "series-1", seriesId: "series_100", title: "Nature Documentary")
        let airing = HDHomeRunGuideEntry(seriesId: "series_100", title: "A Different Episode Title")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "series-1")
    }

    func testSeriesRule_EmptySeriesIdsDoNotCountAsAMatch() {
        // Both rule.seriesId and airing.seriesId are empty strings; the
        // matcher explicitly requires both to be non-empty before comparing.
        let rule = HDHomeRunRecordingRule(recordingRuleId: "series-2", seriesId: "", title: "Different Title")
        let airing = HDHomeRunGuideEntry(seriesId: "", title: "Another Title")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }

    func testSeriesRule_MatchesByExactTitleWhenModeIsNil() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "series-3", seriesId: "auto", title: "Evening News")
        let airing = HDHomeRunGuideEntry(seriesId: nil, title: "Evening News")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "series-3")
    }

    func testSeriesRule_ExactTitleModeDoesNotMatchPartialTitle() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "series-4", seriesId: "auto", title: "News")
        let airing = HDHomeRunGuideEntry(seriesId: nil, title: "Evening News")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }

    func testSeriesRule_ContainsModeMatchesSubstring() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "series-5",
            seriesId: "auto",
            title: "News",
            titleMatchMode: "contains"
        )
        let airing = HDHomeRunGuideEntry(seriesId: nil, title: "Evening News Update")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "series-5")
    }

    func testSeriesRule_ContainsModeDoesNotMatchWhenSubstringAbsent() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "series-6",
            seriesId: "auto",
            title: "Weather",
            titleMatchMode: "contains"
        )
        let airing = HDHomeRunGuideEntry(seriesId: nil, title: "Evening News Update")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }

    func testSeriesRule_TitleMatchIsCaseAndWhitespaceInsensitive() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "series-7", seriesId: "auto", title: "  evening   news  ")
        let airing = HDHomeRunGuideEntry(seriesId: nil, title: "EVENING NEWS")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "series-7")
    }

    func testSeriesRule_EmptyAiringTitleNeverMatches() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "series-8", seriesId: "auto", title: "")
        let airing = HDHomeRunGuideEntry(seriesId: nil, title: "")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }

    func testSeriesRule_ChannelFilterExcludesNonMatchingChannel() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "series-9",
            seriesId: "series_1",
            title: "Show",
            channelOnly: "4.1"
        )
        let airing = HDHomeRunGuideEntry(seriesId: "series_1", title: "Show", channelNumber: "5.1")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "5.1", airing: airing)
        XCTAssertNil(match)
    }

    func testSeriesRule_ChannelFilterMultiChannelPipeDelimited() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "series-10",
            seriesId: "auto",
            title: "Local News",
            channelOnly: "4.1|4.2"
        )
        let airingOnSecondChannel = HDHomeRunGuideEntry(seriesId: nil, title: "Local News", channelNumber: "4.2")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: "4.2", airing: airingOnSecondChannel)
        XCTAssertEqual(match?.recordingRuleId, "series-10")
    }

    func testSeriesRule_DateTimeOnlyRuleExcludedFromSeriesPass() {
        // Even though this rule's series/title would match, it is an episode
        // rule (dateTimeOnly set) whose time does not line up, so it must be
        // excluded entirely from the series-matching pass.
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "not-a-series-rule",
            seriesId: "series_1",
            title: "Show",
            dateTimeOnly: 1_600_000_000
        )
        let airing = HDHomeRunGuideEntry(seriesId: "series_1", title: "Show", start: 1_700_000_000)

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }

    func testFindMatchingRule_ReturnsFirstOfMultipleMatchingSeriesRules() {
        let ruleA = HDHomeRunRecordingRule(recordingRuleId: "first", seriesId: "series_1", title: "Show")
        let ruleB = HDHomeRunRecordingRule(recordingRuleId: "second", seriesId: "series_1", title: "Show")
        let airing = HDHomeRunGuideEntry(seriesId: "series_1", title: "Show")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [ruleA, ruleB], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "first")
    }

    // MARK: - Keyword query matching

    func testKeywordQuery_NilQueryMatchesAnySeriesRule() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "kw-1", seriesId: "series_1", title: "Show", keywordQuery: nil)
        let airing = HDHomeRunGuideEntry(seriesId: "series_1", title: "Show")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "kw-1")
    }

    func testKeywordQuery_BlankQueryMatchesAnySeriesRule() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "kw-2", seriesId: "series_1", title: "Show", keywordQuery: "   ")
        let airing = HDHomeRunGuideEntry(seriesId: "series_1", title: "Show")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "kw-2")
    }

    func testKeywordQuery_MatchesInSynopsis() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "kw-3", seriesId: "series_1", title: "Show", keywordQuery: "space")
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_1",
            title: "Show",
            synopsis: "A journey through outer space and beyond."
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "kw-3")
    }

    func testKeywordQuery_MatchesInCategory() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "kw-4", seriesId: "series_1", title: "Show", keywordQuery: "documentary")
        let airing = HDHomeRunGuideEntry(seriesId: "series_1", title: "Show", category: "Documentary")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "kw-4")
    }

    func testKeywordQuery_MatchesInEpisodeTitle() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "kw-5", seriesId: "series_1", title: "Show", keywordQuery: "finale")
        let airing = HDHomeRunGuideEntry(seriesId: "series_1", title: "Show", episodeTitle: "Season Finale")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "kw-5")
    }

    func testKeywordQuery_NonMatchingKeywordExcludesOtherwiseMatchingRule() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "kw-6", seriesId: "series_1", title: "Show", keywordQuery: "zebra")
        let airing = HDHomeRunGuideEntry(seriesId: "series_1", title: "Show", synopsis: "Nothing relevant here.")

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }

    func testKeywordQuery_MultipleCommaSeparatedTermsMatchOnAny() {
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "kw-7",
            seriesId: "series_1",
            title: "Show",
            keywordQuery: "zebra, space, giraffe"
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_1",
            title: "Show",
            synopsis: "A journey through outer space."
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "kw-7")
    }

    func testKeywordQuery_IsCaseAndWhitespaceInsensitive() {
        let rule = HDHomeRunRecordingRule(recordingRuleId: "kw-8", seriesId: "series_1", title: "Show", keywordQuery: "  OUTER   SPACE  ")
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_1",
            title: "Show",
            synopsis: "A journey through outer space."
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertEqual(match?.recordingRuleId, "kw-8")
    }

    func testKeywordQuery_OnlyAppliedAfterSeriesOrTitleMatch() {
        // Even though the synopsis would satisfy the keyword query, neither
        // the series id nor the title match, so the rule should never even
        // reach keyword evaluation.
        let rule = HDHomeRunRecordingRule(
            recordingRuleId: "kw-9",
            seriesId: "series_other",
            title: "Completely Different",
            keywordQuery: "space"
        )
        let airing = HDHomeRunGuideEntry(
            seriesId: "series_1",
            title: "Show",
            synopsis: "A journey through outer space."
        )

        let match = RecordingRuleMatcher.findMatchingRule(rules: [rule], channelNumber: nil, airing: airing)
        XCTAssertNil(match)
    }
}
