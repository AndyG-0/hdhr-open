package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class DeviceInfo(
    val id: String,
    val name: String
)

@Serializable
data class DeviceListEntry(
    val id: String,
    val name: String,
    @SerialName("last_seen_at")
    val lastSeenAt: String
)

@Serializable
data class DeviceRegisterResult(
    val id: String,
    val name: String,
    @SerialName("is_new")
    val isNew: Boolean = false
)
