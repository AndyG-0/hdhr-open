import HDHROpenKit
import SwiftUI

public struct TVMultiViewGrid: View {
    /// Sentinel `slotFocus`/`focusedSlotIndex` value for the persistent Options button, so it
    /// shares the same focus-index plumbing as the numbered quadrants instead of needing a
    /// separate FocusState type.
    static let optionsFocusIndex = -1

    let slots: [MultiViewSlot]
    let layout: MultiViewLayout
    let activeSlotIndex: Int
    @Binding var focusedSlotIndex: Int?

    let onSlotSelect: (Int) -> Void
    let onAddSlot: () -> Void
    let onOpenOptions: () -> Void
    let onSwapWithHero: (Int) -> Void
    let onCloseSlot: (Int) -> Void

    @FocusState private var slotFocus: Int?
    /// Which slot's options dialog (Make Primary / Close Slot) is showing, if any.
    @State private var tileOptionsIndex: Int?

    /// Distinct `slotFocus` sentinel per tile's options button, so it can be
    /// focused independently of the tile's own select-button (`index`) and
    /// the page-level options button (`optionsFocusIndex`). Negative and
    /// disjoint from both, so `TVMultiPlayerView`'s
    /// `slots.indices.contains(index)` guard on `focusedSlotIndex` changes
    /// correctly ignores it rather than mistaking it for a real slot index.
    private static func tileOptionsFocusIndex(_ index: Int) -> Int {
        -(index + 2)
    }

    public init(
        slots: [MultiViewSlot],
        layout: MultiViewLayout,
        activeSlotIndex: Int,
        focusedSlotIndex: Binding<Int?>,
        onSlotSelect: @escaping (Int) -> Void,
        onAddSlot: @escaping () -> Void,
        onOpenOptions: @escaping () -> Void,
        onSwapWithHero: @escaping (Int) -> Void,
        onCloseSlot: @escaping (Int) -> Void
    ) {
        self.slots = slots
        self.layout = layout
        self.activeSlotIndex = activeSlotIndex
        _focusedSlotIndex = focusedSlotIndex
        self.onSlotSelect = onSlotSelect
        self.onAddSlot = onAddSlot
        self.onOpenOptions = onOpenOptions
        self.onSwapWithHero = onSwapWithHero
        self.onCloseSlot = onCloseSlot
    }

    public var body: some View {
        // The options button used to be a ZStack overlay pinned to the grid's top-trailing
        // corner. On-device that made it unreachable with the Siri Remote: its frame sat
        // entirely inside the quadrant Buttons' geometry underneath it, so the tvOS focus
        // engine's directional search never picked it as a candidate - every arrow press just
        // moved between the video tiles. A real sibling row above the grid, with each row in
        // its own `.focusSection()`, gives the focus engine unambiguous geometry: "up" from the
        // top tiles enters the button's section, "down" from the button returns to whichever
        // tile was last focused (the section's default focus-restore behavior).
        VStack(spacing: 20) {
            HStack {
                Spacer()
                optionsButton
            }
            .focusSection()

            Group {
                switch layout {
                case .sideBySide:
                    sideBySideLayout
                case .threeBox:
                    threeBoxLayout
                case .quad:
                    quadLayout
                }
            }
            .focusSection()
        }
        .padding(32)
        .animation(.easeInOut(duration: 0.3), value: layout)
        .animation(.easeInOut(duration: 0.25), value: slots.count)
        .onChange(of: slotFocus) { _, newFocus in
            focusedSlotIndex = newFocus
        }
        .onChange(of: focusedSlotIndex) { _, newIndex in
            if slotFocus != newIndex {
                slotFocus = newIndex
            }
        }
        .onAppear {
            if slotFocus == nil {
                slotFocus = activeSlotIndex
            }
        }
    }

    // MARK: - Options Button

    private var optionsButton: some View {
        Button(action: onOpenOptions) {
            Image(systemName: "ellipsis.circle.fill")
                .font(.system(size: 32))
                .foregroundColor(.white)
                .padding(14)
                .background(Color.black.opacity(0.55))
                .clipShape(Circle())
        }
        .buttonStyle(.plain)
        .focused($slotFocus, equals: Self.optionsFocusIndex)
    }

    // MARK: - Layouts

    private var sideBySideLayout: some View {
        HStack(spacing: 24) {
            slotView(at: 0)

            if slots.count > 1 {
                slotView(at: 1)
            } else {
                emptySlotView(at: 1)
            }
        }
    }

    private var threeBoxLayout: some View {
        HStack(spacing: 24) {
            // Large Hero tile on left
            slotView(at: 0)
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            // Two stacked tiles on right
            VStack(spacing: 24) {
                if slots.count > 1 {
                    slotView(at: 1)
                } else {
                    emptySlotView(at: 1)
                }

                if slots.count > 2 {
                    slotView(at: 2)
                } else {
                    emptySlotView(at: 2)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var quadLayout: some View {
        VStack(spacing: 24) {
            HStack(spacing: 24) {
                slotView(at: 0)

                if slots.count > 1 {
                    slotView(at: 1)
                } else {
                    emptySlotView(at: 1)
                }
            }

            HStack(spacing: 24) {
                if slots.count > 2 {
                    slotView(at: 2)
                } else {
                    emptySlotView(at: 2)
                }

                if slots.count > 3 {
                    slotView(at: 3)
                } else {
                    emptySlotView(at: 3)
                }
            }
        }
    }

    // MARK: - Slot Views

    @ViewBuilder
    private func slotView(at index: Int) -> some View {
        if slots.indices.contains(index) {
            let slot = slots[index]
            // The tile options button used to live in a long-press `.contextMenu` on the tile
            // itself - undiscoverable (no visible affordance) and, per this file's header
            // comment on the page-level options button, a button placed *inside* the tile
            // Button's own geometry is unreachable by tvOS's directional focus search anyway.
            // A slim header row above the video, in its own `.focusSection()`, gives the same
            // non-overlapping-geometry fix the page-level button already relies on.
            VStack(spacing: 8) {
                HStack {
                    Spacer()
                    tileOptionsButton(for: index)
                }
                .focusSection()

                Button(action: {
                    onSlotSelect(index)
                }) {
                    ZStack {
                        Color.black

                        if let player = slot.playerEngine.avPlayer {
                            PlayerLayerView(player: player)
                        }

                        TVMultiViewSlotOverlay(
                            slot: slot,
                            isFocused: slotFocus == index,
                            isActiveAudio: activeSlotIndex == index
                        )
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                }
                .buttonStyle(.plain)
                .focused($slotFocus, equals: index)
            }
            .confirmationDialog(
                "Tile Options",
                isPresented: Binding(
                    get: { tileOptionsIndex == index },
                    set: {
                        if !$0 {
                            tileOptionsIndex = nil
                        }
                    }
                ),
                titleVisibility: .visible
            ) {
                if index != 0 {
                    Button("Make Primary (Hero)") {
                        onSwapWithHero(index)
                    }
                }
                Button("Close Slot", role: .destructive) {
                    onCloseSlot(index)
                }
            }
        } else {
            emptySlotView(at: index)
        }
    }

    private func tileOptionsButton(for index: Int) -> some View {
        Button(action: {
            tileOptionsIndex = index
        }) {
            Image(systemName: "ellipsis.circle.fill")
                .font(.system(size: 22))
                .foregroundColor(.white)
                .padding(8)
                .background(Color.black.opacity(0.55))
                .clipShape(Circle())
        }
        .buttonStyle(.plain)
        .focused($slotFocus, equals: Self.tileOptionsFocusIndex(index))
        .accessibilityIdentifier("tileOptions_\(index)")
        .accessibilityLabel("Tile options")
    }

    private func emptySlotView(at index: Int) -> some View {
        Button(action: onAddSlot) {
            ZStack {
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color.white.opacity(0.08))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .strokeBorder(
                                slotFocus == index ? Color.white : Color.white.opacity(0.2),
                                lineWidth: slotFocus == index ? 5 : 2
                            )
                    )

                VStack(spacing: 12) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.white.opacity(0.8))
                    Text("Add Feed")
                        .font(.headline)
                        .foregroundColor(.white.opacity(0.8))
                }
            }
        }
        .buttonStyle(.plain)
        .focused($slotFocus, equals: index)
    }
}
