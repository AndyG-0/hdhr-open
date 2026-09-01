package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HDHomeRunGuideEntry(
    @SerialName("series_id")
    val seriesId: String? = null,
    val title: String,
    @SerialName("episode_title")
    val episodeTitle: String? = null,
    @SerialName("episode_number")
    val episodeNumber: String? = null,
    val synopsis: String? = null,
    val start: Double? = null,
    val end: Double? = null,
    @SerialName("original_airdate")
    val originalAirdate: String? = null,
    @SerialName("image_url")
    val imageUrl: String? = null,
    @SerialName("channel_number")
    val channelNumber: String? = null,
    @SerialName("season_number")
    val seasonNumber: Int? = null,
    val category: String? = null,
    @SerialName("is_new")
    val isNew: Boolean? = null,
    @SerialName("has_cc")
    val hasCC: Boolean? = null,
    val audio: String? = null
) {
    val formattedAudio: String?
        get() {
            val a = audio?.trim() ?: return null
            val lower = a.lowercase()
            return when {
                lower == "stereo" -> "STEREO"
                "5.1" in lower -> "5.1"
                "dolby" in lower || "dd" in lower -> "DOLBY"
                lower == "mono" -> "MONO"
                else -> a.uppercase()
            }
        }
    val formattedEpisodeDesignation: String?
        get() {
            if (seasonNumber != null && !episodeNumber.isNullOrEmpty()) {
                val epNum = if (episodeNumber.contains(".")) episodeNumber.substringAfter(".") else episodeNumber
                return "S${seasonNumber}E${epNum}"
            }
            if (!episodeNumber.isNullOrEmpty()) {
                if (episodeNumber.contains(".")) {
                    val s = episodeNumber.substringBefore(".")
                    val e = episodeNumber.substringAfter(".")
                    return "S${s}E${e}"
                }
                return "Ep $episodeNumber"
            }
            return null
        }
    val id: String
        get() = if (seriesId != null && start != null) {
            "${seriesId}_${start.toLong()}_${channelNumber ?: ""}"
        } else {
            "${title}_${start?.toLong() ?: 0}_${channelNumber ?: ""}"
        }

    val durationSeconds: Double?
        get() = if (start != null && end != null && end > start) end - start else null

    fun isCurrentlyAiring(timestamp: Double = System.currentTimeMillis() / 1000.0): Boolean {
        val s = start ?: return false
        val e = end ?: return false
        return timestamp in s..<e
    }

    fun progress(timestamp: Double = System.currentTimeMillis() / 1000.0): Float {
        val s = start ?: return 0f
        val e = end ?: return 0f
        if (e <= s) return 0f
        if (timestamp <= s) return 0f
        if (timestamp >= e) return 1f
        return ((timestamp - s) / (e - s)).toFloat()
    }
}
