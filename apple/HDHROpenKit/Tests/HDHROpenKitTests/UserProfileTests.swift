import XCTest
@testable import HDHROpenKit

final class UserProfileTests: XCTestCase {
    // MARK: - UserRole

    func testDecodeUserRoleAdmin() throws {
        let role = try JSONDecoder().decode(UserRole.self, from: XCTUnwrap("\"admin\"".data(using: .utf8)))
        XCTAssertEqual(role, .admin)
    }

    func testDecodeUserRoleMember() throws {
        let role = try JSONDecoder().decode(UserRole.self, from: XCTUnwrap("\"member\"".data(using: .utf8)))
        XCTAssertEqual(role, .member)
    }

    func testDecodeUserRoleUnknownRawValueThrows() throws {
        XCTAssertThrowsError(
            try JSONDecoder().decode(UserRole.self, from: XCTUnwrap("\"superadmin\"".data(using: .utf8)))
        ) { error in
            guard case DecodingError.dataCorrupted = error else {
                XCTFail("Expected dataCorrupted error, got \(error)")
                return
            }
        }
    }

    func testEncodeUserRoleRawValue() throws {
        let data = try JSONEncoder().encode(UserRole.admin)
        XCTAssertEqual(String(data: data, encoding: .utf8), "\"admin\"")
    }

    // MARK: - UserProfile

    func testDecodeUserProfileAllFieldsPresent() throws {
        let json = """
        {"id": "user_1", "name": "Andy", "avatar": "avatar_3.png", "has_pin": true}
        """.data(using: .utf8)!

        let profile = try JSONDecoder().decode(UserProfile.self, from: json)
        XCTAssertEqual(profile.id, "user_1")
        XCTAssertEqual(profile.name, "Andy")
        XCTAssertEqual(profile.avatar, "avatar_3.png")
        XCTAssertTrue(profile.hasPin)
    }

    func testDecodeUserProfileOptionalAvatarAbsent() throws {
        let json = """
        {"id": "user_2", "name": "Guest", "has_pin": false}
        """.data(using: .utf8)!

        let profile = try JSONDecoder().decode(UserProfile.self, from: json)
        XCTAssertNil(profile.avatar)
        XCTAssertFalse(profile.hasPin)
    }

    func testUserProfileInitDefaults() {
        let profile = UserProfile(id: "user_3", name: "Default")
        XCTAssertNil(profile.avatar)
        XCTAssertFalse(profile.hasPin)
    }

    func testEncodeDecodeUserProfileRoundTrip() throws {
        let original = UserProfile(id: "user_4", name: "Jamie", avatar: "avatar_1.png", hasPin: true)
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(UserProfile.self, from: data)
        XCTAssertEqual(decoded.id, original.id)
        XCTAssertEqual(decoded.avatar, original.avatar)
        XCTAssertEqual(decoded.hasPin, original.hasPin)

        let dict = try encodeToDictionary(original)
        XCTAssertEqual(dict["has_pin"] as? Bool, true)
        XCTAssertNil(dict["hasPin"])
    }

    func testUserProfileHashableEquality() {
        let a = UserProfile(id: "user_5", name: "Same")
        let b = UserProfile(id: "user_5", name: "Same")
        let c = UserProfile(id: "user_6", name: "Different")
        XCTAssertEqual(a, b)
        XCTAssertNotEqual(a, c)
        XCTAssertEqual(Set([a, b, c]).count, 2)
    }

    // MARK: - CurrentUser

    func testDecodeCurrentUserAdmin() throws {
        let json = """
        {"id": "user_7", "name": "Andy", "avatar": null, "role": "admin", "token": "tok_abc"}
        """.data(using: .utf8)!

        let user = try JSONDecoder().decode(CurrentUser.self, from: json)
        XCTAssertEqual(user.id, "user_7")
        XCTAssertEqual(user.role, .admin)
        XCTAssertTrue(user.isAdmin)
        XCTAssertEqual(user.token, "tok_abc")
        XCTAssertNil(user.avatar)
    }

    func testDecodeCurrentUserMemberIsNotAdmin() throws {
        let json = """
        {"id": "user_8", "name": "Guest", "role": "member", "token": null}
        """.data(using: .utf8)!

        let user = try JSONDecoder().decode(CurrentUser.self, from: json)
        XCTAssertEqual(user.role, .member)
        XCTAssertFalse(user.isAdmin)
        XCTAssertNil(user.token)
    }

    func testCurrentUserInitDefaults() {
        let user = CurrentUser(id: "user_9", name: "Defaulted")
        XCTAssertNil(user.avatar)
        XCTAssertEqual(user.role, .member)
        XCTAssertNil(user.token)
        XCTAssertFalse(user.isAdmin)
    }

    func testEncodeDecodeCurrentUserRoundTrip() throws {
        let original = CurrentUser(id: "user_10", name: "Robin", avatar: "a.png", role: .admin, token: "tok_xyz")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(CurrentUser.self, from: data)
        XCTAssertEqual(decoded.role, .admin)
        XCTAssertTrue(decoded.isAdmin)
        XCTAssertEqual(decoded.token, "tok_xyz")
    }

    func testCurrentUserHashableEquality() {
        let a = CurrentUser(id: "user_11", name: "Same", role: .member)
        let b = CurrentUser(id: "user_11", name: "Same", role: .member)
        let c = CurrentUser(id: "user_12", name: "Diff", role: .admin)
        XCTAssertEqual(a, b)
        XCTAssertNotEqual(a, c)
    }

    // MARK: - UserPreferences

    func testDecodeUserPreferencesAllFieldsPresent() throws {
        let json = """
        {"theme": "dark", "locale": "en_US"}
        """.data(using: .utf8)!

        let prefs = try JSONDecoder().decode(UserPreferences.self, from: json)
        XCTAssertEqual(prefs.theme, "dark")
        XCTAssertEqual(prefs.locale, "en_US")
    }

    func testDecodeUserPreferencesFieldsAbsent() throws {
        let json = "{}".data(using: .utf8)!

        let prefs = try JSONDecoder().decode(UserPreferences.self, from: json)
        XCTAssertNil(prefs.theme)
        XCTAssertNil(prefs.locale)
    }

    func testUserPreferencesInitDefaults() {
        let prefs = UserPreferences()
        XCTAssertNil(prefs.theme)
        XCTAssertNil(prefs.locale)
    }

    func testEncodeDecodeUserPreferencesRoundTrip() throws {
        var original = UserPreferences(theme: "light", locale: "fr_FR")
        original.theme = "auto"
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(UserPreferences.self, from: data)
        XCTAssertEqual(decoded.theme, "auto")
        XCTAssertEqual(decoded.locale, "fr_FR")
    }

    // MARK: - SetupStatus

    func testDecodeSetupStatusNeedsSetupTrue() throws {
        let json = """
        {"needs_setup": true}
        """.data(using: .utf8)!

        let status = try JSONDecoder().decode(SetupStatus.self, from: json)
        XCTAssertTrue(status.needsSetup)
    }

    func testDecodeSetupStatusNeedsSetupFalse() throws {
        let json = """
        {"needs_setup": false}
        """.data(using: .utf8)!

        let status = try JSONDecoder().decode(SetupStatus.self, from: json)
        XCTAssertFalse(status.needsSetup)
    }

    func testEncodeDecodeSetupStatusRoundTrip() throws {
        let json = """
        {"needs_setup": true}
        """.data(using: .utf8)!
        let status = try JSONDecoder().decode(SetupStatus.self, from: json)
        let data = try JSONEncoder().encode(status)
        let dict = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(dict["needs_setup"] as? Bool, true)
        let redecoded = try JSONDecoder().decode(SetupStatus.self, from: data)
        XCTAssertTrue(redecoded.needsSetup)
    }

    // MARK: - HouseholdUser

    func testDecodeHouseholdUserAllFieldsPresent() throws {
        let json = """
        {
            "id": "user_13",
            "name": "Family Member",
            "avatar": "avatar_2.png",
            "has_pin": true,
            "role": "member",
            "created_at": "2026-01-15T08:00:00Z"
        }
        """.data(using: .utf8)!

        let user = try JSONDecoder().decode(HouseholdUser.self, from: json)
        XCTAssertEqual(user.id, "user_13")
        XCTAssertEqual(user.name, "Family Member")
        XCTAssertEqual(user.avatar, "avatar_2.png")
        XCTAssertTrue(user.hasPin)
        XCTAssertEqual(user.role, .member)
        XCTAssertEqual(user.createdAt, "2026-01-15T08:00:00Z")
    }

    func testDecodeHouseholdUserOptionalAvatarAbsent() throws {
        let json = """
        {
            "id": "user_14",
            "name": "Admin User",
            "has_pin": false,
            "role": "admin",
            "created_at": "2026-01-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        let user = try JSONDecoder().decode(HouseholdUser.self, from: json)
        XCTAssertNil(user.avatar)
        XCTAssertEqual(user.role, .admin)
    }

    func testDecodeHouseholdUserUnknownRoleThrows() {
        let json = """
        {
            "id": "user_15",
            "name": "Weird Role",
            "has_pin": false,
            "role": "superuser",
            "created_at": "2026-01-01T00:00:00Z"
        }
        """.data(using: .utf8)!

        XCTAssertThrowsError(try JSONDecoder().decode(HouseholdUser.self, from: json))
    }

    func testEncodeDecodeHouseholdUserRoundTrip() throws {
        let json = """
        {
            "id": "user_16",
            "name": "Round Trip",
            "avatar": null,
            "has_pin": true,
            "role": "admin",
            "created_at": "2026-02-02T00:00:00Z"
        }
        """.data(using: .utf8)!

        let user = try JSONDecoder().decode(HouseholdUser.self, from: json)
        let data = try JSONEncoder().encode(user)
        let redecoded = try JSONDecoder().decode(HouseholdUser.self, from: data)
        XCTAssertEqual(redecoded.id, "user_16")
        XCTAssertEqual(redecoded.role, .admin)
        XCTAssertEqual(redecoded.createdAt, "2026-02-02T00:00:00Z")

        let dict = try encodeToDictionary(user)
        XCTAssertEqual(dict["has_pin"] as? Bool, true)
        XCTAssertEqual(dict["created_at"] as? String, "2026-02-02T00:00:00Z")
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
