import SwiftUI
import HDHROpenKit

public struct TVSyncPlayOverlay: View {
    @ObservedObject var playerViewModel: PlayerViewModel
    let onDismiss: () -> Void

    @State private var userName: String = "Apple TV"
    @State private var roomCodeInput: String = ""
    @State private var isBusy: Bool = false
    @State private var errorMessage: String? = nil
    @FocusState private var focusedElement: TVSyncPlayFocus?

    private enum TVSyncPlayFocus: Hashable {
        case close
        case nameField
        case codeField
        case joinButton
        case createButton
        case leaveButton
        case participant(String)
    }

    public init(playerViewModel: PlayerViewModel, onDismiss: @escaping () -> Void) {
        self.playerViewModel = playerViewModel
        self.onDismiss = onDismiss
    }

    public var body: some View {
        ZStack {
            Color.black.opacity(0.85).ignoresSafeArea()

            VStack(alignment: .leading, spacing: 28) {
                // Top Header
                HStack {
                    Image(systemName: "person.2.fill")
                        .font(.title2)
                        .foregroundColor(.cyan)
                    Text("SyncPlay Watch Party")
                        .font(.title2.bold())
                        .foregroundColor(Theme.textPrimary)

                    Spacer()

                    Button("Close", action: onDismiss)
                        .focused($focusedElement, equals: .close)
                }

                Divider().background(Theme.appBorder)

                if let err = errorMessage {
                    Text(err)
                        .font(.callout)
                        .foregroundColor(.red)
                }

                if let room = playerViewModel.syncPlayClient.room, playerViewModel.syncPlayClient.isConnected {
                    // Active Room State
                    HStack(alignment: .top, spacing: 48) {
                        // Room Info Card
                        VStack(alignment: .leading, spacing: 16) {
                            Text("ROOM CODE")
                                .font(.caption.bold())
                                .foregroundColor(.secondary)
                            Text(room.roomCode)
                                .font(.system(size: 44, weight: .black, design: .monospaced))
                                .tracking(6)
                                .foregroundColor(.cyan)

                            if let content = room.currentContent {
                                Text("Playing: \(content.title.isEmpty ? (content.channelNumber ?? "Live Stream") : content.title)")
                                    .font(.headline)
                                    .foregroundColor(.white)
                                    .lineLimit(2)
                            }

                            Spacer()

                            Button(action: {
                                playerViewModel.leaveSyncPlayRoom()
                                onDismiss()
                            }) {
                                HStack {
                                    Image(systemName: "rectangle.portrait.and.arrow.right")
                                    Text("Leave Watch Party")
                                        .fontWeight(.bold)
                                }
                                .foregroundColor(.red)
                            }
                            .focused($focusedElement, equals: .leaveButton)
                        }
                        .frame(width: 380)

                        // Participants List
                        VStack(alignment: .leading, spacing: 16) {
                            Text("Participants (\(playerViewModel.syncPlayClient.participants.count))")
                                .font(.headline)
                                .foregroundColor(.secondary)

                            ScrollView {
                                VStack(spacing: 12) {
                                    ForEach(playerViewModel.syncPlayClient.participants) { participant in
                                        let isMe = participant.sessionId == playerViewModel.syncPlayClient.sessionId
                                        HStack {
                                            Text(participant.userName + (isMe ? " (You)" : ""))
                                                .font(.body.weight(.medium))
                                                .foregroundColor(.white)

                                            if participant.isHost {
                                                Text("HOST")
                                                    .font(.caption2.bold())
                                                    .padding(.horizontal, 8)
                                                    .padding(.vertical, 4)
                                                    .background(Color.yellow.opacity(0.3))
                                                    .foregroundColor(.yellow)
                                                    .cornerRadius(6)
                                            }

                                            Spacer()

                                            if let ping = participant.pingMs, ping > 0 {
                                                Text("\(Int(ping)) ms")
                                                    .font(.caption)
                                                    .foregroundColor(.gray)
                                            }

                                            if playerViewModel.syncPlayClient.isHost && !isMe {
                                                Button("Make Host") {
                                                    playerViewModel.transferSyncPlayHost(targetSessionId: participant.sessionId)
                                                }
                                                .font(.caption.bold())
                                                .focused($focusedElement, equals: .participant(participant.sessionId))
                                            }
                                        }
                                        .padding(.horizontal, 16)
                                        .padding(.vertical, 10)
                                        .background(Color.white.opacity(0.1))
                                        .cornerRadius(10)
                                    }
                                }
                            }
                        }
                    }
                    .frame(maxHeight: 400)
                } else {
                    // Not connected: Join / Create UI
                    HStack(alignment: .top, spacing: 60) {
                        VStack(alignment: .leading, spacing: 20) {
                            Text("Join Existing Party")
                                .font(.headline)
                                .foregroundColor(.secondary)

                            TextField("Display Name", text: $userName)
                                .focused($focusedElement, equals: .nameField)

                            TextField("6-Letter Room Code", text: $roomCodeInput)
                                .focused($focusedElement, equals: .codeField)

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
                                    Text("Join Party")
                                        .font(.headline.bold())
                                    if isBusy {
                                        ProgressView()
                                    }
                                }
                            }
                            .focused($focusedElement, equals: .joinButton)
                            .disabled(roomCodeInput.count != 6 || userName.trimmingCharacters(in: .whitespaces).isEmpty || isBusy)
                        }
                        .frame(maxWidth: .infinity)

                        Divider().background(Theme.appBorder)

                        VStack(alignment: .leading, spacing: 20) {
                            Text("Host New Party")
                                .font(.headline)
                                .foregroundColor(.secondary)

                            Text("Start a synchronized watch party session with your current stream.")
                                .font(.body)
                                .foregroundColor(.gray)

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
                                    Image(systemName: "person.2.badge.gearshape.fill")
                                    Text("Create Watch Party")
                                        .font(.headline.bold())
                                    if isBusy {
                                        ProgressView()
                                    }
                                }
                            }
                            .focused($focusedElement, equals: .createButton)
                            .disabled(userName.trimmingCharacters(in: .whitespaces).isEmpty || isBusy)
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .frame(maxHeight: 380)
                }
            }
            .padding(48)
            .background(Color.black.opacity(0.92))
            .cornerRadius(24)
            .padding(64)
        }
        .onAppear {
            if playerViewModel.syncPlayClient.isConnected {
                focusedElement = .leaveButton
            } else {
                focusedElement = .codeField
            }
        }
    }
}
