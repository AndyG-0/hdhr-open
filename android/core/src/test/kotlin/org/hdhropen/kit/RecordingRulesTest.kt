package org.hdhropen.kit

import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.utilities.RecordingRuleMatcher
import org.junit.Assert.*
import org.junit.Test

class RecordingRulesTest {
    @Test
    fun testFindMatchingSeriesRule() {
        val rule = HDHomeRunRecordingRule(
            recordingRuleId = "rule_1",
            seriesId = "series_100",
            title = "Nature Documentary",
            channelOnly = null
        )

        val airing = HDHomeRunGuideEntry(
            seriesId = "series_100",
            title = "Nature Documentary",
            start = 1700000000.0,
            end = 1700003600.0,
            channelNumber = "5.1"
        )

        val match = RecordingRuleMatcher.findMatchingRule(listOf(rule), "5.1", airing)
        assertNotNull(match)
        assertEquals("rule_1", match?.recordingRuleId)
    }

    @Test
    fun testFindMatchingEpisodeRule() {
        val rule = HDHomeRunRecordingRule(
            recordingRuleId = "rule_2",
            seriesId = "auto",
            title = "Special Live Event",
            channelOnly = "7.1",
            dateTimeOnly = 1700000000.0
        )

        val airing = HDHomeRunGuideEntry(
            seriesId = "series_200",
            title = "Special Live Event",
            start = 1700000000.0,
            end = 1700003600.0,
            channelNumber = "7.1"
        )

        val match = RecordingRuleMatcher.findMatchingRule(listOf(rule), "7.1", airing)
        assertNotNull(match)
        assertEquals("rule_2", match?.recordingRuleId)

        // Non-matching channel
        val noMatch = RecordingRuleMatcher.findMatchingRule(listOf(rule), "9.1", airing)
        assertNull(noMatch)
    }

    @Test
    fun testFindMatchingTitleFallback() {
        val rule = HDHomeRunRecordingRule(
            recordingRuleId = "rule_3",
            seriesId = "",
            title = "Local News at 6",
            channelOnly = "4.1"
        )

        val airing = HDHomeRunGuideEntry(
            seriesId = null,
            title = "Local News at 6",
            start = 1700000000.0,
            end = 1700001800.0,
            channelNumber = "4.1"
        )

        val match = RecordingRuleMatcher.findMatchingRule(listOf(rule), "4.1", airing)
        assertNotNull(match)
        assertEquals("rule_3", match?.recordingRuleId)
    }
}
