package org.hdhropen.app

import android.content.Context
import android.util.Rational
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class PipParamsTest {

    private val context: Context
        get() = RuntimeEnvironment.getApplication()

    @Test
    fun defaultAspectRatioWhenNullOrZero() {
        val defaultNull = PipHelper.calculateAspectRatio(null, null)
        assertEquals(Rational(16, 9), defaultNull)

        val zeroWidth = PipHelper.calculateAspectRatio(0, 1080)
        assertEquals(Rational(16, 9), zeroWidth)

        val zeroHeight = PipHelper.calculateAspectRatio(1920, 0)
        assertEquals(Rational(16, 9), zeroHeight)

        val negativeWidth = PipHelper.calculateAspectRatio(-1, 1080)
        assertEquals(Rational(16, 9), negativeWidth)
    }

    @Test
    fun standardAspectRatiosPreserved() {
        val hd169 = PipHelper.calculateAspectRatio(1920, 1080)
        assertEquals(Rational(1920, 1080), hd169)

        val sd43 = PipHelper.calculateAspectRatio(640, 480)
        assertEquals(Rational(640, 480), sd43)

        val cinemascope = PipHelper.calculateAspectRatio(1920, 817) // ~2.35:1
        assertEquals(Rational(1920, 817), cinemascope)
    }

    @Test
    fun extremeAspectRatiosClampedToAndroidLimits() {
        // Ultra-tall (e.g. 100x1000 = 0.1 ratio, below 1/2.39 ~ 0.41841)
        val ultraTall = PipHelper.calculateAspectRatio(100, 1000)
        assertEquals(Rational(100, 239), ultraTall)

        // Ultra-wide (e.g. 3000x500 = 6.0 ratio, above 2.39)
        val ultraWide = PipHelper.calculateAspectRatio(3000, 500)
        assertEquals(Rational(239, 100), ultraWide)
    }

    @Test
    fun remoteActionsWhenPlayingAndSeekable() {
        val actions = PipHelper.buildRemoteActions(context, isPlaying = true, isSeekable = true)
        assertEquals(3, actions.size)

        // Rewind 10s
        assertEquals("Rewind 10s", actions[0].title.toString())
        assertNotNull(actions[0].actionIntent)

        // Pause
        assertEquals("Pause", actions[1].title.toString())
        assertNotNull(actions[1].actionIntent)

        // Forward 10s
        assertEquals("Forward 10s", actions[2].title.toString())
        assertNotNull(actions[2].actionIntent)
    }

    @Test
    fun remoteActionsWhenPausedAndSeekable() {
        val actions = PipHelper.buildRemoteActions(context, isPlaying = false, isSeekable = true)
        assertEquals(3, actions.size)

        // Rewind 10s
        assertEquals("Rewind 10s", actions[0].title.toString())

        // Play
        assertEquals("Play", actions[1].title.toString())

        // Forward 10s
        assertEquals("Forward 10s", actions[2].title.toString())
    }

    @Test
    fun remoteActionsWhenNonSeekableOnlyShowsPlayPause() {
        val actionsPlaying = PipHelper.buildRemoteActions(context, isPlaying = true, isSeekable = false)
        assertEquals(1, actionsPlaying.size)
        assertEquals("Pause", actionsPlaying[0].title.toString())

        val actionsPaused = PipHelper.buildRemoteActions(context, isPlaying = false, isSeekable = false)
        assertEquals(1, actionsPaused.size)
        assertEquals("Play", actionsPaused[0].title.toString())
    }

    @Test
    fun pipActionConstants() {
        assertEquals("org.hdhropen.app.PIP_PLAY", PipHelper.ACTION_PIP_PLAY)
        assertEquals("org.hdhropen.app.PIP_PAUSE", PipHelper.ACTION_PIP_PAUSE)
        assertEquals("org.hdhropen.app.PIP_REWIND", PipHelper.ACTION_PIP_REWIND)
        assertEquals("org.hdhropen.app.PIP_FORWARD", PipHelper.ACTION_PIP_FORWARD)
    }
}
