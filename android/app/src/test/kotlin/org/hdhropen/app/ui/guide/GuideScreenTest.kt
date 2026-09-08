package org.hdhropen.app.ui.guide

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.media3.common.util.UnstableApi
import io.mockk.coEvery
import io.mockk.mockk
import org.hdhropen.app.ui.screens.guide.GuideScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunChannelsResponse
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.hdhropen.kit.viewmodels.RecordingsViewModel
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@UnstableApi
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class GuideScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testGuideScreenTopBarAndActions() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val channel = HDHomeRunChannel(
            channelNumber = "7.1",
            name = "KGO-HD",
            streamUrl = "http://tuner/stream/ch7.1"
        )
        coEvery { apiClient.getChannels() } returns HDHomeRunChannelsResponse(channels = listOf(channel))
        coEvery { apiClient.getGuide() } returns emptyList()

        val guideViewModel = GuideViewModel(apiClient)
        val recordingsViewModel = RecordingsViewModel(apiClient)
        val playerViewModel = mockk<PlayerViewModel>(relaxed = true)

        guideViewModel.loadData()

        composeTestRule.setContent {
            HDHROpenTheme {
                GuideScreen(
                    guideViewModel = guideViewModel,
                    recordingsViewModel = recordingsViewModel,
                    playerViewModel = playerViewModel
                )
            }
        }

        // Top bar
        composeTestRule.onNodeWithText("Live Guide").assertIsDisplayed()

        // Favorites toggle
        assertFalse(guideViewModel.filterOnlyFavorites.value)
        composeTestRule.onNodeWithContentDescription("Filter Favorites").performClick()
        assertTrue(guideViewModel.filterOnlyFavorites.value)

        // AI Assistant button
        composeTestRule.onNodeWithContentDescription("AI Assistant").assertIsDisplayed()

        // Refresh Guide button
        composeTestRule.onNodeWithContentDescription("Refresh Guide").assertIsDisplayed()

        // Search text field
        composeTestRule.onNodeWithText("Search channels or shows").assertIsDisplayed()
    }
}
