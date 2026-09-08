import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVChannelRowViewTests: XCTestCase {
    private func makeChannel(number: String = "5.1", isHD: Bool = false) -> HDHomeRunChannel {
        HDHomeRunChannel(channelNumber: number, name: "WXYZ", isHD: isHD)
    }

    private func makeAiring(title: String, offsetMinutes: Double = 0, durationMinutes: Double = 30) -> HDHomeRunGuideEntry {
        let now = Date().timeIntervalSince1970
        return HDHomeRunGuideEntry(
            title: title,
            start: now + offsetMinutes * 60,
            end: now + (offsetMinutes + durationMinutes) * 60,
            channelNumber: "5.1"
        )
    }

    func testShowsNoScheduleMessageWhenAiringsEmpty() throws {
        let view = TVChannelRowView(
            channel: makeChannel(),
            airings: [],
            isFavorite: false,
            onSelectAiring: { _ in },
            onTuneChannel: {},
            onToggleFavorite: {}
        )

        XCTAssertNoThrow(try view.inspect().find(text: "No schedule information"))
    }

    func testShowsProgramCardsForEachAiring() throws {
        let airings = [makeAiring(title: "Morning Show"), makeAiring(title: "Evening News", offsetMinutes: 30)]
        let view = TVChannelRowView(
            channel: makeChannel(),
            airings: airings,
            isFavorite: false,
            onSelectAiring: { _ in },
            onTuneChannel: {},
            onToggleFavorite: {}
        )

        XCTAssertThrowsError(try view.inspect().find(text: "No schedule information"))
        XCTAssertEqual(try view.inspect().findAll(TVProgramCardView.self).count, 2)
        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
        XCTAssertNoThrow(try view.inspect().find(text: "Evening News"))
    }

    func testShowsFavoriteStarWhenIsFavorite() throws {
        let view = TVChannelRowView(
            channel: makeChannel(),
            airings: [],
            isFavorite: true,
            onSelectAiring: { _ in },
            onTuneChannel: {},
            onToggleFavorite: {}
        )

        let starImages = try view.inspect().findAll(ViewType.Image.self).filter {
            (try? $0.actualImage().name()) == "star.fill"
        }
        XCTAssertEqual(starImages.count, 1)
    }

    func testHidesFavoriteStarWhenNotFavorite() throws {
        let view = TVChannelRowView(
            channel: makeChannel(),
            airings: [],
            isFavorite: false,
            onSelectAiring: { _ in },
            onTuneChannel: {},
            onToggleFavorite: {}
        )

        let starImages = try view.inspect().findAll(ViewType.Image.self).filter {
            (try? $0.actualImage().name()) == "star.fill"
        }
        XCTAssertEqual(starImages.count, 0)
    }

    func testShowsHDBadgeWhenChannelIsHD() throws {
        let view = TVChannelRowView(
            channel: makeChannel(isHD: true),
            airings: [],
            isFavorite: false,
            onSelectAiring: { _ in },
            onTuneChannel: {},
            onToggleFavorite: {}
        )

        XCTAssertNoThrow(try view.inspect().find(text: "HD"))
    }

    func testHidesHDBadgeWhenChannelIsNotHD() throws {
        let view = TVChannelRowView(
            channel: makeChannel(isHD: false),
            airings: [],
            isFavorite: false,
            onSelectAiring: { _ in },
            onTuneChannel: {},
            onToggleFavorite: {}
        )

        XCTAssertThrowsError(try view.inspect().find(text: "HD"))
    }

    func testTappingChannelHeaderInvokesOnTuneChannel() throws {
        var tuned = false
        let view = TVChannelRowView(
            channel: makeChannel(number: "5.1"),
            airings: [],
            isFavorite: false,
            onSelectAiring: { _ in },
            onTuneChannel: { tuned = true },
            onToggleFavorite: {}
        )

        try view.inspect().find(button: "5.1").tap()

        XCTAssertTrue(tuned)
    }
}
