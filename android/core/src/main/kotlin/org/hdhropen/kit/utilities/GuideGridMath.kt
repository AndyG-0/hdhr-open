package org.hdhropen.kit.utilities

import org.hdhropen.kit.models.HDHomeRunFullGuideChannel
import org.hdhropen.kit.models.HDHomeRunGuideEntry
import kotlin.math.max
import kotlin.math.min

object GuideGridMath {
    const val DP_PER_SECOND = 4.0f / 60.0f // 4dp per minute
    const val MIN_CELL_WIDTH = 90.0f
    const val HOUR_SECONDS = 3600.0
    const val DAY_SECONDS = 86400.0

    fun windowBounds(
        nowSeconds: Double,
        fullGuide: List<HDHomeRunFullGuideChannel>
    ): Pair<Double, Double> {
        var minStart = nowSeconds - 2 * HOUR_SECONDS
        var maxEnd = nowSeconds + 4 * HOUR_SECONDS
        val earliestAllowed = nowSeconds - 6 * HOUR_SECONDS

        for (entry in fullGuide) {
            for (airing in entry.airings) {
                airing.start?.let { minStart = min(minStart, it) }
                airing.end?.let { maxEnd = max(maxEnd, it) }
            }
        }

        minStart = max(minStart, earliestAllowed)
        val start = kotlin.math.floor(minStart / 1800.0) * 1800.0
        return Pair(start, maxEnd)
    }

    data class CellLayout(
        val airing: HDHomeRunGuideEntry,
        val leftDp: Float,
        val widthDp: Float
    )

    fun cellLayouts(
        airings: List<HDHomeRunGuideEntry>,
        windowStart: Double,
        windowEnd: Double
    ): List<CellLayout> {
        val layouts = mutableListOf<CellLayout>()
        for (airing in airings) {
            val airingStart = airing.start ?: continue
            val airingEnd = airing.end ?: continue
            val start = max(airingStart, windowStart)
            val end = min(airingEnd, windowEnd)
            if (end <= start) continue

            val left = ((start - windowStart) * DP_PER_SECOND).toFloat()
            val calculatedWidth = ((end - start) * DP_PER_SECOND).toFloat()
            val width = maxOf(calculatedWidth, MIN_CELL_WIDTH)

            layouts.add(CellLayout(airing, left, width))
        }
        return layouts
    }

    data class HourMark(val seconds: Double, val leftDp: Float, val label: String)
    data class DayMark(val start: Double, val leftDp: Float, val widthDp: Float, val label: String)

    fun hourMarks(windowStart: Double, windowEnd: Double): List<HourMark> {
        val marks = mutableListOf<HourMark>()
        var cursor = (kotlin.math.floor(windowStart / 3600.0) * 3600.0)
        while (cursor < windowEnd) {
            if (cursor >= windowStart) {
                val left = ((cursor - windowStart) * DP_PER_SECOND).toFloat()
                marks.add(HourMark(cursor, left, TimeFormatting.formatHour(cursor)))
            }
            cursor += 3600.0
        }
        return marks
    }

    fun dayMarks(windowStart: Double, windowEnd: Double): List<DayMark> {
        val marks = mutableListOf<DayMark>()
        var cursor = (kotlin.math.floor(windowStart / 86400.0) * 86400.0)
        while (cursor < windowEnd) {
            val dayEnd = cursor + 86400.0
            val segStart = max(cursor, windowStart)
            val segEnd = min(dayEnd, windowEnd)
            if (segEnd > segStart) {
                val left = ((segStart - windowStart) * DP_PER_SECOND).toFloat()
                val width = ((segEnd - segStart) * DP_PER_SECOND).toFloat()
                marks.add(DayMark(cursor, left, width, TimeFormatting.formatDayLabel(segStart)))
            }
            cursor = dayEnd
        }
        return marks
    }
}
