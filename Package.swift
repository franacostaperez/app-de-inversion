// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "DividendIntelligence",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "DividendIntelligenceKit", targets: ["DividendIntelligenceKit"]),
        .executable(name: "DividendIntelligenceApp", targets: ["DividendIntelligenceApp"])
    ],
    targets: [
        .target(
            name: "DividendIntelligenceKit",
            resources: [.process("Resources")]
        ),
        .executableTarget(
            name: "DividendIntelligenceApp",
            dependencies: ["DividendIntelligenceKit"],
            path: "App"
        ),
        .testTarget(
            name: "DividendIntelligenceKitTests",
            dependencies: ["DividendIntelligenceKit"]
        )
    ]
)

