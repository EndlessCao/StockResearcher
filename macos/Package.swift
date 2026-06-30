// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "StockResearcher",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "StockResearcher", targets: ["StockResearcher"])
    ],
    targets: [
        .executableTarget(
            name: "StockResearcher",
            path: "Sources/StockResearcherApp"
        ),
        .testTarget(
            name: "StockResearcherTests",
            dependencies: ["StockResearcher"],
            path: "Tests/StockResearcherTests"
        )
    ]
)
