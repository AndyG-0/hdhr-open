package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class AppSettings(
    val timezone: String? = null,
    @SerialName("guide_provider_priority")
    val guideProviderPriority: String? = null,
    @SerialName("dvr_server_priority")
    val dvrServerPriority: String? = null
)

@Serializable
data class HDHomeRunTranscodePreset(
    val id: String,
    val label: String,
    val description: String,
    @SerialName("input_args")
    val inputArgs: List<String> = emptyList(),
    @SerialName("output_args")
    val outputArgs: List<String> = emptyList(),
    val hardware: Boolean = false
)

@Serializable
data class HWAccelDiagnostics(
    val device: String = "",
    val summary: List<String> = emptyList(),
    @SerialName("sample_error")
    val sampleError: String? = null
)

@Serializable
data class NetworkIntegration(
    val id: String,
    val type: String,
    val name: String,
    val settings: Map<String, JsonElement> = emptyMap()
)

@Serializable
data class NetworkTestConnectionResult(
    val ok: Boolean = false,
    val detail: String? = null,
    val error: String? = null
)
