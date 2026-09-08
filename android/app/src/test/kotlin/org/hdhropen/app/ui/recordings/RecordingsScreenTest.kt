package org.hdhropen.app.ui.recordings

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.media3.common.util.UnstableApi
import io.mockk.coEvery
import io.mockk.mockk
import org.hdhropen.app.ui.screens.recordings.RecordingsScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.hdhropen.kit.viewmodels.RecordingCategoryFilter
import org.hdhropen.kit.viewmodels.RecordingsViewModel
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@UnstableApi
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RecordingsScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testRecordingsScreenEmptyState() {
        val apiClient = mockk<APIClient>(relaxed = true)
        coEvery { apiClient.listRecordings() } returns emptyList()

        val recordingsViewModel = RecordingsViewModel(apiClient)
        val guideViewModel = GuideViewModel(apiClient)
        val playerViewModel = mockk<PlayerViewModel>(relaxed = true)

        recordingsViewModel.loadData()

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingsScreen(
                    recordingsViewModel = recordingsViewModel,
                    guideViewModel = guideViewModel,
                    playerViewModel = playerViewModel
                )
            }
        }

        // Header
        composeTestRule.onNodeWithText("Recordings").assertIsDisplayed()

        // Filter chips
        composeTestRule.onNodeWithText("All").assertIsDisplayed()
        composeTestRule.onNodeWithText("Shows").assertIsDisplayed()
        composeTestRule.onNodeWithText("Movies").assertIsDisplayed()
        composeTestRule.onNodeWithText("Sports").assertIsDisplayed()

        // Filter interaction
        composeTestRule.onNodeWithText("Shows").performClick()
        assertEquals(RecordingCategoryFilter.SHOWS, recordingsViewModel.selectedFilter.value)

        // Empty state message
        composeTestRule.onNodeWithText("No recordings found.").assertIsDisplayed()
    }

    @Test
    fun testRecordingsScreenWithRecordings() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val recording = HDHomeRunRecording(
            recordingId = "rec-1",
            title = "Planet Earth III",
            channelName = "BBC America",
            durationSeconds = 3600.0
        )
        coEvery { apiClient.listRecordings() } returns listOf(recording)

        val recordingsViewModel = RecordingsViewModel(apiClient)
        val guideViewModel = GuideViewModel(apiClient)
        val playerViewModel = mockk<PlayerViewModel>(relaxed = true)

        recordingsViewModel.loadData()

        composeTestRule.setContent {
            HDHROpenTheme {
                RecordingsScreen(
                    recordingsViewModel = recordingsViewModel,
                    guideViewModel = guideViewModel,
                    playerViewModel = playerViewModel
                )
            }
        }

        composeTestRule.onNodeWithText("Planet Earth III").assertIsDisplayed()
    }
}
