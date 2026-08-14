import Foundation

@MainActor
public final class AppModel: ObservableObject {
    @Published public private(set) var snapshot: AppSnapshot?
    @Published public private(set) var isLoading = false
    @Published public private(set) var errorMessage: String?

    private let loader: any SnapshotLoading

    public init(loader: any SnapshotLoading = DataRepository()) {
        self.loader = loader
    }

    public func refresh() async {
        isLoading = true
        defer { isLoading = false }
        do {
            snapshot = try await loader.load()
            errorMessage = nil
        } catch {
            errorMessage = "No se pudieron cargar los datos."
        }
    }
}

