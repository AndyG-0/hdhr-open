import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVPlaybackControlsViewTests: XCTestCase {
    private func makeViewModels() -> (PlayerViewModel, GuideViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        return (playerViewModel, guideViewModel)
    }

    private func makeView(_ playerViewModel: PlayerViewModel, _ guideViewModel: GuideViewModel) -> some View {
        TVPlaybackControlsView(
            playerViewModel: playerViewModel,
            onTogglePlayPause: {},
            onSkipBackward: {},
            onSkipForward: {},
            onClose: {}
        )
        .environmentObject(guideViewModel)
    }

    func testShowsExpectedButtonsInDefaultIdleState() throws {
        let (playerViewModel, guideViewModel) = makeViewModels()
        XCTAssertFalse(playerViewModel.playerEngine.isSeekable)
        XCTAssertFalse(playerViewModel.isWatchSession)
        XCTAssertTrue(playerViewModel.playerEngine.availableAudioTracks.isEmpty)

        let view = makeView(playerViewModel, guideViewModel)

        // Skip back/forward hidden (not seekable), record hidden (not a
        // watch session), audio hidden (no tracks) - only playPause,
        // syncplay, shareplay, captions, close remain.
        let buttons = try view.inspect().findAll(ViewType.Button.self)
        XCTAssertEqual(buttons.count, 5)
    }

    func testHidesRecordButtonWhenNotWatchSession() throws {
        let (playerViewModel, guideViewModel) = makeViewModels()
        XCTAssertFalse(playerViewModel.isWatchSession)

        let view = makeView(playerViewModel, guideViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Record"))
    }

    func testShowsPlayIconWhenPaused() throws {
        let (playerViewModel, guideViewModel) = makeViewModels()
        XCTAssertFalse(playerViewModel.isPlaying)

        let view = makeView(playerViewModel, guideViewModel)

        let image = try view.inspect().find(ViewType.Image.self)
        XCTAssertEqual(try image.actualImage().name(), "play.fill")
    }

    func testHidesAudioTrackButtonWhenNoTracksAvailable() throws {
        let (playerViewModel, guideViewModel) = makeViewModels()
        XCTAssertTrue(playerViewModel.playerEngine.availableAudioTracks.isEmpty)

        let view = makeView(playerViewModel, guideViewModel)

        XCTAssertThrowsError(try view.inspect().find(ViewType.Image.self, where: { try $0.actualImage().name() == "waveform.circle" }))
    }

    func testCaptionsButtonTogglesCaptionControllerEnabled() throws {
        let (playerViewModel, guideViewModel) = makeViewModels()
        XCTAssertFalse(playerViewModel.captionController.isEnabled)

        let view = makeView(playerViewModel, guideViewModel)

        let captionsButton = try view.inspect().find(ViewType.Button.self, where: { button in
            (try? button.find(ViewType.Image.self).actualImage().name()) == "captions.bubble"
        })
        try captionsButton.tap()

        XCTAssertTrue(playerViewModel.captionController.isEnabled)
    }

    func testShowsSyncPlayButtonWhenSharePlayNotActive() throws {
        let (playerViewModel, guideViewModel) = makeViewModels()
        XCTAssertFalse(playerViewModel.sharePlayCoordinator.isSessionActive)

        let view = makeView(playerViewModel, guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.Image.self, where: { try $0.actualImage().name() == "person.2.fill" }))
    }

    func testShowsSharePlayButtonWhenSyncPlayNotConnected() throws {
        let (playerViewModel, guideViewModel) = makeViewModels()
        XCTAssertFalse(playerViewModel.syncPlayClient.isConnected)

        let view = makeView(playerViewModel, guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.Image.self, where: { try $0.actualImage().name() == "shareplay" }))
    }

    func testHidesSharePlayButtonAndShowsParticipantCountWhenSyncPlayConnected() throws {
        let (playerViewModel, guideViewModel) = makeViewModels()
        let syncPlayClient = playerViewModel.syncPlayClient
        try syncPlayClient.connect(url: XCTUnwrap(URL(string: "wss://localhost/syncplay")))
        defer { syncPlayClient.disconnect() }

        syncPlayClient.handleRawMessage("""
        {
            "type": "room_state",
            "your_session_id": "me",
            "room": {
                "room_code": "ABC123",
                "host_session_id": "me",
                "created_at": 0,
                "participants": [
                    {"session_id": "me", "user_name": "Andy", "is_host": true}
                ]
            }
        }
        """)
        XCTAssertTrue(syncPlayClient.isConnected)

        let view = makeView(playerViewModel, guideViewModel)

        XCTAssertThrowsError(try view.inspect().find(ViewType.Image.self, where: { try $0.actualImage().name() == "shareplay" }))
        // playPause, syncplay (now with a participant count), captions, close.
        let buttons = try view.inspect().findAll(ViewType.Button.self)
        XCTAssertEqual(buttons.count, 4)
        XCTAssertNoThrow(try view.inspect().find(text: "1"))
    }
}
