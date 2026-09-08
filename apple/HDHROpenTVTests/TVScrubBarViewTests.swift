import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVScrubBarViewTests: XCTestCase {
    func testShowsLiveIndicatorWhenLive() throws {
        let view = TVScrubBarView(currentTime: 30, duration: 0, isLive: true, isSeekable: false, onSeek: { _ in })

        XCTAssertNoThrow(try view.inspect().find(text: "LIVE"))
    }

    func testShowsCurrentAndTotalTimestampsWhenNotLive() throws {
        let view = TVScrubBarView(currentTime: 65, duration: 125, isLive: false, isSeekable: true, onSeek: { _ in })

        XCTAssertNoThrow(try view.inspect().find(text: "1:05"))
        XCTAssertNoThrow(try view.inspect().find(text: "2:05"))
        XCTAssertThrowsError(try view.inspect().find(text: "LIVE"))
    }

    func testHidesLiveIndicatorAndTotalDurationWhenDurationUnknownAndNotLive() throws {
        let view = TVScrubBarView(currentTime: 5, duration: 0, isLive: false, isSeekable: false, onSeek: { _ in })

        XCTAssertNoThrow(try view.inspect().find(text: "0:05"))
        XCTAssertThrowsError(try view.inspect().find(text: "LIVE"))
    }

    func testHidesThumbnailPreviewWhenNotScrubbing() throws {
        // scrubTime is a private @State defaulting to nil, so the thumbnail
        // preview box (which requires scrubTime != nil to match a cue) never
        // renders in a statically constructed (non-hosted) tree - only a
        // live drag gesture (requiring ViewHosting + gesture simulation)
        // would set it.
        let cue = ThumbnailCue(start: 0, end: 10, x: 0, y: 0, width: 100, height: 60, imageURL: "http://example.com/1.jpg")
        let view = TVScrubBarView(
            currentTime: 5,
            duration: 100,
            isLive: false,
            isSeekable: true,
            thumbnailCues: [cue],
            spriteURL: URL(string: "http://example.com/sprite.jpg"),
            onSeek: { _ in }
        )

        XCTAssertThrowsError(try view.inspect().find(ViewType.AsyncImage.self))
    }
}
