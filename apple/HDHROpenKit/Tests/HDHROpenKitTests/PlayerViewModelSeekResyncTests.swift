import XCTest
@testable import HDHROpenKit

@MainActor
final class PlayerViewModelSeekResyncTests: XCTestCase {
    private func makeSeekableViewModel() -> PlayerViewModel {
        let apiClient = APIClient(baseURL: URL(string: "http://localhost:8000")!)
        let vm = PlayerViewModel(apiClient: apiClient, watchSessionManager: WatchSessionManager(apiClient: apiClient))
        // Puts PlayerEngine into a seekable state (mirroring what
        // playChannel/playRecording do in production) without depending on
        // the fake URL actually resolving - `seek`/`isSeekable` are set
        // synchronously inside `loadMedia`, before any real network I/O.
        vm.playerEngine.loadMedia(url: URL(string: "http://localhost:8000/fake.m3u8")!, isSeekable: true)
        return vm
    }

    private func inProgressRecording(startedSecondsAgo: Double) -> HDHomeRunRecording {
        let now = Date().timeIntervalSince1970
        return HDHomeRunRecording(
            recordingId: "rec-in-progress",
            sessionId: nil,
            playlistUrl: nil,
            seriesId: nil,
            title: "In Progress Recording",
            episodeTitle: nil,
            seasonNumber: nil,
            episodeNumber: nil,
            synopsis: nil,
            channelNumber: nil,
            channelName: nil,
            start: now - startedSecondsAgo,
            recordEnd: now + 3600,
            playUrl: "http://hdhr/rec.mpg",
            imageUrl: nil,
            durationSeconds: nil,
            fileSizeBytes: nil,
            hasCaptions: true,
            videoCodec: nil,
            videoWidth: nil,
            videoHeight: nil,
            audioCodec: nil,
            audioChannels: nil,
            originalAirDate: nil,
            category: nil,
            categoryType: nil,
            isDvrFile: nil,
            provider: nil
        )
    }

    private func finishedRecording() -> HDHomeRunRecording {
        let now = Date().timeIntervalSince1970
        return HDHomeRunRecording(
            recordingId: "rec-finished",
            sessionId: nil,
            playlistUrl: nil,
            seriesId: nil,
            title: "Finished Recording",
            episodeTitle: nil,
            seasonNumber: nil,
            episodeNumber: nil,
            synopsis: nil,
            channelNumber: nil,
            channelName: nil,
            start: now - 3600,
            recordEnd: now - 10,
            playUrl: "http://hdhr/rec2.mpg",
            imageUrl: nil,
            durationSeconds: nil,
            fileSizeBytes: nil,
            hasCaptions: true,
            videoCodec: nil,
            videoWidth: nil,
            videoHeight: nil,
            audioCodec: nil,
            audioChannels: nil,
            originalAirDate: nil,
            category: nil,
            categoryType: nil,
            isDvrFile: nil,
            provider: nil
        )
    }

    func testSeekOnInProgressRecordingResyncsCaptionsImmediatelyWithoutWaitingForPoll() {
        let vm = makeSeekableViewModel()
        let recording = inProgressRecording(startedSecondsAgo: 100)
        vm.activeRecording = recording
        // Already behind live at player time 0 - not yet aligned/stretched.
        vm.lastRawCues = [CaptionCue(start: 95, end: 98, text: "Hello")]
        XCTAssertTrue(vm.captionController.cues.isEmpty)

        vm.seek(to: 50)

        XCTAssertEqual(vm.playerEngine.currentTime, 50)
        XCTAssertEqual(vm.captionController.cues.map(\.text), ["Hello"])
    }

    func testSeekOnFinishedRecordingIsNoOpForCaptions() {
        let vm = makeSeekableViewModel()
        vm.activeRecording = finishedRecording()
        let sentinel = [CaptionCue(start: 0, end: 5, text: "sentinel")]
        vm.captionController.setCues(sentinel)

        vm.seek(to: 30)

        XCTAssertEqual(vm.playerEngine.currentTime, 30)
        XCTAssertEqual(vm.captionController.cues, sentinel)
    }

    func testSeekDoesNotClearOrReStretchAlreadyStretchedCues() {
        let vm = makeSeekableViewModel()
        let recording = inProgressRecording(startedSecondsAgo: 100)
        vm.activeRecording = recording
        vm.lastRawCues = [CaptionCue(start: 95, end: 98, text: "Hello")]

        vm.seek(to: 50)
        let afterFirstSeek = vm.stretchedCueDisplay
        XCTAssertEqual(afterFirstSeek.count, 1)

        vm.seek(to: 80)
        let afterSecondSeek = vm.stretchedCueDisplay

        XCTAssertEqual(afterFirstSeek.count, afterSecondSeek.count)
        for (id, window) in afterFirstSeek {
            guard let secondWindow = afterSecondSeek[id] else {
                XCTFail("missing stretch window for cue \(id) after second seek")
                continue
            }
            XCTAssertEqual(secondWindow.start, window.start)
            XCTAssertEqual(secondWindow.end, window.end)
        }
    }

    func testStretchCursorReAnchorsToNowEachCallInsteadOfDriftingAcrossSeparatePolls() {
        // CC-12 regression test, mirroring web's CC-13 fix/test and
        // Android's CC-11 fix: without resetting nextStretchSlotAbsolute to
        // "now" at the top of every alignLiveCues call, the cursor advances
        // by liveCueStretchSeconds per newly-stretched cue and never resets
        // between separate polls, so a second stale cue arriving on a later
        // poll queues behind the first cue's stale reservation instead of
        // anchoring to its own "now" - a permanent, ever-growing freeze
        // rather than a bounded lag.
        let vm = makeSeekableViewModel()
        let recording = inProgressRecording(startedSecondsAgo: 100)
        vm.activeRecording = recording

        let first = CaptionCue(start: 95, end: 98, text: "First")
        vm.lastRawCues = [first]
        vm.seek(to: 50)
        guard let firstWindow = vm.stretchedCueDisplay[first.id] else {
            XCTFail("expected a stretch window for the first cue")
            return
        }

        // A second stale cue, delivered on what stands in for a *separate*
        // later poll (not the same batch as the first).
        let second = CaptionCue(start: 96, end: 99, text: "Second")
        vm.lastRawCues = [first, second]
        vm.seek(to: 51)
        guard let secondWindow = vm.stretchedCueDisplay[second.id] else {
            XCTFail("expected a stretch window for the second cue")
            return
        }

        // Both should anchor close to their own call's "now" (~100s elapsed
        // capture time), not liveCueStretchSeconds (4s) or more apart.
        XCTAssertEqual(firstWindow.start, secondWindow.start, accuracy: 2.0)
    }

    func testStaleCuesBeyondTheMaxCatchupCapAreLeftUnstretchedInsteadOfQueuedForever() {
        // CC-12: a huge backlog (e.g. first poll after enabling captions
        // mid-show) must not hand out ever-later slots without bound -
        // mirrors web's LIVE_CUE_MAX_CATCHUP_SECONDS cap from CC-13 and
        // Android's liveCueMaxCatchupSeconds from CC-11.
        let vm = makeSeekableViewModel()
        let recording = inProgressRecording(startedSecondsAgo: 100)
        vm.activeRecording = recording

        let cues = (0..<10).map { i in
            CaptionCue(start: 50 + Double(i), end: 52 + Double(i), text: "Line \(i)")
        }
        vm.lastRawCues = cues

        vm.seek(to: 0)

        let displayed = vm.captionController.cues
        let lastDisplayedStart = displayed.map(\.start).max() ?? 0
        // Player-relative start of any displayed cue must stay within the
        // catch-up cap (20s, PlayerViewModel's liveCueMaxCatchupSeconds) of
        // "now" (player position 0) - never queued minutes into the future.
        XCTAssertLessThanOrEqual(lastDisplayedStart, 21.0)
    }

    func testSkipForwardAndSkipBackwardAlsoTriggerCaptionResync() {
        let vm = makeSeekableViewModel()
        let recording = inProgressRecording(startedSecondsAgo: 100)
        vm.activeRecording = recording
        vm.lastRawCues = [CaptionCue(start: 95, end: 98, text: "Hello")]

        vm.skipForward(seconds: 30)
        XCTAssertEqual(vm.playerEngine.currentTime, 30)
        XCTAssertEqual(vm.captionController.cues.map(\.text), ["Hello"])

        vm.skipBackward(seconds: 10)
        XCTAssertEqual(vm.playerEngine.currentTime, 20)
        XCTAssertEqual(vm.captionController.cues.map(\.text), ["Hello"])
    }
}
