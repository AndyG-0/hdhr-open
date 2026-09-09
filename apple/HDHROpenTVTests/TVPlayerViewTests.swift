import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVPlayerViewTests: XCTestCase {
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
        _ multiPlayerViewModel: MultiPlayerViewModel? = nil
    ) -> some View {
        let multiVM = multiPlayerViewModel ?? MultiPlayerViewModel(
            apiClient: APIClient(baseURL: URL(string: "http://localhost:8000")!, session: MockURLProtocol.makeSession()),
            watchSessionManager: WatchSessionManager(apiClient: APIClient(
                baseURL: URL(string: "http://localhost:8000")!,
                session: MockURLProtocol.makeSession()
            ))
        )
        return TVPlayerView()
            .environmentObject(playerViewModel)
            .environmentObject(guideViewModel)
            .environmentObject(recordingsViewModel)
            .environmentObject(multiVM)
    }

    func testShowsLiveTVTitleByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertNil(playerViewModel.activeChannel)
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

    func testIncludesScrubBarAndPlaybackControlsWhenControlsVisible() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()

        // showControls is a private @State defaulting to true.
        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(TVScrubBarView.self))
        XCTAssertNoThrow(try view.inspect().find(TVPlaybackControlsView.self))
    }

    func testShowsCaptionOverlayWhenCaptionControllerHasActiveCue() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        playerViewModel.captionController.setCues([CaptionCue(start: 0, end: 10, text: "Hello Captions")])
        playerViewModel.captionController.isEnabled = true
        playerViewModel.captionController.updatePlaybackTime(0)
        XCTAssertEqual(playerViewModel.captionController.activeCueText, "Hello Captions")

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(text: "Hello Captions"))
    }

    func testHidesChannelSwitcherOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.showChannelSwitcher)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVChannelSwitcherOverlay.self))
    }

    func testHidesSettingsOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.showAudioMenu)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVPlayerSettingsOverlay.self))
    }

    func testHidesSyncPlayOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.showSyncPlaySheet)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVSyncPlayOverlay.self))
    }

    func testHidesRecordMenuOverlayByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()
        XCTAssertFalse(playerViewModel.showRecordMenu)

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertThrowsError(try view.inspect().find(TVPlayerRecordMenuOverlay.self))
    }

    // REV-APL-18: regression coverage for the `.onMoveCommand` "intercepts
    // everything" workaround (see the long comment at TVPlayerView.swift's
    // fallback-focus block, just above `if !showControls`). `.onMoveCommand`
    // is unsupported by ViewInspector on tvOS entirely (confirmed in the
    // vendored ViewInspector's InteractionModifiers.swift), and the 7s
    // auto-hide timer has no injectable clock, so this only tests what's
    // reachable from here: in the default (`showControls == true`) state,
    // no `Color.clear` view is in the tree - confirming the fallback-focus
    // target (`Color.clear.focusable(true).focused($isFallbackFocused)`) is
    // absent and so can't compete with `TVPlaybackControlsView` for focus,
    // which is the whole point of the comment above it being a conditional
    // ZStack child rather than an unconditional modifier. (The other
    // `Color.clear` in this file, in the top gradient's `colors:` array, is a
    // `Gradient` parameter, not a rendered child view, so it isn't part of
    // this search space.) Full remote-input behavior (does a real
    // directional press on the fallback target actually reveal controls)
    // needs on-device verification; `showControls` is private `@State` with
    // no injectable initial value, and - per this codebase's established
    // ViewInspector limitation (see
    // `TVMultiPlayerViewTests.assertTileOptionsButtonIsTappable`'s note) - a
    // `.tap()`-driven `@State` mutation doesn't propagate to a subsequent
    // inspection without `ViewHosting.host(view:)`, which this codebase
    // deliberately avoids, so the post-toggle "fallback view is present when
    // showControls == false" tree shape isn't independently verifiable here.
    func testHidesFallbackFocusTargetWhileControlsAreVisibleByDefault() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(TVPlaybackControlsView.self))
        XCTAssertThrowsError(try view.inspect().find(ViewType.Color.self) { (try? $0.value()) == .clear })
    }

    /// Tapping the view is the only way (short of `ViewHosting`) to exercise
    /// the `.onTapGesture` handler that toggles `showControls` and, when
    /// hiding controls, claims `isFallbackFocused` - confirms the handler is
    /// wired and doesn't throw, per this codebase's established
    /// tap-without-re-inspection convention (see the note above).
    func testTappingPlayerViewDoesNotThrow() throws {
        let (playerViewModel, guideViewModel, recordingsViewModel) = makeEnvironmentObjects()

        let view = makeView(playerViewModel, guideViewModel, recordingsViewModel)

        XCTAssertNoThrow(try view.inspect().find(ViewType.ZStack.self).callOnTapGesture())
    }
}
