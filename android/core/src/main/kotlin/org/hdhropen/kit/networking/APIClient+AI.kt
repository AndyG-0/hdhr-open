package org.hdhropen.kit.networking

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonElement
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.hdhropen.kit.models.*
import org.hdhropen.kit.utilities.Log

private val aiJsonMediaType = "application/json; charset=utf-8".toMediaType()

suspend fun APIClient.sendAIChat(
    request: AIChatRequest,
    onEvent: (AIStreamEvent) -> Unit
) = withContext(Dispatchers.IO) {
    val fullUrl = if (baseURL.endsWith("/")) {
        baseURL + APIEndpoints.aiChat().removePrefix("/")
    } else {
        baseURL + APIEndpoints.aiChat()
    }

    val jsonString = json.encodeToString(request)
    val body = jsonString.toRequestBody(aiJsonMediaType)

    val reqBuilder = Request.Builder()
        .url(fullUrl)
        .post(body)

    bearerToken?.let { reqBuilder.header("Authorization", "Bearer $it") }
    deviceId?.let { reqBuilder.header("X-Device-Id", it) }

    val response = try {
        httpClient.newCall(reqBuilder.build()).execute()
    } catch (e: Exception) {
        throw APIError.NetworkError(e.localizedMessage ?: "Failed to connect to AI assistant")
    }

    if (!response.isSuccessful) {
        val code = response.code
        val errorMsg = response.body?.string() ?: "HTTP $code"
        throw APIError.ServerError(code, errorMsg)
    }

    val stream = response.body?.byteStream() ?: return@withContext
    stream.bufferedReader().useLines { lines ->
        for (line in lines) {
            if (line.startsWith("data: ")) {
                val dataContent = line.removePrefix("data: ").trim()
                if (dataContent.isNotEmpty()) {
                    try {
                        val event = json.decodeFromString<AIStreamEvent>(dataContent)
                        onEvent(event)
                    } catch (e: Exception) {
                        Log.network.error("Error decoding AI stream event: ${e.message}")
                    }
                }
            }
        }
    }
}

suspend fun APIClient.testAIConnection(payload: Map<String, JsonElement> = emptyMap()): NetworkTestConnectionResult {
    return request(path = APIEndpoints.aiTestConnection(), method = "POST", body = payload)
}

suspend fun APIClient.listAIModels(payload: Map<String, JsonElement> = emptyMap()): AIListModelsResponse {
    return request(path = APIEndpoints.aiListModels(), method = "POST", body = payload)
}

suspend fun APIClient.confirmAIAction(actionId: String): AIConfirmActionResponse {
    return request(path = APIEndpoints.aiConfirmAction(actionId), method = "POST")
}

suspend fun APIClient.cancelAIAction(actionId: String): AICancelActionResponse {
    return request(path = APIEndpoints.aiCancelAction(actionId), method = "POST")
}
