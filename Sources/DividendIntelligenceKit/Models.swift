import Foundation

public struct AppSnapshot: Codable, Sendable {
    public let generatedAt: Date
    public let asOfQuarter: String
    public let isDemo: Bool
    public let opportunities: [Opportunity]
    public let investors: [Investor]
    public let consensus: [ConsensusItem]
    public let movements: [Movement]
    public let holdings: [Holding]
    public let filings: [FilingRecord]
    public let filingUpdates: [FilingUpdate]
    public let companyProfiles: [CompanyProfile]
    public let companyReports: [CompanyReport]

    enum CodingKeys: String, CodingKey {
        case generatedAt, asOfQuarter, isDemo, opportunities, investors, consensus, movements, holdings, filings, filingUpdates, companyProfiles, companyReports
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        generatedAt = try container.decode(Date.self, forKey: .generatedAt)
        asOfQuarter = try container.decode(String.self, forKey: .asOfQuarter)
        isDemo = try container.decode(Bool.self, forKey: .isDemo)
        opportunities = try container.decode([Opportunity].self, forKey: .opportunities)
        investors = try container.decode([Investor].self, forKey: .investors)
        consensus = try container.decode([ConsensusItem].self, forKey: .consensus)
        movements = try container.decode([Movement].self, forKey: .movements)
        holdings = try container.decodeIfPresent([Holding].self, forKey: .holdings) ?? []
        filings = try container.decodeIfPresent([FilingRecord].self, forKey: .filings) ?? []
        filingUpdates = try container.decodeIfPresent([FilingUpdate].self, forKey: .filingUpdates) ?? []
        companyProfiles = try container.decodeIfPresent([CompanyProfile].self, forKey: .companyProfiles) ?? []
        companyReports = try container.decodeIfPresent([CompanyReport].self, forKey: .companyReports) ?? []
    }
}

public struct CompanyReport: Codable, Identifiable, Sendable {
    public var id: String { accessionNumber }
    public let cusip: String
    public let ticker: String?
    public let companyName: String
    public let cik: String
    public let accessionNumber: String
    public let form: String
    public let filingDate: Date
    public let reportDate: Date
    public let secURL: URL
    public let source: String
    public let summary: CompanyReportSummary
    public let highlights: String
    public let metrics: [String: FinancialMetric]
}

public struct CompanyReportSummary: Codable, Sendable {
    public let revenue: Double?
    public let expenses: Double?
    public let operatingIncome: Double?
    public let netIncome: Double?
    public let operatingMargin: Double?
    public let roce: Double?
    public let netMargin: Double?
    public let totalDebt: Double?
    public let cash: Double?
    public let cashFromOperations: Double?
    public let capitalExpenditure: Double?
    public let dividendsPaid: Double?
    public let dividendPerShare: Double?
    public let epsDiluted: Double?
    public let expectedRevenue: Double?
    public let expectedEPS: Double?
}

public struct FinancialMetric: Codable, Sendable {
    public let concept: String
    public let periods: [FinancialPeriod]
}

public struct FinancialPeriod: Codable, Identifiable, Sendable {
    public var id: String { "\(startDate ?? "instant")-\(endDate)-\(value)" }
    public let startDate: String?
    public let endDate: String
    public let value: Double
    public let unit: String
    public let fiscalYear: Int?
    public let fiscalPeriod: String?
    public let frame: String?
}

public struct FilingUpdate: Codable, Identifiable, Sendable {
    public var id: String { accessionNumber }
    public let investorId: String
    public let investorName: String
    public let accessionNumber: String
    public let filingDate: Date
    public let reportDate: Date
    public let quarter: String
    public let secURL: URL
    public let positions: Int
    public let newPositions: Int
    public let increasedPositions: Int
    public let reducedPositions: Int
    public let soldPositions: Int
    public let portfolioValue: Double
    public let summary: String
}

public struct CompanyProfile: Codable, Identifiable, Sendable {
    public var id: String { cusip }
    public let cusip: String
    public let name: String
    public let ticker: String?
    public let description: String?
    public let businessModel: String?
    public let revenueModel: String?
    public let economicMoat: String?
    public let brandStrength: String?
    public let exchange: String?
    public let currency: String?
    public let country: String?
    public let sector: String?
    public let industry: String?
    public let marketCapitalization: Double?
    public let marketPrice: Double?
    public let movingAverage1000: Double?
    public let priceVsMovingAverage1000Percent: Double?
    public let movingAverage1000Sessions: Int?
    public let movingAverage1000AsOf: String?
    public let priceHistorySource: String?
    public let paysDividend: Bool?
    public let dividendPerShare: Double?
    public let dividendYield: Double?
    public let peRatio: Double?
    public let eps: Double?
    public let latestQuarterlyReportURL: URL?
    public let latestQuarterlyReportDate: String?
    public let latestAnnualReportURL: URL?
    public let latestAnnualReportDate: String?
    public let investorRelationsURL: URL?
    public let investorRelationsVerified: Bool?
    public let source: String
    public let status: String
    public let updatedAt: Date
}

public struct FilingRecord: Codable, Identifiable, Sendable {
    public var id: String { accessionNumber }
    public let investorId: String
    public let investorName: String
    public let cik: String
    public let form: String
    public let accessionNumber: String
    public let filingDate: Date
    public let reportDate: Date
    public let quarter: String
    public let secURL: URL
}

public struct Holding: Codable, Identifiable, Sendable {
    public var id: String { "\(investorId)-\(cusip)" }
    public let investorId: String
    public let investorName: String
    public let ticker: String
    public let cusip: String
    public let company: String
    public let shares: Double
    public let value: Double
    public let weight: Double
    public let estimatedAveragePurchasePrice: Double?
}

public struct Opportunity: Codable, Identifiable, Sendable {
    public var id: String { ticker }
    public let ticker: String
    public let cusip: String?
    public let company: String
    public let sector: String
    public let yield: Double
    public let pe: Double?
    public let operatingMargin: Double?
    public let dividendGrowth5Y: Double?
    public let debtToEBITDA: Double?
    public let franScore: Int
    public let valuationScore: Int
    public let dividendScore: Int
    public let qualityScore: Int
    public let smartMoneyScore: Int
    public let gurusBuying: Int
}

public struct Investor: Codable, Identifiable, Sendable {
    public let id: String
    public let name: String
    public let manager: String?
    public let quarter: String?
    public let filingDate: Date
    public let quarterEnd: Date
    public let portfolioValue: Double
}

public enum MovementAction: String, Codable, Sendable {
    case new = "NEW"
    case increased = "INCREASED"
    case reduced = "REDUCED"
    case sold = "SOLD"
    case unchanged = "UNCHANGED"

    public var label: String {
        switch self {
        case .new: "Nueva"
        case .increased: "Aumentada"
        case .reduced: "Reducida"
        case .sold: "Vendida"
        case .unchanged: "Sin cambios"
        }
    }
}

public struct Movement: Codable, Identifiable, Sendable {
    public var id: String { "\(investorId)-\(ticker)-\(action.rawValue)" }
    public let investorId: String
    public let investorName: String
    public let ticker: String
    public let cusip: String?
    public let company: String
    public let action: MovementAction
    public let shares: Double
    public let previousShares: Double?
    public let changePercent: Double?
}

public struct ConsensusItem: Codable, Identifiable, Sendable {
    public var id: String { cusip ?? ticker }
    public let ticker: String
    public let cusip: String?
    public let company: String
    public let holders: Int
    public let buying: Int
    public let selling: Int
    public let newPositions: Int?
    public let yield: Double?
    public let pe: Double?
    public let peNotMeaningful: Bool?
    public let earningsPerShare: Double?
    public let peCalculation: String?
    public let marketPrice: Double?
    public let movingAverage1000: Double?
    public let priceVsMovingAverage1000Percent: Double?
    public let operatingMargin: Double?
    public let roce: Double?
    public let dividendGrowth: Double?
    public let yieldInvestorScore: Int?
    public let dividendGrowthInvestorScore: Int?
    public let opportunityScore: Int?
    public let opportunityRank: Int?
    public let previousOpportunityRank: Int?
    public let rankChange: Int?
    public let rankStatus: String?
    public let scoreStatus: String?
    public let missingScoreMetrics: [String]?
    public let scoreCoverage: Int?
    public let dividendInvestorScore: Int?
    public let valuationInvestorScore: Int?
    public let movingAverageInvestorScore: Int?
    public let profitabilityInvestorScore: Int?
    public let operatingMarginRating: Int?
    public let consensusInvestorScore: Int?
    public let sector: String?
    public let sectorPEBenchmark: Double?
    public let brandPremiumApplied: Bool?
}
