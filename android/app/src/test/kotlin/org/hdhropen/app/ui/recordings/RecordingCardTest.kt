package org.hdhropen.app.ui.recordings

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.hdhropen.app.ui.screens.recordings.RecordingCard
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunRecording
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RecordingCardTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testRecordingCardRendersMetadataAndHandlesClick() {
        var clicked = false
        val recording = HDHomeRunRecording(
            recordingId = "rec-123",
            title = "Nova",
            episodeTitle = "Secret Universe",
            seasonNumber = 50,
            episodeNumber = "2",
            provider = "hdhomerun",
            channelName = "KQED",
            durationSeconds = 3300.0,
            fileSizeBytes = 1_500_000_000L
        )

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingCard(recording = recording, onClick = { clicked = true })
            }
        }

        composeTestRule.onNodeWithText("Nova").assertIsDisplayed()
        composeTestRule.onNodeWithText("S50:E2 • Secret Universe").assertIsDisplayed()
        composeTestRule.onNodeWithText("HDHomeRun DVR").assertIsDisplayed()
        composeTestRule.onNodeWithText("55m").assertIsDisplayed()
        composeTestRule.onNodeWithText("1.4 GB").assertIsDisplayed()
        composeTestRule.onNodeWithText("KQED").assertIsDisplayed()

        composeTestRule.onNodeWithText("Nova").performClick()
        assertTrue(clicked)
    }

    @Test
    fun testRecordingCardInProgressShowsRecBadge() {
        val recording = HDHomeRunRecording(
            recordingId = "rec-456",
            title = "NFL Football",
            provider = "builtin",
            recordEnd = (System.currentTimeMillis() / 1000.0) + 3600.0
        )

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingCard(recording = recording, onClick = {})
            }
        }

        composeTestRule.onNodeWithText("NFL Football").assertIsDisplayed()
        composeTestRule.onNodeWithText("REC").assertIsDisplayed()
        composeTestRule.onNodeWithText("Built-in DVR").assertIsDisplayed()
    }
}
