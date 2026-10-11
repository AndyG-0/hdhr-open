package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// Wire shape for GET /api/discovery. `items` reuses the exact same airing
// model the guide already deserializes (HDHomeRunGuideEntry) - the backend
// returns candidates in that shape unchanged, so no separate Discovery
// airing model is defined here.
@Serializable
data class DiscoveryResponse(
    @SerialName("has_profile")
    val hasProfile: Boolean = false,
    val enabled: Boolean = false,
    val items: List<HDHomeRunGuideEntry> = emptyList()
)
