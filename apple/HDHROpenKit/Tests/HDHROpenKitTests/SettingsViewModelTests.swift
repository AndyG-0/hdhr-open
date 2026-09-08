import XCTest
@testable import HDHROpenKit

@MainActor
final class SettingsViewModelTests: XCTestCase {
    private func makeMockedAPIClient() -> APIClient {
        APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
    }

    private func makeServerDiscovery() -> ServerDiscovery {
        ServerDiscovery(defaultURL: "http://localhost:8000", session: MockURLProtocol.makeSession())
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    // MARK: - Individual loaders

    func testLoadAppSettingsSuccess() async {
        MockURLProtocol.handlers["/api/settings"] = (Data("""
        {"timezone": "America/New_York", "guide_provider_priority": "sd", "dvr_server_priority": "builtin"}
        """.utf8), 200)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadAppSettings()

        XCTAssertEqual(vm.appSettings?.timezone, "America/New_York")
    }

    func testLoadAppSettingsFailureIsSilent() async {
        MockURLProtocol.handlers["/api/settings"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadAppSettings()

        XCTAssertNil(vm.appSettings)
    }

    func testLoadPresetsSuccess() async {
        MockURLProtocol.handlers["/api/streaming/transcode-presets"] = (Data("""
        [{"id": "software", "label": "Software", "description": "CPU", "input_args": [], "output_args": [], "hardware": false}]
        """.utf8), 200)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadPresets()

        XCTAssertEqual(vm.transcodePresets.map(\.id), ["software"])
    }

    func testLoadIntegrationsDerivesCurrentPresetId() async {
        MockURLProtocol.handlers["/api/network-settings"] = (Data("""
        [{"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {"hwaccel": "videotoolbox"}}]
        """.utf8), 200)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadIntegrations()

        XCTAssertEqual(vm.networkIntegrations.count, 1)
        XCTAssertEqual(vm.currentPresetId, "videotoolbox")
    }

    func testLoadIntegrationsWithoutHwaccelDefaultsToSoftware() async {
        MockURLProtocol.handlers["/api/network-settings"] = (Data("""
        [{"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {}}]
        """.utf8), 200)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadIntegrations()

        XCTAssertEqual(vm.currentPresetId, "software")
    }

    func testLoadDevicesSuccess() async {
        MockURLProtocol.handlers["/api/devices"] = (Data("""
        [{"id": "dev1", "name": "iPhone", "last_seen_at": "2026-09-06T00:00:00Z"}]
        """.utf8), 200)
        MockURLProtocol.handlers["/api/devices/me"] = (Data("""
        {"id": "dev1", "name": "iPhone"}
        """.utf8), 200)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadDevices()

        XCTAssertEqual(vm.registeredDevices.map(\.id), ["dev1"])
        XCTAssertEqual(vm.currentDevice?.id, "dev1")
    }

    func testLoadDevicesFailureIsSilent() async {
        MockURLProtocol.handlers["/api/devices"] = (Data("{\"detail\":\"boom\"}".utf8), 500)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadDevices()

        XCTAssertTrue(vm.registeredDevices.isEmpty)
        XCTAssertNil(vm.currentDevice)
    }

    func testLoadDataCombinesAllLoaders() async {
        MockURLProtocol.handlers["/api/settings"] = (Data("""
        {"timezone": "UTC"}
        """.utf8), 200)
        MockURLProtocol.handlers["/api/streaming/transcode-presets"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/network-settings"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/devices"] = (Data("[]".utf8), 200)
        MockURLProtocol.handlers["/api/devices/me"] = (Data("""
        {"id": "dev1", "name": "iPhone"}
        """.utf8), 200)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadData()

        XCTAssertFalse(vm.isLoading)
        XCTAssertEqual(vm.appSettings?.timezone, "UTC")
        XCTAssertEqual(vm.currentDevice?.id, "dev1")
    }

    // MARK: - selectPreset (optimistic update + rollback)

    func testSelectPresetSameIdIsNoOp() async {
        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        // currentPresetId defaults to "software"; selecting the same id should
        // return early without ever calling the API (no handler registered for
        // network-settings/hdhomerun, so any call would surface as a 404 error).
        await vm.selectPreset("software")

        XCTAssertEqual(vm.currentPresetId, "software")
        XCTAssertFalse(vm.isSavingPreset)
    }

    func testSelectPresetSuccessUpdatesIntegrationAndPresetId() async {
        MockURLProtocol.handlers["/api/network-settings"] = (Data("""
        [{"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {"hwaccel": "software"}}]
        """.utf8), 200)
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("""
        {"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {"hwaccel": "videotoolbox"}}
        """.utf8), 200)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadIntegrations()
        XCTAssertEqual(vm.currentPresetId, "software")

        await vm.selectPreset("videotoolbox")

        XCTAssertEqual(vm.currentPresetId, "videotoolbox")
        XCTAssertFalse(vm.isSavingPreset)
        XCTAssertEqual(vm.networkIntegrations.first?.settings["hwaccel"]?.value as? String, "videotoolbox")
    }

    func testSelectPresetFailureRollsBackToPreviousPresetId() async {
        MockURLProtocol.handlers["/api/network-settings"] = (Data("""
        [{"id": "int1", "type": "hdhomerun", "name": "HDHomeRun", "settings": {"hwaccel": "software"}}]
        """.utf8), 200)
        // The update endpoint fails - the optimistic write to currentPresetId
        // must be rolled back to the value it had before selectPreset() ran.
        MockURLProtocol.handlers["/api/network-settings/hdhomerun"] = (Data("{\"detail\":\"failed\"}".utf8), 500)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        await vm.loadIntegrations()
        XCTAssertEqual(vm.currentPresetId, "software")

        await vm.selectPreset("videotoolbox")

        XCTAssertEqual(vm.currentPresetId, "software", "should roll back to the previous preset id on failure")
        XCTAssertFalse(vm.isSavingPreset)
        // The integration list itself is untouched since the PATCH never succeeded.
        XCTAssertEqual(vm.networkIntegrations.first?.settings["hwaccel"]?.value as? String, "software")
    }

    // MARK: - testServerConnection

    func testTestServerConnectionSuccess() async throws {
        MockURLProtocol.handlers["/api/setup/status"] = (Data("{}".utf8), 200)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        let ok = try await vm.testServerConnection(url: XCTUnwrap(URL(string: "http://localhost:8000")))

        XCTAssertTrue(ok)
        XCTAssertEqual(vm.connectionStatus, "Server reachable")
        XCTAssertFalse(vm.isTestingConnection)
    }

    func testTestServerConnectionFailure() async throws {
        MockURLProtocol.handlers["/api/setup/status"] = (Data("{}".utf8), 500)

        let vm = SettingsViewModel(apiClient: makeMockedAPIClient(), serverDiscovery: makeServerDiscovery())
        let ok = try await vm.testServerConnection(url: XCTUnwrap(URL(string: "http://localhost:8000")))

        XCTAssertFalse(ok)
        XCTAssertEqual(vm.connectionStatus, "Server unreachable")
        XCTAssertFalse(vm.isTestingConnection)
    }
}
