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
        let current = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        if FileManager.default.fileExists(atPath: current.appendingPathComponent("pyproject.toml").path) {
            return current.path
        }

        let bundledProject = Bundle.main.bundleURL
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        if FileManager.default.fileExists(atPath: bundledProject.appendingPathComponent("pyproject.toml").path) {
            return bundledProject.path
        }
        return NSHomeDirectory()
    }

    static func register() {
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
