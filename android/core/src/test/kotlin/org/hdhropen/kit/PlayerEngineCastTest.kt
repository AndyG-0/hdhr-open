package org.hdhropen.kit

import android.net.Uri
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import io.mockk.every
import io.mockk.mockk
import io.mockk.mockkStatic
import io.mockk.slot
import io.mockk.unmockkStatic
import io.mockk.verify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.hdhropen.kit.playback.PlayerEngine
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

/** CAST-3: verifies PlayerEngine's activePlayer routing. Once a Cast
 * session is connected (isCasting), playback control and loadMedia calls
 * must go to castPlayer instead of exoPlayer, and loadMedia must attach
 * MediaMetadata (title/artwork) for the Cast receiver's UI. Uses reflection
 * to attach a mocked CastPlayer and flip the private _isCasting flag - same
 * pattern PlayerViewModelSeekResyncTest.kt uses for private state. Real
 * CastContext/CastSession construction needs a live device with Play
 * Services and a real Cast route, so session negotiation itself isn't
 * exercised here (no Robolectric in this module's test setup). */
class PlayerEngineCastTest {

    private val uriMock = mockk<Uri>(relaxed = true)

    @Before
    fun setUp() {
        // PlayerEngine's default coroutineScope uses Dispatchers.Main, which
        // has no real implementation in a plain JVM unit test until a test
        // dispatcher is installed here.
        Dispatchers.setMain(UnconfinedTestDispatcher())

        // android.net.Uri is an unmocked stub jar method in a plain JUnit
        // test (no Robolectric) - loadMedia() calls Uri.parse() upfront
        // regardless of which player ends up handling it, so it must be
        // stubbed here for these tests to reach the castPlayer branch at all.
        mockkStatic(Uri::class)
        every { Uri.parse(any()) } returns uriMock
    }

    @After
    fun tearDown() {
        unmockkStatic(Uri::class)
        Dispatchers.resetMain()
    }

    private fun attachMockCastPlayer(engine: PlayerEngine): Player {
        val castPlayer = mockk<Player>(relaxed = true)
        val castPlayerField = PlayerEngine::class.java.getDeclaredField("castPlayer").apply { isAccessible = true }
        castPlayerField.set(engine, castPlayer)

        val isCastingField = PlayerEngine::class.java.getDeclaredField("_isCasting").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        (isCastingField.get(engine) as MutableStateFlow<Boolean>).value = true

        return castPlayer
    }

    @Test
    fun `loadMedia while casting routes to castPlayer and attaches title and artwork metadata`() {
        val engine = PlayerEngine(context = null)
        val castPlayer = attachMockCastPlayer(engine)

        engine.loadMedia(
            url = "http://localhost:8000/api/hls/sess1/tok1/playlist.m3u8",
            isLive = true,
            isSeekable = true,
            title = "Test Show",
            artworkUrl = "http://localhost:8000/art.jpg"
        )

        val itemsSlot = slot<List<MediaItem>>()
        verify { castPlayer.setMediaItems(capture(itemsSlot)) }
        val mediaItem = itemsSlot.captured.single()
        assertEquals("Test Show", mediaItem.mediaMetadata.title?.toString())
        assertEquals(uriMock, mediaItem.mediaMetadata.artworkUri)
        verify { castPlayer.prepare() }
        verify { castPlayer.play() }

        // Confirms this genuinely routed away from ExoPlayer rather than
        // merely also calling castPlayer - context=null means exoPlayer was
        // never constructed, so the cast branch must have short-circuited
        // before any exoPlayer-specific (HlsMediaSource/DataSource.Factory)
        // code, which would otherwise NPE on the null context.
        assertNull(engine.exoPlayer)
    }

    @Test
    fun `play, pause, and seek route to castPlayer once a cast session is connected`() {
        val engine = PlayerEngine(context = null)
        val castPlayer = attachMockCastPlayer(engine)
        engine.loadMedia(url = "http://localhost:8000/api/hls/sess1/tok1/playlist.m3u8", isSeekable = true)

        engine.pause()
        engine.play()
        engine.seek(30.0)

        verify { castPlayer.pause() }
        verify(atLeast = 1) { castPlayer.play() }
        verify { castPlayer.seekTo(30_000L) }
    }
}
