package org.hdhropen.app.ui.player

import android.app.Activity
import android.app.PictureInPictureParams
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import io.mockk.*
import kotlinx.coroutines.flow.MutableStateFlow
import org.hdhropen.app.ui.screens.player.PlayerScreen
import org.hdhropen.app.ui.screens.player.enterPictureInPictureMode
import org.hdhropen.app.ui.screens.player.findActivity
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.CaptionController
import org.hdhropen.kit.playback.PlaybackState
import org.hdhropen.kit.playback.PlayerEngine
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.hdhropen.kit.viewmodels.RecordingsViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PlayerScreenTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    private var activeVm: PlayerViewModel? = null

    @After
    fun tearDown() {
        activeVm?.closePlayer()
        activeVm = null
    }

    private class MockPlayerHolder {
        val apiClient = APIClient("http://localhost:8000")
        val watchSessionManager = mockk<WatchSessionManager>(relaxed = true)
        val playerEngine = spyk(PlayerEngine())
        val captionController = CaptionController()

        val stateFlow = MutableStateFlow<PlaybackState>(PlaybackState.Idle)
        val availableAudioTracksFlow = MutableStateFlow<List<HDHomeRunRecordingAudioInfo>>(emptyList())
        val currentAudioTrackFlow = MutableStateFlow<HDHomeRunRecordingAudioInfo?>(null)

        val playerVm: PlayerViewModel
        val guideVm: GuideViewModel
        val recordingsVm: RecordingsViewModel

        init {
            every { playerEngine.state } returns stateFlow
            every { playerEngine.availableAudioTracks } returns availableAudioTracksFlow
            every { playerEngine.currentAudioTrack } returns currentAudioTrackFlow

            playerVm = spyk(PlayerViewModel(apiClient, watchSessionManager, playerEngine, captionController))
            guideVm = spyk(GuideViewModel(apiClient))
            recordingsVm = spyk(RecordingsViewModel(apiClient))

            coEvery { guideVm.recordEpisode(any(), any(), any(), any()) } returns Unit
            coEvery { guideVm.recordSeries(any(), any(), any()) } returns Unit
            coEvery { guideVm.cancelRule(any()) } returns Unit
            coEvery { recordingsVm.loadDvrInfo() } returns Unit
            coEvery { recordingsVm.loadRules() } returns Unit
        }
    }

    @Test
    fun testFindActivityHelper() {
        val mockActivity = mockk<Activity>()
        val directContext = mockActivity as Context
        assertEquals(mockActivity, directContext.findActivity())

        val wrapperContext = ContextWrapper(mockActivity)
        assertEquals(mockActivity, wrapperContext.findActivity())

        val mockPlainContext = mockk<Context>()
        assertNull(mockPlainContext.findActivity())
    }

    @Test
    fun testEnterPictureInPictureModeHelper() {
        val mockActivity = mockk<Activity>()
        val params = PictureInPictureParams.Builder().build()

        every { mockActivity.enterPictureInPictureMode(params) } returns true
        assertTrue(enterPictureInPictureMode(mockActivity, params))

        every { mockActivity.enterPictureInPictureMode(params) } throws RuntimeException("PiP not supported")
        assertFalse(enterPictureInPictureMode(mockActivity, params))
    }

    @Test
    fun testPlayerScreenPlayingStateWithControls() {
        composeTestRule.mainClock.autoAdvance = false

        val holder = MockPlayerHolder()
        activeVm = holder.playerVm
        var dismissed = false

        holder.stateFlow.value = PlaybackState.Playing

        val channel = HDHomeRunChannel(channelNumber = "5.1", name = "KPIX-HD")
        val airing = HDHomeRunGuideEntry(title = "Evening News", episodeTitle = "Special Report", seriesId = "series-99")
        every { holder.playerVm.activeChannel } returns MutableStateFlow(channel)
        every { holder.playerVm.activeAiring } returns MutableStateFlow(airing)
        every { holder.playerVm.mediaTitle } returns "Evening News"
        every { holder.playerVm.mediaSubtitle } returns "Special Report"

        composeTestRule.setContent {
            HDHROpenTheme {
                PlayerScreen(
                    playerViewModel = holder.playerVm,
                    guideViewModel = holder.guideVm,
                    recordingsViewModel = holder.recordingsVm,
                    onDismiss = { dismissed = true }
                )
            }
        }
        composeTestRule.mainClock.advanceTimeByFrame()

        // Title and Subtitle
        composeTestRule.onNodeWithText("Evening News").assertExists()
        composeTestRule.onNodeWithText("Special Report").assertExists()

        // Play/Pause button
        composeTestRule.onNodeWithContentDescription("Play/Pause").assertExists()
        composeTestRule.onNodeWithContentDescription("Play/Pause").performClick()
        verify { holder.playerVm.togglePlayPause() }

        // Close button
        composeTestRule.onNodeWithContentDescription("Close").performClick()
        assertTrue(dismissed)
        verify { holder.playerVm.closePlayer() }
    }

    @Test
    fun testPlayerScreenLoadingStateWithQuips() {
        composeTestRule.mainClock.autoAdvance = false

        val holder = MockPlayerHolder()
        activeVm = holder.playerVm
        holder.stateFlow.value = PlaybackState.Loading

        composeTestRule.setContent {
            HDHROpenTheme {
                PlayerScreen(
                    playerViewModel = holder.playerVm,
                    guideViewModel = holder.guideVm,
                    recordingsViewModel = holder.recordingsVm,
                    onDismiss = {}
                )
            }
        }
        composeTestRule.mainClock.advanceTimeByFrame()

        // Circular progress should exist during loading
        composeTestRule.onNode(hasProgressBarRangeInfo(ProgressBarRangeInfo.Indeterminate)).assertExists()
    }

    @Test
    fun testPlayerScreenFailedState() {
        composeTestRule.mainClock.autoAdvance = false

        val holder = MockPlayerHolder()
        activeVm = holder.playerVm
        var dismissed = false

        holder.stateFlow.value = PlaybackState.Failed(
            message = "Connection timeout",
            statusCode = 504,
            isNetworkError = true,
            detail = "Gateway timed out reaching tuner"
        )

        composeTestRule.setContent {
            HDHROpenTheme {
                PlayerScreen(
                    playerViewModel = holder.playerVm,
                    guideViewModel = holder.guideVm,
                    recordingsViewModel = holder.recordingsVm,
                    onDismiss = { dismissed = true }
                )
            }
        }
        composeTestRule.mainClock.advanceTimeByFrame()

        composeTestRule.onNodeWithText("Server / Tuner Unavailable").assertExists()
        composeTestRule.onNodeWithText("Connection timeout").assertExists()
        composeTestRule.onNodeWithText("Gateway timed out reaching tuner").assertExists()

        // Retry button
        composeTestRule.onNodeWithText("Retry").performClick()
        verify { holder.playerVm.retry() }

        // Close button
        composeTestRule.onNodeWithText("Close").performClick()
        assertTrue(dismissed)
    }

    @Test
    fun testPlayerScreenTopBarDialogToggles() {
        composeTestRule.mainClock.autoAdvance = false

        val holder = MockPlayerHolder()
        activeVm = holder.playerVm
        var pipEntered = false

        holder.stateFlow.value = PlaybackState.Playing
        val channel = HDHomeRunChannel(channelNumber = "2.1", name = "KTVU")
        val airing = HDHomeRunGuideEntry(title = "Morning Show")
        every { holder.playerVm.activeChannel } returns MutableStateFlow(channel)
        every { holder.playerVm.activeAiring } returns MutableStateFlow(airing)
        every { holder.playerVm.mediaTitle } returns "Morning Show"

        composeTestRule.setContent {
            HDHROpenTheme {
                PlayerScreen(
                    playerViewModel = holder.playerVm,
                    guideViewModel = holder.guideVm,
                    recordingsViewModel = holder.recordingsVm,
                    onDismiss = {},
                    onEnterPip = { pipEntered = true }
                )
            }
        }
        composeTestRule.mainClock.advanceTimeByFrame()

        // PiP button
        composeTestRule.onNodeWithContentDescription("Picture-in-Picture").performClick()
        assertTrue(pipEntered)

        // Captions toggle
        composeTestRule.onNodeWithContentDescription("Captions").performClick()
        assertTrue(holder.playerVm.captionController.isEnabled.value)

        // Playback Info toggle
        composeTestRule.onNodeWithContentDescription("Playback Info").performClick()
        composeTestRule.mainClock.advanceTimeByFrame()
        composeTestRule.onNodeWithText("Playback Info").assertExists()
        // Close playback info dialog
        composeTestRule.onAllNodesWithContentDescription("Close").onLast().performClick()
        composeTestRule.mainClock.advanceTimeByFrame()

        // SyncPlay toggle
        composeTestRule.onNodeWithContentDescription("SyncPlay Watch Party").performClick()
        composeTestRule.mainClock.advanceTimeByFrame()
        composeTestRule.onNodeWithText("SyncPlay Watch Party").assertExists()
    }

    @Test
    fun testPlayerScreenAudioTrackSelection() {
        composeTestRule.mainClock.autoAdvance = false

        val holder = MockPlayerHolder()
        activeVm = holder.playerVm
        holder.stateFlow.value = PlaybackState.Playing

        val track1 = HDHomeRunRecordingAudioInfo(index = 0, codec = "ac3", channels = 6, language = "eng")
        val track2 = HDHomeRunRecordingAudioInfo(index = 1, codec = "ac3", channels = 2, language = "spa")
        holder.availableAudioTracksFlow.value = listOf(track1, track2)
        holder.currentAudioTrackFlow.value = track1

        composeTestRule.setContent {
            HDHROpenTheme {
                PlayerScreen(
                    playerViewModel = holder.playerVm,
                    guideViewModel = holder.guideVm,
                    recordingsViewModel = holder.recordingsVm,
                    onDismiss = {}
                )
            }
        }
        composeTestRule.mainClock.advanceTimeByFrame()

        // Click audio track button to open menu
        composeTestRule.onNodeWithContentDescription("Audio Tracks").performClick()
        composeTestRule.mainClock.advanceTimeByFrame()
        composeTestRule.onNodeWithText(track2.displayLabel).performClick()
        verify { holder.playerVm.selectAudioTrack(track2) }
    }

    @Test
    fun testPlayerScreenWatchSessionRecordActions() {
        composeTestRule.mainClock.autoAdvance = false

        val holder = MockPlayerHolder()
        activeVm = holder.playerVm
        holder.stateFlow.value = PlaybackState.Playing

        val channel = HDHomeRunChannel(channelNumber = "4.1", name = "KRON")
        val airing = HDHomeRunGuideEntry(title = "Local News", seriesId = "series-4")
        every { holder.playerVm.activeChannel } returns MutableStateFlow(channel)
        every { holder.playerVm.activeAiring } returns MutableStateFlow(airing)
        every { holder.playerVm.mediaTitle } returns "Local News"

        // Simulate active watch session
        val isWatchSessionFlow = MutableStateFlow(true)
        val isPromotedFlow = MutableStateFlow(false)
        every { holder.playerVm.isWatchSession } returns isWatchSessionFlow
        every { holder.playerVm.isPromoted } returns isPromotedFlow

        composeTestRule.setContent {
            HDHROpenTheme {
                PlayerScreen(
                    playerViewModel = holder.playerVm,
                    guideViewModel = holder.guideVm,
                    recordingsViewModel = holder.recordingsVm,
                    onDismiss = {}
                )
            }
        }
        composeTestRule.mainClock.advanceTimeByFrame()

        // Click record button to open dropdown
        composeTestRule.onNodeWithContentDescription("Record").performClick()
        composeTestRule.mainClock.advanceTimeByFrame()
        composeTestRule.onNodeWithText("Save Current Recording").performClick()
        verify { holder.playerVm.promoteToRecording() }

        // Open menu again and record episode
        composeTestRule.onNodeWithContentDescription("Record").performClick()
        composeTestRule.mainClock.advanceTimeByFrame()
        composeTestRule.onNodeWithText("Record Episode").performClick()
        coVerify { holder.guideVm.recordEpisode(seriesId = "series-4", channelNumber = "4.1", start = any()) }
    }

    @Test
    fun testPlayerScreenShowsTransientErrorSnackbar() {
        composeTestRule.mainClock.autoAdvance = false

        val holder = MockPlayerHolder()
        activeVm = holder.playerVm
        holder.stateFlow.value = PlaybackState.Playing

        val transientErrorFlow = MutableStateFlow<String?>("Failed to switch audio track: Audio index 2 not available")
        every { holder.playerVm.transientError } returns transientErrorFlow

        composeTestRule.setContent {
            HDHROpenTheme {
                PlayerScreen(
                    playerViewModel = holder.playerVm,
                    guideViewModel = holder.guideVm,
                    recordingsViewModel = holder.recordingsVm,
                    onDismiss = {}
                )
            }
        }
        composeTestRule.mainClock.advanceTimeBy(500)

        composeTestRule.onNodeWithText("Failed to switch audio track: Audio index 2 not available").assertExists()
        verify { holder.playerVm.clearTransientError() }
    }

    @Test
    fun testPlayerScreenShowsFallbackNoticeSnackbar() {
        composeTestRule.mainClock.autoAdvance = false

        val holder = MockPlayerHolder()
        activeVm = holder.playerVm
        holder.stateFlow.value = PlaybackState.Playing

        val fallbackNoticeFlow = MutableStateFlow<String?>("Watch session buffering is unavailable on this device. Playing direct stream instead.")
        every { holder.playerVm.fallbackNotice } returns fallbackNoticeFlow

        composeTestRule.setContent {
            HDHROpenTheme {
                PlayerScreen(
                    playerViewModel = holder.playerVm,
                    guideViewModel = holder.guideVm,
                    recordingsViewModel = holder.recordingsVm,
                    onDismiss = {}
                )
            }
        }
        composeTestRule.mainClock.advanceTimeBy(500)

        composeTestRule.onNodeWithText("Watch session buffering is unavailable on this device. Playing direct stream instead.").assertExists()
        verify { holder.playerVm.clearFallbackNotice() }
    }
}
