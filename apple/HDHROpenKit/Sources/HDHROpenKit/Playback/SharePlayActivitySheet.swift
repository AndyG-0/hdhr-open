#if os(iOS)
import SwiftUI
import UIKit
import GroupActivities

/// Wraps `GroupActivitySharingController`'s system SharePlay sheet.
/// iOS/Mac Catalyst only - confirmed `@available(tvOS, unavailable)` in the
/// SDK, so tvOS starts a session via `SharePlayCoordinator.activateOnTV(_:)`
/// instead (see SHARE-1 plan).
///
/// On the Simulator this sheet reliably shows blank and closes itself almost
/// immediately - there's no FaceTime/iCloud sign-in for it to offer
/// destinations from, and `GroupActivitySharingController` doesn't expose a
/// distinct "nothing to share to" state to react to (only `.success` /
/// `.cancelled`, indistinguishable here from a real cancel). That's a
/// Simulator-only limitation; a real device in a FaceTime call presents this
/// sheet normally.
public struct SharePlayActivitySheet: UIViewControllerRepresentable {
    public let activity: WatchProgramActivity
    public var onDismiss: (() -> Void)?

    public init(activity: WatchProgramActivity, onDismiss: (() -> Void)? = nil) {
        self.activity = activity
        self.onDismiss = onDismiss
    }

    public func makeUIViewController(context: Context) -> UIViewController {
        let dismiss = onDismiss
        guard let controller = try? GroupActivitySharingController(activity) else {
            Task { @MainActor in
                dismiss?()
            }
            return UIViewController()
        }
        Task { @MainActor in
            _ = await controller.result
            dismiss?()
        }
        return controller
    }

    public func updateUIViewController(_ uiViewController: UIViewController, context: Context) {}
}
#endif
