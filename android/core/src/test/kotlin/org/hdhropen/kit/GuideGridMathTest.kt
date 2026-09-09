package org.hdhropen.kit

import org.hdhropen.kit.models.HDHomeRunFullGuideChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.utilities.GuideGridMath
import org.junit.Assert.*
import org.junit.Test

class GuideGridMathTest {

    @Test
    fun testGuideGridMathCalculations() {
        val now = 1700000000.0 // arbitrary epoch seconds

        // 1. windowBounds
        val airings = listOf(
            HDHomeRunGuideEntry(title = "Show 1", start = now - 3600.0, end = now + 7200.0)
        )
        val guideChannels = listOf(
            HDHomeRunFullGuideChannel(channelNumber = "5.1", channelName = "KPIX-HD", airings = airings)
        )
        val (windowStart, windowEnd) = GuideGridMath.windowBounds(now, guideChannels)
        assertTrue(windowStart <= now - 3600.0)
        assertTrue(windowEnd >= now + 7200.0)

        // 2. cellLayouts
        val layouts = GuideGridMath.cellLayouts(airings, windowStart, windowEnd)
        assertEquals(1, layouts.size)
        assertEquals("Show 1", layouts[0].airing.title)
        assertTrue(layouts[0].widthDp >= GuideGridMath.MIN_CELL_WIDTH)

        // 3. hourMarks
        val hourMarks = GuideGridMath.hourMarks(windowStart, windowEnd)
        assertTrue(hourMarks.isNotEmpty())
        for (mark in hourMarks) {
            assertTrue(mark.seconds >= windowStart && mark.seconds <= windowEnd)
            assertNotNull(mark.label)
        }

        // 4. dayMarks
        val dayMarks = GuideGridMath.dayMarks(windowStart, windowEnd)
        assertTrue(dayMarks.isNotEmpty())
        for (day in dayMarks) {
            assertNotNull(day.label)
        }
    }
}
