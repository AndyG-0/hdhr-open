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
    dependencies: [],
    targets: [
        .target(
            name: "HDHROpenKit",
            dependencies: [],
            path: "Sources/HDHROpenKit"
        ),
        .testTarget(
            name: "HDHROpenKitTests",
            dependencies: ["HDHROpenKit"],
            path: "Tests/HDHROpenKitTests"
        )
    ]
)
