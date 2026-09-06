import SwiftUI
import HDHROpenKit

// tvOS equivalent of the web's HDHomeRunPlayerRecordMenu.svelte: a scheduled
// rule for the current channel/airing collapses the menu to just "Cancel
// Recording"; otherwise it offers this app's own quick "save the buffering
// watch session" action alongside episode/series rule creation and the full
// options modal. Rendered as a focus-scoped overlay (mirrors
// TVPlayerSettingsOverlay) rather than a native SwiftUI `Menu`, matching how
// every other in-player tvOS popup in this app is built.
public struct TVPlayerRecordMenuOverlay: View {
    let existingRule: HDHomeRunRecordingRule?
    let canRecordSeries: Bool
    let isPromoted: Bool
    let isPromoting: Bool
    let onSaveCurrentRecording: () -> Void
    let onRecordEpisode: () -> Void
    let onRecordSeries: () -> Void
    let onCancelRule: () -> Void
    let onOptions: () -> Void
    let onDismiss: () -> Void

    @FocusState private var focusedElement: RecordMenuFocus?

    private enum RecordMenuFocus: Hashable {
        case close, cancel, save, episode, series, options
    }

    public init(
        existingRule: HDHomeRunRecordingRule?,
        canRecordSeries: Bool,
        isPromoted: Bool,
        isPromoting: Bool,
        onSaveCurrentRecording: @escaping () -> Void,
        onRecordEpisode: @escaping () -> Void,
        onRecordSeries: @escaping () -> Void,
        onCancelRule: @escaping () -> Void,
        onOptions: @escaping () -> Void,
        onDismiss: @escaping () -> Void
    ) {
        self.existingRule = existingRule
        self.canRecordSeries = canRecordSeries
        self.isPromoted = isPromoted
        self.isPromoting = isPromoting
        self.onSaveCurrentRecording = onSaveCurrentRecording
        self.onRecordEpisode = onRecordEpisode
        self.onRecordSeries = onRecordSeries
        self.onCancelRule = onCancelRule
        self.onOptions = onOptions
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.8).ignoresSafeArea()

            VStack(alignment: .leading, spacing: 24) {
                HStack {
                    Text("Recording")
                        .font(.title2.bold())
                        .foregroundColor(Theme.textPrimary)
                    Spacer()
                    Button("Close", action: onDismiss)
                        .focused($focusedElement, equals: .close)
                }

                Divider().background(Theme.appBorder)

                VStack(alignment: .leading, spacing: 12) {
                    if existingRule != nil {
                        Button(role: .destructive, action: onCancelRule) {
                            Label("Cancel Recording", systemImage: "record.circle")
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                        }
                        .focused($focusedElement, equals: .cancel)

                        Button(action: onOptions) {
                            Label("Recording Options…", systemImage: "slider.horizontal.3")
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                        }
                        .focused($focusedElement, equals: .options)
                    } else {
                        Button(action: onSaveCurrentRecording) {
                            Label(isPromoted ? "Recording Saved" : "Save Current Recording", systemImage: "checkmark.circle")
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                        }
                        .disabled(isPromoting || isPromoted)
                        .focused($focusedElement, equals: .save)

                        Button(action: onRecordEpisode) {
                            Label("Record Episode", systemImage: "record.circle")
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                        }
                        .focused($focusedElement, equals: .episode)

                        if canRecordSeries {
                            Button(action: onRecordSeries) {
                                Label("Record Series", systemImage: "recordingtape")
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 10)
                            }
                            .focused($focusedElement, equals: .series)
                        }

                        Button(action: onOptions) {
                            Label("Recording Options…", systemImage: "slider.horizontal.3")
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                        }
                        .focused($focusedElement, equals: .options)
                    }
                }
            }
            .padding(40)
            .frame(maxWidth: 700)
            .background(Theme.appSurface)
            .cornerRadius(20)
        }
        // Mirrors TVPlaybackControlsView/TVPlayerSettingsOverlay's onAppear
        // focus claim - this overlay is a ZStack sibling added on top of the
        // still-mounted player controls, so nothing moves focus onto it
        // automatically.
        .onAppear {
            focusedElement = existingRule != nil ? .cancel : .save
        }
    }
}
