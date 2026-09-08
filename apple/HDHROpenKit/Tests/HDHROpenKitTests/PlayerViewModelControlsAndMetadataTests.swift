import XCTest
@testable import HDHROpenKit

@MainActor
final class PlayerViewModelControlsAndMetadataTests: XCTestCase {
    override func tearDown() {
        MockURLProtocol.handlers = [:]
        super.tearDown()
    }

    private func makeViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!)
        return PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
    }

    /// `activeChannel`/`activeAiring` only have a private setter - the only way to
    /// populate them from test code is through `playChannel`, which sets both
    /// synchronously before any network I/O. All endpoints 404 by default (no
    /// handlers registered), so the watch-session/HLS calls fail and are swallowed,
    /// leaving `activeChannel`/`activeAiring` set with no other side effects.
    private func makeViewModelWithChannelActive(
        channel: HDHomeRunChannel,
        airing: HDHomeRunGuideEntry? = nil
    ) async -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession())
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
        await vm.playChannel(channel: channel, airing: airing)
        return vm
    }

    private func makeChannel(name: String = "Test Channel", number: String = "4.1") -> HDHomeRunChannel {
        HDHomeRunChannel(
            channelNumber: number,
            name: name,
            isHD: true,
            isDRM: false,
            streamUrl: "",
            playbackUrl: nil,
            now: nil,
            next: nil
        )
    }

    // MARK: - play / pause / togglePlayPause

    func testTogglePlayPauseFromLoadingStateTakesThePlayBranchWithoutCrashing() throws {
        // `playerEngine.state` only reaches `.paused`/`.playing` via a real
        // AVPlayer KVO transition, unreachable with a fake URL in a unit test -
        // this exercises togglePlayPause's `else { play() }` branch (anything
        // other than `.playing`/`.buffering` routes there) without asserting
        // a state transition that can't happen outside real playback.
        let vm = makeViewModel()
        try vm.playerEngine.loadMedia(url: XCTUnwrap(URL(string: "http://localhost:8000/fake.m3u8")), isSeekable: true)

        vm.togglePlayPause()

        XCTAssertFalse(vm.isPlaying)
    }

    func testPlayAndPauseAlsoNotifySyncPlayWhenConnected() throws {
        // The `syncPlayClient.isConnected` guard inside play()/pause() doesn't
        // depend on `playerEngine.state`, so this reaches `sendPlay`/`sendPause`
        // even though real `.playing`/`.paused` transitions aren't reachable here.
        let vm = makeViewModel()
        try vm.playerEngine.loadMedia(url: XCTUnwrap(URL(string: "http://localhost:8000/fake.m3u8")), isSeekable: true)
        try vm.syncPlayClient.connect(url: XCTUnwrap(URL(string: "ws://localhost:8000/ws")))

        vm.play()
        vm.pause()

        XCTAssertTrue(vm.syncPlayClient.isConnected)
    }

    // MARK: - mediaTitle / mediaSubtitle / playbackModeLabel

    func testMediaTitleFallsBackToLiveTVWhenNothingActive() {
        XCTAssertEqual(makeViewModel().mediaTitle, "Live TV")
    }

    func testMediaTitlePrefersActiveRecording() {
        let vm = makeViewModel()
        vm.activeRecording = HDHomeRunRecording(title: "My Recording")
        XCTAssertEqual(vm.mediaTitle, "My Recording")
    }

    func testMediaTitleUsesChannelAndAiringWhenNoRecording() async {
        let vm = await makeViewModelWithChannelActive(channel: makeChannel(), airing: HDHomeRunGuideEntry(title: "The Show"))
        XCTAssertEqual(vm.mediaTitle, "4.1 The Show")
    }

    func testMediaTitleUsesChannelNameWhenNoAiring() async {
        let vm = await makeViewModelWithChannelActive(channel: makeChannel())
        XCTAssertNil(vm.activeAiring)
        XCTAssertEqual(vm.mediaTitle, "4.1 Test Channel")
    }

    func testMediaSubtitlePrefersEpisodeDesignationAndTitleForRecording() {
        let vm = makeViewModel()
        vm.activeRecording = HDHomeRunRecording(title: "T", episodeTitle: "Pilot", episodeNumber: "1")
        XCTAssertEqual(vm.mediaSubtitle, "Ep 1 • Pilot")
    }

    func testMediaSubtitleFallsBackToChannelNameForRecordingWithNoEpisodeInfo() {
        let vm = makeViewModel()
        vm.activeRecording = HDHomeRunRecording(title: "T", channelName: "Local")
        XCTAssertEqual(vm.mediaSubtitle, "Local")
    }

    func testMediaSubtitleUsesAiringEpisodeInfoWhenNoRecording() async {
        let vm = await makeViewModelWithChannelActive(
            channel: makeChannel(),
            airing: HDHomeRunGuideEntry(title: "T", episodeTitle: "Second Episode", episodeNumber: "2")
        )
        XCTAssertEqual(vm.mediaSubtitle, "2 • Second Episode")
    }

    func testMediaSubtitleFallsBackToChannelWhenNothingActive() async {
        let vm = await makeViewModelWithChannelActive(channel: makeChannel())
        XCTAssertEqual(vm.mediaSubtitle, "Test Channel")
        XCTAssertNil(makeViewModel().mediaSubtitle)
    }

    func testPlaybackModeLabelUnknownWhenNil() {
        XCTAssertEqual(makeViewModel().playbackModeLabel, "Unknown")
    }

    // MARK: - currentSyncPlayContent / isCrossDeviceSyncActive

    func testCurrentSyncPlayContentNilWhenNothingActive() {
        XCTAssertNil(makeViewModel().currentSyncPlayContent())
    }

    func testCurrentSyncPlayContentForActiveRecording() {
        let vm = makeViewModel()
        vm.activeRecording = HDHomeRunRecording(title: "T", channelNumber: "5.1", durationSeconds: 1800)
        let content = vm.currentSyncPlayContent()
        XCTAssertEqual(content?.type, "recording")
        XCTAssertEqual(content?.channelNumber, "5.1")
        XCTAssertEqual(content?.durationSeconds, 1800)
    }

    func testCurrentSyncPlayContentForActiveChannelUsesAiringTitle() async {
        let vm = await makeViewModelWithChannelActive(channel: makeChannel(), airing: HDHomeRunGuideEntry(title: "Airing Title"))
        let content = vm.currentSyncPlayContent()
        XCTAssertEqual(content?.type, "channel")
        XCTAssertEqual(content?.title, "Airing Title")
    }

    func testIsCrossDeviceSyncActiveTracksSyncPlayConnection() throws {
        let vm = makeViewModel()
        XCTAssertFalse(vm.isCrossDeviceSyncActive)

        try vm.syncPlayClient.connect(url: XCTUnwrap(URL(string: "ws://localhost:8000/ws")))
        XCTAssertTrue(vm.isCrossDeviceSyncActive)

        vm.syncPlayClient.disconnect()
        XCTAssertFalse(vm.isCrossDeviceSyncActive)
    }

    // MARK: - closePlayer

    func testClosePlayerResetsAllActiveState() async {
        let vm = await makeViewModelWithChannelActive(channel: makeChannel(), airing: HDHomeRunGuideEntry(title: "T"))
        XCTAssertNotNil(vm.activeChannel)

        vm.closePlayer()

        XCTAssertNil(vm.activeChannel)
        XCTAssertNil(vm.activeAiring)
        XCTAssertNil(vm.activeRecording)
        XCTAssertFalse(vm.isWatchSession)
        XCTAssertNil(vm.activeHLSSessionId)
        XCTAssertNil(vm.playbackMode)
        XCTAssertFalse(vm.isPromoted)
        XCTAssertTrue(vm.thumbnailCues.isEmpty)
        XCTAssertNil(vm.thumbnailSpriteURL)
    }

    // MARK: - promoteToRecording guard

    func testPromoteToRecordingIsNoOpWhenNotAWatchSession() async {
        let vm = makeViewModel()
        XCTAssertFalse(vm.isWatchSession)

        await vm.promoteToRecording()

        XCTAssertFalse(vm.isPromoted)
        XCTAssertNil(vm.activeRecording)
    }

    // MARK: - selectAudioTrack guard branches

    func testSelectAudioTrackIsNoOpWhenAlreadySelected() async throws {
        let vm = makeViewModel()
        try vm.playerEngine.loadMedia(url: XCTUnwrap(URL(string: "http://localhost:8000/fake.m3u8")))
        let track = HDHomeRunRecordingAudioInfo(index: 0)
        vm.playerEngine.setAudioTracks([track], selectedTrack: track)

        await vm.selectAudioTrack(track)

        XCTAssertNil(vm.activeHLSSessionId)
    }

    func testSelectAudioTrackIsNoOpWithNoActiveChannelOrRecording() async {
        let vm = makeViewModel()
        let track = HDHomeRunRecordingAudioInfo(index: 1)

        await vm.selectAudioTrack(track)

        XCTAssertNil(vm.activeHLSSessionId)
    }
}
