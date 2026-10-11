import XCTest
@testable import HDHROpenKit

final class DiscoveryTests: XCTestCase {
    func testDecodesHasProfileFromSnakeCase() throws {
        let json = """
        {"enabled": true, "has_profile": true, "items": [{"title": "Show A", "channel_number": "4.1"}]}
        """
        let response = try JSONDecoder().decode(DiscoveryResponse.self, from: Data(json.utf8))

        XCTAssertTrue(response.enabled)
        XCTAssertTrue(response.hasProfile)
        XCTAssertEqual(response.items.map(\.title), ["Show A"])
    }

    func testDecodesDisabledFallbackShape() throws {
        let json = """
        {"enabled": false, "has_profile": false, "items": []}
        """
        let response = try JSONDecoder().decode(DiscoveryResponse.self, from: Data(json.utf8))

        XCTAssertFalse(response.enabled)
        XCTAssertFalse(response.hasProfile)
        XCTAssertTrue(response.items.isEmpty)
    }

    func testDecodesBucketAndSourceFromSnakeCase() throws {
        let json = """
        {"enabled": true, "has_profile": true, "items": [
            {"title": "Oscar Marathon", "bucket": "movies", "source": "network_pick"}
        ]}
        """
        let response = try JSONDecoder().decode(DiscoveryResponse.self, from: Data(json.utf8))

        XCTAssertEqual(response.items.first?.bucket, "movies")
        XCTAssertEqual(response.items.first?.source, "network_pick")
    }

    func testMemberwiseInit() {
        let response = DiscoveryResponse(enabled: true, hasProfile: false, items: [HDHomeRunGuideEntry(title: "T")])

        XCTAssertTrue(response.enabled)
        XCTAssertFalse(response.hasProfile)
        XCTAssertEqual(response.items.count, 1)
    }
}
