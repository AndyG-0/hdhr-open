import XCTest
import GroupActivities
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

    func testPlayerViewModelSharePlayWiring() {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!)
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))

        XCTAssertNotNil(vm.sharePlayCoordinator)
        XCTAssertFalse(vm.sharePlayCoordinator.isSessionActive)
        XCTAssertFalse(vm.isCrossDeviceSyncActive)
    }

    // Real `GroupSession` join/leave/messenger behavior needs two physical
    // devices in a live FaceTime call, and `isSessionActive` is a
    // `private(set)` driven only by an incoming `GroupSession`, so it can't
    // be forced true from a unit test. This only exercises the guard
    // direction that *is* reachable without a real session: SharePlay
    // declining to activate while SyncPlay already owns cross-device sync.
    func testStartSharePlayOnTVNoOpsWhileSyncPlayConnected() async {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!)
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
        vm.syncPlayClient.connect(url: URL(string: "ws://localhost:8000/ws")!)

        XCTAssertTrue(vm.syncPlayClient.isConnected)

        await vm.startSharePlayOnTV()

        XCTAssertFalse(vm.sharePlayCoordinator.isSessionActive)
    }
}
