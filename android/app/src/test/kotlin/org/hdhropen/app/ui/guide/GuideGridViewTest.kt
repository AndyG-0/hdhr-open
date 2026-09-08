package org.hdhropen.app.ui.guide

import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import io.mockk.mockk
import io.mockk.spyk
import org.hdhropen.app.ui.screens.guide.GuideGridMath
import org.hdhropen.app.ui.screens.guide.GuideGridView
import org.hdhropen.app.ui.theme.HDHROpenTheme
import org.hdhropen.kit.models.HDHomeRunChannel
import org.hdhropen.kit.models.HDHomeRunFullGuideChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import org.hdhropen.kit.networking.APIClient
import org.hdhropen.kit.viewmodels.GuideViewModel
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class GuideGridViewTest {

    @get:Rule
    val composeTestRule = createComposeRule()

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

    @Test
    fun testGuideGridViewRendersChannelsAndAirings() {
        composeTestRule.mainClock.autoAdvance = false

        val apiClient = mockk<APIClient>(relaxed = true)
        val guideViewModel = spyk(GuideViewModel(apiClient))

        val now = System.currentTimeMillis() / 1000.0
        val channel = HDHomeRunChannel(channelNumber = "2.1", name = "KTVU")
        val airing = HDHomeRunGuideEntry(
            title = "Morning News",
            start = now - 1800.0,
            end = now + 3600.0,
            hasCC = true
        )
        val fullChannel = HDHomeRunFullGuideChannel(
            channelNumber = "2.1",
            channelName = "KTVU",
            airings = listOf(airing)
        )

        val fullGuideFlow = kotlinx.coroutines.flow.MutableStateFlow(listOf(fullChannel))
        io.mockk.every { guideViewModel.fullGuide } returns fullGuideFlow
        io.mockk.every { guideViewModel.getAirings(any()) } returns listOf(airing)

        var tunedChannel: HDHomeRunChannel? = null
        var selectedAiring: Pair<HDHomeRunChannel, HDHomeRunGuideEntry>? = null

        composeTestRule.setContent {
            HDHROpenTheme {
                GuideGridView(
                    channels = listOf(channel),
                    guideViewModel = guideViewModel,
                    onSelectAiring = { ch, air -> selectedAiring = Pair(ch, air) },
                    onTuneChannel = { ch -> tunedChannel = ch }
                )
            }
        }
        composeTestRule.mainClock.advanceTimeByFrame()

        // Check channel column
        composeTestRule.onNodeWithText("2.1").assertExists()
        composeTestRule.onNodeWithText("KTVU").assertExists()

        // Check airing tile
        composeTestRule.onNodeWithText("Morning News").assertExists()

        // Click airing tile
        composeTestRule.onNodeWithText("Morning News").performClick()
        assertNotNull(selectedAiring)
        assertEquals("Morning News", selectedAiring?.second?.title)

        // Click channel header
        composeTestRule.onNodeWithText("KTVU").performClick()
        assertEquals("2.1", tunedChannel?.channelNumber)
    }
}
