import Security
import XCTest
@testable import HDHROpenKit

// MARK: - Keychain test helpers

//
// AuthManager stores its token/device id under these exact keys (mirrored
// from the private constants in AuthManager.swift). We read/write the
// Keychain directly here - using the same generic-password query shape the
// production code uses - so tests can set up preconditions and verify
// side effects without needing to expose any internals.

private let authTokenKeychainKey = "org.hdhropen.client.bearerToken"
private let authDeviceIdKeychainKey = "org.hdhropen.client.deviceId"

private func keychainSet(_ key: String, _ value: String) {
    keychainDelete(key)
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrAccount as String: key,
        kSecValueData as String: Data(value.utf8),
        kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
    ]
    SecItemAdd(query as CFDictionary, nil)
}

private func keychainGet(_ key: String) -> String? {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrAccount as String: key,
        kSecReturnData as String: true,
        kSecMatchLimit as String: kSecMatchLimitOne
    ]
    var result: AnyObject?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data else { return nil }
    return String(data: data, encoding: .utf8)
}

private func keychainDelete(_ key: String) {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrAccount as String: key
    ]
    SecItemDelete(query as CFDictionary)
}

@MainActor
final class AuthManagerTests: XCTestCase {
    private func makeAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    private func makeManager() -> AuthManager {
        AuthManager(apiClient: makeAPIClient())
    }

    private func makeProfile(id: String = "u1", name: String = "Alice") -> UserProfile {
        UserProfile(id: id, name: name, avatar: nil, hasPin: true)
    }

    override func setUp() {
        super.setUp()
        keychainDelete(authTokenKeychainKey)
        keychainDelete(authDeviceIdKeychainKey)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        keychainDelete(authTokenKeychainKey)
        keychainDelete(authDeviceIdKeychainKey)
        super.tearDown()
    }

    // MARK: - restoreSession

    func testRestoreSessionWithNoStoredTokenLeavesUserNil() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )

        let manager = makeManager()
        await manager.restoreSession()

        XCTAssertNil(manager.currentUser)
        XCTAssertFalse(manager.isAuthenticated)
    }

    func testRestoreSessionWithValidStoredTokenRestoresUser() async {
        keychainSet(authTokenKeychainKey, "valid-token")
        keychainSet(authDeviceIdKeychainKey, "dev-1")
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":false}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/me"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":null}".utf8), 200
        )

        let manager = makeManager()
        await manager.restoreSession()

        XCTAssertEqual(manager.currentUser?.id, "u1")
        XCTAssertEqual(manager.currentUser?.name, "Alice")
        XCTAssertTrue(manager.isAuthenticated)
    }

    func testRestoreSessionWithExpiredTokenClearsKeychainAndLeavesUserNil() async {
        keychainSet(authTokenKeychainKey, "expired-token")
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":false}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/me"] = (
            Data("{\"detail\":\"Token expired\"}".utf8), 401
        )

        let manager = makeManager()
        await manager.restoreSession()

        XCTAssertNil(manager.currentUser)
        XCTAssertFalse(manager.isAuthenticated)
        XCTAssertNil(keychainGet(authTokenKeychainKey), "expired token should be purged from the keychain")
    }

    // MARK: - registerDeviceIfNeeded

    func testRegisterDeviceIfNeededSuccessReturnsTrueAndStoresDeviceId() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-42\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )

        let apiClient = makeAPIClient()
        let manager = AuthManager(apiClient: apiClient)

        let result = await manager.registerDeviceIfNeeded()

        XCTAssertTrue(result)
        let storedDeviceId = await apiClient.currentDeviceId()
        XCTAssertEqual(storedDeviceId, "dev-42")
        XCTAssertEqual(keychainGet(authDeviceIdKeychainKey), "dev-42")
    }

    func testRegisterDeviceIfNeededFailureReturnsFalse() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"detail\":\"server exploded\"}".utf8), 500
        )

        let manager = makeManager()
        let result = await manager.registerDeviceIfNeeded()

        XCTAssertFalse(result)
        XCTAssertNil(keychainGet(authDeviceIdKeychainKey))
    }

    // MARK: - login

    func testLoginSuccessSetsCurrentUserAndStoresToken() async throws {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )

        let manager = makeManager()
        try await manager.login(user: makeProfile(), pin: "1234")

        XCTAssertEqual(manager.currentUser?.id, "u1")
        XCTAssertTrue(manager.isAuthenticated)
        XCTAssertNil(manager.authError)
        XCTAssertEqual(keychainGet(authTokenKeychainKey), "tok-abc")
    }

    func testLoginFailureThrowsAndSetsAuthError() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"detail\":\"Invalid PIN\"}".utf8), 401
        )

        let manager = makeManager()
        do {
            try await manager.login(user: makeProfile(), pin: "0000")
            XCTFail("Expected login to throw")
        } catch let APIError.unauthorized(detail) {
            XCTAssertEqual(detail, "Invalid PIN")
        } catch {
            XCTFail("Expected APIError.unauthorized, got \(error)")
        }

        XCTAssertNil(manager.currentUser)
        XCTAssertFalse(manager.isAuthenticated)
        XCTAssertEqual(manager.authError, "Invalid PIN")
        XCTAssertNil(keychainGet(authTokenKeychainKey))
    }

    /// Covers the auto-registration-retry branch in `login`: a 401 whose
    /// detail mentions "device" triggers a `registerDeviceIfNeeded()` retry.
    /// Here the retry registration itself fails, so we exercise the
    /// `else { authError = detail; throw ... }` arm of that branch. (A
    /// "retry succeeds and the second login attempt returns 200" scenario
    /// isn't reachable through the shared mock, since `MockURLProtocol`
    /// keys a single fixed response per path and both the initial and
    /// retried login calls hit the same path.)
    func testLoginWithDeviceErrorRetriesRegistrationAndThrowsWhenRetryFails() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"detail\":\"cannot register\"}".utf8), 500
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"detail\":\"device not recognized\"}".utf8), 401
        )

        let manager = makeManager()
        do {
            try await manager.login(user: makeProfile(), pin: "1234")
            XCTFail("Expected login to throw")
        } catch let APIError.unauthorized(detail) {
            XCTAssertEqual(detail, "device not recognized")
        } catch {
            XCTFail("Expected APIError.unauthorized, got \(error)")
        }

        XCTAssertEqual(manager.authError, "device not recognized")
        XCTAssertNil(manager.currentUser)
    }

    // MARK: - logout

    func testLogoutClearsStateAndKeychain() async throws {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/logout"] = (Data("{}".utf8), 200)

        let manager = makeManager()
        try await manager.login(user: makeProfile(), pin: "1234")
        XCTAssertTrue(manager.isAuthenticated)

        await manager.logout()

        XCTAssertNil(manager.currentUser)
        XCTAssertFalse(manager.isAuthenticated)
        XCTAssertNil(keychainGet(authTokenKeychainKey))
    }

    func testLogoutStillClearsLocalStateWhenServerCallFails() async throws {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/logout"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let manager = makeManager()
        try await manager.login(user: makeProfile(), pin: "1234")

        await manager.logout()

        XCTAssertNil(manager.currentUser)
        XCTAssertFalse(manager.isAuthenticated)
        XCTAssertNil(keychainGet(authTokenKeychainKey))
    }

    // MARK: - fetchProfiles

    func testFetchProfilesSuccessPopulatesProfiles() async {
        MockURLProtocol.handlers["/api/users"] = (
            Data("""
            [
                {"id":"u1","name":"Alice","avatar":null,"has_pin":true},
                {"id":"u2","name":"Bob","avatar":null,"has_pin":false}
            ]
            """.utf8), 200
        )

        let manager = makeManager()
        await manager.fetchProfiles()

        XCTAssertEqual(manager.profiles.count, 2)
        XCTAssertEqual(manager.profiles.first?.id, "u1")
        XCTAssertFalse(manager.isLoading)
        XCTAssertNil(manager.authError)
    }

    func testFetchProfilesFailureSetsAuthError() async {
        MockURLProtocol.handlers["/api/users"] = (
            Data("{\"detail\":\"boom\"}".utf8), 500
        )

        let manager = makeManager()
        await manager.fetchProfiles()

        XCTAssertTrue(manager.profiles.isEmpty)
        XCTAssertNotNil(manager.authError)
        XCTAssertFalse(manager.isLoading)
    }
}
