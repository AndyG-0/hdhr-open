import XCTest
@testable import HDHROpenKit

/// `Log` is a thin wrapper around `os.Logger` instances. These are light
/// smoke tests confirming each category can be exercised without crashing.
final class LoggerTests: XCTestCase {
    func testGeneralLoggerLogsAtAllLevelsWithoutCrashing() {
        Log.general.trace("trace message")
        Log.general.debug("debug message")
        Log.general.info("info message")
        Log.general.notice("notice message")
        Log.general.warning("warning message")
        Log.general.error("error message")
        Log.general.critical("critical message")
    }

    func testNetworkLoggerLogsWithoutCrashing() {
        Log.network.info("network info message")
        Log.network.error("network error message")
    }

    func testAuthLoggerLogsWithoutCrashing() {
        Log.auth.info("auth info message")
        Log.auth.error("auth error message")
    }

    func testPlayerLoggerLogsWithoutCrashing() {
        Log.player.info("player info message")
        Log.player.error("player error message")
    }

    func testDvrLoggerLogsWithoutCrashing() {
        Log.dvr.info("dvr info message")
        Log.dvr.error("dvr error message")
    }

    func testLoggersSupportStringInterpolation() {
        let code = 42
        let name = "test"
        Log.general.info("interpolated \(name) with code \(code)")
    }

    func testAllCategoriesCanLogTogetherWithoutCrashing() {
        Log.general.warning("general warning")
        Log.network.warning("network warning")
        Log.auth.warning("auth warning")
        Log.player.warning("player warning")
        Log.dvr.warning("dvr warning")
    }
}
