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
    val channelNumber: String? = null
) {
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
