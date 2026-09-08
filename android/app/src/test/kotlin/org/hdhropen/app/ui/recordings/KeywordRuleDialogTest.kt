package org.hdhropen.app.ui.recordings

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import org.hdhropen.app.ui.screens.recordings.KeywordRuleDialog
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.RecordingRuleOptions
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class KeywordRuleDialogTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testKeywordRuleDialogCreateRule() {
        val channel1 = HDHomeRunChannel(channelNumber = "4.1", name = "KRON")
        val channel2 = HDHomeRunChannel(channelNumber = "5.1", name = "KPIX")

        var submittedTitle: String? = null
        var submittedOptions: RecordingRuleOptions? = null

        composeTestRule.setContent {
            HDHROpenTheme {
                KeywordRuleDialog(
                    channels = listOf(channel1, channel2),
                    loading = false,
                    onConfirm = { t, opts ->
                        submittedTitle = t
                        submittedOptions = opts
                    },
                    onDismiss = {}
                )
            }
        }

        // Header
        composeTestRule.onNodeWithText("Add Keyword Rule").assertExists()

        // Create Rule button should be disabled when title is blank
        composeTestRule.onNodeWithText("Create Rule").performScrollTo().assertIsNotEnabled()

        // Enter Title
        composeTestRule.onNodeWithText("Title").performTextInput("Premier League")

        // Select Title contains
        composeTestRule.onNodeWithText("Title contains").performScrollTo().performClick()

        // Enter keywords
        composeTestRule.onNodeWithText("Keywords (optional)").performScrollTo().performTextInput("Arsenal, Liverpool")

        // Select custom channels
        composeTestRule.onNodeWithText("Select channels…").performScrollTo().performClick()
        composeTestRule.onNodeWithText("4.1 KRON").performScrollTo().performClick()

        // Toggle new episodes only
        composeTestRule.onNodeWithText("New episodes only").performScrollTo().performClick()

        // Toggle retention mode to Keep last N
        composeTestRule.onNodeWithText("Keep last N").performScrollTo().performClick()

        // Now Create Rule button should be enabled
        composeTestRule.onNodeWithText("Create Rule").performScrollTo().assertIsEnabled()
        composeTestRule.onNodeWithText("Create Rule").performScrollTo().performClick()

        assertEquals("Premier League", submittedTitle)
        assertNotNull(submittedOptions)
        assertEquals("contains", submittedOptions?.titleMatchMode)
        assertEquals("Arsenal, Liverpool", submittedOptions?.keywordQuery)
        assertEquals("4.1", submittedOptions?.channel)
        assertEquals(true, submittedOptions?.recentOnly)
        assertEquals(3, submittedOptions?.maxEpisodesToKeep)
    }

    @Test
    fun testKeywordRuleDialogCancel() {
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                KeywordRuleDialog(
                    channels = emptyList(),
                    loading = false,
                    onConfirm = { _, _ -> },
                    onDismiss = { dismissed = true }
                )
            }
        }

        composeTestRule.onNodeWithText("Cancel").performScrollTo().performClick()
        assertTrue(dismissed)
    }
}
