import XCTest
@testable import HDHROpenKit

/// `ThemeManager` persists `mode` to `UserDefaults.standard` under this key
/// (mirrored from the private constant in ThemeManager.swift). Tests
/// save/restore whatever was there before so they never leak state into
/// other tests or the developer's machine.
private let themeModeDefaultsKey = "org.hdhropen.client.themeMode"

@MainActor
final class ThemeManagerTests: XCTestCase {
    private var savedDefaultsValue: String?

    override func setUp() {
        super.setUp()
        savedDefaultsValue = UserDefaults.standard.string(forKey: themeModeDefaultsKey)
        UserDefaults.standard.removeObject(forKey: themeModeDefaultsKey)
    }

    override func tearDown() {
        if let savedDefaultsValue {
            UserDefaults.standard.set(savedDefaultsValue, forKey: themeModeDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: themeModeDefaultsKey)
        }
        super.tearDown()
    }

    // MARK: - Init

    func testInitDefaultsToSystemWhenNothingStored() {
        let manager = ThemeManager()

        XCTAssertEqual(manager.mode, .system)
    }

    func testInitUsesStoredValueWhenPresent() {
        UserDefaults.standard.set(ThemeMode.dark.rawValue, forKey: themeModeDefaultsKey)

        let manager = ThemeManager()

        XCTAssertEqual(manager.mode, .dark)
    }

    func testInitFallsBackToSystemForInvalidStoredValue() {
        UserDefaults.standard.set("not-a-real-mode", forKey: themeModeDefaultsKey)

        let manager = ThemeManager()

        XCTAssertEqual(manager.mode, .system)
    }

    // MARK: - Setting mode persists

    func testSettingModePersistsToUserDefaults() {
        let manager = ThemeManager()

        manager.mode = .light

        XCTAssertEqual(UserDefaults.standard.string(forKey: themeModeDefaultsKey), "light")

        manager.mode = .dark

        XCTAssertEqual(UserDefaults.standard.string(forKey: themeModeDefaultsKey), "dark")
    }

    // MARK: - colorScheme mapping

    func testColorSchemeForLightModeIsLight() {
        let manager = ThemeManager()
        manager.mode = .light

        XCTAssertEqual(manager.colorScheme, .light)
    }

    func testColorSchemeForDarkModeIsDark() {
        let manager = ThemeManager()
        manager.mode = .dark

        XCTAssertEqual(manager.colorScheme, .dark)
    }

    func testColorSchemeForSystemModeIsNil() {
        let manager = ThemeManager()
        manager.mode = .system

        XCTAssertNil(manager.colorScheme)
    }

    // MARK: - ThemeMode

    func testThemeModeAllCasesContainsAllThreeModes() {
        XCTAssertEqual(Set(ThemeMode.allCases), Set([.light, .dark, .system]))
    }

    func testThemeModeLabels() {
        XCTAssertEqual(ThemeMode.light.label, "Light")
        XCTAssertEqual(ThemeMode.dark.label, "Dark")
        XCTAssertEqual(ThemeMode.system.label, "System")
    }
}
