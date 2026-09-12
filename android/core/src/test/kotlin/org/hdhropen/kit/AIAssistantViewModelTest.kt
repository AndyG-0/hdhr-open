package org.hdhropen.kit

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.hdhropen.kit.models.AIActionResolution
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.AIAssistantViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AIAssistantViewModelTest {

    private val testDispatcher = StandardTestDispatcher()
    private val testScope = TestScope(testDispatcher)
    private lateinit var server: MockWebServer
    private lateinit var apiClient: APIClient
    private lateinit var viewModel: AIAssistantViewModel

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
        server = MockWebServer()
        server.start()
        val url = server.url("/").toString().removeSuffix("/")
        apiClient = APIClient(baseURL = url, ioDispatcher = testDispatcher)
        viewModel = AIAssistantViewModel(apiClient, ioDispatcher = testDispatcher, externalScope = testScope)
    }

    @After
    fun tearDown() {
        server.shutdown()
        Dispatchers.resetMain()
    }

    @Test
    fun testInitialState() {
        assertTrue(viewModel.turns.value.isEmpty())
        assertFalse(viewModel.isSending.value)
        assertNull(viewModel.errorText.value)
    }

    @Test
    fun testSendPromptStreamsTokens() = testScope.runTest {
        val sseBody = """
            data: {"type":"token","text":"Hello "}
            
            data: {"type":"token","text":"world!"}
            
            data: {"type":"done"}
            
        """.trimIndent()

        server.enqueue(MockResponse().setResponseCode(200).setBody(sseBody))

        viewModel.sendPrompt("Hi")
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(2, viewModel.turns.value.size)
        assertEquals("user", viewModel.turns.value[0].role)
        assertEquals("Hi", viewModel.turns.value[0].text)
        assertEquals("assistant", viewModel.turns.value[1].role)
        assertEquals("Hello world!", viewModel.turns.value[1].text)
        assertFalse(viewModel.isSending.value)
    }

    @Test
    fun testToolCallsAndActionPreviewConfirmation() = testScope.runTest {
        val sseBody = """
            data: {"type":"tool_status","tool":"search_guide","status":"running","message":"Searching..."}
            
            data: {"type":"tool_call","id":"call-1","tool":"schedule_recording","arguments":{"title":"News"}}
            
            data: {"type":"tool_result","id":"call-1","content":{"status":"Scheduled"}}
            
            data: {"type":"action_preview","action_id":"act-1","tool":"schedule_recording","preview":{"title":"News"}}
            
            data: {"type":"done"}
            
        """.trimIndent()

        server.enqueue(MockResponse().setResponseCode(200).setBody(sseBody))
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"result":"ok"}"""))

        viewModel.sendPrompt("Record News")
        testDispatcher.scheduler.advanceUntilIdle()

        val assistantTurn = viewModel.turns.value[1]
        assertEquals(1, assistantTurn.toolStatuses.size)
        assertEquals("search_guide", assistantTurn.toolStatuses[0].tool)
        assertEquals(1, assistantTurn.toolCalls.size)
        assertEquals("call-1", assistantTurn.toolCalls[0].id)
        assertNotNull(assistantTurn.actionPreview)
        assertEquals(AIActionResolution.PENDING, assistantTurn.actionPreview?.resolution)

        viewModel.confirmAction("act-1")
        var attempts = 0
        while (viewModel.turns.value[1].actionPreview?.resolution == AIActionResolution.CONFIRMING && attempts < 50) {
            testDispatcher.scheduler.advanceUntilIdle()
            kotlinx.coroutines.delay(20)
            attempts++
        }

        assertEquals(AIActionResolution.CONFIRMED, viewModel.turns.value[1].actionPreview?.resolution)
    }

    @Test
    fun testCancelAction() = testScope.runTest {
        val sseBody = """
            data: {"type":"action_preview","action_id":"act-2","tool":"delete_rule","preview":{"id":"123"}}
            
            data: {"type":"done"}
            
        """.trimIndent()

        server.enqueue(MockResponse().setResponseCode(200).setBody(sseBody))
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok":true}"""))

        viewModel.sendPrompt("Delete rule")
        testDispatcher.scheduler.advanceUntilIdle()

        viewModel.cancelAction("act-2")
        testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(AIActionResolution.CANCELLED, viewModel.turns.value[1].actionPreview?.resolution)
    }

    @Test
    fun testNewChatClearsState() = testScope.runTest {
        val sseBody = """
            data: {"type":"token","text":"Response"}
            
            data: {"type":"done"}
            
        """.trimIndent()

        server.enqueue(MockResponse().setResponseCode(200).setBody(sseBody))

        viewModel.sendPrompt("Test")
        testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(2, viewModel.turns.value.size)

        viewModel.newChat()
        assertTrue(viewModel.turns.value.isEmpty())
        assertNull(viewModel.errorText.value)
    }
}
