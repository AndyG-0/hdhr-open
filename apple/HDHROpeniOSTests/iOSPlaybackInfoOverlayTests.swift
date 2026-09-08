import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSPlaybackInfoOverlayTests: XCTestCase {
    private func makePlayerViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
    }

    func testShowsPlaybackInfoTitleAndUnknownModeByDefault() throws {
        let playerViewModel = makePlayerViewModel()
        XCTAssertNil(playerViewModel.playbackMode)

        let view = iOSPlaybackInfoOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Playback Info"))
        XCTAssertNoThrow(try view.inspect().find(text: "Unknown"))
    }

    func testHidesVideoAndAudioSectionsByDefault() throws {
        let playerViewModel = makePlayerViewModel()
        XCTAssertNil(playerViewModel.playerEngine.videoSpecs)
        XCTAssertTrue(playerViewModel.playerEngine.availableAudioTracks.isEmpty)

        let view = iOSPlaybackInfoOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertThrowsError(try view.inspect().find(text: "Video"))
        XCTAssertThrowsError(try view.inspect().find(text: "Audio"))
    }

    func testShowsVideoSectionWhenVideoSpecsAreSet() throws {
        let playerViewModel = makePlayerViewModel()
        playerViewModel.playerEngine.setVideoSpecs(
            HDHomeRunRecordingVideoInfo(codec: "hevc", width: 1920, height: 1080, fps: 59.94)
        )

        let view = iOSPlaybackInfoOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Video"))
        XCTAssertNoThrow(try view.inspect().find(text: "HEVC"))
        XCTAssertNoThrow(try view.inspect().find(text: "1920×1080"))
        XCTAssertNoThrow(try view.inspect().find(text: "60 fps"))
    }

    func testShowsAudioTrackRowsWhenTracksAreSet() throws {
        let playerViewModel = makePlayerViewModel()
        playerViewModel.playerEngine.setAudioTracks([
            HDHomeRunRecordingAudioInfo(index: 0, codec: "aac", channels: 2)
        ])

        let view = iOSPlaybackInfoOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Audio"))
        XCTAssertNoThrow(try view.inspect().find(text: "Track 1"))
        XCTAssertNoThrow(try view.inspect().find(text: "AAC · 2ch"))
    }

    func testCloseButtonInvokesOnDismiss() throws {
        let playerViewModel = makePlayerViewModel()
        var dismissed = false
        let view = iOSPlaybackInfoOverlay(playerViewModel: playerViewModel, onDismiss: { dismissed = true })

        try view.inspect().find(ViewType.Button.self).tap()

        XCTAssertTrue(dismissed)
    }
}
