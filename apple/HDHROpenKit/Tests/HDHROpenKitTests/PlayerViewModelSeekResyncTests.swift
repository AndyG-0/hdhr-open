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
