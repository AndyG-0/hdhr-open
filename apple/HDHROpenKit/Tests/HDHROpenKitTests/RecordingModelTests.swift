import XCTest
@testable import HDHROpenKit

final class RecordingModelTests: XCTestCase {
    func testIsInProgressTrueWhenRecordEndInFuture() {
        let rec = HDHomeRunRecording(title: "T", recordEnd: Date().timeIntervalSince1970 + 3600)
        XCTAssertTrue(rec.isInProgress)
    }

    func testIsInProgressFalseWhenRecordEndInPastOrMissing() {
        XCTAssertFalse(HDHomeRunRecording(title: "T", recordEnd: Date().timeIntervalSince1970 - 3600).isInProgress)
        XCTAssertFalse(HDHomeRunRecording(title: "T").isInProgress)
    }

    func testFormattedDurationMinutesOnly() {
        XCTAssertEqual(HDHomeRunRecording(title: "T", durationSeconds: 300).formattedDuration, "5m")
    }

    func testFormattedDurationEmptyWhenMissingOrZero() {
        XCTAssertEqual(HDHomeRunRecording(title: "T").formattedDuration, "")
        XCTAssertEqual(HDHomeRunRecording(title: "T", durationSeconds: 0).formattedDuration, "")
    }

    func testEpisodeDesignationEpisodeOnly() {
        XCTAssertEqual(HDHomeRunRecording(title: "T", episodeNumber: "7").episodeDesignation, "Ep 7")
    }

    func testEpisodeDesignationNilWhenMissing() {
        XCTAssertNil(HDHomeRunRecording(title: "T").episodeDesignation)
    }

    func testFormattedFileSizeMegabytes() {
        let rec = HDHomeRunRecording(title: "T", fileSizeBytes: 200 * 1024 * 1024)
        XCTAssertEqual(rec.formattedFileSize, "200 MB")
    }

    func testFormattedFileSizeEmptyWhenMissingOrZero() {
        XCTAssertEqual(HDHomeRunRecording(title: "T").formattedFileSize, "")
        XCTAssertEqual(HDHomeRunRecording(title: "T", fileSizeBytes: 0).formattedFileSize, "")
    }

    func testAudioInfoDisplayLabelWithTitleAndSurround() {
        let audio = HDHomeRunRecordingAudioInfo(index: 0, codec: "ac3", channels: 6, title: "English")
        XCTAssertEqual(audio.displayLabel, "English • 5.1 Surround • AC3")
        XCTAssertEqual(audio.id, 0)
    }

    func testAudioInfoDisplayLabelWithLanguageFallback() {
        let audio = HDHomeRunRecordingAudioInfo(index: 1, channels: 2, language: "es")
        XCTAssertEqual(audio.displayLabel, "ES • Stereo")
    }

    func testAudioInfoDisplayLabelWithTrackFallbackAndOtherChannelCount() {
        let audio = HDHomeRunRecordingAudioInfo(index: 2, channels: 4)
        XCTAssertEqual(audio.displayLabel, "Track 3 • 4 ch")
    }

    func testRecordingDetailAndTranscodeInfoDecode() throws {
        let json = """
        {
            "is_in_progress": true,
            "duration_seconds": 1800.0,
            "video": {"codec": "h264", "width": 1920, "height": 1080, "fps": 29.97},
            "audio": [{"index": 0, "codec": "ac3", "channels": 2}],
            "has_captions": true,
            "transcode": {"transcoding": true, "preset": "mobile", "preset_label": "Mobile", "hardware": true}
        }
        """.data(using: .utf8)!

        let detail = try JSONDecoder().decode(HDHomeRunRecordingDetail.self, from: json)
        XCTAssertTrue(detail.isInProgress)
        XCTAssertEqual(detail.durationSeconds, 1800.0)
        XCTAssertEqual(detail.video?.codec, "h264")
        XCTAssertEqual(detail.video?.width, 1920)
        XCTAssertEqual(detail.audio.count, 1)
        XCTAssertTrue(detail.hasCaptions)
        XCTAssertTrue(detail.transcode.transcoding)
        XCTAssertEqual(detail.transcode.presetLabel, "Mobile")
        XCTAssertTrue(detail.transcode.hardware)
    }
}
