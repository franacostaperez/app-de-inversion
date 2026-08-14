import SwiftUI
import DividendIntelligenceKit

struct RootView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        Group {
            if let snapshot = model.snapshot {
                TabView {
                    NavigationStack { DashboardView(snapshot: snapshot) }
                        .tabItem { Label("Inicio", systemImage: "house.fill") }
                    NavigationStack { OpportunitiesView(items: snapshot.opportunities) }
                        .tabItem { Label("Oportunidades", systemImage: "sparkles") }
                    NavigationStack { SmartMoneyView(snapshot: snapshot) }
                        .tabItem { Label("Smart Money", systemImage: "chart.line.uptrend.xyaxis") }
                    NavigationStack { CompaniesView(items: snapshot.opportunities) }
                        .tabItem { Label("Empresas", systemImage: "building.2") }
                    NavigationStack { PortfolioPlaceholderView() }
                        .tabItem { Label("Cartera", systemImage: "briefcase") }
                }
                .tint(.mint)
            } else if model.isLoading {
                ProgressView("Cargando inteligencia…")
            } else {
                ContentUnavailableView("Sin datos", systemImage: "externaldrive.badge.exclamationmark", description: Text(model.errorMessage ?? "Inténtalo de nuevo"))
            }
        }
    }
}

private struct DashboardView: View {
    let snapshot: AppSnapshot

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if snapshot.isDemo {
                    Label("Datos de demostración · \(snapshot.asOfQuarter)", systemImage: "info.circle")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text("Las mejores señales de hoy")
                    .font(.title.bold())
                ForEach(snapshot.opportunities.prefix(3)) { item in
                    OpportunityCard(item: item)
                }
                GroupBox("Pulso Smart Money") {
                    HStack {
                        Metric(value: "\(snapshot.investors.count)", label: "Gestores")
                        Spacer()
                        Metric(value: "\(snapshot.movements.filter { $0.action == .increased || $0.action == .new }.count)", label: "Compras")
                        Spacer()
                        Metric(value: "\(snapshot.consensus.count)", label: "Consensos")
                    }.padding(.vertical, 6)
                }
            }.padding()
        }
        .navigationTitle("Dividend Intelligence")
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
                    Text(item.ticker).font(.headline)
                    Text(item.company).font(.caption).foregroundStyle(.secondary)
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

