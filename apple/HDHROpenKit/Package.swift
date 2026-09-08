// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "HDHROpenKit",
    platforms: [
        .iOS(.v17),
        .tvOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .library(
            name: "HDHROpenKit",
            targets: ["HDHROpenKit"]
        )
    ],
    dependencies: [
        .package(url: "https://github.com/nalexn/ViewInspector", from: "0.9.0")
    ],
    targets: [
        .target(
            name: "HDHROpenKit",
            dependencies: [],
            path: "Sources/HDHROpenKit"
        ),
        .testTarget(
            name: "HDHROpenKitTests",
            dependencies: [
                "HDHROpenKit",
                .product(name: "ViewInspector", package: "ViewInspector")
            ],
            path: "Tests/HDHROpenKitTests"
        )
    ]
)
