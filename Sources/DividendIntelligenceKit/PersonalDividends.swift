import Foundation

public struct PersonalDividendSnapshot: Codable, Sendable {
    public let asOf: String
    public let currency: String
    public let source: PersonalDividendSource
    public let summary: PersonalDividendSummary
    public let concentration: PersonalDividendConcentration
    public let byType: [PersonalDividendTypeBreakdown]
    public let goals: [PersonalDividendGoal]
    public let monthly: [PersonalDividendMonth]
    public let ranking: [PersonalDividendRanking]
    public let receipts: [PersonalDividendReceipt]
    public let futureIncome: PersonalFutureIncome
}

public struct PersonalDividendSource: Codable, Sendable {
    public let kind: String
    public let spreadsheetId: String?
    public let tab: String
    public let authority: String
}

public struct PersonalDividendSummary: Codable, Sendable {
    public let historicalTotalEUR: Double
    public let currentYearEUR: Double
    public let last12MonthsEUR: Double
    public let historicalAnnualRunRateEUR: Double
    public let averageMonthlyLast12EUR: Double
    public let receiptCount: Int
    public let companyCount: Int
}

public struct PersonalDividendConcentration: Codable, Sendable {
    public let top5Pct: Double
    public let top10Pct: Double
}

public struct PersonalDividendTypeBreakdown: Codable, Identifiable, Sendable {
    public var id: String { type }
    public let type: String
    public let amountEUR: Double
    public let sharePct: Double
}

public struct PersonalDividendGoal: Codable, Identifiable, Sendable {
    public var id: Double { targetEUR }
    public let targetEUR: Double
    public let progressPct: Double
    public let remainingEUR: Double
}

public struct PersonalDividendMonth: Codable, Identifiable, Sendable {
    public var id: String { month }
    public let month: String
    public let amountEUR: Double
}

public struct PersonalDividendRanking: Codable, Identifiable, Sendable {
    public var id: String { ticker }
    public let ticker: String
    public let company: String
    public let type: String
    public let amountEUR: Double
    public let sharePct: Double
}

public struct PersonalDividendReceipt: Codable, Identifiable, Sendable {
    public var id: String { noticeID }
    public let date: String
    public let company: String
    public let ticker: String
    public let market: String
    public let type: String
    public let amountEUR: Double
    public let noticeURL: URL?
    public let noticeID: String
}

public struct PersonalFutureIncome: Codable, Sendable {
    public let status: String
    public let annualEstimateEUR: Double?
    public let next12MonthsEUR: Double?
    public let remainderCurrentYearEUR: Double?
}

public struct PersonalDividendsRepository: Sendable {
    public static let defaultRemoteURL = URL(
        string: "https://raw.githubusercontent.com/franacostaperez/app-de-inversion/main/data/public/xtb-dividends.json"
    )!

    private let remoteURL: URL
    private let session: URLSession

    public init(remoteURL: URL = defaultRemoteURL, session: URLSession = .shared) {
        self.remoteURL = remoteURL
        self.session = session
    }

    public func load() async throws -> PersonalDividendSnapshot {
        var request = URLRequest(url: remoteURL, cachePolicy: .reloadIgnoringLocalCacheData)
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw SnapshotError.invalidResponse
        }
        return try JSONDecoder().decode(PersonalDividendSnapshot.self, from: data)
    }
}
