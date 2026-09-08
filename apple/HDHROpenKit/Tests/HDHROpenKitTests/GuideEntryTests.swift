import XCTest
@testable import HDHROpenKit

final class GuideEntryTests: XCTestCase {
    func testIdUsesSeriesIdWhenAvailable() {
        let entry = HDHomeRunGuideEntry(seriesId: "SH123", title: "Show", start: 100, channelNumber: "4.1")
        XCTAssertEqual(entry.id, "SH123_100.0_4.1")
    }

    func testIdFallsBackToTitleAndStart() {
        let entry = HDHomeRunGuideEntry(title: "Show", start: 200, channelNumber: "4.1")
        XCTAssertEqual(entry.id, "Show_200.0_4.1")
    }

    func testIdFallsBackWhenNoStartOrChannel() {
        let entry = HDHomeRunGuideEntry(title: "Show")
        XCTAssertEqual(entry.id, "Show_0.0_")
    }

    func testFormattedAudioStereo() {
        XCTAssertEqual(HDHomeRunGuideEntry(title: "T", audio: "Stereo").formattedAudio, "STEREO")
    }

    func testFormattedAudioSurround() {
        XCTAssertEqual(HDHomeRunGuideEntry(title: "T", audio: "5.1 Surround").formattedAudio, "5.1")
    }

    func testFormattedAudioDolby() {
        XCTAssertEqual(HDHomeRunGuideEntry(title: "T", audio: "Dolby Digital").formattedAudio, "DOLBY")
        XCTAssertEqual(HDHomeRunGuideEntry(title: "T", audio: "DD+").formattedAudio, "DOLBY")
    }

    func testFormattedAudioMono() {
        XCTAssertEqual(HDHomeRunGuideEntry(title: "T", audio: "mono").formattedAudio, "MONO")
    }

    func testFormattedAudioFallsBackToUppercasedRaw() {
        XCTAssertEqual(HDHomeRunGuideEntry(title: "T", audio: "custom").formattedAudio, "CUSTOM")
    }

    func testFormattedAudioNilWhenBlankOrMissing() {
        XCTAssertNil(HDHomeRunGuideEntry(title: "T").formattedAudio)
        XCTAssertNil(HDHomeRunGuideEntry(title: "T", audio: "   ").formattedAudio)
    }

    func testFormattedEpisodeDesignationWithSeasonAndEpisode() {
        let entry = HDHomeRunGuideEntry(title: "T", episodeNumber: "5", seasonNumber: 2)
        XCTAssertEqual(entry.formattedEpisodeDesignation, "S2E5")
    }

    func testFormattedEpisodeDesignationWithDottedEpisodeAndSeason() {
        let entry = HDHomeRunGuideEntry(title: "T", episodeNumber: "2.5", seasonNumber: 2)
        XCTAssertEqual(entry.formattedEpisodeDesignation, "S2E5")
    }

    func testFormattedEpisodeDesignationDottedEpisodeOnly() {
        let entry = HDHomeRunGuideEntry(title: "T", episodeNumber: "3.7")
        XCTAssertEqual(entry.formattedEpisodeDesignation, "S3E7")
    }

    func testFormattedEpisodeDesignationPlainEpisodeOnly() {
        let entry = HDHomeRunGuideEntry(title: "T", episodeNumber: "12")
        XCTAssertEqual(entry.formattedEpisodeDesignation, "Ep 12")
    }

    func testFormattedEpisodeDesignationNilWhenMissing() {
        XCTAssertNil(HDHomeRunGuideEntry(title: "T").formattedEpisodeDesignation)
        XCTAssertNil(HDHomeRunGuideEntry(title: "T", episodeNumber: "").formattedEpisodeDesignation)
    }

    func testStartAndEndDates() {
        let entry = HDHomeRunGuideEntry(title: "T", start: 1000, end: 2000)
        XCTAssertEqual(entry.startDate, Date(timeIntervalSince1970: 1000))
        XCTAssertEqual(entry.endDate, Date(timeIntervalSince1970: 2000))
    }

    func testStartAndEndDatesNilWhenMissing() {
        let entry = HDHomeRunGuideEntry(title: "T")
        XCTAssertNil(entry.startDate)
        XCTAssertNil(entry.endDate)
    }

    func testDurationSeconds() {
        let entry = HDHomeRunGuideEntry(title: "T", start: 1000, end: 4600)
        XCTAssertEqual(entry.durationSeconds, 3600)
    }

    func testDurationSecondsNilWhenMissingOrInvalid() {
        XCTAssertNil(HDHomeRunGuideEntry(title: "T").durationSeconds)
        XCTAssertNil(HDHomeRunGuideEntry(title: "T", start: 2000, end: 1000).durationSeconds)
    }

    func testIsCurrentlyAiring() {
        let entry = HDHomeRunGuideEntry(title: "T", start: 1000, end: 2000)
        XCTAssertTrue(entry.isCurrentlyAiring(at: 1500))
        XCTAssertFalse(entry.isCurrentlyAiring(at: 999))
        XCTAssertFalse(entry.isCurrentlyAiring(at: 2000))
    }

    func testIsCurrentlyAiringFalseWhenMissingBounds() {
        XCTAssertFalse(HDHomeRunGuideEntry(title: "T").isCurrentlyAiring(at: 1000))
    }

    func testProgressBeforeStart() {
        let entry = HDHomeRunGuideEntry(title: "T", start: 5_000_000_000, end: 5_000_003_600)
        XCTAssertEqual(entry.progress, 0)
    }

    func testProgressAfterEnd() {
        let entry = HDHomeRunGuideEntry(title: "T", start: 1, end: 2)
        XCTAssertEqual(entry.progress, 1.0)
    }

    func testProgressZeroWhenInvalidBoundsOrMissing() {
        XCTAssertEqual(HDHomeRunGuideEntry(title: "T").progress, 0)
        XCTAssertEqual(HDHomeRunGuideEntry(title: "T", start: 2000, end: 1000).progress, 0)
    }
}
