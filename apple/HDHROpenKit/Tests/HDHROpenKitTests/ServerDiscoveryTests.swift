import XCTest
@testable import HDHROpenKit

/// `ServerDiscovery` persists `serverURLString` to `UserDefaults.standard`
/// under this key (mirrored from the private constant in
/// ServerDiscovery.swift). Tests save/restore whatever was there before so
/// they never leak state into other tests or the developer's machine.
private let serverURLDefaultsKey = "org.hdhropen.client.serverURL"

@MainActor
final class ServerDiscoveryTests: XCTestCase {
    private var savedDefaultsValue: String?

    override func setUp() {
        super.setUp()
        savedDefaultsValue = UserDefaults.standard.string(forKey: serverURLDefaultsKey)
        UserDefaults.standard.removeObject(forKey: serverURLDefaultsKey)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        if let savedDefaultsValue {
            UserDefaults.standard.set(savedDefaultsValue, forKey: serverURLDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: serverURLDefaultsKey)
        }
        super.tearDown()
    }

    private func makeDiscovery(defaultURL: String = "http://127.0.0.1:8000") -> ServerDiscovery {
        ServerDiscovery(defaultURL: defaultURL, session: MockURLProtocol.makeSession())
    }

    // MARK: - Init / persistence

    func testInitUsesDefaultURLWhenNothingStored() {
        let discovery = makeDiscovery(defaultURL: "http://myserver:8000")

        XCTAssertEqual(discovery.serverURLString, "http://myserver:8000")
        XCTAssertEqual(discovery.currentServerURL, URL(string: "http://myserver:8000"))
    }

    func testInitUsesStoredValueWhenPresent() {
        UserDefaults.standard.set("http://stored-server:9000", forKey: serverURLDefaultsKey)

        let discovery = makeDiscovery(defaultURL: "http://default:8000")

        XCTAssertEqual(discovery.serverURLString, "http://stored-server:9000")
    }

    func testSettingServerURLStringPersistsToUserDefaults() {
        let discovery = makeDiscovery()

        discovery.serverURLString = "http://new-server:1234"

        XCTAssertEqual(UserDefaults.standard.string(forKey: serverURLDefaultsKey), "http://new-server:1234")
    }

    func testCurrentServerURLReturnsNilForInvalidString() {
        let discovery = makeDiscovery()

        discovery.serverURLString = "http://bad url with spaces"

        XCTAssertNil(discovery.currentServerURL)
    }

    func testCurrentServerURLReturnsParsedURLForValidString() {
        let discovery = makeDiscovery()

        discovery.serverURLString = "http://192.168.1.50:8000"

        XCTAssertEqual(discovery.currentServerURL, URL(string: "http://192.168.1.50:8000"))
    }

    // MARK: - testConnection

    func testConnectionReturnsTrueOn2xxResponse() async throws {
        MockURLProtocol.handlers["/api/setup/status"] = (Data("{}".utf8), 200)
        let discovery = makeDiscovery()

        let result = try await discovery.testConnection(to: XCTUnwrap(URL(string: "http://localhost:8000")))

        XCTAssertTrue(result)
    }

    func testConnectionReturnsFalseOnServerErrorResponse() async throws {
        MockURLProtocol.handlers["/api/setup/status"] = (Data("{\"detail\":\"nope\"}".utf8), 500)
        let discovery = makeDiscovery()

        let result = try await discovery.testConnection(to: XCTUnwrap(URL(string: "http://localhost:8000")))

        XCTAssertFalse(result)
    }

    func testConnectionReturnsFalseWhenEndpointIsUnhandled() async throws {
        // No handler registered for /api/setup/status -> MockURLProtocol
        // falls back to a 404, exercising the same false-result path a
        // real network/server error would take.
        let discovery = makeDiscovery()

        let result = try await discovery.testConnection(to: XCTUnwrap(URL(string: "http://unreachable-host:8000")))

        XCTAssertFalse(result)
    }

    // MARK: - Bonjour discovery smoke test

    func testStartAndStopDiscoveryDoesNotCrashAndTogglesIsSearching() {
        let discovery = makeDiscovery()

        XCTAssertFalse(discovery.isSearching)

        discovery.startDiscovery()
        XCTAssertTrue(discovery.isSearching)

        // Calling start again while already searching should be a no-op
        // guarded by `isSearching`, not a crash or double-start.
        discovery.startDiscovery()
        XCTAssertTrue(discovery.isSearching)

        discovery.stopDiscovery()
        XCTAssertFalse(discovery.isSearching)

        // Stopping again with no active browser should also be safe.
        discovery.stopDiscovery()
        XCTAssertFalse(discovery.isSearching)
    }
}
