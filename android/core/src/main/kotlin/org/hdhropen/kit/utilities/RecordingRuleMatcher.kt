package org.hdhropen.kit.utilities

import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import kotlin.math.abs

object RecordingRuleMatcher {
    fun findMatchingRule(
        rules: List<HDHomeRunRecordingRule>,
        channelNumber: String?,
        airing: HDHomeRunGuideEntry?
    ): HDHomeRunRecordingRule? {
        if (airing == null) return null

        // 1. Episode rule exact match (DateTimeOnly == airing.start)
        val start = airing.start
        if (start != null) {
            val match = rules.firstOrNull { rule ->
                val dt = rule.dateTimeOnly ?: return@firstOrNull false
                val timeMatches = abs(dt - start) < 60
                if (rule.channelOnly != null && channelNumber != null) {
                    timeMatches && rule.channelOnly == channelNumber
                } else {
                    timeMatches && (rule.seriesId == airing.seriesId || rule.title.equals(airing.title, ignoreCase = true))
                }
            }
            if (match != null) return match
        }

        // 2. Series rule match
        val seriesId = airing.seriesId
        if (!seriesId.isNullOrEmpty()) {
            val match = rules.firstOrNull { rule ->
                rule.isSeriesRule && rule.seriesId == seriesId &&
                        (rule.channelOnly == null || rule.channelOnly == channelNumber)
            }
            if (match != null) return match
        }

        // 3. Title match fallback for series
        return rules.firstOrNull { rule ->
            rule.isSeriesRule && rule.title.equals(airing.title, ignoreCase = true) &&
                    (rule.channelOnly == null || rule.channelOnly == channelNumber)
        }
    }
}
