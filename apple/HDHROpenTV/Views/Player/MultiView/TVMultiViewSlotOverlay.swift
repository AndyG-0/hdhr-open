import HDHROpenKit
import SwiftUI

public struct TVMultiViewSlotOverlay: View {
    let slot: MultiViewSlot
    let isFocused: Bool
    let isActiveAudio: Bool

    public init(
        slot: MultiViewSlot,
        isFocused: Bool,
        isActiveAudio: Bool
    ) {
        self.slot = slot
        self.isFocused = isFocused
        self.isActiveAudio = isActiveAudio
    }

    public var body: some View {
        ZStack {
            // Focus outline
            RoundedRectangle(cornerRadius: 16)
                .strokeBorder(
                    isFocused ? Color.white : (isActiveAudio ? Color.cyan.opacity(0.6) : Color.clear),
                    lineWidth: isFocused ? 5 : 2
                )
                .shadow(color: isFocused ? Color.white.opacity(0.4) : Color.clear, radius: 10)

            // Content Overlay
            VStack(alignment: .leading, spacing: 0) {
                // Top Badges
                HStack(alignment: .top) {
                    // Channel badge
                    HStack(spacing: 8) {
                        Text(slot.channel.channelNumber)
                            .font(.system(size: 20, weight: .bold, design: .rounded))
                            .foregroundColor(.white)

                        Text(slot.channel.name)
                            .font(.system(size: 16, weight: .medium))
                            .foregroundColor(.white.opacity(0.9))
                            .lineLimit(1)

                        if slot.channel.isHD {
                            Text("HD")
                                .font(.system(size: 10, weight: .bold))
                                .padding(.horizontal, 5)
                                .padding(.vertical, 2)
                                .background(Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(4)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.black.opacity(0.75))
                    .cornerRadius(10)

                    Spacer()

                    // Audio Indicator
                    HStack(spacing: 6) {
                        Image(systemName: isActiveAudio ? "speaker.wave.3.fill" : "speaker.slash.fill")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(isActiveAudio ? .green : .white.opacity(0.6))

                        if isActiveAudio {
                            Text("AUDIO")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundColor(.green)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.black.opacity(0.75))
                    .cornerRadius(10)
                }
                .padding(14)

                Spacer()

                // Center spinner or error
                if case let .failed(msg) = slot.playerEngine.state {
                    HStack(alignment: .top, spacing: 14) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.title2)
                            .foregroundColor(.yellow)
                        Text(msg)
                            .font(.callout)
                            .foregroundColor(.white)
                            .multilineTextAlignment(.leading)
                            .lineLimit(6)
                    }
                    .padding(16)
                    .background(Color.black.opacity(0.88))
                    .cornerRadius(12)
                    .padding(.horizontal, 24)
                    .frame(maxWidth: .infinity)
                } else if slot.playerEngine.state == .loading || slot.playerEngine.state == .buffering {
                    ProgressView()
                        .scaleEffect(1.5)
                        .frame(maxWidth: .infinity)
                }

                Spacer()

                // Tuner-capacity warning: its own full-width banner, not squeezed into the
                // bottom info row's leftover horizontal space - at 11-12pt sharing a row with
                // channel/program text it was easy to miss from 10 feet away. A dedicated
                // full-width pill with a larger, bold label reads at a glance instead.
                if let warning = slot.warningMessage {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.black)
                            .font(.system(size: 15, weight: .bold))
                        Text(warning)
                            .font(.system(size: 15, weight: .bold))
                            .foregroundColor(.black)
                            .lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(Color.yellow)
                    .cornerRadius(10)
                    .padding(.horizontal, 14)
                    .padding(.bottom, 6)
                }

                // Bottom Program Info
                HStack(alignment: .bottom) {
                    if let airing = slot.airing {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(airing.title)
                                .font(.system(size: 16, weight: .bold))
                                .foregroundColor(.white)
                                .lineLimit(1)

                            if let sub = slot.subtitle, !sub.isEmpty {
                                Text(sub)
                                    .font(.system(size: 13, weight: .medium))
                                    .foregroundColor(.white.opacity(0.75))
                                    .lineLimit(1)
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.black.opacity(0.75))
                        .cornerRadius(10)
                    }

                    Spacer()
                }
                .padding(14)
            }
        }
    }
}
