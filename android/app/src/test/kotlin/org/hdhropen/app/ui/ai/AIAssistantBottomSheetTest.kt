package org.hdhropen.app.ui.ai

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import io.mockk.mockk
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.hdhropen.app.ui.screens.ai.AIAssistantBottomSheet
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.networking.APIClient
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w400dp-h1000dp")
class AIAssistantBottomSheetTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private lateinit var server: MockWebServer
    private lateinit var apiClient: APIClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        apiClient = APIClient(server.url("/").toString())
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun testAIAssistantRendersHeaderAndEmptyState() {
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                AIAssistantBottomSheet(
                    apiClient = apiClient,
                    onDismiss = { dismissed = true }
                )
            }
        }

        // Header
        composeTestRule.onNodeWithText("AI Assistant").assertIsDisplayed()

        // Empty state
        composeTestRule.onNodeWithText("What can I help you find?").assertIsDisplayed()

        // Input field placeholder
        composeTestRule.onNodeWithText("Ask about schedules, sports, or DVR...").assertExists()

        // Close button
        composeTestRule.onNodeWithContentDescription("Close").performClick()
        assertTrue(dismissed)
    }

    @Test
    fun testAIAssistantSendMessageAndReceiveToken() {
        val sseResponse = buildString {
            append("data: {\"type\":\"token\",\"text\":\"Here is what is on: \"}\n\n")
            append("data: {\"type\":\"token\",\"text\":\"Evening News on Ch 5.1.\"}\n\n")
            append("data: {\"type\":\"done\"}\n\n")
        }
        server.enqueue(MockResponse().setResponseCode(200).setBody(sseResponse))

        composeTestRule.setContent {
            HDHROpenTheme {
                AIAssistantBottomSheet(
                    apiClient = apiClient,
                    onDismiss = {}
                )
            }
        }

        // Enter prompt and click send
        composeTestRule.onNodeWithText("Ask about schedules, sports, or DVR...").performTextInput("What's on?")
        composeTestRule.onNodeWithContentDescription("Send").performClick()

        // User message
        composeTestRule.onNodeWithText("What's on?").assertExists()

        // Assistant streamed response
        composeTestRule.waitUntil(5_000) {
            composeTestRule.onAllNodesWithText("Here is what is on: Evening News on Ch 5.1.").fetchSemanticsNodes().isNotEmpty()
        }

        // "New Chat" button should now exist
        composeTestRule.onNodeWithText("New Chat").assertExists()
        composeTestRule.onNodeWithText("New Chat").performClick()

        // Turns should be cleared, returning to empty state
        composeTestRule.onNodeWithText("What can I help you find?").assertExists()
    }

    @Test
    fun testAIAssistantToolCallAndActionPreviewConfirmation() {
        val sseResponse = buildString {
            append("data: {\"type\":\"tool_status\",\"tool\":\"search_guide\",\"status\":\"running\",\"message\":\"Searching live guide...\"}\n\n")
            append("data: {\"type\":\"tool_call\",\"id\":\"call-1\",\"tool\":\"schedule_recording\",\"arguments\":{\"title\":\"Seinfeld\"}}\n\n")
            append("data: {\"type\":\"action_preview\",\"action_id\":\"act-1\",\"tool\":\"schedule_recording\",\"preview\":{\"title\":\"Seinfeld\",\"channel\":\"2.1 FOX\"}}\n\n")
            append("data: {\"type\":\"done\"}\n\n")
        }
        server.enqueue(MockResponse().setResponseCode(200).setBody(sseResponse))
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"result\":\"ok\"}"))

        composeTestRule.setContent {
            HDHROpenTheme {
                AIAssistantBottomSheet(
                    apiClient = apiClient,
                    onDismiss = {}
                )
            }
        }

        // Send prompt
        composeTestRule.onNodeWithText("Ask about schedules, sports, or DVR...").performTextInput("Record Seinfeld")
        composeTestRule.onNodeWithContentDescription("Send").performClick()

        // Verify tool status and action preview appear
        composeTestRule.waitUntil(5_000) {
            composeTestRule.onAllNodesWithText("Schedule recording").fetchSemanticsNodes().isNotEmpty()
        }
        composeTestRule.onNodeWithText("search_guide").assertExists()
        composeTestRule.onNodeWithText("Title: ").assertExists()
        composeTestRule.onNodeWithText("Seinfeld").assertExists()
        composeTestRule.onNodeWithText("Channel: ").assertExists()
        composeTestRule.onNodeWithText("2.1 FOX").assertExists()

        // Click Confirm Action
        composeTestRule.onNodeWithText("Confirm").performScrollTo().performClick()
        composeTestRule.waitUntil(5_000) {
            composeTestRule.onAllNodesWithText("Action confirmed and executed.").fetchSemanticsNodes().isNotEmpty()
        }
    }
}
