import SwiftUI
import HDHROpenKit

public struct iOSPlayerView: View {
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var showControls: Bool = true
    @State private var controlsTimer: Task<Void, Never>?
    @State private var showPlaybackInfo: Bool = false
    @State private var showRecordingOptionsSheet: Bool = false

    public init() {}

    public var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            // Video Player
            if let avPlayer = playerViewModel.playerEngine.avPlayer {
                PlayerLayerView(player: avPlayer)
                    .ignoresSafeArea()
            }

            // Captions
            if let caption = playerViewModel.captionController.activeCueText {
                VStack {
                    Spacer()
                    Text(caption)
                        .font(.body.bold())
                        .foregroundColor(.yellow)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .background(Color.black.opacity(0.75))
                        .cornerRadius(6)
                        .padding(.bottom, showControls ? 140 : 40)
                }
            }

            // Status / Error Overlay
            if case .failed(let message) = playerViewModel.playerEngine.state {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.yellow)
                    Text("Playback Error")
                        .font(.title3.bold())
                        .foregroundColor(.white)
                    Text(message)
                        .font(.callout)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                    Button(action: {
                        playerViewModel.closePlayer()
                        dismiss()
                    }) {
                        Text("Close")
                            .font(.callout.bold())
                            .padding(.horizontal, 20)
                            .padding(.vertical, 8)
                            .background(Color.white.opacity(0.2))
                            .cornerRadius(8)
                            .foregroundColor(.white)
                    }
                }
                .padding(32)
                .background(Color.black.opacity(0.85))
                .cornerRadius(16)
                .padding(.horizontal, 32)
            } else if playerViewModel.playerEngine.state == .loading || playerViewModel.playerEngine.state == .buffering {
                ProgressView()
                    .scaleEffect(1.5)
                    .tint(.white)
            }

            // Controls Overlay
            if showControls {
                VStack {
                    // Top Navigation Bar
                    HStack(alignment: .top) {
                        Button(action: {
                            playerViewModel.closePlayer()
                            dismiss()
                        }) {
                            Image(systemName: "chevron.backward.circle.fill")
                                .font(.title)
                                .foregroundColor(.white)
                        }

                        VStack(alignment: .leading, spacing: 2) {
                            Text(playerViewModel.mediaTitle)
                                .font(.headline.bold())
                                .foregroundColor(.white)
                                .lineLimit(1)

                            if let sub = playerViewModel.mediaSubtitle {
                                Text(sub)
                                    .font(.caption)
                                    .foregroundColor(.white.opacity(0.8))
                                    .lineLimit(1)
                            }
                        }
                        .padding(.leading, 8)

                        Spacer()

                        // Playback Info Button
                        Button(action: {
                            showPlaybackInfo = true
                        }) {
                            Image(systemName: "info.circle")
                                .font(.title3)
                                .foregroundColor(.white)
                        }
                        .padding(.trailing, 8)

                        // Captions Button
                        Button(action: {
                            playerViewModel.captionController.isEnabled.toggle()
                        }) {
                            Image(systemName: playerViewModel.captionController.isEnabled ? "captions.bubble.fill" : "captions.bubble")
                                .font(.title3)
                                .foregroundColor(playerViewModel.captionController.isEnabled ? .yellow : .white)
                        }

                        // AirPlay Route Picker
                        AirPlayRoutePickerView()
                            .frame(width: 24, height: 24)
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 16)

                    Spacer()

                    // Center Play / Skip Controls
                    HStack(spacing: 48) {
                        if playerViewModel.playerEngine.isSeekable {
                            Button(action: { playerViewModel.skipBackward(seconds: 10) }) {
                                Image(systemName: "gobackward.10")
                                    .font(.system(size: 32))
                                    .foregroundColor(.white)
                            }
                        }

                        Button(action: { playerViewModel.playerEngine.togglePlayPause() }) {
                            Image(systemName: playerViewModel.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                                .font(.system(size: 64))
                                .foregroundColor(.white)
                        }

                        if playerViewModel.playerEngine.isSeekable {
                            Button(action: { playerViewModel.skipForward(seconds: 10) }) {
                                Image(systemName: "goforward.10")
                                    .font(.system(size: 32))
                                    .foregroundColor(.white)
                            }
                        }
                    }

                    Spacer()

                    // Bottom Timeline & Actions
                    VStack(spacing: 12) {
                        iOSScrubBarView(
                            currentTime: playerViewModel.playerEngine.currentTime,
                            duration: playerViewModel.playerEngine.duration,
                            isLive: playerViewModel.playerEngine.isLive,
                            isSeekable: playerViewModel.playerEngine.isSeekable,
                            thumbnailCues: playerViewModel.thumbnailCues,
                            spriteURL: playerViewModel.thumbnailSpriteURL,
                            onSeek: { target in
                                playerViewModel.seek(to: target)
                            }
                        )

                        HStack {
                            if playerViewModel.isWatchSession {
                                let existingRule = guideViewModel.findRule(for: playerViewModel.activeChannel?.channelNumber, airing: playerViewModel.activeAiring)
                                let canRecordSeries = !(playerViewModel.activeAiring?.seriesId?.isEmpty ?? true) || !(playerViewModel.activeAiring?.title.isEmpty ?? true)

                                Menu {
                                    if let rule = existingRule {
                                        Button(role: .destructive) {
                                            Task { try? await guideViewModel.cancelRule(ruleId: rule.recordingRuleId) }
                                        } label: {
                                            Label("Cancel Recording", systemImage: "record.circle")
                                        }
                                    } else {
                                        Button {
                                            Task { await playerViewModel.promoteToRecording() }
                                        } label: {
                                            Label(playerViewModel.isPromoted ? "Recording Saved" : "Save Current Recording", systemImage: "checkmark.circle")
                                        }
                                        .disabled(playerViewModel.isPromoting || playerViewModel.isPromoted)

                                        Button {
                                            Task {
                                                try? await guideViewModel.recordEpisode(
                                                    seriesId: playerViewModel.activeAiring?.seriesId,
                                                    channelNumber: playerViewModel.activeChannel?.channelNumber,
                                                    start: playerViewModel.activeAiring?.start
                                                )
                                            }
                                        } label: {
                                            Label("Record Episode", systemImage: "record.circle")
                                        }

                                        if canRecordSeries {
                                            Button {
                                                Task {
                                                    try? await guideViewModel.recordSeries(
                                                        seriesId: playerViewModel.activeAiring?.seriesId ?? "",
                                                        channelNumber: playerViewModel.activeChannel?.channelNumber
                                                    )
                                                }
                                            } label: {
                                                Label("Record Series", systemImage: "recordingtape")
                                            }
                                        }

                                        Button {
                                            showRecordingOptionsSheet = true
                                        } label: {
                                            Label("Recording Options…", systemImage: "slider.horizontal.3")
                                        }
                                    }
                                } label: {
                                    HStack(spacing: 6) {
                                        Image(systemName: (existingRule != nil || playerViewModel.isPromoted) ? "checkmark.circle.fill" : "record.circle")
                                            .foregroundColor((existingRule != nil || playerViewModel.isPromoted) ? .green : .red)
                                        Text(existingRule != nil ? "Recording Scheduled" : (playerViewModel.isPromoted ? "Recording Saved" : "Record"))
                                            .font(.caption.bold())
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(Color.white.opacity(0.2))
                                    .cornerRadius(8)
                                    .foregroundColor(.white)
                                }
                                .disabled(playerViewModel.isPromoting)
                            }

                            Spacer()

                            if !playerViewModel.playerEngine.availableAudioTracks.isEmpty {
                                Menu {
                                    ForEach(playerViewModel.playerEngine.availableAudioTracks) { track in
                                        let isSelected = playerViewModel.playerEngine.currentAudioTrack?.index == track.index
                                        Button {
                                            Task { await playerViewModel.selectAudioTrack(track) }
                                        } label: {
                                            if isSelected {
                                                Label(track.displayLabel, systemImage: "checkmark")
                                            } else {
                                                Text(track.displayLabel)
                                            }
                                        }
                                    }
                                } label: {
                                    Image(systemName: "waveform.circle")
                                        .font(.title3)
                                        .foregroundColor(.white)
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.bottom, 24)
                }
                .background(
                    LinearGradient(
                        colors: [Color.black.opacity(0.7), Color.clear, Color.black.opacity(0.8)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .ignoresSafeArea()
                )
            }

            if showPlaybackInfo {
                iOSPlaybackInfoOverlay(playerViewModel: playerViewModel, onDismiss: { showPlaybackInfo = false })
            }
        }
        .task {
            if recordingsViewModel.dvrInfo == nil {
                await recordingsViewModel.loadDvrInfo()
            }
        }
        .sheet(isPresented: $showRecordingOptionsSheet) {
            if let channel = playerViewModel.activeChannel, let airing = playerViewModel.activeAiring {
                let existingRule = guideViewModel.findRule(for: channel.channelNumber, airing: airing)
                iOSRecordingOptionsSheet(
                    channel: channel,
                    airing: airing,
                    canRecordSeries: !(airing.seriesId?.isEmpty ?? true) || !airing.title.isEmpty,
                    existingRule: existingRule,
                    onConfirm: { recordSeries, options in
                        Task {
                            if recordSeries {
                                try? await guideViewModel.recordSeries(
                                    seriesId: airing.seriesId ?? "",
                                    channelNumber: channel.channelNumber,
                                    options: options
                                )
                            } else {
                                try? await guideViewModel.recordEpisode(
                                    seriesId: airing.seriesId,
                                    channelNumber: channel.channelNumber,
                                    start: airing.start,
                                    options: options
                                )
                            }
                            showRecordingOptionsSheet = false
                        }
                    },
                    onCancelRule: existingRule.map { rule in
                        {
                            Task {
                                try? await guideViewModel.cancelRule(ruleId: rule.recordingRuleId)
                                showRecordingOptionsSheet = false
                            }
                        }
                    }
                )
            }
        }
        .onChange(of: playerViewModel.playerEngine.state) { _, newState in
            // The auto-hide countdown must only run once there's actually
            // something playing to hide controls over. Starting it on
            // `onAppear` (as before) meant it was already ticking during
            // session negotiation + startup, which can take longer than the
            // 5s countdown - controls were auto-hidden before playback ever
            // began, leaving nothing but a black/loading screen with no way
            // to reopen them. Mirrors the same fix on TVPlayerView.
            if newState == .playing {
                resetTimer()
            } else {
                controlsTimer?.cancel()
            }
        }
        .onTapGesture {
            withAnimation {
                showControls.toggle()
                if showControls { resetTimer() }
            }
        }
    }

    private func resetTimer() {
        controlsTimer?.cancel()
        controlsTimer = Task {
            try? await Task.sleep(nanoseconds: 5_000_000_000)
            if !Task.isCancelled {
                withAnimation { showControls = false }
            }
        }
    }
}
