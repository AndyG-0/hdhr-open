import Combine
import Security
import XCTest
@testable import HDHROpenKit

// MARK: - Keychain test helpers

//
// AuthManager stores its token/device id under these exact keys (mirrored
// from the private constants in AuthManager.swift). AuthViewModel drives
// AuthManager's login/logout, which touches the real Keychain, so tests
// clear these keys before/after each run to avoid cross-test pollution.

private let authTokenKeychainKey = "org.hdhropen.client.bearerToken"
private let authDeviceIdKeychainKey = "org.hdhropen.client.deviceId"

private func keychainDelete(_ key: String) {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrAccount as String: key
    ]
    SecItemDelete(query as CFDictionary)
}

@MainActor
final class AuthViewModelTests: XCTestCase {
    private var cancellables: Set<AnyCancellable> = []

    private func makeAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    private func makeViewModel(apiClient: APIClient? = nil) -> (AuthViewModel, AuthManager) {
        let client = apiClient ?? makeAPIClient()
        let authManager = AuthManager(apiClient: client)
        return (AuthViewModel(authManager: authManager), authManager)
    }

    private func makeProfile(id: String = "u1", name: String = "Alice", hasPin: Bool = true) -> UserProfile {
        UserProfile(id: id, name: name, avatar: nil, hasPin: hasPin)
    }

    override func setUp() {
        super.setUp()
        keychainDelete(authTokenKeychainKey)
        keychainDelete(authDeviceIdKeychainKey)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        cancellables.removeAll()
        keychainDelete(authTokenKeychainKey)
        keychainDelete(authDeviceIdKeychainKey)
        super.tearDown()
    }

    // MARK: - selectProfile

    func testSelectProfileWithPinShowsPINPromptWithoutLoggingIn() {
        let (vm, _) = makeViewModel()
        let profile = makeProfile(hasPin: true)

        vm.selectProfile(profile)

        XCTAssertEqual(vm.selectedProfile?.id, "u1")
        XCTAssertEqual(vm.pinInput, "")
        XCTAssertNil(vm.errorMessage)
        XCTAssertTrue(vm.isPINPromptVisible)
        XCTAssertFalse(vm.isAuthenticated)
    }

    func testSelectProfileWithoutPinLogsInAutomatically() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )

        let (vm, authManager) = makeViewModel()
        let profile = makeProfile(hasPin: false)

        let expectation = expectation(description: "auto login completes")
        authManager.$currentUser
            .dropFirst()
            .sink { _ in expectation.fulfill() }
            .store(in: &cancellables)

        vm.selectProfile(profile)

        await fulfillment(of: [expectation], timeout: 2.0)

        XCTAssertTrue(vm.isAuthenticated)
        XCTAssertEqual(vm.currentUser?.id, "u1")
        // hasPin == false never touches the PIN prompt path.
        XCTAssertFalse(vm.isPINPromptVisible)
    }

    func testSelectProfileWithoutPinSetsErrorMessageOnFailure() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"detail\":\"boom\"}".utf8), 500
        )

        let (vm, _) = makeViewModel()
        let profile = makeProfile(hasPin: false)

        // `selectProfile` itself resets `errorMessage = nil` synchronously
        // before the login Task even runs (and `@Published` republishes on
        // every assignment, not just real changes), so watch for the first
        // *non-nil* value rather than just dropping the initial replay.
        let expectation = expectation(description: "auto login fails")
        vm.$errorMessage
            .compactMap { $0 }
            .first()
            .sink { _ in expectation.fulfill() }
            .store(in: &cancellables)

        vm.selectProfile(profile)

        await fulfillment(of: [expectation], timeout: 2.0)

        XCTAssertFalse(vm.isAuthenticated)
        XCTAssertNotNil(vm.errorMessage)
    }

    // MARK: - submitPIN

    func testSubmitPINWithEmptyInputSetsErrorMessageAndDoesNotLogIn() async {
        let (vm, _) = makeViewModel()
        vm.selectProfile(makeProfile(hasPin: true))

        await vm.submitPIN()

        XCTAssertEqual(vm.errorMessage, "Please enter your PIN")
        XCTAssertTrue(vm.isPINPromptVisible, "prompt should stay open so the user can retry")
        XCTAssertFalse(vm.isAuthenticated)
    }

    func testSubmitPINWithNoSelectedProfileIsANoOp() async {
        let (vm, _) = makeViewModel()

        await vm.submitPIN()

        XCTAssertNil(vm.errorMessage)
        XCTAssertFalse(vm.isPINPromptVisible)
    }

    func testSubmitPINSuccessLogsInAndClearsPromptAndInput() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )

        let (vm, _) = makeViewModel()
        vm.selectProfile(makeProfile(hasPin: true))
        vm.pinInput = "1234"

        await vm.submitPIN()

        XCTAssertFalse(vm.isPINPromptVisible)
        XCTAssertEqual(vm.pinInput, "")
        XCTAssertNil(vm.errorMessage)
        XCTAssertTrue(vm.isAuthenticated)
        XCTAssertEqual(vm.currentUser?.id, "u1")
    }

    func testSubmitPINWrongPinSetsErrorMessageAndClearsInputButKeepsPromptOpen() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"detail\":\"Invalid PIN\"}".utf8), 401
        )

        let (vm, _) = makeViewModel()
        vm.selectProfile(makeProfile(hasPin: true))
        vm.pinInput = "0000"

        await vm.submitPIN()

        XCTAssertEqual(vm.errorMessage, "Invalid PIN")
        XCTAssertEqual(vm.pinInput, "")
        XCTAssertTrue(vm.isPINPromptVisible)
        XCTAssertFalse(vm.isAuthenticated)
    }

    func testSubmitPINLockedOutSetsErrorMessage() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"detail\":\"Too many attempts, try again later\"}".utf8), 429
        )

        let (vm, _) = makeViewModel()
        vm.selectProfile(makeProfile(hasPin: true))
        vm.pinInput = "1234"

        await vm.submitPIN()

        XCTAssertEqual(vm.errorMessage, "Too many attempts, try again later")
        XCTAssertFalse(vm.isAuthenticated)
    }

    // MARK: - cancelPINEntry

    func testCancelPINEntryResetsState() {
        let (vm, _) = makeViewModel()
        vm.selectProfile(makeProfile(hasPin: true))
        vm.pinInput = "12"
        vm.errorMessage = "some error"

        vm.cancelPINEntry()

        XCTAssertFalse(vm.isPINPromptVisible)
        XCTAssertNil(vm.selectedProfile)
        XCTAssertEqual(vm.pinInput, "")
        XCTAssertNil(vm.errorMessage)
    }

    // MARK: - appendPINDigit / deletePINDigit

    func testAppendPINDigitAppendsCharacters() {
        let (vm, _) = makeViewModel()

        vm.appendPINDigit("1")
        vm.appendPINDigit("2")
        vm.appendPINDigit("3")

        XCTAssertEqual(vm.pinInput, "123")
    }

    func testAppendPINDigitStopsAtEightCharacters() {
        let (vm, _) = makeViewModel()

        for digit in "123456789" {
            vm.appendPINDigit(String(digit))
        }

        XCTAssertEqual(vm.pinInput, "12345678")
        XCTAssertEqual(vm.pinInput.count, 8)
    }

    func testDeletePINDigitRemovesLastCharacter() {
        let (vm, _) = makeViewModel()
        vm.appendPINDigit("1")
        vm.appendPINDigit("2")
        vm.appendPINDigit("3")

        vm.deletePINDigit()

        XCTAssertEqual(vm.pinInput, "12")
    }

    func testDeletePINDigitOnEmptyInputIsANoOp() {
        let (vm, _) = makeViewModel()

        vm.deletePINDigit()

        XCTAssertEqual(vm.pinInput, "")
    }

    // MARK: - logout

    func testLogoutClearsSelectedProfileAndPINPromptAndAuthState() async {
        MockURLProtocol.handlers["/api/devices/register"] = (
            Data("{\"id\":\"dev-1\",\"name\":\"Test Device\",\"is_new\":true}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/u1/login"] = (
            Data("{\"id\":\"u1\",\"name\":\"Alice\",\"avatar\":null,\"role\":\"member\",\"token\":\"tok-abc\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/users/logout"] = (Data("{}".utf8), 200)

        let (vm, _) = makeViewModel()
        vm.selectProfile(makeProfile(hasPin: true))
        vm.pinInput = "1234"
        await vm.submitPIN()
        XCTAssertTrue(vm.isAuthenticated)

        await vm.logout()

        XCTAssertFalse(vm.isAuthenticated)
        XCTAssertNil(vm.selectedProfile)
        XCTAssertFalse(vm.isPINPromptVisible)
    }

    // MARK: - forwarding to AuthManager

    func testProfilesForwardsAuthManagerProfiles() async {
        MockURLProtocol.handlers["/api/users"] = (
            Data("""
            [
                {"id":"u1","name":"Alice","avatar":null,"has_pin":true},
                {"id":"u2","name":"Bob","avatar":null,"has_pin":false}
            ]
            """.utf8), 200
        )

        let (vm, authManager) = makeViewModel()
        await authManager.fetchProfiles()

        XCTAssertEqual(vm.profiles.count, 2)
        XCTAssertEqual(vm.profiles.map(\.id), authManager.profiles.map(\.id))
    }
}
