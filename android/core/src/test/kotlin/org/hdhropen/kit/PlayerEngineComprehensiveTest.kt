package org.hdhropen.kit

import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.analytics.AnalyticsListener
import com.google.android.gms.cast.framework.CastSession
import com.google.android.gms.cast.framework.SessionManagerListener
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.hdhropen.kit.models.HDHomeRunRecordingAudioInfo
import org.hdhropen.kit.models.HDHomeRunRecordingVideoInfo
import org.hdhropen.kit.models.HDHomeRunTranscodeInfo
import org.hdhropen.kit.playback.PlaybackState
import org.hdhropen.kit.playback.PlayerEngine
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class PlayerEngineComprehensiveTest {

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun testTrackAndSpecsManagement() {
        val engine = PlayerEngine()

        val audio1 = HDHomeRunRecordingAudioInfo(index = 0, title = "Main", channels = 2)
        val audio2 = HDHomeRunRecordingAudioInfo(index = 1, title = "Commentary", channels = 2)

        engine.setAudioTracks(listOf(audio1, audio2))
        assertEquals(2, engine.availableAudioTracks.value.size)
        assertEquals(audio1, engine.currentAudioTrack.value)

        engine.selectAudioTrack(audio2)
        assertEquals(audio2, engine.currentAudioTrack.value)

        val audio3 = HDHomeRunRecordingAudioInfo(index = 2, title = "Spanish", channels = 2)
        engine.setAudioTracks(listOf(audio1, audio2, audio3), selectedTrack = audio3)
        assertEquals(audio3, engine.currentAudioTrack.value)

        val videoInfo = HDHomeRunRecordingVideoInfo(codec = "h264", width = 1920, height = 1080)
        engine.setVideoSpecs(videoInfo)
        assertEquals(videoInfo, engine.videoSpecs.value)

        val transcode = HDHomeRunTranscodeInfo(transcoding = true, preset = "1080p-30fps", presetLabel = "1080p", hardware = true)
        engine.setTranscodeInfo(transcode)
        assertEquals(transcode, engine.transcodeInfo.value)
    }

    @Test
    fun testDurationSeekAndSkip() {
        val engine = PlayerEngine()
        engine.setDuration(120.0)
        assertEquals(120.0, engine.duration.value, 0.001)

        // Seek while not seekable does nothing
        engine.setSeekable(false)
        assertFalse(engine.isSeekable.value)
        engine.seek(50.0)
        assertEquals(0.0, engine.currentTime.value, 0.001)

        // Make seekable
        engine.setSeekable(true)
        assertTrue(engine.isSeekable.value)
        engine.seek(30.0)
        assertEquals(30.0, engine.currentTime.value, 0.001)

        engine.skipForward(15.0)
        assertEquals(45.0, engine.currentTime.value, 0.001)

        engine.skipBackward(10.0)
        assertEquals(35.0, engine.currentTime.value, 0.001)

        // Backward past 0 coerces to 0
        engine.skipBackward(100.0)
        assertEquals(0.0, engine.currentTime.value, 0.001)

        // Forward past duration coerces to duration
        engine.skipForward(200.0)
        assertEquals(120.0, engine.currentTime.value, 0.001)
    }

    @Test
    fun testTogglePlayPauseAndSetFailed() {
        val engine = PlayerEngine()
        val stateField = PlayerEngine::class.java.getDeclaredField("_state").apply { isAccessible = true }

        // Start paused
        @Suppress("UNCHECKED_CAST")
        (stateField.get(engine) as kotlinx.coroutines.flow.MutableStateFlow<PlaybackState>).value = PlaybackState.Paused

        engine.togglePlayPause()
        assertEquals(PlaybackState.Playing, engine.state.value)

        engine.togglePlayPause()
        assertEquals(PlaybackState.Paused, engine.state.value)

        // Set failed
        engine.setFailed("Playback failed", detail = "Err detail", statusCode = 500, isNetworkError = true)
        val failed = engine.state.value as PlaybackState.Failed
        assertEquals("Playback failed", failed.message)
        assertEquals("Err detail", failed.detail)
        assertEquals(500, failed.statusCode)
        assertTrue(failed.isNetworkError)

        engine.setPlaybackSpeed(1.5f)
        engine.reset()
        assertEquals(PlaybackState.Idle, engine.state.value)
        assertEquals(0.0, engine.currentTime.value, 0.001)
        assertEquals(0.0, engine.duration.value, 0.001)
        assertFalse(engine.isLive.value)
        assertFalse(engine.isSeekable.value)
        assertNull(engine.currentAudioTrack.value)
        assertNull(engine.videoSpecs.value)
        assertNull(engine.transcodeInfo.value)

        engine.release()
    }

    @Test
    fun testPlayerListenerCallbacks() {
        val engine = PlayerEngine()
        val createListenerMethod = PlayerEngine::class.java.getDeclaredMethod("createPlayerListener").apply {
            isAccessible = true
        }
        val listener = createListenerMethod.invoke(engine) as Player.Listener

        // Idle
        listener.onPlaybackStateChanged(Player.STATE_IDLE)

        // Buffering
        listener.onPlaybackStateChanged(Player.STATE_BUFFERING)
        assertEquals(PlaybackState.Buffering, engine.state.value)

        // Ready
        listener.onPlaybackStateChanged(Player.STATE_READY)
        assertEquals(PlaybackState.Paused, engine.state.value)

        // Ended
        listener.onPlaybackStateChanged(Player.STATE_ENDED)
        assertEquals(PlaybackState.Paused, engine.state.value)

        // IsPlaying changed
        listener.onIsPlayingChanged(true)
        assertEquals(PlaybackState.Playing, engine.state.value)

        listener.onIsPlayingChanged(false)
        assertEquals(PlaybackState.Paused, engine.state.value)

        // Behind live window
        val behindEx = PlaybackException("Behind live", null, PlaybackException.ERROR_CODE_BEHIND_LIVE_WINDOW)
        listener.onPlayerError(behindEx)

        // General playback error
        val genEx = PlaybackException("Decoder fail", null, PlaybackException.ERROR_CODE_DECODER_INIT_FAILED)
        listener.onPlayerError(genEx)
        assertTrue(engine.state.value is PlaybackState.Failed)
    }

    @Test
    fun testBandwidthListener() {
        val engine = PlayerEngine()
        val createBandwidthMethod = PlayerEngine::class.java.getDeclaredMethod("createBandwidthListener").apply {
            isAccessible = true
        }
        val listener = createBandwidthMethod.invoke(engine) as AnalyticsListener
        val eventTime = mockk<AnalyticsListener.EventTime>(relaxed = true)

        listener.onBandwidthEstimate(eventTime, 100, 500000L, 8_000_000L)
        assertEquals(8_000_000L, engine.observedBitrateBps.value)
    }

    @Test
    fun testSessionManagerListenerCallbacks() {
        val engine = PlayerEngine()
        val createSessionMethod = PlayerEngine::class.java.getDeclaredMethod("createSessionManagerListener").apply {
            isAccessible = true
        }
        @Suppress("UNCHECKED_CAST")
        val listener = createSessionMethod.invoke(engine) as SessionManagerListener<CastSession>
        val mockSession = mockk<CastSession>(relaxed = true)

        listener.onSessionStarting(mockSession)
        assertFalse(engine.isCasting.value)

        listener.onSessionStarted(mockSession, "sess1")
        assertTrue(engine.isCasting.value)

        listener.onSessionSuspended(mockSession, 1)
        assertFalse(engine.isCasting.value)

        listener.onSessionResuming(mockSession, "sess1")
        listener.onSessionResumed(mockSession, false)
        assertTrue(engine.isCasting.value)

        listener.onSessionEnding(mockSession)
        listener.onSessionEnded(mockSession, 0)
        assertFalse(engine.isCasting.value)

        listener.onSessionStartFailed(mockSession, 1)
        listener.onSessionResumeFailed(mockSession, 1)
    }
}
