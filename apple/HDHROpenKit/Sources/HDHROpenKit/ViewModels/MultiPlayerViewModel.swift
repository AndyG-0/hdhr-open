import Combine
import Foundation

@MainActor
public final class MultiPlayerViewModel: ObservableObject {
    @Published public private(set) var slots: [MultiViewSlot] = []
    @Published public var activeSlotIndex = 0
    @Published public var layout: MultiViewLayout = .sideBySide
    @Published public private(set) var isAllocatingSlot = false
    @Published public private(set) var totalTuners: Int = 2
    @Published public private(set) var maxFeeds: Int = 2
    @Published public private(set) var tunerWarning: String?

    public static let maxFeeds = 4
    public static let maxMultiViewFeeds = 4

    private let apiClient: APIClient
    private let watchSessionManager: WatchSessionManager
    private var engineCancellables: [UUID: AnyCancellable] = [:]

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
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

        // Evaluate physical tuner availability & sharing
        let tunerAvail = await evaluateTunerAvailability(targetChannelNumber: channel.channelNumber, excludeSlotId: slotId)
        if !tunerAvail.available {
            let explanation = tunerAvail.explanation ?? "Physical tuners exhausted."
            playerEngine.setFailed(explanation)
            tunerWarning = explanation
            if let finalIndex = slots.firstIndex(where: { $0.id == slotId }) {
                slots[finalIndex] = MultiViewSlot(
                    id: slotId,
                    channel: channel,
                    airing: airing,
                    playerEngine: playerEngine,
                    isMuted: isMuted,
                    warningMessage: explanation,
                    playbackMode: .serverTranscodedHls
                )
            }
            throw MultiViewError.tunerUnavailable(explanation)
        }

        let tunerWarningMessage: String? = tunerAvail.isShared ? nil : (tunerAvail.totalTuners == tunerAvail.activeRecordingsCount + tunerAvail.activeStreamsCount ? "Physical tuners at capacity." : nil)

        let baseURL = await apiClient.baseURL
        let authHeaders = await hlsAuthHeaders()

        var watchRec: HDHomeRunRecording?
        var hlsSessionId: String?
        let playbackMode: PlaybackMode? = .serverTranscodedHls

        // Stream negotiation: try watch session first, fallback to direct HLS
        var streamStarted = false
        do {
            if let rec = try await watchSessionManager.startSession(channelNumber: channel.channelNumber),
               let playUrl = rec.playUrl
            {
                let hlsSession = try await apiClient.createRecordingHLSSession(
                    url: playUrl,
                    recordingId: rec.recordingId
                )
                if let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) {
                    watchRec = rec
                    hlsSessionId = hlsSession.sessionId
                    playerEngine.loadMedia(url: playlistURL, isLive: true, isSeekable: true, headers: authHeaders)
                    streamStarted = true
                    Log.player.info("Multi-view watch session HLS started: sessionId=\(hlsSession.sessionId) for channel \(channel.channelNumber)")
                }
            }
        } catch {
            Log.player.warning("Multi-view watch session failed for \(channel.channelNumber), falling back to channel HLS: \(error.localizedDescription)")
        }

        if !streamStarted {
            do {
                let rec = try await apiClient.createChannelHLSSession(channelNumber: channel.channelNumber)
                guard let sessionId = rec.sessionId,
                      let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: sessionId)
                else {
                    playerEngine.setFailed("Could not build stream URL.")
                    throw MultiViewError.streamURLCreationFailed
                }
                hlsSessionId = sessionId
                watchRec = rec.recordingId != nil ? rec : nil
                playerEngine.loadMedia(url: playlistURL, isLive: true, isSeekable: false, headers: authHeaders)
                Log.player.info("Multi-view direct channel HLS started: sessionId=\(sessionId) for channel \(channel.channelNumber)")
            } catch {
                playerEngine.setFailed(error.localizedDescription)
                throw error
            }
        }

        guard let finalIndex = slots.firstIndex(where: { $0.id == slotId }) else { return }

        slots[finalIndex] = MultiViewSlot(
            id: slotId,
            channel: channel,
            airing: airing,
            playerEngine: playerEngine,
            watchRecording: watchRec,
            hlsSessionId: hlsSessionId,
            isMuted: isMuted,
            warningMessage: tunerWarningMessage,
            playbackMode: playbackMode
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

        // Check tuner availability
        let tunerAvail = await evaluateTunerAvailability(targetChannelNumber: channel.channelNumber, excludeSlotId: oldSlot.id)
        if !tunerAvail.available {
            let explanation = tunerAvail.explanation ?? "Physical tuners exhausted."
            playerEngine.setFailed(explanation)
            tunerWarning = explanation
            slots[index] = MultiViewSlot(
                id: oldSlot.id,
                channel: channel,
                airing: airing ?? channel.now,
                playerEngine: playerEngine,
                isMuted: wasMuted,
                warningMessage: explanation,
                playbackMode: .serverTranscodedHls
            )
            throw MultiViewError.tunerUnavailable(explanation)
        }

        let tunerWarningMessage: String? = tunerAvail.isShared ? nil : (tunerAvail.totalTuners == tunerAvail.activeRecordingsCount + tunerAvail.activeStreamsCount ? "Physical tuners at capacity." : nil)

        let baseURL = await apiClient.baseURL
        let authHeaders = await hlsAuthHeaders()

        var watchRec: HDHomeRunRecording?
        var hlsSessionId: String?
        var streamStarted = false

        do {
            if let rec = try await watchSessionManager.startSession(channelNumber: channel.channelNumber),
               let playUrl = rec.playUrl
            {
                let hlsSession = try await apiClient.createRecordingHLSSession(
                    url: playUrl,
                    recordingId: rec.recordingId
                )
                if let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: hlsSession.sessionId) {
                    watchRec = rec
                    hlsSessionId = hlsSession.sessionId
                    playerEngine.loadMedia(url: playlistURL, isLive: true, isSeekable: true, headers: authHeaders)
                    streamStarted = true
                }
            }
        } catch {
            Log.player.warning("Multi-view replace feed watch session failed: \(error.localizedDescription)")
        }

        if !streamStarted {
            let rec = try await apiClient.createChannelHLSSession(channelNumber: channel.channelNumber)
            guard let sessionId = rec.sessionId,
                  let playlistURL = StreamURLBuilder.hlsPlaylistURL(baseURL: baseURL, sessionId: sessionId)
            else {
                playerEngine.setFailed("Could not build stream URL.")
                throw MultiViewError.streamURLCreationFailed
            }
            hlsSessionId = sessionId
            watchRec = rec.recordingId != nil ? rec : nil
            playerEngine.loadMedia(url: playlistURL, isLive: true, isSeekable: false, headers: authHeaders)
        }

        slots[index] = MultiViewSlot(
            id: oldSlot.id,
            channel: channel,
            airing: airing ?? channel.now,
            playerEngine: playerEngine,
            watchRecording: watchRec,
            hlsSessionId: hlsSessionId,
            isMuted: wasMuted,
            warningMessage: tunerWarningMessage,
            playbackMode: .serverTranscodedHls
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
    }

    private func hlsAuthHeaders() async -> [String: String] {
        guard let token = await apiClient.currentBearerToken() else { return [:] }
        return ["Authorization": "Bearer \(token)"]
    }
}
