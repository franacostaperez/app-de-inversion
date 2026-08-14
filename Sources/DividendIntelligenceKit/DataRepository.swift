import Foundation

public protocol SnapshotLoading: Sendable {
    func load() async throws -> AppSnapshot
}

public enum SnapshotError: Error {
    case missingBundledData
    case invalidResponse
}

public struct DataRepository: SnapshotLoading {
    private let remoteURL: URL?
    private let session: URLSession
    private let decoder: JSONDecoder

    public init(remoteURL: URL? = DataRepository.configuredRemoteURL(), session: URLSession = .shared) {
        self.remoteURL = remoteURL
        self.session = session
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        self.decoder = decoder
    }

    public func load() async throws -> AppSnapshot {
        if let remoteURL {
            do {
                let (data, response) = try await session.data(from: remoteURL)
                guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
                    throw SnapshotError.invalidResponse
                }
                return try decoder.decode(AppSnapshot.self, from: data)
            } catch {
                // Offline-first: the bundled snapshot keeps the app usable.
            }
        }
        guard let url = Bundle.module.url(forResource: "snapshot", withExtension: "json") else {
            throw SnapshotError.missingBundledData
        }
        return try decoder.decode(AppSnapshot.self, from: Data(contentsOf: url))
    }

    public static func configuredRemoteURL(bundle: Bundle = .main) -> URL? {
        guard let value = bundle.object(forInfoDictionaryKey: "DIVIDEND_DATA_URL") as? String else { return nil }
        return URL(string: value)
    }
}

