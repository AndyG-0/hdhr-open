package org.hdhropen.kit

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.hdhropen.kit.models.*
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.networking.HLSSessionResponse
import org.hdhropen.kit.networking.WatchSessionManager
import org.hdhropen.kit.playback.CaptionController
import org.hdhropen.kit.playback.CaptionCue
import org.hdhropen.kit.playback.PlayerEngine
import org.hdhropen.kit.viewmodels.PlayerViewModel
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/** CC-6: seeking (scrub bar, skip forward/back) previously bypassed
 * PlayerViewModel entirely by calling PlayerEngine directly, so live-cue
 * alignment went stale until the next 1.5s poll tick. These tests exercise
 * PlayerViewModel's seek/skipForward/skipBackward wrappers, which must
 * re-run alignment synchronously instead. */
class PlayerViewModelSeekResyncTest {

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

    private fun newViewModel(): PlayerViewModel {
        val client = mockk<APIClient>(relaxed = true)
        val watchSessionManager = WatchSessionManager(client)
        val playerEngine = PlayerEngine()
        val captionController = CaptionController()
        val vm = PlayerViewModel(client, watchSessionManager, playerEngine, captionController)
        activeVm = vm
        return vm
    }

    @Suppress("UNCHECKED_CAST")
    private fun setActiveRecording(vm: PlayerViewModel, recording: HDHomeRunRecording?) {
        val field = PlayerViewModel::class.java.getDeclaredField("_activeRecording")
        field.isAccessible = true
        val stateFlow = field.get(vm) as kotlinx.coroutines.flow.MutableStateFlow<HDHomeRunRecording?>
        stateFlow.value = recording
    }

    private fun setLastRawCues(vm: PlayerViewModel, cues: List<CaptionCue>) {
        vm.liveCaptionAligner.lastRawCues = cues
    }

    private fun stretchedCueDisplay(vm: PlayerViewModel): MutableMap<String, Pair<Double, Double>> {
        return vm.liveCaptionAligner.stretchedCueDisplay
    }

    private fun inProgressRecording(startedSecondsAgo: Double): HDHomeRunRecording {
        val nowSeconds = System.currentTimeMillis() / 1000.0
        return HDHomeRunRecording(
            recordingId = "rec1",
            title = "Live Show",
            start = nowSeconds - startedSecondsAgo,
            recordEnd = nowSeconds + 3600.0,
            playUrl = "http://example.com/play"
        )
    }

    private fun finishedRecording(): HDHomeRunRecording {
        val nowSeconds = System.currentTimeMillis() / 1000.0
        return HDHomeRunRecording(
            recordingId = "rec2",
            title = "Finished Show",
            start = nowSeconds - 3600.0,
            recordEnd = nowSeconds - 10.0,
            playUrl = "http://example.com/play"
        )
    }

    @Test
    fun `seek on in-progress recording resyncs captions immediately without waiting for a poll`() {
        val vm = newViewModel()
        vm.playerEngine.loadMedia(url = "http://example.com/live.m3u8", isLive = true, isSeekable = true)

        val recording = inProgressRecording(startedSecondsAgo = 100.0)
        setActiveRecording(vm, recording)
        // A cue already well behind live playback (elapsed ~95-98s into a
        // capture that's 100s old, with the player still at t=0) - it needs
        // to stretch to display at all.
        setLastRawCues(vm, listOf(CaptionCue(start = 95.0, end = 98.0, text = "Hello")))

        assertTrue(vm.captionController.cues.value.isEmpty())

        vm.seek(50.0)

        assertEquals(50.0, vm.playerEngine.currentTime.value, 0.001)
        val cues = vm.captionController.cues.value
        assertEquals(1, cues.size)
        assertEquals("Hello", cues[0].text)
    }

    @Test
    fun `seek on a finished recording is a no-op for captions`() {
        val vm = newViewModel()
        vm.playerEngine.loadMedia(url = "http://example.com/vod.m3u8", isLive = false, isSeekable = true)

        val recording = finishedRecording()
        setActiveRecording(vm, recording)
        setLastRawCues(vm, listOf(CaptionCue(start = 5.0, end = 8.0, text = "Should not be touched")))
        val sentinel = listOf(CaptionCue(start = 1.0, end = 2.0, text = "Sentinel"))
        vm.captionController.setCues(sentinel)

        vm.seek(30.0)

        assertEquals(30.0, vm.playerEngine.currentTime.value, 0.001)
        assertEquals(sentinel, vm.captionController.cues.value)
    }

    @Test
    fun `seek does not clear or re-stretch already-stretched cues`() {
        val vm = newViewModel()
        vm.playerEngine.loadMedia(url = "http://example.com/live.m3u8", isLive = true, isSeekable = true)

        val recording = inProgressRecording(startedSecondsAgo = 100.0)
        setActiveRecording(vm, recording)
        setLastRawCues(vm, listOf(CaptionCue(start = 95.0, end = 98.0, text = "Hello")))

        vm.seek(50.0)
        val afterFirstSeek = stretchedCueDisplay(vm).toMap()
        assertEquals(1, afterFirstSeek.size)

        // A second seek must reuse the same stretch window, not clear the
        // map and let this cue look "newly arrived" again - that cascade
        // bug would replay the whole caption history after every seek.
        vm.seek(80.0)
        val afterSecondSeek = stretchedCueDisplay(vm).toMap()
        assertEquals(afterFirstSeek, afterSecondSeek)
    }

    @Test
    fun `stretch cursor re-anchors to now each call instead of drifting across separate polls`() {
        // CC-11 regression test, mirroring web's CC-13 fix/test: without
        // resetting nextStretchSlotAbsolute to "now" at the top of every
        // alignLiveCues call, the cursor advances by LIVE_CUE_STRETCH_SECONDS
        // per newly-stretched cue and never resets between separate polls, so
        // a second stale cue arriving on a later poll queues behind the
        // first cue's stale reservation instead of anchoring to its own "now"
        // - a permanent, ever-growing freeze rather than a bounded lag.
        val vm = newViewModel()
        vm.playerEngine.loadMedia(url = "http://example.com/live.m3u8", isLive = true, isSeekable = true)

        val recording = inProgressRecording(startedSecondsAgo = 100.0)
        setActiveRecording(vm, recording)

        val first = CaptionCue(start = 95.0, end = 98.0, text = "First")
        setLastRawCues(vm, listOf(first))
        vm.seek(50.0)
        val firstSlotStart = stretchedCueDisplay(vm).getValue(first.id).first

        // A second stale cue, delivered on what stands in for a *separate*
        // later poll (not the same batch as the first).
        val second = CaptionCue(start = 96.0, end = 99.0, text = "Second")
        setLastRawCues(vm, listOf(first, second))
        vm.seek(51.0)
        val secondSlotStart = stretchedCueDisplay(vm).getValue(second.id).first

        // Both should anchor close to their own call's "now" (~100s elapsed
        // capture time), not LIVE_CUE_STRETCH_SECONDS (4s) or more apart.
        assertEquals(firstSlotStart, secondSlotStart, 2.0)
    }

    @Test
    fun `stale cues beyond the max-catchup cap are left unstretched instead of queued forever`() {
        // CC-11: a huge backlog (e.g. first poll after enabling captions
        // mid-show) must not hand out ever-later slots without bound -
        // mirrors web's LIVE_CUE_MAX_CATCHUP_SECONDS cap from CC-13.
        val vm = newViewModel()
        vm.playerEngine.loadMedia(url = "http://example.com/live.m3u8", isLive = true, isSeekable = true)

        val recording = inProgressRecording(startedSecondsAgo = 100.0)
        setActiveRecording(vm, recording)

        val cues = (0 until 10).map { i ->
            CaptionCue(start = 50.0 + i, end = 52.0 + i, text = "Line $i")
        }
        setLastRawCues(vm, cues)

        vm.seek(0.0)

        val displayed = vm.captionController.cues.value
        val lastDisplayedStart = displayed.maxOfOrNull { it.start } ?: 0.0
        // Player-relative start of any displayed cue must stay within the
        // catch-up cap (20s, PlayerViewModel's private LIVE_CUE_MAX_CATCHUP_
        // SECONDS) of "now" (player position 0.0) - never queued minutes into
        // the future.
        assertTrue(lastDisplayedStart <= 21.0)
    }

    @Test
    fun `skipForward and skipBackward also trigger a caption resync`() {
        val vm = newViewModel()
        vm.playerEngine.loadMedia(url = "http://example.com/live.m3u8", isLive = true, isSeekable = true)

        val recording = inProgressRecording(startedSecondsAgo = 100.0)
        setActiveRecording(vm, recording)
        setLastRawCues(vm, listOf(CaptionCue(start = 95.0, end = 98.0, text = "Hello")))

        vm.skipForward(30.0)
        assertEquals(30.0, vm.playerEngine.currentTime.value, 0.001)
        assertEquals(1, vm.captionController.cues.value.size)

        vm.skipBackward(10.0)
        assertEquals(20.0, vm.playerEngine.currentTime.value, 0.001)
        assertEquals(1, vm.captionController.cues.value.size)
    }

    @Test
    fun `seek on recording outside seekable range prepares server seek and creates HLS session`() = runTest {
        val client = mockk<APIClient>(relaxed = true)
        val hlsSessionResponse = HLSSessionResponse(sessionId = "new-hls-sess", playlistUrl = "/api/hls/new-hls-sess/playlist.m3u8")
        coEvery {
            client.createRecordingHLSSession(
                url = any(),
                recordingId = any(),
                start = any(),
                audioIndex = any(),
                provider = any(),
                forCast = any()
            )
        } returns hlsSessionResponse

        val watchSessionManager = WatchSessionManager(client)
        val playerEngine = PlayerEngine()
        val captionController = CaptionController()
        val vm = PlayerViewModel(client, watchSessionManager, playerEngine, captionController)
        activeVm = vm

        val recording = HDHomeRunRecording(
            recordingId = "rec-vod",
            title = "Movie",
            playUrl = "http://example.com/recording.ts",
            durationSeconds = 3600.0
        )
        setActiveRecording(vm, recording)
        playerEngine.loadMedia(url = "http://example.com/stream.m3u8", isSeekable = true, initialDuration = 3600.0)

        // Seeking to 1200s (unbuffered/outside seekable range)
        vm.seek(1200.0)

        assertEquals(1200.0, vm.playerEngine.currentTime.value, 0.001)
        coVerify {
            client.createRecordingHLSSession(
                url = "http://example.com/recording.ts",
                recordingId = "rec-vod",
                start = 1200.0,
                audioIndex = any(),
                provider = any(),
                forCast = any()
            )
        }
        assertEquals("new-hls-sess", vm.activeHLSSessionId.value)
        assertEquals(1200.0, vm.playerEngine.timeOffset, 0.001)
    }

    @Test
    fun `seek on channel stream clamps to duration and does not invoke server seek`() = runTest {
        val client = mockk<APIClient>(relaxed = true)
        val watchSessionManager = WatchSessionManager(client)
        val playerEngine = PlayerEngine()
        val captionController = CaptionController()
        val vm = PlayerViewModel(client, watchSessionManager, playerEngine, captionController)
        activeVm = vm

        val channel = HDHomeRunChannel(channelNumber = "5.1", name = "Live Channel")
        val channelField = PlayerViewModel::class.java.getDeclaredField("_activeChannel").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        (channelField.get(vm) as kotlinx.coroutines.flow.MutableStateFlow<HDHomeRunChannel?>).value = channel

        playerEngine.loadMedia(url = "http://example.com/channel.m3u8", isLive = true, isSeekable = true, initialDuration = 60.0)

        // Scrubbing past live duration 60.0 clamps to 60.0 and does not call createRecordingHLSSession
        vm.seek(150.0)
        assertEquals(60.0, vm.playerEngine.currentTime.value, 0.001)
        assertEquals(60.0, vm.playerEngine.duration.value, 0.001)

        coVerify(exactly = 0) { client.createRecordingHLSSession(any(), any(), any(), any(), any(), any()) }
    }
}
