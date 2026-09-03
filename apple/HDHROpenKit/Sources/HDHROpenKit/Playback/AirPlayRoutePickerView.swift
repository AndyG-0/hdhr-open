#if canImport(UIKit)
import SwiftUI
import AVKit
import UIKit

/// Bridges `AVRoutePickerView` (the system AirPlay route-picker button) into
/// SwiftUI - there's no native SwiftUI equivalent. Mirrors `PlayerLayerView`'s
/// `UIViewRepresentable` pattern in this same directory.
public struct AirPlayRoutePickerView: UIViewRepresentable {
    public var tintColor: UIColor

    public init(tintColor: UIColor = .white) {
        self.tintColor = tintColor
    }

    public func makeUIView(context: Context) -> AVRoutePickerView {
        let view = AVRoutePickerView()
        view.tintColor = tintColor
        view.prioritizesVideoDevices = true
        return view
    }

    public func updateUIView(_ uiView: AVRoutePickerView, context: Context) {
        uiView.tintColor = tintColor
    }
}
#endif
