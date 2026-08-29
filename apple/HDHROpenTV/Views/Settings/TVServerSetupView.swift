import SwiftUI
import HDHROpenKit

public struct TVServerSetupView: View {
    @EnvironmentObject private var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss

    public init() {}

    public var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(alignment: .leading, spacing: 28) {
                Text("Server Setup")
                    .font(.largeTitle.bold())
                    .foregroundColor(.white)
                    .padding(.horizontal, 48)
                    .padding(.top, 24)

                TVServerConnectionFields()
                    .padding(24)
                    .background(Color(white: 0.12))
                    .cornerRadius(16)
                    .padding(.horizontal, 48)

                Button("Done") { dismiss() }
                    .padding(.horizontal, 48)

                Spacer()
            }
        }
        .onDisappear {
            Task { await authManager.fetchProfiles() }
        }
    }
}
