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
                .tint(.mint)
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
            VStack(alignment: .leading, spacing: 20) {
                Text("Berkshire Hathaway")
                    .font(.title.bold())
                Text("13F · \(snapshot.asOfQuarter)")
                    .font(.subheadline).foregroundStyle(.secondary)

                GroupBox {
                    HStack {
                        Metric(value: "\(snapshot.holdings.count)", label: "Posiciones")
                        Spacer()
                        Metric(value: compactUSD(snapshot.investors.first?.portfolioValue ?? 0), label: "Valor 13F")
                        Spacer()
                        Metric(value: "\(snapshot.movements.count)", label: "Cambios")
                    }.padding(.vertical, 6)
                }

                Text("Principales posiciones").font(.headline)
                VStack(spacing: 0) {
                    ForEach(Array(snapshot.holdings.prefix(5).enumerated()), id: \.element.id) { index, holding in
                        HStack(spacing: 12) {
                            Text("\(index + 1)").foregroundStyle(.secondary).frame(width: 18)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(holding.company).lineLimit(1)
                                Text("Periodo \(snapshot.asOfQuarter)")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(holding.weight.formatted(.number.precision(.fractionLength(1))) + "%").bold()
                        }
                        .padding(.vertical, 11)
                        if index < min(4, snapshot.holdings.count - 1) { Divider() }
                    }
                }
                .padding(.horizontal)
                .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 16))
            }.padding()
        }
        .navigationTitle("Dividend Intelligence")
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
        VStack { Text(value).font(.title2.bold()); Text(label).font(.caption).foregroundStyle(.secondary) }
    }
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
