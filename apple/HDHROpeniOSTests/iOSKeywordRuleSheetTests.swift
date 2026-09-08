import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSKeywordRuleSheetTests: XCTestCase {
    private func makeEnvironmentObjects() -> (GuideViewModel, RecordingsViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        return (guideViewModel, recordingsViewModel)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    private func makeSheet(onCreated: @escaping () -> Void = {}) -> iOSKeywordRuleSheet {
        iOSKeywordRuleSheet(onCreated: onCreated)
    }

    func testShowsCoreFormSections() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeSheet()
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Exact title"))
        XCTAssertNoThrow(try view.inspect().find(text: "Title contains"))
        XCTAssertNoThrow(try view.inspect().find(text: "Padding"))
        XCTAssertNoThrow(try view.inspect().find(text: "New episodes only"))
        XCTAssertNoThrow(try view.inspect().find(text: "Unlimited"))
        XCTAssertNoThrow(try view.inspect().find(text: "Keep last N"))
    }

    func testCreateButtonDisabledWhenTitleIsEmpty() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeSheet()
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertTrue(try view.inspect().find(button: "Create").isDisabled())
    }

    func testHidesChannelSectionWhenNoChannelsLoaded() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertTrue(guideViewModel.channels.isEmpty)

        let view = makeSheet()
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Any channel"))
        XCTAssertThrowsError(try view.inspect().find(text: "Select channels…"))
    }

    func testShowsChannelModePickerButHidesCustomListByDefaultWhenChannelsLoaded() async throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[
            {"channel_number":"4.1","name":"WNBC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null}
        ],"guide_available":true}
        """.utf8), 200)
        await guideViewModel.loadChannels()
        XCTAssertFalse(guideViewModel.channels.isEmpty)

        let view = makeSheet()
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        // channelMode defaults to "any", so the segmented picker is visible...
        XCTAssertNoThrow(try view.inspect().find(text: "Any channel"))
        XCTAssertNoThrow(try view.inspect().find(text: "Select channels…"))
        // ...but the per-channel selection list only renders once channelMode == "custom".
        XCTAssertThrowsError(try view.inspect().find(text: "4.1 WNBC"))
    }
}
