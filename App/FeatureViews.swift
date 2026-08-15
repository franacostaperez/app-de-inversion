import SwiftUI
#if canImport(DividendIntelligenceKit)
import DividendIntelligenceKit
#endif

struct OpportunitiesView: View {
    let items: [Opportunity]
    var body: some View {
        Group {
            if items.isEmpty {
                ContentUnavailableView(
                    "Sin oportunidades calculadas",
                    systemImage: "checkmark.shield",
                    description: Text("Se mostrarán cuando conectemos métricas financieras verificadas. No se utilizan datos de ejemplo.")
                )
            } else {
                List(items) { item in OpportunityCard(item: item).listRowSeparator(.hidden) }
                    .listStyle(.plain)
            }
        }
        .navigationTitle("Oportunidades")
    }
}

struct FilingsView: View {
    let items: [FilingRecord]

    var body: some View {
        Group {
            if items.isEmpty {
                ContentUnavailableView(
                    "Sin historial 13F",
                    systemImage: "doc.text.magnifyingglass",
                    description: Text("Ejecuta de nuevo la actualización de datos para importar el historial de EDGAR.")
                )
            } else {
                List(items) { filing in
                    Link(destination: filing.secURL) {
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text(filing.investorName).font(.headline).foregroundStyle(.primary)
                                Spacer()
                                Image(systemName: "arrow.up.right.square").foregroundStyle(.mint)
                            }
                            Text("\(filing.quarter) · \(filing.form)")
                                .font(.subheadline).foregroundStyle(.secondary)
                            HStack {
                                Text(filing.filingDate.formatted(date: .abbreviated, time: .omitted))
                                Spacer()
                                Text(filing.accessionNumber)
                            }
                            .font(.caption2).foregroundStyle(.tertiary)
                        }
                        .padding(.vertical, 4)
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Presentaciones 13F")
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
                    HoldingDetailView(
                        item: holding,
                        quarter: snapshot.asOfQuarter,
                        profile: snapshot.companyProfiles.first(where: { $0.cusip == holding.cusip })
                    )
                }
            } label: {
                HStack {
                    VStack(alignment: .leading) {
                        Text(holding.company).bold()
                        Text("Periodo \(snapshot.asOfQuarter)")
                            .font(.caption).foregroundStyle(.secondary)
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
    let profile: CompanyProfile?

    var body: some View {
        List {
            Section("Posición 13F · \(quarter)") {
                LabeledContent("Periodo reportado", value: quarter)
                LabeledContent("Gestor", value: item.investorName)
                LabeledContent("Acciones", value: item.shares.formatted())
                LabeledContent("Valor declarado", value: item.value.formatted(.currency(code: "USD")))
                LabeledContent("Peso", value: item.weight.formatted(.number.precision(.fractionLength(2))) + "%")
            }
            if let profile, profile.status == "enriched" {
                if let description = profile.description {
                    Section("Actividad") { Text(description) }
                }
                Section("Empresa") {
                    if let sector = profile.sector { LabeledContent("Sector", value: sector) }
                    if let industry = profile.industry { LabeledContent("Industria", value: industry) }
                    if let country = profile.country { LabeledContent("País", value: country) }
                    if let marketCap = profile.marketCapitalization {
                        LabeledContent("Capitalización", value: compactUSD(marketCap))
                    }
                    if let paysDividend = profile.paysDividend {
                        LabeledContent("Reparte dividendos", value: paysDividend ? "Sí" : "No")
                    }
                    if let yield = profile.dividendYield, yield > 0 {
                        LabeledContent("Dividend yield", value: yield.formatted(.percent.precision(.fractionLength(2))))
                    }
                    if let pe = profile.peRatio { LabeledContent("PER", value: pe.formatted()) }
                }
                Section { Text("Fuente: \(profile.source)").font(.caption).foregroundStyle(.secondary) }
            } else {
                Section {
                    Text("Perfil empresarial pendiente de enriquecimiento en GitHub.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle(item.company)
    }

    private func compactUSD(_ value: Double) -> String {
        if value >= 1_000_000_000 { return String(format: "$%.1fB", value / 1_000_000_000) }
        if value >= 1_000_000 { return String(format: "$%.1fM", value / 1_000_000) }
        return value.formatted(.currency(code: "USD"))
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
        }.navigationTitle(item.company)
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
                                Text(item.company).bold()
                                Spacer()
                                Text(item.weight.formatted(.number.precision(.fractionLength(2))) + "%")
                                    .foregroundStyle(.mint)
                            }
                            Text("Periodo \(snapshot.asOfQuarter)").font(.caption).foregroundStyle(.secondary)
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
            if snapshot.investors.count > 1 {
                Section("Consenso") {
                    ForEach(snapshot.consensus) { item in
                        VStack(alignment: .leading) {
                            HStack { Text(item.company).bold(); Spacer(); Text("\(item.holders) gestores") }
                            Text("\(item.buying) comprando · \(item.selling) reduciendo").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Section("Últimos movimientos") {
                ForEach(snapshot.movements) { item in
                    HStack {
                        Image(systemName: icon(item.action)).foregroundStyle(color(item.action))
                        VStack(alignment: .leading) {
                            Text(item.company)
                            Text("\(snapshot.asOfQuarter) · \(item.investorName) · \(item.action.label)")
                                .font(.caption).foregroundStyle(.secondary)
                        }
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
