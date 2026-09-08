import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSSyncPlaySheetTests: XCTestCase {
    private func makePlayerViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
    }

    func testShowsJoinAndCreatePartySectionsWhenNotConnected() throws {
        let playerViewModel = makePlayerViewModel()
        XCTAssertNil(playerViewModel.syncPlayClient.room)
        XCTAssertFalse(playerViewModel.syncPlayClient.isConnected)

        let view = iOSSyncPlaySheet().environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Join Watch Party"))
        XCTAssertNoThrow(try view.inspect().find(text: "Create New Party"))
        XCTAssertThrowsError(try view.inspect().find(text: "Watch Party Room"))
    }

    func testJoinButtonDisabledUntilRoomCodeIsComplete() throws {
        let playerViewModel = makePlayerViewModel()
        let view = iOSSyncPlaySheet().environmentObject(playerViewModel)

        // Default @State: userName = "Apple User" (non-empty), roomCodeInput = "" -
        // the join button stays disabled until a full 6-letter code is entered,
        // while the create-room button (which only needs a non-empty name) is enabled.
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

        let view = iOSSyncPlaySheet().environmentObject(playerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Watch Party Room"))
        XCTAssertNoThrow(try view.inspect().find(text: "ABC123"))
        XCTAssertNoThrow(try view.inspect().find(text: "Andy (You)"))
        XCTAssertNoThrow(try view.inspect().find(text: "HOST"))
        XCTAssertNoThrow(try view.inspect().find(text: "Leave Watch Party"))
    }
}
