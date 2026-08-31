package org.hdhropen.kit

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.networking.APIClient
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

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun newViewModel(): PlayerViewModel {
        val client = APIClient("http://localhost:8000")
        val watchSessionManager = WatchSessionManager(client)
        val playerEngine = PlayerEngine()
        val captionController = CaptionController()
        return PlayerViewModel(client, watchSessionManager, playerEngine, captionController)
    }

    @Suppress("UNCHECKED_CAST")
    private fun setActiveRecording(vm: PlayerViewModel, recording: HDHomeRunRecording?) {
        val field = PlayerViewModel::class.java.getDeclaredField("_activeRecording")
        field.isAccessible = true
        val stateFlow = field.get(vm) as kotlinx.coroutines.flow.MutableStateFlow<HDHomeRunRecording?>
        stateFlow.value = recording
    }

    @Suppress("UNCHECKED_CAST")
    private fun setLastRawCues(vm: PlayerViewModel, cues: List<CaptionCue>) {
        val field = PlayerViewModel::class.java.getDeclaredField("lastRawCues")
        field.isAccessible = true
        field.set(vm, cues)
    }

    @Suppress("UNCHECKED_CAST")
    private fun stretchedCueDisplay(vm: PlayerViewModel): MutableMap<String, Pair<Double, Double>> {
        val field = PlayerViewModel::class.java.getDeclaredField("stretchedCueDisplay")
        field.isAccessible = true
        return field.get(vm) as MutableMap<String, Pair<Double, Double>>
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
}
