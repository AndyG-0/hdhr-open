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
import org.hdhropen.kit.networking.HLSSessionResponse
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.CaptionController
import org.hdhropen.kit.playback.PlaybackPreferences
import org.hdhropen.kit.playback.PlayerEngine
import org.hdhropen.kit.playback.QualityPreference
import org.hdhropen.kit.viewmodels.PlaybackMode
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * Covers selectQuality()/switchToQuality() (manual picker, parity with
 * selectAudioTrack()) and the auto-quality poll's buffer-drain gate - the
 * same root-cause fix as HDHomeRunPlayer.svelte's `isBufferDraining()`,
 * ported to Android: a throughput dip must never trigger a downgrade on its
 * own unless the buffer ahead of the playhead is also shrinking.
 */
class PlayerViewModelQualityTest {

    private var activeVm: PlayerViewModel? = null

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        activeVm?.closePlayer()
        activeVm = null
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

    private fun newViewModel(apiClient: APIClient, playerEngine: PlayerEngine = PlayerEngine(context = null)): PlayerViewModel {
        every { apiClient.baseURL } returns "http://localhost:8000"
        val watchSessionManager = WatchSessionManager(apiClient)
        val vm = PlayerViewModel(apiClient, watchSessionManager, playerEngine, CaptionController(), playbackPreferences = PlaybackPreferences())
        activeVm = vm
        return vm
    }

    @Suppress("UNCHECKED_CAST")
    private fun <T> stateFlowField(target: Any, name: String): MutableStateFlow<T> {
        val field = target.javaClass.getDeclaredField(name).apply { isAccessible = true }
        return field.get(target) as MutableStateFlow<T>
    }

    private fun setPlaybackMode(vm: PlayerViewModel, mode: PlaybackMode?) {
        stateFlowField<PlaybackMode?>(vm, "_playbackMode").value = mode
    }

    private fun setActiveChannel(vm: PlayerViewModel, value: HDHomeRunChannel?) {
        stateFlowField<HDHomeRunChannel?>(vm, "_activeChannel").value = value
    }

    private fun setActiveRecording(vm: PlayerViewModel, value: HDHomeRunRecording?) {
        stateFlowField<HDHomeRunRecording?>(vm, "_activeRecording").value = value
    }

    private fun setActiveHLSSessionId(vm: PlayerViewModel, value: String?) {
        stateFlowField<String?>(vm, "_activeHLSSessionId").value = value
    }

    private fun setQuality(vm: PlayerViewModel, value: QualityPreference) {
        stateFlowField<QualityPreference>(vm, "_quality").value = value
    }

    @Suppress("UNCHECKED_CAST")
    private fun setAutoEffectiveTier(vm: PlayerViewModel, backendValue: String) {
        val autoTierClass = Class.forName("org.hdhropen.kit.viewmodels.AutoTier")
        val getBackendValue = autoTierClass.getMethod("getBackendValue").apply { isAccessible = true }
        val tierConstant = autoTierClass.enumConstants.first { getBackendValue.invoke(it) == backendValue }
        val field = PlayerViewModel::class.java.getDeclaredField("autoEffectiveTier").apply { isAccessible = true }
        field.set(vm, tierConstant)
    }

    @Suppress("UNCHECKED_CAST")
    private fun seedBufferedAheadSamples(vm: PlayerViewModel, samples: List<Double>) {
        val field = PlayerViewModel::class.java.getDeclaredField("bufferedAheadSamples").apply { isAccessible = true }
        (field.get(vm) as MutableList<Double>).apply { clear(); addAll(samples) }
    }

    @Suppress("UNCHECKED_CAST")
    private fun seedSpeedSamples(vm: PlayerViewModel, samples: List<Double>) {
        val field = PlayerViewModel::class.java.getDeclaredField("speedSamplesMbps").apply { isAccessible = true }
        (field.get(vm) as MutableList<Double>).apply { clear(); addAll(samples) }
    }

    private fun setObservedBitrateBps(playerEngine: PlayerEngine, bps: Long?) {
        stateFlowField<Long?>(playerEngine, "_observedBitrateBps").value = bps
    }

    private fun sampleAutoQualityTick(vm: PlayerViewModel) {
        val method = PlayerViewModel::class.java.getDeclaredMethod("sampleAutoQualityTick").apply { isAccessible = true }
        method.invoke(vm)
    }

    @Test
    fun `selectQuality is a no-op in Direct play mode`() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val vm = newViewModel(apiClient)
        setPlaybackMode(vm, PlaybackMode.Direct)

        vm.selectQuality(QualityPreference.LOW)

        assertEquals(QualityPreference.AUTO, vm.quality.value)
        coVerify(exactly = 0) { apiClient.createChannelHLSSession(any(), any(), any(), any()) }
    }

    @Test
    fun `selectQuality is a no-op when already at the requested preference`() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val vm = newViewModel(apiClient)
        setPlaybackMode(vm, PlaybackMode.ServerTranscodedHls)
        setQuality(vm, QualityPreference.MEDIUM)

        vm.selectQuality(QualityPreference.MEDIUM)

        coVerify(exactly = 0) { apiClient.createChannelHLSSession(any(), any(), any(), any()) }
    }

    @Test
    fun `selectQuality on a live channel starts a new session at the chosen tier and stops the old one`() {
        val apiClient = mockk<APIClient>(relaxed = true)
        coEvery {
            apiClient.createChannelHLSSession(channelNumber = "4.1", forCast = false, audioIndex = null, quality = "low")
        } returns HDHomeRunRecording(sessionId = "sess-new", playUrl = "/api/hls/sess-new/playlist.m3u8", title = "Channel 4.1")

        val vm = newViewModel(apiClient)
        setPlaybackMode(vm, PlaybackMode.ServerTranscodedHls)
        setActiveChannel(vm, channel)
        setActiveHLSSessionId(vm, "sess-old")

        vm.selectQuality(QualityPreference.LOW)

        assertEquals(QualityPreference.LOW, vm.quality.value)
        assertEquals("sess-new", vm.activeHLSSessionId.value)
        coVerify { apiClient.createChannelHLSSession(channelNumber = "4.1", forCast = false, audioIndex = null, quality = "low") }
        coVerify { apiClient.stopHLSSession("sess-old") }
    }

    @Test
    fun `selectQuality on a recording session passes the chosen tier through to createRecordingHLSSession`() {
        val apiClient = mockk<APIClient>(relaxed = true)
        val recording = HDHomeRunRecording(recordingId = "rec-1", title = "News", playUrl = "http://example.com/play")
        coEvery {
            apiClient.createRecordingHLSSession(
                url = "http://example.com/play",
                recordingId = "rec-1",
                start = any(),
                audioIndex = null,
                provider = null,
                forCast = false,
                quality = "high"
            )
        } returns HLSSessionResponse(sessionId = "sess-new", playlistUrl = "/api/hls/sess-new/playlist.m3u8")

        val vm = newViewModel(apiClient)
        setPlaybackMode(vm, PlaybackMode.ServerTranscodedHls)
        setActiveRecording(vm, recording)
        setActiveHLSSessionId(vm, "sess-old")
        setQuality(vm, QualityPreference.LOW)

        vm.selectQuality(QualityPreference.HIGH)

        assertEquals(QualityPreference.HIGH, vm.quality.value)
        coVerify { apiClient.stopHLSSession("sess-old") }
    }

    @Test
    fun `auto poll downgrades when throughput collapses and the buffer is draining`() {
        val apiClient = mockk<APIClient>(relaxed = true)
        coEvery {
            apiClient.createChannelHLSSession(channelNumber = "4.1", forCast = false, audioIndex = null, quality = "minimal")
        } returns HDHomeRunRecording(sessionId = "sess-new", playUrl = "/api/hls/sess-new/playlist.m3u8", title = "Channel 4.1")

        val playerEngine = PlayerEngine(context = null)
        val vm = newViewModel(apiClient, playerEngine)
        setPlaybackMode(vm, PlaybackMode.ServerTranscodedHls)
        setActiveChannel(vm, channel)
        setActiveHLSSessionId(vm, "sess-old")
        setAutoEffectiveTier(vm, "high")

        // 21 healthy samples near the "high" target (5 Mbps) plus 2 already-low
        // ones, then one more low sample arrives on this tick -> baseline stays
        // near target (so the throughput number alone would normally be
        // ambiguous) while the last 3 samples read as a severe drop.
        seedSpeedSamples(vm, List(21) { 5.0 } + List(2) { 1.0 })
        setObservedBitrateBps(playerEngine, 1_000_000L)

        // Buffer ahead of the playhead has been shrinking for the whole
        // window and is now below the safety floor - genuine evidence the
        // network is losing ground, not just a low-bitrate source.
        seedBufferedAheadSamples(vm, listOf(15.0, 12.0, 9.0, 6.0))

        sampleAutoQualityTick(vm)

        coVerify { apiClient.createChannelHLSSession(channelNumber = "4.1", forCast = false, audioIndex = null, quality = "minimal") }
        coVerify { apiClient.stopHLSSession("sess-old") }
    }

    @Test
    fun `auto poll does not downgrade on low throughput when the buffer stays healthy`() {
        val apiClient = mockk<APIClient>(relaxed = true)

        val playerEngine = PlayerEngine(context = null)
        val vm = newViewModel(apiClient, playerEngine)
        setPlaybackMode(vm, PlaybackMode.ServerTranscodedHls)
        setActiveChannel(vm, channel)
        setActiveHLSSessionId(vm, "sess-old")
        setAutoEffectiveTier(vm, "high")

        // Same low/moderate throughput as the draining case above...
        seedSpeedSamples(vm, List(21) { 5.0 } + List(2) { 1.0 })
        setObservedBitrateBps(playerEngine, 1_000_000L)

        // ...but the buffer ahead of the playhead is flat and healthy the
        // whole window: this is the fast-LAN/modest-content-bitrate case the
        // old throughput-only heuristic wrongly downgraded.
        seedBufferedAheadSamples(vm, listOf(20.0, 20.0, 20.0, 20.0))

        sampleAutoQualityTick(vm)

        assertEquals(QualityPreference.AUTO, vm.quality.value)
        coVerify(exactly = 0) { apiClient.createChannelHLSSession(any(), any(), any(), any()) }
        coVerify(exactly = 0) { apiClient.stopHLSSession(any()) }
    }
}
