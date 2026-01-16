import Foundation

/// Client for communicating with the Python WhisperMeet backend server.
actor BackendClient {
    static let shared = BackendClient()

    private let baseURL = URL(string: "http://127.0.0.1:8765")!
    private var serverProcess: Process?
    private var isServerRunning = false
    private var lastActivityTime = Date()
    private var idleCheckTask: Task<Void, Never>?

    /// Idle timeout in seconds before auto-shutdown
    private let idleTimeout: TimeInterval = 300 // 5 minutes

    // MARK: - Server Lifecycle

    /// Ensure server is running (lazy start).
    private func ensureServerRunning() async throws {
        // Check if already running
        if isServerRunning {
            // Verify it's actually responding
            do {
                _ = try await healthCheckInternal()
                lastActivityTime = Date()
                return
            } catch {
                // Server not responding, restart it
                isServerRunning = false
            }
        }

        // Check if there's already a server running (from another instance)
        do {
            _ = try await healthCheckInternal()
            isServerRunning = true
            lastActivityTime = Date()
            startIdleMonitor()
            return
        } catch {
            // No server running, need to start one
        }

        try await startServerInternal()
    }

    /// Internal method to start the server.
    private func startServerInternal() async throws {
        let process = Process()

        // Try to find Python in common locations
        let pythonPaths = [
            NSHomeDirectory() + "/git/whispermeet/python/.venv/bin/python",
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
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

        // Redirect output
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        // Set environment for venv
        var env = ProcessInfo.processInfo.environment
        let venvPath = NSHomeDirectory() + "/git/whispermeet/python/.venv"
        env["VIRTUAL_ENV"] = venvPath
        env["PATH"] = venvPath + "/bin:" + (env["PATH"] ?? "")
        process.environment = env

        try process.run()
        serverProcess = process

        // Wait for server to be ready
        try await waitForServer(timeout: 30)
        isServerRunning = true
        lastActivityTime = Date()

        // Start idle monitor
        startIdleMonitor()
    }

    /// Stop the Python backend server.
    func stopServer() {
        idleCheckTask?.cancel()
        idleCheckTask = nil

        serverProcess?.terminate()
        serverProcess = nil
        isServerRunning = false
    }

    /// Wait for server to respond to health check.
    private func waitForServer(timeout: TimeInterval) async throws {
        let deadline = Date().addingTimeInterval(timeout)

        while Date() < deadline {
            do {
                _ = try await healthCheckInternal()
                return
            } catch {
                // Server not ready yet, retry
            }
            try await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds
        }

        throw BackendError.serverStartTimeout
    }

    // MARK: - Idle Management

    /// Start monitoring for idle timeout.
    private func startIdleMonitor() {
        idleCheckTask?.cancel()

        idleCheckTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60_000_000_000) // Check every minute

                let idleTime = Date().timeIntervalSince(lastActivityTime)
                if idleTime >= idleTimeout {
                    print("Backend server idle for \(Int(idleTime))s, shutting down...")
                    stopServer()
                    break
                }
            }
        }
    }

    /// Update last activity time.
    private func recordActivity() {
        lastActivityTime = Date()
    }

    // MARK: - API Endpoints

    /// Internal health check (no server start).
    private func healthCheckInternal() async throws -> HealthResponse {
        let url = baseURL.appendingPathComponent("health")
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(HealthResponse.self, from: data)
    }

    /// Check server health (starts server if needed).
    func healthCheck() async throws -> HealthResponse {
        try await ensureServerRunning()
        recordActivity()
        return try await healthCheckInternal()
    }

    /// Transcribe audio file.
    func transcribe(audioURL: URL) async throws -> TranscribeResponse {
        try await ensureServerRunning()
        recordActivity()

        let url = baseURL.appendingPathComponent("transcribe")
        let request = try createMultipartRequest(url: url, fileURL: audioURL, fieldName: "file")

        let (data, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)

        return try JSONDecoder().decode(TranscribeResponse.self, from: data)
    }

    /// Diarize audio file (identify speakers).
    func diarize(audioURL: URL) async throws -> DiarizeResponse {
        try await ensureServerRunning()
        recordActivity()

        let url = baseURL.appendingPathComponent("diarize")
        let request = try createMultipartRequest(url: url, fileURL: audioURL, fieldName: "file")

        let (data, response) = try await URLSession.shared.data(for: request)
        try checkResponse(response)

        return try JSONDecoder().decode(DiarizeResponse.self, from: data)
    }

    /// Generate meeting summary.
    func summarize(request: SummarizeRequest) async throws -> SummarizeResponse {
        try await ensureServerRunning()
        recordActivity()

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
        try await ensureServerRunning()
        recordActivity()

        let url = baseURL.appendingPathComponent("identify-speakers")

        let samplesJSON = try JSONEncoder().encode(speakerSamples)
        let samplesString = String(data: samplesJSON, encoding: .utf8) ?? "{}"

        let request = try createMultipartRequest(
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
        try await ensureServerRunning()
        recordActivity()

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
        try await ensureServerRunning()
        recordActivity()

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

// MARK: - Response Types (keep as before)

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
