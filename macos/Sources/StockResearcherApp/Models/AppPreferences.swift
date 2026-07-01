import Foundation

enum PreferenceKeys {
    static let apiBaseURL = "apiBaseURL"
    static let backendDirectory = "backendDirectory"
    static let autoStartBackend = "autoStartBackend"
    static let defaultMode = "defaultMode"
    static let defaultWebSearch = "defaultWebSearch"
    static let defaultMaxResults = "defaultMaxResults"
    static let sourceAnnualReport = "sourceAnnualReport"
    static let sourceQuarterlyReport = "sourceQuarterlyReport"
    static let sourceAnnouncement = "sourceAnnouncement"
    static let sourceResearch = "sourceResearch"
}

enum AppDefaults {
    static let apiBaseURL = "http://127.0.0.1:8000"
    static let defaultMode = "standard"

    static var backendDirectory: String {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".stock_researcher", isDirectory: true)
            .path
    }

    static var projectDirectory: String {
        var candidates: [URL] = []
        if let configured = ProcessInfo.processInfo.environment["STOCK_RESEARCHER_PROJECT_DIR"] {
            candidates.append(URL(fileURLWithPath: configured, isDirectory: true))
        }
        let current = URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true)
        candidates.append(current)
        candidates.append(current.deletingLastPathComponent())

        var bundleAncestor = Bundle.main.bundleURL
        for _ in 0..<6 {
            bundleAncestor.deleteLastPathComponent()
            candidates.append(bundleAncestor)
        }

        // SwiftPM development builds retain the source location. This keeps
        // the Python project separate from the user's writable app directory.
        var sourceAncestor = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { sourceAncestor.deleteLastPathComponent() }
        candidates.append(sourceAncestor)

        return candidates.first {
            FileManager.default.fileExists(
                atPath: $0.appendingPathComponent("pyproject.toml").path
            )
        }?.path ?? current.path
    }

    static func register() {
        let defaults = UserDefaults.standard
        if let legacyDirectory = defaults.string(forKey: PreferenceKeys.backendDirectory),
           FileManager.default.fileExists(
               atPath: URL(fileURLWithPath: legacyDirectory)
                   .appendingPathComponent("pyproject.toml").path
           ) {
            defaults.set(backendDirectory, forKey: PreferenceKeys.backendDirectory)
        }
        UserDefaults.standard.register(defaults: [
            PreferenceKeys.apiBaseURL: apiBaseURL,
            PreferenceKeys.backendDirectory: backendDirectory,
            PreferenceKeys.autoStartBackend: true,
            PreferenceKeys.defaultMode: defaultMode,
            PreferenceKeys.defaultWebSearch: true,
            PreferenceKeys.defaultMaxResults: 6,
            PreferenceKeys.sourceAnnualReport: true,
            PreferenceKeys.sourceQuarterlyReport: true,
            PreferenceKeys.sourceAnnouncement: true,
            PreferenceKeys.sourceResearch: true,
        ])
    }

    static var selectedSourceTypes: [String] {
        let defaults = UserDefaults.standard
        return [
            defaults.bool(forKey: PreferenceKeys.sourceAnnualReport) ? "annual_report" : nil,
            defaults.bool(forKey: PreferenceKeys.sourceQuarterlyReport) ? "quarterly_report" : nil,
            defaults.bool(forKey: PreferenceKeys.sourceAnnouncement) ? "announcement" : nil,
            defaults.bool(forKey: PreferenceKeys.sourceResearch) ? "research" : nil,
        ].compactMap { $0 }
    }
}
