package org.hdhropen.kit

import org.hdhropen.kit.playback.VTTParser
import org.junit.Assert.*
import org.junit.Test

class VTTParserTest {
    @Test
    fun testParseCaptions() {
        val vtt = """
        WEBVTT

        00:00:01.000 --> 00:00:04.000
        Welcome to HDHR Open!

        00:00:05.500 --> 00:00:08.200
        Enjoy live television and DVR.
        """.trimIndent()

        val cues = VTTParser.parseCaptions(vtt)
        assertEquals(2, cues.size)
        assertEquals(1.0, cues[0].start, 0.001)
        assertEquals(4.0, cues[0].end, 0.001)
        assertEquals("Welcome to HDHR Open!", cues[0].text)

        assertEquals(5.5, cues[1].start, 0.001)
        assertEquals(8.2, cues[1].end, 0.001)
        assertEquals("Enjoy live television and DVR.", cues[1].text)

        assertTrue(cues[0].contains(2.5))
        assertFalse(cues[0].contains(4.5))
    }

    @Test
    fun testParseThumbnailVtt() {
        val vtt = """
        WEBVTT

        00:00:00.000 --> 00:00:10.000
        thumb.jpg#xywh=0,0,160,90

        00:00:10.000 --> 00:00:20.000
        thumb.jpg#xywh=160,0,160,90
        """.trimIndent()

        val cues = VTTParser.parseThumbnailVtt(vtt)
        assertEquals(2, cues.size)
        assertEquals(0.0, cues[0].start, 0.001)
        assertEquals(10.0, cues[0].end, 0.001)
        assertEquals(0, cues[0].x)
        assertEquals(0, cues[0].y)
        assertEquals(160, cues[0].width)
        assertEquals(90, cues[0].height)

        assertEquals(160, cues[1].x)
        assertEquals(0, cues[1].y)
        assertTrue(cues[1].contains(15.0))
    }
}
