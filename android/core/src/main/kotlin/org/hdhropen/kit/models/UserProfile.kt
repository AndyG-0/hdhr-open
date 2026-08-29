package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
enum class UserRole {
    @SerialName("admin")
    ADMIN,
    @SerialName("member")
    MEMBER
}

@Serializable
data class UserProfile(
    val id: String,
    val name: String,
    val avatar: String? = null,
    @SerialName("has_pin")
    val hasPin: Boolean = false
)

@Serializable
data class CurrentUser(
    val id: String,
    val name: String,
    val avatar: String? = null,
    val role: UserRole = UserRole.MEMBER,
    val token: String? = null
) {
    val isAdmin: Boolean get() = role == UserRole.ADMIN
}

@Serializable
data class UserPreferences(
    val theme: String? = null,
    val locale: String? = null
)

@Serializable
data class SetupStatus(
    @SerialName("needs_setup")
    val needsSetup: Boolean = false
)

@Serializable
data class HouseholdUser(
    val id: String,
    val name: String,
    val avatar: String? = null,
    @SerialName("has_pin")
    val hasPin: Boolean = false,
    val role: UserRole = UserRole.MEMBER,
    @SerialName("created_at")
    val createdAt: String = ""
)
