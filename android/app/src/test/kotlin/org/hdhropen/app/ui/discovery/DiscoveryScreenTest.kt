package org.hdhropen.app.ui.discovery

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.media3.common.util.UnstableApi
import io.mockk.coEvery
import io.mockk.mockk
import org.hdhropen.app.ui.screens.discovery.DiscoveryScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.DiscoveryResponse
import org.hdhropen.kit.models.HDHomeRunChannelsResponse
import org.hdhropen.kit.models.HDHomeRunDvrInfo
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.DiscoveryViewModel
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.RecordingsViewModel
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@UnstableApi
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class DiscoveryScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private fun setUpScreen(items: List<HDHomeRunGuideEntry>): DiscoveryViewModel {
        val apiClient = mockk<APIClient>(relaxed = true)
        coEvery { apiClient.getDiscovery() } returns DiscoveryResponse(
            hasProfile = true,
            enabled = true,
            items = items
        )
        coEvery { apiClient.getChannels() } returns HDHomeRunChannelsResponse()
        coEvery { apiClient.getDvrInfo() } returns HDHomeRunDvrInfo()

        val discoveryViewModel = DiscoveryViewModel(apiClient)
        val guideViewModel = GuideViewModel(apiClient)
        val recordingsViewModel = RecordingsViewModel(apiClient)

        discoveryViewModel.loadData()

        composeTestRule.setContent {
            HDHROpenTheme {
                DiscoveryScreen(
                    discoveryViewModel = discoveryViewModel,
                    guideViewModel = guideViewModel,
                    recordingsViewModel = recordingsViewModel
                )
            }
        }

        return discoveryViewModel
    }

    @Test
    fun testFilterChipsNarrowListAndBackToAllRestoresEveryItem() {
        val items = listOf(
            HDHomeRunGuideEntry(title = "Personalized Drama", bucket = "shows", source = "personalized"),
            HDHomeRunGuideEntry(title = "Oscar Marathon", bucket = "movies", source = "network_pick"),
            HDHomeRunGuideEntry(title = "Lakers at Celtics", bucket = "sports", source = "favorite_team")
        )
        val discoveryViewModel = setUpScreen(items)

        composeTestRule.onNodeWithText("Personalized Drama").assertIsDisplayed()
        composeTestRule.onNodeWithText("Oscar Marathon").assertIsDisplayed()
        composeTestRule.onNodeWithText("Lakers at Celtics").assertIsDisplayed()

        composeTestRule.onNodeWithText("Sports").performClick()
        composeTestRule.onNodeWithText("Lakers at Celtics").assertIsDisplayed()
        composeTestRule.onNodeWithText("Favorite team").assertIsDisplayed()

        composeTestRule.onNodeWithText("All").performClick()
        composeTestRule.onNodeWithText("Personalized Drama").assertIsDisplayed()
        composeTestRule.onNodeWithText("Oscar Marathon").assertIsDisplayed()
        composeTestRule.onNodeWithText("Lakers at Celtics").assertIsDisplayed()
    }

    @Test
    fun testSourceBadgeShownOnlyForNonPersonalizedItems() {
        val items = listOf(
            HDHomeRunGuideEntry(title = "Personalized Drama", bucket = "shows", source = "personalized"),
            HDHomeRunGuideEntry(title = "Weekend Movie Block", bucket = "movies", source = "active_rule"),
            HDHomeRunGuideEntry(title = "Drama on NBC", bucket = "shows", source = "network_pick"),
            HDHomeRunGuideEntry(title = "Fresh Pilot", bucket = "shows", source = "new_and_notable")
        )
        setUpScreen(items)

        composeTestRule.onNodeWithText("Active rule").assertIsDisplayed()
        composeTestRule.onNodeWithText("Network pick").assertIsDisplayed()
        composeTestRule.onNodeWithText("New & notable").assertIsDisplayed()
    }
}
