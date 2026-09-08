import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSGuideGridViewTests: XCTestCase {
    private func makeGuideViewModel() -> GuideViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        return GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    private func makeChannel(number: String = "4.1", name: String = "WNBC", isHD: Bool = true, now: HDHomeRunGuideEntry? = nil) -> HDHomeRunChannel {
        HDHomeRunChannel(channelNumber: number, name: name, isHD: isHD, now: now)
    }

    func testShowsChannelNumberAndName() throws {
        let guideViewModel = makeGuideViewModel()
        let channel = makeChannel()

        let view = iOSGuideGridView(channels: [channel], onSelectAiring: { _, _ in }, onTuneChannel: { _ in })
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "4.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "WNBC"))
        XCTAssertNoThrow(try view.inspect().find(text: "HD"))
    }

    func testHidesHDBadgeForSDChannel() throws {
        let guideViewModel = makeGuideViewModel()
        let channel = makeChannel(isHD: false)

        let view = iOSGuideGridView(channels: [channel], onSelectAiring: { _, _ in }, onTuneChannel: { _ in })
            .environmentObject(guideViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "HD"))
    }

    func testShowsFavoriteStarWhenChannelIsFavorited() async throws {
        let guideViewModel = makeGuideViewModel()
        let channel = makeChannel()
        await guideViewModel.toggleFavorite(channelNumber: channel.channelNumber)
        XCTAssertTrue(guideViewModel.favoriteChannels.contains(channel.channelNumber))

        let view = iOSGuideGridView(channels: [channel], onSelectAiring: { _, _ in }, onTuneChannel: { _ in })
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.Image.self, where: { try $0.actualImage().name() == "star.fill" }))
    }

    func testHidesFavoriteStarWhenChannelIsNotFavorited() throws {
        let guideViewModel = makeGuideViewModel()
        let channel = makeChannel()
        XCTAssertTrue(guideViewModel.favoriteChannels.isEmpty)

        let view = iOSGuideGridView(channels: [channel], onSelectAiring: { _, _ in }, onTuneChannel: { _ in })
            .environmentObject(guideViewModel)

        XCTAssertThrowsError(try view.inspect().find(ViewType.Image.self, where: { try $0.actualImage().name() == "star.fill" }))
    }

    /// `trackRow` sources its airings from `guideViewModel.getAirings(for:)`, which falls back to
    /// `guideViewModel.channels` (not the `channels` array passed into the view) when there's no
    /// full-guide entry -- so the view model's own channel list must be loaded/mocked to match.
    func testShowsCurrentAiringTitleInTrackRow() async throws {
        let guideViewModel = makeGuideViewModel()
        let now = Date().timeIntervalSince1970
        let start = now - 1800
        let end = now + 1800

        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[{"channel_number":"4.1","name":"WNBC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,
        "now":{"title":"Today Show","start":\(start),"end":\(end)},"next":null}],"guide_available":true}
        """.utf8), 200)
        await guideViewModel.loadChannels()
        let channel = try XCTUnwrap(guideViewModel.channels.first)

        let view = iOSGuideGridView(channels: [channel], onSelectAiring: { _, _ in }, onTuneChannel: { _ in })
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(textWhere: { value, _ in value.contains("Today Show") }))
    }

    func testShowsRecordingIndicatorWhenRuleMatchesAiring() async throws {
        let guideViewModel = makeGuideViewModel()
        let now = Date().timeIntervalSince1970
        let start = now - 1800
        let end = now + 1800

        MockURLProtocol.handlers["/api/guide/channels"] = (Data("""
        {"channels":[{"channel_number":"4.1","name":"WNBC","is_hd":true,"is_drm":false,"stream_url":"","playback_url":null,
        "now":{"title":"Today Show","start":\(start),"end":\(end)},"next":null}],"guide_available":true}
        """.utf8), 200)
        await guideViewModel.loadChannels()
        let channel = try XCTUnwrap(guideViewModel.channels.first)
        let airing = try XCTUnwrap(channel.now)

        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data("""
        [{"RecordingRuleID":"r1","SeriesID":"s1","Title":"Today Show","DateTimeOnly":\(start)}]
        """.utf8), 200)
        await guideViewModel.loadRules()
        XCTAssertNotNil(guideViewModel.findRule(for: channel.channelNumber, airing: airing))

        let view = iOSGuideGridView(channels: [channel], onSelectAiring: { _, _ in }, onTuneChannel: { _ in })
            .environmentObject(guideViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.Image.self, where: { try $0.actualImage().name() == "record.circle.fill" }))
    }

    func testTapChannelCellInvokesOnTuneChannel() throws {
        let guideViewModel = makeGuideViewModel()
        let channel = makeChannel()
        var tunedChannel: HDHomeRunChannel?

        let view = iOSGuideGridView(
            channels: [channel],
            onSelectAiring: { _, _ in },
            onTuneChannel: { tunedChannel = $0 }
        )
        .environmentObject(guideViewModel)

        let channelButton = try view.inspect().find(ViewType.Button.self, where: { button in
            (try? button.find(text: channel.channelNumber)) != nil
        })
        try channelButton.tap()

        XCTAssertEqual(tunedChannel?.channelNumber, channel.channelNumber)
    }
}
