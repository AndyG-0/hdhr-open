import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVProgramCardViewTests: XCTestCase {
    private func makeAiring(
        title: String = "Morning Show",
        episodeTitle: String? = "The Pilot",
        offsetMinutes: Double = 0,
        durationMinutes: Double = 30
    ) -> HDHomeRunGuideEntry {
        let now = Date().timeIntervalSince1970
        return HDHomeRunGuideEntry(
            title: title,
            episodeTitle: episodeTitle,
            start: now + offsetMinutes * 60,
            end: now + (offsetMinutes + durationMinutes) * 60
        )
    }

    func testShowsAiringTitleAndEpisodeTitle() throws {
        let view = TVProgramCardView(airing: makeAiring(), onSelect: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "The Pilot"))
    }

    func testHidesEpisodeTitleWhenNilOrEmpty() throws {
        let view = TVProgramCardView(airing: makeAiring(episodeTitle: nil), onSelect: {})

        XCTAssertThrowsError(try view.inspect().find(text: "The Pilot"))
    }

    func testShowsLiveBadgeWhenCurrentlyAiring() throws {
        let airing = makeAiring(offsetMinutes: -10, durationMinutes: 30)
        let view = TVProgramCardView(airing: airing, onSelect: {})

        XCTAssertNoThrow(try view.inspect().find(text: "LIVE"))
    }

    func testHidesLiveBadgeWhenNotCurrentlyAiring() throws {
        let airing = makeAiring(offsetMinutes: 60, durationMinutes: 30)
        let view = TVProgramCardView(airing: airing, onSelect: {})

        XCTAssertThrowsError(try view.inspect().find(text: "LIVE"))
    }

    func testShowsRecordingIndicatorWhenScheduled() throws {
        let view = TVProgramCardView(airing: makeAiring(), isScheduled: true, onSelect: {})

        let recordImages = try view.inspect().findAll(ViewType.Image.self).filter {
            (try? $0.actualImage().name()) == "record.circle.fill"
        }
        XCTAssertEqual(recordImages.count, 1)
    }

    func testHidesRecordingIndicatorWhenNotScheduled() throws {
        let view = TVProgramCardView(airing: makeAiring(), isScheduled: false, onSelect: {})

        let recordImages = try view.inspect().findAll(ViewType.Image.self).filter {
            (try? $0.actualImage().name()) == "record.circle.fill"
        }
        XCTAssertEqual(recordImages.count, 0)
    }

    func testTappingCardInvokesOnSelect() throws {
        var selected = false
        let view = TVProgramCardView(airing: makeAiring(), onSelect: { selected = true })

        try view.inspect().find(ViewType.Button.self).tap()

        XCTAssertTrue(selected)
    }
}
