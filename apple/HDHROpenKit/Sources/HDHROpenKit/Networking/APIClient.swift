import Foundation

public struct HLSSessionResponse: Decodable, Sendable {
    public let sessionId: String
    public let playlistUrl: String

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case playlistUrl = "playlist_url"
    }
}

public actor APIClient {
    public var baseURL: URL
    var bearerToken: String?
    var deviceId: String?
    let session: URLSession

    let jsonDecoder = JSONDecoder()

    let jsonEncoder = JSONEncoder()

    public init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    public func setBaseURL(_ url: URL) {
        baseURL = url
    }

    public func setBearerToken(_ token: String?) {
        bearerToken = token
    }

    public func currentBearerToken() -> String? {
        bearerToken
    }

    public func setDeviceId(_ id: String?) {
        deviceId = id
    }

    public func currentDeviceId() -> String? {
        deviceId
    }

    // MARK: - Core HTTP Engine

    public func request<T: Decodable>(
        path: String,
        method: String = "GET",
        body: (any Encodable)? = nil,
        headers: [String: String] = [:]
    ) async throws -> T {
        let data = try await requestRaw(path: path, method: method, body: body, headers: headers)
        do {
            return try jsonDecoder.decode(T.self, from: data)
        } catch {
            Log.network.error("JSON Decode error for \(path): \(error.localizedDescription)")
            throw APIError.decodingError(error.localizedDescription)
        }
    }

    public func requestRaw(
        path: String,
        method: String = "GET",
        body: (any Encodable)? = nil,
        headers: [String: String] = [:]
    ) async throws -> Data {
        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIError.invalidURL
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method

        if let token = bearerToken {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let devId = deviceId {
            urlRequest.setValue(devId, forHTTPHeaderField: "X-Device-Id")
        }

        for (k, v) in headers {
            urlRequest.setValue(v, forHTTPHeaderField: k)
        }

        if let body {
            urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
            urlRequest.httpBody = try jsonEncoder.encode(body)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            throw APIError.networkError(error.localizedDescription)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError("Invalid server response")
        }

        if httpResponse.statusCode >= 400 {
            let detailMessage = extractErrorDetail(from: data) ?? "Request failed with status code \(httpResponse.statusCode)"
            if httpResponse.statusCode == 401 {
                throw APIError.unauthorized(detailMessage)
            } else if httpResponse.statusCode == 403 {
                throw APIError.forbidden
            } else if httpResponse.statusCode == 404 {
                throw APIError.notFound(detailMessage)
            } else if httpResponse.statusCode == 429 {
                throw APIError.lockedOut(detailMessage)
            } else {
                throw APIError.serverError(statusCode: httpResponse.statusCode, message: detailMessage)
            }
        }

        return data
    }

    private func extractErrorDetail(from data: Data) -> String? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            if let raw = String(data: data, encoding: .utf8), !raw.isEmpty {
                Log.network.error("Non-JSON error body: \(raw, privacy: .public)")
            }
            return nil
        }
        if let detail = json["detail"] as? String {
            return detail
        }
        if let detailObject = json["detail"] as? [String: Any], let message = detailObject["message"] as? String {
            return message
        }
        if let error = json["error"] as? String {
            return error
        }
        Log.network.error("Unrecognized error body shape: \(String(describing: json), privacy: .public)")
        return nil
    }

    // MARK: - Guide APIs

    public func getChannels() async throws -> HDHomeRunChannelsResponse {
        try await request(path: APIEndpoints.guideChannels())
    }

    public func getGuide(start: Double? = nil, end: Double? = nil) async throws -> [HDHomeRunFullGuideChannel] {
        try await request(path: APIEndpoints.guide(start: start, end: end))
    }

    public func refreshGuide() async throws {
        _ = try await requestRaw(path: APIEndpoints.refreshGuide(), method: "POST")
    }

    // MARK: - DVR APIs

    public func getDvrInfo() async throws -> HDHomeRunDvrInfo {
        try await request(path: APIEndpoints.dvrInfo())
    }

    public func listRecordings() async throws -> [HDHomeRunRecording] {
        try await request(path: APIEndpoints.recordings())
    }

    public func deleteRecording(id: String) async throws {
        _ = try await requestRaw(path: APIEndpoints.deleteRecording(id), method: "DELETE")
    }

    public func getRecordingDetail(url: String, recordingId: String, start: Double? = nil, recordEnd: Double? = nil) async throws -> HDHomeRunRecordingDetail {
        try await request(path: APIEndpoints.recordingDetail(url: url, recordingId: recordingId, start: start, recordEnd: recordEnd))
    }

    public func listRecordingRules() async throws -> [HDHomeRunRecordingRule] {
        try await request(path: APIEndpoints.recordingRules())
    }

    public func addRecordingRule(payload: AddRecordingRulePayload) async throws -> [HDHomeRunRecordingRule] {
        try await request(path: APIEndpoints.recordingRules(), method: "POST", body: payload)
    }

    public func updateRecordingRule(id: String, payload: AddRecordingRulePayload) async throws -> [HDHomeRunRecordingRule] {
        try await request(path: APIEndpoints.updateRecordingRule(id), method: "PUT", body: payload)
    }

    public func deleteRecordingRule(id: String) async throws -> [HDHomeRunRecordingRule] {
        try await request(path: APIEndpoints.deleteRecordingRule(id), method: "DELETE")
    }

    // MARK: - Live Watch APIs

    public func startWatch(channelNumber: String) async throws -> HDHomeRunRecording? {
        let resp: HDHomeRunRecording = try await request(path: APIEndpoints.startWatch(channelNumber: channelNumber), method: "POST")
        if resp.recordingId == nil, resp.sessionId == nil {
            return nil
        }
        return resp
    }

    public func heartbeatWatch(sessionId: String) async throws {
        _ = try await requestRaw(path: APIEndpoints.heartbeatWatch(sessionId: sessionId), method: "POST")
    }

    public func stopWatch(sessionId: String) async throws {
        _ = try await requestRaw(path: APIEndpoints.stopWatch(sessionId: sessionId), method: "POST")
    }

    public func promoteWatch(sessionId: String, options: [String: AnyCodable]? = nil) async throws -> HDHomeRunRecording {
        try await request(path: APIEndpoints.promoteWatch(sessionId: sessionId), method: "POST", body: options)
    }

    // MARK: - HLS Packaging APIs

    public func createChannelHLSSession(channelNumber: String, audioIndex: Int? = nil) async throws -> HDHomeRunRecording {
        try await request(path: APIEndpoints.hlsChannelSession(channelNumber: channelNumber, audioIndex: audioIndex), method: "POST")
    }

    public func createRecordingHLSSession(
        url: String,
        recordingId: String? = nil,
        start: Double? = nil,
        audioIndex: Int? = nil
    ) async throws -> HLSSessionResponse {
        struct RecordingStreamHLSBody: Encodable {
            let url: String
            let recordingId: String?
            let start: Double?
            let audioIndex: Int?

            enum CodingKeys: String, CodingKey {
                case url
                case recordingId = "recording_id"
                case start
                case audioIndex = "audio_index"
            }
        }
        return try await request(
            path: APIEndpoints.hlsRecordingSession(),
            method: "POST",
            body: RecordingStreamHLSBody(url: url, recordingId: recordingId, start: start, audioIndex: audioIndex)
        )
    }

    public func stopHLSSession(sessionId: String) async throws {
        _ = try await requestRaw(path: APIEndpoints.stopHLSSession(sessionId: sessionId), method: "POST")
    }

    // MARK: - Tuner APIs

    public func getTunerStatus() async throws -> [HDHomeRunTuner] {
        try await request(path: APIEndpoints.tunerStatus())
    }

    public func getTunerInfo() async throws -> HDHomeRunTunerInfo {
        try await request(path: APIEndpoints.tunerInfo())
    }

    // MARK: - Auth & Profile APIs

    public func listProfiles() async throws -> [UserProfile] {
        try await request(path: APIEndpoints.users())
    }

    public func login(userId: String, pin: String?, tokenName: String?) async throws -> CurrentUser {
        struct LoginBody: Codable {
            let pin: String?
            let tokenName: String?
            enum CodingKeys: String, CodingKey {
                case pin
                case tokenName = "token_name"
            }
        }
        return try await request(
            path: APIEndpoints.loginUser(userId),
            method: "POST",
            body: LoginBody(pin: pin, tokenName: tokenName)
        )
    }

    public func logout() async throws {
        _ = try await requestRaw(path: APIEndpoints.logoutUser(), method: "POST")
    }

    public func getCurrentUser() async throws -> CurrentUser {
        try await request(path: APIEndpoints.currentUser())
    }

    public func getUserPreferences() async throws -> UserPreferences {
        try await request(path: APIEndpoints.userPreferences())
    }

    public func updateUserPreferences(_ prefs: UserPreferences) async throws -> UserPreferences {
        try await request(path: APIEndpoints.userPreferences(), method: "PATCH", body: prefs)
    }

    // MARK: - Device APIs

    public func registerDevice() async throws -> DeviceRegisterResult {
        let result: DeviceRegisterResult = try await request(path: APIEndpoints.registerDevice(), method: "POST")
        deviceId = result.id
        return result
    }

    public func getCurrentDevice() async throws -> DeviceInfo {
        try await request(path: APIEndpoints.currentDevice())
    }

    public func listDevices() async throws -> [DeviceListEntry] {
        try await request(path: APIEndpoints.listDevices())
    }

    public func deleteDevice(id: String) async throws {
        _ = try await requestRaw(path: APIEndpoints.deleteDevice(id), method: "DELETE")
    }

    // MARK: - Settings APIs

    public func getSettings() async throws -> AppSettings {
        try await request(path: APIEndpoints.settings())
    }

    public func getTranscodePresets() async throws -> [HDHomeRunTranscodePreset] {
        try await request(path: APIEndpoints.transcodePresets())
    }

    public func getHWAccelDiagnostics() async throws -> HWAccelDiagnostics {
        try await request(path: APIEndpoints.hwaccelDiagnostics())
    }

    public func listNetworkIntegrations() async throws -> [NetworkIntegration] {
        try await request(path: APIEndpoints.networkIntegrations())
    }

    public func getNetworkIntegration(type: String) async throws -> NetworkIntegration {
        try await request(path: APIEndpoints.networkIntegration(type))
    }

    public func updateNetworkIntegration(type: String, settings: [String: AnyCodable]) async throws -> NetworkIntegration {
        try await request(path: APIEndpoints.networkIntegration(type), method: "PATCH", body: settings)
    }

    // MARK: - SyncPlay APIs

    public func createSyncPlayRoom(userName: String, initialContent: SyncPlayContent? = nil) async throws -> CreateSyncPlayRoomResponse {
        struct CreateRoomBody: Encodable {
            let userName: String
            let content: SyncPlayContent

            enum CodingKeys: String, CodingKey {
                case userName = "user_name"
                case content
            }
        }
        let fallbackContent = initialContent ?? SyncPlayContent(type: "channel", channelNumber: "default", title: "Live TV")
        let body = CreateRoomBody(userName: userName, content: fallbackContent)
        return try await request(path: APIEndpoints.syncPlayRooms(), method: "POST", body: body)
    }

    public func getSyncPlayRoom(code: String) async throws -> SyncPlayRoom {
        try await request(path: APIEndpoints.syncPlayRoom(code))
    }

    public func syncPlayWsUrl(roomCode: String, userName: String? = nil) -> URL? {
        // Note: the resulting URL carries the bearer token in its query string
        // (see APIEndpoints.syncPlayWs) - deliberately not logging the URL
        // itself here, only that construction failed and why.
        let path = APIEndpoints.syncPlayWs(roomCode: roomCode, userName: userName, token: bearerToken)
        guard let httpUrl = URL(string: path, relativeTo: baseURL)?.absoluteURL else {
            Log.network.error("syncPlayWsUrl: failed to construct base URL for room \(roomCode, privacy: .public)")
            return nil
        }
        var comps = URLComponents(url: httpUrl, resolvingAgainstBaseURL: true)
        if comps?.scheme == "https" {
            comps?.scheme = "wss"
        } else {
            comps?.scheme = "ws"
        }
        guard let result = comps?.url else {
            Log.network.error("syncPlayWsUrl: failed to resolve URLComponents for room \(roomCode, privacy: .public)")
            return nil
        }
        return result
    }
}
