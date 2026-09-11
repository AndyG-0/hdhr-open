import Foundation

/// Bounded poll for a condition that becomes true asynchronously (e.g. after a
/// fire-and-forget `Task` completes), instead of guessing a fixed sleep is
/// "long enough". Converges immediately once `condition` is true and only
/// spends real time under genuine CI slowness, up to `timeoutSeconds`.
func pollUntil(timeoutSeconds: TimeInterval = 2.0, condition: () -> Bool) async throws {
    let deadline = Date().addingTimeInterval(timeoutSeconds)
    while !condition() {
        if Date() >= deadline {
            return
        }
        try await Task.sleep(nanoseconds: 20_000_000)
    }
}
