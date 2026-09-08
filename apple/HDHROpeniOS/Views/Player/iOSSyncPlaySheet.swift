import HDHROpenKit
import SwiftUI
#if canImport(UIKit)
    import UIKit
#endif

public struct iOSSyncPlaySheet: View {
    @EnvironmentObject private var playerViewModel: PlayerViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var userName = "Apple User"
    @State private var roomCodeInput = ""
    @State private var isBusy = false
    @State private var errorMessage: String? = nil
    @State private var copiedCode = false

    public init() {}

    public var body: some View {
        NavigationStack {
            List {
                if let error = errorMessage {
                    Section {
                        Text(error)
                            .font(.callout)
                            .foregroundColor(.red)
                    }
                }

                if let room = playerViewModel.syncPlayClient.room, playerViewModel.syncPlayClient.isConnected {
                    // Active Room State
                    Section("Watch Party Room") {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("ROOM CODE")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(room.roomCode)
                                    .font(.system(.title, design: .monospaced).bold())
                                    .tracking(4)
                                    .foregroundColor(.accentColor)
                            }
                            Spacer()
                            Button(action: {
                                #if canImport(UIKit)
                                    UIPasteboard.general.string = room.roomCode
                                #endif
                                copiedCode = true
                                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                                    copiedCode = false
                                }
                            }) {
                                Label(copiedCode ? "Copied" : "Copy", systemImage: copiedCode ? "checkmark" : "doc.on.doc")
                                    .font(.subheadline.bold())
                            }
                            .buttonStyle(.bordered)
                        }
                        .padding(.vertical, 4)

                        if let content = room.currentContent {
                            HStack {
                                Image(systemName: content.type == "recording" ? "video.fill" : "tv.fill")
                                    .foregroundColor(.secondary)
                                Text(content.title.isEmpty ? (content.channelNumber ?? "Live Stream") : content.title)
                                    .font(.subheadline.bold())
                                    .lineLimit(1)
                            }
                        }
                    }

                    Section("Participants (\(playerViewModel.syncPlayClient.participants.count))") {
                        ForEach(playerViewModel.syncPlayClient.participants) { participant in
                            let isMe = participant.sessionId == playerViewModel.syncPlayClient.sessionId
                            HStack(spacing: 12) {
                                ZStack {
                                    Circle()
                                        .fill(Color.blue.opacity(0.2))
                                        .frame(width: 36, height: 36)
                                    Text(String(participant.userName.prefix(1)).uppercased())
                                        .font(.subheadline.bold())
                                        .foregroundColor(.blue)
                                }

                                VStack(alignment: .leading, spacing: 2) {
                                    HStack(spacing: 6) {
                                        Text(participant.userName + (isMe ? " (You)" : ""))
                                            .font(.body.weight(.medium))

                                        if participant.isHost {
                                            Text("HOST")
                                                .font(.caption2.bold())
                                                .padding(.horizontal, 6)
                                                .padding(.vertical, 2)
                                                .background(Color.yellow.opacity(0.3))
                                                .foregroundColor(.yellow)
                                                .cornerRadius(4)
                                        }
                                    }

                                    if let ping = participant.pingMs, ping > 0 {
                                        Text("\(Int(ping)) ms")
                                            .font(.caption2)
                                            .foregroundColor(.secondary)
                                    }
                                }

                                Spacer()

                                if playerViewModel.syncPlayClient.isHost, !isMe {
                                    Button("Make Host") {
                                        playerViewModel.transferSyncPlayHost(targetSessionId: participant.sessionId)
                                    }
                                    .font(.caption.bold())
                                    .buttonStyle(.bordered)
                                }
                            }
                            .padding(.vertical, 2)
                        }
                    }

                    Section {
                        Button(role: .destructive, action: {
                            playerViewModel.leaveSyncPlayRoom()
                            dismiss()
                        }) {
                            HStack {
                                Spacer()
                                Label("Leave Watch Party", systemImage: "rectangle.portrait.and.arrow.right")
                                    .font(.body.bold())
                                Spacer()
                            }
                        }
                    }
                } else {
                    // Not connected: Join or Create Room
                    Section("Join Watch Party") {
                        TextField("Your Display Name", text: $userName)
                            .textContentType(.name)

                        TextField("6-Letter Room Code", text: $roomCodeInput)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .font(.system(.body, design: .monospaced))
                            .onChange(of: roomCodeInput) { newValue in
                                if newValue.count > 6 {
                                    roomCodeInput = String(newValue.prefix(6))
                                }
                            }

                        Button(action: {
                            guard roomCodeInput.count == 6, !userName.trimmingCharacters(in: .whitespaces).isEmpty else { return }
                            isBusy = true
                            errorMessage = nil
                            Task {
                                do {
                                    try await playerViewModel.joinSyncPlayRoom(
                                        roomCode: roomCodeInput.uppercased(),
                                        userName: userName
                                    )
                                    isBusy = false
                                } catch {
                                    isBusy = false
                                    errorMessage = error.localizedDescription
                                }
                            }
                        }) {
                            HStack {
                                Spacer()
                                if isBusy {
                                    ProgressView()
                                } else {
                                    Text("Join Party")
                                        .font(.body.bold())
                                }
                                Spacer()
                            }
                        }
                        .disabled(roomCodeInput.count != 6 || userName.trimmingCharacters(in: .whitespaces).isEmpty || isBusy)
                    }

                    Section("Create New Party") {
                        Button(action: {
                            guard !userName.trimmingCharacters(in: .whitespaces).isEmpty else { return }
                            isBusy = true
                            errorMessage = nil
                            Task {
                                do {
                                    _ = try await playerViewModel.createSyncPlayRoom(userName: userName)
                                    isBusy = false
                                } catch {
                                    isBusy = false
                                    errorMessage = error.localizedDescription
                                }
                            }
                        }) {
                            HStack {
                                Spacer()
                                if isBusy {
                                    ProgressView()
                                } else {
                                    Label("Create Watch Party", systemImage: "person.2.badge.gearshape.fill")
                                        .font(.body.bold())
                                }
                                Spacer()
                            }
                        }
                        .disabled(userName.trimmingCharacters(in: .whitespaces).isEmpty || isBusy)
                    }
                }
            }
            .navigationTitle("SyncPlay")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
        }
    }
}
