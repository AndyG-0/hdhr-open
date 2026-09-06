package org.hdhropen.kit.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.util.UUID

@Serializable
data class AIChatWireToolCall(
    val id: String,
    val name: String,
    val arguments: Map<String, JsonElement> = emptyMap()
)

@Serializable
data class AIChatWireMessage(
    val role: String,
    val content: JsonElement? = null,
    @SerialName("tool_calls")
    val toolCalls: List<AIChatWireToolCall>? = null,
    @SerialName("tool_call_id")
    val toolCallId: String? = null,
    val name: String? = null
)

@Serializable
data class AIChatContext(
    val now: String? = null,
    val timezone: String? = null,
    @SerialName("selected_channel")
    val selectedChannel: String? = null
)

@Serializable
data class AIChatRequest(
    val messages: List<AIChatWireMessage>,
    val context: AIChatContext = AIChatContext()
)

@Serializable
data class AIStreamEvent(
    val type: String,
    val text: String? = null,
    val id: String? = null,
    val tool: String? = null,
    val status: String? = null,
    val message: String? = null,
    val arguments: Map<String, JsonElement>? = null,
    val content: Map<String, JsonElement>? = null,
    @SerialName("action_id")
    val actionId: String? = null,
    val preview: Map<String, JsonElement>? = null
)

@Serializable
data class AIConfirmActionResponse(
    val result: JsonElement? = null
)

@Serializable
data class AICancelActionResponse(
    val ok: Boolean = true
)

@Serializable
data class AIListModelsResponse(
    val ok: Boolean = false,
    val models: List<String> = emptyList(),
    val error: String? = null
)

// MARK: - Client View Models & State

enum class AIActionResolution {
    PENDING,
    CONFIRMING,
    CONFIRMED,
    CANCELLED,
    FAILED
}

data class AIToolStatusEntry(
    val tool: String,
    var status: String,
    var message: String? = null
)

data class AIActionPreviewEntry(
    val actionId: String,
    val tool: String,
    val preview: Map<String, JsonElement>,
    var resolution: AIActionResolution = AIActionResolution.PENDING
)

data class AIToolCallRecord(
    val id: String,
    val name: String,
    val arguments: Map<String, JsonElement> = emptyMap(),
    var result: Map<String, JsonElement>? = null
)

data class AIChatTurn(
    val id: String = UUID.randomUUID().toString(),
    val role: String,
    var text: String = "",
    val toolStatuses: MutableList<AIToolStatusEntry> = mutableListOf(),
    var actionPreview: AIActionPreviewEntry? = null,
    val toolCalls: MutableList<AIToolCallRecord> = mutableListOf()
)

object AIChatHelpers {
    val quickSuggestions = listOf(
        "What's on tonight?",
        "Upcoming live sports",
        "What movies are playing today?",
        "Show recording rules"
    )

    fun toWireMessages(turns: List<AIChatTurn>): List<AIChatWireMessage> {
        val wire = mutableListOf<AIChatWireMessage>()
        for (turn in turns) {
            if (turn.role == "user") {
                if (turn.text.isNotBlank()) {
                    wire.add(AIChatWireMessage(role = "user", content = JsonPrimitive(turn.text)))
                }
                continue
            }

            val resolvedCalls = turn.toolCalls.filter { it.result != null }
            if (resolvedCalls.isEmpty()) {
                if (turn.text.isNotBlank()) {
                    wire.add(AIChatWireMessage(role = "assistant", content = JsonPrimitive(turn.text)))
                }
                continue
            }

            val wireCalls = resolvedCalls.map {
                AIChatWireToolCall(id = it.id, name = it.name, arguments = it.arguments)
            }
            wire.add(AIChatWireMessage(role = "assistant", content = JsonPrimitive(turn.text), toolCalls = wireCalls))

            for (call in resolvedCalls) {
                call.result?.let { res ->
                    wire.add(AIChatWireMessage(role = "tool", content = JsonObject(res), toolCallId = call.id, name = call.name))
                }
            }
        }
        return wire
    }
}
