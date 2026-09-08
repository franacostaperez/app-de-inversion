import XCTest
@testable import DividendIntelligenceKit

final class PersonalDividendsTests: XCTestCase {
    func testDecodesPersonalDividendSnapshot() throws {
        let json = #"""
        {
          "asOf":"2026-09-04",
          "currency":"EUR",
          "source":{"kind":"google_sheets","spreadsheetId":"sheet","tab":"Dividendos","authority":"XTB"},
          "summary":{"historicalTotalEUR":776.67,"currentYearEUR":562.52,"last12MonthsEUR":753.26,"historicalAnnualRunRateEUR":753.26,"averageMonthlyLast12EUR":62.77,"receiptCount":251,"companyCount":72},
          "concentration":{"top5Pct":29.05,"top10Pct":44.99},
          "byType":[{"type":"Acción","amountEUR":722.05,"sharePct":92.97}],
          "goals":[{"targetEUR":1000,"progressPct":75.33,"remainingEUR":246.74}],
          "monthly":[{"month":"2026-09","amountEUR":20.67}],
          "ranking":[{"ticker":"LYB.US","company":"LyondellBasell Industries","type":"Acción","amountEUR":64.18,"sharePct":8.26}],
          "receipts":[{"date":"2026-09-04","company":"Example","ticker":"EX.US","market":"US","type":"Acción","amountEUR":1.23,"noticeURL":"https://example.com","noticeID":"abc"}],
          "futureIncome":{"status":"needs_current_portfolio","annualEstimateEUR":null,"next12MonthsEUR":null,"remainderCurrentYearEUR":null}
        }
        """#.data(using: .utf8)!

        let value = try JSONDecoder().decode(PersonalDividendSnapshot.self, from: json)
        XCTAssertEqual(value.summary.last12MonthsEUR, 753.26, accuracy: 0.001)
        XCTAssertEqual(value.goals.first?.targetEUR, 1000)
        XCTAssertEqual(value.receipts.first?.noticeID, "abc")
        XCTAssertEqual(value.futureIncome.status, "needs_current_portfolio")
    }
}
