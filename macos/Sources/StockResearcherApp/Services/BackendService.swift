import Foundation
import Observation

@MainActor
@Observable
final class BackendService {
    private var process: Process?

    var isManagedProcessRunning: Bool {
        process?.isRunning == true
    }

    func start(projectDirectory: String, workingDirectory: String, apiBaseURL: String) throws {
        if process?.isRunning == true { return }

        let projectURL = URL(fileURLWithPath: projectDirectory, isDirectory: true)
        let workingURL = URL(fileURLWithPath: workingDirectory, isDirectory: true)
        try FileManager.default.createDirectory(
            at: workingURL, withIntermediateDirectories: true
        )
        try Self.bootstrapEnvironment(projectURL: projectURL, workingURL: workingURL)
        guard let url = URL(string: apiBaseURL),
              let host = url.host,
              ["127.0.0.1", "localhost"].contains(host) else {
            throw BackendServiceError.nonLocalAddress
        }

        let task = Process()
        if let bundledBackend = Self.bundledBackendExecutable() {
            task.executableURL = bundledBackend
            task.arguments = ["--host", host, "--port", String(url.port ?? 8000)]
        } else {
            guard FileManager.default.fileExists(
                atPath: projectURL.appendingPathComponent("pyproject.toml").path
            ) else {
                throw BackendServiceError.invalidProjectDirectory
            }
            guard let uvExecutable = Self.uvExecutable() else {
                throw BackendServiceError.uvNotFound
            }
            task.executableURL = uvExecutable
            task.arguments = [
                "run", "--project", projectURL.path, "research-agent", "serve",
                "--host", host,
                "--port", String(url.port ?? 8000),
            ]
        }
        task.currentDirectoryURL = workingURL
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        try task.run()
        process = task
    }

    private static func bootstrapEnvironment(projectURL: URL, workingURL: URL) throws {
        let destination = workingURL.appendingPathComponent(".env")
        guard !FileManager.default.fileExists(atPath: destination.path) else { return }
        let source = projectURL.appendingPathComponent(".env")
        if FileManager.default.fileExists(atPath: source.path) {
            try FileManager.default.copyItem(at: source, to: destination)
        } else {
            FileManager.default.createFile(atPath: destination.path, contents: Data())
        }
    }

    private static func bundledBackendExecutable() -> URL? {
        guard let resources = Bundle.main.resourceURL else { return nil }
        let executable = resources
            .appendingPathComponent("backend", isDirectory: true)
            .appendingPathComponent("research-agent-backend")
        return FileManager.default.isExecutableFile(atPath: executable.path) ? executable : nil
    }

    private static func uvExecutable() -> URL? {
        var candidates = [
            "/opt/homebrew/bin/uv",
            "/usr/local/bin/uv",
            "/usr/bin/uv",
        ]
        if let path = ProcessInfo.processInfo.environment["PATH"] {
            candidates.append(contentsOf: path.split(separator: ":").map { "\($0)/uv" })
        }
        return candidates
            .map { URL(fileURLWithPath: $0) }
            .first { FileManager.default.isExecutableFile(atPath: $0.path) }
    }

    func stop() {
        guard let process, process.isRunning else { return }
        process.terminate()
        process.waitUntilExit()
        self.process = nil
    }
}

enum BackendServiceError: LocalizedError {
    case invalidProjectDirectory
    case nonLocalAddress
    case uvNotFound

    var errorDescription: String? {
        switch self {
        case .invalidProjectDirectory:
            return "后端代码目录无效：未找到 pyproject.toml。"
        case .nonLocalAddress:
            return "自动启动仅支持 127.0.0.1 或 localhost 服务地址。"
        case .uvNotFound:
            return "开发构建中未找到内置后端或 uv。请重新构建完整 App。"
        }
    }
}
