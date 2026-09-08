import XCTest
@testable import HDHROpenKit

final class TunerStatusTests: XCTestCase {
    // MARK: - TunerViewerInfo

    func testDecodeTunerViewerInfoAllFields() throws {
        let json = """
        {"user_name": "andy", "client_ip": "192.168.1.20"}
        """.data(using: .utf8)!

        let viewer = try JSONDecoder().decode(TunerViewerInfo.self, from: json)
        XCTAssertEqual(viewer.userName, "andy")
        XCTAssertEqual(viewer.clientIp, "192.168.1.20")
    }

    func testDecodeTunerViewerInfoMissingClientIp() throws {
        let json = """
        {"user_name": "andy"}
        """.data(using: .utf8)!

        let viewer = try JSONDecoder().decode(TunerViewerInfo.self, from: json)
        XCTAssertNil(viewer.clientIp)
    }

    func testEncodeDecodeTunerViewerInfoRoundTrip() throws {
        let json = """
        {"user_name": "guest", "client_ip": null}
        """.data(using: .utf8)!
        let viewer = try JSONDecoder().decode(TunerViewerInfo.self, from: json)
        let data = try JSONEncoder().encode(viewer)
        let redecoded = try JSONDecoder().decode(TunerViewerInfo.self, from: data)
        XCTAssertEqual(redecoded.userName, "guest")
        XCTAssertNil(redecoded.clientIp)
    }

    // MARK: - TunerClientInfo

    func testDecodeTunerClientInfoAllFieldsPresent() throws {
        let json = """
        {
            "type": "browser",
            "name": "Chrome",
            "ip": "192.168.1.20",
            "hostname": "andys-mac",
            "details": "Chrome 120 on macOS",
            "recording_id": "rec_1",
            "scheduled_id": "sched_1",
            "is_recording": true,
            "viewers": [
                {"user_name": "andy", "client_ip": "192.168.1.20"}
            ]
        }
        """.data(using: .utf8)!

        let client = try JSONDecoder().decode(TunerClientInfo.self, from: json)
        XCTAssertEqual(client.type, "browser")
        XCTAssertEqual(client.name, "Chrome")
        XCTAssertEqual(client.ip, "192.168.1.20")
        XCTAssertEqual(client.hostname, "andys-mac")
        XCTAssertEqual(client.details, "Chrome 120 on macOS")
        XCTAssertEqual(client.recordingId, "rec_1")
        XCTAssertEqual(client.scheduledId, "sched_1")
        XCTAssertTrue(client.isRecording)
        XCTAssertEqual(client.viewers.count, 1)
        XCTAssertEqual(client.viewers.first?.userName, "andy")
    }

    func testDecodeTunerClientInfoOptionalFieldsAbsent() throws {
        let json = """
        {
            "type": "hdhomerun",
            "name": "Native",
            "details": "",
            "is_recording": false,
            "viewers": []
        }
        """.data(using: .utf8)!

        let client = try JSONDecoder().decode(TunerClientInfo.self, from: json)
        XCTAssertNil(client.ip)
        XCTAssertNil(client.hostname)
        XCTAssertNil(client.recordingId)
        XCTAssertNil(client.scheduledId)
        XCTAssertFalse(client.isRecording)
        XCTAssertTrue(client.viewers.isEmpty)
    }

    func testEncodeDecodeTunerClientInfoRoundTrip() throws {
        let json = """
        {
            "type": "browser",
            "name": "Safari",
            "ip": null,
            "hostname": null,
            "details": "Safari 18",
            "recording_id": null,
            "scheduled_id": null,
            "is_recording": true,
            "viewers": []
        }
        """.data(using: .utf8)!

        let client = try JSONDecoder().decode(TunerClientInfo.self, from: json)
        let data = try JSONEncoder().encode(client)
        let redecoded = try JSONDecoder().decode(TunerClientInfo.self, from: data)
        XCTAssertEqual(redecoded.name, "Safari")
        XCTAssertTrue(redecoded.isRecording)
        XCTAssertNil(redecoded.ip)
    }

    // MARK: - TunerWarningInfo

    func testDecodeTunerWarningInfo() throws {
        let json = """
        {"severity": "warning", "message": "Weak signal"}
        """.data(using: .utf8)!

        let warning = try JSONDecoder().decode(TunerWarningInfo.self, from: json)
        XCTAssertEqual(warning.severity, "warning")
        XCTAssertEqual(warning.message, "Weak signal")
    }

    func testEncodeDecodeTunerWarningInfoRoundTrip() throws {
        let original = TunerWarningInfo(severity: "error", message: "No signal")
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(TunerWarningInfo.self, from: data)
        XCTAssertEqual(decoded.severity, "error")
        XCTAssertEqual(decoded.message, "No signal")
    }

    // MARK: - HDHomeRunTuner

    func testDecodeHDHomeRunTunerInUseAllFields() throws {
        let json = """
        {
            "index": 0,
            "resource": "/tuner0",
            "in_use": true,
            "channel_number": "5.1",
            "channel_name": "KING-DT",
            "target_ip": "192.168.1.20",
            "client": {
                "type": "browser",
                "name": "Chrome",
                "details": "Chrome 120",
                "is_recording": false,
                "viewers": []
            },
            "warning": {"severity": "warning", "message": "Weak signal"},
            "signal_strength_percent": 85,
            "signal_quality_percent": 90,
            "symbol_quality_percent": 95,
            "network_rate_bps": 19200000
        }
        """.data(using: .utf8)!

        let tuner = try JSONDecoder().decode(HDHomeRunTuner.self, from: json)
        XCTAssertEqual(tuner.id, 0)
        XCTAssertEqual(tuner.index, 0)
        XCTAssertEqual(tuner.resource, "/tuner0")
        XCTAssertTrue(tuner.inUse)
        XCTAssertEqual(tuner.channelNumber, "5.1")
        XCTAssertEqual(tuner.channelName, "KING-DT")
        XCTAssertEqual(tuner.targetIp, "192.168.1.20")
        XCTAssertEqual(tuner.client?.name, "Chrome")
        XCTAssertEqual(tuner.warning?.message, "Weak signal")
        XCTAssertEqual(tuner.signalStrengthPercent, 85)
        XCTAssertEqual(tuner.signalQualityPercent, 90)
        XCTAssertEqual(tuner.symbolQualityPercent, 95)
        XCTAssertEqual(tuner.networkRateBps, 19_200_000)
        XCTAssertEqual(tuner.formattedRateMbps, "19.2 Mbps")
    }

    func testDecodeHDHomeRunTunerIdleAllOptionalFieldsAbsent() throws {
        let json = """
        {
            "index": 1,
            "resource": null,
            "in_use": false
        }
        """.data(using: .utf8)!

        let tuner = try JSONDecoder().decode(HDHomeRunTuner.self, from: json)
        XCTAssertEqual(tuner.id, 1)
        XCTAssertFalse(tuner.inUse)
        XCTAssertNil(tuner.resource)
        XCTAssertNil(tuner.channelNumber)
        XCTAssertNil(tuner.channelName)
        XCTAssertNil(tuner.targetIp)
        XCTAssertNil(tuner.client)
        XCTAssertNil(tuner.warning)
        XCTAssertNil(tuner.signalStrengthPercent)
        XCTAssertNil(tuner.signalQualityPercent)
        XCTAssertNil(tuner.symbolQualityPercent)
        XCTAssertNil(tuner.networkRateBps)
    }

    func testHDHomeRunTunerFormattedRateMbpsWithNilBps() throws {
        let json = """
        {"index": 2, "in_use": false, "network_rate_bps": null}
        """.data(using: .utf8)!
        let tuner = try JSONDecoder().decode(HDHomeRunTuner.self, from: json)
        XCTAssertEqual(tuner.formattedRateMbps, "0.0 Mbps")
    }

    func testHDHomeRunTunerFormattedRateMbpsWithZeroBps() throws {
        let json = """
        {"index": 3, "in_use": false, "network_rate_bps": 0}
        """.data(using: .utf8)!
        let tuner = try JSONDecoder().decode(HDHomeRunTuner.self, from: json)
        XCTAssertEqual(tuner.formattedRateMbps, "0.0 Mbps")
    }

    func testHDHomeRunTunerFormattedRateMbpsRounding() throws {
        let json = """
        {"index": 4, "in_use": true, "network_rate_bps": 1234567}
        """.data(using: .utf8)!
        let tuner = try JSONDecoder().decode(HDHomeRunTuner.self, from: json)
        XCTAssertEqual(tuner.formattedRateMbps, "1.2 Mbps")
    }

    func testEncodeDecodeHDHomeRunTunerRoundTrip() throws {
        let json = """
        {
            "index": 5,
            "resource": "/tuner5",
            "in_use": true,
            "channel_number": "7.1",
            "channel_name": "KIRO-DT",
            "target_ip": "192.168.1.30",
            "client": null,
            "warning": null,
            "signal_strength_percent": 70,
            "signal_quality_percent": 80,
            "symbol_quality_percent": 90,
            "network_rate_bps": 5000000
        }
        """.data(using: .utf8)!

        let tuner = try JSONDecoder().decode(HDHomeRunTuner.self, from: json)
        let data = try JSONEncoder().encode(tuner)
        let redecoded = try JSONDecoder().decode(HDHomeRunTuner.self, from: data)
        XCTAssertEqual(redecoded.index, 5)
        XCTAssertEqual(redecoded.channelNumber, "7.1")
        XCTAssertEqual(redecoded.networkRateBps, 5_000_000)
    }

    // MARK: - HDHomeRunTunerInfo

    func testDecodeHDHomeRunTunerInfoAllFields() throws {
        let json = """
        {
            "friendly_name": "HDHomeRun Flex 4K",
            "model_number": "HDFX-4K",
            "firmware_version": "20240101",
            "tuner_count": 4
        }
        """.data(using: .utf8)!

        let info = try JSONDecoder().decode(HDHomeRunTunerInfo.self, from: json)
        XCTAssertEqual(info.friendlyName, "HDHomeRun Flex 4K")
        XCTAssertEqual(info.modelNumber, "HDFX-4K")
        XCTAssertEqual(info.firmwareVersion, "20240101")
        XCTAssertEqual(info.tunerCount, 4)
    }

    func testDecodeHDHomeRunTunerInfoOptionalFieldsAbsent() throws {
        let json = """
        {"friendly_name": "HDHomeRun"}
        """.data(using: .utf8)!

        let info = try JSONDecoder().decode(HDHomeRunTunerInfo.self, from: json)
        XCTAssertNil(info.modelNumber)
        XCTAssertNil(info.firmwareVersion)
        XCTAssertNil(info.tunerCount)
    }

    func testEncodeDecodeHDHomeRunTunerInfoRoundTrip() throws {
        let json = """
        {"friendly_name": "HDHomeRun Prime", "model_number": "HDHR3-CC", "firmware_version": "20230101", "tuner_count": 3}
        """.data(using: .utf8)!
        let info = try JSONDecoder().decode(HDHomeRunTunerInfo.self, from: json)
        let data = try JSONEncoder().encode(info)
        let redecoded = try JSONDecoder().decode(HDHomeRunTunerInfo.self, from: data)
        XCTAssertEqual(redecoded.friendlyName, "HDHomeRun Prime")
        XCTAssertEqual(redecoded.tunerCount, 3)
    }

    // MARK: - HDHomeRunDvrInfo

    func testDecodeHDHomeRunDvrInfoAllFields() throws {
        let json = """
        {
            "friendly_name": "HDHomeRun DVR",
            "version": "20240601",
            "free_space_bytes": 500000000000,
            "is_builtin": true,
            "provider": "hdhomerun"
        }
        """.data(using: .utf8)!

        let dvr = try JSONDecoder().decode(HDHomeRunDvrInfo.self, from: json)
        XCTAssertEqual(dvr.friendlyName, "HDHomeRun DVR")
        XCTAssertEqual(dvr.version, "20240601")
        XCTAssertEqual(dvr.freeSpaceBytes, 500_000_000_000)
        XCTAssertEqual(dvr.isBuiltin, true)
        XCTAssertEqual(dvr.provider, "hdhomerun")
    }

    func testDecodeHDHomeRunDvrInfoOptionalFieldsAbsent() throws {
        let json = """
        {"friendly_name": "Unknown DVR"}
        """.data(using: .utf8)!

        let dvr = try JSONDecoder().decode(HDHomeRunDvrInfo.self, from: json)
        XCTAssertNil(dvr.version)
        XCTAssertNil(dvr.freeSpaceBytes)
        XCTAssertNil(dvr.isBuiltin)
        XCTAssertNil(dvr.provider)
    }

    func testHDHomeRunDvrInfoFormattedFreeSpaceUnknownWhenNil() throws {
        let json = """
        {"friendly_name": "DVR"}
        """.data(using: .utf8)!
        let dvr = try JSONDecoder().decode(HDHomeRunDvrInfo.self, from: json)
        XCTAssertEqual(dvr.formattedFreeSpace, "Unknown")
    }

    func testHDHomeRunDvrInfoFormattedFreeSpaceUnknownWhenZero() throws {
        let json = """
        {"friendly_name": "DVR", "free_space_bytes": 0}
        """.data(using: .utf8)!
        let dvr = try JSONDecoder().decode(HDHomeRunDvrInfo.self, from: json)
        XCTAssertEqual(dvr.formattedFreeSpace, "Unknown")
    }

    func testHDHomeRunDvrInfoFormattedFreeSpaceInGB() throws {
        let json = """
        {"friendly_name": "DVR", "free_space_bytes": 53687091200}
        """.data(using: .utf8)!
        // 53687091200 bytes = 50 GB
        let dvr = try JSONDecoder().decode(HDHomeRunDvrInfo.self, from: json)
        XCTAssertEqual(dvr.formattedFreeSpace, "50.0 GB free")
    }

    func testHDHomeRunDvrInfoFormattedFreeSpaceInTB() throws {
        // 1100 GiB in bytes, which is >= 1000 GB threshold, so formatted in TB.
        let bytes = Int64(1100.0 * 1_073_741_824.0)
        let json = """
        {"friendly_name": "DVR", "free_space_bytes": \(bytes)}
        """.data(using: .utf8)!
        let dvr = try JSONDecoder().decode(HDHomeRunDvrInfo.self, from: json)
        XCTAssertTrue(dvr.formattedFreeSpace.hasSuffix("TB free"))
        XCTAssertEqual(dvr.formattedFreeSpace, "1.07 TB free")
    }

    func testEncodeDecodeHDHomeRunDvrInfoRoundTrip() throws {
        let json = """
        {"friendly_name": "DVR", "version": "1.0", "free_space_bytes": 1000000, "is_builtin": false, "provider": "custom"}
        """.data(using: .utf8)!
        let dvr = try JSONDecoder().decode(HDHomeRunDvrInfo.self, from: json)
        let data = try JSONEncoder().encode(dvr)
        let redecoded = try JSONDecoder().decode(HDHomeRunDvrInfo.self, from: data)
        XCTAssertEqual(redecoded.provider, "custom")
        XCTAssertEqual(redecoded.isBuiltin, false)
    }
}
