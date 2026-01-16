import Foundation

/// Client for communicating with the Python WhisperMeet backend server.
actor BackendClient {
    static let shared = BackendClient()

    private let baseURL = URL(string: "http://127.0.0.1:8765")!
    private var serverProcess: Process?
    private var isServerRunning = false

    // MARK: - Server Lifecycle

    /// Start the Python backend server.
    func startServer() async throws {
        guard !isServerRunning else { return }

        let process = Process()

        // Try to find Python in common locations
        let pythonPaths = [
            "/usr/bin/python3",
            "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3",
            NSHomeDirectory() + "/git/whispermeet/python/.venv/bin/python",
        ]

        var pythonPath: String?
        for path in pythonPaths {
            if FileManager.default.fileExists(atPath: path) {
                pythonPath = path
                break
            }
        }

        guard let python = pythonPath else {
            throw BackendError.pythonNotFound
        }

        process.executableURL = URL(fileURLWithPath: python)
        process.arguments = ["-m", "whispermeet.server"]
        process.currentDirectoryURL = URL(fileURLWithPath: NSHomeDirectory() + "/git/whispermeet/python")

        // Redirect output to suppress logs (or capture them)
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        // Set environment for venv
        var env = ProcessInfo.processInfo.environment
        env["VIRTUAL_ENV"] = NSHomeDirectory() + "/git/whispermeet/python/.venv"
        env["PATH"] = NSHomeDirectory() + "/git/whispermeet/python/.venv/bin:" + (env["PATH"] ?? "")
        process.environment = env

        try process.run()
        serverProcess = process

        // Wait for server to be ready
        try await waitForServer(timeout: 30)
        isServerRunning = true
    }

    /// Stop the Python backend server.
    func stopServer() {
        serverProcess?.terminate()
        serverProcess = nil
        isServerRunning = false
    }

    /// Wait for server to respond to health check.
    private func waitForServer(timeout: TimeInterval) async throws {
        let deadline = Date().addingTimeInterval(timeout)

        while Date() < deadline {
            do {
                let health = try await healthCheck()
                if health.status == "ok" {
                    return
                }
            } catch {
                // Server not ready yet, retry
            }
            try await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds
        }

        throw BackendError.serverStartTimeout
    }

    // MARK: - API Endpoints

    /// Check server health.
    func healthCheck() async throws -> HealthResponse {
        let url = baseURL.appendingPathComponent("health")
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(HealthResponse.self, from: data)
    }

    /// Transcribe audio file.
    func transcribe(audioURL: URL) async throws -> TranscribeResponse {
        let url = baseURL.appendingPathComponent("transcribe")
        let request = try createMultipartRequest(url: url, fileURL: audioURL, fieldName: "file")

        let (data, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)

        return try JSONDecoder().decode(TranscribeResponse.self, from: data)
    }

    /// Diarize audio file (identify speakers).
    func diarize(audioURL: URL) async throws -> DiarizeResponse {
        let url = baseURL.appendingPathComponent("diarize")
        let request = try createMultipartRequest(url: url, fileURL: audioURL, fieldName: "file")

        let (data, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)

        return try JSONDecoder().decode(DiarizeResponse.self, from: data)
    }

    /// Generate meeting summary.
    func summarize(request: SummarizeRequest) async throws -> SummarizeResponse {
        let url = baseURL.appendingPathComponent("summarize")
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.httpBody = try JSONEncoder().encode(request)

        let (data, response) = try await URLSession.shared.data(for: urlRequest)
        try checkResponse(response)

        return try JSONDecoder().decode(SummarizeResponse.self, from: data)
    }

    /// Identify known speakers from voice samples.
    func identifySpeakers(audioURL: URL, speakerSamples: [String: [Double]]) async throws -> IdentifyResponse {
        let url = baseURL.appendingPathComponent("identify-speakers")

        var request = try createMultipartRequest(url: url, fileURL: audioURL, fieldName: "file")

        // Add speaker_samples as form field
        let samplesJSON = try JSONEncoder().encode(speakerSamples)
        let samplesString = String(data: samplesJSON, encoding: .utf8) ?? "{}"

        // Recreate request with additional field
        request = try createMultipartRequest(
            url: url,
            fileURL: audioURL,
            fieldName: "file",
            additionalFields: ["speaker_samples": samplesString]
        )

        let (data, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)

        return try JSONDecoder().decode(IdentifyResponse.self, from: data)
    }

    /// Save voice profile for future identification.
    func saveVoice(audioURL: URL, name: String, start: Double, end: Double) async throws {
        let url = baseURL.appendingPathComponent("save-voice")

        let request = try createMultipartRequest(
            url: url,
            fileURL: audioURL,
            fieldName: "file",
            additionalFields: [
                "name": name,
                "start": String(start),
                "end": String(end),
            ]
        )

        let (_, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)
    }

    /// Full audio processing pipeline.
    func processAudio(
        audioURL: URL,
        title: String = "Meeting",
        speakerNames: [String: String]? = nil,
        saveVoices: Bool = false
    ) async throws -> ProcessResponse {
        let url = baseURL.appendingPathComponent("process")

        var fields: [String: String] = [
            "title": title,
            "save_voices": saveVoices ? "true" : "false",
        ]

        if let names = speakerNames {
            let namesJSON = try JSONEncoder().encode(names)
            fields["speaker_names"] = String(data: namesJSON, encoding: .utf8) ?? "{}"
        }

        let request = try createMultipartRequest(
            url: url,
            fileURL: audioURL,
            fieldName: "file",
            additionalFields: fields
        )

        let (data, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)

        return try JSONDecoder().decode(ProcessResponse.self, from: data)
    }

    // MARK: - Helpers

    private func createMultipartRequest(
        url: URL,
        fileURL: URL,
        fieldName: String,
        additionalFields: [String: String] = [:]
    ) throws -> URLRequest {
        let boundary = UUID().uuidString

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        var body = Data()

        // Add file
        let fileData = try Data(contentsOf: fileURL)
        let filename = fileURL.lastPathComponent

        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(fieldName)\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n".data(using: .utf8)!)

        // Add additional fields
        for (key, value) in additionalFields {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(value)\r\n".data(using: .utf8)!)
        }

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body
        return request
    }

    private func checkResponse(_ response: URLResponse) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw BackendError.invalidResponse
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw BackendError.serverError(statusCode: httpResponse.statusCode)
        }
    }
}

// MARK: - Error Types

enum BackendError: LocalizedError {
    case pythonNotFound
    case serverStartTimeout
    case invalidResponse
    case serverError(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .pythonNotFound:
            return "Python not found. Please install Python 3."
        case .serverStartTimeout:
            return "Backend server failed to start within timeout."
        case .invalidResponse:
            return "Invalid response from backend server."
        case .serverError(let code):
            return "Backend server error: \(code)"
        }
    }
}

// MARK: - Response Types

struct HealthResponse: Codable {
    let status: String
    let timestamp: String
}

struct TranscribeResponse: Codable {
    let segments: [TranscriptSegment]
    let durationSeconds: Double

    enum CodingKeys: String, CodingKey {
        case segments
        case durationSeconds = "duration_seconds"
    }
}

struct TranscriptSegment: Codable {
    let start: Double
    let end: Double
    let text: String
    let speaker: String?
}

struct DiarizeResponse: Codable {
    let speakers: [String]
    let segments: [SpeakerSegment]
    let speakerSamples: [String: [Double]]

    enum CodingKeys: String, CodingKey {
        case speakers
        case segments
        case speakerSamples = "speaker_samples"
    }
}

struct SpeakerSegment: Codable {
    let speaker: String
    let start: Double
    let end: Double
}

struct SummarizeRequest: Codable {
    let transcript: String
    let title: String
    let date: String
    let duration: String
    let participants: [String]
}

struct SummarizeResponse: Codable {
    let markdown: String
    let title: String
    let tldr: String
    let keyDecisions: [String]
    let actionItems: [String]

    enum CodingKeys: String, CodingKey {
        case markdown
        case title
        case tldr
        case keyDecisions = "key_decisions"
        case actionItems = "action_items"
    }
}

struct IdentifyResponse: Codable {
    let suggestions: [String: String?]
}

struct ProcessResponse: Codable {
    let transcript: String
    let summaryMarkdown: String
    let speakers: [String]
    let durationSeconds: Double

    enum CodingKeys: String, CodingKey {
        case transcript
        case summaryMarkdown = "summary_markdown"
        case speakers
        case durationSeconds = "duration_seconds"
    }
}
