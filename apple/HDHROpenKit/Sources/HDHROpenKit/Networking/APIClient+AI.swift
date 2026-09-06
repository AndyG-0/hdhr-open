import Foundation

extension APIClient {
    // MARK: - AI Assistant APIs

    public func sendAIChat(
        request: AIChatRequest,
        onEvent: @Sendable @escaping (AIStreamEvent) -> Void
    ) async throws {
        guard let url = URL(string: APIEndpoints.aiChat(), relativeTo: baseURL) else {
            throw APIError.invalidURL
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = bearerToken {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let devId = deviceId {
            urlRequest.setValue(devId, forHTTPHeaderField: "X-Device-Id")
        }

        urlRequest.httpBody = try jsonEncoder.encode(request)

        let (asyncBytes, response) = try await session.bytes(for: urlRequest)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError("Invalid server response")
        }

        if httpResponse.statusCode >= 400 {
            throw APIError.serverError(statusCode: httpResponse.statusCode, message: "AI chat failed with status code \(httpResponse.statusCode)")
        }

        for try await line in asyncBytes.lines {
            if line.hasPrefix("data: ") {
                let jsonString = String(line.dropFirst(6)).trimmingCharacters(in: .whitespacesAndNewlines)
                if jsonString.isEmpty { continue }
                if let data = jsonString.data(using: .utf8) {
                    do {
                        let event = try jsonDecoder.decode(AIStreamEvent.self, from: data)
                        onEvent(event)
                    } catch {
                        Log.network.error("Error decoding AI stream event: \(error.localizedDescription)")
                    }
                }
            }
        }
    }

    public func testAIConnection(payload: [String: AnyCodable] = [:]) async throws -> NetworkTestConnectionResult {
        try await request(path: APIEndpoints.aiTestConnection(), method: "POST", body: payload)
    }

    public func listAIModels(payload: [String: AnyCodable] = [:]) async throws -> AIListModelsResponse {
        try await request(path: APIEndpoints.aiListModels(), method: "POST", body: payload)
    }

    public func confirmAIAction(actionId: String) async throws -> AIConfirmActionResponse {
        try await request(path: APIEndpoints.aiConfirmAction(actionId), method: "POST")
    }

    public func cancelAIAction(actionId: String) async throws -> AICancelActionResponse {
        try await request(path: APIEndpoints.aiCancelAction(actionId), method: "POST")
    }
}
