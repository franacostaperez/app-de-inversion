import SwiftUI
import DividendIntelligenceKit

struct OpportunitiesView: View {
    let items: [Opportunity]
    var body: some View {
        List(items) { item in OpportunityCard(item: item).listRowSeparator(.hidden) }
            .listStyle(.plain).navigationTitle("Oportunidades")
    }
}

struct CompaniesView: View {
    let items: [Opportunity]
    var body: some View {
        List(items) { item in
            NavigationLink {
                CompanyDetailView(item: item)
            } label: {
                HStack {
                    VStack(alignment: .leading) { Text(item.ticker).bold(); Text(item.company).font(.caption).foregroundStyle(.secondary) }
                    Spacer(); Text("\(item.franScore)").foregroundStyle(.mint).bold()
                }
            }
        }.navigationTitle("Empresas")
    }
}

private struct CompanyDetailView: View {
    let item: Opportunity
    var body: some View {
        List {
            Section("Métricas") {
                LabeledContent("Yield", value: item.yield.formatted() + "%")
                LabeledContent("PER", value: item.pe?.formatted() ?? "—")
                LabeledContent("Payout", value: item.payout.map { $0.formatted() + "%" } ?? "—")
                LabeledContent("Crecimiento dividendo 5A", value: item.dividendGrowth5Y.map { $0.formatted() + "%" } ?? "—")
                LabeledContent("Deuda / EBITDA", value: item.debtToEBITDA?.formatted() ?? "—")
            }
            Section("Fran Score") {
                LabeledContent("Valoración", value: "\(item.valuationScore)")
                LabeledContent("Dividendo", value: "\(item.dividendScore)")
                LabeledContent("Calidad", value: "\(item.qualityScore)")
                LabeledContent("Smart Money", value: "\(item.smartMoneyScore)")
            }
        }.navigationTitle(item.ticker)
    }
}

struct SmartMoneyView: View {
    let snapshot: AppSnapshot
    var body: some View {
        List {
            Section("Consenso") {
                ForEach(snapshot.consensus) { item in
                    VStack(alignment: .leading) {
                        HStack { Text(item.ticker).bold(); Spacer(); Text("\(item.holders) gestores") }
                        Text("\(item.buying) comprando · \(item.selling) reduciendo").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Section("Últimos movimientos") {
                ForEach(snapshot.movements) { item in
                    HStack {
                        Image(systemName: icon(item.action)).foregroundStyle(color(item.action))
                        VStack(alignment: .leading) { Text("\(item.investorName) · \(item.ticker)"); Text(item.action.label).font(.caption).foregroundStyle(.secondary) }
                    }
                }
            }
        }.navigationTitle("Smart Money")
    }

    private func icon(_ action: MovementAction) -> String {
        switch action { case .new: "plus.circle.fill"; case .increased: "arrow.up.circle.fill"; case .reduced: "arrow.down.circle.fill"; case .sold: "xmark.circle.fill"; case .unchanged: "equal.circle.fill" }
    }
    private func color(_ action: MovementAction) -> Color {
        switch action { case .new, .increased: .green; case .reduced: .yellow; case .sold: .red; case .unchanged: .gray }
    }
}

struct PortfolioPlaceholderView: View {
    var body: some View {
        ContentUnavailableView("Tu cartera", systemImage: "briefcase", description: Text("La persistencia personal con SwiftData llegará en la siguiente iteración."))
            .navigationTitle("Cartera")
    }
}

