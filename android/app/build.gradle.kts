// The 24bit7 phone app (Ben, 24 Nov 2026): open it and 24bit7 can copy playlists to the phone over WiFi.
// Its version is 24bit7's own, read from engine.py, so the APK on a release matches the release.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val appVersion: String = Regex("""^VERSION\s*=\s*"([\d.]+)"""", RegexOption.MULTILINE)
    .find(rootProject.file("../engine.py").readText())?.groupValues?.get(1) ?: "0.0.0"
val appCode: Int = appVersion.split(".").map { it.toIntOrNull() ?: 0 }.let { (it + listOf(0, 0, 0)).take(3) }
    .let { (a, b, c) -> a * 10000 + b * 100 + c }

android {
    namespace = "io.github.twentyfourbit7.transfer"
    compileSdk = 35
    defaultConfig {
        applicationId = "io.github.twentyfourbit7.transfer"
        minSdk = 30
        targetSdk = 35
        versionCode = appCode
        versionName = appVersion
    }
    // One key for every release, so each new version installs over the last (kept as GitHub secrets; a build
    // without them, on a fork or a PC, is signed with the debug key and won't install over a release).
    val keystore = System.getenv("ANDROID_KEYSTORE_FILE")
    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = file(keystore)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = "24bit7"
                keyPassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
            }
        }
    }
    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = if (keystore != null) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    lint { checkReleaseBuilds = false }
}
