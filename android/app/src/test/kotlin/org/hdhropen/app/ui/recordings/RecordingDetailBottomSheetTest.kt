package org.hdhropen.app.ui.recordings

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import io.mockk.coVerify
import io.mockk.mockk
import io.mockk.spyk
import org.hdhropen.app.ui.screens.recordings.RecordingDetailBottomSheet
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunRecording
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
class RecordingDetailBottomSheetTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testRecordingDetailCompletedRecording() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val recordingsVm = spyk(RecordingsViewModel(apiClient))

        var played = false
        var dismissed = false

        val recording = HDHomeRunRecording(
            recordingId = "rec-123",
            title = "Seinfeld",
            episodeTitle = "The Contest",
            seasonNumber = 4,
            episodeNumber = "11",
            channelName = "FOX",
            channelNumber = "2.1",
            synopsis = "The gang enters a bet about self-control.",
            start = 1700000000.0,
            recordEnd = 1700001800.0,
            durationSeconds = 1800.0,
            fileSizeBytes = 1_500_000_000L
        )

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingDetailBottomSheet(
                    recording = recording,
                    recordingsViewModel = recordingsVm,
                    onDismiss = { dismissed = true },
                    onPlay = { played = true }
                )
            }
        }

        // Details
        composeTestRule.onNodeWithText("Seinfeld").assertIsDisplayed()
        composeTestRule.onNodeWithText("• FOX").assertIsDisplayed()
        composeTestRule.onNodeWithText("The gang enters a bet about self-control.").assertIsDisplayed()

        // Play button
        composeTestRule.onNodeWithText("Play Recording").performClick()
        assertTrue(played)
        assertTrue(dismissed)

        // Delete button
        dismissed = false
        composeTestRule.onNodeWithText("Delete Recording").performClick()
        coVerify { recordingsVm.deleteRecording(recording) }
        assertTrue(dismissed)
    }

    @Test
    fun testRecordingDetailInProgressHidesDelete() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val recordingsVm = spyk(RecordingsViewModel(apiClient))

        val now = System.currentTimeMillis() / 1000.0
        val inProgressRecording = HDHomeRunRecording(
            recordingId = "rec-live",
            title = "Live Game",
            start = now - 600.0,
            recordEnd = now + 3600.0
        )

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingDetailBottomSheet(
                    recording = inProgressRecording,
                    recordingsViewModel = recordingsVm,
                    onDismiss = {},
                    onPlay = {}
                )
            }
        }

        // Delete button should not exist for in-progress recording
        composeTestRule.onNodeWithText("Delete Recording").assertDoesNotExist()
    }
}
