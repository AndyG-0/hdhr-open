import SwiftUI
import HDHROpenKit

public struct TVPINEntryView: View {
    @EnvironmentObject private var authViewModel: AuthViewModel

    private let digits: [[String]] = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["delete", "0", "submit"]
    ]

    public init() {}

    public var body: some View {
        ZStack {
            Color.black.opacity(0.9).ignoresSafeArea()

            VStack(spacing: 28) {
                if let profile = authViewModel.selectedProfile {
                    Text("Enter PIN for \(profile.name)")
                        .font(.title.bold())
                        .foregroundColor(Theme.textPrimary)
                }

                // PIN Dots
                HStack(spacing: 16) {
                    ForEach(0..<max(authViewModel.pinInput.count, 4), id: \.self) { idx in
                        Circle()
                            .fill(idx < authViewModel.pinInput.count ? Theme.textPrimary : Theme.appBorder)
                            .frame(width: 20, height: 20)
                    }
                }
                .padding(.vertical, 12)

                if let err = authViewModel.errorMessage {
                    Text(err)
                        .font(.callout.bold())
                        .foregroundColor(.red)
                }

                // Keypad Grid
                VStack(spacing: 12) {
                    ForEach(digits, id: \.self) { row in
                        HStack(spacing: 12) {
                            ForEach(row, id: \.self) { key in
                                keyButton(for: key)
                            }
                        }
                    }
                }

                Button("Cancel") {
                    authViewModel.cancelPINEntry()
                }
                .padding(.top, 12)
            }
            .padding(48)
            .background(Theme.appSurface)
            .cornerRadius(24)
        }
    }

    @ViewBuilder
    private func keyButton(for key: String) -> some View {
        Button(action: {
            if key == "delete" {
                authViewModel.deletePINDigit()
            } else if key == "submit" {
                Task { await authViewModel.submitPIN() }
            } else {
                authViewModel.appendPINDigit(key)
            }
        }) {
            Group {
                if key == "delete" {
                    Image(systemName: "delete.left.fill")
                        .font(.title2)
                } else if key == "submit" {
                    Image(systemName: "checkmark")
                        .font(.title2)
                } else {
                    Text(key)
                        .font(.title.bold())
                }
            }
            .frame(width: 80, height: 70)
        }
    }
}
