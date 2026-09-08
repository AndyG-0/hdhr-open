package org.hdhropen.app.ui.player

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import org.hdhropen.app.ui.screens.player.ScrubBar
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ScrubBarTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testScrubBarRecordedMediaClocks() {
        composeTestRule.setContent {
            HDHROpenTheme {
                ScrubBar(
                    currentTime = 125.0, // 2:05
                    duration = 3600.0,   // 1:00:00
                    isLive = false,
                    isSeekable = true,
                    thumbnailCues = emptyList(),
                    onSeek = {}
                )
            }
        }

        composeTestRule.onNodeWithText("2:05").assertIsDisplayed()
        composeTestRule.onNodeWithText("1:00:00").assertIsDisplayed()
    }

    @Test
    fun testScrubBarLiveMediaShowsLiveIndicator() {
        composeTestRule.setContent {
            HDHROpenTheme {
                ScrubBar(
                    currentTime = 50.0,
                    duration = 0.0,
                    isLive = true,
                    isSeekable = false,
                    thumbnailCues = emptyList(),
                    onSeek = {}
                )
            }
        }

        composeTestRule.onNodeWithText("LIVE").assertIsDisplayed()
    }
}
