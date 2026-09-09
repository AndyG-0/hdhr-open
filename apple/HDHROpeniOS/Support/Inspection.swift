import Combine
import SwiftUI

/// ViewInspector's documented "Approach #2" hook for inspecting views with `@State`
/// after a tap-driven mutation - see the vendored package's guide.md. Intentionally
/// kept `internal`: it must live in the app target (not HDHROpenKit, a separate
/// module) but should never be part of the app's public surface.
final class Inspection<V> {
    let notice = PassthroughSubject<UInt, Never>()
    var callbacks = [UInt: (V) -> Void]()

    func visit(_ view: V, _ line: UInt) {
        if let callback = callbacks.removeValue(forKey: line) {
            callback(view)
        }
    }
}
