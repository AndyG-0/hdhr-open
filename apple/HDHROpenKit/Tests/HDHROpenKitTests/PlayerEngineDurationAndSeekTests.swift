import AVFoundation
import XCTest
@testable import HDHROpenKit

@MainActor
final class PlayerEngineDurationAndSeekTests: XCTestCase {
    func testLoadMediaWithInitialDurationSetsDurationImmediately() throws {
        let engine = PlayerEngine()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))

        engine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0)

        XCTAssertEqual(engine.duration, 3600.0)
        XCTAssertEqual(engine.timeOffset, 0.0)
        XCTAssertTrue(engine.isSeekable)
    }

    func testLoadMediaWithAutoplayFalseLeavesStatePaused() throws {
        let engine = PlayerEngine()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))

        engine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0, autoplay: false)

        XCTAssertEqual(engine.state, .paused)
    }

    func testLoadMediaWithInitialTimeOffsetSetsOffset() throws {
        let engine = PlayerEngine()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))

        engine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0, initialTimeOffset: 900.0)

        XCTAssertEqual(engine.duration, 3600.0)
        XCTAssertEqual(engine.timeOffset, 900.0)
        XCTAssertEqual(engine.currentTime, 900.0)
    }

    func testResetClearsTimeOffsetAndDuration() throws {
        let engine = PlayerEngine()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))

        engine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0, initialTimeOffset: 900.0)
        engine.reset()

        XCTAssertEqual(engine.duration, 0.0)
        XCTAssertEqual(engine.timeOffset, 0.0)
        XCTAssertEqual(engine.currentTime, 0.0)
    }

    func testSeekUpdatesCurrentTimeOptimistically() throws {
        let engine = PlayerEngine()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))

        engine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0)
        engine.seek(to: 500.0)

        XCTAssertEqual(engine.currentTime, 500.0)
    }

    func testPrepareForServerSeekSetsCurrentTimeAndBuffersWithoutSeekingAVPlayer() throws {
        let engine = PlayerEngine()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))

        engine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0)
        engine.prepareForServerSeek(to: 1200.0)

        XCTAssertEqual(engine.currentTime, 1200.0)
        XCTAssertEqual(engine.state, .buffering)
    }

    func testIsPositionInSeekableRangeReturnsFalseWhenNoRanges() {
        let engine = PlayerEngine()
        XCTAssertFalse(engine.isPositionInSeekableRange(100.0))
    }

    func testIsPositionInSeekableRangeReturnsFalseForPositionBeforeTimeOffset() throws {
        let engine = PlayerEngine()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))
        engine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0, initialTimeOffset: 600.0)

        // Seeking to 300s when session starts at 600s is before the session start
        XCTAssertFalse(engine.isPositionInSeekableRange(300.0))
    }
}
