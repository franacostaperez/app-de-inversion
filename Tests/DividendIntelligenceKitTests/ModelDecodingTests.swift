import XCTest
@testable import DividendIntelligenceKit

final class ModelDecodingTests: XCTestCase {
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
