package org.hdhropen.app.ui.tuners

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import io.mockk.coEvery
import io.mockk.mockk
import org.hdhropen.app.ui.screens.tuners.TunerStatusScreen
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunTuner
import org.hdhropen.kit.models.HDHomeRunTunerInfo
import org.hdhropen.kit.models.TunerClientInfo
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.TunerViewModel
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class TunerStatusScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testTunerStatusScreenEmptyState() {
        val apiClient = mockk<APIClient>(relaxed = true)
        coEvery { apiClient.getTunerStatus() } returns emptyList()
        coEvery { apiClient.getTunerInfo() } returns HDHomeRunTunerInfo()

        val tunerViewModel = TunerViewModel(apiClient)
        tunerViewModel.loadData()

        composeTestRule.setContent {
            HDHROpenTheme {
                TunerStatusScreen(tunerViewModel = tunerViewModel)
            }
        }

        composeTestRule.onNodeWithText("Tuners").assertIsDisplayed()
        composeTestRule.onNodeWithText("No HDHomeRun tuners found.").assertIsDisplayed()
    }

    @Test
    fun testTunerStatusScreenActiveTuner() {
        val apiClient = mockk<APIClient>(relaxed = true)

        val tuner0 = HDHomeRunTuner(
            index = 0,
            inUse = true,
            channelNumber = "5.1",
            channelName = "KPIX-HD",
            client = TunerClientInfo(name = "Living Room Apple TV"),
            signalStrengthPercent = 95,
            signalQualityPercent = 100,
            symbolQualityPercent = 100,
            networkRateBps = 14500000L
        )

        val info = HDHomeRunTunerInfo(
            friendlyName = "HDHomeRun CONNECT DUO",
            modelNumber = "HDHR5-2US",
            firmwareVersion = "20230713",
            tunerCount = 2
        )

        coEvery { apiClient.getTunerStatus() } returns listOf(tuner0)
        coEvery { apiClient.getTunerInfo() } returns info

        val tunerViewModel = TunerViewModel(apiClient)
        tunerViewModel.loadData()

        composeTestRule.setContent {
            HDHROpenTheme {
                TunerStatusScreen(tunerViewModel = tunerViewModel)
            }
        }

        // Verify Device Card
        composeTestRule.onNodeWithText("HDHomeRun CONNECT DUO").assertIsDisplayed()
        composeTestRule.onNodeWithText("Model: HDHR5-2US").assertIsDisplayed()
        composeTestRule.onNodeWithText("Firmware: 20230713").assertIsDisplayed()
        composeTestRule.onNodeWithText("2 Tuners").assertIsDisplayed()

        // Verify Tuner 0 (In Use)
        composeTestRule.onNodeWithText("Tuner 0").assertIsDisplayed()
        composeTestRule.onNodeWithText("IN USE").assertIsDisplayed()
        composeTestRule.onNodeWithText("Channel: 5.1 KPIX-HD").assertIsDisplayed()
        composeTestRule.onNodeWithText("Signal Strength").assertIsDisplayed()
        composeTestRule.onNodeWithText("95%").assertIsDisplayed()

        // Test refresh button click
        composeTestRule.onNodeWithContentDescription("Refresh").performClick()
    }

    @Test
    fun testTunerStatusScreenIdleTuner() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val tunerIdle = HDHomeRunTuner(index = 1, inUse = false)
        coEvery { apiClient.getTunerStatus() } returns listOf(tunerIdle)
        coEvery { apiClient.getTunerInfo() } returns HDHomeRunTunerInfo()

        val tunerViewModel = TunerViewModel(apiClient)
        tunerViewModel.loadData()

        composeTestRule.setContent {
            HDHROpenTheme {
                TunerStatusScreen(tunerViewModel = tunerViewModel)
            }
        }

        composeTestRule.onNodeWithText("Tuner 1").assertIsDisplayed()
        composeTestRule.onNodeWithText("IDLE").assertIsDisplayed()
    }
}
