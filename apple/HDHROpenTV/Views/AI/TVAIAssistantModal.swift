import HDHROpenKit
import SwiftUI

public struct TVAIAssistantModal: View {
    let apiClient: APIClient
    @Environment(\.dismiss) private var dismiss

    @Namespace private var focusNamespace
    @State private var turns: [AIChatTurn] = []
    @State private var inputText = ""
    @State private var isSending = false
    @State private var errorText: String?

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 20) {
                headerView

                Divider().background(Theme.appBorder)

                quickSuggestionsBar

                messagesArea

                if let errorText {
                    Text(errorText)
                        .font(.callout)
                        .foregroundColor(.red)
                        .padding(.horizontal, 16)
                }

                Divider().background(Theme.appBorder)

                inputBar
            }
            .padding(40)
            .frame(maxWidth: 1300, maxHeight: 920)
            .background(Theme.appSurface)
            .cornerRadius(24)
            .overlay(
                RoundedRectangle(cornerRadius: 24)
                    .stroke(Theme.appBorder, lineWidth: 1)
            )
        }
        .focusScope(focusNamespace)
    }

    // MARK: - Header

    private var headerView: some View {
        HStack {
            Image(systemName: "sparkles")
                .font(.title)
                .foregroundColor(.blue)

            Text("AI Guide Assistant")
                .font(.title.bold())
                .foregroundColor(Theme.textPrimary)

            Spacer()

            Button("New Chat") {
                turns = []
                errorText = nil
            }
            .disabled(turns.isEmpty || isSending)

            Button("Close") {
                dismiss()
            }
        }
    }

    // MARK: - Quick Suggestions

    private var quickSuggestionsBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 16) {
                ForEach(AIChatHelpers.quickSuggestions, id: \.self) { suggestion in
                    Button(action: {
                        sendPrompt(suggestion)
                    }) {
                        HStack(spacing: 8) {
                            Image(systemName: "magnifyingglass")
                            Text(suggestion)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding(.vertical, 4)
        }
    }

    // MARK: - Messages Area

    private var messagesArea: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 20) {
                    if turns.isEmpty {
                        VStack(spacing: 16) {
                            Spacer()
                            Text("Use dictation or pick a suggestion above to search.")
                                .font(.title3)
                                .foregroundColor(Theme.textMuted)
                            Spacer()
                        }
                        .frame(maxWidth: .infinity, minHeight: 280)
                    } else {
                        ForEach(turns) { turn in
                            turnView(turn)
                        }

                        if isSending, turns.last?.text.isEmpty ?? true, turns.last?.toolStatuses.isEmpty ?? true {
                            HStack(spacing: 12) {
                                ProgressView()
                                Text("Thinking...")
                                    .font(.headline)
                                    .foregroundColor(Theme.textMuted)
                            }
                            .padding(.leading, 12)
                        }
                    }

                    Color.clear
                        .frame(height: 1)
                        .id("bottomID")
                }
                .padding(.vertical, 8)
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

    // MARK: - Turn View

    private func turnView(_ turn: AIChatTurn) -> some View {
        VStack(alignment: turn.role == "user" ? .trailing : .leading, spacing: 8) {
            if turn.role == "user" {
                HStack {
                    Spacer(minLength: 120)
                    Text(turn.text)
                        .font(.headline)
                        .foregroundColor(.white)
                        .padding(.horizontal, 24)
                        .padding(.vertical, 14)
                        .background(Color.blue)
                        .cornerRadius(20)
                }
            } else {
                HStack {
                    VStack(alignment: .leading, spacing: 12) {
                        if !turn.toolStatuses.isEmpty {
                            toolBadges(turn.toolStatuses)
                        }

                        if !turn.text.isEmpty {
                            Text(LocalizedStringKey(turn.text))
                                .font(.headline)
                                .foregroundColor(Theme.textPrimary)
                                .padding(.horizontal, 24)
                                .padding(.vertical, 14)
                                .background(Theme.appSurfaceVariant)
                                .cornerRadius(20)
                        }

                        if let action = turn.actionPreview {
                            tvActionCard(action)
                        }
                    }
                    Spacer(minLength: 120)
                }
            }
        }
    }

    // MARK: - Tool Badges

    private func toolBadges(_ statuses: [AIToolStatusEntry]) -> some View {
        HStack(spacing: 10) {
            ForEach(statuses) { status in
                HStack(spacing: 6) {
                    if status.status == "running" {
                        ProgressView()
                            .scaleEffect(0.7)
                    } else if status.status == "error" {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.red)
                    } else {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundColor(.green)
                    }
                    Text(status.tool)
                        .font(.caption.weight(.semibold))
                        .foregroundColor(Theme.textSecondary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Theme.appSurface)
                .cornerRadius(10)
            }
        }
    }

    // MARK: - TV Action Card

    private func tvActionCard(_ action: AIActionPreviewEntry) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "record.circle")
                    .foregroundColor(.red)
                Text(humanReadableToolName(action.tool))
                    .font(.headline.bold())
                    .foregroundColor(Theme.textPrimary)
            }

            VStack(alignment: .leading, spacing: 6) {
                ForEach(action.preview.keys.sorted(), id: \.self) { key in
                    if let val = action.preview[key]?.value {
                        HStack(alignment: .top) {
                            Text(key.replacingOccurrences(of: "_", with: " ").capitalized + ":")
                                .font(.subheadline.bold())
                                .foregroundColor(Theme.textMuted)
                                .frame(width: 140, alignment: .leading)
                            Text("\(String(describing: val))")
                                .font(.subheadline)
                                .foregroundColor(Theme.textPrimary)
                        }
                    }
                }
            }

            switch action.resolution {
            case .pending, .confirming:
                HStack(spacing: 20) {
                    Button(action: {
                        confirmAction(action.actionId)
                    }) {
                        HStack {
                            if action.resolution == .confirming {
                                ProgressView()
                            }
                            Text(action.resolution == .confirming ? "Confirming..." : "Confirm Action")
                        }
                    }
                    .disabled(action.resolution == .confirming)

                    Button("Cancel") {
                        cancelAction(action.actionId)
                    }
                    .disabled(action.resolution == .confirming)
                }
                .padding(.top, 8)

            case .confirmed:
                HStack(spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                    Text("Action confirmed and executed.")
                        .font(.headline)
                        .foregroundColor(.green)
                }

            case .cancelled:
                HStack(spacing: 8) {
                    Image(systemName: "xmark.circle")
                        .foregroundColor(Theme.textMuted)
                    Text("Action cancelled.")
                        .font(.headline)
                        .foregroundColor(Theme.textMuted)
                }

            case .failed:
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(.red)
                    Text("Execution failed.")
                        .font(.headline)
                        .foregroundColor(.red)
                }
            }
        }
        .padding(20)
        .frame(maxWidth: 500, alignment: .leading)
        .background(Theme.appSurface)
        .cornerRadius(16)
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(Theme.appBorder, lineWidth: 1)
        )
    }

    // MARK: - Input Bar

    private var inputBar: some View {
        HStack(spacing: 20) {
            TextField("Type or dictate a question...", text: $inputText)
                .padding(14)
                .background(Theme.appSurfaceVariant)
                .cornerRadius(12)

            Button(action: {
                sendPrompt(inputText)
            }) {
                HStack {
                    Image(systemName: "arrow.up.circle.fill")
                    Text("Send")
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
            }
            .disabled(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
        }
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
