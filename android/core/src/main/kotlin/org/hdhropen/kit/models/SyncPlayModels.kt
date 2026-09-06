package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SyncPlayContent(
    val type: String,
    val id: String = "",
    val title: String = "",
    @SerialName("channel_number")
    val channelNumber: String? = null,
    @SerialName("play_url")
    val playUrl: String? = null,
    @SerialName("recording_id")
    val recordingId: String? = null,
    @SerialName("duration_seconds")
    val durationSeconds: Double? = null
)

@Serializable
data class SyncPlayPlaybackState(
    @SerialName("is_playing")
    val isPlaying: Boolean = false,
    val position: Double = 0.0,
    @SerialName("playback_rate")
    val playbackRate: Double = 1.0,
    @SerialName("updated_at")
    val updatedAt: Double = 0.0
)

@Serializable
data class SyncPlayParticipant(
    @SerialName("session_id")
    val sessionId: String,
    @SerialName("user_id")
    val userId: String? = null,
    @SerialName("user_name")
    val userName: String = "Viewer",
    val avatar: String? = null,
    @SerialName("is_host")
    val isHost: Boolean = false,
    @SerialName("is_ready")
    val isReady: Boolean = true,
    @SerialName("ping_ms")
    val pingMs: Double = 0.0,
    val position: Double = 0.0,
    @SerialName("last_seen")
    val lastSeen: Double = 0.0
)

@Serializable
data class SyncPlayRoom(
    @SerialName("room_code")
    val roomCode: String,
    @SerialName("created_at")
    val createdAt: Double = 0.0,
    @SerialName("host_session_id")
    val hostSessionId: String? = null,
    val content: SyncPlayContent? = null,
    @SerialName("playback_state")
    val playbackState: SyncPlayPlaybackState,
    val participants: List<SyncPlayParticipant> = emptyList()
) {
    val currentContent: SyncPlayContent? get() = content
}

@Serializable
data class CreateSyncPlayRoomRequest(
    val content: SyncPlayContent,
    @SerialName("user_name")
    val userName: String? = null
)

@Serializable
data class CreateSyncPlayRoomResponse(
    @SerialName("room_code")
    val roomCode: String,
    val room: SyncPlayRoom
)

@Serializable
data class SyncPlayMessage(
    val type: String,
    val action: String? = null,
    val room: SyncPlayRoom? = null,
    @SerialName("your_session_id")
    val yourSessionId: String? = null,
    val participant: SyncPlayParticipant? = null,
    @SerialName("session_id")
    val sessionId: String? = null,
    @SerialName("new_host_session_id")
    val newHostSessionId: String? = null,
    val position: Double? = null,
    @SerialName("playback_rate")
    val playbackRate: Double? = null,
    @SerialName("is_playing")
    val isPlaying: Boolean? = null,
    @SerialName("server_time")
    val serverTime: Double? = null,
    @SerialName("client_time")
    val clientTime: Double? = null,
    @SerialName("triggered_by")
    val triggeredBy: String? = null,
    val content: SyncPlayContent? = null
)
