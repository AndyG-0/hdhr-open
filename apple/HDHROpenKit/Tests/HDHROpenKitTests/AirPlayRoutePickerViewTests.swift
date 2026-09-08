import XCTest
@testable import HDHROpenKit

#if canImport(UIKit)
    import AVKit
    import SwiftUI
    import UIKit
    import ViewInspector

    /// `AVRoutePickerView` (and `UIViewRepresentableContext`) are UIKit-only
    /// types with no public initializer SwiftUI exposes for tests to
    /// construct directly, so `makeUIView`/`updateUIView` can't be called in
    /// isolation. Instead these tests use ViewInspector's `ViewHosting`,
    /// which drives the representable through a real (offscreen) SwiftUI
    /// host and hands back the concrete `AVRoutePickerView` it produced -
    /// this whole file is a no-op when `swift test` runs against the host
    /// macOS platform (no UIKit); it only actually exercises anything in an
    /// iOS/tvOS simulator test run.
    @MainActor
    final class AirPlayRoutePickerViewTests: XCTestCase {
        func test_makeUIView_producesAVRoutePickerView() throws {
            let view = AirPlayRoutePickerView(tintColor: .red)
            ViewHosting.host(view: view)
            defer { ViewHosting.expel() }

            let picker = try view.uiView()

            XCTAssertEqual(picker.tintColor, .red)
        }

        func test_makeUIView_prioritizesVideoDevices() throws {
            let view = AirPlayRoutePickerView(tintColor: .white)
            ViewHosting.host(view: view)
            defer { ViewHosting.expel() }

            let picker = try view.uiView()

            XCTAssertTrue(picker.prioritizesVideoDevices)
        }

        func test_defaultInit_usesWhiteTintColor() {
            let view = AirPlayRoutePickerView()

            XCTAssertEqual(view.tintColor, .white)
        }

        func test_init_storesProvidedTintColor() {
            let view = AirPlayRoutePickerView(tintColor: .systemBlue)

            XCTAssertEqual(view.tintColor, .systemBlue)
        }
    }
#endif
