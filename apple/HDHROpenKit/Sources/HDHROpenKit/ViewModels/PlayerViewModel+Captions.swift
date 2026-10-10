import Foundation

/// Live caption polling/alignment subsystem (CC-7/CC-13), split out of
/// `PlayerViewModel.swift` the same way auto-quality was split into
/// `PlayerViewModel+AutoQuality.swift` - mostly to keep that file under
/// SwiftLint's file-length cap. `lastRawCues`, `stretchedCueDisplay`,
/// `nextStretchSlotAbsolute`, and `captionPollTask` remain stored properties
/// on `PlayerViewModel` itself (extensions can't add stored instance
/// properties), alongside the `captionPollIntervalNanos`/
/// `liveCueStretchSeconds`/`liveCueMaxCatchupSeconds` constants.
extension PlayerViewModel {
    /// Fetches and parses the caption VTT once, then aligns/stretches it
    /// against the player's current clock before publishing it to
    /// `captionController`. Best-effort: captions may not be extracted yet
    /// for an in-progress recording, so any failure here is swallowed - a
    /// poller (if running) retries on the next tick.
    func fetchCaptionsOnce(recording: HDHomeRunRecording) async {
        guard let recId = recording.recordingId, let playUrl = recording.playUrl else { return }
        let baseURL = await apiClient.baseURL
        guard let capURL = StreamURLBuilder.captionsURL(baseURL: baseURL, recordingId: recId, playUrl: playUrl, recordEnd: recording.recordEnd) else { return }
        guard let (data, _) = try? await URLSession.shared.data(from: capURL),
              let vttString = String(data: data, encoding: .utf8) else { return }
        let cues = VTTParser.parseCaptions(from: vttString)
        lastRawCues = cues
        captionController.setCues(alignLiveCues(recording: recording, cues: cues))
    }

    /// Re-fetches captions every `captionPollIntervalNanos` while `recording`
    /// is in progress, so live captions keep appearing as CC extraction
    /// catches up. No-ops for an already-finished recording. Always does one
    /// more fetch right after the recording transitions out of "in
    /// progress" to pick up the final complete VTT before stopping.
    func startCaptionPolling(recording: HDHomeRunRecording) {
        guard recording.isInProgress else { return }
        captionPollTask?.cancel()
        captionPollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: Self.captionPollIntervalNanos)
                guard let self, let current = activeRecording else { break }
                let wasInProgress = current.isInProgress
                await fetchCaptionsOnce(recording: current)
                if !wasInProgress {
                    break
                }
            }
        }
    }

    /// Remaps raw cue timestamps (anchored to the capture's absolute
    /// wall-clock start) onto the player's own rolling-live-window clock,
    /// and "stretches" any cue whose natural shifted end has already passed
    /// the current player time into a synthetic display window - CC
    /// extraction lag routinely runs well past a cue's own few-second
    /// window, so without this such cues would never satisfy
    /// `CaptionCue.contains` and would silently never display. Recomputed
    /// fresh on every call (not cached) since `baseOffsetSeconds` shifts as
    /// the live HLS window grows; only the per-cue stretch *decision* is
    /// memoized (keyed by cue id, which is stable across re-fetches) so a
    /// re-poll or re-seek reuses the same synthetic window instead of
    /// flickering it. VOD/finished recordings pass through untouched.
    private func alignLiveCues(recording: HDHomeRunRecording, cues: [CaptionCue]) -> [CaptionCue] {
        guard recording.isInProgress, let start = recording.start else { return cues }

        let elapsedCaptureSeconds = Date().timeIntervalSince1970 - start
        let playerTime = playerEngine.currentTime
        let baseOffsetSeconds = elapsedCaptureSeconds - playerTime

        // Re-anchor to "now" on every call instead of trusting wherever a
        // previous, separate call left the cursor. Without this, the cursor
        // advances by liveCueStretchSeconds per newly-stretched cue - slower
        // than real cue cadence (~2.85s avg observed) - so it drifts further
        // ahead of real time on every poll and never catches back up, pinning
        // near the cap below and queuing every cue after that behind an
        // unreachable backlog: a permanent freeze, not a bounded lag. Same
        // bug and fix as web's caption-controller.ts (CC-13).
        nextStretchSlotAbsolute = elapsedCaptureSeconds

        return cues.compactMap { cue in
            let window: (start: Double, end: Double)
            if let stretched = stretchedCueDisplay[cue.id] {
                window = stretched
            } else {
                let naturalEnd = cue.end - baseOffsetSeconds
                if naturalEnd > playerTime {
                    window = (cue.start, cue.end)
                } else {
                    let slotStart = max(cue.start, max(nextStretchSlotAbsolute, elapsedCaptureSeconds))
                    if slotStart - elapsedCaptureSeconds > Self.liveCueMaxCatchupSeconds {
                        window = (cue.start, cue.end)
                    } else {
                        let slotEnd = slotStart + Self.liveCueStretchSeconds
                        stretchedCueDisplay[cue.id] = (slotStart, slotEnd)
                        nextStretchSlotAbsolute = slotEnd
                        window = (slotStart, slotEnd)
                    }
                }
            }
            let displayEnd = window.end - baseOffsetSeconds
            guard displayEnd > 0 else { return nil }
            let displayStart = max(0, window.start - baseOffsetSeconds)
            return CaptionCue(start: displayStart, end: displayEnd, text: cue.text)
        }
    }

    /// Re-runs cue alignment against `lastRawCues` immediately after a
    /// seek/skip, instead of waiting for the next poll tick (which could be
    /// up to `captionPollIntervalNanos` away). No network call - the
    /// underlying VTT content hasn't changed, only the player's position.
    /// No-op for a finished/VOD recording, whose cue timestamps are static.
    /// Deliberately does not touch `stretchedCueDisplay`:
    /// `alignLiveCues` recomputes display coordinates fresh on every call
    /// from stretch windows stored in absolute time, so there's no stale
    /// state to clear. Clearing it here would be actively harmful - since
    /// each poll re-fetches and re-parses the *entire* caption history
    /// (full replace, not incremental), clearing the map would make every
    /// already-stretched cue in `lastRawCues` look "newly arrived"
    /// simultaneously, replaying the whole caption history in back-to-back
    /// stretch slots right after a seek.
    func resyncCaptionsAfterSeek() {
        guard let recording = activeRecording, recording.isInProgress else { return }
        captionController.setCues(alignLiveCues(recording: recording, cues: lastRawCues))
    }

    func resetCueStretch() {
        stretchedCueDisplay.removeAll()
        nextStretchSlotAbsolute = 0.0
        lastRawCues = []
    }
}
