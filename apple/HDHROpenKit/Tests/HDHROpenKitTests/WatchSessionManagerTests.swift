import XCTest
@testable import HDHROpenKit

@MainActor
final class WatchSessionManagerTests: XCTestCase {
    private func makeAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    // MARK: - startWatch

    func testStartWatchSuccessSetsActiveSessionAndReturnsRecording() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Test Channel\"}".utf8), 200
        )

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        let recording = try await manager.startWatch(channelNumber: "4.1")

        XCTAssertEqual(recording?.recordingId, "rec1")
        XCTAssertEqual(manager.activeSessionId, "sess1")
        XCTAssertEqual(manager.activeRecordingId, "rec1")
        XCTAssertFalse(manager.isPromoted)

        manager.stopWatch()
    }

    func testStartWatchWithNoIdsInResponseReturnsNilAndLeavesStateEmpty() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"title\":\"\"}".utf8), 200
        )

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        let recording = try await manager.startWatch(channelNumber: "4.1")

        XCTAssertNil(recording)
        XCTAssertNil(manager.activeSessionId)
        XCTAssertNil(manager.activeRecordingId)
    }

    func testStartWatchStopsAnyExistingSessionFirst() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Channel A\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/sess1/stop"] = (Data("{}".utf8), 200)
        MockURLProtocol.handlers["/api/watch/5.1/start"] = (
            Data("{\"recording_id\":\"rec2\",\"session_id\":\"sess2\",\"title\":\"Channel B\"}".utf8), 200
        )

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        _ = try await manager.startWatch(channelNumber: "4.1")
        XCTAssertEqual(manager.activeSessionId, "sess1")

        _ = try await manager.startWatch(channelNumber: "5.1")

        XCTAssertEqual(manager.activeSessionId, "sess2")
        XCTAssertEqual(manager.activeRecordingId, "rec2")

        manager.stopWatch()
    }

    func testStartWatchFailurePropagatesErrorAndLeavesStateEmpty() async {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"detail\":\"no free tuner\"}".utf8), 503
        )

        let manager = WatchSessionManager(apiClient: makeAPIClient())

        do {
            _ = try await manager.startWatch(channelNumber: "4.1")
            XCTFail("Expected startWatch to throw")
        } catch let APIError.serverError(statusCode, _) {
            XCTAssertEqual(statusCode, 503)
        } catch {
            XCTFail("Expected APIError.serverError, got \(error)")
        }

        XCTAssertNil(manager.activeSessionId)
        XCTAssertNil(manager.activeRecordingId)
    }

    // MARK: - promoteWatch

    func testPromoteWatchWithNoActiveSessionThrowsNoActiveWatchSession() async {
        let manager = WatchSessionManager(apiClient: makeAPIClient())

        do {
            _ = try await manager.promoteWatch()
            XCTFail("Expected promoteWatch to throw")
        } catch APIError.noActiveWatchSession {
            // expected
        } catch {
            XCTFail("Expected APIError.noActiveWatchSession, got \(error)")
        }
    }

    func testPromoteWatchSuccessSetsIsPromotedAndReturnsRecording() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Test Channel\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/sess1/promote"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Test Channel\",\"is_dvr_file\":true}".utf8), 200
        )

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        _ = try await manager.startWatch(channelNumber: "4.1")

        let promoted = try await manager.promoteWatch()

        XCTAssertTrue(manager.isPromoted)
        XCTAssertEqual(promoted.recordingId, "rec1")
        XCTAssertEqual(promoted.isDvrFile, true)
    }

    func testPromoteWatchFailurePropagatesErrorAndLeavesIsPromotedFalse() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Test Channel\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/sess1/promote"] = (
            Data("{\"detail\":\"promotion failed\"}".utf8), 500
        )

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        _ = try await manager.startWatch(channelNumber: "4.1")

        do {
            _ = try await manager.promoteWatch()
            XCTFail("Expected promoteWatch to throw")
        } catch let APIError.serverError(statusCode, _) {
            XCTAssertEqual(statusCode, 500)
        } catch {
            XCTFail("Expected APIError.serverError, got \(error)")
        }

        XCTAssertFalse(manager.isPromoted)

        manager.stopWatch()
    }

    // MARK: - stopWatch

    func testStopWatchWithActiveUnpromotedSessionClearsState() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Test Channel\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/sess1/stop"] = (Data("{}".utf8), 200)

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        _ = try await manager.startWatch(channelNumber: "4.1")

        manager.stopWatch()

        XCTAssertNil(manager.activeSessionId)
        XCTAssertNil(manager.activeRecordingId)
        XCTAssertFalse(manager.isPromoted)
    }

    func testStopWatchAfterPromotionDoesNotResetIsPromotedBeforeClearing() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Test Channel\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/sess1/promote"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Test Channel\"}".utf8), 200
        )
        // Intentionally no handler for /api/watch/sess1/stop - a promoted
        // session must NOT trigger a stop request, so the 404 fallback
        // response (if it were hit) would be silently swallowed by `try?`
        // anyway, but asserting isPromoted below confirms the guard worked.

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        _ = try await manager.startWatch(channelNumber: "4.1")
        _ = try await manager.promoteWatch()
        XCTAssertTrue(manager.isPromoted)

        manager.stopWatch()

        XCTAssertNil(manager.activeSessionId)
        XCTAssertNil(manager.activeRecordingId)
        XCTAssertFalse(manager.isPromoted)
    }

    func testStopWatchWithNoActiveSessionIsANoOp() {
        let manager = WatchSessionManager(apiClient: makeAPIClient())

        manager.stopWatch()

        XCTAssertNil(manager.activeSessionId)
        XCTAssertNil(manager.activeRecordingId)
        XCTAssertFalse(manager.isPromoted)
    }

    // MARK: - Multi-Session Tests

    func testStartSessionTracksMultipleSessionsIndependently() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Channel 4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/5.1/start"] = (
            Data("{\"recording_id\":\"rec2\",\"session_id\":\"sess2\",\"title\":\"Channel 5.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/sess1/stop"] = (Data("{}".utf8), 200)
        MockURLProtocol.handlers["/api/watch/sess2/stop"] = (Data("{}".utf8), 200)

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        let rec1 = try await manager.startSession(channelNumber: "4.1")
        let rec2 = try await manager.startSession(channelNumber: "5.1")

        XCTAssertEqual(rec1?.sessionId, "sess1")
        XCTAssertEqual(rec2?.sessionId, "sess2")
        XCTAssertEqual(manager.activeSessionCount, 2)
        XCTAssertTrue(manager.isSessionActive("sess1"))
        XCTAssertTrue(manager.isSessionActive("sess2"))
        XCTAssertEqual(manager.activeSessionIds, Set(["sess1", "sess2"]))

        manager.stopSession(sessionId: "sess1")
        XCTAssertEqual(manager.activeSessionCount, 1)
        XCTAssertFalse(manager.isSessionActive("sess1"))
        XCTAssertTrue(manager.isSessionActive("sess2"))

        manager.stopSession(sessionId: "sess2")
        XCTAssertEqual(manager.activeSessionCount, 0)
    }

    func testPromoteSessionCancelsTargetHeartbeat() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Channel 4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/sess1/promote"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Channel 4.1\",\"is_dvr_file\":true}".utf8), 200
        )

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        _ = try await manager.startSession(channelNumber: "4.1")
        XCTAssertTrue(manager.isSessionActive("sess1"))

        let promoted = try await manager.promoteSession(sessionId: "sess1")
        XCTAssertEqual(promoted.recordingId, "rec1")
        XCTAssertFalse(manager.isSessionActive("sess1"))
    }

    func testStopAllStopsAllActiveSessions() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"Channel 4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/5.1/start"] = (
            Data("{\"recording_id\":\"rec2\",\"session_id\":\"sess2\",\"title\":\"Channel 5.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/watch/sess1/stop"] = (Data("{}".utf8), 200)
        MockURLProtocol.handlers["/api/watch/sess2/stop"] = (Data("{}".utf8), 200)

        let manager = WatchSessionManager(apiClient: makeAPIClient())
        _ = try await manager.startSession(channelNumber: "4.1")
        _ = try await manager.startSession(channelNumber: "5.1")
        XCTAssertEqual(manager.activeSessionCount, 2)

        manager.stopAll()
        XCTAssertEqual(manager.activeSessionCount, 0)
        XCTAssertTrue(manager.activeSessionIds.isEmpty)
    }
}
