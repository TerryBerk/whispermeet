import ScreenCaptureKit
import AVFoundation
import Combine

class AudioCapture: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var duration: TimeInterval = 0

    private var stream: SCStream?
    private var audioFile: AVAudioFile?
    private var startTime: Date?
    private var durationTimer: Timer?

    private let outputDirectory: URL

    override init() {
        let transcriptsPath = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Transcripts")
        self.outputDirectory = transcriptsPath

        super.init()

        try? FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
    }

    func startRecording(appBundleId: String) async throws -> URL {
        let content = try await SCShareableContent.current

        guard let app = content.applications.first(where: { $0.bundleIdentifier == appBundleId }) else {
            throw CaptureError.appNotFound
        }

        let filter = SCContentFilter(desktopIndependentWindow: content.windows.first { $0.owningApplication?.bundleIdentifier == appBundleId }!)

        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 16000
        config.channelCount = 1

        let outputURL = createOutputURL(for: app.applicationName)
        audioFile = try createAudioFile(at: outputURL)

        stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream?.addStreamOutput(self, type: .audio, sampleHandlerQueue: .main)
        try await stream?.startCapture()

        startTime = Date()
        isRecording = true
        startDurationTimer()

        return outputURL
    }

    func stopRecording() async throws {
        try await stream?.stopCapture()
        stream = nil
        audioFile = nil
        isRecording = false
        stopDurationTimer()
        duration = 0
    }

    /// Process recorded audio through the Python backend.
    func processRecording(
        at url: URL,
        title: String = "Meeting",
        speakerNames: [String: String]? = nil,
        saveVoices: Bool = false
    ) async throws -> ProcessResponse {
        return try await BackendClient.shared.processAudio(
            audioURL: url,
            title: title,
            speakerNames: speakerNames,
            saveVoices: saveVoices
        )
    }

    private func createOutputURL(for appName: String) -> URL {
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd-HHmmss"
        let timestamp = dateFormatter.string(from: Date())
        let safeName = appName.replacingOccurrences(of: " ", with: "-").lowercased()
        return outputDirectory.appendingPathComponent("\(timestamp)-\(safeName).wav")
    }

    private func createAudioFile(at url: URL) throws -> AVAudioFile {
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 16000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false
        ]
        return try AVAudioFile(forWriting: url, settings: settings)
    }

    private func startDurationTimer() {
        durationTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            guard let self, let start = self.startTime else { return }
            self.duration = Date().timeIntervalSince(start)
        }
    }

    private func stopDurationTimer() {
        durationTimer?.invalidate()
        durationTimer = nil
    }

    enum CaptureError: Error {
        case appNotFound
        case audioFileCreationFailed
    }
}

extension AudioCapture: SCStreamDelegate {
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        print("Stream stopped with error: \(error)")
        isRecording = false
    }
}

extension AudioCapture: SCStreamOutput {
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio,
              let audioFile,
              let samples = sampleBuffer.asPCMBuffer else { return }

        try? audioFile.write(from: samples)
    }
}

extension CMSampleBuffer {
    var asPCMBuffer: AVAudioPCMBuffer? {
        guard let formatDescription = formatDescription,
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(formatDescription) else {
            return nil
        }

        let format = AVAudioFormat(streamDescription: asbd)!
        let numSamples = CMSampleBufferGetNumSamples(self)

        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(numSamples)) else {
            return nil
        }

        buffer.frameLength = AVAudioFrameCount(numSamples)
        CMSampleBufferCopyPCMDataIntoAudioBufferList(self, at: 0, frameCount: Int32(numSamples), into: buffer.mutableAudioBufferList)

        return buffer
    }
}
