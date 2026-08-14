import SwiftUI
import DividendIntelligenceKit

@main
struct DividendIntelligenceApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .task { await model.refresh() }
        }
    }
}

