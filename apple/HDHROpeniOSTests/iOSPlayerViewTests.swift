import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpeniOS

/// `PlaybackPreferences` persists `autoSkipCommercialsEnabled` to
/// `UserDefaults.standard` under this key (mirrored from the private
/// constant in PlaybackPreferences.swift). Save/restore it in setUp/tearDown
/// so a test that turns the preference on never leaks it into another test
/// via the shared, disk-backed UserDefaults.standard.
private let autoSkipCommercialsDefaultsKey = "org.hdhropen.client.autoSkipCommercialsEnabled"

@MainActor
final class iOSPlayerViewTests: XCTestCase {
    private var savedAutoSkipDefaultsValue: Bool?

    override func setUp() {
        super.setUp()
        if UserDefaults.standard.object(forKey: autoSkipCommercialsDefaultsKey) != nil {
            savedAutoSkipDefaultsValue = UserDefaults.standard.bool(forKey: autoSkipCommercialsDefaultsKey)
        }
        UserDefaults.standard.removeObject(forKey: autoSkipCommercialsDefaultsKey)
    }

    override func tearDown() {
        if let savedAutoSkipDefaultsValue {
            UserDefaults.standard.set(savedAutoSkipDefaultsValue, forKey: autoSkipCommercialsDefaultsKey)
        } else {
            UserDefaults.standard.removeObject(forKey: autoSkipCommercialsDefaultsKey)
        }
        super.tearDown()
    }

    private func makeEnvironmentObjects() -> (PlayerViewModel, GuideViewModel, RecordingsViewModel) {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let watchSessionManager = WatchSessionManager(apiClient: apiClient)
        let playerViewModel = PlayerViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let guideViewModel = GuideViewModel(apiClient: apiClient, watchSessionManager: watchSessionManager)
        let recordingsViewModel = RecordingsViewModel(apiClient: apiClient)
        return (playerViewModel, guideViewModel, recordingsViewModel)
    }

    private func makeView(
        _ playerViewModel: PlayerViewModel,
        _ guideViewModel: GuideViewModel,
        _ recordingsViewModel: RecordingsViewModel,
        _ multiPlayerViewModel: MultiPlayerViewModel? = nil,
        isRegularSizeClass: Bool? = nil,
        playbackPreferences: PlaybackPreferences? = nil
    ) -> some View {
        let multiVM = multiPlayerViewModel ?? MultiPlayerViewModel(
            apiClient: APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession()),
            watchSessionManager: WatchSessionManager(apiClient: APIClient(
                baseURL: URL(string: "http://localhost:8000")!,
                session: MockURLProtocol.makeSession()
            ))
        )
        return iOSPlayerView(isRegularSizeClassOverride: isRegularSizeClass)
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)
            .environmentObject(multiVM)
            .environmentObject(playbackPreferences ?? PlaybackPreferences())
    }

    func testShowsLiveTVTitleByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(playerViewModel.activeChannel)
        XCTAssertNil(playerViewModel.activeRecording)
        XCTAssertEqual(playerViewModel.mediaTitle, "Live TV")

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Live TV"))
    }

    func testHidesErrorAndLoadingOverlaysInIdleState() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertEqual(playerViewModel.playerEngine.state, .idle)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Playback Error"))
        XCTAssertThrowsError(try view.inspect().find(ViewType.ProgressView.self))
    }

    func testShowsErrorOverlayWhenPlaybackFails() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        playerViewModel.playerEngine.setFailed("Stream broke")

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Playback Error"))
        XCTAssertNoThrow(try view.inspect().find(text: "Stream broke"))
        XCTAssertNoThrow(try view.inspect().find(text: "Close"))
    }

    func testShowsLoadingSpinnerWhenLoading() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        playerViewModel.playerEngine.setLoading()

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.ProgressView.self))
        XCTAssertThrowsError(try view.inspect().find(text: "Playback Error"))
    }

    func testIncludesScrubBarAndAirPlayPicker() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(iOSScrubBarView.self))
        XCTAssertNoThrow(try view.inspect().find(AirPlayRoutePickerView.self))
    }

    func testHidesSkipCommercialButtonByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(playerViewModel.playerEngine.activeCommercialSegment)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Skip Commercial"))
    }

    func testShowsSkipCommercialButtonWhenCurrentTimeInsideSegment() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))
        playerViewModel.playerEngine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0)
        playerViewModel.playerEngine.setCommercialSegments([
            HDHomeRunCommercialSegment(startSeconds: 100, endSeconds: 160),
        ])
        playerViewModel.playerEngine.seek(to: 120)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Skip Commercial"))
    }

    // showAutoSkipPill defaults to false and only flips via `.onChange(of:
    // playerViewModel.autoSkipPulse)`, which this codebase's established
    // convention (see TVPlayerViewTests) doesn't exercise without
    // `ViewHosting`. What's independently verifiable in a static tree is
    // that enabling the preference suppresses the manual button even with
    // an active segment, since the pill itself stays hidden until a pulse
    // fires.
    func testHidesManualSkipCommercialButtonWhenAutoSkipPreferenceEnabledEvenWithActiveSegment() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let fakeURL = try XCTUnwrap(URL(string: "http://localhost:8000/stream.m3u8"))
        playerViewModel.playerEngine.loadMedia(url: fakeURL, isSeekable: true, initialDuration: 3600.0)
        playerViewModel.playerEngine.setCommercialSegments([
            HDHomeRunCommercialSegment(startSeconds: 100, endSeconds: 160),
        ])
        playerViewModel.playerEngine.seek(to: 120)
        let preferences = PlaybackPreferences()
        preferences.autoSkipCommercialsEnabled = true

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel, playbackPreferences: preferences)

        XCTAssertThrowsError(try view.inspect().find(text: "Skip Commercial"))
        XCTAssertThrowsError(try view.inspect().find(text: "Commercial skipped"))
    }

    func testHidesRecordMenuWhenNotAWatchSession() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.isWatchSession)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(text: "Record"))
    }

    func testHidesPlaybackInfoOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(iOSPlaybackInfoOverlay.self))
    }

    func testShowsMultiViewButtonInRegularSizeClassWhenLiveChannel() async throws {
        MockURLProtocol.handlers["/api/watch/4.1/start"] = (
            Data("{\"recording_id\":\"rec1\",\"session_id\":\"sess1\",\"title\":\"NBC\",\"play_url\":\"/stream/4.1\"}".utf8), 200
        )
        MockURLProtocol.handlers["/api/dvr/recording-stream-hls"] = (
            Data("{\"session_id\":\"hls_sess1\",\"playlist_url\":\"/api/streaming/hls/hls_sess1/playlist.m3u8\"}".utf8), 200
        )
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        await playerViewModel.playChannel(channel: HDHomeRunChannel(channelNumber: "4.1", name: "NBC"))

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel, isRegularSizeClass: true)

        XCTAssertNoThrow(try view.inspect().find(where: { v in
            if let img = try? v.image() {
                return (try? img.actualImage().name()) == "square.grid.2x2"
            }
            return false
        }))
    }
}
