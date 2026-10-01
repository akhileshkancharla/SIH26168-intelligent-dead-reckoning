plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "org.sih26168.s1logger"
    compileSdk = 36
    buildToolsVersion = "35.0.0"

    defaultConfig {
        applicationId = "org.sih26168.s1logger"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0-spike"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "GIT_COMMIT", "\"${providers.environmentVariable("GIT_COMMIT").orElse("unavailable").get()}\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }

    testOptions {
        unitTests.isIncludeAndroidResources = false
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1") {
        // concurrent-futures-ktx 1.1.0's legacy POM pulls the pre-multiplatform
        // coroutines artifact; AndroidX Test already supplies core-jvm 1.7.1.
        exclude(group = "org.jetbrains.kotlinx", module = "kotlinx-coroutines-core")
    }
}

dependencyLocking {
    lockAllConfigurations()
}
