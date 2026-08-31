import Foundation
#if os(iOS) || os(tvOS)
import UIKit
#endif

/// Fires `operation` in a detached, best-effort task, requesting a brief
/// grace period from the OS first. Without this, a stop/release request
/// issued right as the app backgrounds can be cut off mid-flight by
/// suspension before it reaches the server.
@MainActor
func runWithBackgroundGrace(name: String, operation: @escaping @Sendable () async -> Void) {
    #if os(iOS) || os(tvOS)
    var taskId: UIBackgroundTaskIdentifier = .invalid
    taskId = UIApplication.shared.beginBackgroundTask(withName: name) {
        UIApplication.shared.endBackgroundTask(taskId)
        taskId = .invalid
    }
    Task {
        await operation()
        if taskId != .invalid {
            UIApplication.shared.endBackgroundTask(taskId)
        }
    }
    #else
    Task {
        await operation()
    }
    #endif
}
