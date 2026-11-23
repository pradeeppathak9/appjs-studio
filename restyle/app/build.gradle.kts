import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// Google Sign-In: put your OAuth *Web* client ID in local.properties as
//   google.webClientId=1234-abc.apps.googleusercontent.com
// Leave it empty to use the demo sign-in.
val localProps = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
val googleWebClientId: String = localProps.getProperty("google.webClientId", "")

// AppJs Studio backend: the app "restyle-ai". The emulator reaches the Mac's localhost as 10.0.2.2.
//   appjs.baseUrl=http://10.0.2.2:8010
//   appjs.appKey=cak_...
val appjsBaseUrl: String = localProps.getProperty("appjs.baseUrl", "http://10.0.2.2:8010").trimEnd('/')
val appjsAppKey: String = localProps.getProperty("appjs.appKey", "")

android {
    namespace = "com.appjs.restyle"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.appjs.restyle"
        minSdk = 29
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "GOOGLE_WEB_CLIENT_ID", "\"$googleWebClientId\"")
        buildConfigField("String", "APPJS_BASE_URL", "\"$appjsBaseUrl\"")
        buildConfigField("String", "APPJS_APP_KEY", "\"$appjsAppKey\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.credentials)
    implementation(libs.androidx.credentials.play.services)
    implementation(libs.googleid)
    implementation(libs.okhttp)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
