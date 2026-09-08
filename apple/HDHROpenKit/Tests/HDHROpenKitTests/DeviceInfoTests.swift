import XCTest
@testable import HDHROpenKit

final class DeviceInfoTests: XCTestCase {
    // MARK: - DeviceInfo

    func testDecodeDeviceInfo() throws {
        let json = """
        {"id": "dev_1", "name": "Living Room Apple TV"}
        """.data(using: .utf8)!

        let device = try JSONDecoder().decode(DeviceInfo.self, from: json)
        XCTAssertEqual(device.id, "dev_1")
        XCTAssertEqual(device.name, "Living Room Apple TV")
    }

    func testEncodeDecodeDeviceInfoRoundTrip() throws {
        let original = DeviceInfo(id: "dev_2", name: "iPhone")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(DeviceInfo.self, from: data)
        XCTAssertEqual(decoded.id, original.id)
        XCTAssertEqual(decoded.name, original.name)

        let dict = try encodeToDictionary(original)
        XCTAssertEqual(dict["id"] as? String, "dev_2")
        XCTAssertEqual(dict["name"] as? String, "iPhone")
    }

    func testDeviceInfoMissingFieldThrows() {
        let json = """
        {"id": "dev_3"}
        """.data(using: .utf8)!

        XCTAssertThrowsError(try JSONDecoder().decode(DeviceInfo.self, from: json))
    }

    // MARK: - DeviceListEntry

    func testDecodeDeviceListEntry() throws {
        let json = """
        {"id": "dev_4", "name": "MacBook Pro", "last_seen_at": "2026-09-06T12:00:00Z"}
        """.data(using: .utf8)!

        let entry = try JSONDecoder().decode(DeviceListEntry.self, from: json)
        XCTAssertEqual(entry.id, "dev_4")
        XCTAssertEqual(entry.name, "MacBook Pro")
        XCTAssertEqual(entry.lastSeenAt, "2026-09-06T12:00:00Z")
    }

    func testDeviceListEntryMissingLastSeenAtThrows() {
        let json = """
        {"id": "dev_5", "name": "iPad"}
        """.data(using: .utf8)!

        XCTAssertThrowsError(try JSONDecoder().decode(DeviceListEntry.self, from: json))
    }

    func testEncodeDecodeDeviceListEntryRoundTrip() throws {
        let original = DeviceListEntry(id: "dev_6", name: "Apple TV", lastSeenAt: "2026-01-01T00:00:00Z")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(DeviceListEntry.self, from: data)
        XCTAssertEqual(decoded.lastSeenAt, original.lastSeenAt)

        let dict = try encodeToDictionary(original)
        XCTAssertEqual(dict["last_seen_at"] as? String, "2026-01-01T00:00:00Z")
        XCTAssertNil(dict["lastSeenAt"])
    }

    // MARK: - DeviceRegisterResult

    func testDecodeDeviceRegisterResultNewDevice() throws {
        let json = """
        {"id": "dev_7", "name": "New Device", "is_new": true}
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(DeviceRegisterResult.self, from: json)
        XCTAssertEqual(result.id, "dev_7")
        XCTAssertEqual(result.name, "New Device")
        XCTAssertTrue(result.isNew)
    }

    func testDecodeDeviceRegisterResultExistingDevice() throws {
        let json = """
        {"id": "dev_8", "name": "Existing Device", "is_new": false}
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(DeviceRegisterResult.self, from: json)
        XCTAssertFalse(result.isNew)
    }

    func testEncodeDecodeDeviceRegisterResultRoundTrip() throws {
        let original = DeviceRegisterResult(id: "dev_9", name: "Device Nine", isNew: true)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(DeviceRegisterResult.self, from: data)
        XCTAssertEqual(decoded.isNew, original.isNew)

        let dict = try encodeToDictionary(original)
        XCTAssertEqual(dict["is_new"] as? Bool, true)
        XCTAssertNil(dict["isNew"])
    }

    private func encodeToDictionary(_ value: some Encodable) throws -> [String: Any] {
        let data = try JSONEncoder().encode(value)
        guard let dict = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            XCTFail("Expected JSON object")
            return [:]
        }
        return dict
    }
}
