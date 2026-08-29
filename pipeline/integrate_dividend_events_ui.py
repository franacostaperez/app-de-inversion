#!/usr/bin/env python3
"""One-time/idempotent source codemod for the dividend events UI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "Sources/DividendIntelligenceKit/Models.swift"
ROOT_VIEW = ROOT / "App/RootView.swift"

DIVIDEND_MODEL = r'''
public struct DividendEvent: Codable, Identifiable, Sendable {
    public var id: String {
        let eventDate = paymentDate ?? exDividendDate ?? recordDate ?? declarationDate ?? "undated"
        return "\(ticker)-\(eventDate)-\(amount)-\(source)"
    }

    public let ticker: String
    public let company: String
    public let amount: Double
    public let currency: String
    public let declarationDate: String?
    public let exDividendDate: String?
    public let recordDate: String?
    public let paymentDate: String?
    public let status: String
    public let source: String
    public let sourceURL: URL?
    public let sourcePriority: Int
    public let confidence: Int
    public let estimatedReason: String?

    public var isEstimated: Bool { status.lowercased() == "estimated" }
}

'''

EVENTS_UI = r'''
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
                                    DividendEventCard(event: event)
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
                DividendSummaryMetric(value: "\(snapshot.dividendEvents.count)", label: "Eventos", tint: WhaleTheme.info)
            }
        }
        .padding(16)
        .whalePanel()
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
                    Text((event.isEstimated ? "≈ " : "") + event.amount.formatted(.number.precision(.fractionLength(2...4))))
                        .font(.title3.bold().monospacedDigit())
                    Text(event.currency + " / acción")
                        .font(.caption2).foregroundStyle(.secondary)
                }
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

'''


def update_models() -> bool:
    text = MODELS.read_text()
    original = text
    if "public let dividendEvents: [DividendEvent]" not in text:
        text = text.replace(
            "    public let fundPortfolios: [FundPortfolio]\n",
            "    public let fundPortfolios: [FundPortfolio]\n    public let dividendEvents: [DividendEvent]\n",
            1,
        )
        text = text.replace(
            "case generatedAt, asOfQuarter, isDemo, opportunities, investors, consensus, movements, holdings, filings, filingUpdates, companyProfiles, companyReports, fundPortfolios",
            "case generatedAt, asOfQuarter, isDemo, opportunities, investors, consensus, movements, holdings, filings, filingUpdates, companyProfiles, companyReports, fundPortfolios, dividendEvents",
            1,
        )
        text = text.replace(
            "        fundPortfolios = try container.decodeIfPresent([FundPortfolio].self, forKey: .fundPortfolios) ?? []\n",
            "        fundPortfolios = try container.decodeIfPresent([FundPortfolio].self, forKey: .fundPortfolios) ?? []\n        dividendEvents = try container.decodeIfPresent([DividendEvent].self, forKey: .dividendEvents) ?? []\n",
            1,
        )
    if "public struct DividendEvent:" not in text:
        marker = "/// Complementary disclosures, kept separate from USD/share-based SEC 13Fs.\n"
        if marker not in text:
            raise RuntimeError("Models.swift insertion marker not found")
        text = text.replace(marker, DIVIDEND_MODEL + marker, 1)
    if text != original:
        MODELS.write_text(text)
        return True
    return False


def update_root_view() -> bool:
    text = ROOT_VIEW.read_text()
    original = text
    text = text.replace(
        "NavigationStack { UpdatesView(snapshot: snapshot) }\n                .tabItem { Label(\"Eventos\", systemImage: \"calendar.badge.clock\") }",
        "NavigationStack { EventsHubView(snapshot: snapshot) }\n                .tabItem { Label(\"Eventos\", systemImage: \"calendar.badge.clock\") }",
        1,
    )
    if "private struct EventsHubView:" not in text:
        marker = "private struct DividendLoadingView: View {\n"
        if marker not in text:
            raise RuntimeError("RootView.swift insertion marker not found")
        text = text.replace(marker, EVENTS_UI + marker, 1)
    if text != original:
        ROOT_VIEW.write_text(text)
        return True
    return False


def main() -> None:
    changed = []
    if update_models():
        changed.append(str(MODELS.relative_to(ROOT)))
    if update_root_view():
        changed.append(str(ROOT_VIEW.relative_to(ROOT)))
    print("Updated: " + (", ".join(changed) if changed else "nothing (already integrated)"))


if __name__ == "__main__":
    main()
