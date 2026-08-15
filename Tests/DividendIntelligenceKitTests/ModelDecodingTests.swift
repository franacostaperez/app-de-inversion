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
}
