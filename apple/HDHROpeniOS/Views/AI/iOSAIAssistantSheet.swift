import HDHROpenKit
import SwiftUI

public struct iOSAIAssistantSheet: View {
    let apiClient: APIClient
    @Environment(\.dismiss) private var dismiss

    @State private var turns: [AIChatTurn] = []
    @State private var inputText = ""
    @State private var isSending = false
    @State private var errorText: String?

    let inspection = Inspection<Self>()

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                messagesScrollView

                if let errorText {
                    Text(errorText)
                        .font(.footnote)
                        .foregroundColor(.red)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.red.opacity(0.1))
                }

                Divider()

                inputBar
            }
            .background(Theme.appBackground)
            .navigationTitle("AI Assistant")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("New Chat") {
                        turns = []
                        errorText = nil
                    }
                    .disabled(turns.isEmpty || isSending)
                }

                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
        .onReceive(inspection.notice) { inspection.visit(self, $0) }
    }

    // MARK: - Messages View

    private var messagesScrollView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 16) {
                    if turns.isEmpty {
                        emptyStateView
                    } else {
                        ForEach(turns) { turn in
                            chatTurnView(turn)
                        }

                        if isSending, turns.last?.text.isEmpty ?? true, turns.last?.toolStatuses.isEmpty ?? true {
                            HStack(spacing: 8) {
                                ProgressView()
                                    .scaleEffect(0.8)
                                Text("Thinking...")
                                    .font(.subheadline)
                                    .foregroundColor(Theme.textMuted)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 16)
                        }
                    }

                    Color.clear
                        .frame(height: 1)
                        .id("bottomID")
                }
                .padding(.vertical, 16)
            }
            .onChange(of: turns.count) { _, _ in
                withAnimation {
                    proxy.scrollTo("bottomID", anchor: .bottom)
                }
            }
            .onChange(of: turns.last?.text) { _, _ in
                proxy.scrollTo("bottomID", anchor: .bottom)
            }
        }
    }

    // MARK: - Empty State & Suggestion Chips

    private var emptyStateView: some View {
        VStack(spacing: 20) {
            Image(systemName: "sparkles")
                .font(.system(size: 48))
                .foregroundColor(.blue)
                .padding(.top, 40)

            Text("What can I help you find?")
                .font(.headline)
                .foregroundColor(Theme.textPrimary)

            Text("Ask questions about TV schedules, live sports, or manage your DVR recordings.")
                .font(.subheadline)
                .foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            VStack(spacing: 10) {
                ForEach(AIChatHelpers.quickSuggestions, id: \.self) { suggestion in
                    Button(action: {
                        sendPrompt(suggestion)
                    }) {
                        HStack {
                            Image(systemName: "bubble.left")
                                .font(.footnote)
                            Text(suggestion)
                                .font(.subheadline.weight(.medium))
                            Spacer()
                            Image(systemName: "arrow.up.right")
                                .font(.caption2)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .background(Theme.appSurface)
                        .foregroundColor(.blue)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(Theme.appBorder, lineWidth: 1)
                        )
                    }
                    .padding(.horizontal, 24)
                }
            }
            .padding(.top, 10)
        }
    }

    // MARK: - Chat Turn Item

    private func chatTurnView(_ turn: AIChatTurn) -> some View {
        VStack(alignment: turn.role == "user" ? .trailing : .leading, spacing: 8) {
            if turn.role == "user" {
                HStack {
                    Spacer(minLength: 40)
                    Text(turn.text)
                        .font(.body)
                        .foregroundColor(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(Color.blue)
                        .cornerRadius(18)
                }
                .padding(.horizontal, 16)
            } else {
                HStack {
                    VStack(alignment: .leading, spacing: 8) {
                        if !turn.toolStatuses.isEmpty {
                            toolStatusesView(turn.toolStatuses)
                        }

                        if !turn.text.isEmpty {
                            Text(LocalizedStringKey(turn.text))
                                .font(.body)
                                .foregroundColor(Theme.textPrimary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 10)
                                .background(Theme.appSurfaceVariant)
                                .cornerRadius(18)
                        }

                        if let action = turn.actionPreview {
                            actionCardView(action)
                        }
                    }
                    Spacer(minLength: 40)
                }
                .padding(.horizontal, 16)
            }
        }
    }

    // MARK: - Tool Badges

    private func toolStatusesView(_ statuses: [AIToolStatusEntry]) -> some View {
        HStack(spacing: 6) {
            ForEach(statuses) { status in
                HStack(spacing: 4) {
                    if status.status == "running" {
                        ProgressView()
                            .scaleEffect(0.6)
                    } else if status.status == "error" {
                        Image(systemName: "xmark.circle.fill")
                            .font(.caption2)
                            .foregroundColor(.red)
                    } else {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.caption2)
                            .foregroundColor(.green)
                    }
                    Text(status.tool)
                        .font(.caption.weight(.semibold))
                        .foregroundColor(Theme.textSecondary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Theme.appSurface)
                .cornerRadius(8)
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Theme.appBorder, lineWidth: 0.5)
                )
            }
        }
    }

    // MARK: - Action Confirmation Card

    private func actionCardView(_ action: AIActionPreviewEntry) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Image(systemName: "record.circle")
                    .foregroundColor(.red)
                Text(humanReadableToolName(action.tool))
                    .font(.subheadline.bold())
                    .foregroundColor(Theme.textPrimary)
            }

            Divider()

            VStack(alignment: .leading, spacing: 4) {
                ForEach(action.preview.keys.sorted(), id: \.self) { key in
                    if let val = action.preview[key]?.value {
                        HStack(alignment: .top) {
                            Text(key.replacingOccurrences(of: "_", with: " ").capitalized + ":")
                                .font(.caption.weight(.medium))
                                .foregroundColor(Theme.textMuted)
                                .frame(width: 90, alignment: .leading)
                            Text("\(String(describing: val))")
                                .font(.caption)
                                .foregroundColor(Theme.textPrimary)
                        }
                    }
                }
            }

            switch action.resolution {
            case .pending, .confirming:
                HStack(spacing: 12) {
                    Button(action: {
                        confirmAction(action.actionId)
                    }) {
                        HStack {
                            if action.resolution == .confirming {
                                ProgressView()
                                    .scaleEffect(0.7)
                            }
                            Text(action.resolution == .confirming ? "Confirming..." : "Confirm")
                                .font(.subheadline.weight(.semibold))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(8)
                    }
                    .disabled(action.resolution == .confirming)

                    Button(action: {
                        cancelAction(action.actionId)
                    }) {
                        Text("Cancel")
                            .font(.subheadline)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .background(Theme.appSurfaceVariant)
                            .foregroundColor(Theme.textSecondary)
                            .cornerRadius(8)
                    }
                    .disabled(action.resolution == .confirming)
                }
                .padding(.top, 4)

            case .confirmed:
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                    Text("Action confirmed and scheduled.")
                        .font(.footnote.weight(.medium))
                        .foregroundColor(.green)
                }
                .padding(.top, 4)

            case .cancelled:
                HStack(spacing: 6) {
                    Image(systemName: "xmark.circle")
                        .foregroundColor(Theme.textMuted)
                    Text("Action cancelled.")
                        .font(.footnote)
                        .foregroundColor(Theme.textMuted)
                }
                .padding(.top, 4)

            case .failed:
                HStack(spacing: 6) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.red)
                    Text("Failed to execute action.")
                        .font(.footnote)
                        .foregroundColor(.red)
                }
                .padding(.top, 4)
            }
        }
        .padding(14)
        .frame(maxWidth: 320, alignment: .leading)
        .background(Theme.appSurface)
        .cornerRadius(14)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(Theme.appBorder, lineWidth: 1)
        )
    }

    // MARK: - Input Bar

    private var inputBar: some View {
        HStack(spacing: 12) {
            TextField("Ask a question...", text: $inputText, axis: .vertical)
                .lineLimit(1...4)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Theme.appSurfaceVariant)
                .cornerRadius(20)

            Button(action: {
                sendPrompt(inputText)
            }) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 32))
                    .foregroundColor(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending ? Theme.textMuted : .blue)
            }
            .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Theme.appSurface)
    }

    // MARK: - Actions

    private func sendPrompt(_ content: String) {
        let trimmed = content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isSending else { return }

        inputText = ""
        errorText = nil

        let priorWire = AIChatHelpers.toWireMessages(turns: turns)
        var wire = priorWire
        wire.append(.user(trimmed))

        turns.append(AIChatTurn(role: "user", text: trimmed))
        turns.append(AIChatTurn(role: "assistant", text: ""))

        let assistantIndex = turns.count - 1
        isSending = true

        Task {
            do {
                try await apiClient.sendAIChat(request: AIChatRequest(messages: wire)) { event in
                    Task { @MainActor in
                        handleStreamEvent(event, forTurnIndex: assistantIndex)
                    }
                }
            } catch {
                await MainActor.run {
                    errorText = error.localizedDescription
                }
            }
            await MainActor.run {
                isSending = false
            }
        }
    }

    private func handleStreamEvent(_ event: AIStreamEvent, forTurnIndex index: Int) {
        guard index < turns.count else { return }

        switch event.type {
        case "token":
            if let text = event.text {
                turns[index].text += text
            }
        case "tool_call":
            if let id = event.id, let tool = event.tool {
                turns[index].toolCalls.append(
                    AIToolCallRecord(id: id, name: tool, arguments: event.arguments ?? [:])
                )
            }
        case "tool_status":
            if let tool = event.tool, let status = event.status {
                if let existing = turns[index].toolStatuses.firstIndex(where: { $0.tool == tool }) {
                    turns[index].toolStatuses[existing].status = status
                    turns[index].toolStatuses[existing].message = event.message
                } else {
                    turns[index].toolStatuses.append(
                        AIToolStatusEntry(tool: tool, status: status, message: event.message)
                    )
                }
            }
        case "tool_result":
            if let id = event.id, let content = event.content {
                if let recIdx = turns[index].toolCalls.firstIndex(where: { $0.id == id }) {
                    turns[index].toolCalls[recIdx].result = content
                }
            }
        case "action_preview":
            if let actionId = event.actionId, let tool = event.tool, let preview = event.preview {
                turns[index].actionPreview = AIActionPreviewEntry(
                    actionId: actionId,
                    tool: tool,
                    preview: preview,
                    resolution: .pending
                )
            }
        case "error":
            if let msg = event.message {
                errorText = msg
            }
        case "done":
            isSending = false
        default:
            break
        }
    }

    private func confirmAction(_ actionId: String) {
        guard let turnIdx = turns.firstIndex(where: { $0.actionPreview?.actionId == actionId }) else { return }
        turns[turnIdx].actionPreview?.resolution = .confirming

        Task {
            do {
                _ = try await apiClient.confirmAIAction(actionId: actionId)
                await MainActor.run {
                    turns[turnIdx].actionPreview?.resolution = .confirmed
                }
            } catch {
                await MainActor.run {
                    turns[turnIdx].actionPreview?.resolution = .failed
                }
            }
        }
    }

    private func cancelAction(_ actionId: String) {
        guard let turnIdx = turns.firstIndex(where: { $0.actionPreview?.actionId == actionId }) else { return }
        turns[turnIdx].actionPreview?.resolution = .cancelled

        Task {
            _ = try? await apiClient.cancelAIAction(actionId: actionId)
        }
    }

    private func humanReadableToolName(_ tool: String) -> String {
        switch tool {
        case "schedule_recording": "Schedule Recording"
        case "cancel_recording_rule": "Cancel Recording Rule"
        case "delete_recording": "Delete Recording"
        default: tool.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
}
