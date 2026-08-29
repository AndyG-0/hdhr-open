import SwiftUI
import HDHROpenKit

public struct TVChannelSwitcherOverlay: View {
    let channels: [HDHomeRunChannel]
    let currentChannel: HDHomeRunChannel?
    let onSelectChannel: (HDHomeRunChannel) -> Void
    let onDismiss: () -> Void

    @FocusState private var focusedChannelNumber: String?

    public init(
        channels: [HDHomeRunChannel],
        currentChannel: HDHomeRunChannel?,
        onSelectChannel: @escaping (HDHomeRunChannel) -> Void,
        onDismiss: @escaping () -> Void
    ) {
        self.channels = channels
        self.currentChannel = currentChannel
        self.onSelectChannel = onSelectChannel
        self.onDismiss = onDismiss
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Quick Channel Switcher")
                    .font(.headline)
                    .foregroundColor(.white.opacity(0.8))

                Spacer()

                Button("Dismiss", action: onDismiss)
                    .font(.caption)
            }
            .padding(.horizontal, 32)

            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 16) {
                    ForEach(channels) { ch in
                        let isCurrent = ch.channelNumber == currentChannel?.channelNumber

                        Button(action: {
                            onSelectChannel(ch)
                        }) {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(ch.channelNumber)
                                        .font(.title3.bold())
                                        .foregroundColor(isCurrent ? .blue : .white)
                                        .lineLimit(1)

                                    if ch.isHD {
                                        Text("HD")
                                            .font(.system(size: 9, weight: .bold))
                                            .padding(.horizontal, 4)
                                            .background(Color.blue.opacity(0.6))
                                            .cornerRadius(2)
                                    }
                                }

                                Text(ch.name)
                                    .font(.caption.bold())
                                    .foregroundColor(.white)
                                    .lineLimit(1)

                                if let now = ch.now {
                                    Text(now.title)
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                        .lineLimit(1)
                                }
                            }
                            .padding(12)
                            .frame(width: 180, height: 140)
                            .background(isCurrent ? Color.blue.opacity(0.2) : Color(white: 0.15))
                            .cornerRadius(10)
                            .overlay(
                                RoundedRectangle(cornerRadius: 10)
                                    .stroke(focusedChannelNumber == ch.channelNumber ? Color.white : Color.clear, lineWidth: 3)
                            )
                        }
                        .buttonStyle(.plain)
                        .focused($focusedChannelNumber, equals: ch.channelNumber)
                    }
                }
                .padding(.horizontal, 32)
                .padding(.vertical, 8)
            }
        }
        .padding(.vertical, 16)
        .background(Color.black.opacity(0.85))
        // See TVPlayerSettingsOverlay - this overlay is added as a ZStack
        // sibling on top of the still-mounted player controls, so focus
        // doesn't move onto it automatically when it appears.
        .onAppear {
            focusedChannelNumber = currentChannel?.channelNumber ?? channels.first?.channelNumber
        }
    }
}
