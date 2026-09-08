import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVChannelSwitcherOverlayTests: XCTestCase {
    private let channel1 = HDHomeRunChannel(channelNumber: "4.1", name: "WNBC", isHD: true)
    private let channel2 = HDHomeRunChannel(channelNumber: "5.1", name: "WNYW", isHD: false)

    func testShowsHeaderAndDismissButton() throws {
        let view = TVChannelSwitcherOverlay(channels: [channel1], currentChannel: nil, onSelectChannel: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Quick Channel Switcher"))
        XCTAssertNoThrow(try view.inspect().find(button: "Dismiss"))
    }

    func testShowsChannelNumberAndName() throws {
        let view = TVChannelSwitcherOverlay(channels: [channel1, channel2], currentChannel: nil, onSelectChannel: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "4.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "WNBC"))
        XCTAssertNoThrow(try view.inspect().find(text: "5.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "WNYW"))
    }

    func testShowsHDBadgeOnlyForHDChannels() throws {
        let view = TVChannelSwitcherOverlay(channels: [channel1, channel2], currentChannel: nil, onSelectChannel: { _ in }, onDismiss: {})

        // Only channel1 is HD, so exactly one "HD" badge should render.
        let hdTexts = try view.inspect().findAll(ViewType.Text.self, where: { try $0.string() == "HD" })
        XCTAssertEqual(hdTexts.count, 1)
    }

    func testShowsNowPlayingTitleWhenPresent() throws {
        let airing = HDHomeRunGuideEntry(title: "Nightly News")
        let channelWithNow = HDHomeRunChannel(channelNumber: "4.1", name: "WNBC", now: airing)
        let view = TVChannelSwitcherOverlay(channels: [channelWithNow], currentChannel: nil, onSelectChannel: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Nightly News"))
    }

    func testHidesNowPlayingTitleWhenAbsent() throws {
        let view = TVChannelSwitcherOverlay(channels: [channel1], currentChannel: nil, onSelectChannel: { _ in }, onDismiss: {})

        XCTAssertNil(channel1.now)
        XCTAssertThrowsError(try view.inspect().find(ViewType.Text.self, where: { try $0.string() == "Nightly News" }))
    }

    func testTappingDismissButtonInvokesCallback() throws {
        var dismissed = false
        let view = TVChannelSwitcherOverlay(channels: [channel1], currentChannel: nil, onSelectChannel: { _ in }, onDismiss: { dismissed = true })

        try view.inspect().find(button: "Dismiss").tap()

        XCTAssertTrue(dismissed)
    }

    func testTappingChannelInvokesOnSelectChannel() throws {
        var selected: HDHomeRunChannel?
        let view = TVChannelSwitcherOverlay(
            channels: [channel1, channel2],
            currentChannel: nil,
            onSelectChannel: { selected = $0 },
            onDismiss: {}
        )

        // Button order in the tree: Dismiss, then one per channel in list order.
        let buttons = try view.inspect().findAll(ViewType.Button.self)
        XCTAssertEqual(buttons.count, 3)
        try buttons[2].tap()

        XCTAssertEqual(selected?.channelNumber, "5.1")
    }
}
