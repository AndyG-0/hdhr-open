import XCTest
@testable import HDHROpenKit

final class StreamURLBuilderTests: XCTestCase {
    func testLiveStreamURL() throws {
        let base = try XCTUnwrap(URL(string: "http://192.168.1.100:8000"))
        let url = StreamURLBuilder.liveStreamURL(baseURL: base, channelNumber: "4.1")
        XCTAssertEqual(url?.absoluteString, "http://192.168.1.100:8000/api/streaming/stream/4.1")
    }

    func testHLSPlaylistURL() throws {
        let base = try XCTUnwrap(URL(string: "http://192.168.1.100:8000"))
        let url = StreamURLBuilder.hlsPlaylistURL(baseURL: base, sessionId: "abc123")
        XCTAssertEqual(url?.absoluteString, "http://192.168.1.100:8000/api/hls/abc123/playlist.m3u8")
    }

    func testRecordingStreamURL() throws {
        let base = try XCTUnwrap(URL(string: "http://192.168.1.100:8000"))
        let url = StreamURLBuilder.recordingStreamURL(
            baseURL: base,
            playUrl: "http://hdhr/rec.mpg",
            recordingId: "rec_123",
            startOffset: 120.5,
            audioIndex: 1
        )
        XCTAssertNotNil(url)
        let str = try XCTUnwrap(url?.absoluteString)
        XCTAssertTrue(str.contains("recording_id=rec_123"))
        XCTAssertTrue(str.contains("start=120.5"))
        XCTAssertTrue(str.contains("audio_index=1"))
    }
}
