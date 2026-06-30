import Foundation
import Observation

@MainActor
@Observable
final class AppStore {
    var reports: [Report] = []
    var selectedReportID: String?
    var health: HealthStatus?
    var isLoading = false
    var isGenerating = false
    var answeringReportIDs: Set<String> = []
    var chatMessages: [String: [ChatMessage]] = [:]
    var errorMessage: String?
    var environmentConfig: EnvironmentConfig?
    var isLoadingConfiguration = false
    var isSavingConfiguration = false
    var configurationMessage: String?

    let backend = BackendService()
    private var didBootstrap = false

    init() {
        AppDefaults.register()
    }

    var selectedReport: Report? {
        reports.first { $0.id == selectedReportID }
    }

    func bootstrap() async {
        guard !didBootstrap else { return }
        didBootstrap = true

        if await refreshHealth(silent: true) == false,
           UserDefaults.standard.bool(forKey: PreferenceKeys.autoStartBackend) {
            do {
                try startBackend()
                for _ in 0..<20 {
                    try? await Task.sleep(for: .milliseconds(400))
                    if await refreshHealth(silent: true) { break }
                }
            } catch {
                errorMessage = error.localizedDescription
            }
        }
        await loadReports()
    }

    @discardableResult
    func refreshHealth(silent: Bool = false) async -> Bool {
        do {
            health = try await client().health()
            return true
        } catch {
            health = nil
            if !silent { errorMessage = error.localizedDescription }
            return false
        }
    }

    func loadReports() async {
        isLoading = true
        defer { isLoading = false }
        do {
            reports = try await client().listReports()
            if selectedReportID == nil || !reports.contains(where: { $0.id == selectedReportID }) {
                selectedReportID = reports.first?.id
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func createReport(_ request: CreateReportRequest) async -> Bool {
        isGenerating = true
        defer { isGenerating = false }
        do {
            let report = try await client().createReport(request)
            reports.removeAll { $0.id == report.id }
            reports.append(report)
            sortReports()
            selectedReportID = report.id
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func renameReport(_ report: Report, title: String) async -> Bool {
        let normalized = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalized.isEmpty else {
            errorMessage = "研报标题不能为空。"
            return false
        }
        do {
            replaceReport(try await client().updateReport(reportID: report.id, title: normalized))
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func togglePinned(_ report: Report) async {
        do {
            replaceReport(
                try await client().updateReport(
                    reportID: report.id, isPinned: !report.isPinned
                )
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteReport(_ report: Report) async {
        do {
            try await client().deleteReport(reportID: report.id)
            reports.removeAll { $0.id == report.id }
            chatMessages[report.id] = nil
            if selectedReportID == report.id {
                selectedReportID = reports.first?.id
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    func loadEnvironmentConfiguration() async -> Bool {
        isLoadingConfiguration = true
        defer { isLoadingConfiguration = false }
        do {
            environmentConfig = try await client().loadEnvironmentConfig()
            configurationMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    @discardableResult
    func saveEnvironmentConfiguration(_ values: [String: String]) async -> Bool {
        isSavingConfiguration = true
        configurationMessage = nil
        defer { isSavingConfiguration = false }
        do {
            environmentConfig = try await client().saveEnvironmentConfig(values)
            let shouldRestart = backend.isManagedProcessRunning
            if shouldRestart {
                backend.stop()
                try startBackend()
                for _ in 0..<20 {
                    try? await Task.sleep(for: .milliseconds(400))
                    if await refreshHealth(silent: true) { break }
                }
                await loadReports()
                configurationMessage = "配置已保存，本地服务已重启。"
            } else {
                configurationMessage = "配置已写入 .env；请重启当前服务后生效。"
            }
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func ask(reportID: String, question: String) async {
        let trimmed = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !answeringReportIDs.contains(reportID) else { return }

        chatMessages[reportID, default: []].append(ChatMessage(role: .user, content: trimmed))
        answeringReportIDs.insert(reportID)
        defer { answeringReportIDs.remove(reportID) }

        do {
            let response = try await client().chat(reportID: reportID, question: trimmed)
            chatMessages[reportID, default: []].append(
                ChatMessage(role: .assistant, content: response.answer, citations: response.citations)
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func startBackend() throws {
        try backend.start(
            projectDirectory: UserDefaults.standard.string(forKey: PreferenceKeys.backendDirectory)
                ?? AppDefaults.backendDirectory,
            apiBaseURL: UserDefaults.standard.string(forKey: PreferenceKeys.apiBaseURL)
                ?? AppDefaults.apiBaseURL
        )
    }

    func restartConnection() async {
        health = nil
        if UserDefaults.standard.bool(forKey: PreferenceKeys.autoStartBackend) {
            do {
                if backend.isManagedProcessRunning {
                    backend.stop()
                }
                try startBackend()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
        _ = await refreshHealth()
        await loadReports()
    }

    private func client() throws -> APIClient {
        try APIClient(
            baseURLString: UserDefaults.standard.string(forKey: PreferenceKeys.apiBaseURL)
                ?? AppDefaults.apiBaseURL
        )
    }

    private func replaceReport(_ report: Report) {
        reports.removeAll { $0.id == report.id }
        reports.append(report)
        sortReports()
    }

    private func sortReports() {
        reports.sort {
            if $0.isPinned != $1.isPinned { return $0.isPinned && !$1.isPinned }
            return $0.createdAt > $1.createdAt
        }
    }
}
