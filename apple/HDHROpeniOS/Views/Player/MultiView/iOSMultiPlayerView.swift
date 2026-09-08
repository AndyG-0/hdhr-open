import HDHROpenKit
import SwiftUI

public struct iOSMultiPlayerView: View {
    @EnvironmentObject private var multiPlayerViewModel: MultiPlayerViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var guideViewModel: GuideViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var showChannelSheet = false
    @State private var targetSlotIndexForChannelChange: Int?

    public init() {}

    public var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                // Top Navigation Bar
                topBar
                    .padding(.horizontal, 20)
                    .padding(.vertical, 12)
                    .background(Color.black.opacity(0.85))

                // Main Multi-View Grid
                mainGrid
                    .padding(16)
            }
        }
        .sheet(isPresented: $showChannelSheet) {
            channelPickerSheet
        }
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack(spacing: 16) {
            // Close / Exit Button
            Button(action: {
                multiPlayerViewModel.closeAll()
                dismiss()
            }) {
                HStack(spacing: 6) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title2)
                    Text("Done")
                        .font(.headline)
                }
                .foregroundColor(.white)
            }

            Spacer()

            // Header Title
            VStack(spacing: 2) {
                Text("Multi-View")
                    .font(.headline)
                    .foregroundColor(.white)
                Text("\(multiPlayerViewModel.slots.count) of \(MultiPlayerViewModel.maxFeeds) Feeds Active")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            Spacer()

            // Layout Picker Menu
            Menu {
                Button {
                    multiPlayerViewModel.layout = .sideBySide
                } label: {
                    Label("Side by Side (2)", systemImage: "rectangle.split.2x1")
                }

                Button {
                    multiPlayerViewModel.layout = .threeBox
                } label: {
                    Label("Three-Box (3)", systemImage: "rectangle.split.3x1")
                }

                Button {
                    multiPlayerViewModel.layout = .quad
                } label: {
                    Label("Quad Grid (4)", systemImage: "rectangle.split.2x2")
                }
            } label: {
                Image(systemName: "square.grid.2x2")
                    .font(.title3)
                    .foregroundColor(.white)
            }

            // Add Feed Button
            if multiPlayerViewModel.canAddFeed {
                Button(action: {
                    targetSlotIndexForChannelChange = nil
                    showChannelSheet = true
                }) {
                    Image(systemName: "plus.circle.fill")
                        .font(.title2)
                        .foregroundColor(.blue)
                }
            }
        }
    }

    // MARK: - Main Grid

    private var mainGrid: some View {
        Group {
            switch multiPlayerViewModel.layout {
            case .sideBySide:
                sideBySideGrid
            case .threeBox:
                threeBoxGrid
            case .quad:
                quadGrid
            }
        }
        .animation(.easeInOut(duration: 0.25), value: multiPlayerViewModel.layout)
        .animation(.easeInOut(duration: 0.25), value: multiPlayerViewModel.slots.count)
    }

    private var sideBySideGrid: some View {
        HStack(spacing: 12) {
            tileView(at: 0)
            if multiPlayerViewModel.slots.count > 1 {
                tileView(at: 1)
            } else {
                emptyTileView(at: 1)
            }
        }
    }

    private var threeBoxGrid: some View {
        HStack(spacing: 12) {
            tileView(at: 0)
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            VStack(spacing: 12) {
                if multiPlayerViewModel.slots.count > 1 {
                    tileView(at: 1)
                } else {
                    emptyTileView(at: 1)
                }

                if multiPlayerViewModel.slots.count > 2 {
                    tileView(at: 2)
                } else {
                    emptyTileView(at: 2)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var quadGrid: some View {
        VStack(spacing: 12) {
            HStack(spacing: 12) {
                tileView(at: 0)
                if multiPlayerViewModel.slots.count > 1 {
                    tileView(at: 1)
                } else {
                    emptyTileView(at: 1)
                }
            }

            HStack(spacing: 12) {
                if multiPlayerViewModel.slots.count > 2 {
                    tileView(at: 2)
                } else {
                    emptyTileView(at: 2)
                }

                if multiPlayerViewModel.slots.count > 3 {
                    tileView(at: 3)
                } else {
                    emptyTileView(at: 3)
                }
            }
        }
    }

    // MARK: - Tile Views

    @ViewBuilder
    private func tileView(at index: Int) -> some View {
        if multiPlayerViewModel.slots.indices.contains(index) {
            let slot = multiPlayerViewModel.slots[index]
            let isActiveAudio = multiPlayerViewModel.activeSlotIndex == index

            ZStack {
                Color.black

                if let player = slot.playerEngine.avPlayer {
                    PlayerLayerView(player: player)
                }

                // Overlay
                slotOverlay(for: slot, index: index, isActiveAudio: isActiveAudio)
            }
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(isActiveAudio ? Color.cyan : Color.white.opacity(0.15), lineWidth: isActiveAudio ? 3 : 1)
            )
            .contentShape(Rectangle())
            .onTapGesture {
                multiPlayerViewModel.setAudioSlot(index: index)
            }
            .contextMenu {
                Button {
                    expandToFullScreen(at: index)
                } label: {
                    Label("Expand to Full Screen", systemImage: "arrow.up.left.and.arrow.down.right")
                }

                if index != 0 {
                    Button {
                        multiPlayerViewModel.swapSlots(from: index, to: 0)
                    } label: {
                        Label("Make Primary (Hero)", systemImage: "star")
                    }
                }

                Button {
                    targetSlotIndexForChannelChange = index
                    showChannelSheet = true
                } label: {
                    Label("Change Channel", systemImage: "arrow.triangle.2.circlepath")
                }

                Button(role: .destructive) {
                    multiPlayerViewModel.removeFeed(at: index)
                } label: {
                    Label("Close Feed", systemImage: "xmark.circle")
                }
            }
        } else {
            emptyTileView(at: index)
        }
    }

    private func emptyTileView(at index: Int) -> some View {
        Button(action: {
            targetSlotIndexForChannelChange = nil
            showChannelSheet = true
        }) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.white.opacity(0.06))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .strokeBorder(Color.white.opacity(0.15), lineWidth: 1)
                    )

                VStack(spacing: 8) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 36))
                        .foregroundColor(.blue)
                    Text("Add Channel")
                        .font(.caption.bold())
                        .foregroundColor(.white.opacity(0.8))
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func slotOverlay(for slot: MultiViewSlot, index: Int, isActiveAudio: Bool) -> some View {
        VStack {
            // Top badges
            HStack {
                HStack(spacing: 6) {
                    Text(slot.channel.channelNumber)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                    Text(slot.channel.name)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white.opacity(0.85))
                        .lineLimit(1)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.black.opacity(0.75))
                .cornerRadius(6)

                Spacer()

                // Audio Badge
                HStack(spacing: 4) {
                    Image(systemName: isActiveAudio ? "speaker.wave.3.fill" : "speaker.slash.fill")
                        .font(.caption2)
                        .foregroundColor(isActiveAudio ? .green : .white.opacity(0.5))
                    if isActiveAudio {
                        Text("AUDIO")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.green)
                    }
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 3)
                .background(Color.black.opacity(0.75))
                .cornerRadius(6)
            }
            .padding(8)

            Spacer()

            // Loading / Error
            if case let .failed(msg) = slot.playerEngine.state {
                Text(msg)
                    .font(.caption2)
                    .foregroundColor(.yellow)
                    .padding(6)
                    .background(Color.black.opacity(0.8))
                    .cornerRadius(6)
            } else if slot.playerEngine.state == .loading || slot.playerEngine.state == .buffering {
                ProgressView()
                    .tint(.white)
            }

            Spacer()

            // Bottom info
            HStack {
                if let airing = slot.airing {
                    Text(airing.title)
                        .font(.caption.bold())
                        .foregroundColor(.white)
                        .lineLimit(1)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.black.opacity(0.75))
                        .cornerRadius(6)
                }

                Spacer()

                if let warning = slot.warningMessage {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.yellow)
                        .font(.caption)
                        .padding(4)
                        .background(Color.black.opacity(0.8))
                        .cornerRadius(4)
                }
            }
            .padding(8)
        }
    }

    // MARK: - Channel Picker Sheet

    private var channelPickerSheet: some View {
        NavigationStack {
            List(guideViewModel.channels) { channel in
                Button(action: {
                    selectChannel(channel)
                }) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(channel.channelNumber)
                                    .font(.headline)
                                    .foregroundColor(.blue)
                                Text(channel.name)
                                    .font(.headline)
                            }
                            if let now = channel.now {
                                Text(now.title)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        Spacer()
                        if channel.isHD {
                            Text("HD")
                                .font(.caption2.bold())
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background(Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(3)
                        }
                    }
                }
                .foregroundColor(.primary)
            }
            .navigationTitle(targetSlotIndexForChannelChange == nil ? "Add Channel Feed" : "Change Channel")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") {
                        showChannelSheet = false
                    }
                }
            }
        }
    }

    private func selectChannel(_ channel: HDHomeRunChannel) {
        showChannelSheet = false
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
}
