import XCTest
@testable import HDHROpenKit

/// A `URLProtocol` that records the last `URLRequest` it saw (headers, URL,
/// and body included) and answers with a canned response. Distinct from the
/// shared `MockURLProtocol`, which only keys off request path and can't
/// surface what was actually sent - this one is for tests that need to
/// assert on outgoing headers/query strings/bodies.
private final class RequestRecordingURLProtocol: URLProtocol {
    static var lastRequest: URLRequest?
    static var responseBody = Data("{}".utf8)
    static var statusCode = 200

    override class func canInit(with _: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        RequestRecordingURLProtocol.lastRequest = request
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: RequestRecordingURLProtocol.statusCode,
            httpVersion: nil,
            headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: RequestRecordingURLProtocol.responseBody)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [RequestRecordingURLProtocol.self]
        return URLSession(configuration: config)
    }

    static func reset() {
        lastRequest = nil
        responseBody = Data("{}".utf8)
        statusCode = 200
    }
}

private func bodyData(from request: URLRequest?) -> Data? {
    guard let request else { return nil }
    if let body = request.httpBody {
        return body
    }
    guard let stream = request.httpBodyStream else { return nil }
    stream.open()
    defer { stream.close() }
    var data = Data()
    let bufferSize = 4096
    var buffer = [UInt8](repeating: 0, count: bufferSize)
    while stream.hasBytesAvailable {
        let read = stream.read(&buffer, maxLength: bufferSize)
        if read > 0 {
            data.append(buffer, count: read)
        } else {
            break
        }
    }
    return data
}

final class APIClientTests: XCTestCase {
    private let baseURL = URL(string: "http://localhost:8000")!

    private func makeMockedAPIClient() -> APIClient {
        APIClient(baseURL: baseURL, session: MockURLProtocol.makeSession())
    }

    private func makeRecordingAPIClient() -> APIClient {
        APIClient(baseURL: baseURL, session: RequestRecordingURLProtocol.makeSession())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        RequestRecordingURLProtocol.reset()
        super.tearDown()
    }

    // MARK: - Basic property accessors

    func testInitStoresBaseURLAndSetBaseURLUpdatesIt() async throws {
        let client = APIClient(baseURL: baseURL, session: MockURLProtocol.makeSession())
        let initial = await client.baseURL
        XCTAssertEqual(initial, baseURL)

        let newURL = try XCTUnwrap(URL(string: "https://example.org"))
        await client.setBaseURL(newURL)
        let updated = await client.baseURL
        XCTAssertEqual(updated, newURL)
    }

    func testBearerTokenGetterSetterAndClearing() async {
        let client = makeMockedAPIClient()
        let initial = await client.currentBearerToken()
        XCTAssertNil(initial)

        await client.setBearerToken("tok-123")
        let set = await client.currentBearerToken()
        XCTAssertEqual(set, "tok-123")

        await client.setBearerToken(nil)
        let cleared = await client.currentBearerToken()
        XCTAssertNil(cleared)
    }

    func testDeviceIdGetterAndSetter() async {
        let client = makeMockedAPIClient()
        let initial = await client.currentDeviceId()
        XCTAssertNil(initial)

        await client.setDeviceId("device-abc")
        let set = await client.currentDeviceId()
        XCTAssertEqual(set, "device-abc")
    }

    // MARK: - Header injection

    func testRequestInjectsAuthorizationAndDeviceIdHeaders() async throws {
        let client = makeRecordingAPIClient()
        await client.setBearerToken("secret-token")
        await client.setDeviceId("device-xyz")

        _ = try await client.requestRaw(path: "/api/tuner/status")

        let sent = RequestRecordingURLProtocol.lastRequest
        XCTAssertEqual(sent?.value(forHTTPHeaderField: "Authorization"), "Bearer secret-token")
        XCTAssertEqual(sent?.value(forHTTPHeaderField: "X-Device-Id"), "device-xyz")
    }

    func testRequestOmitsAuthorizationHeaderWhenNoTokenSet() async throws {
        let client = makeRecordingAPIClient()

        _ = try await client.requestRaw(path: "/api/tuner/status")

        let sent = RequestRecordingURLProtocol.lastRequest
        XCTAssertNil(sent?.value(forHTTPHeaderField: "Authorization"))
        XCTAssertNil(sent?.value(forHTTPHeaderField: "X-Device-Id"))
    }

    func testRequestMergesCustomHeadersAndSetsContentTypeWhenBodyPresent() async throws {
        let client = makeRecordingAPIClient()
        struct Body: Encodable { let hello: String }

        _ = try await client.requestRaw(
            path: "/api/settings",
            method: "POST",
            body: Body(hello: "world"),
            headers: ["X-Custom": "custom-value"]
        )

        let sent = RequestRecordingURLProtocol.lastRequest
        XCTAssertEqual(sent?.value(forHTTPHeaderField: "X-Custom"), "custom-value")
        XCTAssertEqual(sent?.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(sent?.httpMethod, "POST")
        let body = bodyData(from: sent)
        XCTAssertNotNil(body)
        let decodedBody = try XCTUnwrap(body)
        let json = try JSONSerialization.jsonObject(with: decodedBody) as? [String: String]
        XCTAssertEqual(json?["hello"], "world")
    }

    func testRequestHasNoContentTypeHeaderWhenNoBody() async throws {
        let client = makeRecordingAPIClient()

        _ = try await client.requestRaw(path: "/api/tuner/status")

        let sent = RequestRecordingURLProtocol.lastRequest
        XCTAssertNil(sent?.value(forHTTPHeaderField: "Content-Type"))
    }

    // MARK: - requestRaw / request success paths

    func testRequestRawReturnsRawBodyOnSuccess() async throws {
        MockURLProtocol.handlers["/api/settings"] = (Data("{\"timezone\":\"UTC\"}".utf8), 200)
        let client = makeMockedAPIClient()

        let data = try await client.requestRaw(path: "/api/settings")

        let json = try JSONSerialization.jsonObject(with: data) as? [String: String]
        XCTAssertEqual(json?["timezone"], "UTC")
    }

    func testRequestDecodesJSONBodyOnSuccess() async throws {
        let body = """
        {"channels": [{"channel_number": "4.1", "name": "WCBS-DT", "is_hd": true, "is_drm": false, "stream_url": "http://x/stream"}], "guide_available": true}
        """
        MockURLProtocol.handlers["/api/guide/channels"] = (Data(body.utf8), 200)
        let client = makeMockedAPIClient()

        let response = try await client.getChannels()

        XCTAssertTrue(response.guideAvailable)
        XCTAssertEqual(response.channels.count, 1)
        XCTAssertEqual(response.channels.first?.channelNumber, "4.1")
        XCTAssertEqual(response.channels.first?.name, "WCBS-DT")
    }

    func testRequestThrowsDecodingErrorOnMalformedJSON() async {
        MockURLProtocol.handlers["/api/guide/channels"] = (Data("not json at all".utf8), 200)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getChannels()
            XCTFail("expected decodingError to be thrown")
        } catch let APIError.decodingError(message) {
            XCTAssertFalse(message.isEmpty)
        } catch {
            XCTFail("expected APIError.decodingError, got \(error)")
        }
    }

    // MARK: - Status code -> APIError mapping

    func testStatusCode401ThrowsUnauthorizedWithDetailFromBody() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("{\"detail\":\"bad token\"}".utf8), 401)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected unauthorized error")
        } catch let APIError.unauthorized(message) {
            XCTAssertEqual(message, "bad token")
        } catch {
            XCTFail("expected APIError.unauthorized, got \(error)")
        }
    }

    func testStatusCode403ThrowsForbidden() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("{}".utf8), 403)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected forbidden error")
        } catch APIError.forbidden {
            // expected
        } catch {
            XCTFail("expected APIError.forbidden, got \(error)")
        }
    }

    func testStatusCode404ThrowsNotFoundWithDetailFromBody() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("{\"detail\":\"no such tuner\"}".utf8), 404)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected notFound error")
        } catch let APIError.notFound(message) {
            XCTAssertEqual(message, "no such tuner")
        } catch {
            XCTFail("expected APIError.notFound, got \(error)")
        }
    }

    func testStatusCode429ThrowsLockedOutWithDetailFromBody() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("{\"detail\":\"too many attempts\"}".utf8), 429)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected lockedOut error")
        } catch let APIError.lockedOut(message) {
            XCTAssertEqual(message, "too many attempts")
        } catch {
            XCTFail("expected APIError.lockedOut, got \(error)")
        }
    }

    func testStatusCode500ThrowsServerErrorWithDefaultMessageWhenNoDetailKey() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("{\"unrelated\":\"field\"}".utf8), 500)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected serverError")
        } catch let APIError.serverError(statusCode, message) {
            XCTAssertEqual(statusCode, 500)
            XCTAssertEqual(message, "Request failed with status code 500")
        } catch {
            XCTFail("expected APIError.serverError, got \(error)")
        }
    }

    func testStatusCode500ParsesNestedDetailObjectMessage() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("{\"detail\":{\"message\":\"tuner offline\"}}".utf8), 500)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected serverError")
        } catch let APIError.serverError(statusCode, message) {
            XCTAssertEqual(statusCode, 500)
            XCTAssertEqual(message, "tuner offline")
        } catch {
            XCTFail("expected APIError.serverError, got \(error)")
        }
    }

    func testStatusCode500ParsesErrorKey() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("{\"error\":\"something broke\"}".utf8), 500)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected serverError")
        } catch let APIError.serverError(statusCode, message) {
            XCTAssertEqual(statusCode, 500)
            XCTAssertEqual(message, "something broke")
        } catch {
            XCTFail("expected APIError.serverError, got \(error)")
        }
    }

    func testStatusCode500FallsBackToDefaultMessageOnNonJSONBody() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("not json".utf8), 500)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected serverError")
        } catch let APIError.serverError(statusCode, message) {
            XCTAssertEqual(statusCode, 500)
            XCTAssertEqual(message, "Request failed with status code 500")
        } catch {
            XCTFail("expected APIError.serverError, got \(error)")
        }
    }

    func testOtherErrorStatusCodeFallsThroughToServerError() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("{\"detail\":\"teapot\"}".utf8), 418)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.getTunerStatus()
            XCTFail("expected serverError")
        } catch let APIError.serverError(statusCode, message) {
            XCTAssertEqual(statusCode, 418)
            XCTAssertEqual(message, "teapot")
        } catch {
            XCTFail("expected APIError.serverError, got \(error)")
        }
    }

    // MARK: - Query-string building

    func testGetGuideBuildsQueryStringWithStartAndEnd() async throws {
        RequestRecordingURLProtocol.responseBody = Data("[]".utf8)
        let client = makeRecordingAPIClient()

        _ = try await client.getGuide(start: 1000, end: 2000)

        let sentURL = RequestRecordingURLProtocol.lastRequest?.url
        XCTAssertEqual(sentURL?.path, "/api/guide")
        let query = sentURL?.query ?? ""
        XCTAssertTrue(query.contains("start=1000.0"))
        XCTAssertTrue(query.contains("end=2000.0"))
    }

    func testGetGuideOmitsQueryStringWhenNoWindowGiven() async throws {
        RequestRecordingURLProtocol.responseBody = Data("[]".utf8)
        let client = makeRecordingAPIClient()

        _ = try await client.getGuide()

        let sentURL = RequestRecordingURLProtocol.lastRequest?.url
        XCTAssertEqual(sentURL?.path, "/api/guide")
        XCTAssertNil(sentURL?.query)
    }

    func testGetRecordingDetailBuildsExpectedQueryString() async throws {
        RequestRecordingURLProtocol.responseBody = Data("""
        {"is_in_progress": false, "audio": [], "has_captions": false, "transcode": {"transcoding": false, "hardware": false}}
        """.utf8)
        let client = makeRecordingAPIClient()

        _ = try await client.getRecordingDetail(url: "http://tuner/rec.ts", recordingId: "rec1", start: 5, recordEnd: 10)

        let sentURL = RequestRecordingURLProtocol.lastRequest?.url
        XCTAssertEqual(sentURL?.path, "/api/dvr/recording-detail")
        let query = sentURL?.query ?? ""
        XCTAssertTrue(query.contains("url=http://tuner/rec.ts"))
        XCTAssertTrue(query.contains("recording_id=rec1"))
        XCTAssertTrue(query.contains("start=5.0"))
        XCTAssertTrue(query.contains("record_end=10.0"))
    }

    func testGetRecordingDetailPercentEncodesSpacesInUrlQueryParam() async throws {
        RequestRecordingURLProtocol.responseBody = Data("""
        {"is_in_progress": false, "audio": [], "has_captions": false, "transcode": {"transcoding": false, "hardware": false}}
        """.utf8)
        let client = makeRecordingAPIClient()

        _ = try await client.getRecordingDetail(url: "http://tuner/my recording.ts", recordingId: "rec1")

        let sentURL = RequestRecordingURLProtocol.lastRequest?.url
        let query = sentURL?.query ?? ""
        // Spaces (unlike '/', '?', '&', which urlQueryAllowed treats as legal
        // query characters) are not in .urlQueryAllowed and must be escaped.
        XCTAssertTrue(query.contains("url=http://tuner/my%20recording.ts"))
    }

    // MARK: - Guide / DVR wrapper spot checks

    func testRefreshGuidePostsAndSucceedsWithNoBody() async throws {
        MockURLProtocol.handlers["/api/guide/refresh"] = (Data("{}".utf8), 200)
        let client = makeMockedAPIClient()

        try await client.refreshGuide()
        // no throw == success
    }

    func testGetDvrInfoDecodes() async throws {
        let body = """
        {"friendly_name": "Server", "version": "1.0", "free_space_bytes": 123456, "is_builtin": true, "provider": "hdhomerun"}
        """
        MockURLProtocol.handlers["/api/dvr/info"] = (Data(body.utf8), 200)
        let client = makeMockedAPIClient()

        let info = try await client.getDvrInfo()

        XCTAssertEqual(info.friendlyName, "Server")
        XCTAssertEqual(info.freeSpaceBytes, 123_456)
        XCTAssertTrue(info.isBuiltin ?? false)
    }

    func testListRecordingsDecodesArray() async throws {
        let body = """
        [{"title": "Show A", "recording_id": "rec1"}, {"title": "Show B", "recording_id": "rec2"}]
        """
        MockURLProtocol.handlers["/api/dvr/recordings"] = (Data(body.utf8), 200)
        let client = makeMockedAPIClient()

        let recordings = try await client.listRecordings()

        XCTAssertEqual(recordings.count, 2)
        XCTAssertEqual(recordings.map(\.recordingId), ["rec1", "rec2"])
    }

    func testDeleteRecordingSucceeds() async throws {
        MockURLProtocol.handlers["/api/dvr/recordings/rec1"] = (Data("{}".utf8), 200)
        let client = makeMockedAPIClient()

        try await client.deleteRecording(id: "rec1")
        // no throw == success
    }

    func testRecordingRuleAddDecodesUpdatedList() async throws {
        let body = """
        [{"RecordingRuleID": "rule1", "SeriesID": "series1", "Title": "Show A"}]
        """
        MockURLProtocol.handlers["/api/dvr/recording-rules"] = (Data(body.utf8), 200)
        let client = makeMockedAPIClient()

        let rules = try await client.addRecordingRule(payload: AddRecordingRulePayload(seriesId: "series1"))

        XCTAssertEqual(rules.count, 1)
        XCTAssertEqual(rules.first?.recordingRuleId, "rule1")
        XCTAssertTrue(rules.first?.isSeriesRule ?? false)
    }

    func testRecordingRuleUpdateDecodesUpdatedList() async throws {
        let body = """
        [{"RecordingRuleID": "rule-upd", "SeriesID": "series1", "Title": "Updated"}]
        """
        MockURLProtocol.handlers["/api/dvr/recording-rules/rule-upd"] = (Data(body.utf8), 200)
        let client = makeMockedAPIClient()

        let rules = try await client.updateRecordingRule(id: "rule-upd", payload: AddRecordingRulePayload(seriesId: "series1"))

        XCTAssertEqual(rules.first?.title, "Updated")
    }

    func testRecordingRuleDeleteDecodesUpdatedList() async throws {
        MockURLProtocol.handlers["/api/dvr/recording-rules/rule-del"] = (Data("[]".utf8), 200)
        let client = makeMockedAPIClient()

        let rules = try await client.deleteRecordingRule(id: "rule-del")

        XCTAssertTrue(rules.isEmpty)
    }

    // MARK: - Watch session branching

    func testStartWatchReturnsNilWhenResponseHasNoRecordingOrSessionId() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data("{\"title\": \"\"}".utf8), 200)
        let client = makeMockedAPIClient()

        let result = try await client.startWatch(channelNumber: "4.1")

        XCTAssertNil(result)
    }

    func testStartWatchReturnsRecordingWhenSessionIdPresent() async throws {
        let body = """
        {"title": "Live", "session_id": "sess-1", "playlist_url": "/api/hls/sess-1/playlist.m3u8"}
        """
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (Data(body.utf8), 200)
        let client = makeMockedAPIClient()

        let result = try await client.startWatch(channelNumber: "4.1")

        XCTAssertEqual(result?.sessionId, "sess-1")
    }

    func testHeartbeatAndStopWatchSucceed() async throws {
        MockURLProtocol.handlers["/api/watch/sess-1/heartbeat"] = (Data("{}".utf8), 200)
        MockURLProtocol.handlers["/api/watch/sess-1/stop"] = (Data("{}".utf8), 200)
        let client = makeMockedAPIClient()

        try await client.heartbeatWatch(sessionId: "sess-1")
        try await client.stopWatch(sessionId: "sess-1")
        // no throw == success
    }

    // MARK: - HLS session wrappers

    func testCreateRecordingHLSSessionEncodesBodyAndDecodesResponse() async throws {
        RequestRecordingURLProtocol.responseBody = Data("""
        {"session_id": "sess-9", "playlist_url": "/api/hls/sess-9/playlist.m3u8"}
        """.utf8)
        let client = makeRecordingAPIClient()

        let response = try await client.createRecordingHLSSession(url: "http://tuner/rec.ts", recordingId: "rec1", start: 5, audioIndex: 2)

        XCTAssertEqual(response.sessionId, "sess-9")
        XCTAssertEqual(response.playlistUrl, "/api/hls/sess-9/playlist.m3u8")

        let sentBody = try XCTUnwrap(bodyData(from: RequestRecordingURLProtocol.lastRequest))
        let json = try JSONSerialization.jsonObject(with: sentBody) as? [String: Any]
        XCTAssertEqual(json?["url"] as? String, "http://tuner/rec.ts")
        XCTAssertEqual(json?["recording_id"] as? String, "rec1")
        XCTAssertEqual(json?["audio_index"] as? Int, 2)
    }

    func testStopHLSSessionSucceeds() async throws {
        MockURLProtocol.handlers["/api/hls/sess-9/stop"] = (Data("{}".utf8), 200)
        let client = makeMockedAPIClient()

        try await client.stopHLSSession(sessionId: "sess-9")
        // no throw == success
    }

    // MARK: - Tuner / device wrappers

    func testGetTunerStatusDecodesArray() async throws {
        let body = """
        [{"index": 0, "in_use": true, "channel_number": "4.1"}]
        """
        MockURLProtocol.handlers["/api/tuner/status"] = (Data(body.utf8), 200)
        let client = makeMockedAPIClient()

        let tuners = try await client.getTunerStatus()

        XCTAssertEqual(tuners.count, 1)
        XCTAssertTrue(tuners.first?.inUse ?? false)
    }

    func testRegisterDeviceStoresReturnedIdAsSideEffect() async throws {
        MockURLProtocol.handlers["/api/devices/register"] = (Data("{\"id\": \"dev-1\", \"name\": \"iPhone\", \"is_new\": true}".utf8), 200)
        let client = makeMockedAPIClient()

        let result = try await client.registerDevice()

        XCTAssertEqual(result.id, "dev-1")
        let storedDeviceId = await client.currentDeviceId()
        XCTAssertEqual(storedDeviceId, "dev-1")
    }

    // MARK: - Auth wrappers

    func testLoginPostsBodyAndDecodesCurrentUser() async throws {
        RequestRecordingURLProtocol.responseBody = Data("""
        {"id": "user1", "name": "Andy", "role": "admin", "token": "tok-1"}
        """.utf8)
        let client = makeRecordingAPIClient()

        let user = try await client.login(userId: "user1", pin: "1234", tokenName: "iphone")

        XCTAssertEqual(user.id, "user1")
        XCTAssertTrue(user.isAdmin)

        let sentBody = try XCTUnwrap(bodyData(from: RequestRecordingURLProtocol.lastRequest))
        let json = try JSONSerialization.jsonObject(with: sentBody) as? [String: Any]
        XCTAssertEqual(json?["pin"] as? String, "1234")
        XCTAssertEqual(json?["token_name"] as? String, "iphone")
    }

    // MARK: - Network integration wrapper (PATCH with AnyCodable body)

    func testUpdateNetworkIntegrationSendsPatchWithSettingsBody() async throws {
        RequestRecordingURLProtocol.responseBody = Data("""
        {"id": "ni1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {"host": "1.2.3.4"}}
        """.utf8)
        let client = makeRecordingAPIClient()

        let integration = try await client.updateNetworkIntegration(type: "hdhomerun", settings: ["host": AnyCodable("1.2.3.4")])

        XCTAssertEqual(integration.name, "HDHomeRun")
        XCTAssertEqual(RequestRecordingURLProtocol.lastRequest?.httpMethod, "PATCH")

        let sentBody = try XCTUnwrap(bodyData(from: RequestRecordingURLProtocol.lastRequest))
        let json = try JSONSerialization.jsonObject(with: sentBody) as? [String: Any]
        XCTAssertEqual(json?["host"] as? String, "1.2.3.4")
    }

    // MARK: - SyncPlay wrappers

    func testCreateSyncPlayRoomDecodesNestedRoomAndPostsUserName() async throws {
        RequestRecordingURLProtocol.responseBody = Data("""
        {"room": {"room_code": "ABCD", "host_session_id": "host1", "created_at": 100}, "ws_url": "/api/syncplay/ws/ABCD"}
        """.utf8)
        let client = makeRecordingAPIClient()

        let response = try await client.createSyncPlayRoom(userName: "Andy")

        XCTAssertEqual(response.room.roomCode, "ABCD")
        XCTAssertEqual(response.wsUrl, "/api/syncplay/ws/ABCD")

        let sentBody = try XCTUnwrap(bodyData(from: RequestRecordingURLProtocol.lastRequest))
        let json = try JSONSerialization.jsonObject(with: sentBody) as? [String: Any]
        XCTAssertEqual(json?["user_name"] as? String, "Andy")
    }

    func testGetSyncPlayRoomDecodes() async throws {
        let body = """
        {"room_code": "WXYZ", "host_session_id": "host2", "created_at": 200}
        """
        MockURLProtocol.handlers["/api/syncplay/rooms/WXYZ"] = (Data(body.utf8), 200)
        let client = makeMockedAPIClient()

        let room = try await client.getSyncPlayRoom(code: "WXYZ")

        XCTAssertEqual(room.roomCode, "WXYZ")
    }

    // MARK: - syncPlayWsUrl scheme rewriting

    func testSyncPlayWsUrlConvertsHttpsBaseToWss() async throws {
        let client = try APIClient(baseURL: XCTUnwrap(URL(string: "https://example.org")), session: MockURLProtocol.makeSession())

        let url = await client.syncPlayWsUrl(roomCode: "ABCD", userName: "Andy")

        XCTAssertEqual(url?.scheme, "wss")
        XCTAssertEqual(url?.path, "/api/syncplay/ws/ABCD")
        XCTAssertTrue(url?.query?.contains("user_name=Andy") ?? false)
    }

    func testSyncPlayWsUrlConvertsHttpBaseToWs() async throws {
        let client = try APIClient(baseURL: XCTUnwrap(URL(string: "http://localhost:8000")), session: MockURLProtocol.makeSession())

        let url = await client.syncPlayWsUrl(roomCode: "ABCD")

        XCTAssertEqual(url?.scheme, "ws")
        XCTAssertEqual(url?.path, "/api/syncplay/ws/ABCD")
    }

    func testSyncPlayWsUrlIncludesBearerTokenInQuery() async throws {
        let client = try APIClient(baseURL: XCTUnwrap(URL(string: "https://example.org")), session: MockURLProtocol.makeSession())
        await client.setBearerToken("tok-77")

        let url = await client.syncPlayWsUrl(roomCode: "ABCD")

        XCTAssertTrue(url?.query?.contains("token=tok-77") ?? false)
    }
}
