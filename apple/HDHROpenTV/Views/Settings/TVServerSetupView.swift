import SwiftUI
import HDHROpenKit

public struct TVServerSetupView: View {
    @EnvironmentObject private var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss

    public init() {}

    public var body: some View {
        ZStack {
            Theme.appBackground.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 28) {
                Text("Server Setup")
                    .font(.largeTitle.bold())
                    .foregroundColor(Theme.textPrimary)
                    .padding(.horizontal, 48)
                    .padding(.top, 24)

                TVServerConnectionFields()
                    .padding(24)
                    .background(Theme.appSurface)
                    .cornerRadius(16)
                    .padding(.horizontal, 48)

                HStack {
                    Spacer()
                    Button("Done") { dismiss() }
                }
                .padding(.horizontal, 48)

                Spacer()
            }
        }
        .onDisappear {
            Task { await authManager.fetchProfiles() }
        }
    }
}
