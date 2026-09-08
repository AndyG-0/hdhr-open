import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSPlayerViewTests: XCTestCase {
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
        _ recordingsViewModel: RecordingsViewModel,
        _ multiPlayerViewModel: MultiPlayerViewModel? = nil
    ) -> some View {
        let multiVM = multiPlayerViewModel ?? MultiPlayerViewModel(
            apiClient: APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession()),
            watchSessionManager: WatchSessionManager(apiClient: APIClient(
                baseURL: URL(string: "http://localhost:8000")!,
                session: MockURLProtocol.makeSession()
            ))
        )
        return iOSPlayerView()
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)
            .environmentObject(multiVM)
    }

    func testShowsLiveTVTitleByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(playerViewModel.activeChannel)
        XCTAssertNil(playerViewModel.activeRecording)
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

    func testIncludesScrubBarAndAirPlayPicker() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(iOSScrubBarView.self))
        XCTAssertNoThrow(try view.inspect().find(AirPlayRoutePickerView.self))
    }

    func testHidesRecordMenuWhenNotAWatchSession() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.isWatchSession)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Record"))
    }

    func testHidesPlaybackInfoOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(iOSPlaybackInfoOverlay.self))
    }

    func testShowsMultiViewButtonInRegularSizeClassWhenLiveChannel() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"NBC\",\"play_url\":\"/stream/4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls_sess1\",\"playlist_url\":\"/api/streaming/hls/hls_sess1/playlist.m3u8\"}".utf8), 200
        )
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        await playerViewModel.playChannel(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)
            .environment(\.horizontalSizeClass, .regular)

        XCTAssertNoThrow(try view.inspect().find(where: { v in
            if let img = try? v.image() {
                return (try? img.actualImage().name()) == "square.grid.2x2"
            }
            return false
        }))
    }
}
