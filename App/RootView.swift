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
                ProgressView("Cargando inteligencia…")
            } else {
                ContentUnavailableView {
                    Label("Sin datos", systemImage: "icloud.slash")
                } description: {
                    Text(model.errorMessage ?? "Inténtalo de nuevo")
                } actions: {
                    Button("Reintentar") { Task { await model.refresh() } }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
    }
}

private struct FundTabs: View {
    let snapshot: AppSnapshot
    @State private var selectedInvestorID = ""

    private var selection: Binding<String> {
        Binding(
            get: {
                snapshot.investors.contains(where: { $0.id == selectedInvestorID })
                    ? selectedInvestorID
                    : snapshot.investors.first?.id ?? ""
            },
            set: { selectedInvestorID = $0 }
        )
    }

    var body: some View {
        TabView {
            NavigationStack { DashboardView(snapshot: snapshot, selectedInvestorID: selection) }
                .tabItem { Label("Inicio", systemImage: "house.fill") }
            NavigationStack { FilingsView(snapshot: snapshot, selectedInvestorID: selection) }
                .tabItem { Label("13F", systemImage: "doc.text.magnifyingglass") }
            NavigationStack { SmartMoneyView(snapshot: snapshot, selectedInvestorID: selection) }
                .tabItem { Label("Smart Money", systemImage: "chart.line.uptrend.xyaxis") }
            NavigationStack { FundsView(snapshot: snapshot, selectedInvestorID: selection) }
                .tabItem { Label("Fondos", systemImage: "building.columns.fill") }
            NavigationStack { UpdatesView(snapshot: snapshot) }
                .tabItem { Label("Novedades", systemImage: "sparkles") }
        }
        .tint(WhaleTheme.accent)
        .onAppear {
            if selectedInvestorID.isEmpty { selectedInvestorID = snapshot.investors.first?.id ?? "" }
        }
    }
}

private struct DashboardView: View {
    let snapshot: AppSnapshot
    @Binding var selectedInvestorID: String

    private var investor: Investor? {
        snapshot.investors.first(where: { $0.id == selectedInvestorID }) ?? snapshot.investors.first
    }
    private var holdings: [Holding] {
        snapshot.holdings.filter { $0.investorId == investor?.id }.sorted { $0.value > $1.value }
    }
    private var movements: [Movement] {
        snapshot.movements.filter { $0.investorId == investor?.id }
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                FundSelector(investors: snapshot.investors, selection: $selectedInvestorID)
                WhaleHeader(
                    eyebrow: "GESTOR INSTITUCIONAL",
                    title: investor?.name ?? "Gestor",
                    subtitle: "Cartera 13F · periodo reportado \(investor?.quarter ?? snapshot.asOfQuarter)"
                )

                HStack(spacing: 8) {
                    Metric(value: compactUSD(investor?.portfolioValue ?? 0), label: "Valor cartera")
                    Metric(value: "\(holdings.count)", label: "Posiciones")
                    Metric(value: "\(movements.count)", label: "Movimientos")
                }

                SectionTitle("Principales posiciones", detail: "Por peso en cartera")
                VStack(spacing: 0) {
                    HoldingTableHeader()
                    ForEach(Array(holdings.prefix(10).enumerated()), id: \.element.id) { index, holding in
                        HoldingSummaryRow(rank: index + 1, holding: holding)
                        if index < min(9, holdings.count - 1) { Divider().padding(.leading, 42) }
                    }
                }
                .whalePanel()

                if !movements.isEmpty {
                    SectionTitle("Actividad del trimestre", detail: investor?.quarter ?? snapshot.asOfQuarter)
                    HStack(spacing: 8) {
                        ActivityLink(title: "Nuevas", action: .new, color: WhaleTheme.positive, movements: movements, quarter: investor?.quarter ?? snapshot.asOfQuarter)
                        ActivityLink(title: "Aumentadas", action: .increased, color: WhaleTheme.info, movements: movements, quarter: investor?.quarter ?? snapshot.asOfQuarter)
                        ActivityLink(title: "Reducidas", action: .reduced, color: WhaleTheme.warning, movements: movements, quarter: investor?.quarter ?? snapshot.asOfQuarter)
                        ActivityLink(title: "Vendidas", action: .sold, color: WhaleTheme.negative, movements: movements, quarter: investor?.quarter ?? snapshot.asOfQuarter)
                    }
                }
            }
            .padding(16)
        }
        .background(WhaleTheme.background.ignoresSafeArea())
        .navigationTitle("Resumen 13F")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func compactUSD(_ value: Double) -> String {
        if value >= 1_000_000_000 { return String(format: "$%.0fB", value / 1_000_000_000) }
        if value >= 1_000_000 { return String(format: "$%.0fM", value / 1_000_000) }
        return value.formatted(.currency(code: "USD"))
    }
}

struct FundSelector: View {
    let investors: [Investor]
    @Binding var selection: String

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(investors) { investor in
                    Button {
                        withAnimation(.snappy) { selection = investor.id }
                    } label: {
                        HStack(spacing: 7) {
                            Image(systemName: selection == investor.id ? "checkmark.circle.fill" : "building.columns")
                            Text(investor.name).lineLimit(1)
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(selection == investor.id ? .white : .primary)
                        .padding(.horizontal, 13).padding(.vertical, 9)
                        .background(selection == investor.id ? WhaleTheme.accent : WhaleTheme.panel, in: Capsule())
                        .overlay(Capsule().stroke(selection == investor.id ? .clear : .primary.opacity(0.08)))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .contentMargins(.horizontal, 1, for: .scrollContent)
        .accessibilityLabel("Seleccionar fondo")
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

enum WhaleTheme {
    static let navy = Color(red: 0.055, green: 0.105, blue: 0.17)
    static let accent = Color(red: 0.04, green: 0.58, blue: 0.52)
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
    var body: some View {
        HStack(spacing: 10) {
            Text("\(rank)").font(.caption.bold()).foregroundStyle(.secondary).frame(width: 20)
            VStack(alignment: .leading, spacing: 5) {
                Text(holding.company).font(.subheadline.weight(.semibold)).lineLimit(1)
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

    private var items: [Movement] { movements.filter { $0.action == action } }
    private var companies: [ActivityCompanySummary] { ActivityCompanySummary.group(items) }

    var body: some View {
        NavigationLink {
            QuarterlyActivityView(title: title, action: action, items: companies, quarter: quarter)
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
                    VStack(alignment: .leading, spacing: 8) {
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
                    }
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
