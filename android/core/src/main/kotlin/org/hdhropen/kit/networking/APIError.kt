package org.hdhropen.kit.networking

sealed class APIError(message: String) : Exception(message) {
    object InvalidURL : APIError("Invalid URL")
    data class NetworkError(override val message: String) : APIError(message)
    data class DecodingError(override val message: String) : APIError(message)
    data class Unauthorized(override val message: String) : APIError(message)
    object Forbidden : APIError("Forbidden")
    data class NotFound(override val message: String) : APIError(message)
    data class LockedOut(override val message: String) : APIError(message)
    data class ServerError(val statusCode: Int, override val message: String) : APIError(message)
    object NoActiveWatchSession : APIError("No active watch session")
}
