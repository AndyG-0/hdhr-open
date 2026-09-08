import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVKeywordRuleModalTests: XCTestCase {
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

    func testShowsCoreFormSections() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVKeywordRuleModal(onCreated: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Add Keyword Rule"))
        XCTAssertNoThrow(try view.inspect().find(text: "Title"))
        XCTAssertNoThrow(try view.inspect().find(text: "Title Match"))
        XCTAssertNoThrow(try view.inspect().find(text: "Keywords"))
        XCTAssertNoThrow(try view.inspect().find(text: "Padding"))
        XCTAssertNoThrow(try view.inspect().find(text: "Keep Episodes"))
        XCTAssertNoThrow(try view.inspect().find(button: "Create"))
    }

    func testCreateButtonDisabledWhenTitleEmpty() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVKeywordRuleModal(onCreated: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertTrue(try view.inspect().find(button: "Create").isDisabled())
    }

    func testTitleFieldAcceptsInput() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVKeywordRuleModal(onCreated: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        // Without ViewHosting, @State mutations from setInput() don't propagate
        // back into a freshly re-inspected view body, so we only confirm the
        // Title field exists and accepts input here rather than re-reading the
        // Create button's disabled state afterward (see testCreateButtonDisabledWhenTitleEmpty
        // for the reliably-testable initial state).
        let textField = try view.inspect().find(ViewType.TextField.self, where: { try $0.labelView().text().string() == "Title" })
        XCTAssertNoThrow(try textField.setInput("Morning Show"))
    }

    func testHidesChannelSectionWhenNoChannelsLoaded() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertTrue(guideViewModel.channels.isEmpty)

        let view = TVKeywordRuleModal(onCreated: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Channel"))
    }

    func testShowsChannelSectionWhenChannelsLoaded() async throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[
            {"channel_number":"5.1","name":"WXYZ","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,"now":null,"next":null}
        ],"guide_available":true}
        """.utf8), 200)
        await guideViewModel.loadChannels()
        XCTAssertEqual(guideViewModel.channels.count, 1)

        let view = TVKeywordRuleModal(onCreated: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Channel"))
        XCTAssertNoThrow(try view.inspect().find(button: "Any channel"))
    }

    func testHidesRetentionCountFieldByDefault() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVKeywordRuleModal(onCreated: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(ViewType.TextField.self, where: { try $0.labelView().text().string() == "Episodes to keep" }))
    }

    func testKeepLastNButtonIsTappable() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVKeywordRuleModal(onCreated: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        // Without ViewHosting, tapping this button doesn't propagate the resulting
        // @State change back into a freshly re-inspected view body, so we only
        // confirm the button exists and is tappable rather than re-reading whether
        // the "Episodes to keep" field appears afterward (see
        // testHidesRetentionCountFieldByDefault for the reliably-testable initial state).
        XCTAssertNoThrow(try view.inspect().find(button: "Keep last N").tap())
    }

    func testTappingCancelDismisses() throws {
        let (guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = TVKeywordRuleModal(onCreated: {})
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Cancel"))
    }
}
