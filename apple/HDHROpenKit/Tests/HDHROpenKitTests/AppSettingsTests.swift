import XCTest
@testable import HDHROpenKit

final class AppSettingsTests: XCTestCase {
    // MARK: - AppSettings

    func testDecodeAppSettingsAllFieldsPresent() throws {
        let json = """
        {
            "timezone": "America/Los_Angeles",
            "guide_provider_priority": "schedules_direct",
            "dvr_server_priority": "hdhomerun"
        }
        """.data(using: .utf8)!

        let settings = try JSONDecoder().decode(AppSettings.self, from: json)
        XCTAssertEqual(settings.timezone, "America/Los_Angeles")
        XCTAssertEqual(settings.guideProviderPriority, "schedules_direct")
        XCTAssertEqual(settings.dvrServerPriority, "hdhomerun")
    }

    func testDecodeAppSettingsAllFieldsAbsent() throws {
        let json = "{}".data(using: .utf8)!

        let settings = try JSONDecoder().decode(AppSettings.self, from: json)
        XCTAssertNil(settings.timezone)
        XCTAssertNil(settings.guideProviderPriority)
        XCTAssertNil(settings.dvrServerPriority)
    }

    func testDecodeAppSettingsExplicitNulls() throws {
        let json = """
        {
            "timezone": null,
            "guide_provider_priority": null,
            "dvr_server_priority": null
        }
        """.data(using: .utf8)!

        let settings = try JSONDecoder().decode(AppSettings.self, from: json)
        XCTAssertNil(settings.timezone)
        XCTAssertNil(settings.guideProviderPriority)
        XCTAssertNil(settings.dvrServerPriority)
    }

    func testAppSettingsInitDefaults() {
        let settings = AppSettings()
        XCTAssertNil(settings.timezone)
        XCTAssertNil(settings.guideProviderPriority)
        XCTAssertNil(settings.dvrServerPriority)
    }

    func testEncodeDecodeAppSettingsRoundTrip() throws {
        let original = AppSettings(
            timezone: "UTC",
            guideProviderPriority: "xmltv",
            dvrServerPriority: "builtin"
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(AppSettings.self, from: data)
        XCTAssertEqual(decoded.timezone, original.timezone)
        XCTAssertEqual(decoded.guideProviderPriority, original.guideProviderPriority)
        XCTAssertEqual(decoded.dvrServerPriority, original.dvrServerPriority)

        let dict = try encodeToDictionary(original)
        XCTAssertEqual(dict["guide_provider_priority"] as? String, "xmltv")
        XCTAssertEqual(dict["dvr_server_priority"] as? String, "builtin")
    }

    // MARK: - HDHomeRunTranscodePreset

    func testDecodeHDHomeRunTranscodePreset() throws {
        let json = """
        {
            "id": "preset_720p",
            "label": "720p",
            "description": "Transcode to 720p H.264",
            "input_args": ["-hwaccel", "auto"],
            "output_args": ["-vf", "scale=1280:720"],
            "hardware": true
        }
        """.data(using: .utf8)!

        let preset = try JSONDecoder().decode(HDHomeRunTranscodePreset.self, from: json)
        XCTAssertEqual(preset.id, "preset_720p")
        XCTAssertEqual(preset.label, "720p")
        XCTAssertEqual(preset.description, "Transcode to 720p H.264")
        XCTAssertEqual(preset.inputArgs, ["-hwaccel", "auto"])
        XCTAssertEqual(preset.outputArgs, ["-vf", "scale=1280:720"])
        XCTAssertTrue(preset.hardware)
    }

    func testEncodeDecodeHDHomeRunTranscodePresetRoundTrip() throws {
        let json = """
        {
            "id": "preset_cpu",
            "label": "Software",
            "description": "CPU-only transcode",
            "input_args": [],
            "output_args": ["-c:v", "libx264"],
            "hardware": false
        }
        """.data(using: .utf8)!

        let preset = try JSONDecoder().decode(HDHomeRunTranscodePreset.self, from: json)
        let data = try JSONEncoder().encode(preset)
        let redecoded = try JSONDecoder().decode(HDHomeRunTranscodePreset.self, from: data)
        XCTAssertEqual(redecoded.id, preset.id)
        XCTAssertEqual(redecoded.inputArgs, preset.inputArgs)
        XCTAssertEqual(redecoded.outputArgs, preset.outputArgs)
        XCTAssertFalse(redecoded.hardware)
    }

    // MARK: - HWAccelDiagnostics

    func testDecodeHWAccelDiagnosticsWithSampleError() throws {
        let json = """
        {
            "device": "videotoolbox",
            "summary": ["Hardware acceleration available", "Encoder: h264_videotoolbox"],
            "sample_error": "Failed to open encoder"
        }
        """.data(using: .utf8)!

        let diagnostics = try JSONDecoder().decode(HWAccelDiagnostics.self, from: json)
        XCTAssertEqual(diagnostics.device, "videotoolbox")
        XCTAssertEqual(diagnostics.summary.count, 2)
        XCTAssertEqual(diagnostics.sampleError, "Failed to open encoder")
    }

    func testDecodeHWAccelDiagnosticsWithoutSampleError() throws {
        let json = """
        {
            "device": "none",
            "summary": []
        }
        """.data(using: .utf8)!

        let diagnostics = try JSONDecoder().decode(HWAccelDiagnostics.self, from: json)
        XCTAssertEqual(diagnostics.device, "none")
        XCTAssertTrue(diagnostics.summary.isEmpty)
        XCTAssertNil(diagnostics.sampleError)
    }

    // MARK: - NetworkIntegration / AnyCodable

    func testDecodeNetworkIntegrationWithMixedSettingsTypes() throws {
        let json = """
        {
            "id": "int_1",
            "type": "webhook",
            "name": "Discord Alerts",
            "settings": {
                "enabled": true,
                "retries": 3,
                "timeout": 2.5,
                "url": "https://example.com/hook",
                "tags": ["alerts", "recording"],
                "nested": {"level": 1},
                "extra": null
            }
        }
        """.data(using: .utf8)!

        let integration = try JSONDecoder().decode(NetworkIntegration.self, from: json)
        XCTAssertEqual(integration.id, "int_1")
        XCTAssertEqual(integration.type, "webhook")
        XCTAssertEqual(integration.name, "Discord Alerts")
        XCTAssertEqual(integration.settings["enabled"]?.value as? Bool, true)
        XCTAssertEqual(integration.settings["retries"]?.value as? Int, 3)
        XCTAssertEqual(integration.settings["timeout"]?.value as? Double, 2.5)
        XCTAssertEqual(integration.settings["url"]?.value as? String, "https://example.com/hook")
        XCTAssertEqual(integration.settings["tags"]?.value as? [String], ["alerts", "recording"])
        let nested = integration.settings["nested"]?.value as? [String: Any]
        XCTAssertEqual(nested?["level"] as? Int, 1)
        XCTAssertTrue(integration.settings["extra"]?.value is NSNull)
    }

    func testNetworkIntegrationIdentifiable() throws {
        let json = """
        {"id": "int_2", "type": "syslog", "name": "Syslog", "settings": {}}
        """.data(using: .utf8)!

        let integration = try JSONDecoder().decode(NetworkIntegration.self, from: json)
        XCTAssertEqual(integration.id, "int_2")
    }

    // MARK: - NetworkTestConnectionResult

    func testDecodeNetworkTestConnectionResultSuccess() throws {
        let json = """
        {"ok": true, "detail": "Connected in 42ms", "error": null}
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(NetworkTestConnectionResult.self, from: json)
        XCTAssertTrue(result.ok)
        XCTAssertEqual(result.detail, "Connected in 42ms")
        XCTAssertNil(result.error)
    }

    func testDecodeNetworkTestConnectionResultFailureMinimal() throws {
        let json = """
        {"ok": false, "error": "Connection refused"}
        """.data(using: .utf8)!

        let result = try JSONDecoder().decode(NetworkTestConnectionResult.self, from: json)
        XCTAssertFalse(result.ok)
        XCTAssertNil(result.detail)
        XCTAssertEqual(result.error, "Connection refused")
    }

    // MARK: - AnyCodable direct tests

    func testAnyCodableDecodesBool() throws {
        let value = try JSONDecoder().decode(AnyCodable.self, from: XCTUnwrap("true".data(using: .utf8)))
        XCTAssertEqual(value.value as? Bool, true)
    }

    func testAnyCodableDecodesInt() throws {
        let value = try JSONDecoder().decode(AnyCodable.self, from: XCTUnwrap("42".data(using: .utf8)))
        XCTAssertEqual(value.value as? Int, 42)
    }

    func testAnyCodableDecodesDouble() throws {
        let value = try JSONDecoder().decode(AnyCodable.self, from: XCTUnwrap("3.14".data(using: .utf8)))
        XCTAssertEqual(value.value as? Double, 3.14)
    }

    func testAnyCodableDecodesString() throws {
        let value = try JSONDecoder().decode(AnyCodable.self, from: XCTUnwrap("\"hello\"".data(using: .utf8)))
        XCTAssertEqual(value.value as? String, "hello")
    }

    func testAnyCodableDecodesArray() throws {
        let value = try JSONDecoder().decode(AnyCodable.self, from: XCTUnwrap("[1, 2, 3]".data(using: .utf8)))
        XCTAssertEqual(value.value as? [Int], [1, 2, 3])
    }

    func testAnyCodableDecodesDictionary() throws {
        let value = try JSONDecoder().decode(AnyCodable.self, from: XCTUnwrap("{\"a\": 1}".data(using: .utf8)))
        let dict = value.value as? [String: Any]
        XCTAssertEqual(dict?["a"] as? Int, 1)
    }

    func testAnyCodableDecodesNullAsNSNull() throws {
        let value = try JSONDecoder().decode(AnyCodable.self, from: XCTUnwrap("null".data(using: .utf8)))
        XCTAssertTrue(value.value is NSNull)
    }

    func testAnyCodableEncodesEachSupportedType() throws {
        let cases: [(AnyCodable, String)] = [
            (AnyCodable(true), "true"),
            (AnyCodable(7), "7"),
            (AnyCodable("hi"), "\"hi\"")
        ]
        for (codable, _) in cases {
            let data = try JSONEncoder().encode(codable)
            let redecoded = try JSONDecoder().decode(AnyCodable.self, from: data)
            switch codable.value {
            case let b as Bool:
                XCTAssertEqual(redecoded.value as? Bool, b)
            case let i as Int:
                XCTAssertEqual(redecoded.value as? Int, i)
            case let s as String:
                XCTAssertEqual(redecoded.value as? String, s)
            default:
                XCTFail("Unexpected type")
            }
        }
    }

    func testAnyCodableEncodesUnsupportedTypeAsNil() throws {
        // A Date has no explicit encode case, so it falls through to encodeNil.
        let codable = AnyCodable(Date())
        let data = try JSONEncoder().encode(codable)
        let string = String(data: data, encoding: .utf8)
        XCTAssertEqual(string, "null")
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
