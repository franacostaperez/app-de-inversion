import XCTest
@testable import DividendIntelligenceKit

final class ModelDecodingTests: XCTestCase {
    func testMovementActionLabel() {
        XCTAssertEqual(MovementAction.increased.label, "Aumentada")
        XCTAssertEqual(MovementAction.sold.label, "Vendida")
    }
}

