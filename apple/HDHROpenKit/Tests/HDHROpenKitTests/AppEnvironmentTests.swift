import XCTest
@testable import HDHROpenKit

/// `AppEnvironment` wires up `ServerDiscovery`, `ThemeManager`, and friends,
/// which in turn persist to `UserDefaults.standard` under these keys
/// (mirrored from the private constants in ServerDiscovery.swift and
/// ThemeManager.swift). Tests save/restore whatever was there before so
/// they never leak state into other tests or the developer's machine.
private let serverURLDefaultsKey = "org.hdhropen.client.serverURL"
private let themeModeDefaultsKey = "org.hdhropen.client.themeMode"

@MainActor
final class AppEnvironmentTests: XCTestCase {
    private var savedServerURLValue: String?
    private var savedThemeModeValue: String?

    override func setUp() {
        super.setUp()
        savedServerURLValue = UserDefaults.standard.string(forKey: serverURLDefaultsKey)
        savedThemeModeValue = UserDefaults.standard.string(forKey: themeModeDefaultsKey)
        UserDefaults.standard.removeObject(forKey: serverURLDefaultsKey)
        UserDefaults.standard.removeObject(forKey: themeModeDefaultsKey)
    }

    override func tearDown() {
        if let savedServerURLValue {
            UserDefaults.standard.set(savedServerURLValue, forKey: serverURLDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: serverURLDefaultsKey)
        }
        if let savedThemeModeValue {
            UserDefaults.standard.set(savedThemeModeValue, forKey: themeModeDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: themeModeDefaultsKey)
        }
        super.tearDown()
    }

    // MARK: - Wiring: ServerDiscovery -> APIClient

    func testInitWiresApiClientBaseURLFromDefaultURLStringWhenNothingStored() async {
        let env = AppEnvironment(defaultURLString: "http://192.168.50.10:9200")

        let baseURL = await env.apiClient.baseURL

        XCTAssertEqual(baseURL, URL(string: "http://192.168.50.10:9200"))
        XCTAssertEqual(env.serverDiscovery.currentServerURL, baseURL)
    }

    func testInitWiresApiClientBaseURLFromStoredServerURLOverDefault() async {
        UserDefaults.standard.set("http://stored-server:7000", forKey: serverURLDefaultsKey)

        let env = AppEnvironment(defaultURLString: "http://127.0.0.1:8000")

        let baseURL = await env.apiClient.baseURL

        XCTAssertEqual(baseURL, URL(string: "http://stored-server:7000"))
        XCTAssertEqual(env.serverDiscovery.serverURLString, "http://stored-server:7000")
    }

    // MARK: - Wiring: shared APIClient/AuthManager reach the view models

    func testAuthViewModelForwardsAuthManagerState() {
        let env = AppEnvironment()

        // Fresh AuthManager: no session restored yet, so both should agree
        // it's unauthenticated with no profiles loaded - proving
        // `authViewModel` reads through to the same `authManager` instance
        // rather than owning independent state.
        XCTAssertEqual(env.authViewModel.isAuthenticated, env.authManager.isAuthenticated)
        XCTAssertFalse(env.authViewModel.isAuthenticated)
        XCTAssertEqual(env.authViewModel.profiles.count, env.authManager.profiles.count)
        XCTAssertNil(env.authViewModel.currentUser)
    }

    // MARK: - Construction: dependent objects exist with expected defaults

    func testInitConstructsAllDependentObjectsWithDefaultState() {
        let env = AppEnvironment()

        XCTAssertTrue(env.tunerViewModel.tuners.isEmpty)
        XCTAssertNil(env.tunerViewModel.tunerInfo)
        XCTAssertFalse(env.tunerViewModel.isPolling)

        XCTAssertTrue(env.authManager.profiles.isEmpty)
        XCTAssertFalse(env.authManager.isAuthenticated)

        XCTAssertFalse(env.serverDiscovery.isSearching)

        XCTAssertEqual(env.themeManager.mode, .system)

        XCTAssertTrue(env.multiPlayerViewModel.slots.isEmpty)
        XCTAssertEqual(env.multiPlayerViewModel.activeSlotIndex, 0)
        XCTAssertEqual(env.multiPlayerViewModel.layout, .sideBySide)
        XCTAssertFalse(env.multiPlayerViewModel.isMultiViewActive)
    }

    func testEachAppEnvironmentInstanceGetsItsOwnObjectGraph() {
        let envA = AppEnvironment(defaultURLString: "http://host-a:8000")
        let envB = AppEnvironment(defaultURLString: "http://host-b:8000")

        XCTAssertFalse(envA.tunerViewModel === envB.tunerViewModel)
        XCTAssertFalse(envA.authManager === envB.authManager)
        XCTAssertFalse(envA.themeManager === envB.themeManager)
        XCTAssertFalse(envA.multiPlayerViewModel === envB.multiPlayerViewModel)
    }
}
