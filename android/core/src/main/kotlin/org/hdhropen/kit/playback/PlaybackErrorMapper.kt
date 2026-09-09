package org.hdhropen.kit.playback

import androidx.media3.common.PlaybackException
import androidx.media3.datasource.HttpDataSource
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.hdhropen.kit.networking.APIError

object PlaybackErrorMapper {

    fun extractDetailFromBody(bytes: ByteArray): String? {
        if (bytes.isEmpty()) return null
        return try {
            val text = String(bytes, Charsets.UTF_8).trim()
            if (text.startsWith("{")) {
                val root = Json { ignoreUnknownKeys = true }.parseToJsonElement(text)
                root.jsonObject["detail"]?.jsonPrimitive?.contentOrNull
            } else if (!text.startsWith("<") && text.length < 300) {
                text
            } else {
                null
            }
        } catch (e: Exception) {
            null
        }
    }

    fun mapHttpStatus(statusCode: Int, serverDetail: String? = null): ParsedPlaybackError {
        return when (statusCode) {
            502 -> ParsedPlaybackError(
                message = "Tuner or streaming server unavailable (HTTP 502)",
                detail = serverDetail ?: "The streaming server or HDHomeRun tuner reported a temporary failure. Try again in a few moments.",
                statusCode = 502,
                isNetworkError = true
            )
            503 -> ParsedPlaybackError(
                message = "Streaming service unavailable (HTTP 503)",
                detail = serverDetail ?: "The server is temporarily busy or unavailable. Please try again shortly.",
                statusCode = 503,
                isNetworkError = true
            )
            504 -> ParsedPlaybackError(
                message = "Stream gateway timeout (HTTP 504)",
                detail = serverDetail ?: "The server timed out waiting for the tuner or transcoder.",
                statusCode = 504,
                isNetworkError = true
            )
            404 -> ParsedPlaybackError(
                message = "Stream or channel not found (HTTP 404)",
                detail = serverDetail ?: "The live watch session or recording stream has ended or expired.",
                statusCode = 404,
                isNetworkError = true
            )
            401 -> ParsedPlaybackError(
                message = "Authentication required (HTTP 401)",
                detail = serverDetail ?: "Your session is invalid or expired. Please sign in again.",
                statusCode = 401,
                isNetworkError = true
            )
            403 -> ParsedPlaybackError(
                message = "Authentication error (HTTP 403)",
                detail = serverDetail ?: "Your session is invalid or expired. Please sign in again.",
                statusCode = 403,
                isNetworkError = true
            )
            429 -> ParsedPlaybackError(
                message = "Account locked out (HTTP 429)",
                detail = serverDetail ?: "Account locked out due to too many attempts.",
                statusCode = 429,
                isNetworkError = false
            )
            else -> ParsedPlaybackError(
                message = "Server error (HTTP $statusCode)",
                detail = serverDetail ?: "The server returned HTTP status code $statusCode.",
                statusCode = statusCode,
                isNetworkError = true
            )
        }
    }

    fun mapApiError(e: Throwable): ParsedPlaybackError {
        return when (e) {
            is APIError.ServerError -> mapHttpStatus(e.statusCode, e.message)
            is APIError.NetworkError -> ParsedPlaybackError(
                message = "Network connection error",
                detail = "Unable to connect to the HDHomeRun Open server. Please check your network connection.",
                statusCode = null,
                isNetworkError = true
            )
            is APIError.Unauthorized -> ParsedPlaybackError(
                message = "Authentication required (HTTP 401)",
                detail = e.message,
                statusCode = 401,
                isNetworkError = true
            )
            is APIError.NotFound -> ParsedPlaybackError(
                message = "Stream or channel not found (HTTP 404)",
                detail = e.message,
                statusCode = 404,
                isNetworkError = true
            )
            is APIError.LockedOut -> ParsedPlaybackError(
                message = "Account locked out (HTTP 429)",
                detail = e.message,
                statusCode = 429,
                isNetworkError = false
            )
            else -> ParsedPlaybackError(
                message = "Failed to start stream",
                detail = e.localizedMessage ?: "An unexpected error occurred while starting stream",
                statusCode = null,
                isNetworkError = false
            )
        }
    }

    fun parseExoPlayerError(error: PlaybackException): ParsedPlaybackError {
        var cur: Throwable? = error
        var httpException: HttpDataSource.InvalidResponseCodeException? = null
        var networkException: HttpDataSource.HttpDataSourceException? = null

        while (cur != null) {
            if (cur is HttpDataSource.InvalidResponseCodeException) {
                httpException = cur
                break
            }
            if (cur is HttpDataSource.HttpDataSourceException && networkException == null) {
                networkException = cur
            }
            cur = cur.cause
        }

        if (httpException != null) {
            val code = httpException.responseCode
            val serverDetail = extractDetailFromBody(httpException.responseBody)
            return mapHttpStatus(code, serverDetail)
        }

        if (networkException != null) {
            val rootCause = networkException.cause
            val detail = when (rootCause) {
                is java.net.ConnectException -> "Could not connect to the streaming server. Verify the server is running."
                is java.net.SocketTimeoutException -> "The connection to the streaming server timed out."
                is java.net.UnknownHostException -> "Could not resolve the server hostname."
                else -> networkException.message ?: "Failed to read data from the server."
            }
            return ParsedPlaybackError(
                message = "Network connection error",
                detail = detail,
                statusCode = null,
                isNetworkError = true
            )
        }

        if (error.errorCode == PlaybackException.ERROR_CODE_DECODER_INIT_FAILED) {
            return ParsedPlaybackError(
                message = "Video decoder error",
                detail = "Unable to initialize video decoder for this broadcast format.",
                statusCode = null,
                isNetworkError = false
            )
        }

        val cleanMsg = error.localizedMessage
            ?.takeIf { !it.contains("androidx.media3") && !it.contains("Exception") }
            ?: "An unexpected playback error occurred."

        return ParsedPlaybackError(
            message = "Playback error",
            detail = cleanMsg,
            statusCode = null,
            isNetworkError = false
        )
    }
}

// Top-level aliases for backward-compatibility with tests/call sites
fun extractDetailFromBody(bytes: ByteArray): String? = PlaybackErrorMapper.extractDetailFromBody(bytes)
fun parseExoPlayerError(error: PlaybackException): ParsedPlaybackError = PlaybackErrorMapper.parseExoPlayerError(error)
