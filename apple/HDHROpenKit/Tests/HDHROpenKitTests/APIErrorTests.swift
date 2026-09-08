import XCTest
@testable import HDHROpenKit

final class APIErrorTests: XCTestCase {
    func testInvalidURLDescription() {
        XCTAssertEqual(APIError.invalidURL.errorDescription, "Invalid server URL.")
        XCTAssertEqual(APIError.invalidURL.localizedDescription, "Invalid server URL.")
    }

    func testNetworkErrorDescription() {
        let error = APIError.networkError("The Internet connection appears to be offline.")
        XCTAssertEqual(error.errorDescription, "Network connection error: The Internet connection appears to be offline.")
    }

    func testServerErrorDescription() {
        let error = APIError.serverError(statusCode: 500, message: "boom")
        XCTAssertEqual(error.errorDescription, "Server error (500): boom")
    }

    func testUnauthorizedDescriptionPassesThroughMessage() {
        // .unauthorized surfaces the raw message verbatim (no extra prefix),
        // unlike most other cases which wrap the message in boilerplate text.
        let error = APIError.unauthorized("Session expired")
        XCTAssertEqual(error.errorDescription, "Session expired")
    }

    func testForbiddenDescription() {
        XCTAssertEqual(APIError.forbidden.errorDescription, "Admin privileges required for this action.")
    }

    func testNotFoundDescriptionIncludesResource() {
        let error = APIError.notFound("recording_id=abc123")
        XCTAssertEqual(error.errorDescription, "Resource not found: recording_id=abc123")
    }

    func testDecodingErrorDescription() {
        let error = APIError.decodingError("keyNotFound(title)")
        XCTAssertEqual(error.errorDescription, "Data parsing error: keyNotFound(title)")
    }

    func testNoActiveWatchSessionDescription() {
        XCTAssertEqual(APIError.noActiveWatchSession.errorDescription, "No active watch session.")
    }

    func testLockedOutDescriptionPassesThroughMessage() {
        // .lockedOut also surfaces its message verbatim, same as .unauthorized.
        let error = APIError.lockedOut("Too many attempts, try again later.")
        XCTAssertEqual(error.errorDescription, "Too many attempts, try again later.")
    }

    func testCrossDeviceSyncActiveDescription() {
        XCTAssertEqual(
            APIError.crossDeviceSyncActive.errorDescription,
            "SyncPlay and SharePlay can't run at the same time. Leave the current session first."
        )
    }

    func testErrorDescriptionDrivesLocalizedDescriptionForAllCases() {
        // LocalizedError's default localizedDescription implementation defers
        // to errorDescription - verify that bridging holds for a representative
        // sample of cases (not just the trivial ones above).
        let cases: [APIError] = [
            .serverError(statusCode: 418, message: "teapot"),
            .notFound("thing"),
            .decodingError("parse fail")
        ]
        for error in cases {
            XCTAssertEqual(error.localizedDescription, error.errorDescription)
        }
    }
}
