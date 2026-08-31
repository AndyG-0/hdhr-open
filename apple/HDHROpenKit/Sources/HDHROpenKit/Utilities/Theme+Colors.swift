import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

// Centralized neutral color tokens, parallel to Android's Color.kt. Dark values
// match what tvOS shipped hardcoded before this file existed; light values are
// new. Each token tracks whatever `.preferredColorScheme` resolves to (explicit
// pick or system) with no per-view observation code required.
public enum Theme {
    public static let appBackground = dynamicColor(light: (0xF2, 0xF2, 0xF7), dark: (0x00, 0x00, 0x00))
    public static let appSurface = dynamicColor(light: (0xFF, 0xFF, 0xFF), dark: (0x1F, 0x1F, 0x1F))
    public static let appSurfaceVariant = dynamicColor(light: (0xE5, 0xE5, 0xEA), dark: (0x2E, 0x2E, 0x2E))
    public static let appBorder = dynamicColor(light: (0xD1, 0xD1, 0xD6), dark: (0x4D, 0x4D, 0x4D))

    public static let textPrimary = dynamicColor(light: (0x1C, 0x1C, 0x1E), dark: (0xFF, 0xFF, 0xFF))
    public static let textSecondary = dynamicColor(light: (0x3A, 0x3A, 0x3C), dark: (0x8E, 0x8E, 0x93))
    public static let textMuted = dynamicColor(light: (0x8E, 0x8E, 0x93), dark: (0x70, 0x70, 0x78))

    // A fixed subtle tint for "selected/active" backgrounds - the brand blue
    // itself doesn't change between themes, so this needs no light/dark split.
    public static let accentSubtle = Color.blue.opacity(0.15)

    private static func dynamicColor(light: (UInt8, UInt8, UInt8), dark: (UInt8, UInt8, UInt8)) -> Color {
        #if canImport(UIKit)
        return Color(uiColor: UIColor(dynamicProvider: { traits in
            let rgb = traits.userInterfaceStyle == .dark ? dark : light
            return UIColor(
                red: CGFloat(rgb.0) / 255,
                green: CGFloat(rgb.1) / 255,
                blue: CGFloat(rgb.2) / 255,
                alpha: 1
            )
        }))
        #else
        return Color(red: Double(light.0) / 255, green: Double(light.1) / 255, blue: Double(light.2) / 255)
        #endif
    }
}
