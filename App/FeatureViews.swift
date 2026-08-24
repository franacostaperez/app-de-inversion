import SwiftUI
import Charts
#if canImport(DividendIntelligenceKit)
import DividendIntelligenceKit
#endif

private extension CompanyReport {
    var isAnnualReport: Bool {
        let normalized = form.uppercased()
        return normalized.hasPrefix("10-K") || normalized.hasPrefix("20-F") || normalized.hasPrefix("40-F")
    }
    var isQuarterlyReport: Bool { form.uppercased().hasPrefix("10-Q") }
}

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
    @State private var period: NewsPeriod = .week

    private var filings: [FilingUpdate] {
        let recent = snapshot.filingUpdates.filter { $0.filingDate >= retentionCutoff }
        if filter == "companies" { return [] }
        return filter == "all" || filter == "13f" ? recent : recent.filter { $0.investorId == filter }
    }

    private var companyReports: [CompanyReport] {
        guard filter == "all" || filter == "companies" else { return [] }
        return snapshot.companyReports.filter { $0.filingDate >= retentionCutoff && $0.isAnnualReport }
    }

    private var news: [NewsEntry] {
        (filings.map(NewsEntry.filing) + companyReports.map(NewsEntry.companyReport))
            .filter { $0.date >= period.cutoff }
            .sorted { $0.date > $1.date }
    }

    private var sections: [NewsSection] {
        Dictionary(grouping: news) { Calendar.current.startOfDay(for: $0.date) }
            .map { NewsSection(date: $0.key, entries: $0.value.sorted { $0.date > $1.date }) }
            .sorted { $0.date > $1.date }
    }

    private var sortedInvestors: [Investor] {
        snapshot.investors.sorted { $0.portfolioValue > $1.portfolioValue }
    }

    private var retentionCutoff: Date { Calendar.current.date(byAdding: .year, value: -3, to: Date()) ?? .distantPast }

    private var nextPlannedUpdate: Date {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(secondsFromGMT: 0)!
        let now = Date()
        let today = utc.startOfDay(for: now)
        let scheduled = utc.date(bySettingHour: 7, minute: 17, second: 0, of: today)!
        return scheduled > now ? scheduled : utc.date(byAdding: .day, value: 1, to: scheduled)!
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                updateOverview
                Picker("Periodo", selection: $period) {
                    ForEach(NewsPeriod.allCases) { option in Text(option.title).tag(option) }
                }
                .pickerStyle(.segmented)
                updateFilter

                if news.isEmpty {
                    ContentUnavailableView(
                        "Sin novedades en este periodo",
                        systemImage: "calendar.badge.checkmark",
                        description: Text("Prueba otro intervalo o fuente. La revisión automática sigue activa.")
                    )
                    .frame(maxWidth: .infinity).padding(.top, 28)
                } else {
                    ForEach(sections) { section in
                        Section {
                            ForEach(section.entries) { item in
                            switch item {
                            case .filing(let update): UpdateCard(update: update)
                            case .companyReport(let report):
                                CompanyReportUpdateCard(
                                    report: report,
                                    profile: snapshot.companyProfiles.first { $0.cusip == report.cusip },
                                    reports: snapshot.companyReports.filter { $0.cusip == report.cusip && $0.isAnnualReport },
                                    holdings: snapshot.holdings.filter { $0.cusip == report.cusip }
                                )
                            }
                            }
                        } header: {
                            Text(section.title)
                                .font(.caption.bold()).foregroundStyle(.secondary)
                                .textCase(.uppercase).tracking(0.7)
                        }
                    }
                }
            }
            .padding(16)
        }
        .background(WhaleTheme.background)
        .navigationTitle("Novedades")
    }

    private var updateOverview: some View {
        VStack(alignment: .leading, spacing: 13) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("CENTRO DE ACTUALIZACIONES").font(.system(size: 9, weight: .bold)).tracking(0.9)
                        .foregroundStyle(WhaleTheme.accent)
                    Text("\(news.count) novedades · \(period.title.lowercased())")
                        .font(.title3.bold())
                }
                Spacer()
                Image(systemName: "arrow.triangle.2.circlepath.circle.fill")
                    .font(.title2).foregroundStyle(WhaleTheme.accent)
            }
            Divider()
            HStack(spacing: 10) {
                scheduleMetric("Última carga", snapshot.generatedAt.formatted(date: .abbreviated, time: .shortened), "checkmark.circle.fill")
                scheduleMetric("Siguiente", nextPlannedUpdate.formatted(date: .abbreviated, time: .shortened), "clock.badge")
            }
            Text("Revisión automática diaria a las 07:17 UTC")
                .font(.caption2).foregroundStyle(.secondary)
        }
        .padding(15).whalePanel()
    }

    private func scheduleMetric(_ label: String, _ value: String, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Label(label.uppercased(), systemImage: icon).font(.system(size: 8, weight: .bold)).foregroundStyle(.secondary)
            Text(value).font(.caption.bold().monospacedDigit()).lineLimit(1).minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var updateFilter: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                FilterChip(title: "Todos", selected: filter == "all") { filter = "all" }
                FilterChip(title: "Empresas", selected: filter == "companies") { filter = "companies" }
                FilterChip(title: "13F", selected: filter == "13f") { filter = "13f" }
                ForEach(sortedInvestors) { investor in
                    FilterChip(title: investor.name, selected: filter == investor.id) { filter = investor.id }
                }
            }
        }
    }
}

private enum NewsPeriod: String, CaseIterable, Identifiable {
    case day, week, all
    var id: String { rawValue }
    var title: String {
        switch self { case .day: "Último día"; case .week: "Última semana"; case .all: "Todo" }
    }
    var cutoff: Date {
        switch self {
        case .day: Calendar.current.date(byAdding: .day, value: -1, to: Date()) ?? .distantPast
        case .week: Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? .distantPast
        case .all: .distantPast
        }
    }
}

private struct NewsSection: Identifiable {
    let date: Date
    let entries: [NewsEntry]
    var id: Date { date }
    var title: String {
        if Calendar.current.isDateInToday(date) { return "Hoy" }
        if Calendar.current.isDateInYesterday(date) { return "Ayer" }
        return date.formatted(date: .long, time: .omitted)
    }
}

private enum NewsEntry: Identifiable {
    case filing(FilingUpdate)
    case companyReport(CompanyReport)

    var id: String {
        switch self {
        case .filing(let item): "13f-" + item.id
        case .companyReport(let item): "company-" + item.id
        }
    }

    var date: Date {
        switch self {
        case .filing(let item): item.filingDate
        case .companyReport(let item): item.filingDate
        }
    }
}

private struct CompanyReportUpdateCard: View {
    let report: CompanyReport
    let profile: CompanyProfile?
    let reports: [CompanyReport]
    let holdings: [Holding]

    var body: some View {
        NavigationLink {
            CompanyFinancialOverviewView(companyName: report.companyName, profile: profile, reports: reports, holdings: holdings)
        } label: {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("NUEVO INFORME DE EMPRESA")
                            .font(.system(size: 9, weight: .bold)).tracking(0.8).foregroundStyle(WhaleTheme.info)
                        Text(report.companyName).font(.headline).foregroundStyle(.primary)
                    }
                    Spacer()
                    Text(report.form).font(.caption.bold()).padding(.horizontal, 9).padding(.vertical, 5)
                        .background(WhaleTheme.info.opacity(0.11), in: Capsule())
                }
                HStack(spacing: 14) {
                    Label(report.filingDate.formatted(date: .abbreviated, time: .omitted), systemImage: "arrow.up.doc")
                    Label("Periodo " + report.reportDate.formatted(date: .abbreviated, time: .omitted), systemImage: "calendar")
                }
                .font(.caption).foregroundStyle(.secondary)
                Text(report.highlights).font(.subheadline).foregroundStyle(.primary).lineLimit(4)
                HStack(spacing: 8) {
                    reportMetric("Ingresos", report.summary.revenue)
                    reportMetric("Beneficio", report.summary.netIncome)
                    if let margin = report.summary.netMargin {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(margin.formatted(.number.precision(.fractionLength(1))) + "%").font(.caption.bold())
                            Text("MARGEN").font(.system(size: 7, weight: .bold)).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                Label("Ver análisis y evolución", systemImage: "chart.xyaxis.line")
                    .font(.caption.bold()).foregroundStyle(WhaleTheme.accent)
            }
            .padding(15).whalePanel()
        }
        .buttonStyle(.plain)
    }

    private func reportMetric(_ label: String, _ value: Double?) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value.map(compactMoney) ?? "—").font(.caption.bold().monospacedDigit())
            Text(label.uppercased()).font(.system(size: 7, weight: .bold)).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading)
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
                CompanyFinancialOverviewView(
                    companyName: holding.company,
                    profile: snapshot.companyProfiles.first(where: { $0.cusip == holding.cusip }),
                    reports: snapshot.companyReports.filter { $0.cusip == holding.cusip },
                    holdings: snapshot.holdings.filter { $0.cusip == holding.cusip }
                )
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
                if profile.latestAnnualReportURL != nil {
                    Section("Informes oficiales") {
                        if let url = profile.latestAnnualReportURL {
                            Link("Último informe anual" + reportDate(profile.latestAnnualReportDate), destination: url)
                        }
                    }
                }
                if let url = profile.investorRelationsURL {
                    Section("Accionistas") {
                        Link(profile.investorRelationsVerified == true ? "Página oficial de inversores" : "Buscar relaciones con inversores", destination: url)
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
        ConsensusRankingView(items: snapshot.consensus, profiles: snapshot.companyProfiles, reports: snapshot.companyReports)
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
    let reports: [CompanyReport]
    @State private var ranking: Ranking = .opportunity
    @State private var search = ""
    @State private var yieldFilter: DividendYieldFilter = .all

    private var rankedItems: [ConsensusItem] {
        let searched = search.isEmpty ? items : items.filter { $0.company.localizedCaseInsensitiveContains(search) }
        let filtered = searched.filter { yieldFilter.matches($0.yield) }
        return filtered.sorted { lhs, rhs in
            switch ranking {
            case .opportunity: (lhs.opportunityScore ?? 0, lhs.newPositions ?? 0, lhs.buying, lhs.holders) > (rhs.opportunityScore ?? 0, rhs.newPositions ?? 0, rhs.buying, rhs.holders)
            case .holders: (lhs.holders, lhs.newPositions ?? 0, lhs.buying) > (rhs.holders, rhs.newPositions ?? 0, rhs.buying)
            case .buying: (lhs.newPositions ?? 0, lhs.buying, lhs.holders) > (rhs.newPositions ?? 0, rhs.buying, rhs.holders)
            }
        }
    }

    private var targetYieldCount: Int {
        items.filter { ($0.yield ?? -1) >= 3 && ($0.yield ?? 10) <= 9 }.count
    }

    private var scoredCount: Int { items.filter { $0.opportunityScore != nil }.count }
    private var pendingCount: Int { items.count - scoredCount }

    var body: some View {
        List {
            Section {
                HStack(spacing: 0) {
                    rankingMetric(value: "\(items.count)", label: "EMPRESAS", icon: "building.2")
                    Divider().frame(height: 38).padding(.horizontal, 14)
                    rankingMetric(value: "\(scoredCount)", label: "CON SCORE", icon: "checkmark.seal")
                    Divider().frame(height: 38).padding(.horizontal, 14)
                    rankingMetric(value: "\(pendingCount)", label: "COMPLETANDO", icon: "arrow.triangle.2.circlepath")
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
                        OpportunityAnalysisView(
                            item: item,
                            profile: profile(for: item),
                            reports: reports.filter { $0.cusip == item.cusip }
                        )
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
                                HStack(spacing: 7) {
                                    Text(displayCompanyName(item.company)).font(.subheadline.weight(.semibold)).lineLimit(2)
                                    if ranking == .opportunity {
                                        OpportunityRankMovementBadge(item: item)
                                    }
                                }
                                HStack(spacing: 10) {
                                    Label("\(item.holders) fondos", systemImage: "building.columns")
                                    Label("+\(item.buying)", systemImage: "arrow.up.circle.fill").foregroundStyle(WhaleTheme.positive)
                                    if let newPositions = item.newPositions, newPositions > 0 {
                                        Label("\(newPositions) nuevas", systemImage: "sparkles").foregroundStyle(WhaleTheme.accent)
                                    }
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
                                if item.opportunityScore == nil {
                                    Text("Faltan " + scoreMetricNames(item.missingScoreMetrics).joined(separator: ", "))
                                        .font(.caption2).foregroundStyle(WhaleTheme.warning).lineLimit(1)
                                }
                            }
                            Spacer()
                            VStack(spacing: 2) {
                                Text(item.opportunityScore.map(String.init) ?? "—")
                                    .font(.title3.bold().monospacedDigit()).foregroundStyle(.white)
                                Text(item.opportunityScore == nil ? "DATOS" : "SCORE").font(.system(size: 7, weight: .bold)).foregroundStyle(.white.opacity(0.72))
                            }
                            .frame(width: 48, height: 48)
                            .background(item.opportunityScore.map(scoreColor) ?? WhaleTheme.warning, in: RoundedRectangle(cornerRadius: 12))
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

struct OpportunityAnalysisView: View {
    let item: ConsensusItem
    let profile: CompanyProfile?
    let reports: [CompanyReport]

    private var annualReports: [CompanyReport] { reports.filter(\.isAnnualReport) }
    private var missingMetricLabels: [String] { scoreMetricNames(item.missingScoreMetrics) }

    private var reasons: [String] {
        var result: [String] = []
        let net = item.buying - item.selling
        if item.holders >= 5 { result.append("Existe consenso: la mantienen \(item.holders) de los fondos seguidos.") }
        if let newPositions = item.newPositions, newPositions > 0 {
            result.append("\(newPositions) fondos la han incorporado como nueva posición en su último 13F.")
        }
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
        } else if item.peNotMeaningful == true {
            result.append("El beneficio por acción no es positivo, por lo que el PER no es significativo y la valoración obtiene cero puntos.")
        } else if item.pe == nil {
            result.append("No hay PER verificable; el score no se publica hasta completar la valoración.")
        }
        if let relativePrice = item.priceVsMovingAverage1000Percent {
            if relativePrice < 0 {
                result.append("La cotización está un \(abs(relativePrice).formatted(.number.precision(.fractionLength(1)))) % por debajo de su media de 1.000 sesiones y mejora el score.")
            } else if relativePrice == 0 {
                result.append("La cotización está prácticamente en su media de 1.000 sesiones.")
            } else {
                result.append("La cotización está un \(relativePrice.formatted(.number.precision(.fractionLength(1)))) % por encima de su media de 1.000 sesiones y recibe menos puntos.")
            }
        } else {
            result.append("No existe todavía una media verificable de 1.000 sesiones; el score queda pendiente.")
        }
        if let margin = item.operatingMargin {
            if margin <= 0 { result.append("El margen operativo no es positivo y no aporta puntos de rentabilidad.") }
            else if margin < 5 { result.append("El margen operativo del \(margin.formatted(.number.precision(.fractionLength(1)))) % es reducido y ofrece poco colchón ante una caída de ingresos.") }
            else if margin < 15 { result.append("El margen operativo es moderado y aporta una puntuación intermedia de rentabilidad.") }
            else { result.append("El margen operativo del \(margin.formatted(.number.precision(.fractionLength(1)))) % refleja una rentabilidad elevada y refuerza el score.") }
        } else {
            result.append("No hay margen operativo anual comparable; el score queda pendiente hasta obtenerlo.")
        }
        if item.leverageStatus == "NOT_COMPARABLE_FINANCIAL" {
            result.append("En una entidad financiera la deuda forma parte de la actividad y no es comparable con la de una empresa industrial; recibe una puntuación neutral.")
        } else if item.leverageStatus == "LOSS_MAKING_WITH_DEBT" {
            result.append("La empresa tiene deuda y pérdidas en el último ejercicio; el componente de solvencia recibe cero puntos.")
        } else if let ratio = item.debtToEarnings {
            let basis = item.debtRatioBasis == "NET_DEBT_TO_NET_INCOME" ? "deuda neta" : "deuda total"
            if ratio <= 1 { result.append("La \(basis) equivale a \(ratio.formatted(.number.precision(.fractionLength(1)))) años de beneficio, una posición financiera sólida.") }
            else if ratio <= 3 { result.append("La \(basis) equivale a \(ratio.formatted(.number.precision(.fractionLength(1)))) veces el beneficio anual, un nivel manejable.") }
            else if ratio <= 5 { result.append("La \(basis) equivale a \(ratio.formatted(.number.precision(.fractionLength(1)))) veces el beneficio anual y penaliza el score por apalancamiento elevado.") }
            else { result.append("La \(basis) supera cinco veces el beneficio anual y recibe una penalización severa.") }
        } else {
            result.append("Falta deuda o beneficio anual comparable; el score queda pendiente hasta completar la solvencia.")
        }
        if let growth = item.dividendGrowth {
            if growth < 0 { result.append("El dividendo por acción ha disminuido y no obtiene puntos por crecimiento.") }
            else if growth < 3 { result.append("El dividendo por acción crece a un ritmo anualizado moderado del \(growth.formatted(.number.precision(.fractionLength(1)))) %.") }
            else { result.append("El dividendo por acción crece aproximadamente un \(growth.formatted(.number.precision(.fractionLength(1)))) % anualizado y mejora el score.") }
        }
        return result
    }

    var body: some View {
        List {
            if let profile {
                Section {
                    BusinessSummaryPanel(profile: profile)
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                }
                if profile.marketPrice != nil || profile.movingAverage1000 != nil {
                    Section {
                        PriceVsMovingAverageChart(profile: profile)
                            .listRowInsets(EdgeInsets())
                            .listRowBackground(Color.clear)
                    }
                }
            }
            Section {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Score para dividendos a largo plazo").font(.caption).foregroundStyle(.secondary)
                        if let score = item.opportunityScore {
                            Text("\(score) / 100").font(.largeTitle.bold().monospacedDigit())
                        } else {
                            Text("Pendiente de datos").font(.title2.bold())
                            Text("Cobertura \(item.scoreCoverage ?? 0)% · falta " + missingMetricLabels.joined(separator: ", "))
                                .font(.caption).foregroundStyle(WhaleTheme.warning)
                        }
                    }
                    Spacer()
                    Image(systemName: "chart.line.uptrend.xyaxis.circle.fill")
                        .font(.system(size: 42)).foregroundStyle(WhaleTheme.accent)
                }
            }
            if !annualReports.isEmpty {
                Section("Serie financiera anual") {
                    CompanyFinancialSeriesDashboard(reports: annualReports)
                        .listRowInsets(EdgeInsets())
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
                if let rank = item.opportunityRank {
                    LabeledContent("Puesto en el ranking") {
                        HStack(spacing: 8) {
                            Text("#\(rank)").monospacedDigit()
                            OpportunityRankMovementBadge(item: item)
                        }
                    }
                }
                LabeledContent("Fondos con posición", value: "\(item.holders)")
                LabeledContent("Comprando", value: "\(item.buying)")
                LabeledContent("Nuevas posiciones", value: "\(item.newPositions ?? 0)")
                LabeledContent("Reduciendo", value: "\(item.selling)")
                LabeledContent("Yield", value: item.yield.map { $0.formatted(.number.precision(.fractionLength(2))) + "%" } ?? "—")
                LabeledContent("PER", value: item.pe.map { $0.formatted(.number.precision(.fractionLength(1))) + "x" } ?? "—")
                LabeledContent("BPA diluido anual", value: item.earningsPerShare.map { $0.formatted(.currency(code: "USD")) } ?? "—")
                if item.peCalculation == "PRICE_OVER_ANNUAL_DILUTED_EPS" {
                    Text("PER calculado con cotización diaria ÷ BPA diluido del último ejercicio.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                LabeledContent("Precio", value: item.marketPrice.map { $0.formatted(.currency(code: "USD")) } ?? "—")
                LabeledContent("Media 1.000 sesiones", value: item.movingAverage1000.map { $0.formatted(.currency(code: "USD")) } ?? "—")
                LabeledContent("Precio vs media", value: item.priceVsMovingAverage1000Percent.map(relativePriceLabel) ?? "—")
                LabeledContent("Margen operativo", value: item.operatingMargin.map { $0.formatted(.number.precision(.fractionLength(1))) + "%" } ?? "—")
                if let rating = item.operatingMarginRating {
                    LabeledContent("Nivel del margen", value: "\(rating) / 10")
                }
                LabeledContent("Crecimiento del dividendo", value: item.dividendGrowth.map { $0.formatted(.number.precision(.fractionLength(1))) + "% anual" } ?? "—")
                LabeledContent("Deuda total", value: item.totalDebt.map(compactMoney) ?? "—")
                LabeledContent("Efectivo", value: item.cash.map(compactMoney) ?? "—")
                LabeledContent("Deuda neta", value: item.netDebt.map(compactMoney) ?? "—")
                LabeledContent("Beneficio neto anual", value: item.netIncome.map(compactMoney) ?? "—")
                LabeledContent("Deuda / beneficio", value: item.debtToEarnings.map { $0.formatted(.number.precision(.fractionLength(2))) + "x" } ?? (item.leverageStatus == "NOT_COMPARABLE_FINANCIAL" ? "No comparable" : "—"))
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
                Text("Cada fila muestra los puntos obtenidos y su peso máximo sobre el total de 100.")
                    .font(.footnote).foregroundStyle(.secondary)
                ScoreComponentRow(label: "Valoración", value: item.valuationInvestorScore ?? 0, maximum: 35, icon: "scalemass.fill")
                ScoreComponentRow(label: "Precio vs media 1.000", value: item.movingAverageInvestorScore ?? 0, maximum: 6, icon: "waveform.path.ecg")
                ScoreComponentRow(label: "Yield", value: item.yieldInvestorScore ?? 0, maximum: 22, icon: "percent")
                ScoreComponentRow(label: "Dividendo creciente", value: item.dividendGrowthInvestorScore ?? 0, maximum: 8, icon: "chart.line.uptrend.xyaxis")
                ScoreComponentRow(label: "Margen operativo", value: item.profitabilityInvestorScore ?? 0, maximum: 12, icon: "gauge.with.dots.needle.50percent")
                ScoreComponentRow(label: "Solvencia", value: item.leverageInvestorScore ?? 0, maximum: 10, icon: "shield.lefthalf.filled")
                ScoreComponentRow(label: "Consenso", value: item.consensusInvestorScore ?? 0, maximum: 7, icon: "building.columns.fill")
            }
            if !annualReports.isEmpty {
                Section("Informes anuales publicados") {
                    ForEach(annualReports.sorted { $0.filingDate > $1.filingDate }.prefix(8)) { report in
                        NavigationLink {
                            CompanyReportDetailView(report: report)
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(report.form).font(.caption.bold()).foregroundStyle(WhaleTheme.accent)
                                    Spacer()
                                    Text(report.filingDate.formatted(date: .abbreviated, time: .omitted))
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Text("Periodo terminado " + report.reportDate.formatted(date: .abbreviated, time: .omitted))
                                    .font(.subheadline)
                                HStack {
                                    Text("Ingresos " + (report.summary.revenue.map(compactMoney) ?? "—"))
                                    Spacer()
                                    Text("Margen " + (report.summary.netMargin.map { $0.formatted(.number.precision(.fractionLength(1))) + "%" } ?? "—"))
                                }
                                .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            if let profile {
                if profile.latestAnnualReportURL != nil {
                    Section("Informes oficiales") {
                        if let url = profile.latestAnnualReportURL {
                            Link(destination: url) {
                                Label("Último informe anual" + reportDate(profile.latestAnnualReportDate), systemImage: "books.vertical.fill")
                            }
                        }
                    }
                }
                if let url = profile.investorRelationsURL {
                    Section("Accionistas") {
                        Link(destination: url) {
                            Label(profile.investorRelationsVerified == true ? "Página oficial de inversores" : "Buscar relaciones con inversores", systemImage: "person.2.badge.gearshape")
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

    private func relativePriceLabel(_ value: Double) -> String {
        value.formatted(.number.sign(strategy: .always()).precision(.fractionLength(1))) + "%"
    }
}

private struct OpportunityRankMovementBadge: View {
    let item: ConsensusItem

    private var presentation: (icon: String, text: String, color: Color, accessibility: String)? {
        switch item.rankStatus {
        case "UP":
            let positions = abs(item.rankChange ?? 0)
            return ("arrow.up", "+\(positions)", WhaleTheme.positive, "Sube \(positions) puestos desde la actualización anterior")
        case "DOWN":
            let positions = abs(item.rankChange ?? 0)
            return ("arrow.down", "−\(positions)", WhaleTheme.negative, "Baja \(positions) puestos desde la actualización anterior")
        case "NEW":
            return ("sparkles", "Nueva", WhaleTheme.accent, "Nueva entrada en el ranking")
        case "UNCHANGED":
            return ("minus", "=", Color.secondary, "Sin cambios desde la actualización anterior")
        default:
            return nil
        }
    }

    var body: some View {
        if let presentation {
            Label(presentation.text, systemImage: presentation.icon)
                .font(.caption2.bold().monospacedDigit())
                .foregroundStyle(presentation.color)
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(presentation.color.opacity(0.12), in: Capsule())
                .accessibilityLabel(presentation.accessibility)
        }
    }
}

private func scoreMetricNames(_ metrics: [String]?) -> [String] {
    (metrics ?? []).map {
        switch $0 {
        case "yield": "yield"
        case "pe": "PER"
        case "dividendGrowth": "crecimiento del dividendo"
        case "operatingMargin": "margen operativo"
        case "movingAverage1000": "media de 1.000 sesiones"
        case "debtToEarnings": "deuda frente a beneficio"
        default: $0
        }
    }
}

struct CompanyFinancialOverviewView: View {
    let companyName: String
    let profile: CompanyProfile?
    let reports: [CompanyReport]
    var holdings: [Holding] = []

    private var annualReports: [CompanyReport] { reports.filter(\.isAnnualReport) }
    private var quarterlyReports: [CompanyReport] { reports.filter(\.isQuarterlyReport).sorted { $0.reportDate > $1.reportDate } }
    private var latest: CompanyReport? { annualReports.max { $0.reportDate < $1.reportDate } }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("EMPRESA").font(.system(size: 9, weight: .bold)).tracking(1).foregroundStyle(.white.opacity(0.65))
                    Text(profile?.name ?? companyName).font(.title2.bold()).foregroundStyle(.white)
                    HStack(spacing: 12) {
                        if let sector = profile?.sector { Label(sector, systemImage: "square.grid.2x2") }
                        if let date = latest?.reportDate { Label(date.formatted(date: .abbreviated, time: .omitted), systemImage: "calendar") }
                    }
                    .font(.caption).foregroundStyle(.white.opacity(0.72))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(18)
                .background(WhaleTheme.navy, in: RoundedRectangle(cornerRadius: 15))

                if let profile {
                    BusinessSummaryPanel(profile: profile)

                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        overviewMetric("YIELD", profile.dividendYield.map { $0.formatted(.percent.precision(.fractionLength(1))) } ?? "—", "leaf.fill")
                        overviewMetric("PER", profile.peRatio.map { $0.formatted(.number.precision(.fractionLength(1))) + "x" } ?? "—", "chart.line.uptrend.xyaxis")
                        overviewMetric("PRECIO", profile.marketPrice.map { $0.formatted(.currency(code: profile.currency ?? "USD")) } ?? "—", "dollarsign")
                        overviewMetric(
                            "VS MEDIA 1.000",
                            profile.priceVsMovingAverage1000Percent.map(relativePriceLabel) ?? "—",
                            profile.priceVsMovingAverage1000Percent.map { $0 <= 0 ? "arrow.down.right" : "arrow.up.right" } ?? "calendar.badge.exclamationmark"
                        )
                    }
                    if let average = profile.movingAverage1000 {
                        Text("Media de 1.000 cierres diarios ajustados: \(average.formatted(.currency(code: profile.currency ?? "USD")))"
                             + (profile.movingAverage1000AsOf.map { " · hasta \($0)" } ?? ""))
                            .font(.caption2).foregroundStyle(.secondary)
                    } else {
                        Text("La media de 1.000 sesiones aparecerá cuando exista historial suficiente y verificable.")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                    if profile.marketPrice != nil || profile.movingAverage1000 != nil {
                        PriceVsMovingAverageChart(profile: profile)
                    }
                }

                if !holdings.isEmpty {
                    SectionTitle("Fondos con posición", detail: "\(holdings.count)")
                    VStack(spacing: 0) {
                        ForEach(holdings.sorted { $0.value > $1.value }) { holding in
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(holding.investorName).font(.subheadline.weight(.semibold))
                                    Text(holding.weight.formatted(.number.precision(.fractionLength(2))) + "% de su cartera")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text(compactMoney(holding.value)).font(.caption.bold().monospacedDigit())
                            }.padding(12)
                            if holding.id != holdings.sorted(by: { $0.value > $1.value }).last?.id { Divider() }
                        }
                    }.whalePanel()
                }

                if !annualReports.isEmpty {
                    SectionTitle("Evolución financiera", detail: "Solo ejercicios anuales")
                    CompanyFinancialSeriesDashboard(reports: annualReports)
                } else {
                    ContentUnavailableView("Sin resultados financieros", systemImage: "chart.xyaxis.line", description: Text("El agente añadirá las series cuando exista información estructurada en la SEC."))
                        .padding().whalePanel()
                }

                if !quarterlyReports.isEmpty {
                    SectionTitle("Resultados trimestrales", detail: "Resumen, sin incluirlos en las gráficas")
                    VStack(spacing: 0) {
                        ForEach(Array(quarterlyReports.prefix(8).enumerated()), id: \.element.id) { index, report in
                            NavigationLink {
                                CompanyQuarterSummaryView(
                                    report: report,
                                    previous: quarterlyReports.dropFirst(index + 1).first
                                )
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(report.form).font(.caption.bold()).foregroundStyle(WhaleTheme.accent)
                                        Text("Periodo " + report.reportDate.formatted(date: .abbreviated, time: .omitted))
                                            .font(.subheadline).foregroundStyle(.primary)
                                    }
                                    Spacer()
                                    Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                                }.padding(12)
                            }.buttonStyle(.plain)
                            if index < min(quarterlyReports.count, 8) - 1 { Divider() }
                        }
                    }.whalePanel()
                }

                if let profile {
                    if let url = profile.investorRelationsURL {
                        Link(destination: url) {
                            Label(profile.investorRelationsVerified == true ? "Página oficial de inversores" : "Buscar relaciones con inversores", systemImage: "arrow.up.right.square")
                                .frame(maxWidth: .infinity, alignment: .leading).padding(15)
                        }.whalePanel()
                    }
                }

                if !annualReports.isEmpty {
                    SectionTitle("Informes anuales", detail: "Más reciente primero")
                    VStack(spacing: 0) {
                        ForEach(annualReports.sorted { $0.filingDate > $1.filingDate }) { report in
                            NavigationLink {
                                CompanyReportDetailView(report: report)
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(report.form).font(.caption.bold()).foregroundStyle(WhaleTheme.accent)
                                        Text("Periodo " + report.reportDate.formatted(date: .abbreviated, time: .omitted))
                                            .font(.subheadline).foregroundStyle(.primary)
                                    }
                                    Spacer()
                                    Text(report.filingDate.formatted(date: .numeric, time: .omitted)).font(.caption).foregroundStyle(.secondary)
                                    Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                                }.padding(12)
                            }.buttonStyle(.plain)
                            if report.id != annualReports.sorted(by: { $0.filingDate > $1.filingDate }).last?.id { Divider() }
                        }
                    }.whalePanel()
                }
            }
            .padding(16)
        }
        .background(WhaleTheme.background.ignoresSafeArea())
        .navigationTitle(profile?.name ?? companyName)
        .navigationBarTitleDisplayMode(.inline)
    }

    private func overviewMetric(_ label: String, _ value: String, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Image(systemName: icon).font(.caption).foregroundStyle(WhaleTheme.accent)
            Text(value).font(.headline.bold().monospacedDigit())
            Text(label).font(.system(size: 8, weight: .bold)).foregroundStyle(.secondary)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(12).whalePanel()
    }

    private func relativePriceLabel(_ value: Double) -> String {
        value.formatted(.number.sign(strategy: .always()).precision(.fractionLength(1))) + "%"
    }

    private func textPanel(_ title: String, _ text: String, _ icon: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon).font(.headline)
            Text(text).font(.subheadline).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(15).whalePanel()
    }
}

private struct PriceVsMovingAverageChart: View {
    let profile: CompanyProfile

    private struct Point: Identifiable {
        let id: String
        let label: String
        let value: Double
        let isCurrentPrice: Bool
    }

    private var points: [Point] {
        var result: [Point] = []
        if let price = profile.marketPrice {
            result.append(Point(id: "price", label: "Cotización", value: price, isCurrentPrice: true))
        }
        if let average = profile.movingAverage1000 {
            result.append(Point(id: "average", label: "Media 1.000", value: average, isCurrentPrice: false))
        }
        return result
    }

    private func relativePriceLabel(_ value: Double) -> String {
        value.formatted(.number.sign(strategy: .always()).precision(.fractionLength(1))) + "%"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Precio frente a su histórico").font(.headline)
                    Text("Cotización de la última actualización y media de 1.000 cierres")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if let difference = profile.priceVsMovingAverage1000Percent {
                    Text(relativePriceLabel(difference))
                        .font(.caption.bold().monospacedDigit())
                        .foregroundStyle(difference <= 0 ? WhaleTheme.positive : WhaleTheme.warning)
                }
            }
            Chart(points) { point in
                BarMark(
                    x: .value("Precio", point.value),
                    y: .value("Referencia", point.label)
                )
                .foregroundStyle(point.isCurrentPrice ? WhaleTheme.accent : WhaleTheme.navy.opacity(0.72))
                .cornerRadius(5)
                .annotation(position: .trailing) {
                    Text(point.value.formatted(.currency(code: profile.currency ?? "USD")))
                        .font(.caption2.bold().monospacedDigit())
                }
            }
            .chartLegend(.hidden)
            .frame(height: 112)
            HStack {
                Text("Precio actualizado: " + profile.updatedAt.formatted(date: .abbreviated, time: .omitted))
                Spacer()
                if let date = profile.movingAverage1000AsOf { Text("Media hasta: \(date)") }
            }
            .font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(15)
        .whalePanel()
    }
}

private struct BusinessSummaryPanel: View {
    let profile: CompanyProfile
    @State private var expanded = false

    private var hasContent: Bool {
        [profile.description, profile.businessModel, profile.revenueModel, profile.economicMoat]
            .contains { !($0 ?? "").isEmpty }
    }

    var body: some View {
        if hasContent {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label("Negocio en pocas palabras", systemImage: "building.2.crop.circle.fill")
                        .font(.headline)
                    Spacer()
                    Button(expanded ? "Ver menos" : "Ver más") { withAnimation { expanded.toggle() } }
                        .font(.caption.bold())
                }
                if let description = profile.description {
                    Text(description)
                        .font(.subheadline).foregroundStyle(.secondary)
                        .lineLimit(expanded ? nil : 2)
                }
                compactBusinessItem("Cómo gana dinero", profile.revenueModel, "banknote")
                compactBusinessItem("Foso defensivo", profile.economicMoat, "shield.lefthalf.filled")
                if expanded {
                    compactBusinessItem("Modelo operativo", profile.businessModel, "gearshape.2")
                    HStack(spacing: 12) {
                        if let sector = profile.sector { Label(sector, systemImage: "square.grid.2x2") }
                        if let industry = profile.industry { Label(industry, systemImage: "hammer") }
                    }
                    .font(.caption).foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(15)
            .whalePanel()
        }
    }

    @ViewBuilder
    private func compactBusinessItem(_ title: String, _ text: String?, _ icon: String) -> some View {
        if let text, !text.isEmpty {
            Divider()
            VStack(alignment: .leading, spacing: 4) {
                Label(title, systemImage: icon).font(.caption.bold()).foregroundStyle(WhaleTheme.accent)
                Text(text).font(.subheadline).foregroundStyle(.primary).lineLimit(expanded ? nil : 1)
            }
        }
    }
}

private struct CompanyQuarterSummaryView: View {
    let report: CompanyReport
    let previous: CompanyReport?

    var body: some View {
        List {
            Section("Resumen del trimestre") {
                comparison("Ingresos", current: report.summary.revenue, previous: previous?.summary.revenue, format: compactMoney)
                comparison("Beneficio neto", current: report.summary.netIncome, previous: previous?.summary.netIncome, format: compactMoney)
                comparison("Margen operativo", current: report.summary.operatingMargin, previous: previous?.summary.operatingMargin) { value in
                    value.formatted(.number.precision(.fractionLength(1))) + "%"
                }
                comparison("Beneficio por acción", current: report.summary.epsDiluted, previous: previous?.summary.epsDiluted) { value in
                    value.formatted(.currency(code: "USD"))
                }
            }
            Section("Frente a expectativas") {
                if let expected = report.summary.expectedRevenue, let actual = report.summary.revenue {
                    expectation("Ingresos", actual: actual, expected: expected, format: compactMoney)
                }
                if let expected = report.summary.expectedEPS, let actual = report.summary.epsDiluted {
                    expectation("BPA", actual: actual, expected: expected) { $0.formatted(.currency(code: "USD")) }
                }
                if report.summary.expectedRevenue == nil && report.summary.expectedEPS == nil {
                    Label("No hay una estimación de consenso verificable en la fuente disponible.", systemImage: "exclamationmark.magnifyingglass")
                        .foregroundStyle(.secondary)
                    Text("La SEC publica resultados oficiales, pero no expectativas de analistas. La app no inventa ni aproxima esa comparación.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            Section("Lectura del trimestre") {
                Text(report.highlights)
                if let previous {
                    Text("Comparación realizada con el trimestre terminado el \(previous.reportDate.formatted(date: .abbreviated, time: .omitted)).")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            Section {
                Link(destination: report.secURL) { Label("Abrir informe oficial en la SEC", systemImage: "arrow.up.right.square") }
            }
        }
        .navigationTitle(report.companyName)
        .navigationBarTitleDisplayMode(.inline)
    }

    @ViewBuilder
    private func comparison(_ label: String, current: Double?, previous: Double?, format: (Double) -> String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack { Text(label); Spacer(); Text(current.map(format) ?? "—").bold().monospacedDigit() }
            if let current, let previous, previous != 0 {
                let change = (current / previous - 1) * 100
                Text("Frente al trimestre anterior: \(change.formatted(.number.sign(strategy: .always()).precision(.fractionLength(1)))) %")
                    .font(.caption).foregroundStyle(change >= 0 ? WhaleTheme.positive : WhaleTheme.negative)
            } else {
                Text("Sin trimestre anterior comparable").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func expectation(_ label: String, actual: Double, expected: Double, format: (Double) -> String) -> some View {
        let surprise = expected == 0 ? 0 : (actual / expected - 1) * 100
        VStack(alignment: .leading, spacing: 4) {
            HStack { Text(label); Spacer(); Text(format(actual)).bold().monospacedDigit() }
            Text("Esperado \(format(expected)) · sorpresa \(surprise.formatted(.number.sign(strategy: .always()).precision(.fractionLength(1)))) %")
                .font(.caption).foregroundStyle(surprise >= 0 ? WhaleTheme.positive : WhaleTheme.negative)
        }
    }
}

private struct FinancialSeriesPoint: Identifiable {
    let metric: String
    let date: Date
    let value: Double
    var id: String { metric + "-" + date.ISO8601Format() }
}

private struct MarginSeriesPoint: Identifiable {
    let metric: String
    let date: Date
    let value: Double
    var id: String { metric + "-" + date.ISO8601Format() }
}

struct CompanyFinancialSeriesDashboard: View {
    let reports: [CompanyReport]

    var body: some View {
        VStack(spacing: 14) {
            groupedChart("Cuenta de resultados anual", subtitle: "Ingresos netos · beneficio neto", points: resultPoints)
            marginChart
            dividendChart
            groupedChart("Balance", subtitle: "Deuda y efectivo al cierre", points: instantPoints(keys: ["totalDebt", "cash"]))
            groupedChart("Generación de caja", subtitle: "Caja operativa e inversión", points: cashFlowPoints)
        }
    }

    private var merged: [String: [FinancialPeriod]] {
        var values: [String: [String: FinancialPeriod]] = [:]
        for report in reports.sorted(by: { $0.filingDate < $1.filingDate }) {
            for (metric, series) in report.metrics {
                for period in series.periods {
                    let key = (period.startDate ?? "instant") + "-" + period.endDate
                    values[metric, default: [:]][key] = period
                }
            }
        }
        return values.mapValues { $0.values.sorted { $0.endDate < $1.endDate } }
    }

    private var resultPoints: [FinancialSeriesPoint] {
        points(keys: ["revenue", "netIncome"], include: isAnnual)
    }

    private var cashFlowPoints: [FinancialSeriesPoint] {
        points(keys: ["cashFromOperations", "capitalExpenditure"], include: isAnnual)
    }

    @ViewBuilder
    private var dividendChart: some View {
        let perShare = points(keys: ["dividendPerShare"], include: isAnnual)
        if !perShare.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("Dividendo anual por acción").font(.headline)
                Text("Importe declarado en cada ejercicio").font(.caption).foregroundStyle(.secondary)
                Chart(perShare) { point in
                    LineMark(x: .value("Ejercicio", point.date), y: .value("Dividendo", point.value))
                        .foregroundStyle(WhaleTheme.positive).lineStyle(StrokeStyle(lineWidth: 3))
                    PointMark(x: .value("Ejercicio", point.date), y: .value("Dividendo", point.value))
                        .foregroundStyle(WhaleTheme.positive)
                }
                .chartYAxis { AxisMarks(position: .leading) { value in
                    AxisGridLine(); AxisValueLabel { if let amount = value.as(Double.self) { Text(amount.formatted(.currency(code: "USD"))) } }
                }}
                .chartYScale(domain: .automatic(includesZero: true))
                .frame(height: 210)
            }.padding(15).whalePanel()
        }
    }

    private func instantPoints(keys: [String]) -> [FinancialSeriesPoint] {
        points(keys: keys) { $0.startDate == nil && $0.fiscalPeriod == "FY" }
    }

    private func points(keys: [String], include: (FinancialPeriod) -> Bool) -> [FinancialSeriesPoint] {
        keys.flatMap { key in
            metricPeriods(key).compactMap { period in
                guard include(period), let date = financialDate(period.endDate) else { return nil }
                return FinancialSeriesPoint(metric: metricLabel(key), date: date, value: period.value)
            }
        }
    }

    @ViewBuilder
    private func groupedChart(_ title: String, subtitle: String, points: [FinancialSeriesPoint]) -> some View {
        if !points.isEmpty {
            let metrics = Array(Set(points.map(\.metric))).sorted()
            VStack(alignment: .leading, spacing: 10) {
                Text(title).font(.headline)
                Text(subtitle).font(.caption).foregroundStyle(.secondary)
                Chart(points) { point in
                    LineMark(x: .value("Periodo", point.date), y: .value("Valor", point.value))
                        .foregroundStyle(by: .value("Métrica", point.metric))
                        .lineStyle(StrokeStyle(lineWidth: point.metric == "Beneficio neto" ? 3 : 2))
                    PointMark(x: .value("Periodo", point.date), y: .value("Valor", point.value))
                        .foregroundStyle(by: .value("Métrica", point.metric))
                }
                .chartForegroundStyleScale(domain: metrics, range: metrics.map(metricColor))
                .chartYAxis { AxisMarks(position: .leading, values: .automatic(desiredCount: 4)) { value in
                    AxisGridLine(); AxisValueLabel { if let amount = value.as(Double.self) { Text(compactMoney(amount)) } }
                }}
                .chartYScale(domain: .automatic(includesZero: true))
                .frame(height: 230)
            }.padding(15).whalePanel()
        }
    }

    private var marginChart: some View {
        let values = marginPoints
        return Group {
            if !values.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Márgenes anuales").font(.headline)
                    Text("Margen operativo y neto comparables").font(.caption).foregroundStyle(.secondary)
                    HStack(spacing: 14) {
                        ForEach(latestMargins, id: \.metric) { point in
                            HStack(spacing: 5) {
                                Circle().fill(marginColor(point.metric)).frame(width: 7, height: 7)
                                Text(point.metric + " " + point.value.formatted(.percent.precision(.fractionLength(1))))
                                    .font(.caption.bold().monospacedDigit())
                            }
                        }
                    }
                    Chart(values) { point in
                        LineMark(x: .value("Periodo", point.date), y: .value("Margen", point.value))
                            .foregroundStyle(by: .value("Métrica", point.metric)).interpolationMethod(.catmullRom)
                        PointMark(x: .value("Periodo", point.date), y: .value("Margen", point.value))
                            .foregroundStyle(by: .value("Métrica", point.metric))
                    }
                    .chartForegroundStyleScale(
                        domain: ["Margen neto", "Margen operativo"],
                        range: [WhaleTheme.positive, WhaleTheme.info]
                    )
                    .chartYAxis { AxisMarks(position: .leading, values: .automatic(desiredCount: 5)) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let margin = value.as(Double.self) {
                                Text(margin.formatted(.percent.precision(.fractionLength(0...1))))
                            }
                        }
                    }}
                    .chartYScale(domain: .automatic(includesZero: true))
                    .frame(height: 210)
                }.padding(15).whalePanel()
            }
        }
    }

    private var marginPoints: [MarginSeriesPoint] {
        let revenue = Dictionary(uniqueKeysWithValues: (merged["revenue"] ?? []).map { (periodKey($0), $0) })
        return [("operatingIncome", "Margen operativo"), ("netIncome", "Margen neto")].flatMap { key, label in
            (merged[key] ?? []).compactMap { period in
                guard isAnnual(period), let base = revenue[periodKey(period)], base.value != 0, let date = financialDate(period.endDate) else { return nil }
                return MarginSeriesPoint(
                    metric: label,
                    date: date,
                    value: period.value / base.value
                )
            }
        }
    }

    private var latestMargins: [MarginSeriesPoint] {
        Dictionary(grouping: marginPoints, by: \.metric).values.compactMap { $0.max { $0.date < $1.date } }
            .sorted { $0.metric < $1.metric }
    }

    private func marginColor(_ metric: String) -> Color {
        metric == "Margen neto" ? WhaleTheme.positive : WhaleTheme.info
    }

    private func metricPeriods(_ key: String) -> [FinancialPeriod] {
        if key == "dividendsPaid" {
            return (merged[key] ?? []).map {
                FinancialPeriod(startDate: $0.startDate, endDate: $0.endDate, value: abs($0.value), unit: $0.unit,
                                fiscalYear: $0.fiscalYear, fiscalPeriod: $0.fiscalPeriod, frame: $0.frame)
            }
        }
        guard key == "operatingExpenses" else { return merged[key] ?? [] }
        let revenue = Dictionary(uniqueKeysWithValues: (merged["revenue"] ?? []).map { (periodKey($0), $0) })
        let operatingIncome = Dictionary(uniqueKeysWithValues: (merged["operatingIncome"] ?? []).map { (periodKey($0), $0) })
        return revenue.compactMap { key, revenuePeriod in
            guard let income = operatingIncome[key] else { return nil }
            return FinancialPeriod(
                startDate: revenuePeriod.startDate,
                endDate: revenuePeriod.endDate,
                value: revenuePeriod.value - income.value,
                unit: revenuePeriod.unit,
                fiscalYear: revenuePeriod.fiscalYear,
                fiscalPeriod: revenuePeriod.fiscalPeriod,
                frame: revenuePeriod.frame
            )
        }.sorted { $0.endDate < $1.endDate }
    }

    private func periodKey(_ period: FinancialPeriod) -> String { (period.startDate ?? "instant") + "-" + period.endDate }
    private func duration(_ period: FinancialPeriod) -> Int? {
        guard let start = period.startDate.flatMap(financialDate), let end = financialDate(period.endDate) else { return nil }
        return Calendar.current.dateComponents([.day], from: start, to: end).day
    }
    private func isAnnual(_ period: FinancialPeriod) -> Bool {
        guard period.fiscalPeriod == "FY", let days = duration(period) else { return false }
        return (330...400).contains(days)
    }
    private func metricColor(_ metric: String) -> Color {
        ["Ingresos netos": WhaleTheme.info, "Gastos": WhaleTheme.warning, "Beneficio neto": WhaleTheme.positive,
         "Deuda": WhaleTheme.negative, "Efectivo": WhaleTheme.accent,
         "Caja operativa": WhaleTheme.positive, "Inversión": WhaleTheme.info,
         "Dividendos pagados": WhaleTheme.positive][metric] ?? WhaleTheme.accent
    }
    private func metricLabel(_ key: String) -> String {
        ["revenue": "Ingresos netos", "operatingExpenses": "Gastos", "netIncome": "Beneficio neto", "totalDebt": "Deuda", "cash": "Efectivo", "cashFromOperations": "Caja operativa", "capitalExpenditure": "Inversión", "dividendPerShare": "Dividendo por acción", "dividendsPaid": "Dividendos pagados"][key] ?? key
    }
}

private func financialDate(_ value: String) -> Date? {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.date(from: value)
}

struct CompanyReportDetailView: View {
    let report: CompanyReport
    @State private var selectedMetric = "revenue"

    private let metricOrder = [
        "revenue", "operatingExpenses", "grossProfit", "operatingIncome", "netIncome",
        "dividendPerShare", "cashFromOperations", "capitalExpenditure",
        "totalDebt", "cash", "totalAssets", "totalLiabilities"
    ]

    private var availableMetrics: [String] {
        metricOrder.filter { !(report.metrics[$0]?.periods.isEmpty ?? true) }
    }

    private var selectedPeriods: [FinancialPeriod] {
        report.metrics[selectedMetric]?.periods ?? []
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text(report.form).font(.caption.bold()).foregroundStyle(WhaleTheme.accent)
                        Spacer()
                        Text(report.filingDate.formatted(date: .abbreviated, time: .omitted))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Text(report.companyName).font(.title2.bold())
                    Text("Periodo reportado: " + report.reportDate.formatted(date: .long, time: .omitted))
                        .font(.subheadline).foregroundStyle(.secondary)
                    Text(report.highlights).font(.subheadline)
                }
                .padding(.vertical, 5)
            }

            Section("Resumen financiero") {
                financialRow("Ingresos", report.summary.revenue)
                financialRow("Gastos", report.summary.expenses)
                financialRow("Beneficio operativo", report.summary.operatingIncome)
                financialRow("Beneficio neto", report.summary.netIncome)
                percentageRow("Margen operativo", report.summary.operatingMargin)
                percentageRow("Margen neto", report.summary.netMargin)
                financialRow("Deuda", report.summary.totalDebt)
                financialRow("Efectivo", report.summary.cash)
                financialRow("Flujo de caja operativo", report.summary.cashFromOperations)
                financialRow("Inversión de capital", report.summary.capitalExpenditure)
                if let dividend = report.summary.dividendPerShare {
                    LabeledContent("Dividendo por acción", value: dividend.formatted(.currency(code: "USD")))
                }
            }

            if !availableMetrics.isEmpty {
                Section("Evolución incluida en el informe") {
                    Picker("Métrica", selection: $selectedMetric) {
                        ForEach(availableMetrics, id: \.self) { Text(metricLabel($0)).tag($0) }
                    }
                    .pickerStyle(.menu)

                    if !selectedPeriods.isEmpty {
                        Chart(selectedPeriods) { period in
                            BarMark(
                                x: .value("Periodo", shortDate(period.endDate)),
                                y: .value(metricLabel(selectedMetric), period.value)
                            )
                            .foregroundStyle(WhaleTheme.accent.gradient)
                            .cornerRadius(4)
                        }
                        .chartYAxis {
                            AxisMarks(position: .leading) { value in
                                AxisGridLine()
                                AxisValueLabel {
                                    if let amount = value.as(Double.self) { Text(compactMoney(amount)) }
                                }
                            }
                        }
                        .frame(height: 220)

                        ForEach(selectedPeriods) { period in
                            HStack {
                                Text(periodLabel(period))
                                Spacer()
                                Text(formatted(period.value, unit: period.unit)).bold().monospacedDigit()
                            }
                            .font(.caption)
                        }
                    }
                    Text("Se muestran todos los periodos comparativos etiquetados en el XBRL de esta presentación.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }

            Section("Fuente oficial") {
                Link(destination: report.secURL) {
                    Label("Abrir el informe completo en la SEC", systemImage: "arrow.up.right.square")
                }
                Text("Datos estructurados obtenidos de SEC EDGAR XBRL. Las etiquetas pueden variar entre compañías.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Resultados")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            if report.metrics[selectedMetric] == nil { selectedMetric = availableMetrics.first ?? "revenue" }
        }
    }

    private func financialRow(_ label: String, _ value: Double?) -> some View {
        LabeledContent(label, value: value.map(compactMoney) ?? "—")
    }

    private func percentageRow(_ label: String, _ value: Double?) -> some View {
        LabeledContent(label, value: value.map { $0.formatted(.number.precision(.fractionLength(1))) + "%" } ?? "—")
    }

    private func metricLabel(_ key: String) -> String {
        [
            "revenue": "Ingresos", "operatingExpenses": "Gastos operativos", "grossProfit": "Beneficio bruto",
            "operatingIncome": "Beneficio operativo", "netIncome": "Beneficio neto", "cashFromOperations": "Caja operativa",
            "dividendPerShare": "Dividendo por acción", "dividendsPaid": "Dividendos pagados",
            "capitalExpenditure": "Inversión de capital", "totalDebt": "Deuda", "cash": "Efectivo",
            "totalAssets": "Activos", "totalLiabilities": "Pasivos"
        ][key] ?? key
    }

    private func periodLabel(_ period: FinancialPeriod) -> String {
        if let start = period.startDate { return shortDate(start) + " – " + shortDate(period.endDate) }
        return shortDate(period.endDate)
    }

    private func shortDate(_ value: String) -> String {
        let parts = value.split(separator: "-")
        return parts.count >= 2 ? "\(parts[1])/\(parts[0])" : value
    }

    private func formatted(_ value: Double, unit: String) -> String {
        unit == "USD/shares"
            ? value.formatted(.currency(code: "USD"))
            : compactMoney(value)
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
                    VStack(alignment: .trailing, spacing: 1) {
                        Text("\(value) / \(maximum)").bold().monospacedDigit()
                        Text("Peso: \(maximum) %").font(.caption2).foregroundStyle(.secondary)
                    }
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
