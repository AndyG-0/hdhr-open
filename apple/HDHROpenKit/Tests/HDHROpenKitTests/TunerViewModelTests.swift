import Combine
import XCTest
@testable import HDHROpenKit

@MainActor
final class TunerViewModelTests: XCTestCase {
    private var cancellables: Set<AnyCancellable> = []

    private func makeViewModel() -> TunerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return TunerViewModel(apiClient: apiClient)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        cancellables.removeAll()
        super.tearDown()
    }

    // MARK: - Initial state

    func testInitialStateIsEmpty() {
        let vm = makeViewModel()

        XCTAssertTrue(vm.tuners.isEmpty)
        XCTAssertNil(vm.tunerInfo)
        XCTAssertFalse(vm.isLoading)
        XCTAssertFalse(vm.isPolling)
    }

    // MARK: - loadStatus

    func testLoadStatusSuccessPopulatesTuners() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (
            Data("""
            [
                {"index": 0, "in_use": false},
                {"index": 1, "in_use": true, "channel_number": "4.1", "channel_name": "Test Channel"}
            ]
            """.utf8), 200
        )

        let vm = makeViewModel()
        await vm.loadStatus()

        XCTAssertEqual(vm.tuners.count, 2)
        XCTAssertEqual(vm.tuners[1].channelNumber, "4.1")
        XCTAssertTrue(vm.tuners[1].inUse)
    }

    func testLoadStatusFailureLeavesTunersEmpty() async {
        // No handler registered for /api/tuner/status -> MockURLProtocol
        // falls back to a 404, exercising the caught-and-logged error path.
        let vm = makeViewModel()

        await vm.loadStatus()

        XCTAssertTrue(vm.tuners.isEmpty)
    }

    // MARK: - loadInfo

    func testLoadInfoSuccessPopulatesTunerInfo() async {
        MockURLProtocol.handlers["/api/tuner/info"] = (
            Data("""
            {"friendly_name": "HDHomeRun CONNECT", "model_number": "HDHR5-4DT", "firmware_version": "20240101", "tuner_count": 4}
            """.utf8), 200
        )

        let vm = makeViewModel()
        await vm.loadInfo()

        XCTAssertEqual(vm.tunerInfo?.friendlyName, "HDHomeRun CONNECT")
        XCTAssertEqual(vm.tunerInfo?.tunerCount, 4)
    }

    func testLoadInfoFailureLeavesTunerInfoNil() async {
        let vm = makeViewModel()

        await vm.loadInfo()

        XCTAssertNil(vm.tunerInfo)
    }

    // MARK: - loadData

    func testLoadDataLoadsBothStatusAndInfoAndClearsIsLoading() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (
            Data("[{\"index\": 0, \"in_use\": false}]".utf8), 200
        )
        MockURLProtocol.handlers["/api/tuner/info"] = (
            Data("{\"friendly_name\": \"HDHomeRun CONNECT\"}".utf8), 200
        )

        let vm = makeViewModel()
        await vm.loadData()

        XCTAssertEqual(vm.tuners.count, 1)
        XCTAssertEqual(vm.tunerInfo?.friendlyName, "HDHomeRun CONNECT")
        XCTAssertFalse(vm.isLoading)
    }

    func testLoadDataWithFailingEndpointsClearsIsLoadingAndLeavesStateEmpty() async {
        let vm = makeViewModel()

        await vm.loadData()

        XCTAssertTrue(vm.tuners.isEmpty)
        XCTAssertNil(vm.tunerInfo)
        XCTAssertFalse(vm.isLoading)
    }

    // MARK: - Polling

    func testStartPollingSetsIsPollingTrueAndLoadsStatusImmediately() async {
        MockURLProtocol.handlers["/api/tuner/status"] = (
            Data("[{\"index\": 0, \"in_use\": false}]".utf8), 200
        )

        let vm = makeViewModel()
        let expectation = expectation(description: "polling loads tuner status")
        vm.$tuners
            .dropFirst()
            .sink { _ in expectation.fulfill() }
            .store(in: &cancellables)

        // A long interval keeps the poll loop from firing a second time
        // within the test window, isolating the "loads immediately on
        // start" behavior from the periodic re-poll behavior.
        vm.startPolling(intervalSeconds: 30)

        XCTAssertTrue(vm.isPolling)
        await fulfillment(of: [expectation], timeout: 2.0)

        XCTAssertEqual(vm.tuners.count, 1)

        vm.stopPolling()
    }

    func testStartPollingIsNoOpWhenAlreadyPolling() {
        let vm = makeViewModel()

        vm.startPolling(intervalSeconds: 30)
        XCTAssertTrue(vm.isPolling)

        // Calling again while already polling should be guarded as a
        // no-op rather than spawning a second poll loop.
        vm.startPolling(intervalSeconds: 30)
        XCTAssertTrue(vm.isPolling)

        vm.stopPolling()
    }

    func testStopPollingSetsIsPollingFalse() {
        let vm = makeViewModel()
        vm.startPolling(intervalSeconds: 30)
        XCTAssertTrue(vm.isPolling)

        vm.stopPolling()

        XCTAssertFalse(vm.isPolling)
    }

    func testStopPollingWithoutStartingIsSafe() {
        let vm = makeViewModel()

        vm.stopPolling()

        XCTAssertFalse(vm.isPolling)
    }

    func testStartPollingAfterStopCanStartAgain() {
        let vm = makeViewModel()

        vm.startPolling(intervalSeconds: 30)
        vm.stopPolling()
        XCTAssertFalse(vm.isPolling)

        vm.startPolling(intervalSeconds: 30)
        XCTAssertTrue(vm.isPolling)

        vm.stopPolling()
    }
}
