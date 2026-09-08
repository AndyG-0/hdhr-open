package org.hdhropen.app.ui.guide

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import org.hdhropen.app.ui.screens.guide.RecordingOptionsBottomSheet
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.models.RecordingRuleOptions
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RecordingOptionsBottomSheetTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testRecordingOptionsNewRuleCreation() {
        val channel1 = HDHomeRunChannel(channelNumber = "5.1", name = "KPIX")
        val channel2 = HDHomeRunChannel(channelNumber = "7.1", name = "KGO")
        val airing = HDHomeRunGuideEntry(
            title = "NFL Football",
            episodeTitle = "49ers vs Chiefs",
            seriesId = "series-nfl"
        )

        var confirmedSeries: Boolean? = null
        var confirmedOptions: RecordingRuleOptions? = null
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingOptionsBottomSheet(
                    channel = channel1,
                    airing = airing,
                    channels = listOf(channel1, channel2),
                    canRecordSeries = true,
                    officialDvrActive = false,
                    existingRule = null,
                    onConfirm = { isSeries, options ->
                        confirmedSeries = isSeries
                        confirmedOptions = options
                    },
                    onCancelRule = null,
                    onDismiss = { dismissed = true }
                )
            }
        }

        composeTestRule.onNodeWithText("Recording Options").assertExists()
        composeTestRule.onNodeWithText("NFL Football").assertExists()

        // Test use episode title as keyword
        composeTestRule.onNodeWithText("+ Use \"49ers vs Chiefs\" as keyword").performScrollTo().performClick()

        // Toggle title match to contains
        composeTestRule.onNodeWithText("Title contains").performScrollTo().performClick()

        // Toggle new episodes only
        composeTestRule.onNodeWithText("New episodes only").performScrollTo().performClick()

        // Toggle retention mode to Keep last N
        composeTestRule.onNodeWithText("Keep last N").performScrollTo().performClick()

        // Confirm Record Series
        composeTestRule.onNodeWithText("Record Series (with keywords)").performScrollTo().performClick()

        assertTrue(dismissed)
        assertEquals(true, confirmedSeries)
        assertNotNull(confirmedOptions)
        assertEquals("contains", confirmedOptions?.titleMatchMode)
        assertEquals("49ers vs Chiefs", confirmedOptions?.keywordQuery)
        assertEquals(true, confirmedOptions?.recentOnly)
        assertEquals("builtin", confirmedOptions?.server)
        assertEquals(3, confirmedOptions?.maxEpisodesToKeep)
    }

    @Test
    fun testRecordingOptionsExistingRuleUpdateAndCancel() {
        val channel = HDHomeRunChannel(channelNumber = "11.1", name = "KNTV")
        val airing = HDHomeRunGuideEntry(title = "Nightly News")
        val existingRule = HDHomeRunRecordingRule(
            recordingRuleId = "rule-news",
            seriesId = "series-news",
            title = "Nightly News",
            channelOnly = "11.1",
            startPadding = 120,
            endPadding = 300,
            maxEpisodesToKeep = 5,
            recentOnly = 1
        )

        var cancelled = false
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingOptionsBottomSheet(
                    channel = channel,
                    airing = airing,
                    channels = listOf(channel),
                    canRecordSeries = false,
                    officialDvrActive = true,
                    existingRule = existingRule,
                    onConfirm = { _, _ -> },
                    onCancelRule = { cancelled = true },
                    onDismiss = { dismissed = true }
                )
            }
        }

        // Verify existing rule button label
        composeTestRule.onNodeWithText("Update Series Recording").assertExists()

        // Test Cancel Recording button
        composeTestRule.onNodeWithText("Cancel Recording").performScrollTo().performClick()
        assertTrue(cancelled)
        assertTrue(dismissed)
    }
}
