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
        assertNotNull(cues[1].id)
    }

    @Test
    fun testParseTimeFormatsAndEdgeCases() {
        // 2 parts: mm:ss.mmm
        assertEquals(75.5, VTTParser.parseTime("01:15.500") ?: 0.0, 0.001)
        // 2 parts with comma
        assertEquals(75.5, VTTParser.parseTime("01:15,500") ?: 0.0, 0.001)

        // 3 parts: hh:mm:ss.mmm
        assertEquals(3665.25, VTTParser.parseTime("01:01:05.250") ?: 0.0, 0.001)
        // 3 parts with comma
        assertEquals(3665.25, VTTParser.parseTime("01:01:05,250") ?: 0.0, 0.001)

        // Invalid formats
        assertNull(VTTParser.parseTime("invalid"))
        assertNull(VTTParser.parseTime("01:02:03:04"))
        assertNull(VTTParser.parseTime("ab:cd"))
        assertNull(VTTParser.parseTime("01:ab:cd"))
    }

    @Test
    fun testCueProperties() {
        val cue = org.hdhropen.kit.playback.CaptionCue(start = 1.0, end = 5.0, text = "Hello")
        assertNotNull(cue.id)
        assertTrue(cue.contains(1.0))
        assertTrue(cue.contains(3.0))
        assertTrue(cue.contains(5.0))
        assertFalse(cue.contains(0.9))
        assertFalse(cue.contains(5.1))

        val thumb = org.hdhropen.kit.playback.ThumbnailCue(start = 0.0, end = 10.0, x = 0, y = 0, width = 100, height = 50)
        assertNotNull(thumb.id)
        assertTrue(thumb.contains(5.0))
        assertFalse(thumb.contains(10.5))
    }

    @Test
    fun testMalformedVttHandling() {
        val malformedCaptions = """
            WEBVTT
            bad_line_no_arrow
            00:00:01.000 --> 00:00:02.000

            00:00:03.000 --> bad_end
            Some text
        """.trimIndent()
        val cues = VTTParser.parseCaptions(malformedCaptions)
        assertTrue(cues.isEmpty())

        val malformedThumbs = """
            WEBVTT
            00:00:00.000 --> 00:00:10.000
            not_an_image_tag
            00:00:10.000 --> 00:00:20.000
            thumb.jpg#xywh=invalid,coords
        """.trimIndent()
        val thumbCues = VTTParser.parseThumbnailVtt(malformedThumbs)
        assertTrue(thumbCues.isEmpty())
    }
}

