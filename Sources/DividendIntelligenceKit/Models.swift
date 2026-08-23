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

    enum CodingKeys: String, CodingKey {
        case generatedAt, asOfQuarter, isDemo, opportunities, investors, consensus, movements, holdings, filings, filingUpdates, companyProfiles
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
    }
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
    public let exchange: String?
    public let currency: String?
    public let country: String?
    public let sector: String?
    public let industry: String?
    public let marketCapitalization: Double?
    public let paysDividend: Bool?
    public let dividendPerShare: Double?
    public let dividendYield: Double?
    public let peRatio: Double?
    public let eps: Double?
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
    public let company: String
    public let sector: String
    public let yield: Double
    public let pe: Double?
    public let payout: Double?
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
    public let yield: Double?
    public let pe: Double?
    public let opportunityScore: Int?
    public let dividendInvestorScore: Int?
    public let valuationInvestorScore: Int?
    public let consensusInvestorScore: Int?
}
