package org.hdhropen.kit

import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.CaptionController
import org.hdhropen.kit.playback.PlayerEngine
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/** CC-2: the busy-tuner direct-HLS fallback now backs the stream with a
 * real (temporary) capture when the backend can arrange one, so this
 * exercises `playChannel`'s fallback branch (case 2) with a mocked
 * `APIClient` to confirm it picks up the returned recording metadata
 * (and captions wiring via `loadRecordingMetadata`) instead of always
 * discarding it as before. */
class PlayerViewModelChannelFallbackTest {

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private val channel = HDHomeRunChannel(
        channelNumber = "4.1",
        name = "Test Channel",
        isHD = true,
        isDRM = false,
        streamUrl = "",
        playbackUrl = null,
        now = null,
        next = null
    )

    private fun newViewModel(apiClient: APIClient): PlayerViewModel {
        val watchSessionManager = WatchSessionManager(apiClient)
        return PlayerViewModel(apiClient, watchSessionManager, PlayerEngine(), CaptionController())
    }

    @Test
    fun `playChannel fallback loads recording metadata when backend returns a real capture`() {
        val apiClient = mockk<APIClient>()
        every { apiClient.baseURL } returns "http://localhost:8000"
        every { apiClient.bearerToken } returns null
        coEvery { apiClient.startWatch("4.1") } returns null
        coEvery { apiClient.createChannelHLSSession("4.1") } returns HDHomeRunRecording(
            recordingId = "rec_fallback",
            sessionId = "sess-123",
            playlistUrl = "/api/hls/sess-123/playlist.m3u8",
            title = "Test Channel",
            channelNumber = "4.1",
            playUrl = "/recorded/rec_fallback",
            hasCaptions = true
        )
        coEvery { apiClient.getRecordingDetail(any(), any(), any(), any(), any()) } throws RuntimeException("not stubbed")

        val vm = newViewModel(apiClient)
        vm.playChannel(channel)

        assertEquals("sess-123", vm.activeHLSSessionId.value)
        assertFalse(vm.isWatchSession.value)
        assertEquals("rec_fallback", vm.activeRecording.value?.recordingId)
    }

    @Test
    fun `playChannel fallback without a capture leaves activeRecording null`() {
        val apiClient = mockk<APIClient>()
        every { apiClient.baseURL } returns "http://localhost:8000"
        every { apiClient.bearerToken } returns null
        coEvery { apiClient.startWatch("4.1") } returns null
        coEvery { apiClient.createChannelHLSSession("4.1") } returns HDHomeRunRecording(
            sessionId = "sess-456",
            playlistUrl = "/api/hls/sess-456/playlist.m3u8",
            title = "Channel 4.1"
        )

        val vm = newViewModel(apiClient)
        vm.playChannel(channel)

        assertEquals("sess-456", vm.activeHLSSessionId.value)
        assertNull(vm.activeRecording.value)
    }
}
