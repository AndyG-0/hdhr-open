import HDHROpenKit
import SwiftUI

public struct TVMultiPlayerView: View {
    @EnvironmentObject private var multiPlayerViewModel: MultiPlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel

    @State private var focusedSlotIndex: Int? = 0
    @State private var expandedSlotIndex: Int?
    @State private var showEditBar = false
    @State private var showChannelPicker = false
    @State private var targetSlotIndexForChannelChange: Int?
    @State private var editBarTimer: Task<Void, Never>?

    @FocusState private var editFocus: EditBarFocus?

    let inspection = Inspection<Self>()

    private enum EditBarFocus {
        case done, layout2up, layout3up, layoutQuad, addFeed, closeAll
    }

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
                    expandSlot(at: index)
                },
                onAddSlot: {
                    targetSlotIndexForChannelChange = nil
                    showChannelPicker = true
                },
                onOpenOptions: {
                    showEditBar = true
                    scheduleEditBarAutoHide()
                },
                onSwapWithHero: { index in
                    multiPlayerViewModel.swapSlots(from: index, to: 0)
                    repushFocusToActiveSlot()
                },
                onCloseSlot: { index in
                    multiPlayerViewModel.removeFeed(at: index)
                    repushFocusToActiveSlot()
                }
            )
            // Grid shouldn't take focus/input while something is layered over it - a fullscreen
            // tile, the edit bar, or the channel picker. Merely drawing those on top isn't
            // enough: the grid's Buttons stay in the tvOS focus tree underneath them, and since
            // the edit bar sits close above the top row of tiles, moving focus sideways within
            // the bar can jump down into a tile instead of the next bar button. Disabling the
            // grid removes its buttons from focus consideration entirely while covered.
            .disabled(expandedSlotIndex != nil || showEditBar || showChannelPicker)
            // Dynamic Audio Routing on Focus Change
            .onChange(of: focusedSlotIndex) { _, newIndex in
                if let index = newIndex, multiPlayerViewModel.slots.indices.contains(index) {
                    multiPlayerViewModel.setAudioSlot(index: index)
                }
            }

            // Fullscreen Expanded Tile
            if let expandedIndex = expandedSlotIndex, multiPlayerViewModel.slots.indices.contains(expandedIndex) {
                let slot = multiPlayerViewModel.slots[expandedIndex]
                ZStack {
                    Color.black
                    if let player = slot.playerEngine.avPlayer {
                        PlayerLayerView(player: player)
                    }
                }
                .ignoresSafeArea()
                .transition(.opacity)
            }

            // Edit Bar (layout / add feed / close)
            if showEditBar {
                VStack {
                    editBar
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
        .animation(.easeInOut(duration: 0.25), value: expandedSlotIndex)
        .animation(.easeInOut(duration: 0.25), value: showEditBar)
        .animation(.easeInOut(duration: 0.25), value: showChannelPicker)
        .onExitCommand {
            if expandedSlotIndex != nil {
                collapseExpandedSlot()
            } else if showChannelPicker {
                showChannelPicker = false
            } else if showEditBar {
                closeEditBar()
            } else {
                multiPlayerViewModel.closeAll()
            }
        }
        .task {
            await multiPlayerViewModel.refreshTunerCapacity()
            multiPlayerViewModel.startTunerPolling()
        }
        .onReceive(inspection.notice) { inspection.visit(self, $0) }
    }

    // MARK: - Edit Bar

    private var editBar: some View {
        let allowedLayouts = MultiViewLayout.availableLayouts(for: multiPlayerViewModel.maxFeeds)

        return HStack(spacing: 24) {
            // Feeds count & title
            VStack(alignment: .leading, spacing: 4) {
                Text("Multi-View Playback")
                    .font(.title2.bold())
                    .foregroundColor(.white)
                Text("\(multiPlayerViewModel.slots.count) of \(multiPlayerViewModel.maxFeeds) Feeds Active")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            Spacer()

            // Layout Picker Buttons
            HStack(spacing: 12) {
                if allowedLayouts.contains(.sideBySide) {
                    Button(action: {
                        multiPlayerViewModel.layout = .sideBySide
                        scheduleEditBarAutoHide()
                    }) {
                        Label("2-Up", systemImage: "rectangle.split.2x1")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(multiPlayerViewModel.layout == .sideBySide ? .blue : .gray.opacity(0.3))
                    .focused($editFocus, equals: .layout2up)
                }

                if allowedLayouts.contains(.threeBox), multiPlayerViewModel.slots.count >= 3 || multiPlayerViewModel.canAddFeed {
                    Button(action: {
                        multiPlayerViewModel.layout = .threeBox
                        scheduleEditBarAutoHide()
                    }) {
                        Label("3-Up", systemImage: "rectangle.split.3x1")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(multiPlayerViewModel.layout == .threeBox ? .blue : .gray.opacity(0.3))
                    .focused($editFocus, equals: .layout3up)
                }

                if allowedLayouts.contains(.quad), multiPlayerViewModel.slots.count >= 4 || multiPlayerViewModel.canAddFeed {
                    Button(action: {
                        multiPlayerViewModel.layout = .quad
                        scheduleEditBarAutoHide()
                    }) {
                        Label("Quad", systemImage: "rectangle.split.2x2")
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(multiPlayerViewModel.layout == .quad ? .blue : .gray.opacity(0.3))
                    .focused($editFocus, equals: .layoutQuad)
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
                .focused($editFocus, equals: .addFeed)
            }

            // Done Button
            Button(action: {
                closeEditBar()
            }) {
                Label("Done", systemImage: "checkmark")
            }
            .buttonStyle(.bordered)
            .focused($editFocus, equals: .done)

            // Close All Button
            Button(role: .destructive, action: {
                multiPlayerViewModel.closeAll()
            }) {
                Label("Close Multi-View", systemImage: "xmark")
            }
            .buttonStyle(.bordered)
            .focused($editFocus, equals: .closeAll)
        }
        .padding(28)
        .background(Color.black.opacity(0.85))
        .cornerRadius(20)
        .padding(.horizontal, 48)
        .padding(.top, 24)
        .focusSection()
        // tvOS doesn't retarget focus onto a newly-appeared sibling on its own
        // (see TVPlayerView's isFallbackFocused for the same caveat) - claim it
        // explicitly so arrow keys have somewhere to start from immediately.
        .onAppear {
            editFocus = .done
        }
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

    /// Expands a tile in place to fill the screen, keeping the whole multi-view session
    /// (all slots' player engines and server sessions) alive underneath.
    private func expandSlot(at index: Int) {
        guard multiPlayerViewModel.slots.indices.contains(index) else { return }
        expandedSlotIndex = index
        multiPlayerViewModel.setAudioSlot(index: index)
        multiPlayerViewModel.pauseBackgroundSlots(except: index)
    }

    /// Collapses the fullscreen tile back to the grid and resumes the paused background slots.
    private func collapseExpandedSlot() {
        expandedSlotIndex = nil
        multiPlayerViewModel.resumeBackgroundSlots()
    }

    /// Round-trips `focusedSlotIndex` through nil so `TVMultiViewGrid`'s
    /// two-way sync with tvOS's focus engine re-pushes focus even when
    /// `activeSlotIndex` is unchanged from before the mutation - simply
    /// reassigning the same value doesn't reliably re-push tvOS focus.
    /// Mirrors `closeEditBar()`'s existing idiom, but keyed off
    /// `activeSlotIndex` (already correctly maintained by `removeFeed`/
    /// `swapSlots` for audio routing) rather than the previously-focused
    /// index, since a close/swap can leave that index pointing at a
    /// different slot or none at all.
    private func repushFocusToActiveSlot() {
        let target = multiPlayerViewModel.activeSlotIndex
        focusedSlotIndex = nil
        Task { @MainActor in
            focusedSlotIndex = target
        }
    }

    private func closeEditBar() {
        editBarTimer?.cancel()
        showEditBar = false
        editFocus = nil
        // Round-trip focusedSlotIndex through nil so the grid's onChange fires even when the
        // target index is unchanged from before the bar opened - simply reassigning the same
        // value doesn't reliably re-push tvOS focus onto the matching slot button.
        let target = focusedSlotIndex
        focusedSlotIndex = nil
        Task { @MainActor in
            focusedSlotIndex = target
        }
    }

    private func scheduleEditBarAutoHide() {
        editBarTimer?.cancel()
        editBarTimer = Task {
            try? await Task.sleep(nanoseconds: 6_000_000_000)
            if !Task.isCancelled {
                closeEditBar()
            }
        }
    }
}
