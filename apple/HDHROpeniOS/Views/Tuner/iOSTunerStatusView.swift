import HDHROpenKit
import SwiftUI

public struct iOSTunerStatusView: View {
    @EnvironmentObject private var tunerViewModel: TunerViewModel

    public init() {}

    public var body: some View {
        List {
            if let info = tunerViewModel.tunerInfo {
                Section(header: Text("Tuner Device")) {
                    HStack {
                        Text("Model")
                        Spacer()
                        Text(info.friendlyName).foregroundColor(.secondary)
                    }
                    if let fw = info.firmwareVersion {
                        HStack {
                            Text("Firmware")
                            Spacer()
                            Text(fw).foregroundColor(.secondary)
                        }
                    }
                }
            }

            Section(header: Text("Tuners")) {
                if tunerViewModel.tuners.isEmpty {
                    Text("Scanning for tuners...")
                        .foregroundColor(.secondary)
                } else {
                    ForEach(tunerViewModel.tuners) { tuner in
                        VStack(alignment: .leading, spacing: 10) {
                            HStack {
                                Circle()
                                    .fill(tuner.inUse ? Color.green : Color.gray)
                                    .frame(width: 10, height: 10)
                                Text("Tuner \(tuner.index)")
                                    .font(.headline)

                                Spacer()

                                if tuner.inUse {
                                    Text(tuner.formattedRateMbps)
                                        .font(.caption.monospacedDigit().bold())
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color.blue.opacity(0.15))
                                        .foregroundColor(.blue)
                                        .cornerRadius(4)
                                } else {
                                    Text("Idle")
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                            }

                            if tuner.inUse {
                                if let ch = tuner.channelNumber {
                                    Text("Streaming Channel \(ch) (\(tuner.channelName ?? ""))")
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }

                                if let client = tuner.client {
                                    Text("Client: \(client.name.isEmpty ? (client.ip ?? "Unknown") : client.name)")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                }

                                HStack(spacing: 16) {
                                    miniMeter(label: "Signal", value: tuner.signalStrengthPercent ?? 0)
                                    miniMeter(label: "Quality", value: tuner.signalQualityPercent ?? 0)
                                    miniMeter(label: "Symbol", value: tuner.symbolQualityPercent ?? 0)
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
        .navigationTitle("Tuner Status")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(action: { Task { await tunerViewModel.loadData() } }) {
                    Image(systemName: "arrow.clockwise")
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

    private func miniMeter(label: String, value: Int) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(label): \(value)%")
                .font(.caption2.bold())
                .foregroundColor(.secondary)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.gray.opacity(0.2))
                    Capsule()
                        .fill(value >= 80 ? Color.green : (value >= 50 ? Color.yellow : Color.red))
                        .frame(width: geo.size.width * CGFloat(min(100, max(0, value))) / 100.0)
                }
            }
            .frame(height: 6)
        }
    }
}
