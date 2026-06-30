import Foundation
import Observation

@MainActor
@Observable
final class BackendService {
    private var process: Process?

    var isManagedProcessRunning: Bool {
        process?.isRunning == true
    }

    func start(projectDirectory: String, apiBaseURL: String) throws {
        if process?.isRunning == true { return }

        let projectURL = URL(fileURLWithPath: projectDirectory, isDirectory: true)
        guard FileManager.default.fileExists(atPath: projectURL.appendingPathComponent("pyproject.toml").path) else {
            throw BackendServiceError.invalidProjectDirectory
        }
        guard let url = URL(string: apiBaseURL),
              let host = url.host,
              ["127.0.0.1", "localhost"].contains(host) else {
            throw BackendServiceError.nonLocalAddress
        }

        guard let uvExecutable = Self.uvExecutable() else {
            throw BackendServiceError.uvNotFound
        }

        let task = Process()
        task.executableURL = uvExecutable
        task.arguments = [
            "run", "research-agent", "serve",
            "--host", host,
            "--port", String(url.port ?? 8000),
        ]
        task.currentDirectoryURL = projectURL
        task.standardOutput = FileHandle.nullDevice
        task.standardError = FileHandle.nullDevice
        try task.run()
        process = task
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
            return "项目目录无效：未找到 pyproject.toml。"
        case .nonLocalAddress:
            return "自动启动仅支持 127.0.0.1 或 localhost 服务地址。"
        case .uvNotFound:
            return "未找到 uv，请先安装 uv，或手动启动 FastAPI 服务。"
        }
    }
}
