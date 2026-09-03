import XCTest
@testable import HDHROpenKit

final class LoadingQuipsTests: XCTestCase {

    func testDefaultQuipsNotEmpty() {
        XCTAssertGreaterThanOrEqual(LoadingQuips.defaultQuips.count, 20)
        for quip in LoadingQuips.defaultQuips {
            XCTAssertFalse(quip.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
    }

    func testRandomQuipWithoutExclusion() {
        let quip = LoadingQuips.random()
        XCTAssertTrue(LoadingQuips.defaultQuips.contains(quip))
    }

    func testRandomQuipExcludesPrevious() {
        let previous = LoadingQuips.defaultQuips[0]
        for _ in 0..<20 {
            let next = LoadingQuips.random(excluding: previous)
            XCTAssertNotEqual(previous, next)
            XCTAssertTrue(LoadingQuips.defaultQuips.contains(next))
        }
    }

    func testRandomQuipEdgeCases() {
        XCTAssertEqual(LoadingQuips.random(excluding: nil, from: ["Single"]), "Single")
        XCTAssertEqual(LoadingQuips.random(excluding: "Single", from: ["Single"]), "Single")
        XCTAssertEqual(LoadingQuips.random(excluding: nil, from: []), "Loading…")
    }
}
