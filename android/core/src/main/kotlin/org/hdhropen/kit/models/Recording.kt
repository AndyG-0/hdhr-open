package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class HDHomeRunRecordingVideoInfo(
    val codec: String? = null,
    val width: Int? = null,
    val height: Int? = null,
    val fps: Double? = null
)

@Serializable
data class HDHomeRunRecordingAudioInfo(
    val index: Int,
    val codec: String? = null,
    val channels: Int? = null,
    val language: String? = null
) {
    val displayLabel: String
        get() {
            val parts = mutableListOf<String>()
            if (!language.isNullOrEmpty()) {
                parts.add(language.uppercase())
            } else {
                parts.add("Track ${index + 1}")
            }
            if (channels != null) {
                when (channels) {
                    6 -> parts.add("5.1 Surround")
                    2 -> parts.add("Stereo")
                    else -> parts.add("$channels ch")
                }
            }
            if (!codec.isNullOrEmpty()) {
                parts.add(codec.uppercase())
            }
            return parts.joinToString(" • ")
        }
}

@Serializable
data class HDHomeRunTranscodeInfo(
    val transcoding: Boolean = false,
    val preset: String? = null,
    @SerialName("preset_label")
    val presetLabel: String? = null,
    val hardware: Boolean = false
)

@Serializable
data class HDHomeRunRecordingDetail(
    @SerialName("is_in_progress")
    val isInProgress: Boolean = false,
    @SerialName("duration_seconds")
    val durationSeconds: Double? = null,
    val video: HDHomeRunRecordingVideoInfo? = null,
    val audio: List<HDHomeRunRecordingAudioInfo> = emptyList(),
    @SerialName("has_captions")
    val hasCaptions: Boolean = false,
    val transcode: HDHomeRunTranscodeInfo? = null
)

@Serializable
data class HDHomeRunRecording(
    @SerialName("recording_id")
    val recordingId: String? = null,
    @SerialName("session_id")
    val sessionId: String? = null,
    @SerialName("playlist_url")
    val playlistUrl: String? = null,
    @SerialName("series_id")
    val seriesId: String? = null,
    val title: String,
    @SerialName("episode_title")
    val episodeTitle: String? = null,
    @SerialName("season_number")
    val seasonNumber: Int? = null,
    @SerialName("episode_number")
    val episodeNumber: String? = null,
    val synopsis: String? = null,
    @SerialName("channel_number")
    val channelNumber: String? = null,
    @SerialName("channel_name")
    val channelName: String? = null,
    val start: Double? = null,
    @SerialName("record_end")
    val recordEnd: Double? = null,
    @SerialName("play_url")
    val playUrl: String? = null,
    @SerialName("image_url")
    val imageUrl: String? = null,
    @SerialName("duration_seconds")
    val durationSeconds: Double? = null,
    @SerialName("file_size_bytes")
    val fileSizeBytes: Long? = null,
    @SerialName("has_captions")
    val hasCaptions: Boolean? = null,
    @SerialName("video_codec")
    val videoCodec: String? = null,
    @SerialName("video_width")
    val videoWidth: Int? = null,
    @SerialName("video_height")
    val videoHeight: Int? = null,
    @SerialName("audio_codec")
    val audioCodec: String? = null,
    @SerialName("audio_channels")
    val audioChannels: Int? = null,
    @SerialName("original_air_date")
    val originalAirDate: String? = null,
    val category: String? = null,
    @SerialName("category_type")
    val categoryType: String? = null,
    @SerialName("is_dvr_file")
    val isDvrFile: Boolean? = null,
    val provider: String? = null
) {
    val id: String
        get() = recordingId ?: playUrl ?: "${title}_${start?.toLong() ?: 0}"

    val isInProgress: Boolean
        get() {
            val end = recordEnd ?: return false
            return end > (System.currentTimeMillis() / 1000.0)
        }

    val formattedDuration: String
        get() {
            val dur = durationSeconds ?: return ""
            if (dur <= 0) return ""
            val totalMinutes = (dur / 60).toInt()
            val hours = totalMinutes / 60
            val remMinutes = totalMinutes % 60
            return if (hours > 0) {
                "${hours}h ${remMinutes}m"
            } else {
                "${totalMinutes}m"
            }
        }

    val episodeDesignation: String?
        get() {
            if (seasonNumber != null && episodeNumber != null) {
                return "S$seasonNumber:E$episodeNumber"
            }
            if (episodeNumber != null) {
                return "Ep $episodeNumber"
            }
            return null
        }

    val formattedFileSize: String
        get() {
            val bytes = fileSizeBytes ?: return ""
            if (bytes <= 0) return ""
            val gb = bytes.toDouble() / 1_073_741_824.0
            if (gb >= 1.0) {
                return String.format("%.1f GB", gb)
            }
            val mb = bytes.toDouble() / 1_048_576.0
            return String.format("%.0f MB", mb)
        }
}
