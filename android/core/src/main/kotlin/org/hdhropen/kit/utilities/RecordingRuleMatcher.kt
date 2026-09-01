package org.hdhropen.kit.utilities

import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import kotlin.math.abs

object RecordingRuleMatcher {
    private fun normalize(s: String): String = s.trim().lowercase().replace(Regex("\\s+"), " ")

    private fun keywordMatches(keywordQuery: String?, airing: HDHomeRunGuideEntry): Boolean {
        if (keywordQuery.isNullOrBlank()) return true
        val terms = keywordQuery.split(",").map { normalize(it) }.filter { it.isNotEmpty() }
        if (terms.isEmpty()) return true
        val haystacks = listOfNotNull(airing.episodeTitle, airing.synopsis, airing.category, airing.title).map { normalize(it) }
        return terms.any { term -> haystacks.any { it.contains(term) } }
    }

    private fun titleMatches(ruleTitle: String, airingTitle: String?, mode: String?): Boolean {
        if (airingTitle.isNullOrBlank()) return false
        val normRule = normalize(ruleTitle)
        val normAiring = normalize(airingTitle)
        return if (mode == "contains") normAiring.contains(normRule) else normRule == normAiring
    }

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

        // 2. Keyword / Series / Title rules
        return rules.firstOrNull { rule ->
            if (!rule.isSeriesRule) return@firstOrNull false
            if (rule.channelOnly != null && channelNumber != null && rule.channelOnly != channelNumber) {
                return@firstOrNull false
            }
            val seriesMatches = !rule.seriesId.isNullOrEmpty() && !airing.seriesId.isNullOrEmpty() && rule.seriesId == airing.seriesId
            val titleMatchesAiring = titleMatches(rule.title, airing.title, rule.titleMatchMode)
            if (!seriesMatches && !titleMatchesAiring) return@firstOrNull false
            keywordMatches(rule.keywordQuery, airing)
        }
    }
}
