import XCTest
@testable import HDHROpenKit

final class ModelsSerializationTests: XCTestCase {
    func testDecodeChannel() throws {
        let json = """
        {
            "channel_number": "5.1",
            "name": "KING-DT",
            "is_hd": true,
            "is_drm": false,
            "stream_url": "http://192.168.1.50:5004/auto/v5.1",
            "playback_url": "/api/streaming/stream/5.1",
            "now": {
                "title": "Evening News",
                "start": 1700000000,
                "end": 1700003600
            },
            "next": null
        }
        """.data(using: .utf8)!

        let channel = try JSONDecoder().decode(HDHomeRunChannel.self, from: json)
        XCTAssertEqual(channel.channelNumber, "5.1")
        XCTAssertEqual(channel.name, "KING-DT")
        XCTAssertTrue(channel.isHD)
        XCTAssertEqual(channel.now?.title, "Evening News")
    }

    func testDecodeRecording() throws {
        let json = """
        {
            "recording_id": "rec_999",
            "title": "Cosmos: A Spacetime Odyssey",
            "episode_title": "Standing Up in the Milky Way",
            "season_number": 1,
            "episode_number": "1",
            "start": 1700000000,
            "record_end": 1700003600,
            "play_url": "/api/dvr/rec_999.mpg",
            "duration_seconds": 3600.0,
            "file_size_bytes": 4500000000
        }
        """.data(using: .utf8)!

        let rec = try JSONDecoder().decode(HDHomeRunRecording.self, from: json)
        XCTAssertEqual(rec.recordingId, "rec_999")
        XCTAssertEqual(rec.title, "Cosmos: A Spacetime Odyssey")
        XCTAssertEqual(rec.episodeDesignation, "S1:E1")
        XCTAssertEqual(rec.formattedDuration, "1h 0m")
        XCTAssertTrue(rec.formattedFileSize.contains("GB"))
    }
}
