package org.hdhropen.kit.utilities

import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

object TimeFormatting {
    private val timeFormat = SimpleDateFormat("h:mm a", Locale.getDefault())
    private val shortTimeFormat = SimpleDateFormat("h:mm", Locale.getDefault())
    private val hourFormat = SimpleDateFormat("h a", Locale.getDefault())
    private val weekdayFormat = SimpleDateFormat("EEEE", Locale.getDefault())
    private val fullDateFormat = SimpleDateFormat("EEEE, MMMM d", Locale.getDefault())

    fun formatTime(timestamp: Double?): String {
        if (timestamp == null) return ""
        return timeFormat.format(Date((timestamp * 1000).toLong()))
    }

    fun formatTimeRange(start: Double?, end: Double?): String {
        if (start == null && end == null) return ""
        if (start != null && end == null) return formatTime(start)
        if (start == null && end != null) return "Until ${formatTime(end)}"
        val startDate = Date((start!! * 1000).toLong())
        val endDate = Date((end!! * 1000).toLong())
        return "${shortTimeFormat.format(startDate)} – ${timeFormat.format(endDate)}"
    }

    fun formatHour(timestamp: Double): String {
        return hourFormat.format(Date((timestamp * 1000).toLong()))
    }

    fun formatDayLabel(timestamp: Double): String {
        val cal = Calendar.getInstance()
        val targetCal = Calendar.getInstance().apply {
            timeInMillis = (timestamp * 1000).toLong()
        }

        val isSameDay = cal.get(Calendar.YEAR) == targetCal.get(Calendar.YEAR) &&
                cal.get(Calendar.DAY_OF_YEAR) == targetCal.get(Calendar.DAY_OF_YEAR)
        if (isSameDay) return "Today"

        cal.add(Calendar.DAY_OF_YEAR, 1)
        val isTomorrow = cal.get(Calendar.YEAR) == targetCal.get(Calendar.YEAR) &&
                cal.get(Calendar.DAY_OF_YEAR) == targetCal.get(Calendar.DAY_OF_YEAR)
        if (isTomorrow) return "Tomorrow"

        return weekdayFormat.format(targetCal.time)
    }

    fun formatFullDate(timestamp: Double): String {
        return fullDateFormat.format(Date((timestamp * 1000).toLong()))
    }

    fun formatDuration(durationSeconds: Double?): String {
        if (durationSeconds == null || durationSeconds <= 0) return ""
        val minutes = (durationSeconds / 60).toInt()
        val hours = minutes / 60
        val remMinutes = minutes % 60
        return if (hours > 0) {
            "${hours}h ${remMinutes}m"
        } else {
            "${minutes}m"
        }
    }

    fun formatSecondsToClock(seconds: Double): String {
        val totalSecs = seconds.toInt().coerceAtLeast(0)
        val mins = totalSecs / 60
        val secs = totalSecs % 60
        val hrs = mins / 60
        val remMins = mins % 60
        return if (hrs > 0) {
            String.format("%d:%02d:%02d", hrs, remMins, secs)
        } else {
            String.format("%d:%02d", remMins, secs)
        }
    }
}
