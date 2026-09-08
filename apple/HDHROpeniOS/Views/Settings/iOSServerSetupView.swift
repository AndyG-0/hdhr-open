import HDHROpenKit
import SwiftUI

public struct iOSServerSetupView: View {
    @EnvironmentObject private var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss

    public init() {}

    public var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("Server Connection")) {
                    iOSServerConnectionFields()
                }
            }
            .navigationTitle("Server Setup")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .onDisappear {
                Task { await authManager.fetchProfiles() }
            }
        }
    }
}
