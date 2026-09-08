import XCTest
@testable import HDHROpenKit

/// Records the last outgoing `URLRequest` (for header/body inspection) and
/// answers with a canned response body. Distinct from the shared
/// `MockURLProtocol`, which only keys off path and can't surface what was
/// actually sent.
private final class AIRequestRecordingURLProtocol: URLProtocol {
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
        AIRequestRecordingURLProtocol.lastRequest = request
        let response = HTTPURLResponse(
            url: request.url!,
            statusCode: AIRequestRecordingURLProtocol.statusCode,
            httpVersion: nil,
            headerFields: nil
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: AIRequestRecordingURLProtocol.responseBody)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}

    static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [AIRequestRecordingURLProtocol.self]
        return URLSession(configuration: config)
    }

    static func reset() {
        lastRequest = nil
        responseBody = Data("{}".utf8)
        statusCode = 200
    }
}

/// `session.bytes(for:)` (used by `sendAIChat`) delivers the request body via
/// `httpBodyStream` rather than `httpBody`, unlike `session.data(for:)` - so
/// body inspection needs to handle both.
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

/// Thread-safe accumulator for events delivered via `sendAIChat`'s
/// synchronous `onEvent` callback.
private final class EventBox: @unchecked Sendable {
    private var events: [AIStreamEvent] = []
    private let lock = NSLock()

    func append(_ event: AIStreamEvent) {
        lock.lock()
        events.append(event)
        lock.unlock()
    }

    var all: [AIStreamEvent] {
        lock.lock()
        defer { lock.unlock() }
        return events
    }
}

final class APIClientAITests: XCTestCase {
    private let baseURL = URL(string: "http://localhost:8000")!

    private func makeMockedAPIClient() -> APIClient {
        APIClient(baseURL: baseURL, session: MockURLProtocol.makeSession())
    }

    private func makeRecordingAPIClient() -> APIClient {
        APIClient(baseURL: baseURL, session: AIRequestRecordingURLProtocol.makeSession())
    }

    private func makeChatRequest() -> AIChatRequest {
        AIChatRequest(messages: [.user("What's on tonight?")])
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        AIRequestRecordingURLProtocol.reset()
        super.tearDown()
    }

    // MARK: - SSE line parsing (via sendAIChat)

    func testSendAIChatParsesDataLinesAndSkipsNonDataAndEmptyAndMalformedLines() async throws {
        let sseLines = [
            "data: {\"type\":\"text\",\"text\":\"Hello\"}",
            "",
            ": this is a comment line and should be ignored",
            "",
            "data: ",
            "",
            "data: {\"type\":\"text\",\"text\":\"World\"}",
            "",
            "data: {this is not valid json}",
            "",
            "data: {\"type\":\"done\"}",
            ""
        ]
        MockURLProtocol.handlers["/api/ai/chat"] = (Data(sseLines.joined(separator: "\n").utf8), 200)
        let client = makeMockedAPIClient()
        let box = EventBox()

        try await client.sendAIChat(request: makeChatRequest()) { event in
            box.append(event)
        }

        let received = box.all
        XCTAssertEqual(received.count, 3, "expected only the 3 well-formed 'data: ' lines to produce events")
        XCTAssertEqual(received.map(\.type), ["text", "text", "done"])
        XCTAssertEqual(received[0].text, "Hello")
        XCTAssertEqual(received[1].text, "World")
    }

    func testSendAIChatWithNoDataLinesProducesNoEvents() async throws {
        MockURLProtocol.handlers["/api/ai/chat"] = (Data("\n\n".utf8), 200)
        let client = makeMockedAPIClient()
        let box = EventBox()

        try await client.sendAIChat(request: makeChatRequest()) { event in
            box.append(event)
        }

        XCTAssertTrue(box.all.isEmpty)
    }

    // MARK: - sendAIChat status code handling

    func testSendAIChatThrowsServerErrorOnErrorStatusCode() async {
        MockURLProtocol.handlers["/api/ai/chat"] = (Data("{}".utf8), 500)
        let client = makeMockedAPIClient()

        do {
            try await client.sendAIChat(request: makeChatRequest()) { _ in
                XCTFail("onEvent should not be called when the initial response is an error status")
            }
            XCTFail("expected sendAIChat to throw")
        } catch let APIError.serverError(statusCode, message) {
            XCTAssertEqual(statusCode, 500)
            XCTAssertEqual(message, "AI chat failed with status code 500")
        } catch {
            XCTFail("expected APIError.serverError, got \(error)")
        }
    }

    func testSendAIChatThrowsServerErrorOn401() async {
        // Unlike the main request() path, sendAIChat's SSE path maps every
        // >=400 status to a flat .serverError rather than distinguishing
        // .unauthorized/.forbidden/etc.
        MockURLProtocol.handlers["/api/ai/chat"] = (Data("{\"detail\":\"nope\"}".utf8), 401)
        let client = makeMockedAPIClient()

        do {
            try await client.sendAIChat(request: makeChatRequest()) { _ in }
            XCTFail("expected sendAIChat to throw")
        } catch let APIError.serverError(statusCode, _) {
            XCTAssertEqual(statusCode, 401)
        } catch {
            XCTFail("expected APIError.serverError, got \(error)")
        }
    }

    // MARK: - sendAIChat headers and body

    func testSendAIChatInjectsHeadersAndEncodesRequestBody() async throws {
        AIRequestRecordingURLProtocol.responseBody = Data("data: {\"type\":\"ping\"}\n\n".utf8)
        let client = makeRecordingAPIClient()
        await client.setBearerToken("tok-ai")
        await client.setDeviceId("device-ai")

        try await client.sendAIChat(request: makeChatRequest()) { _ in }

        let sent = AIRequestRecordingURLProtocol.lastRequest
        XCTAssertEqual(sent?.httpMethod, "POST")
        XCTAssertEqual(sent?.value(forHTTPHeaderField: "Authorization"), "Bearer tok-ai")
        XCTAssertEqual(sent?.value(forHTTPHeaderField: "X-Device-Id"), "device-ai")
        XCTAssertEqual(sent?.value(forHTTPHeaderField: "Content-Type"), "application/json")
        XCTAssertEqual(sent?.url?.path, "/api/ai/chat")

        guard let body = bodyData(from: sent) else {
            XCTFail("expected a body on the AI chat request")
            return
        }
        let json = try JSONSerialization.jsonObject(with: body) as? [String: Any]
        let messages = json?["messages"] as? [[String: Any]]
        XCTAssertEqual(messages?.first?["role"] as? String, "user")
    }

    // MARK: - Thin wrapper methods

    func testTestAIConnectionDecodesResult() async throws {
        MockURLProtocol.handlers["/api/ai/test-connection"] = (Data("{\"ok\": true, \"detail\": \"reachable\", \"error\": null}".utf8), 200)
        let client = makeMockedAPIClient()

        let result = try await client.testAIConnection()

        XCTAssertTrue(result.ok)
        XCTAssertEqual(result.detail, "reachable")
        XCTAssertNil(result.error)
    }

    func testTestAIConnectionSurfacesFailure() async throws {
        MockURLProtocol.handlers["/api/ai/test-connection"] = (Data("{\"ok\": false, \"detail\": null, \"error\": \"timeout\"}".utf8), 200)
        let client = makeMockedAPIClient()

        let result = try await client.testAIConnection()

        XCTAssertFalse(result.ok)
        XCTAssertEqual(result.error, "timeout")
    }

    func testListAIModelsDecodesModelList() async throws {
        MockURLProtocol.handlers["/api/ai/list-models"] = (Data("{\"ok\": true, \"models\": [\"gpt-4\", \"gpt-4o-mini\"], \"error\": null}".utf8), 200)
        let client = makeMockedAPIClient()

        let result = try await client.listAIModels()

        XCTAssertEqual(result.models, ["gpt-4", "gpt-4o-mini"])
    }

    func testConfirmAIActionDecodesResult() async throws {
        MockURLProtocol.handlers["/api/ai/actions/act1/confirm"] = (Data("{\"result\": \"ok\"}".utf8), 200)
        let client = makeMockedAPIClient()

        let result = try await client.confirmAIAction(actionId: "act1")

        XCTAssertEqual(result.result?.value as? String, "ok")
    }

    func testCancelAIActionDecodesResult() async throws {
        MockURLProtocol.handlers["/api/ai/actions/act1/cancel"] = (Data("{\"ok\": true}".utf8), 200)
        let client = makeMockedAPIClient()

        let result = try await client.cancelAIAction(actionId: "act1")

        XCTAssertTrue(result.ok)
    }

    func testConfirmAIActionThrowsNotFoundOn404() async {
        MockURLProtocol.handlers["/api/ai/actions/missing/confirm"] = (Data("{\"detail\":\"unknown action\"}".utf8), 404)
        let client = makeMockedAPIClient()

        do {
            _ = try await client.confirmAIAction(actionId: "missing")
            XCTFail("expected notFound error")
        } catch let APIError.notFound(message) {
            XCTAssertEqual(message, "unknown action")
        } catch {
            XCTFail("expected APIError.notFound, got \(error)")
        }
    }
}
