import SwiftUI
#if canImport(DividendIntelligenceKit)
import DividendIntelligenceKit
#endif

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if let snapshot = model.snapshot {
                FundTabs(snapshot: snapshot)
            } else if model.isLoading {
                DividendLoadingView()
            } else {
                DividendDataErrorView(message: model.errorMessage) {
                    Task { await model.refresh() }
                }
            }
        }
    }
}

private struct FundTabs: View {
    let snapshot: AppSnapshot
    @State private var selectedInvestorID = ""

    private var sortedInvestors: [Investor] {
        snapshot.investors.sorted { $0.portfolioValue > $1.portfolioValue }
    }

    private var recentUpdates: Int {
        let cutoff = Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? .distantPast
        let filings = snapshot.filingUpdates.filter { $0.filingDate >= cutoff }.count
        let annualReports = snapshot.companyReports.filter {
            $0.filingDate >= cutoff && ($0.form.uppercased().hasPrefix("10-K") || $0.form.uppercased().hasPrefix("20-F") || $0.form.uppercased().hasPrefix("40-F"))
        }.count
        return filings + annualReports
    }

    private var selection: Binding<String> {
        Binding(
            get: {
                sortedInvestors.contains(where: { $0.id == selectedInvestorID })
                    ? selectedInvestorID
                    : sortedInvestors.first?.id ?? ""
            },
            set: { selectedInvestorID = $0 }
        )
    }

    var body: some View {
        TabView {
            NavigationStack { DashboardView(snapshot: snapshot, selectedInvestorID: selection) }
                .tabItem { Label("Dividendos", systemImage: "leaf.fill") }
            NavigationStack { SmartMoneyView(snapshot: snapshot, selectedInvestorID: selection) }
                .tabItem { Label("Smart Money", systemImage: "chart.line.uptrend.xyaxis") }
            NavigationStack { FilingsView(snapshot: snapshot, selectedInvestorID: selection) }
                .tabItem { Label("13F", systemImage: "doc.text.magnifyingglass") }
            NavigationStack { FundsView(snapshot: snapshot, selectedInvestorID: selection) }
                .tabItem { Label("Fondos", systemImage: "building.columns.fill") }
            NavigationStack { EventsHubView(snapshot: snapshot) }
                .tabItem { Label("Eventos", systemImage: "calendar.badge.clock") }
                .badge(recentUpdates)
        }
        .tint(WhaleTheme.accent)
        .onAppear {
            if selectedInvestorID.isEmpty { selectedInvestorID = sortedInvestors.first?.id ?? "" }
        }
    }
}


private enum EventsHubSection: String, CaseIterable, Identifiable {
    case dividends
    case updates

    var id: String { rawValue }
    var title: String { self == .dividends ? "Dividendos" : "Novedades" }
}

private struct EventsHubView: View {
    let snapshot: AppSnapshot
    @State private var section: EventsHubSection = .dividends

    var body: some View {
        VStack(spacing: 0) {
            Picker("Eventos", selection: $section) {
                ForEach(EventsHubSection.allCases) { item in
                    Text(item.title).tag(item)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 4)
            .background(WhaleTheme.background)

            if section == .dividends {
                DividendEventsView(snapshot: snapshot)
            } else {
                UpdatesView(snapshot: snapshot)
            }
        }
        .background(WhaleTheme.background.ignoresSafeArea())
    }
}

private enum DividendEventFilter: String, CaseIterable, Identifiable {
    case all
    case confirmed
    case estimated

    var id: String { rawValue }
    var title: String {
        switch self {
        case .all: "Todos"
        case .confirmed: "Confirmados"
        case .estimated: "Estimados"
        }
    }

    func matches(_ event: DividendEvent) -> Bool {
        switch self {
        case .all: true
        case .confirmed: !event.isEstimated
        case .estimated: event.isEstimated
        }
    }
}

private struct DividendDaySection: Identifiable {
    let date: Date
    let events: [DividendEvent]
    var id: Date { date }
}

private struct DividendEventsView: View {
    @EnvironmentObject private var model: AppModel
    let snapshot: AppSnapshot
    @State private var filter: DividendEventFilter = .all
    @State private var selectedDate: Date?

    private var today: Date { Calendar.current.startOfDay(for: Date()) }

    private var upcomingEvents: [DividendEvent] {
        snapshot.dividendEvents
            .filter { event in
                guard let next = nextDividendDate(event, onOrAfter: today) else { return false }
                return next >= today && filter.matches(event)
            }
            .sorted {
                (nextDividendDate($0, onOrAfter: today) ?? .distantFuture) <
                (nextDividendDate($1, onOrAfter: today) ?? .distantFuture)
            }
    }

    private var visibleEvents: [DividendEvent] {
        guard let selectedDate else { return upcomingEvents }
        return upcomingEvents.filter {
            guard let date = nextDividendDate($0, onOrAfter: today) else { return false }
            return Calendar.current.isDate(date, inSameDayAs: selectedDate)
        }
    }

    private var eventDays: [Date] {
        var seen = Set<Date>()
        return upcomingEvents.compactMap { nextDividendDate($0, onOrAfter: today) }
            .map { Calendar.current.startOfDay(for: $0) }
            .filter { seen.insert($0).inserted }
            .prefix(14)
            .map { $0 }
    }

    private var sections: [DividendDaySection] {
        let grouped = Dictionary(grouping: visibleEvents) { event in
            Calendar.current.startOfDay(for: nextDividendDate(event, onOrAfter: today) ?? .distantFuture)
        }
        return grouped.map { DividendDaySection(date: $0.key, events: $0.value) }
            .sorted { $0.date < $1.date }
    }

    private var confirmedCount: Int { snapshot.dividendEvents.filter { !$0.isEstimated }.count }
    private var estimatedCount: Int { snapshot.dividendEvents.filter(\.isEstimated).count }

    private var profilesByTicker: [String: CompanyProfile] {
        Dictionary(
            snapshot.companyProfiles.compactMap { profile in
                profile.ticker.map { ($0.uppercased(), profile) }
            },
            uniquingKeysWith: { first, _ in first }
        )
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                overview

                Picker("Estado", selection: $filter) {
                    ForEach(DividendEventFilter.allCases) { item in Text(item.title).tag(item) }
                }
                .pickerStyle(.segmented)
                .onChange(of: filter) { _, _ in selectedDate = nil }

                dateStrip

                if visibleEvents.isEmpty {
                    ContentUnavailableView(
                        "Sin dividendos próximos",
                        systemImage: "calendar.badge.checkmark",
                        description: Text("No hay eventos que coincidan con el filtro actual. Los confirmados prevalecen sobre las estimaciones.")
                    )
                    .frame(maxWidth: .infinity)
                    .padding(.top, 28)
                } else {
                    ForEach(sections) { section in
                        Section {
                            VStack(spacing: 10) {
                                ForEach(section.events) { event in
                                    DividendEventCard(
                                        event: event,
                                        profile: profilesByTicker[event.ticker.uppercased()],
                                        exchangeRates: snapshot.exchangeRates
                                    )
                                }
                            }
                        } header: {
                            DividendDateHeader(date: section.date)
                        }
                    }
                }

                Label(
                    "Fuentes: Investor Relations → SEC/EDGAR → Alpha Vantage → estimación",
                    systemImage: "checkmark.shield.fill"
                )
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.top, 4)

                if let rates = snapshot.exchangeRates {
                    Label("Conversión aproximada a EUR · \(rates.source) · \(rates.asOf)", systemImage: "eurosign.arrow.circlepath")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
        }
        .background(WhaleTheme.background)
        .navigationTitle("Eventos de dividendos")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refresh() }
    }

    private var overview: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("CALENDARIO DE DIVIDENDOS")
                        .font(.system(size: 9, weight: .heavy))
                        .tracking(1)
                        .foregroundStyle(WhaleTheme.accent)
                    Text("Próximos eventos")
                        .font(.title2.bold())
                    Text("Declaración, ex-dividendo, registro y pago en una sola vista.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "calendar.badge.clock")
                    .font(.system(size: 30, weight: .semibold))
                    .foregroundStyle(WhaleTheme.accent)
            }

            HStack(spacing: 9) {
                DividendSummaryMetric(value: "\(confirmedCount)", label: "Confirmados", tint: WhaleTheme.positive)
                DividendSummaryMetric(value: "\(estimatedCount)", label: "Estimados", tint: WhaleTheme.warning)
                DividendSummaryMetric(value: totalEURText, label: "Total EUR / acción", tint: WhaleTheme.info)
            }
        }
        .padding(16)
        .whalePanel()
    }

    private var totalEURText: String {
        guard let rates = snapshot.exchangeRates else { return "—" }
        let converted = visibleEvents.compactMap { rates.amountInEUR($0.amount, currency: $0.currency) }
        guard converted.count == visibleEvents.count, !converted.isEmpty else { return "—" }
        let approximate = visibleEvents.contains { $0.currency.uppercased() != "EUR" || $0.isEstimated }
        return (approximate ? "≈ " : "") + converted.reduce(0, +).formatted(.currency(code: "EUR"))
    }

    private var dateStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Button {
                    selectedDate = nil
                } label: {
                    VStack(spacing: 3) {
                        Text("TODOS").font(.system(size: 8, weight: .bold))
                        Image(systemName: "calendar")
                            .font(.subheadline.bold())
                    }
                    .foregroundStyle(selectedDate == nil ? .white : .primary)
                    .frame(width: 58, height: 54)
                    .background(selectedDate == nil ? WhaleTheme.accent : WhaleTheme.panel, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)

                ForEach(eventDays, id: \.self) { day in
                    let selected = selectedDate.map { Calendar.current.isDate($0, inSameDayAs: day) } ?? false
                    Button {
                        selectedDate = selected ? nil : day
                    } label: {
                        VStack(spacing: 2) {
                            Text(day.formatted(.dateTime.weekday(.abbreviated)).uppercased())
                                .font(.system(size: 8, weight: .bold))
                            Text(day.formatted(.dateTime.day()))
                                .font(.headline.bold().monospacedDigit())
                            Text(day.formatted(.dateTime.month(.abbreviated)))
                                .font(.system(size: 8, weight: .medium))
                        }
                        .foregroundStyle(selected ? .white : .primary)
                        .frame(width: 58, height: 54)
                        .background(selected ? WhaleTheme.accent : WhaleTheme.panel, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(selected ? .clear : .primary.opacity(0.06)))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

private struct DividendSummaryMetric: View {
    let value: String
    let label: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value).font(.title3.bold().monospacedDigit()).foregroundStyle(tint)
            Text(label.uppercased()).font(.system(size: 7, weight: .bold)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(tint.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
    }
}

private struct DividendDateHeader: View {
    let date: Date

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.headline)
            Spacer()
            Text(date.formatted(date: .abbreviated, time: .omitted))
                .font(.caption.bold()).foregroundStyle(.secondary)
        }
    }

    private var title: String {
        if Calendar.current.isDateInToday(date) { return "Hoy" }
        if Calendar.current.isDateInTomorrow(date) { return "Mañana" }
        return date.formatted(.dateTime.weekday(.wide)).capitalized
    }
}

private struct DividendEventCard: View {
    let event: DividendEvent
    let profile: CompanyProfile?
    let exchangeRates: ExchangeRates?

    private var amountInEUR: Double? {
        exchangeRates?.amountInEUR(event.amount, currency: event.currency)
    }

    private var quoteCurrency: String {
        (profile?.currency ?? event.currency).uppercased()
    }

    private var quoteInEUR: Double? {
        guard let price = profile?.marketPrice else { return nil }
        return exchangeRates?.amountInEUR(price, currency: quoteCurrency)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 13) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 7) {
                        Text(event.ticker)
                            .font(.caption.bold().monospaced())
                            .foregroundStyle(WhaleTheme.accent)
                            .padding(.horizontal, 7).padding(.vertical, 4)
                            .background(WhaleTheme.accent.opacity(0.10), in: Capsule())
                        DividendStatusBadge(event: event)
                    }
                    Text(event.company).font(.headline).lineLimit(2)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 2) {
                    if let amountInEUR {
                        Text(((event.isEstimated || event.currency.uppercased() != "EUR") ? "≈ " : "") + amountInEUR.formatted(.currency(code: "EUR")))
                            .font(.title3.bold().monospacedDigit())
                        Text("por acción")
                            .font(.caption2).foregroundStyle(.secondary)
                        if event.currency.uppercased() != "EUR" {
                            Text("Original: " + event.amount.formatted(.number.precision(.fractionLength(2...6))) + " " + event.currency)
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    } else {
                        Text((event.isEstimated ? "≈ " : "") + event.amount.formatted(.number.precision(.fractionLength(2...6))) + " " + event.currency)
                            .font(.title3.bold().monospacedDigit())
                        Text("Conversión a EUR no disponible")
                            .font(.caption2).foregroundStyle(WhaleTheme.warning)
                    }
                }
            }

            if let price = profile?.marketPrice {
                HStack(spacing: 8) {
                    Image(systemName: "chart.line.uptrend.xyaxis")
                        .foregroundStyle(WhaleTheme.info)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("COTIZACIÓN")
                            .font(.system(size: 7, weight: .bold))
                            .foregroundStyle(.secondary)
                        if let quoteInEUR {
                            Text((quoteCurrency == "EUR" ? "" : "≈ ") + quoteInEUR.formatted(.currency(code: "EUR")))
                                .font(.subheadline.bold().monospacedDigit())
                            if quoteCurrency != "EUR" {
                                Text("Original: " + price.formatted(.currency(code: quoteCurrency)))
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                        } else {
                            Text(price.formatted(.currency(code: quoteCurrency)))
                                .font(.subheadline.bold().monospacedDigit())
                        }
                    }
                    Spacer()
                    if let updatedAt = profile?.updatedAt {
                        Text("Actualizada\n" + updatedAt.formatted(date: .abbreviated, time: .shortened))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.trailing)
                    }
                }
                .padding(10)
                .background(WhaleTheme.info.opacity(0.06), in: RoundedRectangle(cornerRadius: 9))
            }

            HStack(spacing: 7) {
                DividendMilestone(label: "EX-DIV", value: event.exDividendDate, estimated: event.isEstimated)
                DividendMilestone(label: "REGISTRO", value: event.recordDate, estimated: event.isEstimated)
                DividendMilestone(label: "PAGO", value: event.paymentDate, estimated: event.isEstimated)
            }

            Divider()

            HStack(spacing: 8) {
                Image(systemName: event.isEstimated ? "wand.and.stars" : "checkmark.seal.fill")
                    .foregroundStyle(event.isEstimated ? WhaleTheme.warning : WhaleTheme.positive)
                VStack(alignment: .leading, spacing: 2) {
                    Text(event.source).font(.caption.bold())
                    Text("Confianza \(event.confidence)%")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                if let url = event.sourceURL {
                    Link(destination: url) {
                        Image(systemName: "arrow.up.right.square")
                            .font(.subheadline.bold())
                            .foregroundStyle(WhaleTheme.accent)
                    }
                }
            }

            if let reason = event.estimatedReason, event.isEstimated {
                Text(reason)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(15)
        .whalePanel()
        .overlay {
            if event.isEstimated {
                RoundedRectangle(cornerRadius: 12)
                    .stroke(WhaleTheme.warning.opacity(0.35), style: StrokeStyle(lineWidth: 1, dash: [5, 4]))
            }
        }
    }
}

private struct DividendStatusBadge: View {
    let event: DividendEvent

    var body: some View {
        Text(event.isEstimated ? "ESTIMADO" : "CONFIRMADO")
            .font(.system(size: 8, weight: .heavy))
            .tracking(0.5)
            .foregroundStyle(event.isEstimated ? WhaleTheme.warning : WhaleTheme.positive)
            .padding(.horizontal, 7).padding(.vertical, 4)
            .background((event.isEstimated ? WhaleTheme.warning : WhaleTheme.positive).opacity(0.10), in: Capsule())
    }
}

private struct DividendMilestone: View {
    let label: String
    let value: String?
    let estimated: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.system(size: 7, weight: .bold)).foregroundStyle(.secondary)
            Text(formatted)
                .font(.caption.bold().monospacedDigit())
                .foregroundStyle(value == nil ? .tertiary : .primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(9)
        .background(WhaleTheme.navy.opacity(0.045), in: RoundedRectangle(cornerRadius: 9))
    }

    private var formatted: String {
        guard let value, let date = parseDividendDate(value) else { return "—" }
        let prefix = estimated ? "≈ " : ""
        return prefix + date.formatted(.dateTime.day().month(.abbreviated))
    }
}

private func parseDividendDate(_ value: String?) -> Date? {
    guard let value else { return nil }
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.date(from: value)
}

private func nextDividendDate(_ event: DividendEvent, onOrAfter cutoff: Date) -> Date? {
    let dates = [event.exDividendDate, event.recordDate, event.paymentDate, event.declarationDate]
        .compactMap(parseDividendDate)
        .map { Calendar.current.startOfDay(for: $0) }
        .filter { $0 >= Calendar.current.startOfDay(for: cutoff) }
    return dates.min()
}

private struct DividendLoadingView: View {
    var body: some View {
        VStack(spacing: 22) {
            ZStack {
                Circle().fill(WhaleTheme.accent.opacity(0.12)).frame(width: 82, height: 82)
                Image(systemName: "leaf.fill")
                    .font(.system(size: 34, weight: .semibold))
                    .foregroundStyle(WhaleTheme.accent)
            }
            VStack(spacing: 7) {
                Text("Dividend Intelligence")
                    .font(.title2.bold())
                Text("Actualizando oportunidades y movimientos 13F…")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            ProgressView().tint(WhaleTheme.accent)
        }
        .padding(30)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(WhaleTheme.background)
    }
}

private struct DividendDataErrorView: View {
    let message: String?
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "icloud.slash.fill")
                .font(.system(size: 36))
                .foregroundStyle(WhaleTheme.warning)
                .frame(width: 78, height: 78)
                .background(WhaleTheme.warning.opacity(0.12), in: Circle())
            VStack(spacing: 8) {
                Text("No podemos actualizar los datos")
                    .font(.title2.bold())
                Text(message ?? "Comprueba la conexión e inténtalo de nuevo.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            Button(action: retry) {
                Label("Volver a intentar", systemImage: "arrow.clockwise")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 4)
            }
            .buttonStyle(.borderedProminent)
            .tint(WhaleTheme.accent)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(WhaleTheme.background)
    }
}

private struct DashboardView: View {
    @EnvironmentObject private var model: AppModel
    let snapshot: AppSnapshot
    @Binding var selectedInvestorID: String
    @State private var yieldFilter: DividendYieldFilter = .all

    private var investor: Investor? {
        snapshot.investors.first(where: { $0.id == selectedInvestorID }) ?? snapshot.investors.first
    }
    private var holdings: [Holding] {
        snapshot.holdings
            .filter { $0.investorId == investor?.id && yieldFilter.matches(yieldPercent(for: $0)) }
            .sorted { $0.value > $1.value }
    }
    private var movements: [Movement] {
        snapshot.movements.filter { $0.investorId == investor?.id }
    }

    private var scoredCompanies: [ConsensusItem] {
        snapshot.consensus
            .filter { $0.opportunityScore != nil }
            .sorted { ($0.opportunityScore ?? 0, $0.holders) > ($1.opportunityScore ?? 0, $1.holders) }
    }

    private var incomeIdeas: [ConsensusItem] {
        scoredCompanies
            .filter { $0.holders > 0 && ($0.yield ?? 0) >= 3 && ($0.yield ?? 0) <= 9 }
            .sorted {
                ($0.opportunityScore ?? 0, $0.yield ?? 0, $0.holders) >
                ($1.opportunityScore ?? 0, $1.yield ?? 0, $1.holders)
            }
    }

    private var growingDividendIdeas: [ConsensusItem] {
        scoredCompanies
            .filter { $0.holders > 0 && ($0.dividendGrowth ?? 0) > 0 && ($0.yield ?? 0) > 0 }
            .sorted {
                ($0.dividendGrowth ?? 0, $0.opportunityScore ?? 0) >
                ($1.dividendGrowth ?? 0, $1.opportunityScore ?? 0)
            }
    }

    private var discountedIdeas: [ConsensusItem] {
        scoredCompanies
            .filter { $0.holders > 0 && ($0.priceVsMovingAverage1000Percent ?? 1) < 0 }
            .sorted {
                ($0.opportunityScore ?? 0, -($0.priceVsMovingAverage1000Percent ?? 0)) >
                ($1.opportunityScore ?? 0, -($1.priceVsMovingAverage1000Percent ?? 0))
            }
    }

    private var highConvictionCount: Int {
        snapshot.consensus.filter { $0.holders >= 4 && $0.buying > $0.selling }.count
    }

    private var targetYieldCount: Int {
        snapshot.consensus.filter { ($0.yield ?? 0) >= 3 && ($0.yield ?? 0) <= 9 }.count
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 22) {
                dividendHomeHeader
                dividendPulse

                if !incomeIdeas.isEmpty {
                    SectionTitle("Oportunidades de renta", detail: "Yield 3–9 % · score completo")
                    ScrollView(.horizontal, showsIndicators: false) {
                        LazyHStack(spacing: 12) {
                            ForEach(incomeIdeas.prefix(8)) { item in
                                NavigationLink {
                                    opportunityDestination(item)
                                } label: {
                                    DividendIdeaCard(item: item)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    .contentMargins(.horizontal, 16, for: .scrollContent)
                    .padding(.horizontal, -16)
                }

                if !growingDividendIdeas.isEmpty {
                    dividendCollection(
                        title: "Dividendo creciente",
                        detail: "Crecimiento anual positivo",
                        icon: "chart.line.uptrend.xyaxis",
                        tint: WhaleTheme.positive,
                        items: Array(growingDividendIdeas.prefix(5)),
                        value: { item in
                            item.dividendGrowth.map { "+" + $0.formatted(.number.precision(.fractionLength(1))) + "% anual" } ?? "—"
                        }
                    )
                }

                if !discountedIdeas.isEmpty {
                    dividendCollection(
                        title: "Precio bajo su tendencia",
                        detail: "Por debajo de la media de 1.000 sesiones",
                        icon: "arrow.down.right.circle.fill",
                        tint: WhaleTheme.info,
                        items: Array(discountedIdeas.prefix(5)),
                        value: { item in
                            item.priceVsMovingAverage1000Percent.map { $0.formatted(.number.sign(strategy: .always()).precision(.fractionLength(1))) + "%" } ?? "—"
                        }
                    )
                }

                fundMonitor

                Label(
                    "Datos actualizados " + snapshot.generatedAt.formatted(date: .abbreviated, time: .shortened),
                    systemImage: "icloud.and.arrow.down"
                )
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.top, 4)
            }
            .padding(16)
        }
        .background(WhaleTheme.background.ignoresSafeArea())
        .navigationTitle("Dividend Intelligence")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refresh() }
    }

    private var dividendHomeHeader: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("RADAR DE DIVIDENDOS")
                        .font(.system(size: 10, weight: .heavy))
                        .tracking(1.2)
                        .foregroundStyle(.white.opacity(0.68))
                    Text("Invierte con renta\ny convicción")
                        .font(.system(size: 29, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                Image(systemName: "leaf.circle.fill")
                    .font(.system(size: 44))
                    .foregroundStyle(WhaleTheme.mint)
            }

            HStack(spacing: 8) {
                Label(snapshot.asOfQuarter, systemImage: "calendar")
                Label("GitHub", systemImage: "checkmark.icloud.fill")
                Label("Diario", systemImage: "arrow.triangle.2.circlepath")
            }
            .font(.caption.bold())
            .foregroundStyle(.white.opacity(0.82))
        }
        .padding(20)
        .background(
            LinearGradient(
                colors: [WhaleTheme.navy, Color(red: 0.035, green: 0.30, blue: 0.28)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 24, style: .continuous)
        )
        .overlay(alignment: .bottomTrailing) {
            Circle()
                .fill(WhaleTheme.mint.opacity(0.12))
                .frame(width: 150, height: 150)
                .offset(x: 44, y: 60)
        }
        .clipped()
        .shadow(color: WhaleTheme.navy.opacity(0.16), radius: 18, y: 9)
    }

    private var dividendPulse: some View {
        VStack(alignment: .leading, spacing: 13) {
            SectionTitle("Pulso de oportunidades", detail: "Universo institucional")
            HStack(spacing: 9) {
                PulseMetric(value: "\(scoredCompanies.count)", label: "Analizadas", icon: "checkmark.seal.fill", tint: WhaleTheme.accent)
                PulseMetric(value: "\(targetYieldCount)", label: "Yield objetivo", icon: "percent", tint: WhaleTheme.positive)
                PulseMetric(value: "\(highConvictionCount)", label: "Convicción", icon: "building.columns.fill", tint: WhaleTheme.info)
            }
        }
    }

    @ViewBuilder
    private func dividendCollection(
        title: String,
        detail: String,
        icon: String,
        tint: Color,
        items: [ConsensusItem],
        value: @escaping (ConsensusItem) -> String
    ) -> some View {
        VStack(alignment: .leading, spacing: 11) {
            SectionTitle(title, detail: detail)
            VStack(spacing: 0) {
                ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
                    NavigationLink {
                        opportunityDestination(item)
                    } label: {
                        DividendSignalRow(item: item, icon: icon, tint: tint, signal: value(item))
                    }
                    .buttonStyle(.plain)
                    if index < items.count - 1 { Divider().padding(.leading, 58) }
                }
            }
            .whalePanel()
        }
    }

    private var fundMonitor: some View {
        VStack(alignment: .leading, spacing: 13) {
            SectionTitle("Monitor 13F", detail: investor?.quarter ?? snapshot.asOfQuarter)
            FundSelector(investors: snapshot.investors, selection: $selectedInvestorID)

            HStack(spacing: 9) {
                Metric(value: compactUSD(investor?.portfolioValue ?? 0), label: "Cartera")
                Metric(value: "\(holdings.count)", label: "Posiciones")
                Metric(value: "\(movements.count)", label: "Cambios")
            }

            if !movements.isEmpty {
                HStack(spacing: 8) {
                    ActivityLink(title: "Nuevas", action: .new, color: WhaleTheme.positive, movements: movements, quarter: investor?.quarter ?? snapshot.asOfQuarter, snapshot: snapshot)
                    ActivityLink(title: "Aumentadas", action: .increased, color: WhaleTheme.info, movements: movements, quarter: investor?.quarter ?? snapshot.asOfQuarter, snapshot: snapshot)
                    ActivityLink(title: "Reducidas", action: .reduced, color: WhaleTheme.warning, movements: movements, quarter: investor?.quarter ?? snapshot.asOfQuarter, snapshot: snapshot)
                    ActivityLink(title: "Vendidas", action: .sold, color: WhaleTheme.negative, movements: movements, quarter: investor?.quarter ?? snapshot.asOfQuarter, snapshot: snapshot)
                }
            }

            DisclosureGroup("Principales posiciones") {
                DividendYieldFilterPicker(selection: $yieldFilter)
                    .padding(.top, 8)
                VStack(spacing: 0) {
                    ForEach(Array(holdings.prefix(8).enumerated()), id: \.element.id) { index, holding in
                        NavigationLink {
                            CompanyFinancialOverviewView(
                                companyName: holding.company,
                                profile: profile(for: holding),
                                reports: snapshot.companyReports.filter { $0.cusip == holding.cusip },
                                holdings: snapshot.holdings.filter { $0.cusip == holding.cusip }
                            )
                        } label: {
                            HoldingSummaryRow(rank: index + 1, holding: holding, dividendYield: yieldPercent(for: holding), peRatio: profile(for: holding)?.peRatio)
                        }
                        .buttonStyle(.plain)
                        if index < min(7, holdings.count - 1) { Divider().padding(.leading, 42) }
                    }
                }
                .whalePanel()
                .padding(.top, 8)
            }
            .font(.subheadline.weight(.semibold))
        }
    }

    @ViewBuilder
    private func opportunityDestination(_ item: ConsensusItem) -> some View {
        OpportunityAnalysisView(
            item: item,
            profile: item.cusip.flatMap { cusip in snapshot.companyProfiles.first { $0.cusip == cusip } },
            reports: snapshot.companyReports.filter { $0.cusip == item.cusip }
        )
    }

    private func compactUSD(_ value: Double) -> String {
        if value >= 1_000_000_000 { return String(format: "$%.0fB", value / 1_000_000_000) }
        if value >= 1_000_000 { return String(format: "$%.0fM", value / 1_000_000) }
        return value.formatted(.currency(code: "USD"))
    }

    private func profile(for holding: Holding) -> CompanyProfile? {
        snapshot.companyProfiles.first { $0.cusip == holding.cusip }
    }

    private func yieldPercent(for holding: Holding) -> Double? {
        profile(for: holding)?.dividendYield.map { $0 * 100 }
    }
}

enum DividendYieldFilter: String, CaseIterable, Identifiable {
    case all = "Todas"
    case betweenThreeAndFive = "Yield 3–5 %"
    case aboveFive = "Yield > 5 %"
    case belowThreeOrNone = "Yield < 3 % o sin dividendo"

    var id: Self { self }

    func matches(_ yield: Double?) -> Bool {
        switch self {
        case .all: true
        case .betweenThreeAndFive: yield.map { $0 >= 3 && $0 <= 5 } ?? false
        case .aboveFive: yield.map { $0 > 5 } ?? false
        case .belowThreeOrNone: yield.map { $0 < 3 } ?? true
        }
    }
}

struct DividendYieldFilterPicker: View {
    @Binding var selection: DividendYieldFilter

    var body: some View {
        HStack {
            Label("Filtro de dividendos", systemImage: "line.3.horizontal.decrease.circle")
                .font(.subheadline.weight(.semibold))
            Spacer()
            Picker("Yield", selection: $selection) {
                ForEach(DividendYieldFilter.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.menu)
        }
        .padding(.horizontal, 12).padding(.vertical, 9)
        .whalePanel()
    }
}

struct FundSelector: View {
    let investors: [Investor]
    @Binding var selection: String

    private var sortedInvestors: [Investor] {
        investors.sorted { $0.portfolioValue > $1.portfolioValue }
    }

    private var selectedInvestor: Investor? {
        investors.first { $0.id == selection } ?? sortedInvestors.first
    }

    var body: some View {
        Menu {
            ForEach(sortedInvestors) { investor in
                Button {
                    withAnimation(.snappy) { selection = investor.id }
                } label: {
                    Label(investor.name, systemImage: selection == investor.id ? "checkmark" : "building.columns")
                }
            }
        } label: {
            HStack(spacing: 11) {
                Image(systemName: "building.columns.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(WhaleTheme.accent)
                    .frame(width: 34, height: 34)
                    .background(WhaleTheme.accent.opacity(0.11), in: RoundedRectangle(cornerRadius: 9))
                VStack(alignment: .leading, spacing: 2) {
                    Text("FONDO SELECCIONADO")
                        .font(.system(size: 8, weight: .bold))
                        .tracking(0.7)
                        .foregroundStyle(.secondary)
                    Text(selectedInvestor?.name ?? "Seleccionar fondo")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                    if let manager = selectedInvestor?.manager {
                        Text(manager).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                Spacer()
                Text("\(investors.count)")
                    .font(.caption.bold().monospacedDigit())
                    .foregroundStyle(.secondary)
                Image(systemName: "chevron.up.chevron.down")
                    .font(.caption2.bold())
                    .foregroundStyle(.tertiary)
            }
            .padding(10)
            .whalePanel()
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Seleccionar fondo")
        .accessibilityValue(selectedInvestor?.name ?? "Ninguno")
    }
}

private struct Metric: View {
    let value: String
    let label: String
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label.uppercased())
                .font(.system(size: 9, weight: .semibold)).foregroundStyle(.secondary)
            Text(value).font(.system(size: 17, weight: .bold, design: .rounded)).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .whalePanel()
    }
}

private struct PulseMetric: View {
    let value: String
    let label: String
    let icon: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Image(systemName: icon)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(tint)
                .frame(width: 30, height: 30)
                .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 9, style: .continuous))
            Text(value)
                .font(.system(size: 21, weight: .bold, design: .rounded))
                .monospacedDigit()
            Text(label)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .whalePanel()
    }
}

private struct DividendIdeaCard: View {
    let item: ConsensusItem

    var body: some View {
        VStack(alignment: .leading, spacing: 13) {
            HStack(alignment: .top) {
                CompanyMonogram(name: item.company, tint: WhaleTheme.accent)
                Spacer()
                ScorePill(score: item.opportunityScore, maximum: item.opportunityScoreMaximum ?? 100)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(displayCompanyName(item.company))
                    .font(.headline)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
                    .frame(height: 44, alignment: .topLeading)
                Text(displaySector)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Divider()
            HStack(spacing: 12) {
                miniMetric("YIELD", item.yield.map { $0.formatted(.number.precision(.fractionLength(1))) + "%" } ?? "—", WhaleTheme.positive)
                miniMetric("PER", item.pe.map { $0.formatted(.number.precision(.fractionLength(1))) + "x" } ?? "—", .primary)
                miniMetric("FONDOS", "\(item.holders)", WhaleTheme.info)
            }
        }
        .padding(15)
        .frame(width: 250, alignment: .leading)
        .background(WhaleTheme.panel, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.primary.opacity(0.07)))
        .shadow(color: Color.black.opacity(0.045), radius: 10, y: 4)
    }

    private var displaySector: String {
        guard let sector = item.sector, sector.lowercased() != "unknown", !sector.isEmpty else {
            return "Oportunidad con score completo"
        }
        return sector
    }

    private func miniMetric(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value).font(.subheadline.bold().monospacedDigit()).foregroundStyle(color)
            Text(label).font(.system(size: 7, weight: .heavy)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DividendSignalRow: View {
    let item: ConsensusItem
    let icon: String
    let tint: Color
    let signal: String

    var body: some View {
        HStack(spacing: 12) {
            CompanyMonogram(name: item.company, tint: tint)
            VStack(alignment: .leading, spacing: 5) {
                Text(displayCompanyName(item.company))
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                HStack(spacing: 7) {
                    Label(signal, systemImage: icon)
                        .foregroundStyle(tint)
                    Text("·")
                    Text("\(item.holders) fondos")
                }
                .font(.caption.bold())
            }
            Spacer()
            ScorePill(score: item.opportunityScore, maximum: item.opportunityScoreMaximum ?? 100)
            Image(systemName: "chevron.right")
                .font(.caption2.bold())
                .foregroundStyle(.tertiary)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 11)
        .contentShape(Rectangle())
    }
}

func displayCompanyName(_ value: String) -> String {
    guard value == value.uppercased() else { return value }
    return value.lowercased().capitalized
}

private struct CompanyMonogram: View {
    let name: String
    let tint: Color

    var body: some View {
        Text(initials)
            .font(.system(size: 12, weight: .heavy, design: .rounded))
            .foregroundStyle(tint)
            .frame(width: 38, height: 38)
            .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
            .accessibilityHidden(true)
    }

    private var initials: String {
        let words = name.split(separator: " ").prefix(2)
        return words.compactMap(\.first).map(String.init).joined().uppercased()
    }
}

private struct ScorePill: View {
    let score: Int?
    let maximum: Int

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "sparkles")
            Text(score.map(String.init) ?? "—").monospacedDigit()
        }
        .font(.caption.bold())
        .foregroundStyle(color)
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(color.opacity(0.11), in: Capsule())
        .accessibilityLabel(score.map { "Score \($0) sobre \(maximum)" } ?? "Score pendiente")
    }

    private var color: Color {
        guard let score else { return .secondary }
        if score >= 75 { return WhaleTheme.positive }
        if score >= 55 { return WhaleTheme.accent }
        return WhaleTheme.warning
    }
}

enum WhaleTheme {
    static let navy = Color(red: 0.055, green: 0.105, blue: 0.17)
    static let accent = Color(red: 0.04, green: 0.58, blue: 0.52)
    static let mint = Color(red: 0.45, green: 0.94, blue: 0.76)
    static let background = Color(uiColor: .systemGroupedBackground)
    static let panel = Color(uiColor: .secondarySystemGroupedBackground)
    static let positive = Color(red: 0.05, green: 0.62, blue: 0.38)
    static let info = Color(red: 0.12, green: 0.48, blue: 0.86)
    static let warning = Color(red: 0.91, green: 0.58, blue: 0.10)
    static let negative = Color(red: 0.84, green: 0.22, blue: 0.25)
}

extension View {
    func whalePanel() -> some View {
        background(WhaleTheme.panel, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.primary.opacity(0.07)))
    }
}

struct WhaleHeader: View {
    let eyebrow: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(eyebrow).font(.system(size: 10, weight: .bold)).tracking(1.1).foregroundStyle(.white.opacity(0.65))
            Text(title).font(.title2.bold()).foregroundStyle(.white)
            Text(subtitle).font(.caption).foregroundStyle(.white.opacity(0.7))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .background(WhaleTheme.navy, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(alignment: .topTrailing) {
            Image(systemName: "chart.bar.xaxis")
                .font(.system(size: 34)).foregroundStyle(WhaleTheme.accent.opacity(0.8)).padding(18)
        }
    }
}

struct SectionTitle: View {
    let title: String
    let detail: String
    init(_ title: String, detail: String) { self.title = title; self.detail = detail }
    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.headline)
            Spacer()
            Text(detail).font(.caption).foregroundStyle(.secondary)
        }
    }
}

private struct HoldingTableHeader: View {
    var body: some View {
        HStack {
            Text("POSICIÓN").frame(maxWidth: .infinity, alignment: .leading)
            Text("VALOR").frame(width: 70, alignment: .trailing)
            Text("PESO").frame(width: 52, alignment: .trailing)
        }
        .font(.system(size: 9, weight: .bold)).foregroundStyle(.secondary)
        .padding(.horizontal, 12).padding(.vertical, 9)
        .background(WhaleTheme.navy.opacity(0.06))
    }
}

private struct HoldingSummaryRow: View {
    let rank: Int
    let holding: Holding
    let dividendYield: Double?
    let peRatio: Double?
    var body: some View {
        HStack(spacing: 10) {
            Text("\(rank)").font(.caption.bold()).foregroundStyle(.secondary).frame(width: 20)
            VStack(alignment: .leading, spacing: 5) {
                Text(holding.company).font(.subheadline.weight(.semibold)).lineLimit(1)
                HStack(spacing: 7) {
                    if let dividendYield {
                        Label(dividendYield.formatted(.number.precision(.fractionLength(1))) + "%", systemImage: "dollarsign.circle.fill")
                            .foregroundStyle(dividendYield > 4 ? WhaleTheme.positive : .secondary)
                    }
                    if let peRatio {
                        Text("PER " + peRatio.formatted(.number.precision(.fractionLength(1))) + "x")
                    }
                }
                .font(.caption2.bold().monospacedDigit())
                GeometryReader { proxy in
                    Capsule().fill(WhaleTheme.accent.opacity(0.14))
                        .overlay(alignment: .leading) {
                            Capsule().fill(WhaleTheme.accent)
                                .frame(width: proxy.size.width * min(holding.weight / 30, 1))
                        }
                }.frame(height: 3)
            }
            Text(compactMoney(holding.value)).font(.caption.monospacedDigit()).frame(width: 70, alignment: .trailing)
            Text(holding.weight.formatted(.number.precision(.fractionLength(1))) + "%")
                .font(.caption.bold().monospacedDigit()).foregroundStyle(WhaleTheme.accent)
                .frame(width: 52, alignment: .trailing)
        }
        .padding(.horizontal, 12).padding(.vertical, 11)
    }
}

private struct ActivityLink: View {
    let title: String
    let action: MovementAction
    let color: Color
    let movements: [Movement]
    let quarter: String
    let snapshot: AppSnapshot

    private var items: [Movement] { movements.filter { $0.action == action } }
    private var companies: [ActivityCompanySummary] { ActivityCompanySummary.group(items) }

    var body: some View {
        NavigationLink {
            QuarterlyActivityView(title: title, action: action, items: companies, quarter: quarter, snapshot: snapshot)
        } label: {
            VStack(alignment: .leading, spacing: 5) {
                HStack {
                    Circle().fill(color).frame(width: 7, height: 7)
                    Spacer()
                    Image(systemName: "chevron.right").font(.system(size: 8, weight: .bold)).foregroundStyle(.tertiary)
                }
                Text("\(companies.count)").font(.title3.bold().monospacedDigit()).foregroundStyle(.primary)
                Text(title).font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading).padding(10).whalePanel()
        }
        .buttonStyle(.plain)
    }
}

private struct QuarterlyActivityView: View {
    let title: String
    let action: MovementAction
    let items: [ActivityCompanySummary]
    let quarter: String
    let snapshot: AppSnapshot

    var body: some View {
        Group {
            if items.isEmpty {
                ContentUnavailableView(
                    "Sin posiciones \(title.lowercased())",
                    systemImage: "tray",
                    description: Text("No se registraron movimientos de este tipo en \(quarter).")
                )
            } else {
                List(items) { item in
                    NavigationLink {
                        CompanyFinancialOverviewView(
                            companyName: item.company,
                            profile: snapshot.companyProfiles.first { $0.cusip == item.cusip },
                            reports: snapshot.companyReports.filter { $0.cusip == item.cusip },
                            holdings: snapshot.holdings.filter { $0.cusip == item.cusip }
                        )
                    } label: { VStack(alignment: .leading, spacing: 8) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(item.company).font(.headline).lineLimit(2)
                            Spacer()
                            if let change = item.changePercent {
                                Text(change.formatted(.number.sign(strategy: .always()).precision(.fractionLength(1))) + "%")
                                    .font(.subheadline.bold().monospacedDigit())
                                    .foregroundStyle(actionColor)
                            }
                        }
                        HStack {
                            Text(item.investors)
                            Spacer()
                            Text("Actual " + item.shares.formatted(.number.notation(.compactName)))
                        }
                        .font(.caption).foregroundStyle(.secondary)
                        HStack(spacing: 0) {
                            ComparisonValue(label: "ANTERIOR", value: item.previousShares)
                            Image(systemName: "arrow.right").font(.caption2).foregroundStyle(.tertiary).padding(.horizontal, 8)
                            ComparisonValue(label: "ACTUAL", value: item.shares)
                            Spacer()
                            ComparisonValue(label: "DIFERENCIA", value: item.shareDifference, signed: true)
                        }
                        .padding(.top, 3)
                    }}
                    .padding(.vertical, 5)
                    .listRowBackground(WhaleTheme.panel)
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
                .background(WhaleTheme.background)
            }
        }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .top) {
            HStack {
                Text("PERIODO REPORTADO").font(.system(size: 9, weight: .bold)).tracking(0.8)
                Spacer()
                Text(quarter).font(.caption.bold())
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 16).padding(.vertical, 9)
            .background(.bar)
        }
    }

    private var actionColor: Color {
        switch action {
        case .new: WhaleTheme.positive
        case .increased: WhaleTheme.info
        case .reduced: WhaleTheme.warning
        case .sold: WhaleTheme.negative
        case .unchanged: .secondary
        }
    }
}

private struct ActivityCompanySummary: Identifiable {
    let id: String
    let company: String
    let cusip: String?
    let investors: String
    let shares: Double
    let previousShares: Double
    let changePercent: Double?

    static func group(_ movements: [Movement]) -> [ActivityCompanySummary] {
        let grouped = Dictionary(grouping: movements) { movement in
            movement.company
                .folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
                .split(whereSeparator: { $0.isWhitespace })
                .joined(separator: " ")
                .uppercased()
        }

        return grouped.map { key, rows in
            let totalShares = rows.reduce(0) { $0 + $1.shares }
            let previousShares = rows.reduce(0) { $0 + ($1.previousShares ?? inferredPreviousShares(for: $1)) }
            let managers = Array(Set(rows.map(\.investorName))).sorted().joined(separator: " · ")
            let weightedChange: Double? = previousShares > 0
                ? (totalShares / previousShares - 1) * 100
                : nil
            return ActivityCompanySummary(
                id: key,
                company: rows.first?.company ?? key,
                cusip: rows.first?.cusip,
                investors: managers,
                shares: totalShares,
                previousShares: previousShares,
                changePercent: weightedChange
            )
        }
        .sorted { $0.shares > $1.shares }
    }

    var shareDifference: Double { shares - previousShares }

    private static func inferredPreviousShares(for movement: Movement) -> Double {
        guard let change = movement.changePercent else { return 0 }
        if change == -100 { return movement.shares }
        let ratio = 1 + change / 100
        return ratio > 0 ? movement.shares / ratio : 0
    }
}

private struct ComparisonValue: View {
    let label: String
    let value: Double
    var signed = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.system(size: 8, weight: .bold)).foregroundStyle(.tertiary)
            Text(formattedValue)
                .font(.caption.bold().monospacedDigit())
                .foregroundStyle(signed ? differenceColor : .primary)
        }
    }

    private var formattedValue: String {
        let base = abs(value).formatted(.number.notation(.compactName).precision(.fractionLength(0...1)))
        guard signed else { return base }
        if value > 0 { return "+" + base }
        if value < 0 { return "−" + base }
        return base
    }

    private var differenceColor: Color {
        if value > 0 { return WhaleTheme.positive }
        if value < 0 { return WhaleTheme.negative }
        return .secondary
    }
}

func compactMoney(_ value: Double) -> String {
    if value >= 1_000_000_000 { return String(format: "$%.1fB", value / 1_000_000_000) }
    if value >= 1_000_000 { return String(format: "$%.1fM", value / 1_000_000) }
    if value >= 1_000 { return String(format: "$%.1fK", value / 1_000) }
    return value.formatted(.currency(code: "USD"))
}

struct OpportunityCard: View {
    let item: Opportunity
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading) {
                    Text(item.company).font(.headline)
                    Text(item.sector).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Text("\(item.franScore)").font(.title2.bold()).foregroundStyle(item.franScore >= 80 ? .green : .orange)
                Text("/100").font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Label(item.yield.formatted(.number.precision(.fractionLength(1))) + "%", systemImage: "percent")
                Spacer()
                Text(item.pe.map { "PER \($0.formatted(.number.precision(.fractionLength(1))))x" } ?? "PER —")
                Spacer()
                Text("\(item.gurusBuying) comprando")
            }.font(.caption)
        }
        .padding().background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
    }
}
