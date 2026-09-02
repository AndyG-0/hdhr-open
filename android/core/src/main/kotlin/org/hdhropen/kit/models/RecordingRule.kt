package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HDHomeRunRecordingRule(
    @SerialName("RecordingRuleID")
    val recordingRuleId: String,
    @SerialName("SeriesID")
    val seriesId: String,
    @SerialName("Title")
    val title: String,
    @SerialName("Synopsis")
    val synopsis: String? = null,
    @SerialName("ImageURL")
    val imageUrl: String? = null,
    @SerialName("ChannelOnly")
    val channelOnly: String? = null,
    @SerialName("DateTimeOnly")
    val dateTimeOnly: Double? = null,
    @SerialName("Priority")
    val priority: Int? = null,
    @SerialName("StartPadding")
    val startPadding: Int? = null,
    @SerialName("EndPadding")
    val endPadding: Int? = null,
    @SerialName("RecentOnly")
    val recentOnly: Int? = null,
    @SerialName("MaxEpisodesToKeep")
    val maxEpisodesToKeep: Int? = null,
    @SerialName("TitleMatchMode")
    val titleMatchMode: String? = null,
    @SerialName("KeywordQuery")
    val keywordQuery: String? = null,
    @SerialName("Provider")
    val provider: String? = null
) {
    val id: String get() = recordingRuleId
    val isSeriesRule: Boolean get() = dateTimeOnly == null
    val isEpisodeRule: Boolean get() = dateTimeOnly != null
}

data class RecordingRuleOptions(
    val title: String? = null,
    val titleMatchMode: String? = null,
    val keywordQuery: String? = null,
    // Channel scope override — pipe-delimited for multi-channel rules
    // (e.g. "4.1|5.1"). Null means "use the airing's own channel".
    val channel: String? = null,
    val startPadding: Int? = null,
    val endPadding: Int? = null,
    val recentOnly: Boolean? = null,
    val maxEpisodesToKeep: Int? = null,
    val server: String? = null
)

@Serializable
data class AddRecordingRulePayload(
    @SerialName("series_id")
    val seriesId: String,
    @SerialName("date_time")
    val dateTime: Double? = null,
    val channel: String? = null,
    val title: String? = null,
    @SerialName("title_match_mode")
    val titleMatchMode: String? = null,
    @SerialName("keyword_query")
    val keywordQuery: String? = null,
    @SerialName("recent_only")
    val recentOnly: Boolean? = null,
    @SerialName("start_padding")
    val startPadding: Int? = null,
    @SerialName("end_padding")
    val endPadding: Int? = null,
    @SerialName("max_episodes_to_keep")
    val maxEpisodesToKeep: Int? = null,
    val server: String? = null
)
