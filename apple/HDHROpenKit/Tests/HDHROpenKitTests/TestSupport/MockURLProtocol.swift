import Foundation

/// Intercepts requests by exact path suffix, so tests can stub specific
/// endpoints without spinning up a real server. Unregistered paths get a
/// 404 - fire-and-forget calls made by production code are expected to hit
/// this and fail silently via `try?` where applicable, which is fine for
/// tests exercising those paths.
final class MockURLProtocol: URLProtocol {
    static var handlers: [String: (Data, Int)] = [:]

    override class func canInit(with _: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        let path = request.url?.path ?? ""
        let (data, status) = MockURLProtocol.handlers[path] ?? (Data("{}".utf8), 404)
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
