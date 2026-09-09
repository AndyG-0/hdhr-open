import Combine
import Foundation

@MainActor
public final class MultiPlayerViewModel: ObservableObject {
    @Published public private(set) var slots: [MultiViewSlot] = []
    @Published public var activeSlotIndex = 0
    @Published public var layout: MultiViewLayout = .sideBySide
    @Published public private(set) var isAllocatingSlot = false
    @Published public private(set) var totalTuners = 2
    @Published public private(set) var maxFeeds = 2
    @Published public private(set) var tunerWarning: String?

    public static let maxFeeds = 4
    public static let maxMultiViewFeeds = 4
    /// ~2 Mbps: comfortably legible on a background multi-view tile without
    /// meaningfully contributing to concurrent-decode battery/thermal cost.
    private static let backgroundBitrateCapBps: Double = 2_000_000

    private let apiClient: APIClient
    private let watchSessionManager: WatchSessionManager
    private let negotiator: ChannelStreamNegotiator
    private var engineCancellables: [UUID: AnyCancellable] = [:]
    private var tunerPollTask: Task<Void, Never>?

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
        negotiator = ChannelStreamNegotiator(apiClient: apiClient, watchSessionManager: watchSessionManager)
    }

    public var canAddFeed: Bool {
        slots.count < maxFeeds
    }

    public var activeSlot: MultiViewSlot? {
        slots.indices.contains(activeSlotIndex) ? slots[activeSlotIndex] : nil
    }

    public var isMultiViewActive: Bool {
        !slots.isEmpty
    }

    // MARK: - Tuner Capacity & Availability

    /// Loads and refreshes total physical tuner count and adapts maxFeeds and layouts accordingly.
    @discardableResult
    public func refreshTunerCapacity() async -> Int {
        do {
            let info = try await apiClient.getTunerInfo()
            if let count = info.tunerCount, count > 0 {
                totalTuners = count
                let newMaxFeeds = min(Self.maxMultiViewFeeds, max(1, count))
                maxFeeds = newMaxFeeds
                let allowed = MultiViewLayout.availableLayouts(for: newMaxFeeds)
                if !allowed.contains(layout) {
                    layout = .sideBySide
                }
                return newMaxFeeds
            }
        } catch {
            Log.player.warning("Multi-view: failed to fetch tuner info: \(error.localizedDescription)")
        }
        return maxFeeds
    }

    /// Evaluates real-time physical tuner availability for a target channel, accounting for tuner sharing on active recordings or streams.
    public func evaluateTunerAvailability(
        targetChannelNumber: String? = nil,
        excludeSlotId: UUID? = nil
    ) async -> TunerAvailabilityResult {
        var detectedTotalTuners = totalTuners
        var tuners: [HDHomeRunTuner] = []

        if let info = try? await apiClient.getTunerInfo(), let count = info.tunerCount, count > 0 {
            detectedTotalTuners = count
            totalTuners = count
            maxFeeds = min(Self.maxMultiViewFeeds, max(1, count))
        }

        if let status = try? await apiClient.getTunerStatus() {
            tuners = status
        }

        var activeRecordings: [(channel: String, title: String)] = []
        var activeStreams: [(channel: String, viewer: String)] = []
        var sharableSet = Set<String>()

        if !tuners.isEmpty {
            detectedTotalTuners = max(detectedTotalTuners, tuners.count)
            for t in tuners where t.inUse {
                let ch = t.channelNumber ?? t.channelName ?? "Unknown"
                if let chNum = t.channelNumber {
                    sharableSet.insert(chNum)
                }
                if t.client?.isRecording == true || t.client?.type == "scheduled_recording" || t.client?.recordingId != nil {
                    let title = t.client?.name ?? t.channelName ?? "Recording on \(ch)"
                    activeRecordings.append((channel: ch, title: title))
                } else {
                    let viewer = t.client?.name ?? "Live TV Viewer"
                    activeStreams.append((channel: ch, viewer: viewer))
                }
            }
        }

        // Include channels currently running in other multi-view slots (excluding the slot being added/replaced)
        for slot in slots where slot.id != excludeSlotId {
            if case .failed = slot.playerEngine.state {
                continue
            }
            sharableSet.insert(slot.channel.channelNumber)
        }

        let inUseCount = tuners.filter(\.inUse).count
        let freeTuners = max(0, detectedTotalTuners - inUseCount)
        let sharableChannels = Array(sharableSet)
        let isTargetShared = targetChannelNumber.map { sharableSet.contains($0) } ?? false

        if isTargetShared || freeTuners > 0 {
            return TunerAvailabilityResult(
                available: true,
                isShared: isTargetShared,
                totalTuners: detectedTotalTuners,
                activeRecordingsCount: activeRecordings.count,
                activeStreamsCount: activeStreams.count,
                sharableChannels: sharableChannels
            )
        }

        var explanation = "All \(detectedTotalTuners) tuners are currently in use."
        var breakdownParts: [String] = []
        if !activeRecordings.isEmpty {
            let recDesc = activeRecordings.map { "\($0.title) (Ch \($0.channel))" }.joined(separator: ", ")
            breakdownParts.append("\(activeRecordings.count) recording: \(recDesc)")
        }
        if !activeStreams.isEmpty {
            let streamDesc = activeStreams.map { "Ch \($0.channel) (\($0.viewer))" }.joined(separator: ", ")
            breakdownParts.append("\(activeStreams.count) streaming: \(streamDesc)")
        }
        if !breakdownParts.isEmpty {
            explanation += " Currently: \(breakdownParts.joined(separator: "; "))."
        }

        if !activeRecordings.isEmpty {
            let recChannels = activeRecordings.map { "Ch \($0.channel)" }.joined(separator: ", ")
            explanation += " You can watch \(recChannels) without consuming another tuner, or close an active feed."
        } else {
            explanation += " Close an active feed to free up a tuner."
        }

        return TunerAvailabilityResult(
            available: false,
            isShared: false,
            totalTuners: detectedTotalTuners,
            activeRecordingsCount: activeRecordings.count,
            activeStreamsCount: activeStreams.count,
            sharableChannels: sharableChannels,
            explanation: explanation
        )
    }

    /// Starts periodically re-evaluating every active slot's tuner-capacity
    /// warning. Without this, `warningMessage` is computed once at
    /// negotiation time and never updated, so a slot can keep showing
    /// "tuners at capacity" long after another feed frees one up, or never
    /// warn about capacity reached while it was negotiated. Mirrors
    /// `TunerViewModel`'s poll-loop pattern.
    public func startTunerPolling(intervalSeconds: UInt64 = 5) {
        guard tunerPollTask == nil else { return }
        tunerPollTask = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { break }
                await refreshSlotWarnings()
                try? await Task.sleep(nanoseconds: intervalSeconds * 1_000_000_000)
            }
        }
    }

    public func stopTunerPolling() {
        tunerPollTask?.cancel()
        tunerPollTask = nil
    }

    /// Re-evaluates the tuner-capacity warning for every settled (non-loading,
    /// non-failed) slot against current tuner state.
    private func refreshSlotWarnings() async {
        for slot in slots where slot.hlsSessionId != nil || slot.watchRecording != nil {
            let tunerAvail = await evaluateTunerAvailability(targetChannelNumber: slot.channel.channelNumber, excludeSlotId: slot.id)
            let warning: String? = tunerAvail.isShared
                ? nil
                : (tunerAvail.totalTuners == tunerAvail.activeRecordingsCount + tunerAvail.activeStreamsCount ? "Physical tuners at capacity." : nil)
            if let index = slots.firstIndex(where: { $0.id == slot.id }) {
                slots[index].warningMessage = warning
            }
        }
    }

    // MARK: - Feed Lifecycle

    /// Adds a channel feed to the multi-view grid.
    /// Checks available physical tuners, allocates stream sessions, configures audio focus, and adapts layout.
    public func addFeed(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = nil) async throws {
        let slotId = try beginAddFeed(channel: channel, airing: airing)
        try await finishAddFeed(slotId: slotId)
    }

    /// Synchronously reserves a slot for `channel`, showing a `.loading` tile immediately,
    /// before any network negotiation happens. Pair with `finishAddFeed` to complete the feed.
    @discardableResult
    public func beginAddFeed(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = nil) throws -> UUID {
        guard slots.count < maxFeeds else {
            throw MultiViewError.maxSlotsReached
        }

        let slotId = UUID()
        let playerEngine = PlayerEngine()
        let isFirstSlot = slots.isEmpty
        let isMuted = !isFirstSlot

        // Enforce mute state on the new player engine
        playerEngine.setMuted(isMuted)
        playerEngine.setLoading()

        // Forward engine changes to view model
        engineCancellables[slotId] = playerEngine.objectWillChange
            .sink { [weak self] _ in
                self?.objectWillChange.send()
            }

        let slot = MultiViewSlot(
            id: slotId,
            channel: channel,
            airing: airing ?? channel.now,
            playerEngine: playerEngine,
            isMuted: isMuted
        )

        slots.append(slot)

        if isFirstSlot {
            activeSlotIndex = 0
        }

        // Auto-adapt layout if current layout cannot accommodate the slot count
        if slots.count > layout.maxSlots {
            layout = MultiViewLayout.recommended(for: slots.count, maxFeeds: maxFeeds)
        }

        updateAudioRouting()

        return slotId
    }

    /// Negotiates the stream session for a slot reserved via `beginAddFeed` and updates it in place.
    /// If the slot was removed (e.g. the user closed it) while this was in flight, this is a no-op.
    public func finishAddFeed(slotId: UUID) async throws {
        guard let index = slots.firstIndex(where: { $0.id == slotId }) else { return }

        isAllocatingSlot = true
        defer { isAllocatingSlot = false }

        let channel = slots[index].channel
        let airing = slots[index].airing
        let playerEngine = slots[index].playerEngine
        let isMuted = slots[index].isMuted

        // Bump the generation before the first `await` below, so a slot
        // that's removed or re-targeted by a second finishAddFeed/replaceFeed
        // while this negotiation is in flight can be detected (by every
        // re-fetch-by-id + generation check below) instead of this call
        // silently clobbering a newer negotiation's result or leaking the
        // backend session it's about to negotiate.
        let myGeneration = slots[index].negotiationGeneration + 1
        slots[index].negotiationGeneration = myGeneration

        // Evaluate physical tuner availability & sharing
        let tunerAvail = await evaluateTunerAvailability(targetChannelNumber: channel.channelNumber, excludeSlotId: slotId)

        guard let currentIndex = slots.firstIndex(where: { $0.id == slotId }),
              slots[currentIndex].negotiationGeneration == myGeneration
        else {
            return
        }

        if !tunerAvail.available {
            let explanation = tunerAvail.explanation ?? "Physical tuners exhausted."
            playerEngine.setFailed(explanation)
            tunerWarning = explanation
            slots[currentIndex] = MultiViewSlot(
                id: slotId,
                channel: channel,
                airing: airing,
                playerEngine: playerEngine,
                isMuted: isMuted,
                warningMessage: explanation,
                playbackMode: .serverTranscodedHls,
                negotiationGeneration: myGeneration
            )
            throw MultiViewError.tunerUnavailable(explanation)
        }

        let tunerWarningMessage: String? = tunerAvail
            .isShared ? nil :
            (tunerAvail.totalTuners == tunerAvail.activeRecordingsCount + tunerAvail.activeStreamsCount ? "Physical tuners at capacity." : nil)

        let result: StreamNegotiationResult
        do {
            result = try await negotiator.negotiate(.channel(channel))
        } catch {
            playerEngine.setFailed(error.localizedDescription)
            throw error
        }

        guard let finalIndex = slots.firstIndex(where: { $0.id == slotId }),
              slots[finalIndex].negotiationGeneration == myGeneration
        else {
            negotiator.teardown(result)
            return
        }

        let authHeaders = await hlsAuthHeaders()
        playerEngine.loadMedia(url: result.streamURL, isLive: result.isLive, isSeekable: result.isSeekable, headers: authHeaders)
        Log.player.info("Multi-view stream started: sessionId=\(result.hlsSessionId) for channel \(channel.channelNumber)")

        slots[finalIndex] = MultiViewSlot(
            id: slotId,
            channel: channel,
            airing: airing,
            playerEngine: playerEngine,
            watchRecording: result.recording,
            hlsSessionId: result.hlsSessionId,
            isMuted: isMuted,
            warningMessage: tunerWarningMessage,
            playbackMode: .serverTranscodedHls,
            negotiationGeneration: myGeneration
        )
    }

    /// Removes a feed at the given index, tearing down its player engine and server sessions.
    public func removeFeed(at index: Int) {
        guard slots.indices.contains(index) else { return }

        let removedSlot = slots.remove(at: index)
        engineCancellables[removedSlot.id]?.cancel()
        engineCancellables.removeValue(forKey: removedSlot.id)

        teardownSlot(removedSlot)

        // Adjust activeSlotIndex
        if slots.isEmpty {
            activeSlotIndex = 0
            stopTunerPolling()
        } else if activeSlotIndex >= slots.count {
            activeSlotIndex = slots.count - 1
        } else if index < activeSlotIndex {
            activeSlotIndex -= 1
        }

        // Auto-adapt layout if down to fewer slots than previous layout's recommended count
        if slots.count <= 2, layout != .sideBySide {
            layout = .sideBySide
        } else if slots.count == 3, layout == .quad {
            layout = MultiViewLayout.recommended(for: slots.count, maxFeeds: maxFeeds)
        }

        updateAudioRouting()
    }

    /// Replaces the channel feed in a specific slot without disturbing other active feeds.
    public func replaceFeed(at index: Int, with channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = nil) async throws {
        guard slots.indices.contains(index) else {
            throw MultiViewError.slotNotFound(index)
        }

        let oldSlot = slots[index]
        teardownSlot(oldSlot)

        let wasMuted = oldSlot.isMuted
        let playerEngine = oldSlot.playerEngine
        playerEngine.reset()
        playerEngine.setMuted(wasMuted)
        playerEngine.setLoading()

        // Bump the generation before the first `await` below - see the
        // matching comment in `finishAddFeed`. From here on, re-fetch the
        // slot by `oldSlot.id` rather than trusting the positional `index`
        // parameter: the array can mutate (a remove/swap/another replace)
        // during either `await` below, which would otherwise make `index`
        // point at an unrelated slot by the time of the final write.
        let myGeneration = oldSlot.negotiationGeneration + 1
        slots[index].negotiationGeneration = myGeneration

        // Check tuner availability
        let tunerAvail = await evaluateTunerAvailability(targetChannelNumber: channel.channelNumber, excludeSlotId: oldSlot.id)

        guard let currentIndex = slots.firstIndex(where: { $0.id == oldSlot.id }),
              slots[currentIndex].negotiationGeneration == myGeneration
        else {
            return
        }

        if !tunerAvail.available {
            let explanation = tunerAvail.explanation ?? "Physical tuners exhausted."
            playerEngine.setFailed(explanation)
            tunerWarning = explanation
            slots[currentIndex] = MultiViewSlot(
                id: oldSlot.id,
                channel: channel,
                airing: airing ?? channel.now,
                playerEngine: playerEngine,
                isMuted: wasMuted,
                warningMessage: explanation,
                playbackMode: .serverTranscodedHls,
                negotiationGeneration: myGeneration
            )
            throw MultiViewError.tunerUnavailable(explanation)
        }

        let tunerWarningMessage: String? = tunerAvail
            .isShared ? nil :
            (tunerAvail.totalTuners == tunerAvail.activeRecordingsCount + tunerAvail.activeStreamsCount ? "Physical tuners at capacity." : nil)

        let result: StreamNegotiationResult
        do {
            result = try await negotiator.negotiate(.channel(channel))
        } catch {
            playerEngine.setFailed(error.localizedDescription)
            throw error
        }

        guard let finalIndex = slots.firstIndex(where: { $0.id == oldSlot.id }),
              slots[finalIndex].negotiationGeneration == myGeneration
        else {
            negotiator.teardown(result)
            return
        }

        let authHeaders = await hlsAuthHeaders()
        playerEngine.loadMedia(url: result.streamURL, isLive: result.isLive, isSeekable: result.isSeekable, headers: authHeaders)

        slots[finalIndex] = MultiViewSlot(
            id: oldSlot.id,
            channel: channel,
            airing: airing ?? channel.now,
            playerEngine: playerEngine,
            watchRecording: result.recording,
            hlsSessionId: result.hlsSessionId,
            isMuted: wasMuted,
            warningMessage: tunerWarningMessage,
            playbackMode: .serverTranscodedHls,
            negotiationGeneration: myGeneration
        )

        updateAudioRouting()
    }

    /// Selects the audio slot index, ensuring only this slot's player is unmuted.
    public func setAudioSlot(index: Int) {
        guard slots.indices.contains(index) else { return }
        activeSlotIndex = index
        updateAudioRouting()
    }

    /// Swaps the position of two slots in the grid and keeps audio focus on the moved item.
    public func swapSlots(from: Int, to: Int) {
        guard slots.indices.contains(from), slots.indices.contains(to), from != to else { return }

        slots.swapAt(from, to)

        if activeSlotIndex == from {
            activeSlotIndex = to
        } else if activeSlotIndex == to {
            activeSlotIndex = from
        }

        updateAudioRouting()
    }

    /// Pauses every slot except `index` (used when expanding a tile to fullscreen), so background
    /// feeds stop decoding while the user is focused on one stream.
    public func pauseBackgroundSlots(except index: Int) {
        for (i, slot) in slots.enumerated() where i != index {
            slot.playerEngine.pause()
        }
    }

    /// Resumes every currently-paused slot (used when collapsing back to the grid). Seekable
    /// (watch-session-backed) slots are snapped to the live edge first so they don't resume from
    /// the stale position they were paused at; non-seekable direct-channel slots simply resume.
    public func resumeBackgroundSlots() {
        for slot in slots {
            guard slot.playerEngine.state == .paused else { continue }
            if slot.playerEngine.isSeekable {
                slot.playerEngine.seek(to: slot.playerEngine.duration)
            }
            slot.playerEngine.play()
        }
    }

    /// Closes and cleans up all active feeds and their streaming sessions.
    public func removeAllFeeds() {
        closeAll()
    }

    public func closeAll() {
        for slot in slots {
            engineCancellables[slot.id]?.cancel()
            teardownSlot(slot)
        }
        engineCancellables.removeAll()
        slots.removeAll()
        activeSlotIndex = 0
        stopTunerPolling()
    }

    // MARK: - Private Helpers

    private func teardownSlot(_ slot: MultiViewSlot) {
        slot.playerEngine.reset()

        if let hlsSessionId = slot.hlsSessionId {
            let client = apiClient
            runWithBackgroundGrace(name: "StopMultiViewHLS_\(hlsSessionId)") {
                try? await client.stopHLSSession(sessionId: hlsSessionId)
                Log.player.info("Stopped multi-view HLS session \(hlsSessionId)")
            }
        }

        if let watchSessionId = slot.watchRecording?.sessionId {
            watchSessionManager.stopSession(sessionId: watchSessionId)
        }
    }

    private func updateAudioRouting() {
        for i in 0..<slots.count {
            let shouldBeUnmuted = (i == activeSlotIndex)
            let isMuted = !shouldBeUnmuted
            if slots[i].isMuted != isMuted {
                slots[i].isMuted = isMuted
            }
            slots[i].playerEngine.setMuted(isMuted)
        }
        applyBackgroundBitrateCapping()
    }

    /// Caps decode bitrate on every slot except the audio-focused one: up to
    /// 4 concurrent `AVPlayer`s decoding at full quality simultaneously is
    /// expensive (battery/thermals), but multi-view's whole premise is
    /// seeing every tile live at once, so tiles are never paused by default
    /// (see `pauseBackgroundSlots`, which only fires on explicit fullscreen
    /// expand) - this is the mitigation instead. Reset to unlimited (`0`) on
    /// the focused slot so switching audio focus restores full quality
    /// there. Called from `updateAudioRouting()` so it stays in sync with
    /// every path that can change `activeSlotIndex` or the slot list
    /// (`setAudioSlot`, `swapSlots`, add/replace/remove-feed).
    private func applyBackgroundBitrateCapping() {
        for (i, slot) in slots.enumerated() {
            let bitRate = (i == activeSlotIndex) ? 0.0 : Self.backgroundBitrateCapBps
            slot.playerEngine.setPreferredPeakBitRate(bitRate)
        }
    }

    private func hlsAuthHeaders() async -> [String: String] {
        guard let token = await apiClient.currentBearerToken() else { return [:] }
        return ["Authorization": "Bearer \(token)"]
    }
}
