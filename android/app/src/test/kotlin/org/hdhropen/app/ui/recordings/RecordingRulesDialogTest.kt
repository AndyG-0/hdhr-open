package org.hdhropen.app.ui.recordings

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import io.mockk.coVerify
import io.mockk.mockk
import io.mockk.spyk
import org.hdhropen.app.ui.screens.recordings.RecordingRulesDialog
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.RecordingsViewModel
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RecordingRulesDialogTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testRecordingRulesDialogEmptyState() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val recordingsVm = spyk(RecordingsViewModel(apiClient))
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingRulesDialog(
                    rules = emptyList(),
                    recordingsViewModel = recordingsVm,
                    onDismiss = { dismissed = true }
                )
            }
        }

        composeTestRule.onNodeWithText("Scheduled Rules").assertIsDisplayed()
        composeTestRule.onNodeWithText("No scheduled rules.").assertIsDisplayed()

        // Close button
        composeTestRule.onNodeWithContentDescription("Close").performClick()
        assertTrue(dismissed)
    }

    @Test
    fun testRecordingRulesDialogWithRulesAndDelete() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val recordingsVm = spyk(RecordingsViewModel(apiClient))

        val rule1 = HDHomeRunRecordingRule(
            recordingRuleId = "rule-1",
            title = "Modern Family",
            seriesId = "series-mf",
            channelOnly = "7.1",
            keywordQuery = "Phil Dunphy",
            titleMatchMode = "contains",
            recentOnly = 1,
            maxEpisodesToKeep = 10,
            startPadding = 60,
            endPadding = 180,
            provider = "builtin"
        )

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingRulesDialog(
                    rules = listOf(rule1),
                    recordingsViewModel = recordingsVm,
                    onDismiss = {}
                )
            }
        }

        composeTestRule.onNodeWithText("Modern Family").assertIsDisplayed()
        composeTestRule.onNodeWithText("Series Rule • Ch 7.1").assertIsDisplayed()
        composeTestRule.onNodeWithText("Keyword: Phil Dunphy").assertIsDisplayed()
        composeTestRule.onNodeWithText("Contains match").assertIsDisplayed()

        // Click delete rule icon
        composeTestRule.onNodeWithContentDescription("Delete Rule").performClick()
        coVerify { recordingsVm.deleteRule("rule-1") }
        coVerify { recordingsVm.loadRules() }
    }
}
