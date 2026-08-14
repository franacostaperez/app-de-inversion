import Foundation

public struct AppSnapshot: Codable, Sendable {
    public let generatedAt: Date
    public let asOfQuarter: String
    public let isDemo: Bool
    public let opportunities: [Opportunity]
    public let investors: [Investor]
    public let consensus: [ConsensusItem]
    public let movements: [Movement]
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
    public let changePercent: Double?
}

public struct ConsensusItem: Codable, Identifiable, Sendable {
    public var id: String { ticker }
    public let ticker: String
    public let company: String
    public let holders: Int
    public let buying: Int
    public let selling: Int
    public let yield: Double?
}

