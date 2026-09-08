import Combine
import Foundation
import GroupActivities

/// Sibling object to `SyncPlayClient` (see `SyncPlayClient.swift`), same
/// shape but backed by Apple's `GroupActivities`/FaceTime transport instead
/// of a server-brokered WebSocket room. Owns the `GroupSession` lifecycle
/// and its `GroupSessionMessenger` content-change broadcast; playback
/// coordination itself (play/pause/seek/rate/buffering) is handled entirely
/// by `AVPlayerPlaybackCoordinator` once `PlayerViewModel` hands a session to
/// `PlayerEngine.coordinateWithGroupSession(_:)` via `onSessionAvailable`.
@MainActor
public final class SharePlayCoordinator: ObservableObject {
    @Published public private(set) var isSessionActive = false
    @Published public private(set) var participantCount = 0

    public var onRemoteContentChange: ((SyncPlayContent) -> Void)?
    public var onSessionAvailable: ((GroupSession<WatchProgramActivity>) -> Void)?
    public var onSessionEnded: (() -> Void)?

    private var currentSession: GroupSession<WatchProgramActivity>?
    private var messenger: GroupSessionMessenger?

    private var sessionsTask: Task<Void, Never>?
    private var stateTask: Task<Void, Never>?
    private var participantsTask: Task<Void, Never>?
    private var messagesTask: Task<Void, Never>?

    public init() {
        sessionsTask = Task { [weak self] in
            for await session in WatchProgramActivity.sessions() {
                guard let self else { return }
                configure(session)
            }
        }
    }

    deinit {
        sessionsTask?.cancel()
        stateTask?.cancel()
        participantsTask?.cancel()
        messagesTask?.cancel()
    }

    /// tvOS entry point - no `GroupActivitySharingController` exists there
    /// (confirmed unavailable in the SDK; see SHARE-1 plan), so the activity
    /// is activated directly and the system surfaces any needed UI on a
    /// paired device that's in an active FaceTime call. Returns whether the
    /// system actually began activation (the caller shouldn't assume a
    /// session followed - that arrives separately via `onSessionAvailable`).
    @discardableResult
    public func activateOnTV(content: SyncPlayContent) async throws -> Bool {
        let activity = WatchProgramActivity(content: content)
        return try await activity.activate()
    }

    /// Broadcasts a channel/recording switch to every other participant.
    /// No-op without an active session/messenger - callers are expected to
    /// gate this on `isSessionActive` (mirrors `SyncPlayClient.changeContent`
    /// being gated on `isConnected`).
    public func sendContentChange(_ content: SyncPlayContent) {
        guard let messenger else { return }
        Task {
            do {
                try await messenger.send(content)
            } catch {
                Log.player.error("SharePlay content-change send failed: \(error.localizedDescription, privacy: .public)")
            }
        }
    }

    /// Leaves the session for this device only - the FaceTime call (and the
    /// `GroupSession` for every other participant) continues.
    public func leaveSession() {
        currentSession?.leave()
        teardownSession()
    }

    private func configure(_ session: GroupSession<WatchProgramActivity>) {
        teardownSession()

        currentSession = session
        let messenger = GroupSessionMessenger(session: session)
        self.messenger = messenger

        stateTask = Task { [weak self] in
            for await state in session.$state.values {
                guard let self else { return }
                switch state {
                case .waiting, .joined:
                    break
                case .invalidated:
                    teardownSession()
                    onSessionEnded?()
                @unknown default:
                    break
                }
            }
        }

        participantsTask = Task { [weak self] in
            for await participants in session.$activeParticipants.values {
                guard let self else { return }
                participantCount = participants.count
            }
        }

        messagesTask = Task { [weak self] in
            for await (content, _) in messenger.messages(of: SyncPlayContent.self) {
                guard let self else { return }
                onRemoteContentChange?(content)
            }
        }

        isSessionActive = true
        session.join()
        onSessionAvailable?(session)
    }

    private func teardownSession() {
        stateTask?.cancel()
        stateTask = nil
        participantsTask?.cancel()
        participantsTask = nil
        messagesTask?.cancel()
        messagesTask = nil
        currentSession = nil
        messenger = nil
        isSessionActive = false
        participantCount = 0
    }
}
