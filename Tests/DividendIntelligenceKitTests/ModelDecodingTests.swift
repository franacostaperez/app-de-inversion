import XCTest
@testable import DividendIntelligenceKit

final class ModelDecodingTests: XCTestCase {
    func testVersionedScoreMaximumsAndLegacyCompatibility() throws {
        let legacy = Data("""
        {"ticker":"BAH","company":"Booz Allen","holders":1,"buying":1,"selling":0}
        """.utf8)
        let old = try JSONDecoder().decode(ConsensusItem.self, from: legacy)
        XCTAssertNil(old.dividendGrowthScoreMaximum)
        XCTAssertNil(old.opportunityScoreMaximum)
        let current = Data("""
        {"ticker":"BAH","company":"Booz Allen","holders":1,"buying":1,"selling":0,
         "dividendGrowthInvestorScore":5,"dividendGrowthScoreMaximum":5,
         "opportunityScore":52,"opportunityScoreMaximum":97}
        """.utf8)
        let updated = try JSONDecoder().decode(ConsensusItem.self, from: current)
        XCTAssertEqual(updated.dividendGrowthScoreMaximum, 5)
        XCTAssertEqual(updated.opportunityScoreMaximum, 97)
    }

    func testMovementActionLabel() {
        XCTAssertEqual(MovementAction.increased.label, "Aumentada")
        XCTAssertEqual(MovementAction.sold.label, "Vendida")
    }

    func testDefaultRepositoryPointsToVersionedGitHubData() {
        XCTAssertEqual(
            DataRepository.defaultRemoteURL.absoluteString,
            "https://raw.githubusercontent.com/franacostaperez/app-de-inversion/main/data/public/snapshot.json"
        )
    }

    func testSnapshotWithoutCNMVDataRemainsCompatible() throws {
        let data = Data("""
        {"generatedAt":"2026-08-28T00:00:00Z","asOfQuarter":"2026-Q2",
         "isDemo":false,"opportunities":[],"investors":[],"consensus":[],"movements":[]}
        """.utf8)
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let snapshot = try decoder.decode(AppSnapshot.self, from: data)
        XCTAssertTrue(snapshot.fundPortfolios.isEmpty)
        XCTAssertNil(snapshot.exchangeRates)
    }

    func testEURConversionUsesSnapshotRateAndKeepsEURUnchanged() throws {
        let data = Data("""
        {"base":"EUR","asOf":"2026-08-28","source":"Banco Central Europeo",
         "sourceURL":"https://www.ecb.europa.eu/","rates":{"EUR":1,"USD":1.25}}
        """.utf8)
        let rates = try JSONDecoder().decode(ExchangeRates.self, from: data)
        XCTAssertEqual(rates.amountInEUR(1, currency: "USD")!, 0.8, accuracy: 0.000_001)
        XCTAssertEqual(rates.amountInEUR(1, currency: "EUR"), 1)
        XCTAssertNil(rates.amountInEUR(1, currency: "CAD"))
    }

    func testCNMVPositionDoesNotRequireFabricatedSharesOrMarketMetrics() throws {
        let data = Data("""
        {"isin":"US76169C1009","company":"Rexford Industrial Realty",
         "reportedCurrency":"USD","value":8898000,"weight":2.75,
         "previousValue":0,"previousWeight":0,"weightChangePoints":2.75,
         "status":"NEW","shares":null,"metrics":null}
        """.utf8)
        let position = try JSONDecoder().decode(FundPosition.self, from: data)
        XCTAssertNil(position.shares)
        XCTAssertNil(position.metrics)
        XCTAssertNil(position.ticker)
        XCTAssertEqual(position.value, 8898000)
    }
}
