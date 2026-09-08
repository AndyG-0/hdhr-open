package org.hdhropen.kit

import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.utilities.RecordingRuleMatcher
import org.junit.Assert.*
import org.junit.Test

class RecordingRuleMatcherTest {

    @Test
    fun testNullAiringReturnsNull() {
        val rule = HDHomeRunRecordingRule(recordingRuleId = "r1", seriesId = "s1", title = "News")
        assertNull(RecordingRuleMatcher.findMatchingRule(listOf(rule), "4.1", null))
    }

    @Test
    fun testExactEpisodeRuleMatchByDateTimeOnly() {
        val airing = HDHomeRunGuideEntry(
            title = "Special Report",
            seriesId = "s1",
            start = 1700000000.0,
            channelNumber = "4.1"
        )
        // DateTime within 60s matches
        val matchingRuleWithChannel = HDHomeRunRecordingRule(
            recordingRuleId = "r1",
            seriesId = "s1",
            title = "Different Title",
            dateTimeOnly = 1700000030.0,
            channelOnly = "4.1"
        )
        val result1 = RecordingRuleMatcher.findMatchingRule(listOf(matchingRuleWithChannel), "4.1", airing)
        assertEquals(matchingRuleWithChannel, result1)

        // Channel mismatch should not match
        val result2 = RecordingRuleMatcher.findMatchingRule(listOf(matchingRuleWithChannel), "5.1", airing)
        assertNull(result2)

        // Without channelOnly, matches on seriesId or title
        val matchingBySeries = HDHomeRunRecordingRule(
            recordingRuleId = "r2",
            seriesId = "s1",
            title = "Irrelevant",
            dateTimeOnly = 1700000010.0
        )
        val result3 = RecordingRuleMatcher.findMatchingRule(listOf(matchingBySeries), null, airing)
        assertEquals(matchingBySeries, result3)

        val matchingByTitle = HDHomeRunRecordingRule(
            recordingRuleId = "r3",
            seriesId = "wrong",
            title = "Special Report",
            dateTimeOnly = 1700000010.0
        )
        val result4 = RecordingRuleMatcher.findMatchingRule(listOf(matchingByTitle), null, airing)
        assertEquals(matchingByTitle, result4)

        // DateTime too far away (> 60s)
        val tooFarRule = HDHomeRunRecordingRule(
            recordingRuleId = "r4",
            seriesId = "s1",
            title = "Special Report",
            dateTimeOnly = 1700000100.0
        )
        val result5 = RecordingRuleMatcher.findMatchingRule(listOf(tooFarRule), null, airing)
        assertNull(result5)
    }

    @Test
    fun testSeriesAndKeywordRules() {
        val airing = HDHomeRunGuideEntry(
            title = "Star Trek: Discovery",
            episodeTitle = "The Vulcan Hello",
            synopsis = "A new journey begins with Michael Burnham.",
            category = "Sci-Fi",
            seriesId = "series_st",
            channelNumber = "7.1"
        )

        // Series rule matching by seriesId
        val seriesRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_series",
            seriesId = "series_st",
            title = "Star Trek"
        )
        val res1 = RecordingRuleMatcher.findMatchingRule(listOf(seriesRule), "7.1", airing)
        assertEquals(seriesRule, res1)

        // Channel filter on rule
        val wrongChannelRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_wrong_ch",
            seriesId = "series_st",
            title = "Star Trek",
            channelOnly = "9.1"
        )
        assertNull(RecordingRuleMatcher.findMatchingRule(listOf(wrongChannelRule), "7.1", airing))

        // Title matches with exact mode vs contains mode
        val containsRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_contains",
            seriesId = "",
            title = "Discovery",
            titleMatchMode = "contains"
        )
        val res2 = RecordingRuleMatcher.findMatchingRule(listOf(containsRule), "7.1", airing)
        assertEquals(containsRule, res2)

        val exactMismatchRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_exact_mismatch",
            seriesId = "",
            title = "Discovery" // default exact match will fail on "Star Trek: Discovery"
        )
        assertNull(RecordingRuleMatcher.findMatchingRule(listOf(exactMismatchRule), "7.1", airing))

        // Keyword queries (comma separated, matching episode title, synopsis, category)
        val kwEpisodeRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_kw_ep",
            seriesId = "series_st",
            title = "Star Trek",
            keywordQuery = "Vulcan, Klingon"
        )
        assertEquals(kwEpisodeRule, RecordingRuleMatcher.findMatchingRule(listOf(kwEpisodeRule), "7.1", airing))

        val kwSynopsisRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_kw_syn",
            seriesId = "series_st",
            title = "Star Trek",
            keywordQuery = "Burnham"
        )
        assertEquals(kwSynopsisRule, RecordingRuleMatcher.findMatchingRule(listOf(kwSynopsisRule), "7.1", airing))

        val kwCategoryRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_kw_cat",
            seriesId = "series_st",
            title = "Star Trek",
            keywordQuery = "sci-fi"
        )
        assertEquals(kwCategoryRule, RecordingRuleMatcher.findMatchingRule(listOf(kwCategoryRule), "7.1", airing))

        val kwMismatchRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_kw_none",
            seriesId = "series_st",
            title = "Star Trek",
            keywordQuery = "Romulan, Borg"
        )
        assertNull(RecordingRuleMatcher.findMatchingRule(listOf(kwMismatchRule), "7.1", airing))

        // Empty keywordQuery matches anything
        val kwBlankRule = HDHomeRunRecordingRule(
            recordingRuleId = "r_kw_blank",
            seriesId = "series_st",
            title = "Star Trek",
            keywordQuery = "   "
        )
        assertEquals(kwBlankRule, RecordingRuleMatcher.findMatchingRule(listOf(kwBlankRule), "7.1", airing))
    }
}
