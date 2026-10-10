import XCTest
@testable import HDHROpenKit

final class APIEndpointsTests: XCTestCase {
    func testGuideWithoutWindow() {
        XCTAssertEqual(APIEndpoints.guide(), "/api/guide")
    }

    func testGuideWithWindow() {
        let path = APIEndpoints.guide(start: 100, end: 200)
        XCTAssertTrue(path.hasPrefix("/api/guide?"))
        XCTAssertTrue(path.contains("start=100.0"))
        XCTAssertTrue(path.contains("end=200.0"))
    }

    func testUpdateRecordingRule() {
        XCTAssertEqual(APIEndpoints.updateRecordingRule("rule_123"), "/api/dvr/recording-rules/rule_123")
    }

    func testRecordingsWithoutSearch() {
        XCTAssertEqual(APIEndpoints.recordings(), "/api/dvr/recordings")
    }

    func testRecordingsWithBlankSearchOmitsQueryString() {
        XCTAssertEqual(APIEndpoints.recordings(search: ""), "/api/dvr/recordings")
    }

    func testRecordingsWithSearchAppendsQueryString() {
        XCTAssertEqual(APIEndpoints.recordings(search: "the office"), "/api/dvr/recordings?search=the%20office")
    }
}
