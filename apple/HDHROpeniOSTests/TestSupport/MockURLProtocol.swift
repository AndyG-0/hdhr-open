import Foundation

/// Intercepts requests by exact path suffix, so tests can stub specific
/// endpoints without spinning up a real server. Unregistered paths get a
/// 404. Mirrors `HDHROpenKitTests`'s `MockURLProtocol` - duplicated here
/// rather than shared, since app-target test bundles and the Kit package's
/// test target are separate modules.
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
