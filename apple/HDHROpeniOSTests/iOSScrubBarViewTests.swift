import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

@MainActor
final class iOSScrubBarViewTests: XCTestCase {
    func testShowsLiveIndicatorWhenLive() throws {
        let view = iOSScrubBarView(currentTime: 30, duration: 0, isLive: true, isSeekable: false, onSeek: { _ in })

        XCTAssertNoThrow(try view.inspect().find(text: "LIVE"))
    }

    func testShowsCurrentAndTotalTimestampsWhenNotLive() throws {
        let view = iOSScrubBarView(currentTime: 65, duration: 125, isLive: false, isSeekable: true, onSeek: { _ in })

        XCTAssertNoThrow(try view.inspect().find(text: "1:05"))
        XCTAssertNoThrow(try view.inspect().find(text: "2:05"))
        XCTAssertThrowsError(try view.inspect().find(text: "LIVE"))
    }

    func testHidesLiveIndicatorAndShowsElapsedTimeWhenDurationUnknownAndNotLive() throws {
        let view = iOSScrubBarView(currentTime: 5, duration: 0, isLive: false, isSeekable: false, onSeek: { _ in })

        XCTAssertNoThrow(try view.inspect().find(text: "0:05"))
        XCTAssertThrowsError(try view.inspect().find(text: "LIVE"))
    }

    func testHidesThumbnailPreviewWhenNotDragging() throws {
        // isDragging is a private @State defaulting to false, so the
        // AsyncImage thumbnail preview never renders in a statically
        // constructed (non-hosted) tree, even when cues/spriteURL are
        // supplied - only a live drag gesture (which requires ViewHosting +
        // gesture simulation) would flip isDragging to true.
        let cue = ThumbnailCue(start: 0, end: 10, x: 0, y: 0, width: 100, height: 60, imageURL: "http://example.com/1.jpg")
        let view = iOSScrubBarView(
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
