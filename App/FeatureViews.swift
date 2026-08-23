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

struct UpdatesView: View {
    let snapshot: AppSnapshot
    @State private var filter = "all"

    private var updates: [FilingUpdate] {
        let recent = snapshot.filingUpdates.filter { $0.filingDate >= retentionCutoff }
        let filtered = filter == "all" ? recent : recent.filter { $0.investorId == filter }
        return filtered.sorted {
            if $0.filingDate != $1.filingDate {
                return $0.filingDate > $1.filingDate
            }
            return $0.investorName.localizedCaseInsensitiveCompare($1.investorName) == .orderedAscending
        }
    }

    private var sortedInvestors: [Investor] {
        snapshot.investors.sorted { $0.portfolioValue > $1.portfolioValue }
    }

    private var retentionCutoff: Date { Calendar.current.date(byAdding: .year, value: -3, to: Date()) ?? .distantPast }

    var body: some View {
        Group {
            if updates.isEmpty {
                ContentUnavailableView(
                    "Sin novedades 13F",
                    systemImage: "sparkles",
                    description: Text("Las nuevas publicaciones detectadas por el agente aparecerán aquí.")
                )
            } else {
                ScrollView {
                    LazyVStack(spacing: 12) {
                        updateFilter
                        ForEach(updates) { update in
                            UpdateCard(update: update)
                        }
                    }
                    .padding(16)
                }
                .background(WhaleTheme.background)
            }
        }
        .navigationTitle("Novedades 13F")
    }

    private var updateFilter: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                FilterChip(title: "Todos", selected: filter == "all") { filter = "all" }
                ForEach(sortedInvestors) { investor in
                    FilterChip(title: investor.name, selected: filter == investor.id) { filter = investor.id }
                }
            }
        }
    }
}

private struct FilterChip: View {
    let title: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title).font(.subheadline.weight(.semibold)).lineLimit(1)
                .foregroundStyle(selected ? .white : .primary)
                .padding(.horizontal, 13).padding(.vertical, 8)
                .background(selected ? WhaleTheme.accent : WhaleTheme.panel, in: Capsule())
                .overlay(Capsule().stroke(selected ? .clear : .primary.opacity(0.08)))
        }
        .buttonStyle(.plain)
    }
}

private struct UpdateCard: View {
    let update: FilingUpdate

    var body: some View {
        VStack(alignment: .leading, spacing: 13) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("NUEVO 13F").font(.system(size: 9, weight: .bold)).tracking(1).foregroundStyle(WhaleTheme.accent)
                    Text(update.investorName).font(.headline)
                }
                Spacer()
                Text(update.quarter).font(.caption.bold()).padding(.horizontal, 9).padding(.vertical, 5)
                    .background(WhaleTheme.navy.opacity(0.08), in: Capsule())
            }

            HStack(spacing: 14) {
                Label(update.filingDate.formatted(date: .abbreviated, time: .omitted), systemImage: "arrow.up.doc")
                Label(update.reportDate.formatted(date: .abbreviated, time: .omitted), systemImage: "calendar")
            }
            .font(.caption).foregroundStyle(.secondary)

            Text(update.summary).font(.subheadline).fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 6) {
                UpdateStat(value: update.newPositions, label: "Nuevas", color: WhaleTheme.positive)
                UpdateStat(value: update.increasedPositions, label: "Aumentadas", color: WhaleTheme.info)
                UpdateStat(value: update.reducedPositions, label: "Reducidas", color: WhaleTheme.warning)
                UpdateStat(value: update.soldPositions, label: "Vendidas", color: WhaleTheme.negative)
            }

            Link(destination: update.secURL) {
                Label("Ver presentación en la SEC", systemImage: "arrow.up.right.square")
                    .font(.caption.bold()).foregroundStyle(WhaleTheme.accent)
            }
        }
        .padding(15).whalePanel()
    }
}

private struct UpdateStat: View {
    let value: Int
    let label: String
    let color: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("\(value)").font(.subheadline.bold().monospacedDigit()).foregroundStyle(color)
            Text(label).font(.system(size: 8, weight: .medium)).foregroundStyle(.secondary).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(8)
        .background(color.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
    }
}

struct FilingsView: View {
    let snapshot: AppSnapshot
    @Binding var selectedInvestorID: String

    private var items: [FilingRecord] {
        let cutoff = Calendar.current.date(byAdding: .year, value: -3, to: Date()) ?? .distantPast
        return snapshot.filings.filter { $0.investorId == selectedInvestorID && $0.filingDate >= cutoff }
    }

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
                        VStack(alignment: .leading, spacing: 9) {
                            HStack {
                                Text(filing.form).font(.caption.bold()).foregroundStyle(WhaleTheme.accent)
                                Spacer()
                                Text(filing.quarter).font(.caption.bold()).foregroundStyle(.secondary)
                            }
                            Text(filing.investorName).font(.headline).foregroundStyle(.primary)
                            HStack {
                                Label("Reportado " + filing.reportDate.formatted(date: .abbreviated, time: .omitted), systemImage: "calendar")
                                Spacer()
                                Image(systemName: "arrow.up.right.square")
                            }
                            .font(.caption).foregroundStyle(.secondary)
                        }
                        .padding(14).whalePanel()
                    }
                    .listRowInsets(EdgeInsets(top: 5, leading: 16, bottom: 5, trailing: 16))
                    .listRowSeparator(.hidden).listRowBackground(Color.clear)
                }
                .listStyle(.plain)
                .background(WhaleTheme.background)
            }
        }
        .navigationTitle("Presentaciones 13F")
        .safeAreaInset(edge: .top) {
            FundSelector(investors: snapshot.investors, selection: $selectedInvestorID)
                .padding(.horizontal, 16).padding(.vertical, 8).background(.bar)
        }
    }
}

struct FundsView: View {
    let snapshot: AppSnapshot
    @Binding var selectedInvestorID: String

    private var sortedInvestors: [Investor] {
        snapshot.investors.sorted { $0.portfolioValue > $1.portfolioValue }
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(sortedInvestors) { investor in
                    Button {
                        withAnimation(.snappy) { selectedInvestorID = investor.id }
                    } label: {
                        FundCard(
                            investor: investor,
                            positions: snapshot.holdings.filter { $0.investorId == investor.id }.count,
                            selected: selectedInvestorID == investor.id
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(16)
        }
        .background(WhaleTheme.background)
        .navigationTitle("Fondos seguidos")
    }
}

private struct FundCard: View {
    let investor: Investor
    let positions: Int
    let selected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                Image(systemName: "building.columns.fill")
                    .font(.title3).foregroundStyle(.white)
                    .frame(width: 42, height: 42)
                    .background(WhaleTheme.navy, in: RoundedRectangle(cornerRadius: 11))
                VStack(alignment: .leading, spacing: 3) {
                    Text(investor.name).font(.headline).foregroundStyle(.primary)
                    Text("Responsable · " + (investor.manager ?? "No informado"))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if selected {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(WhaleTheme.accent)
                }
            }

            Divider()

            HStack(spacing: 0) {
                FundMetric(label: "VALOR DE LA CARTERA", value: compactMoney(investor.portfolioValue))
                Divider().frame(height: 34).padding(.horizontal, 18)
                FundMetric(label: "POSICIONES", value: "\(positions)")
                Spacer()
            }
        }
        .padding(16)
        .whalePanel()
        .overlay {
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(selected ? WhaleTheme.accent : .clear, lineWidth: 1.5)
        }
    }
}

private struct FundMetric: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.system(size: 8, weight: .bold)).foregroundStyle(.secondary)
            Text(value).font(.title3.bold().monospacedDigit()).foregroundStyle(.primary)
        }
    }
}

struct CompaniesView: View {
    let snapshot: AppSnapshot
    @Binding var selectedInvestorID: String
    @State private var yieldFilter: DividendYieldFilter = .all

    private var holdings: [Holding] {
        snapshot.holdings
            .filter { $0.investorId == selectedInvestorID && yieldFilter.matches(dividendYield(for: $0)) }
            .sorted { $0.value > $1.value }
    }

    var body: some View {
        List(holdings) { holding in
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
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Text(holding.company).font(.subheadline.weight(.semibold)).lineLimit(1)
                        if let yield = dividendYield(for: holding), yield > 4 {
                            HighYieldBadge(yield: yield)
                        }
                        Spacer()
                        Text(holding.weight.formatted(.number.precision(.fractionLength(2))) + "%")
                            .foregroundStyle(WhaleTheme.accent).bold().monospacedDigit()
                    }
                    HStack {
                        Text(compactMoney(holding.value))
                        Spacer()
                        if let yield = dividendYield(for: holding), yield > 0 {
                            Label("Yield " + percent(yield), systemImage: "dollarsign.circle.fill")
                                .foregroundStyle(yield > 4 ? WhaleTheme.positive : .secondary)
                        }
                        if let pe = peRatio(for: holding) {
                            Text("PER " + ratio(pe))
                        }
                    }.font(.caption).foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
            }
            .listRowBackground(WhaleTheme.panel)
        }
        .listStyle(.insetGrouped).scrollContentBackground(.hidden).background(WhaleTheme.background)
        .navigationTitle("Empresas")
        .safeAreaInset(edge: .top) {
            VStack(spacing: 8) {
                FundSelector(investors: snapshot.investors, selection: $selectedInvestorID)
                DividendYieldFilterPicker(selection: $yieldFilter)
            }
            .padding(.horizontal, 16).padding(.vertical, 8).background(.bar)
        }
    }

    private func profile(for holding: Holding) -> CompanyProfile? {
        snapshot.companyProfiles.first { $0.cusip == holding.cusip }
    }

    private func dividendYield(for holding: Holding) -> Double? {
        if let value = profile(for: holding)?.dividendYield { return value * 100 }
        return snapshot.opportunities.first { $0.ticker == holding.ticker }?.yield
    }

    private func peRatio(for holding: Holding) -> Double? {
        profile(for: holding)?.peRatio
            ?? snapshot.opportunities.first { $0.ticker == holding.ticker }?.pe
    }

    private func percent(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(1))) + "%"
    }

    private func ratio(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(1))) + "x"
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
                LabeledContent(
                    "Precio medio estimado",
                    value: item.estimatedAveragePurchasePrice?.formatted(.currency(code: "USD")) ?? "—"
                )
                LabeledContent("Peso", value: item.weight.formatted(.number.precision(.fractionLength(2))) + "%")
            }
            Section {
                Text("Estimación construida con los cambios trimestrales de acciones y el valor declarado al cierre. El 13F no informa del precio real de compra.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
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
                }
                Section("Dividendos") {
                    if let paysDividend = profile.paysDividend {
                        Label(paysDividend ? "Reparte dividendos" : "No reparte dividendos",
                              systemImage: paysDividend ? "dollarsign.circle.fill" : "minus.circle")
                            .foregroundStyle(paysDividend ? WhaleTheme.positive : .secondary)
                    }
                    if let yield = profile.dividendYield, yield > 0 {
                        LabeledContent("Yield", value: yield.formatted(.percent.precision(.fractionLength(2))))
                        if yield > 0.04 { HighYieldBadge(yield: yield * 100) }
                    }
                    if let dividend = profile.dividendPerShare {
                        LabeledContent("Dividendo por acción", value: dividend.formatted(.currency(code: profile.currency ?? "USD")))
                    }
                }
                if let pe = profile.peRatio {
                    Section("Valoración") {
                        LabeledContent("PER", value: pe.formatted(.number.precision(.fractionLength(1))) + "x")
                    }
                }
                if profile.latestQuarterlyReportURL != nil || profile.latestAnnualReportURL != nil {
                    Section("Informes oficiales") {
                        if let url = profile.latestQuarterlyReportURL {
                            Link("Último informe trimestral" + reportDate(profile.latestQuarterlyReportDate), destination: url)
                        }
                        if let url = profile.latestAnnualReportURL {
                            Link("Último informe anual" + reportDate(profile.latestAnnualReportDate), destination: url)
                        }
                    }
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

    private func reportDate(_ value: String?) -> String {
        value.map { " · " + $0 } ?? ""
    }
}

private struct CompanyDetailView: View {
    let item: Opportunity
    var body: some View {
        List {
            Section("Dividendos") {
                Label(item.yield > 0 ? "Reparte dividendos" : "No reparte dividendos",
                      systemImage: item.yield > 0 ? "dollarsign.circle.fill" : "minus.circle")
                    .foregroundStyle(item.yield > 0 ? WhaleTheme.positive : .secondary)
                LabeledContent("Yield", value: item.yield.formatted(.number.precision(.fractionLength(2))) + "%")
                if item.yield > 4 { HighYieldBadge(yield: item.yield) }
                LabeledContent("Payout", value: item.payout.map { $0.formatted() + "%" } ?? "—")
                LabeledContent("Crecimiento dividendo 5A", value: item.dividendGrowth5Y.map { $0.formatted() + "%" } ?? "—")
            }
            Section("Valoración") {
                LabeledContent("PER", value: item.pe.map { $0.formatted(.number.precision(.fractionLength(1))) + "x" } ?? "—")
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

private struct HighYieldBadge: View {
    let yield: Double

    var body: some View {
        Label("Yield " + yield.formatted(.number.precision(.fractionLength(1))) + "%", systemImage: "leaf.fill")
            .font(.caption2.bold())
            .foregroundStyle(WhaleTheme.positive)
            .padding(.horizontal, 7)
            .padding(.vertical, 4)
            .background(WhaleTheme.positive.opacity(0.12), in: Capsule())
            .accessibilityLabel("Rentabilidad por dividendo superior al cuatro por ciento")
    }
}

struct SmartMoneyView: View {
    let snapshot: AppSnapshot
    @Binding var selectedInvestorID: String

    var body: some View {
        ConsensusRankingView(items: snapshot.consensus, profiles: snapshot.companyProfiles)
    }
}

private struct ConsensusRankingView: View {
    enum Ranking: String, CaseIterable, Identifiable {
        case opportunity = "Oportunidad"
        case holders = "Más compartidas"
        case buying = "Más compradas"
        var id: Self { self }
    }

    let items: [ConsensusItem]
    let profiles: [CompanyProfile]
    @State private var ranking: Ranking = .opportunity
    @State private var search = ""
    @State private var yieldFilter: DividendYieldFilter = .all

    private var rankedItems: [ConsensusItem] {
        let searched = search.isEmpty ? items : items.filter { $0.company.localizedCaseInsensitiveContains(search) }
        let filtered = searched.filter { yieldFilter.matches($0.yield) }
        return filtered.sorted { lhs, rhs in
            switch ranking {
            case .opportunity: (lhs.opportunityScore ?? 0, lhs.buying, lhs.holders) > (rhs.opportunityScore ?? 0, rhs.buying, rhs.holders)
            case .holders: (lhs.holders, lhs.buying) > (rhs.holders, rhs.buying)
            case .buying: (lhs.buying, lhs.holders) > (rhs.buying, rhs.holders)
            }
        }
    }

    private var targetYieldCount: Int {
        items.filter { ($0.yield ?? -1) >= 3 && ($0.yield ?? 10) <= 9 }.count
    }

    var body: some View {
        List {
            Section {
                HStack(spacing: 0) {
                    rankingMetric(value: "\(items.count)", label: "ANALIZADAS", icon: "chart.bar.doc.horizontal")
                    Divider().frame(height: 38).padding(.horizontal, 14)
                    rankingMetric(value: "\(targetYieldCount)", label: "YIELD 3–9 %", icon: "leaf.fill")
                    Divider().frame(height: 38).padding(.horizontal, 14)
                    rankingMetric(value: "\(rankedItems.count)", label: "RESULTADOS", icon: "line.3.horizontal.decrease")
                }
                .padding(14)
                .background(WhaleTheme.navy, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
            Section {
                Picker("Clasificación", selection: $ranking) {
                    ForEach(Ranking.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
                Picker("Filtro de dividendos", selection: $yieldFilter) {
                    ForEach(DividendYieldFilter.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.menu)
            }
            Section {
                if rankedItems.isEmpty {
                    ContentUnavailableView(
                        "Sin coincidencias",
                        systemImage: "line.3.horizontal.decrease.circle",
                        description: Text("Prueba otro rango de yield o elimina el texto de búsqueda.")
                    )
                    .listRowBackground(Color.clear)
                }
                ForEach(Array(rankedItems.enumerated()), id: \.element.id) { index, item in
                    NavigationLink {
                        OpportunityAnalysisView(item: item, profile: profile(for: item))
                    } label: {
                        HStack(spacing: 12) {
                            ZStack {
                                Circle().fill(index < 3 ? WhaleTheme.accent.opacity(0.14) : Color.primary.opacity(0.05))
                                Text("\(index + 1)")
                                    .font(.caption.bold().monospacedDigit())
                                    .foregroundStyle(index < 3 ? WhaleTheme.accent : .secondary)
                            }
                            .frame(width: 32, height: 32)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(item.company).font(.subheadline.weight(.semibold)).lineLimit(2)
                                HStack(spacing: 10) {
                                    Label("\(item.holders) fondos", systemImage: "building.columns")
                                    Label("+\(item.buying)", systemImage: "arrow.up.circle.fill").foregroundStyle(WhaleTheme.positive)
                                    Label("−\(item.selling)", systemImage: "arrow.down.circle.fill").foregroundStyle(WhaleTheme.negative)
                                }
                                .font(.caption)
                                HStack(spacing: 8) {
                                    if let yield = item.yield {
                                        Text("Yield " + yield.formatted(.number.precision(.fractionLength(1))) + "%")
                                            .foregroundStyle(yield > 4 ? WhaleTheme.positive : .secondary)
                                    }
                                    if let pe = item.pe {
                                        Text("PER " + pe.formatted(.number.precision(.fractionLength(1))) + "x")
                                    }
                                }
                                .font(.caption.bold().monospacedDigit())
                            }
                            Spacer()
                            VStack(spacing: 2) {
                                Text("\(item.opportunityScore ?? 0)")
                                    .font(.title3.bold().monospacedDigit()).foregroundStyle(.white)
                                Text("SCORE").font(.system(size: 7, weight: .bold)).foregroundStyle(.white.opacity(0.72))
                            }
                            .frame(width: 48, height: 48)
                            .background(scoreColor(item.opportunityScore ?? 0), in: RoundedRectangle(cornerRadius: 12))
                        }
                    }
                    .padding(.vertical, 6)
                    .listRowBackground(WhaleTheme.panel)
                }
            } header: {
                Text("Ranking de oportunidades para dividendos")
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(WhaleTheme.background)
        .navigationTitle("Smart Money")
        .searchable(text: $search, prompt: "Buscar empresa")
    }

    private func profile(for item: ConsensusItem) -> CompanyProfile? {
        guard let cusip = item.cusip else { return nil }
        return profiles.first { $0.cusip == cusip }
    }

    private func rankingMetric(value: String, label: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(value, systemImage: icon)
                .font(.headline.bold().monospacedDigit())
                .foregroundStyle(.white)
            Text(label).font(.system(size: 7, weight: .bold)).foregroundStyle(.white.opacity(0.62))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func scoreColor(_ score: Int) -> Color {
        if score >= 75 { return WhaleTheme.positive }
        if score >= 55 { return WhaleTheme.accent }
        return WhaleTheme.warning
    }
}

private struct OpportunityAnalysisView: View {
    let item: ConsensusItem
    let profile: CompanyProfile?

    private var reasons: [String] {
        var result: [String] = []
        let net = item.buying - item.selling
        if item.holders >= 5 { result.append("Existe consenso: la mantienen \(item.holders) de los fondos seguidos.") }
        if net > 0 { result.append("La tendencia institucional es positiva, con \(net) compradores netos en el trimestre.") }
        if let yield = item.yield {
            if yield > 12 { result.append("El yield supera ampliamente el 9 % objetivo y recibe una penalización fuerte por posible riesgo de recorte.") }
            else if yield > 9 { result.append("El yield está por encima del rango objetivo del 3–9 % y se penaliza hasta confirmar su sostenibilidad.") }
            else if yield >= 3 { result.append("El yield del \(yield.formatted(.number.precision(.fractionLength(1)))) % está dentro del rango objetivo del 3–9 %.") }
            else if yield > 0 { result.append("El dividendo es inferior al 3 %; puede ser interesante si crece, pero aporta menos renta inicial.") }
            else { result.append("No reparte dividendo y, por tanto, obtiene cero puntos en el componente principal del score.") }
        }
        if let pe = item.pe, let benchmark = item.sectorPEBenchmark {
            let ratio = pe / benchmark
            if ratio <= 0.85 { result.append("El PER de \(pe.formatted(.number.precision(.fractionLength(1))))x cotiza por debajo de la referencia sectorial ajustada de \(benchmark.formatted(.number.precision(.fractionLength(1))))x.") }
            else if ratio <= 1.10 { result.append("El PER está cerca de la referencia razonable para su sector.") }
            else { result.append("El PER supera la referencia ajustada de su sector y reduce el atractivo de valoración.") }
            if item.brandPremiumApplied == true { result.append("La referencia admite una prima moderada porque la empresa posee una marca o ecosistema especialmente fuerte.") }
        } else if item.pe == nil {
            result.append("No hay PER disponible; la valoración requiere comprobación adicional.")
        }
        return result
    }

    var body: some View {
        List {
            Section {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Score para dividendos a largo plazo").font(.caption).foregroundStyle(.secondary)
                        Text("\(item.opportunityScore ?? 0) / 100").font(.largeTitle.bold().monospacedDigit())
                    }
                    Spacer()
                    Image(systemName: "chart.line.uptrend.xyaxis.circle.fill")
                        .font(.system(size: 42)).foregroundStyle(WhaleTheme.accent)
                }
            }
            Section("Por qué puede ser una oportunidad") {
                ForEach(reasons, id: \.self) { reason in
                    Label(reason, systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.primary)
                }
                Text("El score es una señal cuantitativa, no una recomendación de inversión.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Indicadores") {
                LabeledContent("Fondos con posición", value: "\(item.holders)")
                LabeledContent("Comprando", value: "\(item.buying)")
                LabeledContent("Reduciendo", value: "\(item.selling)")
                LabeledContent("Yield", value: item.yield.map { $0.formatted(.number.precision(.fractionLength(2))) + "%" } ?? "—")
                LabeledContent("PER", value: item.pe.map { $0.formatted(.number.precision(.fractionLength(1))) + "x" } ?? "—")
                if let sector = item.sector { LabeledContent("Sector", value: sector) }
                if let benchmark = item.sectorPEBenchmark {
                    LabeledContent("PER de referencia", value: benchmark.formatted(.number.precision(.fractionLength(1))) + "x")
                }
                if item.brandPremiumApplied == true {
                    Label("Referencia ajustada por poder de marca", systemImage: "star.circle.fill")
                        .foregroundStyle(WhaleTheme.accent)
                }
            }
            Section("Desglose del score") {
                ScoreComponentRow(label: "Dividendo", value: item.dividendInvestorScore ?? 0, maximum: 55, icon: "dollarsign.circle.fill")
                ScoreComponentRow(label: "Valoración", value: item.valuationInvestorScore ?? 0, maximum: 25, icon: "scalemass.fill")
                ScoreComponentRow(label: "Consenso", value: item.consensusInvestorScore ?? 0, maximum: 20, icon: "building.columns.fill")
            }
            if let profile {
                if let description = profile.description { Section("A qué se dedica") { Text(description) } }
                if let business = profile.businessModel { Section("Modelo de negocio") { Text(business) } }
                if let revenue = profile.revenueModel { Section("Cómo gana dinero") { Text(revenue) } }
                if let moat = profile.economicMoat { Section("Foso defensivo") { Text(moat) } }
                if profile.latestQuarterlyReportURL != nil || profile.latestAnnualReportURL != nil {
                    Section("Informes oficiales") {
                        if let url = profile.latestQuarterlyReportURL {
                            Link(destination: url) {
                                Label("Último informe trimestral" + reportDate(profile.latestQuarterlyReportDate), systemImage: "doc.text.fill")
                            }
                        }
                        if let url = profile.latestAnnualReportURL {
                            Link(destination: url) {
                                Label("Último informe anual" + reportDate(profile.latestAnnualReportDate), systemImage: "books.vertical.fill")
                            }
                        }
                    }
                }
                Section { Text("Datos empresariales almacenados en GitHub · Fuente de métricas: \(profile.source)").font(.caption).foregroundStyle(.secondary) }
            } else {
                Section("Empresa") {
                    Text("El perfil cualitativo todavía está pendiente de incorporación a GitHub.")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle(item.company)
        .navigationBarTitleDisplayMode(.inline)
    }

    private func reportDate(_ value: String?) -> String {
        value.map { " · " + $0 } ?? ""
    }
}

private struct ScoreComponentRow: View {
    let label: String
    let value: Int
    let maximum: Int
    let icon: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon).foregroundStyle(WhaleTheme.accent).frame(width: 22)
            VStack(alignment: .leading, spacing: 5) {
                HStack {
                    Text(label)
                    Spacer()
                    Text("\(value) / \(maximum)").bold().monospacedDigit()
                }
                ProgressView(value: Double(value), total: Double(maximum)).tint(WhaleTheme.accent)
            }
        }
    }
}

struct PortfolioPlaceholderView: View {
    var body: some View {
        ContentUnavailableView("Tu cartera", systemImage: "briefcase", description: Text("La persistencia personal con SwiftData llegará en la siguiente iteración."))
            .navigationTitle("Cartera")
    }
}
