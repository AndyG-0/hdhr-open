import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVPlayerViewTests: XCTestCase {
    private func makeEnvironmentObjects() -> (PlayerViewModel, GuideViewModel, RecordingsViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        return (playerViewModel, guideViewModel, recordingsViewModel)
    }

    private func makeView(
        _ playerViewModel: PlayerViewModel,
        _ guideViewModel: GuideViewModel,
        _ recordingsViewModel: RecordingsViewModel
    ) -> some View {
        TVPlayerView()
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)
    }

    func testShowsLiveTVTitleByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(playerViewModel.activeChannel)
        XCTAssertEqual(playerViewModel.mediaTitle, "Live TV")

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Live TV"))
    }

    func testHidesErrorAndLoadingOverlaysInIdleState() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertEqual(playerViewModel.playerEngine.state, .idle)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Playback Error"))
        XCTAssertThrowsError(try view.inspect().find(ViewType.ProgressView.self))
    }

    func testShowsErrorOverlayWhenPlaybackFails() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        playerViewModel.playerEngine.setFailed("Stream broke")

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Playback Error"))
        XCTAssertNoThrow(try view.inspect().find(text: "Stream broke"))
        XCTAssertNoThrow(try view.inspect().find(text: "Close"))
    }

    func testShowsLoadingSpinnerWhenLoading() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        playerViewModel.playerEngine.setLoading()

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.ProgressView.self))
        XCTAssertThrowsError(try view.inspect().find(text: "Playback Error"))
    }

    func testIncludesScrubBarAndPlaybackControlsWhenControlsVisible() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()

        // showControls is a private @State defaulting to true.
        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(TVScrubBarView.self))
        XCTAssertNoThrow(try view.inspect().find(TVPlaybackControlsView.self))
    }

    func testShowsCaptionOverlayWhenCaptionControllerHasActiveCue() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        playerViewModel.captionController.setCues([CaptionCue(start: 0, end: 10, text: "Hello Captions")])
        playerViewModel.captionController.isEnabled = true
        playerViewModel.captionController.updatePlaybackTime(0)
        XCTAssertEqual(playerViewModel.captionController.activeCueText, "Hello Captions")

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Hello Captions"))
    }

    func testHidesChannelSwitcherOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.showChannelSwitcher)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVChannelSwitcherOverlay.self))
    }

    func testHidesSettingsOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.showAudioMenu)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVPlayerSettingsOverlay.self))
    }

    func testHidesSyncPlayOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.showSyncPlaySheet)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVSyncPlayOverlay.self))
    }

    func testHidesRecordMenuOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.showRecordMenu)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVPlayerRecordMenuOverlay.self))
    }
}
