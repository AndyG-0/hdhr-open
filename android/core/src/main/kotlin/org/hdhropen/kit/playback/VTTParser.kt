package org.hdhropen.kit.playback

data class CaptionCue(
    val start: Double,
    val end: Double,
    val text: String
) {
    val id: String get() = "${start}_${end}_${text.hashCode()}"

    fun contains(time: Double): Boolean = time in start..end
}

data class ThumbnailCue(
    val start: Double,
    val end: Double,
    val x: Int,
    val y: Int,
    val width: Int,
    val height: Int,
    val imageUrl: String? = null
) {
    val id: String get() = "${start}_${end}_${x}_${y}"

    fun contains(time: Double): Boolean = time in start..end
}

object VTTParser {
    fun parseTime(timeString: String): Double? {
        val trimmed = timeString.trim()
        val parts = trimmed.split(":")
        if (parts.size != 2 && parts.size != 3) return null

        return try {
            if (parts.size == 2) {
                val minutes = parts[0].toDouble()
                val seconds = parts[1].replace(",", ".").toDouble()
                minutes * 60.0 + seconds
            } else {
                val hours = parts[0].toDouble()
                val minutes = parts[1].toDouble()
                val seconds = parts[2].replace(",", ".").toDouble()
                hours * 3600.0 + minutes * 60.0 + seconds
            }
        } catch (e: Exception) {
            null
        }
    }

    fun parseCaptions(vttString: String): List<CaptionCue> {
        val cues = mutableListOf<CaptionCue>()
        val lines = vttString.lines()
        var i = 0

        while (i < lines.size) {
            val line = lines[i].trim()
            if (line.contains("-->")) {
                val timeParts = line.split("-->")
                if (timeParts.size == 2) {
                    val startStr = timeParts[0].trim()
                    val endStr = timeParts[1].trim().split(" ")[0]
                    val start = parseTime(startStr)
                    val end = parseTime(endStr)
                    if (start != null && end != null) {
                        val textLines = mutableListOf<String>()
                        i++
                        while (i < lines.size && lines[i].trim().isNotEmpty()) {
                            textLines.add(lines[i].trim())
                            i++
                        }
                        val text = textLines.joinToString("\n")
                        if (text.isNotEmpty()) {
                            cues.add(CaptionCue(start, end, text))
                        }
                    }
                }
            }
            i++
        }
        return cues
    }

    fun parseThumbnailVtt(vttString: String): List<ThumbnailCue> {
        val cues = mutableListOf<ThumbnailCue>()
        val lines = vttString.lines()
        var i = 0

        while (i < lines.size) {
            val line = lines[i].trim()
            if (line.contains("-->")) {
                val timeParts = line.split("-->")
                if (timeParts.size == 2) {
                    val startStr = timeParts[0].trim()
                    val endStr = timeParts[1].trim().split(" ")[0]
                    val start = parseTime(startStr)
                    val end = parseTime(endStr)
                    if (start != null && end != null) {
                        i++
                        if (i < lines.size) {
                            val mediaLine = lines[i].trim()
                            val xywhIdx = mediaLine.indexOf("#xywh=")
                            if (xywhIdx != -1) {
                                val imagePart = mediaLine.substring(0, xywhIdx)
                                val coordsPart = mediaLine.substring(xywhIdx + "#xywh=".length)
                                val coords = coordsPart.split(",").mapNotNull { it.trim().toIntOrNull() }
                                if (coords.size == 4) {
                                    cues.add(
                                        ThumbnailCue(
                                            start = start,
                                            end = end,
                                            x = coords[0],
                                            y = coords[1],
                                            width = coords[2],
                                            height = coords[3],
                                            imageUrl = imagePart.ifEmpty { null }
                                        )
                                    )
                                }
                            }
                        }
                    }
                }
            }
            i++
        }
        return cues
    }
}
