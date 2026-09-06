package org.hdhropen.kit

import androidx.media3.common.PlaybackException
import androidx.media3.datasource.DataSpec
import androidx.media3.datasource.HttpDataSource
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.APIError
import org.hdhropen.kit.networking.HLSSessionResponse
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.*
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import java.io.IOException

@RunWith(RobolectricTestRunner::class)
class PlayerErrorHandlingTest {

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private val testChannel = HDHomeRunChannel(
        channelNumber = "3.3",
        name = "Outlaw",
        isHD = true,
        isDRM = false,
        streamUrl = "",
        playbackUrl = null,
        now = null,
        next = null
    )

    private val testRecording = HDHomeRunRecording(
        recordingId = "rec-123",
        title = "Test Show",
        channelNumber = "3.3",
        playUrl = "/api/dvr/recordings/rec-123/stream"
    )

    @Test
    fun `extractDetailFromBody parses JSON detail successfully`() {
        val json = """{"detail":"Tuner 2 is locked by another client. All 4 tuners in use."}"""
        val detail = extractDetailFromBody(json.toByteArray(Charsets.UTF_8))
        assertEquals("Tuner 2 is locked by another client. All 4 tuners in use.", detail)
    }

    @Test
    fun `extractDetailFromBody handles non-JSON plain text gracefully`() {
        val text = "Server temporarily busy"
        val detail = extractDetailFromBody(text.toByteArray(Charsets.UTF_8))
        assertEquals("Server temporarily busy", detail)
    }

    @Test
    fun `extractDetailFromBody returns null for HTML error bodies`() {
        val html = "<html><head><title>502 Bad Gateway</title></head><body>502 Bad Gateway</body></html>"
        val detail = extractDetailFromBody(html.toByteArray(Charsets.UTF_8))
        assertNull(detail)
    }

    @Test
    fun `parseExoPlayerError for 502 with JSON detail produces user-friendly error`() {
        val json = """{"detail":"FFmpeg failed to start: device or resource busy"}"""
        val httpEx = HttpDataSource.InvalidResponseCodeException(
            502,
            "Bad Gateway",
            null,
            emptyMap(),
            DataSpec(android.net.Uri.EMPTY),
            json.toByteArray(Charsets.UTF_8)
        )
        val playbackEx = PlaybackException(
            "Source error",
            httpEx,
            PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS
        )

        val parsed = parseExoPlayerError(playbackEx)
        assertEquals(502, parsed.statusCode)
        assertTrue(parsed.isNetworkError)
        assertTrue(parsed.message.contains("502"))
        assertEquals("FFmpeg failed to start: device or resource busy", parsed.detail)
    }

    @Test
    fun `parseExoPlayerError for 503 produces service unavailable message`() {
        val httpEx = HttpDataSource.InvalidResponseCodeException(
            503,
            "Service Unavailable",
            null,
            emptyMap(),
            DataSpec(android.net.Uri.EMPTY),
            ByteArray(0)
        )
        val playbackEx = PlaybackException(
            "Source error",
            httpEx,
            PlaybackException.ERROR_CODE_IO_BAD_HTTP_STATUS
        )

        val parsed = parseExoPlayerError(playbackEx)
        assertEquals(503, parsed.statusCode)
        assertTrue(parsed.isNetworkError)
        assertTrue(parsed.message.contains("503"))
    }

    @Test
    fun `playChannel sets Failed state with 502 details when backend returns 502`() {
        val apiClient = mockk<APIClient>()
        every { apiClient.baseURL } returns "http://localhost:8100"
        every { apiClient.bearerToken } returns null
        coEvery { apiClient.startWatch("3.3") } throws APIError.ServerError(502, "All 4 tuners in use by other clients")
        coEvery { apiClient.createChannelHLSSession("3.3", any()) } throws APIError.ServerError(502, "All 4 tuners in use by other clients")

        val engine = PlayerEngine()
        val vm = PlayerViewModel(apiClient, WatchSessionManager(apiClient), engine, CaptionController())

        vm.playChannel(testChannel)

        val state = engine.state.value
        assertTrue("State should be PlaybackState.Failed", state is PlaybackState.Failed)
        val failed = state as PlaybackState.Failed
        assertEquals(502, failed.statusCode)
        assertTrue(failed.isNetworkError)
        assertTrue(failed.message.contains("502"))
        assertEquals("All 4 tuners in use by other clients", failed.detail)
    }

    @Test
    fun `retry after 502 failure re-attempts playChannel`() {
        val apiClient = mockk<APIClient>()
        every { apiClient.baseURL } returns "http://localhost:8100"
        every { apiClient.bearerToken } returns null
        coEvery { apiClient.startWatch("3.3") } throws APIError.ServerError(502, "Tuner busy")
        coEvery { apiClient.createChannelHLSSession("3.3", any()) } throws APIError.ServerError(502, "Tuner busy")

        val engine = PlayerEngine()
        val vm = PlayerViewModel(apiClient, WatchSessionManager(apiClient), engine, CaptionController())

        vm.playChannel(testChannel)
        assertTrue(engine.state.value is PlaybackState.Failed)

        // Now mock success for retry
        coEvery { apiClient.createChannelHLSSession("3.3", any()) } returns HDHomeRunRecording(
            sessionId = "sess-recovered",
            playlistUrl = "/api/hls/sess-recovered/playlist.m3u8",
            title = "Outlaw"
        )

        vm.retry()

        assertEquals("sess-recovered", vm.activeHLSSessionId.value)
    }

    @Test
    fun `playRecording handles 502 error and allows retry`() {
        val apiClient = mockk<APIClient>()
        every { apiClient.baseURL } returns "http://localhost:8100"
        every { apiClient.bearerToken } returns null
        coEvery { apiClient.createRecordingHLSSession(any(), any(), any(), any(), any(), any()) } throws APIError.ServerError(502, "Transcoder failed")

        val engine = PlayerEngine()
        val vm = PlayerViewModel(apiClient, WatchSessionManager(apiClient), engine, CaptionController())

        vm.playRecording(testRecording)

        val state = engine.state.value
        assertTrue(state is PlaybackState.Failed)
        val failed = state as PlaybackState.Failed
        assertEquals(502, failed.statusCode)
        assertEquals("Transcoder failed", failed.detail)

        // Retry succeeds
        coEvery { apiClient.createRecordingHLSSession(any(), any(), any(), any(), any(), any()) } returns HLSSessionResponse(
            sessionId = "rec-sess-ok",
            playlistUrl = "/api/hls/rec-sess-ok/playlist.m3u8"
        )
        coEvery { apiClient.getRecordingDetail(any(), any(), any(), any(), any()) } throws RuntimeException("not stubbed")

        vm.retry()
        assertEquals("rec-sess-ok", vm.activeHLSSessionId.value)
    }
}
