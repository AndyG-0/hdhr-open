import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVSyncPlayOverlayTests: XCTestCase {
    private func makePlayerViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
    }

    func testShowsJoinAndHostSectionsWhenNotConnected() throws {
        let playerViewModel = makePlayerViewModel()
        XCTAssertNil(playerViewModel.syncPlayClient.room)
        XCTAssertFalse(playerViewModel.syncPlayClient.isConnected)

        let view = TVSyncPlayOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Join Existing Party"))
        XCTAssertNoThrow(try view.inspect().find(text: "Host New Party"))
        XCTAssertThrowsError(try view.inspect().find(text: "ROOM CODE"))
    }

    func testJoinButtonDisabledUntilRoomCodeIsComplete() throws {
        let playerViewModel = makePlayerViewModel()
        let view = TVSyncPlayOverlay(playerViewModel: playerViewModel, onDismiss: {})

        // Default @State: userName = "Apple TV" (non-empty), roomCodeInput =
        // "" - Join stays disabled until a full 6-letter code is entered,
        // while Create (which only needs a non-empty name) is enabled.
        XCTAssertTrue(try view.inspect().find(button: "Join Party").isDisabled())
        XCTAssertFalse(try view.inspect().find(button: "Create Watch Party").isDisabled())
    }

    func testShowsActiveRoomSectionWhenConnectedWithRoomState() throws {
        let playerViewModel = makePlayerViewModel()
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
        XCTAssertEqual(syncPlayClient.room?.roomCode, "ABC123")

        let view = TVSyncPlayOverlay(playerViewModel: playerViewModel, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "ROOM CODE"))
        XCTAssertNoThrow(try view.inspect().find(text: "ABC123"))
        XCTAssertNoThrow(try view.inspect().find(text: "Andy (You)"))
        XCTAssertNoThrow(try view.inspect().find(text: "HOST"))
        XCTAssertNoThrow(try view.inspect().find(text: "Leave Watch Party"))
        XCTAssertThrowsError(try view.inspect().find(text: "Join Existing Party"))
    }

    func testTappingCloseInvokesOnDismiss() throws {
        let playerViewModel = makePlayerViewModel()
        var dismissed = false
        let view = TVSyncPlayOverlay(playerViewModel: playerViewModel, onDismiss: { dismissed = true })

        try view.inspect().find(button: "Close").tap()

        XCTAssertTrue(dismissed)
    }
}
