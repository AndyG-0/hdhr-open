import Foundation
import SwiftUI

public enum ThemeMode: String, CaseIterable, Sendable {
    case light
    case dark
    case system

    public var label: String {
        switch self {
        case .light: "Light"
        case .dark: "Dark"
        case .system: "System"
        }
    }
}

@MainActor
public final class ThemeManager: ObservableObject {
    @Published public var mode: ThemeMode {
        didSet {
            UserDefaults.standard.set(mode.rawValue, forKey: modeStorageKey)
        }
    }

    private let modeStorageKey = "org.hdhropen.client.themeMode"

    public init() {
        let stored = UserDefaults.standard.string(forKey: "org.hdhropen.client.themeMode")
        mode = stored.flatMap(ThemeMode.init(rawValue:)) ?? .system
    }

    /// `nil` tells SwiftUI to defer to the OS setting, which already live-updates
    /// on system appearance change with no manual observation needed.
    public var colorScheme: ColorScheme? {
        switch mode {
        case .light: .light
        case .dark: .dark
        case .system: nil
        }
    }
}
