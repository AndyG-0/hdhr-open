import HDHROpenKit
import SwiftUI

public struct TVTunerStatusView: View {
    @EnvironmentObject private var tunerViewModel: TunerViewModel

    public init() {}

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 24) {
                // Header
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Tuner Hardware & Signal")
                            .font(.largeTitle.bold())
                            .foregroundColor(Theme.textPrimary)

                        if let info = tunerViewModel.tunerInfo {
                            Text("\(info.friendlyName) • Firmware \(info.firmwareVersion ?? "Unknown")")
                                .font(.headline)
                                .foregroundColor(.secondary)
                        }
                    }

                    Spacer()

                    Button(action: {
                        Task { await tunerViewModel.loadData() }
                    }) {
                        Label("Refresh", systemImage: "arrow.clockwise")
                    }
                }
                .padding(.horizontal, 48)
                .padding(.top, 24)

                // Tuners List
                if tunerViewModel.tuners.isEmpty {
                    VStack(spacing: 12) {
                        Spacer()
                        ProgressView("Discovering Tuners...")
                            .scaleEffect(1.5)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 20) {
                            ForEach(tunerViewModel.tuners) { tuner in
                                tunerCard(for: tuner)
                            }
                        }
                        .padding(.horizontal, 48)
                        .padding(.bottom, 64)
                    }
                }
            }
        }
        .onAppear {
            tunerViewModel.startPolling(intervalSeconds: 2)
        }
        .onDisappear {
            tunerViewModel.stopPolling()
        }
    }

    private func tunerCard(for tuner: HDHomeRunTuner) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                HStack(spacing: 8) {
                    Circle()
                        .fill(tuner.inUse ? Color.green : Theme.textMuted)
                        .frame(width: 12, height: 12)

                    Text("Tuner \(tuner.index)")
                        .font(.title2.bold())
                        .foregroundColor(Theme.textPrimary)
                }

                Spacer()

                if tuner.inUse {
                    HStack(spacing: 12) {
                        if let ch = tuner.channelNumber {
                            Text("Channel \(ch)")
                                .font(.headline)
                                .foregroundColor(.blue)
                        }

                        if let name = tuner.channelName {
                            Text(name)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }

                        Text(tuner.formattedRateMbps)
                            .font(.caption.monospacedDigit().bold())
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.blue.opacity(0.3))
                            .cornerRadius(6)
                    }

                    if let client = tuner.client {
                        Text("Client: \(client.name.isEmpty ? (client.ip ?? "Unknown") : client.name)")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                } else {
                    Text("Idle / Available")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
            }

            if tuner.inUse {
                Divider().background(Theme.appBorder)

                HStack(spacing: 32) {
                    metricGauge(
                        title: "Signal Strength",
                        value: tuner.signalStrengthPercent ?? 0,
                        unit: "%"
                    )

                    metricGauge(
                        title: "Signal Quality",
                        value: tuner.signalQualityPercent ?? 0,
                        unit: "%"
                    )

                    metricGauge(
                        title: "Symbol Quality",
                        value: tuner.symbolQualityPercent ?? 0,
                        unit: "%"
                    )
                }
            }
        }
        .padding(24)
        .background(Theme.appSurface)
        .cornerRadius(16)
    }

    private func metricGauge(title: String, value: Int, unit: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)

            HStack(spacing: 8) {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Theme.appSurfaceVariant)
                            .frame(height: 8)

                        Capsule()
                            .fill(gaugeColor(for: value))
                            .frame(width: geo.size.width * CGFloat(min(100, max(0, value))) / 100.0, height: 8)
                    }
                }
                .frame(height: 8)

                Text("\(value)\(unit)")
                    .font(.caption.bold().monospacedDigit())
                    .foregroundColor(gaugeColor(for: value))
                    .frame(width: 44, alignment: .trailing)
            }
        }
    }

    private func gaugeColor(for percent: Int) -> Color {
        if percent >= 80 {
            return .green
        }
        if percent >= 50 {
            return .yellow
        }
        return .red
    }
}
