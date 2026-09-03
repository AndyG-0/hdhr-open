package org.hdhropen.kit.networking

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.hdhropen.kit.models.*
import org.hdhropen.kit.utilities.Log
import java.io.IOException
import java.util.concurrent.TimeUnit

class InMemoryCookieJar : CookieJar {
    private val cookieStore = mutableMapOf<String, MutableList<Cookie>>()

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        val host = url.host
        val currentCookies = cookieStore.getOrPut(host) { mutableListOf() }
        cookies.forEach { newCookie ->
            currentCookies.removeAll { it.name == newCookie.name }
            currentCookies.add(newCookie)
        }
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        val host = url.host
        val currentCookies = cookieStore[host] ?: return emptyList()
        val now = System.currentTimeMillis()
        currentCookies.removeAll { it.expiresAt < now }
        return currentCookies
    }

    fun clear() {
        cookieStore.clear()
    }
}

@Serializable
data class HLSSessionResponse(
    @SerialName("session_id")
    val sessionId: String,
    @SerialName("playlist_url")
    val playlistUrl: String
)

@Serializable
private data class LoginBody(
    val pin: String? = null,
    @SerialName("token_name")
    val tokenName: String? = null
)

@Serializable
private data class RecordingStreamHLSBody(
    val url: String,
    @SerialName("recording_id")
    val recordingId: String? = null,
    val start: Double? = null,
    @SerialName("audio_index")
    val audioIndex: Int? = null,
    val provider: String? = null,
    @SerialName("for_cast")
    val forCast: Boolean = false
)

class APIClient(
    var baseURL: String,
    val cookieJar: InMemoryCookieJar = InMemoryCookieJar(),
    private val httpClient: OkHttpClient = OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()
) {
    var bearerToken: String? = null
    var deviceId: String? = null

    val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        encodeDefaults = true
        coerceInputValues = true
    }

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    // MARK: - Core HTTP Engine

    suspend fun requestRaw(
        path: String,
        method: String = "GET",
        jsonBody: String? = null,
        headers: Map<String, String> = emptyMap()
    ): ByteArray = withContext(Dispatchers.IO) {
        val fullUrl = if (path.startsWith("http://") || path.startsWith("https://")) {
            path
        } else {
            val base = baseURL.trimEnd('/')
            val cleanPath = if (path.startsWith("/")) path else "/$path"
            "$base$cleanPath"
        }

        val requestBuilder = Request.Builder().url(fullUrl)

        bearerToken?.let { token ->
            requestBuilder.header("Authorization", "Bearer $token")
        }

        deviceId?.let { id ->
            requestBuilder.header("X-Device-Id", id)
        }

        headers.forEach { (k, v) ->
            requestBuilder.header(k, v)
        }

        when (method.uppercase()) {
            "GET" -> requestBuilder.get()
            "POST" -> {
                val body = jsonBody?.toRequestBody(jsonMediaType) ?: "".toRequestBody(jsonMediaType)
                requestBuilder.post(body)
            }
            "DELETE" -> requestBuilder.delete()
            "PATCH" -> {
                val body = jsonBody?.toRequestBody(jsonMediaType) ?: "".toRequestBody(jsonMediaType)
                requestBuilder.patch(body)
            }
            "PUT" -> {
                val body = jsonBody?.toRequestBody(jsonMediaType) ?: "".toRequestBody(jsonMediaType)
                requestBuilder.put(body)
            }
        }

        val response: Response
        try {
            response = httpClient.newCall(requestBuilder.build()).execute()
        } catch (e: IOException) {
            throw APIError.NetworkError(e.localizedMessage ?: "Network error")
        }

        val bytes = response.body?.bytes() ?: ByteArray(0)

        if (!response.isSuccessful) {
            val detailMessage = extractErrorDetail(bytes) ?: "Request failed with status code ${response.code}"
            when (response.code) {
                401 -> throw APIError.Unauthorized(detailMessage)
                403 -> throw APIError.Forbidden
                404 -> throw APIError.NotFound(detailMessage)
                429 -> throw APIError.LockedOut(detailMessage)
                else -> throw APIError.ServerError(response.code, detailMessage)
            }
        }

        bytes
    }

    suspend inline fun <reified T> request(
        path: String,
        method: String = "GET",
        body: Any? = null,
        headers: Map<String, String> = emptyMap()
    ): T = withContext(Dispatchers.IO) {
        val jsonBody = body?.let {
            when (it) {
                is String -> it
                else -> json.encodeToString(it)
            }
        }
        val data = requestRaw(path, method, jsonBody, headers)
        val text = String(data, Charsets.UTF_8)
        try {
            json.decodeFromString<T>(text)
        } catch (e: Exception) {
            Log.network.error("JSON Decode error for $path: ${e.localizedMessage}")
            throw APIError.DecodingError(e.localizedMessage ?: "Decoding error")
        }
    }

    private fun extractErrorDetail(bytes: ByteArray): String? {
        if (bytes.isEmpty()) return null
        return try {
            val text = String(bytes, Charsets.UTF_8)
            val jsonObject = json.parseToJsonElement(text).jsonObject
            jsonObject["detail"]?.jsonPrimitive?.content
        } catch (e: Exception) {
            null
        }
    }

    // MARK: - Guide APIs

    suspend fun getChannels(): HDHomeRunChannelsResponse =
        request(APIEndpoints.guideChannels())

    suspend fun getGuide(): List<HDHomeRunFullGuideChannel> =
        request(APIEndpoints.guide())

    suspend fun refreshGuide() {
        requestRaw(APIEndpoints.refreshGuide(), method = "POST")
    }

    // MARK: - DVR APIs

    suspend fun getDvrInfo(): HDHomeRunDvrInfo =
        request(APIEndpoints.dvrInfo())

    suspend fun listRecordings(): List<HDHomeRunRecording> =
        request(APIEndpoints.recordings())

    suspend fun deleteRecording(id: String) {
        requestRaw(APIEndpoints.deleteRecording(id), method = "DELETE")
    }

    suspend fun getRecordingDetail(
        url: String,
        recordingId: String,
        start: Double? = null,
        recordEnd: Double? = null,
        provider: String? = null
    ): HDHomeRunRecordingDetail =
        request(APIEndpoints.recordingDetail(url, recordingId, start, recordEnd, provider))

    suspend fun listRecordingRules(): List<HDHomeRunRecordingRule> =
        request(APIEndpoints.recordingRules())

    suspend fun addRecordingRule(payload: AddRecordingRulePayload): List<HDHomeRunRecordingRule> =
        request(APIEndpoints.recordingRules(), method = "POST", body = json.encodeToString(payload))

    suspend fun deleteRecordingRule(id: String): List<HDHomeRunRecordingRule> =
        request(APIEndpoints.deleteRecordingRule(id), method = "DELETE")

    // MARK: - Live Watch APIs

    suspend fun startWatch(channelNumber: String): HDHomeRunRecording? {
        return try {
            val resp: HDHomeRunRecording = request(APIEndpoints.startWatch(channelNumber), method = "POST")
            if (resp.recordingId == null && resp.sessionId == null) null else resp
        } catch (e: Exception) {
            null
        }
    }

    suspend fun heartbeatWatch(sessionId: String) {
        requestRaw(APIEndpoints.heartbeatWatch(sessionId), method = "POST")
    }

    suspend fun stopWatch(sessionId: String) {
        requestRaw(APIEndpoints.stopWatch(sessionId), method = "POST")
    }

    suspend fun promoteWatch(sessionId: String, options: Map<String, JsonElement>? = null): HDHomeRunRecording {
        val bodyStr = options?.let { json.encodeToString(it) }
        return request(APIEndpoints.promoteWatch(sessionId), method = "POST", body = bodyStr)
    }

    // MARK: - HLS Packaging APIs

    suspend fun createChannelHLSSession(
        channelNumber: String,
        forCast: Boolean = false,
        audioIndex: Int? = null
    ): HDHomeRunRecording =
        request(APIEndpoints.hlsChannelSession(channelNumber, forCast, audioIndex), method = "POST")

    suspend fun createRecordingHLSSession(
        url: String,
        recordingId: String? = null,
        start: Double? = null,
        audioIndex: Int? = null,
        provider: String? = null,
        forCast: Boolean = false
    ): HLSSessionResponse {
        val body = RecordingStreamHLSBody(url, recordingId, start, audioIndex, provider, forCast)
        return request(APIEndpoints.hlsRecordingSession(), method = "POST", body = json.encodeToString(body))
    }

    suspend fun stopHLSSession(sessionId: String) {
        requestRaw(APIEndpoints.stopHLSSession(sessionId), method = "POST")
    }

    // MARK: - Tuner APIs

    suspend fun getTunerStatus(): List<HDHomeRunTuner> =
        request(APIEndpoints.tunerStatus())

    suspend fun getTunerInfo(): HDHomeRunTunerInfo =
        request(APIEndpoints.tunerInfo())

    // MARK: - Auth & Profile APIs

    suspend fun listProfiles(): List<UserProfile> =
        request(APIEndpoints.users())

    suspend fun login(userId: String, pin: String?, tokenName: String?): CurrentUser {
        val body = LoginBody(pin, tokenName)
        return request(APIEndpoints.loginUser(userId), method = "POST", body = json.encodeToString(body))
    }

    suspend fun logout() {
        requestRaw(APIEndpoints.logoutUser(), method = "POST")
    }

    suspend fun getCurrentUser(): CurrentUser =
        request(APIEndpoints.currentUser())

    suspend fun getUserPreferences(): UserPreferences =
        request(APIEndpoints.userPreferences())

    suspend fun updateUserPreferences(prefs: UserPreferences): UserPreferences =
        request(APIEndpoints.userPreferences(), method = "PATCH", body = json.encodeToString(prefs))

    // MARK: - Device APIs

    suspend fun registerDevice(): DeviceRegisterResult {
        val result: DeviceRegisterResult = request(APIEndpoints.registerDevice(), method = "POST")
        deviceId = result.id
        return result
    }

    suspend fun getCurrentDevice(): DeviceInfo =
        request(APIEndpoints.currentDevice())

    suspend fun listDevices(): List<DeviceListEntry> =
        request(APIEndpoints.listDevices())

    suspend fun deleteDevice(id: String) {
        requestRaw(APIEndpoints.deleteDevice(id), method = "DELETE")
    }

    // MARK: - Settings APIs

    suspend fun getSettings(): AppSettings =
        request(APIEndpoints.settings())

    suspend fun getTranscodePresets(): List<HDHomeRunTranscodePreset> =
        request(APIEndpoints.transcodePresets())

    suspend fun getHWAccelDiagnostics(): HWAccelDiagnostics =
        request(APIEndpoints.hwaccelDiagnostics())

    suspend fun listNetworkIntegrations(): List<NetworkIntegration> =
        request(APIEndpoints.networkIntegrations())

    suspend fun getNetworkIntegration(type: String): NetworkIntegration =
        request(APIEndpoints.networkIntegration(type))

    suspend fun updateNetworkIntegration(type: String, settings: Map<String, JsonElement>): NetworkIntegration =
        request(APIEndpoints.networkIntegration(type), method = "PATCH", body = json.encodeToString(settings))

    suspend fun fetchRawString(url: String): String = withContext(Dispatchers.IO) {
        val data = requestRaw(url)
        String(data, Charsets.UTF_8)
    }
}
