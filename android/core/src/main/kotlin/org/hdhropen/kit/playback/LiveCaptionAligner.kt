package org.hdhropen.kit.playback

import org.hdhropen.kit.models.HDHomeRunRecording

class LiveCaptionAligner {
    companion object {
        const val LIVE_CUE_STRETCH_SECONDS = 4.0
        const val LIVE_CUE_MAX_CATCHUP_SECONDS = 20.0
    }

    // Keyed by CaptionCue.id (stable across polls - derived from the raw,
    // pre-alignment start/end/text the backend won't change once emitted).
    val stretchedCueDisplay = mutableMapOf<String, Pair<Double, Double>>()
    var nextStretchSlotAbsolute = 0.0
        internal set

    // The raw (pre-alignment) cues from the most recent fetchCaptionsOnce
    var lastRawCues: List<CaptionCue> = emptyList()
        internal set

    /**
     * While a recording is in progress, the backend serves cue timestamps
     * anchored to the capture's absolute start (`recording.start`), but the
     * HLS session actually being played is a fresh rolling live window whose
     * own position clock has no fixed relationship to that origin - so raw
     * cue times drift against `playerTime` and cues appear to repeat/misalign.
     * Shift cues by the gap between elapsed capture time and playerTime.
     */
    fun alignLiveCues(
        recording: HDHomeRunRecording,
        cues: List<CaptionCue>,
        playerTime: Double,
        nowSeconds: Double = System.currentTimeMillis() / 1000.0
    ): List<CaptionCue> {
        val start = recording.start
        if (!recording.isInProgress || start == null) return cues
        val elapsedCaptureSeconds = nowSeconds - start
        val baseOffsetSeconds = elapsedCaptureSeconds - playerTime

        // Re-anchor to "now" on every call instead of trusting wherever a
        // previous, separate call left the cursor.
        nextStretchSlotAbsolute = elapsedCaptureSeconds

        return cues.mapNotNull { cue ->
            val (absStart, absEnd) = stretchedCueDisplay[cue.id] ?: run {
                val naturalEnd = cue.end - baseOffsetSeconds
                if (naturalEnd > playerTime) {
                    cue.start to cue.end
                } else {
                    val slotStart = maxOf(cue.start, nextStretchSlotAbsolute, elapsedCaptureSeconds)
                    if (slotStart - elapsedCaptureSeconds > LIVE_CUE_MAX_CATCHUP_SECONDS) {
                        return@run cue.start to cue.end
                    }
                    val slotEnd = slotStart + LIVE_CUE_STRETCH_SECONDS
                    stretchedCueDisplay[cue.id] = slotStart to slotEnd
                    nextStretchSlotAbsolute = slotEnd
                    slotStart to slotEnd
                }
            }
            val displayEnd = absEnd - baseOffsetSeconds
            if (displayEnd <= 0) return@mapNotNull null
            cue.copy(start = (absStart - baseOffsetSeconds).coerceAtLeast(0.0), end = displayEnd)
        }
    }

    /**
     * Synchronously computes resynced cues from cached [lastRawCues] after a seek or skip.
     * Returns null if no live recording is in progress.
     */
    fun resyncCaptionsAfterSeek(
        recording: HDHomeRunRecording?,
        playerTime: Double,
        nowSeconds: Double = System.currentTimeMillis() / 1000.0
    ): List<CaptionCue>? {
        if (recording == null || !recording.isInProgress) return null
        return alignLiveCues(recording, lastRawCues, playerTime, nowSeconds)
    }

    /**
     * Clears live-cue stretch bookkeeping so a new playback session doesn't
     * reuse stale slot/display decisions from a previous one.
     */
    fun reset() {
        stretchedCueDisplay.clear()
        nextStretchSlotAbsolute = 0.0
        lastRawCues = emptyList()
    }
}
