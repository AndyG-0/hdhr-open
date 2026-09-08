import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVTunerStatusViewTests: XCTestCase {
    private func makeTunerViewModel() -> TunerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        return TunerViewModel(apiClient: apiClient)
    }

    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    func testShowsDiscoveringMessageWhenNoTuners() throws {
        let tunerViewModel = makeTunerViewModel()
        XCTAssertTrue(tunerViewModel.tuners.isEmpty)

        let view = TVTunerStatusView().environmentObject(tunerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Discovering Tuners..."))
    }

    func testHidesTunerInfoHeaderWhenNil() throws {
        let tunerViewModel = makeTunerViewModel()
        XCTAssertNil(tunerViewModel.tunerInfo)

        let view = TVTunerStatusView().environmentObject(tunerViewModel)

        XCTAssertThrowsError(
            try view.inspect().find(ViewType.Text.self, where: { try $0.string().contains("Firmware") })
        )
    }

    func testShowsTunerInfoHeaderWhenLoaded() async throws {
        let tunerViewModel = makeTunerViewModel()
        MockURLProtocol.handlers["/api/tuner/info"] = (Data("""
        {"friendly_name":"HDHomeRun FLEX","firmware_version":"20230815"}
        """.utf8), 200)
        await tunerViewModel.loadInfo()

        let view = TVTunerStatusView().environmentObject(tunerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "HDHomeRun FLEX • Firmware 20230815"))
    }

    func testShowsIdleTunerRow() async throws {
        let tunerViewModel = makeTunerViewModel()
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("""
        [{"index":0,"in_use":false}]
        """.utf8), 200)
        await tunerViewModel.loadStatus()
        XCTAssertEqual(tunerViewModel.tuners.count, 1)

        let view = TVTunerStatusView().environmentObject(tunerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Tuner 0"))
        XCTAssertNoThrow(try view.inspect().find(text: "Idle / Available"))
    }

    func testShowsInUseTunerDetailsAndSignalGauges() async throws {
        let tunerViewModel = makeTunerViewModel()
        MockURLProtocol.handlers["/api/tuner/status"] = (Data("""
        [{
            "index":1,
            "in_use":true,
            "channel_number":"4.1",
            "channel_name":"WNBC",
            "client":{"type":"tuner","name":"Living Room","details":"HLS","is_recording":false,"viewers":[]},
            "signal_strength_percent":90,
            "signal_quality_percent":85,
            "symbol_quality_percent":80,
            "network_rate_bps":5000000
        }]
        """.utf8), 200)
        await tunerViewModel.loadStatus()
        let tuner = try XCTUnwrap(tunerViewModel.tuners.first)
        XCTAssertEqual(tuner.formattedRateMbps, "5.0 Mbps")

        let view = TVTunerStatusView().environmentObject(tunerViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Tuner 1"))
        XCTAssertThrowsError(try view.inspect().find(text: "Idle / Available"))
        XCTAssertNoThrow(try view.inspect().find(text: "5.0 Mbps"))
        XCTAssertNoThrow(try view.inspect().find(text: "Channel 4.1"))
        XCTAssertNoThrow(try view.inspect().find(text: "WNBC"))
        XCTAssertNoThrow(try view.inspect().find(text: "Client: Living Room"))
        XCTAssertNoThrow(try view.inspect().find(text: "Signal Strength"))
        XCTAssertNoThrow(try view.inspect().find(text: "90%"))
    }

    func testShowsRefreshButton() throws {
        let tunerViewModel = makeTunerViewModel()
        let view = TVTunerStatusView().environmentObject(tunerViewModel)

        XCTAssertNoThrow(try view.inspect().find(button: "Refresh"))
    }
}
