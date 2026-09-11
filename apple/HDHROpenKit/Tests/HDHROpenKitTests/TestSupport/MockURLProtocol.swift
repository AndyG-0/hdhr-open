import Foundation

/// Intercepts requests by exact path suffix, so tests can stub specific
/// endpoints without spinning up a real server. Unregistered paths get a
/// 404 - fire-and-forget calls made by production code are expected to hit
/// this and fail silently via `try?` where applicable, which is fine for
/// tests exercising those paths.
final class MockURLProtocol: URLProtocol {
    static var handlers: [String: (Data, Int)] = [:]

    /// Every request path seen, in arrival order - lets tests assert a
    /// teardown call (e.g. an HLS/watch-session stop) actually happened,
    /// rather than only inferring it from local view-model state.
    private static let logLock = NSLock()
    private static var _requestLog: [String] = []
    static var requestLog: [String] {
        logLock.lock(); defer { logLock.unlock() }
        return _requestLog
    }

    static func resetLog() {
        logLock.lock(); defer { logLock.unlock() }
        _requestLog = []
    }

    /// Paths whose response is held back (on the background thread
    /// `startLoading` runs on) until `releaseGate(for:)` signals it - lets
    /// tests deterministically land a view-model mutation while a specific
    /// network call is still in flight, instead of racing on timing.
    private static let gateLock = NSLock()
    private static var gateSemaphores: [String: DispatchSemaphore] = [:]

    static func addGate(for path: String) {
        gateLock.lock(); defer { gateLock.unlock() }
        gateSemaphores[path] = DispatchSemaphore(value: 0)
    }

    static func releaseGate(for path: String) {
        gateLock.lock()
        let sem = gateSemaphores.removeValue(forKey: path)
        gateLock.unlock()
        sem?.signal()
    }

    static func resetGates() {
        gateLock.lock(); defer { gateLock.unlock() }
        gateSemaphores = [:]
    }

    /// Suspends until `path` has actually reached `startLoading` (i.e. is
    /// logged in `requestLog`), instead of guessing a fixed sleep is "long
    /// enough" for a concurrently-started task to get there. Use this before
    /// firing a second, un-gated call whose ordering relative to the first
    /// depends on the first having already reached its gate - a blind sleep
    /// that's too short lets the second call race ahead and breaks that
    /// ordering under CI contention.
    static func waitUntilLogged(_ path: String, timeoutSeconds: TimeInterval = 2.0) async throws {
        let deadline = Date().addingTimeInterval(timeoutSeconds)
        while !requestLog.contains(path) {
            if Date() >= deadline {
                throw NSError(
                    domain: "MockURLProtocol", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "Timed out waiting for \(path) to be logged"]
                )
            }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
    }

    /// Per-path FIFO queues, consumed one response per request before
    /// falling back to `handlers[path]`. Needed for endpoints that don't
    /// vary by path per logical resource (e.g. `/api/dvr/recording-stream-hls`
    /// is one fixed path for every session) - registering plain `handlers`
    /// entries for two different sessions on the same path just has the
    /// second overwrite the first, so a test juggling concurrent negotiations
    /// against that path needs each request to get its own queued response,
    /// in the order the requests actually arrive.
    private static let queueLock = NSLock()
    private static var queuedResponses: [String: [(Data, Int)]] = [:]

    static func enqueueResponse(_ data: Data, status: Int, for path: String) {
        queueLock.lock(); defer { queueLock.unlock() }
        queuedResponses[path, default: []].append((data, status))
    }

    static func resetQueues() {
        queueLock.lock(); defer { queueLock.unlock() }
        queuedResponses = [:]
    }

    fileprivate static func dequeueOrHandler(for path: String) -> (Data, Int) {
        queueLock.lock()
        if var queue = queuedResponses[path], !queue.isEmpty {
            let next = queue.removeFirst()
            queuedResponses[path] = queue
            queueLock.unlock()
            return next
        }
        queueLock.unlock()
        return handlers[path] ?? (Data("{}".utf8), 404)
    }

    override class func canInit(with _: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        let path = request.url?.path ?? ""

        MockURLProtocol.logLock.lock()
        MockURLProtocol._requestLog.append(path)
        MockURLProtocol.logLock.unlock()

        MockURLProtocol.gateLock.lock()
        let sem = MockURLProtocol.gateSemaphores[path]
        MockURLProtocol.gateLock.unlock()

        // `startLoading` runs on the session's shared (serial) loading queue,
        // not a per-request thread - blocking it here with `sem.wait()` would
        // starve every other in-flight request on the same session, including
        // the unrelated one a test needs to complete before it can release
        // this gate, deadlocking the whole session. Waiting on a detached
        // global-queue thread instead keeps that queue free.
        if let sem {
            DispatchQueue.global().async {
                sem.wait()
                self.respond(path: path)
            }
        } else {
            respond(path: path)
        }
    }

    private func respond(path: String) {
        let (data, status) = MockURLProtocol.dequeueOrHandler(for: path)
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

extension MockURLProtocol {
    /// A `URLSession` configured to route every request through
    /// `MockURLProtocol.handlers` instead of the network.
    static func makeSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        return URLSession(configuration: config)
    }
}
