import XCTest
@testable import HDHROpenKit

final class VTTParserTests: XCTestCase {
    func testParseCaptions() {
        let vtt = """
        WEBVTT

        00:00:01.000 --> 00:00:04.000
        Welcome to HDHR Open!

        00:00:05.500 --> 00:00:08.200
        Enjoy live television and DVR.
        """

        let cues = VTTParser.parseCaptions(from: vtt)
        XCTAssertEqual(cues.count, 2)
        XCTAssertEqual(cues[0].start, 1.0)
        XCTAssertEqual(cues[0].end, 4.0)
        XCTAssertEqual(cues[0].text, "Welcome to HDHR Open!")

        XCTAssertEqual(cues[1].start, 5.5)
        XCTAssertEqual(cues[1].end, 8.2)
        XCTAssertEqual(cues[1].text, "Enjoy live television and DVR.")

        XCTAssertTrue(cues[0].contains(time: 2.5))
        XCTAssertFalse(cues[0].contains(time: 4.5))
    }

    func testParseThumbnailVtt() {
        let vtt = """
        WEBVTT

        00:00:00.000 --> 00:00:10.000
        thumb.jpg#xywh=0,0,160,90

        00:00:10.000 --> 00:00:20.000
        thumb.jpg#xywh=160,0,160,90
        """

        let cues = VTTParser.parseThumbnailVtt(from: vtt)
        XCTAssertEqual(cues.count, 2)
        XCTAssertEqual(cues[0].start, 0.0)
        XCTAssertEqual(cues[0].end, 10.0)
        XCTAssertEqual(cues[0].x, 0)
        XCTAssertEqual(cues[0].y, 0)
        XCTAssertEqual(cues[0].width, 160)
        XCTAssertEqual(cues[0].height, 90)

        XCTAssertEqual(cues[1].x, 160)
        XCTAssertEqual(cues[1].y, 0)
        XCTAssertTrue(cues[1].contains(time: 15.0))
    }
}
