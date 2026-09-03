package org.hdhropen.kit

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
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
import org.junit.Before
import org.junit.Test

/** CAST-3: playChannel's HLS-session-creation calls must thread
 * `forCast = true` through to APIClient once a Cast session is connected,
 * so the backend mints a cast-token-scoped playlist_url instead of the
 * cookie/bearer-gated one it hands native players. Flips PlayerEngine's
 * private _isCasting flag via reflection (same pattern as
 * PlayerEngineCastTest/PlayerViewModelSeekResyncTest) rather than attaching
 * a real CastPlayer - the forCast flag is read and passed to APIClient
 * before loadMedia() ever branches on isCasting, so no castPlayer is needed
 * to observe it (loadMedia's cast branch simply no-ops here since
 * castPlayer stays null, mirroring PlayerEngineChannelFallbackTest's
 * existing tolerance of loadMedia being unexercised). */
class PlayerViewModelCastTest {

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

    private fun markCasting(engine: PlayerEngine) {
        val isCastingField = PlayerEngine::class.java.getDeclaredField("_isCasting").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        (isCastingField.get(engine) as MutableStateFlow<Boolean>).value = true
    }

    @Test
    fun `playChannel fallback passes forCast=true to createChannelHLSSession once a cast session is connected`() {
        val apiClient = mockk<APIClient>()
        every { apiClient.baseURL } returns "http://localhost:8000"
        every { apiClient.bearerToken } returns null
        coEvery { apiClient.startWatch("4.1") } returns null
        coEvery { apiClient.createChannelHLSSession("4.1", forCast = true) } returns HDHomeRunRecording(
            sessionId = "sess-cast",
            playlistUrl = "/api/hls/sess-cast/tok-abc/playlist.m3u8",
            title = "Channel 4.1"
        )

        val playerEngine = PlayerEngine(context = null)
        markCasting(playerEngine)
        val watchSessionManager = WatchSessionManager(apiClient)
        val vm = PlayerViewModel(apiClient, watchSessionManager, playerEngine, CaptionController())

        vm.playChannel(channel)

        coVerify { apiClient.createChannelHLSSession("4.1", forCast = true) }
    }

    @Test
    fun `playChannel without a cast session passes forCast=false`() {
        val apiClient = mockk<APIClient>()
        every { apiClient.baseURL } returns "http://localhost:8000"
        every { apiClient.bearerToken } returns null
        coEvery { apiClient.startWatch("4.1") } returns null
        coEvery { apiClient.createChannelHLSSession("4.1", forCast = false) } returns HDHomeRunRecording(
            sessionId = "sess-native",
            playlistUrl = "/api/hls/sess-native/playlist.m3u8",
            title = "Channel 4.1"
        )

        val watchSessionManager = WatchSessionManager(apiClient)
        val vm = PlayerViewModel(apiClient, watchSessionManager, PlayerEngine(context = null), CaptionController())

        vm.playChannel(channel)

        coVerify { apiClient.createChannelHLSSession("4.1", forCast = false) }
    }
}
