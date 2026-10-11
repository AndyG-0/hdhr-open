import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVDiscoveryCardViewTests: XCTestCase {
    private func makeAiring(
        title: String = "Morning Show",
        episodeTitle: String? = "The Pilot",
        channelNumber: String? = "4.1",
        isNew: Bool? = nil,
        imageUrl: String? = nil,
        start: TimeInterval? = 1_700_000_000,
        source: String? = nil
    ) -> HDHomeRunGuideEntry {
        HDHomeRunGuideEntry(
            title: title,
            episodeTitle: episodeTitle,
            start: start,
            imageUrl: imageUrl,
            channelNumber: channelNumber,
            isNew: isNew,
            source: source
        )
    }

    func testShowsTitleAndEpisodeTitle() throws {
        let view = TVDiscoveryCardView(airing: makeAiring()) {}

        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "The Pilot"))
    }

    func testHidesEpisodeTitleWhenMissing() throws {
        let view = TVDiscoveryCardView(airing: makeAiring(episodeTitle: nil)) {}

        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
        XCTAssertThrowsError(try view.inspect().find(text: "The Pilot"))
    }

    func testShowsChannelNumberWhenPresent() throws {
        let view = TVDiscoveryCardView(airing: makeAiring(channelNumber: "7.2")) {}

        XCTAssertNoThrow(try view.inspect().find(text: "7.2"))
    }

    func testHidesChannelNumberWhenMissing() throws {
        let view = TVDiscoveryCardView(airing: makeAiring(channelNumber: nil)) {}

        XCTAssertThrowsError(try view.inspect().find(text: "7.2"))
    }

    func testShowsNewBadgeWhenMarkedNew() throws {
        let view = TVDiscoveryCardView(airing: makeAiring(isNew: true)) {}

        XCTAssertNoThrow(try view.inspect().find(text: "NEW"))
    }

    func testHidesNewBadgeWhenNotNew() throws {
        let view = TVDiscoveryCardView(airing: makeAiring(isNew: false)) {}

        XCTAssertThrowsError(try view.inspect().find(text: "NEW"))
    }

    func testHidesNewBadgeWhenIsNewNil() throws {
        let view = TVDiscoveryCardView(airing: makeAiring(isNew: nil)) {}

        XCTAssertThrowsError(try view.inspect().find(text: "NEW"))
    }

    func testShowsPlaceholderIconWhenNoImage() throws {
        let view = TVDiscoveryCardView(airing: makeAiring(imageUrl: nil)) {}

        let image = try view.inspect().find(ViewType.Image.self)
        XCTAssertEqual(try image.actualImage().name(), "sparkles")
    }

    func testTappingCardInvokesOnSelect() throws {
        var didSelect = false
        let view = TVDiscoveryCardView(airing: makeAiring()) { didSelect = true }

        try view.inspect().find(ViewType.Button.self).tap()

        XCTAssertTrue(didSelect)
    }

    func testShowsSourceBadgeForNonPersonalizedSource() throws {
        let view = TVDiscoveryCardView(airing: makeAiring(source: "network_pick")) {}

        XCTAssertNoThrow(try view.inspect().find(text: "Network pick"))
    }

    func testHidesSourceBadgeWhenSourceIsPersonalizedOrNil() throws {
        let personalizedView = TVDiscoveryCardView(airing: makeAiring(source: "personalized")) {}
        XCTAssertThrowsError(try personalizedView.inspect().find(text: "Network pick"))

        let nilSourceView = TVDiscoveryCardView(airing: makeAiring(source: nil)) {}
        XCTAssertThrowsError(try nilSourceView.inspect().find(text: "Network pick"))
    }

    func testShowsFormattedDayDate() throws {
        let airing = makeAiring(start: 1_700_000_000)
        let view = TVDiscoveryCardView(airing: airing) {}

        XCTAssertNoThrow(try view.inspect().find(text: TimeFormatting.formatDayDate(airing.start)))
    }
}
