import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVPlayerSettingsOverlayTests: XCTestCase {
    private func makePlayerViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
    }

    func testShowsDefaultAudioTrackLabelWhenNoTracksAvailable() throws {
        let playerViewModel = makePlayerViewModel()
        XCTAssertTrue(playerViewModel.playerEngine.availableAudioTracks.isEmpty)

        let view = TVPlayerSettingsOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Default Audio Track"))
    }

    func testShowsAudioTrackListWhenTracksAvailable() throws {
        let playerViewModel = makePlayerViewModel()
        let track = HDHomeRunRecordingAudioInfo(index: 0, language: "eng")
        playerViewModel.playerEngine.setAudioTracks([track])

        let view = TVPlayerSettingsOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: track.displayLabel))
        XCTAssertThrowsError(try view.inspect().find(text: "Default Audio Track"))
    }

    func testHidesStreamDetailsWhenNoVideoSpecs() throws {
        let playerViewModel = makePlayerViewModel()
        XCTAssertNil(playerViewModel.playerEngine.videoSpecs)

        let view = TVPlayerSettingsOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertThrowsError(try view.inspect().find(text: "Stream Details"))
    }

    func testShowsStreamDetailsWhenVideoSpecsAvailable() throws {
        let playerViewModel = makePlayerViewModel()
        playerViewModel.playerEngine.setVideoSpecs(HDHomeRunRecordingVideoInfo(codec: "h264", width: 1920, height: 1080, fps: 59.94))

        let view = TVPlayerSettingsOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Stream Details"))
        XCTAssertNoThrow(try view.inspect().find(text: "1920x1080"))
        XCTAssertNoThrow(try view.inspect().find(text: "60 fps"))
        XCTAssertNoThrow(try view.inspect().find(text: "H264"))
    }

    func testShowsUnknownPlaybackModeByDefault() throws {
        let playerViewModel = makePlayerViewModel()
        XCTAssertNil(playerViewModel.playbackMode)

        let view = TVPlayerSettingsOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Unknown"))
    }

    func testTappingCloseInvokesOnDismiss() throws {
        let playerViewModel = makePlayerViewModel()
        var dismissed = false
        let view = TVPlayerSettingsOverlay(playerViewModel: playerViewModel, onDismiss: { dismissed = true })

        try view.inspect().find(button: "Close").tap()

        XCTAssertTrue(dismissed)
    }
}
