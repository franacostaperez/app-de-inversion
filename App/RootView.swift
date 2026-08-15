import SwiftUI
#if canImport(DividendIntelligenceKit)
import DividendIntelligenceKit
#endif

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if let snapshot = model.snapshot {
                TabView {
                    NavigationStack { DashboardView(snapshot: snapshot) }
                        .tabItem { Label("Inicio", systemImage: "house.fill") }
                    NavigationStack { FilingsView(items: snapshot.filings) }
                        .tabItem { Label("13F", systemImage: "doc.text.magnifyingglass") }
                    NavigationStack { SmartMoneyView(snapshot: snapshot) }
                        .tabItem { Label("Smart Money", systemImage: "chart.line.uptrend.xyaxis") }
                    NavigationStack { CompaniesView(snapshot: snapshot) }
                        .tabItem { Label("Empresas", systemImage: "building.2") }
                    NavigationStack { PortfolioPlaceholderView() }
                        .tabItem { Label("Cartera", systemImage: "briefcase") }
                }
                .tint(WhaleTheme.accent)
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

private struct DashboardView: View {
    let snapshot: AppSnapshot

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                WhaleHeader(
                    eyebrow: "GESTOR INSTITUCIONAL",
                    title: snapshot.investors.first?.name ?? "Berkshire Hathaway",
                    subtitle: "Cartera 13F · periodo reportado \(snapshot.asOfQuarter)"
                )

                HStack(spacing: 8) {
                    Metric(value: compactUSD(snapshot.investors.first?.portfolioValue ?? 0), label: "Valor cartera")
                    Metric(value: "\(snapshot.holdings.count)", label: "Posiciones")
                    Metric(value: "\(snapshot.movements.count)", label: "Movimientos")
                }

                SectionTitle("Principales posiciones", detail: "Por peso en cartera")
                VStack(spacing: 0) {
                    HoldingTableHeader()
                    ForEach(Array(snapshot.holdings.prefix(10).enumerated()), id: \.element.id) { index, holding in
                        HoldingSummaryRow(rank: index + 1, holding: holding)
                        if index < min(9, snapshot.holdings.count - 1) { Divider().padding(.leading, 42) }
                    }
                }
                .whalePanel()

                if !snapshot.movements.isEmpty {
                    SectionTitle("Actividad del trimestre", detail: snapshot.asOfQuarter)
                    HStack(spacing: 8) {
                        ActivityMetric(title: "Nuevas", count: count(.new), color: WhaleTheme.positive)
                        ActivityMetric(title: "Aumentadas", count: count(.increased), color: WhaleTheme.info)
                        ActivityMetric(title: "Reducidas", count: count(.reduced), color: WhaleTheme.warning)
                        ActivityMetric(title: "Vendidas", count: count(.sold), color: WhaleTheme.negative)
                    }
                }
            }
            .padding(16)
        }
        .background(WhaleTheme.background.ignoresSafeArea())
        .navigationTitle("Resumen 13F")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func count(_ action: MovementAction) -> Int {
        snapshot.movements.filter { $0.action == action }.count
    }

    private func compactUSD(_ value: Double) -> String {
        if value >= 1_000_000_000 { return String(format: "$%.0fB", value / 1_000_000_000) }
        if value >= 1_000_000 { return String(format: "$%.0fM", value / 1_000_000) }
        return value.formatted(.currency(code: "USD"))
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

private struct ActivityMetric: View {
    let title: String
    let count: Int
    let color: Color
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text("\(count)").font(.title3.bold().monospacedDigit())
            Text(title).font(.system(size: 9, weight: .medium)).foregroundStyle(.secondary).lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(10).whalePanel()
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
