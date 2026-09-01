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

    func testDecodeGuideEntry() throws {
        let json = """
        {
            "series_id": "SH123",
            "title": "Cosmos: A Spacetime Odyssey",
            "episode_title": "Standing Up in the Milky Way",
            "season_number": 1,
            "episode_number": "1",
            "synopsis": "A journey across time and space.",
            "start": 1700000000,
            "end": 1700003600,
            "original_airdate": "2023-11-14",
            "image_url": "http://example.com/poster.jpg",
            "channel_number": "4.1",
            "category": "Documentary, Science",
            "is_new": true,
            "has_cc": true,
            "audio": "stereo"
        }
        """.data(using: .utf8)!

        let entry = try JSONDecoder().decode(HDHomeRunGuideEntry.self, from: json)
        XCTAssertEqual(entry.title, "Cosmos: A Spacetime Odyssey")
        XCTAssertEqual(entry.episodeTitle, "Standing Up in the Milky Way")
        XCTAssertEqual(entry.seasonNumber, 1)
        XCTAssertEqual(entry.formattedEpisodeDesignation, "S1E1")
        XCTAssertEqual(entry.category, "Documentary, Science")
        XCTAssertEqual(entry.isNew, true)
        XCTAssertEqual(entry.hasCC, true)
        XCTAssertEqual(entry.formattedAudio, "STEREO")
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
        XCTAssertFalse(rec.isHDHomeRunNative)
    }

    func testDecodeHDHomeRunNativeRecording() throws {
        let json = """
        {
            "recording_id": "EP012345670001",
            "title": "Local News",
            "episode_title": null,
            "channel_number": "4.1",
            "channel_name": "NBC",
            "start": 1700000000,
            "record_end": 1700001800,
            "play_url": "http://192.168.1.50:50000/recorded/12345678",
            "duration_seconds": 1800.0,
            "provider": "hdhomerun",
            "is_dvr_file": true
        }
        """.data(using: .utf8)!

        let rec = try JSONDecoder().decode(HDHomeRunRecording.self, from: json)
        XCTAssertEqual(rec.recordingId, "EP012345670001")
        XCTAssertEqual(rec.title, "Local News")
        XCTAssertEqual(rec.playUrl, "http://192.168.1.50:50000/recorded/12345678")
        XCTAssertTrue(rec.isHDHomeRunNative)
        XCTAssertEqual(rec.formattedDuration, "30m")
    }
}
