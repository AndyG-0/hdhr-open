package org.hdhropen.app.ui.guide

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import io.mockk.*
import kotlinx.coroutines.flow.MutableStateFlow
import org.hdhropen.app.ui.screens.guide.ProgramDetailBottomSheet
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.models.HDHomeRunRecordingRule
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ProgramDetailBottomSheetTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testProgramDetailBottomSheetNewAiringWithoutExistingRule() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val guideViewModel = spyk(GuideViewModel(apiClient))

        var tuned = false
        var dismissed = false

        val channel = HDHomeRunChannel(
            channelNumber = "5.1",
            name = "KPIX-HD",
            isHD = true
        )
        val airing = HDHomeRunGuideEntry(
            title = "Star Trek",
            episodeTitle = "The Trouble with Tribbles",
            episodeNumber = "S02E15",
            synopsis = "Kirk and crew deal with cute furry creatures that multiply rapidly.",
            start = 1700000000.0,
            end = 1700003600.0,
            isNew = true,
            hasCC = true,
            audio = "stereo",
            category = "Sci-Fi, Adventure",
            seriesId = "series-trek"
        )

        composeTestRule.setContent {
            HDHROpenTheme {
                ProgramDetailBottomSheet(
                    channel = channel,
                    airing = airing,
                    channels = listOf(channel),
                    officialDvrActive = false,
                    guideViewModel = guideViewModel,
                    onDismiss = { dismissed = true },
                    onTune = { tuned = true }
                )
            }
        }

        // Channel header
        composeTestRule.onNodeWithText("5.1").assertExists()
        composeTestRule.onNodeWithText("KPIX-HD").assertExists()

        // Title and Episode
        composeTestRule.onNodeWithText("Star Trek").assertExists()
        composeTestRule.onNodeWithText("Ep S02E15 • The Trouble with Tribbles").assertExists()
        composeTestRule.onNodeWithText("NEW").assertExists()
        composeTestRule.onNodeWithText("CC").assertExists()
        composeTestRule.onNodeWithText("Kirk and crew deal with cute furry creatures that multiply rapidly.").assertExists()

        // Favorite click
        composeTestRule.onNodeWithContentDescription("Favorite").performClick()
        verify { guideViewModel.toggleFavorite("5.1") }

        // Tune channel
        composeTestRule.onNodeWithText("Tune Channel 5.1").performScrollTo().performClick()
        assertTrue(tuned)
        assertTrue(dismissed)
    }

    @Test
    fun testProgramDetailBottomSheetRecordButtons() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val guideViewModel = spyk(GuideViewModel(apiClient))

        val channel = HDHomeRunChannel(channelNumber = "7.1", name = "KGO")
        val airing = HDHomeRunGuideEntry(title = "Jeopardy!", seriesId = "series-jeopardy", start = 1000.0)

        composeTestRule.setContent {
            HDHROpenTheme {
                ProgramDetailBottomSheet(
                    channel = channel,
                    airing = airing,
                    channels = listOf(channel),
                    officialDvrActive = false,
                    guideViewModel = guideViewModel,
                    onDismiss = {},
                    onTune = {}
                )
            }
        }

        // Record Episode
        composeTestRule.onNodeWithText("Record Ep").performScrollTo().performClick()
        coVerify { guideViewModel.recordEpisode(seriesId = "series-jeopardy", channelNumber = "7.1", start = 1000.0) }

        // Record Series
        composeTestRule.onNodeWithText("Record Series").performScrollTo().performClick()
        coVerify { guideViewModel.recordSeries(seriesId = "series-jeopardy", channelNumber = "7.1") }
    }

    @Test
    fun testProgramDetailBottomSheetExistingRuleState() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val guideViewModel = spyk(GuideViewModel(apiClient))

        val channel = HDHomeRunChannel(channelNumber = "9.1", name = "KQED")
        val airing = HDHomeRunGuideEntry(title = "Nova", seriesId = "series-nova")
        val rule = HDHomeRunRecordingRule(
            recordingRuleId = "rule-nova",
            seriesId = "series-nova",
            title = "Nova",
            channelOnly = "9.1"
        )

        val rulesFlow = MutableStateFlow(listOf(rule))
        every { guideViewModel.recordingRules } returns rulesFlow
        every { guideViewModel.findRule("9.1", any()) } returns rule
        coEvery { guideViewModel.cancelRule(any()) } just Runs

        composeTestRule.setContent {
            HDHROpenTheme {
                ProgramDetailBottomSheet(
                    channel = channel,
                    airing = airing,
                    channels = listOf(channel),
                    officialDvrActive = false,
                    guideViewModel = guideViewModel,
                    onDismiss = {},
                    onTune = {}
                )
            }
        }

        // Cancel Recording button should appear
        composeTestRule.onNodeWithText("Cancel Recording (Series)").performScrollTo().performClick()
        coVerify { guideViewModel.cancelRule("rule-nova") }
    }
}
