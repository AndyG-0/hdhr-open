package org.hdhropen.kit

import org.hdhropen.kit.models.HDHomeRunRecording
import org.hdhropen.kit.playback.CaptionCue
import org.hdhropen.kit.playback.LiveCaptionAligner
import org.junit.Assert.*
import org.junit.Test

class LiveCaptionAlignerTest {

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

    @Test
    fun testAlignLiveCues_stretchesExpiredCues() {
        val aligner = LiveCaptionAligner()
        val recording = inProgressRecording(startedSecondsAgo = 100.0)

        val rawCue = CaptionCue(start = 95.0, end = 98.0, text = "Hello")
        val aligned = aligner.alignLiveCues(recording, listOf(rawCue), playerTime = 50.0)

        assertEquals(1, aligned.size)
        assertEquals("Hello", aligned[0].text)
        assertEquals(1, aligner.stretchedCueDisplay.size)
    }

    @Test
    fun testAlignLiveCues_retainsExistingStretchDecisionAcrossCalls() {
        val aligner = LiveCaptionAligner()
        val recording = inProgressRecording(startedSecondsAgo = 100.0)
        val rawCue = CaptionCue(start = 95.0, end = 98.0, text = "Hello")
        aligner.alignLiveCues(recording, listOf(rawCue), playerTime = 50.0)
        val initialStretch = aligner.stretchedCueDisplay[rawCue.id]

        aligner.alignLiveCues(recording, listOf(rawCue), playerTime = 55.0)
        assertEquals(initialStretch, aligner.stretchedCueDisplay[rawCue.id])
    }

    @Test
    fun testMaxCatchupBounding() {
        val aligner = LiveCaptionAligner()
        val recording = inProgressRecording(startedSecondsAgo = 100.0)

        val cues = (0 until 10).map { i ->
            CaptionCue(start = 50.0 + i, end = 52.0 + i, text = "Line $i")
        }

        val aligned = aligner.alignLiveCues(recording, cues, playerTime = 0.0)
        val lastStart = aligned.maxOfOrNull { it.start } ?: 0.0
        assertTrue(lastStart <= LiveCaptionAligner.LIVE_CUE_MAX_CATCHUP_SECONDS + 1.0)
    }

    @Test
    fun testResetClearsState() {
        val aligner = LiveCaptionAligner()
        aligner.stretchedCueDisplay["c1"] = 10.0 to 20.0
        aligner.lastRawCues = listOf(CaptionCue(start = 1.0, end = 2.0, text = "hi"))
        aligner.nextStretchSlotAbsolute = 100.0

        aligner.reset()
        assertTrue(aligner.stretchedCueDisplay.isEmpty())
        assertTrue(aligner.lastRawCues.isEmpty())
        assertEquals(0.0, aligner.nextStretchSlotAbsolute, 0.001)
    }
}
