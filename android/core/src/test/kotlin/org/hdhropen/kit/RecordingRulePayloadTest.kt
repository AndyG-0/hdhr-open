package org.hdhropen.kit

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.hdhropen.kit.models.AddRecordingRulePayload
import org.junit.Assert.*
import org.junit.Test

class RecordingRulePayloadTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun testEncodeExactTitle() {
        val payload = AddRecordingRulePayload(
            seriesId = "auto",
            title = "Evening News",
            titleMatchMode = "exact"
        )
        val obj = json.encodeToJsonElement(AddRecordingRulePayload.serializer(), payload).jsonObject
        assertEquals("Evening News", obj["title"]?.jsonPrimitive?.content)
        assertEquals("exact", obj["title_match_mode"]?.jsonPrimitive?.content)
    }

    @Test
    fun testEncodeContainsTitle() {
        val payload = AddRecordingRulePayload(
            seriesId = "auto",
            title = "Football",
            titleMatchMode = "contains"
        )
        val obj = json.encodeToJsonElement(AddRecordingRulePayload.serializer(), payload).jsonObject
        assertEquals("contains", obj["title_match_mode"]?.jsonPrimitive?.content)
    }

    @Test
    fun testEncodeKeywordQuery() {
        val payload = AddRecordingRulePayload(
            seriesId = "auto",
            keywordQuery = "Ohio State, Michigan",
            server = "builtin"
        )
        val obj = json.encodeToJsonElement(AddRecordingRulePayload.serializer(), payload).jsonObject
        assertEquals("Ohio State, Michigan", obj["keyword_query"]?.jsonPrimitive?.content)
        assertEquals("builtin", obj["server"]?.jsonPrimitive?.content)
    }

    @Test
    fun testEncodeMultiChannelScope() {
        val payload = AddRecordingRulePayload(
            seriesId = "auto",
            channel = "4.1|5.1",
            title = "Local News"
        )
        val obj = json.encodeToJsonElement(AddRecordingRulePayload.serializer(), payload).jsonObject
        assertEquals("4.1|5.1", obj["channel"]?.jsonPrimitive?.content)
    }

    @Test
    fun testEncodeRetentionLimit() {
        val payload = AddRecordingRulePayload(
            seriesId = "series_1",
            maxEpisodesToKeep = 3
        )
        val obj = json.encodeToJsonElement(AddRecordingRulePayload.serializer(), payload).jsonObject
        assertEquals(3, obj["max_episodes_to_keep"]?.jsonPrimitive?.int)
    }

    @Test
    fun testEncodeServerTarget() {
        val payload = AddRecordingRulePayload(
            seriesId = "series_1",
            server = "hdhomerun"
        )
        val obj = json.encodeToJsonElement(AddRecordingRulePayload.serializer(), payload).jsonObject
        assertEquals("hdhomerun", obj["server"]?.jsonPrimitive?.content)
    }
}
