package org.hdhropen.app.ui.player

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import org.hdhropen.app.ui.screens.player.PlaybackInfoDialog
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunRecordingAudioInfo
import org.hdhropen.kit.models.HDHomeRunRecordingVideoInfo
import org.hdhropen.kit.models.HDHomeRunTranscodeInfo
import org.hdhropen.kit.viewmodels.PlaybackMode
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PlaybackInfoDialogTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun testPlaybackInfoDialogDirectMode() {
        var dismissed = false

        composeTestRule.setContent {
            HDHROpenTheme {
                PlaybackInfoDialog(
                    playbackMode = PlaybackMode.Direct,
                    transcodeInfo = null,
                    videoSpecs = HDHomeRunRecordingVideoInfo(
                        codec = "h264",
                        width = 1920,
                        height = 1080,
                        fps = 29.97
                    ),
                    audioTracks = listOf(
                        HDHomeRunRecordingAudioInfo(index = 0, codec = "ac3", channels = 6)
                    ),
                    observedBitrateBps = 8_500_000L,
                    onDismiss = { dismissed = true }
                )
            }
        }

        composeTestRule.onNodeWithText("Playback Info").assertExists()
        composeTestRule.onNodeWithText("Playback").assertExists()
        composeTestRule.onNodeWithText("Direct (client-side)").assertExists()

        // Video Specs
        composeTestRule.onNodeWithText("Video").assertExists()
        composeTestRule.onNodeWithText("H264").assertExists()
        composeTestRule.onNodeWithText("1920×1080").assertExists()
        composeTestRule.onNodeWithText("29 fps").assertExists()

        // Audio Specs
        composeTestRule.onNodeWithText("Audio").assertExists()
        composeTestRule.onNodeWithText("AC3 · 6ch").assertExists()

        // Bitrate
        composeTestRule.onNodeWithText("Network").assertExists()
        composeTestRule.onNodeWithText("8.5 Mbps").assertExists()

        // Dismiss
        composeTestRule.onNodeWithContentDescription("Close").performClick()
        assertTrue(dismissed)
    }

    @Test
    fun testPlaybackInfoDialogTranscodedModeWithHW() {
        composeTestRule.setContent {
            HDHROpenTheme {
                PlaybackInfoDialog(
                    playbackMode = PlaybackMode.ServerTranscodedHls,
                    transcodeInfo = HDHomeRunTranscodeInfo(
                        preset = "1080p-30fps",
                        presetLabel = "1080p 30fps",
                        hardware = true
                    ),
                    videoSpecs = null,
                    audioTracks = emptyList(),
                    observedBitrateBps = null,
                    onDismiss = {}
                )
            }
        }

        composeTestRule.onNodeWithText("Server transcoded via 1080p 30fps (HW)").assertExists()
    }

    @Test
    fun testPlaybackInfoDialogTranscodedModeWithoutPreset() {
        composeTestRule.setContent {
            HDHROpenTheme {
                PlaybackInfoDialog(
                    playbackMode = PlaybackMode.ServerTranscodedHls,
                    transcodeInfo = null,
                    videoSpecs = null,
                    audioTracks = emptyList(),
                    observedBitrateBps = null,
                    onDismiss = {}
                )
            }
        }

        composeTestRule.onNodeWithText("Server transcoded (HLS)").assertExists()
    }

    @Test
    fun testPlaybackInfoDialogNullMode() {
        composeTestRule.setContent {
            HDHROpenTheme {
                PlaybackInfoDialog(
                    playbackMode = null,
                    transcodeInfo = null,
                    videoSpecs = null,
                    audioTracks = emptyList(),
                    observedBitrateBps = null,
                    onDismiss = {}
                )
            }
        }

        composeTestRule.onNodeWithText("Unknown").assertExists()
    }
}
