package org.hdhropen.kit

import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.*
import org.hdhropen.kit.models.*
import org.junit.Assert.*
import org.junit.Test

class AIModelsTest {
    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
    }

    @Test
    fun testEncodeChatRequest() {
        val wire = listOf(
            AIChatWireMessage(role = "user", content = JsonPrimitive("What's on tonight?")),
            AIChatWireMessage(
                role = "assistant",
                content = JsonPrimitive("Checking guide..."),
                toolCalls = listOf(
                    AIChatWireToolCall(
                        id = "call_1",
                        name = "search_guide",
                        arguments = mapOf("query" to JsonPrimitive("news"))
                    )
                )
            ),
            AIChatWireMessage(
                role = "tool",
                content = buildJsonObject { put("found", 2) },
                toolCallId = "call_1",
                name = "search_guide"
            )
        )
        val context = AIChatContext(now = "2026-09-06T12:00:00Z", timezone = "America/Los_Angeles", selectedChannel = "5.1")
        val request = AIChatRequest(messages = wire, context = context)

        val jsonString = json.encodeToString(request)
        val parsed = json.parseToJsonElement(jsonString).jsonObject

        assertNotNull(parsed["messages"])
        assertNotNull(parsed["context"])

        val msgs = parsed["messages"]!!.jsonArray
        assertEquals(3, msgs.size)
        assertEquals("user", msgs[0].jsonObject["role"]?.jsonPrimitive?.content)
        assertEquals("What's on tonight?", msgs[0].jsonObject["content"]?.jsonPrimitive?.content)
        assertEquals("assistant", msgs[1].jsonObject["role"]?.jsonPrimitive?.content)
        assertEquals("tool", msgs[2].jsonObject["role"]?.jsonPrimitive?.content)
        assertEquals("call_1", msgs[2].jsonObject["tool_call_id"]?.jsonPrimitive?.content)
    }

    @Test
    fun testDecodeStreamEvents() {
        val tokenJson = """{"type": "token", "text": "Hello world"}"""
        val tokenEvent = json.decodeFromString<AIStreamEvent>(tokenJson)
        assertEquals("token", tokenEvent.type)
        assertEquals("Hello world", tokenEvent.text)

        val toolCallJson = """{"type": "tool_call", "id": "call_123", "tool": "search_guide", "arguments": {"query": "movies"}}"""
        val toolCallEvent = json.decodeFromString<AIStreamEvent>(toolCallJson)
        assertEquals("tool_call", toolCallEvent.type)
        assertEquals("call_123", toolCallEvent.id)
        assertEquals("search_guide", toolCallEvent.tool)
        assertEquals("movies", toolCallEvent.arguments?.get("query")?.jsonPrimitive?.content)

        val actionPreviewJson = """
        {
            "type": "action_preview",
            "action_id": "act_456",
            "tool": "schedule_recording",
            "preview": {"title": "Nova", "channel": "9.1"}
        }
        """.trimIndent()
        val actionPreviewEvent = json.decodeFromString<AIStreamEvent>(actionPreviewJson)
        assertEquals("action_preview", actionPreviewEvent.type)
        assertEquals("act_456", actionPreviewEvent.actionId)
        assertEquals("schedule_recording", actionPreviewEvent.tool)
        assertEquals("Nova", actionPreviewEvent.preview?.get("title")?.jsonPrimitive?.content)

        val doneJson = """{"type": "done"}"""
        val doneEvent = json.decodeFromString<AIStreamEvent>(doneJson)
        assertEquals("done", doneEvent.type)

        val statusJson = """{"type": "tool_status", "status": "running", "message": "Searching guide...", "content": {"key": "val"}}"""
        val statusEvent = json.decodeFromString<AIStreamEvent>(statusJson)
        assertEquals("tool_status", statusEvent.type)
        assertEquals("running", statusEvent.status)
        assertEquals("Searching guide...", statusEvent.message)
        assertNotNull(statusEvent.content)
    }

    @Test
    fun testAIResponsesAndUIModels() {
        val listResp = json.decodeFromString<AIListModelsResponse>("""{"ok": true, "models": ["gpt-4o", "gemini-pro"]}""")
        assertTrue(listResp.ok)
        assertEquals(2, listResp.models.size)
        assertNull(listResp.error)

        val confirmResp = json.decodeFromString<AIConfirmActionResponse>("""{"result": {"rule_id": "r1"}}""")
        assertNotNull(confirmResp.result)

        val cancelResp = json.decodeFromString<AICancelActionResponse>("""{"ok": true}""")
        assertTrue(cancelResp.ok)

        val toolEntry = AIToolStatusEntry("search_guide", "done", "Finished searching")
        assertEquals("search_guide", toolEntry.tool)
        assertEquals("done", toolEntry.status)
        assertEquals("Finished searching", toolEntry.message)
        toolEntry.status = "error"
        assertEquals("error", toolEntry.status)

        val actionEntry = AIActionPreviewEntry("act1", "record", mapOf("title" to JsonPrimitive("Show")))
        assertEquals(AIActionResolution.PENDING, actionEntry.resolution)
        actionEntry.resolution = AIActionResolution.CONFIRMED
        assertEquals(AIActionResolution.CONFIRMED, actionEntry.resolution)
        assertEquals(5, AIActionResolution.values().size)
    }

    @Test
    fun testToWireMessages() {
        val turns = listOf(
            AIChatTurn(role = "user", text = "Record news"),
            AIChatTurn(
                role = "assistant",
                text = "Found News at 6.",
                toolStatuses = mutableListOf(AIToolStatusEntry("search_guide", "done")),
                actionPreview = AIActionPreviewEntry(
                    actionId = "act_1",
                    tool = "schedule_recording",
                    preview = mapOf("title" to JsonPrimitive("News at 6"))
                ),
                toolCalls = mutableListOf(
                    AIToolCallRecord(
                        id = "call_1",
                        name = "search_guide",
                        arguments = mapOf("query" to JsonPrimitive("news")),
                        result = mapOf("count" to JsonPrimitive(1))
                    )
                )
            )
        )

        val wire = AIChatHelpers.toWireMessages(turns)
        assertEquals(3, wire.size)
        assertEquals("user", wire[0].role)
        assertEquals("Record news", wire[0].content?.jsonPrimitive?.content)
        assertEquals("assistant", wire[1].role)
        assertEquals(1, wire[1].toolCalls?.size)
        assertEquals("search_guide", wire[1].toolCalls?.first()?.name)
        assertEquals("tool", wire[2].role)
        assertEquals("call_1", wire[2].toolCallId)
    }
}
