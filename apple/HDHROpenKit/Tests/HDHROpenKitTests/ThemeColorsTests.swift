import SwiftUI
import XCTest
@testable import HDHROpenKit

/// `Theme` is a bag of computed color tokens with no branching logic to
/// exercise directly - these are smoke tests confirming each token is
/// reachable and that visually-distinct tokens aren't accidentally aliased
/// to the same underlying color.
final class ThemeColorsTests: XCTestCase {
    func test_allTokens_areAccessible() {
        let tokens: [Color] = [
            Theme.appBackground,
            Theme.appSurface,
            Theme.appSurfaceVariant,
            Theme.appBorder,
            Theme.textPrimary,
            Theme.textSecondary,
            Theme.textMuted,
            Theme.accentSubtle
        ]

        XCTAssertEqual(tokens.count, 8)
    }

    func test_appBackgroundAndAppSurface_areDistinctTokens() {
        XCTAssertNotEqual(Theme.appBackground, Theme.appSurface)
    }

    func test_appSurfaceAndAppSurfaceVariant_areDistinctTokens() {
        XCTAssertNotEqual(Theme.appSurface, Theme.appSurfaceVariant)
    }

    func test_appBorder_isDistinctFromAppBackground() {
        XCTAssertNotEqual(Theme.appBorder, Theme.appBackground)
    }

    func test_textPrimaryAndTextSecondary_areDistinctTokens() {
        XCTAssertNotEqual(Theme.textPrimary, Theme.textSecondary)
    }

    func test_textSecondaryAndTextMuted_areDistinctTokens() {
        XCTAssertNotEqual(Theme.textSecondary, Theme.textMuted)
    }

    func test_textPrimaryAndTextMuted_areDistinctTokens() {
        XCTAssertNotEqual(Theme.textPrimary, Theme.textMuted)
    }

    /// `accentSubtle` is a fixed brand tint (not routed through the
    /// light/dark `dynamicColor` helper), so unlike the other tokens it can
    /// be compared against a literal expected value on every platform.
    func test_accentSubtle_isBlueAt15PercentOpacity() {
        XCTAssertEqual(Theme.accentSubtle, Color.blue.opacity(0.15))
    }
}
