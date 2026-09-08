import HDHROpenKit
import SwiftUI

public struct TVMultiPlayerView: View {
    @EnvironmentObject private var multiPlayerViewModel: MultiPlayerViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel

    @State private var focusedSlotIndex: Int? = 0
    @State private var showControls = false
    @State private var showChannelPicker = false
    @State private var targetSlotIndexForChannelChange: Int?
    @State private var controlsTimer: Task<Void, Never>?

    public init() {}

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            // Main Multi-View Grid
            TVMultiViewGrid(
                slots: multiPlayerViewModel.slots,
                layout: multiPlayerViewModel.layout,
                activeSlotIndex: multiPlayerViewModel.activeSlotIndex,
                focusedSlotIndex: $focusedSlotIndex,
                onSlotSelect: { index in
                    targetSlotIndexForChannelChange = index
                    showControls.toggle()
                    scheduleControlsAutoHide()
                },
                onAddSlot: {
                    targetSlotIndexForChannelChange = nil
                    showChannelPicker = true
                },
                onExpandToFullScreen: { index in
                    expandToFullScreen(at: index)
                },
                onSwapWithHero: { index in
                    multiPlayerViewModel.swapSlots(from: index, to: 0)
                },
                onCloseSlot: { index in
                    multiPlayerViewModel.removeFeed(at: index)
                }
            )

            // Dynamic Audio Routing on Focus Change
            .onChange(of: focusedSlotIndex) { _, newIndex in
                if let index = newIndex, index < multiPlayerViewModel.slots.count {
                    multiPlayerViewModel.setAudioSlot(index: index)
                }
            }

            // Top Overlay Bar (Controls)
            if showControls {
                VStack {
                    topControlsBar
                    Spacer()
                }
                .transition(.move(edge: .top).combined(with: .opacity))
            }

            // Channel Picker Modal / Drawer
            if showChannelPicker {
                channelPickerDrawer
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.easeInOut(duration: 0.25), value: showControls)
        .animation(.easeInOut(duration: 0.25), value: showChannelPicker)
        .onExitCommand {
            if showChannelPicker {
                showChannelPicker = false
            } else if showControls {
                showControls = false
            } else {
                multiPlayerViewModel.closeAll()
            }
        }
    }

    // MARK: - Top Controls Bar

    private var topControlsBar: some View {
        HStack(spacing: 24) {
            // Feeds count & title
            VStack(alignment: .leading, spacing: 4) {
                Text("Multi-View Playback")
                    .font(.title2.bold())
                    .foregroundColor(.white)
                Text("\(multiPlayerViewModel.slots.count) of \(MultiPlayerViewModel.maxFeeds) Feeds Active")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            Spacer()

            // Layout Picker Buttons
            HStack(spacing: 12) {
                Button(action: {
                    multiPlayerViewModel.layout = .sideBySide
                    scheduleControlsAutoHide()
                }) {
                    Label("2-Up", systemImage: "rectangle.split.2x1")
                }
                .buttonStyle(.borderedProminent)
                .tint(multiPlayerViewModel.layout == .sideBySide ? .blue : .gray.opacity(0.3))

                if multiPlayerViewModel.slots.count >= 3 || multiPlayerViewModel.canAddFeed {
                    Button(action: {
                        multiPlayerViewModel.layout = .threeBox
                        scheduleControlsAutoHide()
                    }) {
                        Label("3-Up", systemImage: "rectangle.split.3x1")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(multiPlayerViewModel.layout == .threeBox ? .blue : .gray.opacity(0.3))
                }

                if multiPlayerViewModel.slots.count >= 4 || multiPlayerViewModel.canAddFeed {
                    Button(action: {
                        multiPlayerViewModel.layout = .quad
                        scheduleControlsAutoHide()
                    }) {
                        Label("Quad", systemImage: "rectangle.split.2x2")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(multiPlayerViewModel.layout == .quad ? .blue : .gray.opacity(0.3))
                }
            }

            // Add Feed Button
            if multiPlayerViewModel.canAddFeed {
                Button(action: {
                    targetSlotIndexForChannelChange = nil
                    showChannelPicker = true
                }) {
                    Label("Add Feed", systemImage: "plus")
                }
                .buttonStyle(.bordered)
            }

            // Close All Button
            Button(role: .destructive, action: {
                multiPlayerViewModel.closeAll()
            }) {
                Label("Close Multi-View", systemImage: "xmark")
            }
            .buttonStyle(.bordered)
        }
        .padding(28)
        .background(Color.black.opacity(0.85))
        .cornerRadius(20)
        .padding(.horizontal, 48)
        .padding(.top, 24)
    }

    // MARK: - Channel Picker Drawer

    private var channelPickerDrawer: some View {
        ZStack {
            Color.black.opacity(0.6).ignoresSafeArea()
                .onTapGesture {
                    showChannelPicker = false
                }

            VStack(alignment: .leading, spacing: 20) {
                HStack {
                    Text(targetSlotIndexForChannelChange == nil ? "Select Channel to Add" : "Change Channel for Tile")
                        .font(.title2.bold())
                        .foregroundColor(.white)

                    Spacer()

                    Button("Done") {
                        showChannelPicker = false
                    }
                    .buttonStyle(.bordered)
                }
                .padding(.horizontal, 40)
                .padding(.top, 32)

                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(spacing: 24) {
                        ForEach(guideViewModel.channels) { channel in
                            Button(action: {
                                selectChannel(channel)
                            }) {
                                VStack(alignment: .leading, spacing: 8) {
                                    HStack {
                                        Text(channel.channelNumber)
                                            .font(.title3.bold())
                                            .foregroundColor(.white)
                                        if channel.isHD {
                                            Text("HD")
                                                .font(.system(size: 10, weight: .bold))
                                                .padding(.horizontal, 4)
                                                .padding(.vertical, 2)
                                                .background(Color.blue)
                                                .cornerRadius(4)
                                        }
                                    }

                                    Text(channel.name)
                                        .font(.headline)
                                        .foregroundColor(.white)
                                        .lineLimit(1)

                                    if let now = channel.now {
                                        Text(now.title)
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                            .lineLimit(2)
                                    }
                                }
                                .padding(20)
                                .frame(width: 260, height: 140)
                                .background(Theme.appSurface)
                                .cornerRadius(16)
                            }
                            .buttonStyle(.card)
                        }
                    }
                    .padding(.horizontal, 40)
                    .padding(.bottom, 32)
                }
            }
            .background(Color.black.opacity(0.95))
            .cornerRadius(24)
            .padding(.horizontal, 32)
            .padding(.bottom, 24)
        }
    }

    // MARK: - Actions

    private func selectChannel(_ channel: HDHomeRunChannel) {
        showChannelPicker = false
        Task {
            if let targetIndex = targetSlotIndexForChannelChange {
                try? await multiPlayerViewModel.replaceFeed(at: targetIndex, with: channel)
            } else {
                try? await multiPlayerViewModel.addFeed(channel: channel)
            }
        }
    }

    private func expandToFullScreen(at index: Int) {
        guard multiPlayerViewModel.slots.indices.contains(index) else { return }
        let channel = multiPlayerViewModel.slots[index].channel
        let airing = multiPlayerViewModel.slots[index].airing
        multiPlayerViewModel.closeAll()
        Task {
            await playerViewModel.playChannel(channel: channel, airing: airing)
        }
    }

    private func scheduleControlsAutoHide() {
        controlsTimer?.cancel()
        controlsTimer = Task {
            try? await Task.sleep(nanoseconds: 6_000_000_000)
            if !Task.isCancelled {
                showControls = false
            }
        }
    }
}
