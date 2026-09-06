import SwiftUI
import HDHROpenKit

public struct iOSProgramDetailSheet: View {
    let channel: HDHomeRunChannel
    let airing: HDHomeRunGuideEntry

    @EnvironmentObject private var guideViewModel: GuideViewModel
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @EnvironmentObject private var recordingsViewModel: RecordingsViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var showRecordingOptionsSheet = false

    public init(channel: HDHomeRunChannel, airing: HDHomeRunGuideEntry) {
        self.channel = channel
        self.airing = airing
    }

    public var body: some View {
        let existingRule = guideViewModel.findRule(for: channel.channelNumber, airing: airing)

        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if let img = airing.imageUrl, let url = URL(string: img) {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(16/9, contentMode: .fill)
                        } placeholder: {
                            Color.gray.opacity(0.2)
                        }
                        .frame(maxWidth: .infinity, maxHeight: 200)
                        .cornerRadius(12)
                        .clipped()
                    }

                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Text(channel.channelNumber)
                                .font(.subheadline.bold())
                                .foregroundColor(.blue)
                            Text(channel.name)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                            if channel.isHD {
                                Text("HD")
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(Color.blue.opacity(0.8))
                                    .foregroundColor(.white)
                                    .cornerRadius(3)
                            }
                        }

                        Text(airing.title)
                            .font(.title2.bold())

                        if let epDesig = airing.formattedEpisodeDesignation {
                            if let ep = airing.episodeTitle, !ep.isEmpty {
                                Text("\(epDesig) • \(ep)")
                                    .font(.headline)
                                    .foregroundColor(.secondary)
                            } else {
                                Text(epDesig)
                                    .font(.headline)
                                    .foregroundColor(.secondary)
                            }
                        } else if let ep = airing.episodeTitle {
                            Text(ep)
                                .font(.headline)
                                .foregroundColor(.secondary)
                        }

                        HStack(spacing: 6) {
                            if channel.isHD {
                                Text("HD")
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(Color.blue.opacity(0.8))
                                    .foregroundColor(.white)
                                    .cornerRadius(3)
                            }
                            if airing.hasCC != false {
                                Text("CC")
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(Color.secondary.opacity(0.2))
                                    .foregroundColor(.primary)
                                    .cornerRadius(3)
                            }
                            if airing.isNew == true {
                                Text("NEW")
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(Color.green.opacity(0.2))
                                    .foregroundColor(.green)
                                    .cornerRadius(3)
                            }
                            if let audio = airing.formattedAudio, !audio.isEmpty {
                                Text(audio)
                                    .font(.caption2.bold())
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(Color.secondary.opacity(0.2))
                                    .foregroundColor(.primary)
                                    .cornerRadius(3)
                            }
                            if let cat = airing.category, !cat.isEmpty {
                                Text(cat.components(separatedBy: ",").first?.trimmingCharacters(in: .whitespaces) ?? cat)
                                    .font(.caption2)
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(Color.secondary.opacity(0.15))
                                    .foregroundColor(.secondary)
                                    .cornerRadius(3)
                            }
                        }

                        Text(TimeFormatting.formatTimeRange(start: airing.start, end: airing.end))
                            .font(.subheadline)
                            .foregroundColor(.secondary)

                        if let airDate = airing.originalAirdate, !airDate.isEmpty {
                            Text("Original Air Date: \(airDate)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }

                    if let syn = airing.synopsis, !syn.isEmpty {
                        Text(syn)
                            .font(.body)
                            .foregroundColor(.primary)
                    }

                    Divider().padding(.vertical, 8)

                    VStack(spacing: 12) {
                        if airing.isCurrentlyAiring() {
                            Button(action: {
                                dismiss()
                                Task {
                                    await playerViewModel.playChannel(channel: channel, airing: airing)
                                }
                            }) {
                                Label("Watch Live", systemImage: "play.fill")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 12)
                            }
                            .buttonStyle(.borderedProminent)
                        }

                        if let rule = existingRule {
                            Button(role: .destructive, action: {
                                Task {
                                    try? await guideViewModel.cancelRule(ruleId: rule.recordingRuleId)
                                    dismiss()
                                }
                            }) {
                                Label("Cancel Recording", systemImage: "record.circle")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 12)
                            }
                            .buttonStyle(.bordered)
                        } else {
                            Button(action: {
                                Task {
                                    try? await guideViewModel.recordEpisode(
                                        seriesId: airing.seriesId,
                                        channelNumber: channel.channelNumber,
                                        start: airing.start
                                    )
                                    dismiss()
                                }
                            }) {
                                Label("Record Episode", systemImage: "record.circle")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 12)
                            }
                            .buttonStyle(.bordered)

                            Button(action: {
                                Task {
                                    try? await guideViewModel.recordSeries(
                                        seriesId: airing.seriesId ?? "",
                                        channelNumber: channel.channelNumber
                                    )
                                    dismiss()
                                }
                            }) {
                                Label("Record Series", systemImage: "recordingtape")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 12)
                            }
                            .buttonStyle(.bordered)
                        }

                        Button(action: {
                            showRecordingOptionsSheet = true
                        }) {
                            Label("Recording Options…", systemImage: "slider.horizontal.3")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding(20)
            }
            .navigationTitle("Program Details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .task {
                if recordingsViewModel.dvrInfo == nil {
                    await recordingsViewModel.loadDvrInfo()
                }
            }
            .sheet(isPresented: $showRecordingOptionsSheet) {
                iOSRecordingOptionsSheet(
                    channel: channel,
                    airing: airing,
                    canRecordSeries: true,
                    existingRule: existingRule,
                    onConfirm: { recordSeries, options in
                        Task {
                            if let rule = existingRule {
                                try? await guideViewModel.updateRule(
                                    ruleId: rule.recordingRuleId,
                                    isSeries: recordSeries,
                                    options: options,
                                    seriesId: airing.seriesId,
                                    start: airing.start,
                                    channelNumber: channel.channelNumber
                                )
                            } else if recordSeries {
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
                            dismiss()
                        }
                    },
                    onCancelRule: existingRule.map { rule in
                        {
                            Task {
                                try? await guideViewModel.cancelRule(ruleId: rule.recordingRuleId)
                                dismiss()
                            }
                        }
                    }
                )
            }
        }
    }
}
