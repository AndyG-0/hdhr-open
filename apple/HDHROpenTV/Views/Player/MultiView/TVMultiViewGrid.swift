import HDHROpenKit
import SwiftUI

public struct TVMultiViewGrid: View {
    let slots: [MultiViewSlot]
    let layout: MultiViewLayout
    let activeSlotIndex: Int
    @Binding var focusedSlotIndex: Int?

    let onSlotSelect: (Int) -> Void
    let onAddSlot: () -> Void
    let onExpandToFullScreen: (Int) -> Void
    let onSwapWithHero: (Int) -> Void
    let onCloseSlot: (Int) -> Void

    @FocusState private var slotFocus: Int?

    public init(
        slots: [MultiViewSlot],
        layout: MultiViewLayout,
        activeSlotIndex: Int,
        focusedSlotIndex: Binding<Int?>,
        onSlotSelect: @escaping (Int) -> Void,
        onAddSlot: @escaping () -> Void,
        onExpandToFullScreen: @escaping (Int) -> Void,
        onSwapWithHero: @escaping (Int) -> Void,
        onCloseSlot: @escaping (Int) -> Void
    ) {
        self.slots = slots
        self.layout = layout
        self.activeSlotIndex = activeSlotIndex
        self._focusedSlotIndex = focusedSlotIndex
        self.onSlotSelect = onSlotSelect
        self.onAddSlot = onAddSlot
        self.onExpandToFullScreen = onExpandToFullScreen
        self.onSwapWithHero = onSwapWithHero
        self.onCloseSlot = onCloseSlot
    }

    public var body: some View {
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
            .contextMenu {
                Button {
                    onExpandToFullScreen(index)
                } label: {
                    Label("Expand to Full Screen", systemImage: "arrow.up.left.and.arrow.down.right")
                }

                if index != 0 {
                    Button {
                        onSwapWithHero(index)
                    } label: {
                        Label("Make Primary (Hero)", systemImage: "star")
                    }
                }

                Button(role: .destructive) {
                    onCloseSlot(index)
                } label: {
                    Label("Close Slot", systemImage: "xmark.circle")
                }
            }
        } else {
            emptySlotView(at: index)
        }
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
