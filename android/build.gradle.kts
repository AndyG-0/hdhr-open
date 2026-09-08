plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.compose.compiler) apply false
}

tasks.register("qualityCheck") {
    group = "verification"
    description = "Runs Android Lint, unit/UI tests for core & app, and assembleDebug."
    dependsOn(
        ":core:lintDebug",
        ":app:lintDebug",
        ":core:testDebugUnitTest",
        ":app:testDebugUnitTest",
        ":app:assembleDebug"
    )
}

