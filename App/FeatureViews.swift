import SwiftUI
#if canImport(DividendIntelligenceKit)
import DividendIntelligenceKit
#endif

struct OpportunitiesView: View {
    let items: [Opportunity]
    var body: some View {
        List(items) { item in OpportunityCard(item: item).listRowSeparator(.hidden) }
            .listStyle(.plain).navigationTitle("Oportunidades")
    }
}

struct CompaniesView: View {
    let snapshot: AppSnapshot

    var body: some View {
        List(snapshot.holdings) { holding in
            NavigationLink {
                if let opportunity = snapshot.opportunities.first(where: { $0.ticker == holding.ticker }) {
                    CompanyDetailView(item: opportunity)
                } else {
                    HoldingDetailView(item: holding, quarter: snapshot.asOfQuarter)
                }
            } label: {
                HStack {
                    VStack(alignment: .leading) {
                        Text(holding.ticker).bold()
                        Text(holding.company).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(holding.weight.formatted(.number.precision(.fractionLength(2))) + "%")
                        .foregroundStyle(.mint).bold()
                }
            }
        }.navigationTitle("Empresas")
    }
}

private struct HoldingDetailView: View {
    let item: Holding
    let quarter: String

    var body: some View {
        List {
            Section("Posición 13F · \(quarter)") {
                LabeledContent("Gestor", value: item.investorName)
                LabeledContent("CUSIP", value: item.cusip)
                LabeledContent("Acciones", value: item.shares.formatted())
                LabeledContent("Valor declarado", value: item.value.formatted(.currency(code: "USD")))
                LabeledContent("Peso", value: item.weight.formatted(.number.precision(.fractionLength(2))) + "%")
            }
            Section {
                Text("Las métricas de dividendo y valoración se añadirán cuando exista una correspondencia fiable de ticker y proveedor financiero.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle(item.ticker)
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
            Section("Portfolio 13F · \(snapshot.asOfQuarter)") {
                if snapshot.holdings.isEmpty {
                    Text("El snapshot todavía no contiene posiciones.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(snapshot.holdings) { item in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(item.ticker).bold()
                                Spacer()
                                Text(item.weight.formatted(.number.precision(.fractionLength(2))) + "%")
                                    .foregroundStyle(.mint)
                            }
                            Text(item.company)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            HStack {
                                Text(item.shares.formatted(.number.notation(.compactName)) + " acciones")
                                Spacer()
                                Text(compactUSD(item.value))
                            }
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                        }
                    }
                }
            }
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

    private func compactUSD(_ value: Double) -> String {
        if value >= 1_000_000_000 { return String(format: "$%.1fB", value / 1_000_000_000) }
        if value >= 1_000_000 { return String(format: "$%.1fM", value / 1_000_000) }
        if value >= 1_000 { return String(format: "$%.1fK", value / 1_000) }
        return value.formatted(.currency(code: "USD"))
    }
}

struct PortfolioPlaceholderView: View {
    var body: some View {
        ContentUnavailableView("Tu cartera", systemImage: "briefcase", description: Text("La persistencia personal con SwiftData llegará en la siguiente iteración."))
            .navigationTitle("Cartera")
    }
}
