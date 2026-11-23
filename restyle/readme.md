# Restyle (Android)

Turn any photo into a styled post. Kotlin + Jetpack Compose + Material 3, built from the
"Restyle — Android app flow" design (Login → OTP → Templates → Add photo → Result).

## Status: Phase 1 (fully working UI, fake backend)

| Area | Phase 1 | Phase 2 |
|---|---|---|
| Login | **Continue with Google** via Credential Manager (demo user until `google.webClientId` is set); phone OTP as fallback (`FakeAuthService`, any 6-digit code) | Verify the Google ID token on your backend / Firebase Auth |
| Image generation | `FakeImageGenerator`: crop + colour filter per style | Real image-gen API behind your backend |
| Credits | Start at **0**; tapping a style you can't afford opens **Subscribe**. Plans (placeholder prices in `data/Models.kt`) grant credits without payment | Google Play Billing subscriptions, server-side balance |
| Creations | Saved in app storage, listed in "My creations" | Optional cloud sync |

The fakes sit behind `AuthService` and `ImageGenerator` in
`app/src/main/java/com/appjs/restyle/data/Services.kt`, so swapping them doesn't touch the UI.

## Enabling real Google Sign-In

1. In Google Cloud Console (or your Firebase project) create an OAuth client of type **Android**:
   package `com.appjs.restyle`, plus the SHA-1 of your signing key. Debug key SHA-1 on this Mac:
   `DC:97:72:A5:60:24:24:A7:79:D2:C0:DC:D7:A8:B0:81:7B:4B:19:EA`
2. Create an OAuth client of type **Web application** and copy its client ID.
3. Add it to `local.properties`: `google.webClientId=1234-abc.apps.googleusercontent.com`, then rebuild.

## Build & run

Requires the Android SDK (`~/Library/Android/sdk`) and a JDK 17+ (Android Studio's bundled JBR works).

```sh
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Or open the folder in Android Studio and press Run.

- minSdk 29 (Android 10), target/compile SDK 37
- AGP 9.4.1, Gradle 9.8.2, Kotlin 2.4.21, Compose BOM 2026.09.00

## Layout

```
app/src/main/java/com/appjs/restyle/
  MainActivity.kt          navigation between screens
  AppViewModel.kt          app state (session, credits, draft, result)
  data/                    models, templates, fake services, local storage
  ui/theme/                colours, Inter type, stroke icons from the design
  ui/components/           buttons, pills, credits chip, hills illustration
  ui/screens/              Auth (Login, OTP), Home (Templates, My creations, Profile),
                           Create (Add photo, Result)
```
