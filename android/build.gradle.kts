plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.android.library) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.compose.compiler) apply false
    alias(libs.plugins.detekt) apply false
}

subprojects {
    apply(plugin = "io.gitlab.arturbosch.detekt")

    configure<io.gitlab.arturbosch.detekt.extensions.DetektExtension> {
        buildUponDefaultConfig = true
        allRules = false
        config.setFrom(files("$rootDir/detekt.yml"))
    }

    tasks.withType<io.gitlab.arturbosch.detekt.Detekt>().configureEach {
        reports {
            html.required.set(true)
            xml.required.set(false)
            txt.required.set(false)
            sarif.required.set(false)
        }
    }
}

tasks.register("qualityCheck") {
    group = "verification"
    description = "Runs Android Lint, Detekt, unit/UI tests for core & app, and assembleDebug."
    dependsOn(
        ":core:lintDebug",
        ":app:lintDebug",
        ":core:detekt",
        ":app:detekt",
        ":core:testDebugUnitTest",
        ":app:testDebugUnitTest",
        ":app:assembleDebug"
    )
}

