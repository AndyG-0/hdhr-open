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

    func testSliderTrackHas44PointTouchTargetHeight() throws {
        let view = iOSScrubBarView(currentTime: 10, duration: 100, isLive: false, isSeekable: true, onSeek: { _ in })
        let geo = try view.inspect().find(ViewType.GeometryReader.self)
        let frameHeight = try geo.fixedHeight()
        XCTAssertEqual(frameHeight, 44)
    }

    func testDraggableThumbKnobPresentWhenSeekableAndHasDuration() throws {
        let seekableView = iOSScrubBarView(currentTime: 10, duration: 100, isLive: false, isSeekable: true, onSeek: { _ in })
        let nonSeekableView = iOSScrubBarView(currentTime: 10, duration: 100, isLive: false, isSeekable: false, onSeek: { _ in })

        let seekableShapes = try seekableView.inspect().findAll(ViewType.Shape.self).count
        let nonSeekableShapes = try nonSeekableView.inspect().findAll(ViewType.Shape.self).count

        // Draggable thumb knob adds an additional shape to the slider track
        XCTAssertEqual(seekableShapes - nonSeekableShapes, 1)
    }

    func testThumbKnobAbsentWhenZeroDuration() throws {
        let zeroDurationSeekableView = iOSScrubBarView(currentTime: 10, duration: 0, isLive: false, isSeekable: true, onSeek: { _ in })
        let zeroDurationNonSeekableView = iOSScrubBarView(currentTime: 10, duration: 0, isLive: false, isSeekable: false, onSeek: { _ in })

        let seekableShapes = try zeroDurationSeekableView.inspect().findAll(ViewType.Shape.self).count
        let nonSeekableShapes = try zeroDurationNonSeekableView.inspect().findAll(ViewType.Shape.self).count

        // When duration is 0, thumb knob is omitted (shape count matches non-seekable)
        XCTAssertEqual(seekableShapes, nonSeekableShapes)
    }

    func testAcceptsOnScrubbingChangedCallback() throws {
        var scrubbingChangedCalled = false
        let view = iOSScrubBarView(
            currentTime: 10,
            duration: 100,
            isLive: false,
            isSeekable: true,
            onScrubbingChanged: { _ in scrubbingChangedCalled = true },
            onSeek: { _ in }
        )
        XCTAssertNotNil(view)
        XCTAssertFalse(scrubbingChangedCalled)
    }
}
