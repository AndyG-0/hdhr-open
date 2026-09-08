import XCTest
@testable import HDHROpenKit

/// Tracks completions from a `@Sendable` closure without capturing a mutable
/// var directly (which `@Sendable` closures cannot do).
private actor Counter {
    private(set) var value = 0

    func increment() {
        value += 1
    }
}

final class BackgroundGraceTaskTests: XCTestCase {
    @MainActor
    func testOperationEventuallyExecutes() async {
        let expectation = expectation(description: "operation executes")
        runWithBackgroundGrace(name: "test-task") {
            expectation.fulfill()
        }
        await fulfillment(of: [expectation], timeout: 1.0)
    }

    @MainActor
    func testOperationExecutesExactlyOnce() async {
        let counter = Counter()
        let expectation = expectation(description: "operation executes once")
        runWithBackgroundGrace(name: "count-task") {
            await counter.increment()
            expectation.fulfill()
        }
        await fulfillment(of: [expectation], timeout: 1.0)
        let count = await counter.value
        XCTAssertEqual(count, 1)
    }

    @MainActor
    func testMultipleInvocationsEachExecuteIndependently() async {
        let expectation1 = expectation(description: "first operation executes")
        let expectation2 = expectation(description: "second operation executes")
        runWithBackgroundGrace(name: "task-1") {
            expectation1.fulfill()
        }
        runWithBackgroundGrace(name: "task-2") {
            expectation2.fulfill()
        }
        await fulfillment(of: [expectation1, expectation2], timeout: 1.0)
    }

    @MainActor
    func testOperationCanPerformAsyncWorkBeforeCompleting() async {
        let counter = Counter()
        let expectation = expectation(description: "async operation completes")
        runWithBackgroundGrace(name: "async-task") {
            try? await Task.sleep(nanoseconds: 10_000_000) // 10ms
            await counter.increment()
            expectation.fulfill()
        }
        await fulfillment(of: [expectation], timeout: 1.0)
        let count = await counter.value
        XCTAssertEqual(count, 1)
    }

    @MainActor
    func testEmptyNameDoesNotPreventOperationFromRunning() async {
        let expectation = expectation(description: "operation executes with empty name")
        runWithBackgroundGrace(name: "") {
            expectation.fulfill()
        }
        await fulfillment(of: [expectation], timeout: 1.0)
    }
}
