package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HDHomeRunChannel(
    @SerialName("channel_number")
    val channelNumber: String,
    val name: String,
    @SerialName("is_hd")
    val isHD: Boolean = false,
    @SerialName("is_drm")
    val isDRM: Boolean = false,
    @SerialName("stream_url")
    val streamUrl: String = "",
    @SerialName("playback_url")
    val playbackUrl: String? = null,
    val now: HDHomeRunGuideEntry? = null,
    val next: HDHomeRunGuideEntry? = null
) {
    val id: String get() = channelNumber
    val displayNumber: String get() = channelNumber
}

@Serializable
data class HDHomeRunChannelsResponse(
    val channels: List<HDHomeRunChannel> = emptyList(),
    @SerialName("guide_available")
    val guideAvailable: Boolean = false
)

@Serializable
data class HDHomeRunFullGuideChannel(
    @SerialName("channel_number")
    val channelNumber: String,
    @SerialName("channel_name")
    val channelName: String,
    val airings: List<HDHomeRunGuideEntry> = emptyList()
) {
    val id: String get() = channelNumber
}

@Serializable
data class HDHomeRunChannelSetting(
    val id: String,
    @SerialName("channel_number")
    val channelNumber: String,
    val name: String,
    @SerialName("is_hd")
    val isHD: Boolean = false,
    @SerialName("is_favorite")
    val isFavorite: Boolean = false,
    val hidden: Boolean = false,
    @SerialName("guide_provider")
    val guideProvider: String? = null,
    @SerialName("xmltv_channel_id")
    val xmltvChannelId: String? = null,
    @SerialName("xmltv_display_name")
    val xmltvDisplayName: String? = null,
    @SerialName("sd_station_id")
    val sdStationId: String? = null,
    @SerialName("sd_lineup_id")
    val sdLineupId: String? = null
)
