package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class TunerViewerInfo(
    @SerialName("user_name")
    val userName: String = "",
    @SerialName("client_ip")
    val clientIp: String? = null
)

@Serializable
data class TunerClientInfo(
    val type: String = "idle",
    val name: String = "",
    val ip: String? = null,
    val hostname: String? = null,
    val details: String = "",
    @SerialName("recording_id")
    val recordingId: String? = null,
    @SerialName("scheduled_id")
    val scheduledId: String? = null,
    @SerialName("is_recording")
    val isRecording: Boolean = false,
    val viewers: List<TunerViewerInfo> = emptyList()
)

@Serializable
data class TunerWarningInfo(
    val severity: String = "info",
    val message: String = ""
)

@Serializable
data class HDHomeRunTuner(
    val index: Int,
    val resource: String? = null,
    @SerialName("in_use")
    val inUse: Boolean = false,
    @SerialName("channel_number")
    val channelNumber: String? = null,
    @SerialName("channel_name")
    val channelName: String? = null,
    @SerialName("target_ip")
    val targetIp: String? = null,
    val client: TunerClientInfo? = null,
    val warning: TunerWarningInfo? = null,
    @SerialName("signal_strength_percent")
    val signalStrengthPercent: Int? = null,
    @SerialName("signal_quality_percent")
    val signalQualityPercent: Int? = null,
    @SerialName("symbol_quality_percent")
    val symbolQualityPercent: Int? = null,
    @SerialName("network_rate_bps")
    val networkRateBps: Long? = null
) {
    val id: Int get() = index

    val formattedRateMbps: String
        get() {
            val bps = networkRateBps ?: return "0.0 Mbps"
            if (bps <= 0) return "0.0 Mbps"
            val mbps = bps.toDouble() / 1_000_000.0
            return String.format("%.1f Mbps", mbps)
        }
}

@Serializable
data class HDHomeRunTunerInfo(
    @SerialName("friendly_name")
    val friendlyName: String = "",
    @SerialName("model_number")
    val modelNumber: String? = null,
    @SerialName("firmware_version")
    val firmwareVersion: String? = null,
    @SerialName("tuner_count")
    val tunerCount: Int? = null
)

@Serializable
data class HDHomeRunDvrInfo(
    @SerialName("friendly_name")
    val friendlyName: String = "",
    val version: String? = null,
    @SerialName("free_space_bytes")
    val freeSpaceBytes: Long? = null,
    @SerialName("is_builtin")
    val isBuiltin: Boolean? = null,
    val provider: String? = null
) {
    val formattedFreeSpace: String
        get() {
            val bytes = freeSpaceBytes ?: return "Unknown"
            if (bytes <= 0) return "Unknown"
            val gb = bytes.toDouble() / 1_073_741_824.0
            if (gb >= 1000.0) {
                val tb = gb / 1024.0
                return String.format("%.2f TB free", tb)
            }
            return String.format("%.1f GB free", gb)
        }
}
