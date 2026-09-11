import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

/// Tracks whether a `pollingInspection` attempt has already succeeded, so later
/// checkpoints become no-ops instead of re-running (and possibly re-triggering)
/// an action that already fired.
@MainActor
final class InspectionPollResult {
    private(set) var succeeded = false
    fileprivate func markSucceeded() {
        succeeded = true
    }
}

/// Schedules `attempt` across five increasing `inspect(after:)` checkpoints and
/// stops retrying once it first returns `true`, instead of gambling that one
/// fixed delay is "long enough" for an async UI transition to have landed.
/// Converges immediately in the common case and tolerates arbitrary CI slowness
/// up to the last checkpoint. `Inspection.callbacks` is keyed by call-site line
/// number, so each checkpoint needs its own source line here - a loop would
/// collide and silently drop all but the last registered callback.
@MainActor
func pollingInspection<V: View>(
    on inspection: Inspection<V>,
    at checkpoints: (TimeInterval, TimeInterval, TimeInterval, TimeInterval, TimeInterval),
    attempt: @escaping (InspectableView<ViewType.View<V>>) throws -> Bool
) -> (expectations: [XCTestExpectation], result: InspectionPollResult) {
    let result = InspectionPollResult()
    func attemptIfNotYetSucceeded(_ view: InspectableView<ViewType.View<V>>) throws {
        guard !result.succeeded else { return }
        if try attempt(view) {
            result.markSucceeded()
        }
    }
    let exp1 = inspection.inspect(after: checkpoints.0) { view in try attemptIfNotYetSucceeded(view) }
    let exp2 = inspection.inspect(after: checkpoints.1) { view in try attemptIfNotYetSucceeded(view) }
    let exp3 = inspection.inspect(after: checkpoints.2) { view in try attemptIfNotYetSucceeded(view) }
    let exp4 = inspection.inspect(after: checkpoints.3) { view in try attemptIfNotYetSucceeded(view) }
    let exp5 = inspection.inspect(after: checkpoints.4) { view in try attemptIfNotYetSucceeded(view) }
    return ([exp1, exp2, exp3, exp4, exp5], result)
}
