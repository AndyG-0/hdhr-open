package org.hdhropen.kit

import org.hdhropen.kit.playback.CaptionCue
import org.hdhropen.kit.playback.CaptionController
import org.junit.Assert.*
import org.junit.Test

class CaptionControllerTest {
    @Test
    fun testSetCuesFullyReplacesExisting() {
        val controller = CaptionController()
        val first = listOf(CaptionCue(0.0, 2.0, "first"))
        val second = listOf(CaptionCue(10.0, 12.0, "second"))

        controller.setCues(first)
        controller.setCues(second)

        assertEquals(second, controller.cues.value)
    }

    @Test
    fun testUpdatePlaybackTimeNoOpWhenDisabled() {
        val controller = CaptionController()
        controller.setCues(listOf(CaptionCue(0.0, 5.0, "hello")))

        controller.updatePlaybackTime(2.0)

        assertNull(controller.activeCueText.value)
    }

    @Test
    fun testUpdatePlaybackTimeActivatesMatchingCue() {
        val controller = CaptionController()
        controller.setEnabled(true)
        controller.setCues(
            listOf(
                CaptionCue(1.0, 4.0, "a"),
                CaptionCue(5.5, 8.2, "b")
            )
        )

        controller.updatePlaybackTime(2.5)
        assertEquals("a", controller.activeCueText.value)

        controller.updatePlaybackTime(4.5)
        assertNull(controller.activeCueText.value)

        controller.updatePlaybackTime(6.0)
        assertEquals("b", controller.activeCueText.value)
    }

    @Test
    fun testCueBoundariesInclusive() {
        val controller = CaptionController()
        controller.setEnabled(true)
        controller.setCues(listOf(CaptionCue(1.0, 4.0, "a")))

        controller.updatePlaybackTime(1.0)
        assertEquals("a", controller.activeCueText.value)

        controller.updatePlaybackTime(4.0)
        assertEquals("a", controller.activeCueText.value)
    }

    @Test
    fun testToggleEnabledClearsActiveCueAndDoesNotAutoRecomputeOnReEnable() {
        val controller = CaptionController()
        controller.setEnabled(true)
        controller.setCues(listOf(CaptionCue(1.0, 4.0, "a")))
        controller.updatePlaybackTime(2.0)
        assertEquals("a", controller.activeCueText.value)

        controller.toggleEnabled()
        assertFalse(controller.isEnabled.value)
        assertNull(controller.activeCueText.value)

        controller.toggleEnabled()
        assertTrue(controller.isEnabled.value)
        assertNull(controller.activeCueText.value)

        controller.updatePlaybackTime(2.0)
        assertEquals("a", controller.activeCueText.value)
    }

    @Test
    fun testResetClearsCuesAndActiveTextButPreservesEnabledState() {
        val controller = CaptionController()
        controller.setEnabled(true)
        controller.setCues(listOf(CaptionCue(1.0, 4.0, "a")))
        controller.updatePlaybackTime(2.0)
        assertEquals("a", controller.activeCueText.value)

        controller.reset()

        assertTrue(controller.cues.value.isEmpty())
        assertNull(controller.activeCueText.value)
        assertTrue(controller.isEnabled.value)
    }
}
