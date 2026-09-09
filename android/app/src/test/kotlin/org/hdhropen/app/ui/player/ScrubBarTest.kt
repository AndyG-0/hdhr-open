package org.hdhropen.app.ui.player

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import org.hdhropen.app.ui.screens.player.ScrubBar
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.junit.Assert.*
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

    @Test
    fun testScrubBarTapToSeek() {
        var seekTarget: Double? = null
        composeTestRule.setContent {
            HDHROpenTheme {
                ScrubBar(
                    currentTime = 0.0,
                    duration = 3600.0,
                    isLive = false,
                    isSeekable = true,
                    thumbnailCues = emptyList(),
                    onSeek = { seekTarget = it }
                )
            }
        }

        composeTestRule.onNodeWithTag("ScrubBarTrack").performTouchInput {
            click(percentOffset(0.5f, 0.5f))
        }

        assertNotNull(seekTarget)
        assertEquals(1800.0, seekTarget!!, 50.0)
    }

    @Test
    fun testScrubBarDragToSeekAndScrubbingState() {
        var seekTarget: Double? = null
        val scrubbingStates = mutableListOf<Boolean>()

        composeTestRule.setContent {
            HDHROpenTheme {
                ScrubBar(
                    currentTime = 300.0,
                    duration = 3600.0,
                    isLive = false,
                    isSeekable = true,
                    thumbnailCues = emptyList(),
                    onSeek = { seekTarget = it },
                    onScrubbingStateChange = { scrubbingStates.add(it) }
                )
            }
        }

        composeTestRule.onNodeWithTag("ScrubBarTrack").performTouchInput {
            down(percentOffset(0.25f, 0.5f))
            moveTo(percentOffset(0.75f, 0.5f))
            up()
        }

        assertNotNull(seekTarget)
        assertEquals(2700.0, seekTarget!!, 50.0)
        assertEquals(listOf(true, false), scrubbingStates)
    }

    @Test
    fun testScrubBarNoSeekWhenNotSeekable() {
        var seekTarget: Double? = null

        composeTestRule.setContent {
            HDHROpenTheme {
                ScrubBar(
                    currentTime = 50.0,
                    duration = 3600.0,
                    isLive = false,
                    isSeekable = false,
                    thumbnailCues = emptyList(),
                    onSeek = { seekTarget = it }
                )
            }
        }

        composeTestRule.onNodeWithTag("ScrubBarTrack").performTouchInput {
            click(percentOffset(0.5f, 0.5f))
        }

        assertNull(seekTarget)
    }

    @Test
    fun testScrubBarNoSeekWhenZeroDuration() {
        var seekTarget: Double? = null

        composeTestRule.setContent {
            HDHROpenTheme {
                ScrubBar(
                    currentTime = 0.0,
                    duration = 0.0,
                    isLive = true,
                    isSeekable = true,
                    thumbnailCues = emptyList(),
                    onSeek = { seekTarget = it }
                )
            }
        }

        composeTestRule.onNodeWithTag("ScrubBarTrack").performTouchInput {
            click(percentOffset(0.5f, 0.5f))
        }

        assertNull(seekTarget)
    }
}
