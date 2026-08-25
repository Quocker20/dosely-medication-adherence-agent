plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.kapt")
    id("com.google.dagger.hilt.android")
    id("com.google.gms.google-services")
}

android {
    namespace = "com.remindrx.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.remindrx.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0-mvp"
    }

    buildTypes {
        debug {
            buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000/api/v1/\"")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("String", "API_BASE_URL", "\"https://remindrx.duckdns.org/api/v1/\"")
        }
        create("demo") {
            // Debug-signed build pointed at the public VPS backend, for uploading
            // as a direct-download APK so people can try the app — see
            // docs/android-app-testing.md. Domain is a DuckDNS record pointed at the
            // FossVPS; only needs updating here if the VPS itself changes.
            initWith(getByName("debug"))
            matchingFallbacks += listOf("debug")
            buildConfigField("String", "API_BASE_URL", "\"https://remindrx.duckdns.org/api/v1/\"")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.06.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.1")
    implementation("androidx.navigation:navigation-compose:2.7.7")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.4")
    implementation(platform("com.google.firebase:firebase-bom:34.18.0"))
    implementation("com.google.firebase:firebase-messaging")

    // Dependency injection — sẵn sàng cho khi ViewModel cần gọi backend thật.
    implementation("com.google.dagger:hilt-android:2.51.1")
    kapt("com.google.dagger:hilt-android-compiler:2.51.1")
    implementation("androidx.hilt:hilt-navigation-compose:1.2.0")

    // Networking — trỏ vào src/api/routes.py (/api/v1) khi apply base này.
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
