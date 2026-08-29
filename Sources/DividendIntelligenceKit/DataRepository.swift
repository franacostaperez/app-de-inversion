import Foundation

public protocol SnapshotLoading: Sendable {
    func load() async throws -> AppSnapshot
}

public enum SnapshotError: Error {
    case invalidResponse
}

public struct DataRepository: SnapshotLoading {
    public static let defaultRemoteURL = URL(
        string: "https://raw.githubusercontent.com/franacostaperez/app-de-inversion/main/data/public/snapshot.json"
    )!

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
        guard let remoteURL else {
            throw SnapshotError.invalidResponse
        }
        var request = URLRequest(url: remoteURL, cachePolicy: .reloadIgnoringLocalCacheData)
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw SnapshotError.invalidResponse
        }
        return try decoder.decode(AppSnapshot.self, from: data)
    }

    public static func configuredRemoteURL(bundle: Bundle = .main) -> URL? {
        guard let value = bundle.object(forInfoDictionaryKey: "DIVIDEND_DATA_URL") as? String else {
            return defaultRemoteURL
        }
        return URL(string: value) ?? defaultRemoteURL
    }
}
