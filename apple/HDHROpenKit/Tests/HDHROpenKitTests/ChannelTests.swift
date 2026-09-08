import XCTest
@testable import HDHROpenKit

final class ChannelTests: XCTestCase {
    // MARK: - HDHomeRunChannel

    func testDecodeHDHomeRunChannelAllFieldsPresent() throws {
        let json = """
        {
            "channel_number": "7.1",
            "name": "KIRO-DT",
            "is_hd": true,
            "is_drm": false,
            "stream_url": "http://192.168.1.50:5004/auto/v7.1",
            "playback_url": "/api/streaming/stream/7.1",
            "now": {
                "title": "Local News at Six",
                "start": 1700000000,
                "end": 1700003600
            },
            "next": {
                "title": "Evening Weather",
                "start": 1700003600,
                "end": 1700005400
            }
        }
        """.data(using: .utf8)!

        let channel = try JSONDecoder().decode(HDHomeRunChannel.self, from: json)
        XCTAssertEqual(channel.channelNumber, "7.1")
        XCTAssertEqual(channel.name, "KIRO-DT")
        XCTAssertTrue(channel.isHD)
        XCTAssertFalse(channel.isDRM)
        XCTAssertEqual(channel.streamUrl, "http://192.168.1.50:5004/auto/v7.1")
        XCTAssertEqual(channel.playbackUrl, "/api/streaming/stream/7.1")
        XCTAssertEqual(channel.now?.title, "Local News at Six")
        XCTAssertEqual(channel.next?.title, "Evening Weather")
    }

    func testDecodeHDHomeRunChannelOptionalFieldsAbsent() throws {
        let json = """
        {
            "channel_number": "9.1",
            "name": "KCTS",
            "is_hd": false,
            "is_drm": true,
            "stream_url": "http://192.168.1.50:5004/auto/v9.1"
        }
        """.data(using: .utf8)!

        let channel = try JSONDecoder().decode(HDHomeRunChannel.self, from: json)
        XCTAssertNil(channel.playbackUrl)
        XCTAssertNil(channel.now)
        XCTAssertNil(channel.next)
        XCTAssertTrue(channel.isDRM)
    }

    func testHDHomeRunChannelIdAndDisplayNumberMatchChannelNumber() {
        let channel = HDHomeRunChannel(channelNumber: "12.3", name: "Test")
        XCTAssertEqual(channel.id, "12.3")
        XCTAssertEqual(channel.displayNumber, "12.3")
    }

    func testHDHomeRunChannelInitDefaults() {
        let channel = HDHomeRunChannel(channelNumber: "4.1", name: "NBC")
        XCTAssertFalse(channel.isHD)
        XCTAssertFalse(channel.isDRM)
        XCTAssertEqual(channel.streamUrl, "")
        XCTAssertNil(channel.playbackUrl)
        XCTAssertNil(channel.now)
        XCTAssertNil(channel.next)
    }

    func testEncodeDecodeHDHomeRunChannelRoundTrip() throws {
        let original = HDHomeRunChannel(
            channelNumber: "5.1",
            name: "KING-DT",
            isHD: true,
            isDRM: false,
            streamUrl: "http://example.com/stream",
            playbackUrl: "/api/streaming/stream/5.1",
            now: HDHomeRunGuideEntry(title: "Evening News", start: 1_700_000_000, end: 1_700_003_600),
            next: nil
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(HDHomeRunChannel.self, from: data)
        XCTAssertEqual(decoded.channelNumber, original.channelNumber)
        XCTAssertEqual(decoded.name, original.name)
        XCTAssertEqual(decoded.isHD, original.isHD)
        XCTAssertEqual(decoded.now?.title, "Evening News")
        XCTAssertNil(decoded.next)

        let dict = try encodeToDictionary(original)
        XCTAssertEqual(dict["channel_number"] as? String, "5.1")
        XCTAssertEqual(dict["is_hd"] as? Bool, true)
        XCTAssertEqual(dict["is_drm"] as? Bool, false)
        XCTAssertEqual(dict["stream_url"] as? String, "http://example.com/stream")
        XCTAssertEqual(dict["playback_url"] as? String, "/api/streaming/stream/5.1")
    }

    func testHDHomeRunChannelHashableEquality() {
        let a = HDHomeRunChannel(channelNumber: "5.1", name: "KING-DT")
        let b = HDHomeRunChannel(channelNumber: "5.1", name: "KING-DT")
        let c = HDHomeRunChannel(channelNumber: "5.2", name: "KING-DT2")
        XCTAssertEqual(a, b)
        XCTAssertNotEqual(a, c)
        XCTAssertEqual(Set([a, b, c]).count, 2)
    }

    // MARK: - HDHomeRunChannelsResponse

    func testDecodeHDHomeRunChannelsResponse() throws {
        let json = """
        {
            "channels": [
                {"channel_number": "5.1", "name": "KING-DT", "is_hd": true, "is_drm": false, "stream_url": "http://x/1"},
                {"channel_number": "7.1", "name": "KIRO-DT", "is_hd": true, "is_drm": false, "stream_url": "http://x/2"}
            ],
            "guide_available": true
        }
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(HDHomeRunChannelsResponse.self, from: json)
        XCTAssertEqual(response.channels.count, 2)
        XCTAssertTrue(response.guideAvailable)
    }

    func testHDHomeRunChannelsResponseEmptyChannelsAndUnavailableGuide() throws {
        let json = """
        {"channels": [], "guide_available": false}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(HDHomeRunChannelsResponse.self, from: json)
        XCTAssertTrue(response.channels.isEmpty)
        XCTAssertFalse(response.guideAvailable)
    }

    func testEncodeDecodeHDHomeRunChannelsResponseRoundTrip() throws {
        let original = HDHomeRunChannelsResponse(
            channels: [HDHomeRunChannel(channelNumber: "5.1", name: "KING-DT")],
            guideAvailable: true
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(HDHomeRunChannelsResponse.self, from: data)
        XCTAssertEqual(decoded.channels.count, 1)
        XCTAssertTrue(decoded.guideAvailable)
    }

    // MARK: - HDHomeRunFullGuideChannel

    func testDecodeHDHomeRunFullGuideChannel() throws {
        let json = """
        {
            "channel_number": "5.1",
            "channel_name": "KING-DT",
            "airings": [
                {"title": "Morning Show", "start": 1700000000, "end": 1700003600},
                {"title": "Midday News", "start": 1700003600, "end": 1700007200}
            ]
        }
        """.data(using: .utf8)!

        let channel = try JSONDecoder().decode(HDHomeRunFullGuideChannel.self, from: json)
        XCTAssertEqual(channel.id, "5.1")
        XCTAssertEqual(channel.channelNumber, "5.1")
        XCTAssertEqual(channel.channelName, "KING-DT")
        XCTAssertEqual(channel.airings.count, 2)
        XCTAssertEqual(channel.airings.first?.title, "Morning Show")
    }

    func testDecodeHDHomeRunFullGuideChannelEmptyAirings() throws {
        let json = """
        {"channel_number": "9.1", "channel_name": "KCTS", "airings": []}
        """.data(using: .utf8)!

        let channel = try JSONDecoder().decode(HDHomeRunFullGuideChannel.self, from: json)
        XCTAssertTrue(channel.airings.isEmpty)
    }

    func testEncodeDecodeHDHomeRunFullGuideChannelRoundTrip() throws {
        let original = HDHomeRunFullGuideChannel(
            channelNumber: "5.1",
            channelName: "KING-DT",
            airings: [HDHomeRunGuideEntry(title: "Show", start: 1, end: 2)]
        )
        let data = try JSONEncoder().encode(original)
        let decoded = try JSONDecoder().decode(HDHomeRunFullGuideChannel.self, from: data)
        XCTAssertEqual(decoded.channelName, "KING-DT")
        XCTAssertEqual(decoded.airings.count, 1)
    }

    // MARK: - HDHomeRunChannelSetting

    func testDecodeHDHomeRunChannelSettingAllFieldsPresent() throws {
        let json = """
        {
            "id": "cs_1",
            "channel_number": "5.1",
            "name": "KING-DT",
            "is_hd": true,
            "is_favorite": true,
            "hidden": false,
            "guide_provider": "schedules_direct",
            "xmltv_channel_id": "5.1@example.com",
            "xmltv_display_name": "KING",
            "sd_station_id": "12345",
            "sd_lineup_id": "USA-OTA-98005"
        }
        """.data(using: .utf8)!

        let setting = try JSONDecoder().decode(HDHomeRunChannelSetting.self, from: json)
        XCTAssertEqual(setting.id, "cs_1")
        XCTAssertEqual(setting.channelNumber, "5.1")
        XCTAssertTrue(setting.isFavorite)
        XCTAssertFalse(setting.hidden)
        XCTAssertEqual(setting.guideProvider, "schedules_direct")
        XCTAssertEqual(setting.xmltvChannelId, "5.1@example.com")
        XCTAssertEqual(setting.xmltvDisplayName, "KING")
        XCTAssertEqual(setting.sdStationId, "12345")
        XCTAssertEqual(setting.sdLineupId, "USA-OTA-98005")
    }

    func testDecodeHDHomeRunChannelSettingOptionalFieldsAbsent() throws {
        let json = """
        {
            "id": "cs_2",
            "channel_number": "9.1",
            "name": "KCTS",
            "is_hd": false,
            "is_favorite": false,
            "hidden": true
        }
        """.data(using: .utf8)!

        let setting = try JSONDecoder().decode(HDHomeRunChannelSetting.self, from: json)
        XCTAssertNil(setting.guideProvider)
        XCTAssertNil(setting.xmltvChannelId)
        XCTAssertNil(setting.xmltvDisplayName)
        XCTAssertNil(setting.sdStationId)
        XCTAssertNil(setting.sdLineupId)
        XCTAssertTrue(setting.hidden)
    }

    func testEncodeDecodeHDHomeRunChannelSettingRoundTrip() throws {
        let json = """
        {
            "id": "cs_3",
            "channel_number": "5.1",
            "name": "KING-DT",
            "is_hd": true,
            "is_favorite": false,
            "hidden": false,
            "guide_provider": null,
            "xmltv_channel_id": null,
            "xmltv_display_name": null,
            "sd_station_id": null,
            "sd_lineup_id": null
        }
        """.data(using: .utf8)!

        let setting = try JSONDecoder().decode(HDHomeRunChannelSetting.self, from: json)
        let data = try JSONEncoder().encode(setting)
        let redecoded = try JSONDecoder().decode(HDHomeRunChannelSetting.self, from: data)
        XCTAssertEqual(redecoded.id, "cs_3")
        XCTAssertNil(redecoded.guideProvider)
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
