import GroupActivities
import XCTest
@testable import HDHROpenKit

@MainActor
final class SharePlayCoordinatorTests: XCTestCase {
    func testWatchProgramActivityFromContent() {
        let content = SyncPlayContent(type: "channel", recordingId: nil, channelNumber: "5.1", title: "Local News", durationSeconds: nil)
        let activity = WatchProgramActivity(content: content)

        XCTAssertEqual(activity.channelNumber, "5.1")
        XCTAssertNil(activity.recordingId)
        XCTAssertEqual(activity.title, "Local News")
        XCTAssertEqual(WatchProgramActivity.activityIdentifier, "org.hdhropen.watch-program")
    }

    func testWatchProgramActivityMetadata() async {
        let activity = WatchProgramActivity(channelNumber: "5.1", title: "Local News")
        let metadata = await activity.metadata

        XCTAssertEqual(metadata.title, "Local News")
        XCTAssertEqual(metadata.type, .watchTogether)
        XCTAssertTrue(metadata.supportsContinuationOnTV)
    }

    func testSharePlayCoordinatorInitialState() {
        let coordinator = SharePlayCoordinator()

        XCTAssertFalse(coordinator.isSessionActive)
        XCTAssertEqual(coordinator.participantCount, 0)
    }

    func testPlayerViewModelSharePlayWiring() throws {
        let apiClient = try APIClient(baseURL: XCTUnwrap(URL(string: "http://localhost:8000")))
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))

        XCTAssertNotNil(vm.sharePlayCoordinator)
        XCTAssertFalse(vm.sharePlayCoordinator.isSessionActive)
        XCTAssertFalse(vm.isCrossDeviceSyncActive)
    }

    /// Real `GroupSession` join/leave/messenger behavior needs two physical
    /// devices in a live FaceTime call, and `isSessionActive` is a
    /// `private(set)` driven only by an incoming `GroupSession`, so it can't
    /// be forced true from a unit test. This only exercises the guard
    /// direction that *is* reachable without a real session: SharePlay
    /// declining to activate while SyncPlay already owns cross-device sync.
    func testStartSharePlayOnTVNoOpsWhileSyncPlayConnected() async throws {
        let apiClient = try APIClient(baseURL: XCTUnwrap(URL(string: "http://localhost:8000")))
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
        try vm.syncPlayClient.connect(url: XCTUnwrap(URL(string: "ws://localhost:8000/ws")))

        XCTAssertTrue(vm.syncPlayClient.isConnected)

        await vm.startSharePlayOnTV()

        XCTAssertFalse(vm.sharePlayCoordinator.isSessionActive)
    }

    func testSendContentChangeIsNoOpWithoutActiveSession() {
        let coordinator = SharePlayCoordinator()
        let content = SyncPlayContent(type: "channel", recordingId: nil, channelNumber: "5.1", title: "Local News", durationSeconds: nil)

        // No messenger exists without a real GroupSession, so this should
        // simply return without crashing or mutating state.
        coordinator.sendContentChange(content)

        XCTAssertFalse(coordinator.isSessionActive)
    }

    func testLeaveSessionIsSafeWithoutActiveSession() {
        let coordinator = SharePlayCoordinator()

        coordinator.leaveSession()

        XCTAssertFalse(coordinator.isSessionActive)
        XCTAssertEqual(coordinator.participantCount, 0)
    }

    func testOnSessionCallbacksCanBeAssignedAndAreUnusedWithoutASession() {
        let coordinator = SharePlayCoordinator()
        var contentChangeCalled = false
        var sessionEndedCalled = false

        coordinator.onRemoteContentChange = { _ in contentChangeCalled = true }
        coordinator.onSessionEnded = { sessionEndedCalled = true }
        coordinator.onSessionAvailable = { _ in }

        coordinator.leaveSession()

        XCTAssertFalse(contentChangeCalled)
        XCTAssertFalse(sessionEndedCalled)
    }

    // MARK: - Extracted stream handlers

    //
    // `GroupSession<WatchProgramActivity>` has no public initializer, so it can't be
    // constructed or faked directly in a unit test - but its nested `State` enum
    // (`.waiting`/`.joined`/`.invalidated`) is a plain, freely constructible public
    // enum, and `SyncPlayContent` is an app-owned type. Feeding hand-rolled
    // `AsyncStream`s of those concrete types into the extracted handler methods lets
    // this exercise the coordinator's real reaction logic without a live session.

    func testHandleStateStreamInvalidatedTearsDownSessionAndFiresCallback() async {
        let coordinator = SharePlayCoordinator()
        var sessionEndedCalled = false
        coordinator.onSessionEnded = { sessionEndedCalled = true }

        let (stream, continuation) = AsyncStream<GroupSession<WatchProgramActivity>.State>.makeStream()
        continuation.yield(.waiting)
        continuation.yield(.invalidated(reason: CancellationError()))
        continuation.finish()

        await coordinator.handleStateStream(stream)

        XCTAssertTrue(sessionEndedCalled)
        XCTAssertFalse(coordinator.isSessionActive)
        XCTAssertEqual(coordinator.participantCount, 0)
    }

    func testHandleStateStreamWaitingAndJoinedDoNotTearDownOrFireCallback() async {
        let coordinator = SharePlayCoordinator()
        var sessionEndedCalled = false
        coordinator.onSessionEnded = { sessionEndedCalled = true }

        let (stream, continuation) = AsyncStream<GroupSession<WatchProgramActivity>.State>.makeStream()
        continuation.yield(.waiting)
        continuation.yield(.joined)
        continuation.finish()

        await coordinator.handleStateStream(stream)

        XCTAssertFalse(sessionEndedCalled)
    }

    func testHandleParticipantsStreamUpdatesCount() async {
        let coordinator = SharePlayCoordinator()

        let (stream, continuation) = AsyncStream<Set<Participant>>.makeStream()
        continuation.yield(Set<Participant>())
        continuation.finish()

        await coordinator.handleParticipantsStream(stream)

        XCTAssertEqual(coordinator.participantCount, 0)
    }

    func testHandleMessagesStreamForwardsContentToCallback() async {
        let coordinator = SharePlayCoordinator()
        var received: [SyncPlayContent] = []
        coordinator.onRemoteContentChange = { received.append($0) }

        let content = SyncPlayContent(type: "channel", recordingId: nil, channelNumber: "7.1", title: "News", durationSeconds: nil)
        let (stream, continuation) = AsyncStream<SyncPlayContent>.makeStream()
        continuation.yield(content)
        continuation.finish()

        await coordinator.handleMessagesStream(stream)

        XCTAssertEqual(received.count, 1)
        XCTAssertEqual(received.first?.channelNumber, "7.1")
        XCTAssertEqual(received.first?.title, "News")
    }

    func testHandleMessagesStreamIsNoOpWithoutACallback() async {
        let coordinator = SharePlayCoordinator()
        let content = SyncPlayContent(type: "channel", recordingId: nil, channelNumber: "7.1", title: "News", durationSeconds: nil)
        let (stream, continuation) = AsyncStream<SyncPlayContent>.makeStream()
        continuation.yield(content)
        continuation.finish()

        await coordinator.handleMessagesStream(stream)
    }
}
