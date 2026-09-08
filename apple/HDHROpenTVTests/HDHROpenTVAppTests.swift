import HDHROpenKit
import XCTest

@MainActor
final class HDHROpenTVAppTests: XCTestCase {
    private func makePlayerViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
    }

    /// Mirrors the background-teardown guard in `HDHROpenTVApp`'s
    /// `onChange(of: scenePhase)` handler (tvOS has no PiP support, so unlike
    /// the iOS app this only checks external playback and SharePlay). SwiftUI
    /// Scene lifecycle events can't be driven from XCTest, so this asserts the
    /// same boolean condition directly against a freshly constructed PlayerViewModel.
    func testBackgroundTeardownGuardHoldsInDefaultState() {
        let vm = makePlayerViewModel()

        XCTAssertFalse(vm.playerEngine.isExternalPlaybackActive)
        XCTAssertFalse(vm.sharePlayCoordinator.isSessionActive)

        let shouldTearDown = !vm.playerEngine.isExternalPlaybackActive
            && !vm.sharePlayCoordinator.isSessionActive
        XCTAssertTrue(shouldTearDown)
    }

    func testClosePlayerIsSafeAndResetsState() {
        let vm = makePlayerViewModel()
        vm.closePlayer()

        XCTAssertNil(vm.activeChannel)
        XCTAssertNil(vm.activeRecording)
        XCTAssertNil(vm.activeAiring)
        XCTAssertFalse(vm.isWatchSession)
        XCTAssertNil(vm.activeHLSSessionId)
        XCTAssertNil(vm.playbackMode)
    }
}
