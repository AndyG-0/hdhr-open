import Combine
import Foundation

@MainActor
public final class MultiPlayerViewModel: ObservableObject {
    @Published public private(set) var slots: [MultiViewSlot] = []
    @Published public var activeSlotIndex = 0
    @Published public var layout: MultiViewLayout = .sideBySide
    @Published public private(set) var isAllocatingSlot = false

    public static let maxFeeds = 4

    private let apiClient: APIClient
    private let watchSessionManager: WatchSessionManager
    private var engineCancellables: [UUID: AnyCancellable] = [:]

    public init(apiClient: APIClient, watchSessionManager: WatchSessionManager) {
        self.apiClient = apiClient
        self.watchSessionManager = watchSessionManager
    }

    public var canAddFeed: Bool {
        slots.count < Self.maxFeeds
    }

    public var activeSlot: MultiViewSlot? {
        slots.indices.contains(activeSlotIndex) ? slots[activeSlotIndex] : nil
    }

    public var isMultiViewActive: Bool {
        !slots.isEmpty
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
    ///
    /// This split exists so `slots` becomes non-empty (and `TVMultiPlayerView` mounts) on the
    /// same run loop turn as the call, instead of only after the stream negotiation resolves.
    @discardableResult
    public func beginAddFeed(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry? = nil) throws -> UUID {
        guard slots.count < Self.maxFeeds else {
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
            layout = MultiViewLayout.recommended(for: slots.count)
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

        // 1. Check physical tuner status from backend
        var tunerWarning: String?
        if let tuners = try? await apiClient.getTunerStatus(), !tuners.isEmpty {
            let availableTuners = tuners.filter { !$0.inUse }
            if availableTuners.isEmpty {
                tunerWarning = "Physical tuners exhausted. Playback may fail or conflict with active recordings."
                Log.player.warning("Multi-view: physical tuners exhausted when allocating feed for channel \(channel.channelNumber)")
            }
        }

        let baseURL = await apiClient.baseURL
        let authHeaders = await hlsAuthHeaders()

        var watchRec: HDHomeRunRecording?
        var hlsSessionId: String?
        let playbackMode: PlaybackMode? = .serverTranscodedHls

        // 2. Stream negotiation: try watch session first, fallback to direct HLS
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
            warningMessage: tunerWarning,
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
            layout = .threeBox
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

        // Check tuners
        var tunerWarning: String?
        if let tuners = try? await apiClient.getTunerStatus(), !tuners.isEmpty {
            if tuners.allSatisfy(\.inUse) {
                tunerWarning = "Physical tuners exhausted. Playback may fail or conflict with active recordings."
            }
        }

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
            warningMessage: tunerWarning,
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
