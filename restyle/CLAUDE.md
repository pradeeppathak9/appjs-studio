# restyle (Android)

Kotlin + Jetpack Compose + Material 3 client for the AppJs Studio app `restyle-ai`: Login → OTP →
Templates → Add photo → Result, plus credits and subscribe. Lives in the appjs monorepo (`appjs/restyle/`).

**The readme's "Phase 1, fake backend" table is out of date.** `data/Api.kt` is a real client for
AppJs Studio's `/v1/app/*` (contract: `../studio/docs/APPS_API.md`). Check `Services.kt` for
which pieces still use fakes before assuming either way.

## Layout (`app/src/main/java/com/appjs/restyle/`)

- `MainActivity.kt` (navigation) · `AppViewModel.kt` (session, credits, draft, result)
- `data/`: `Api.kt` (HTTP client), `Services.kt` (`AuthService` / `ImageGenerator` interfaces + fakes),
  `GoogleAuth.kt` (Credential Manager), `LocalStore.kt`, `Models.kt` (plans, placeholder prices)
- `ui/screens/`: `AuthScreens`, `HomeScreen`, `CreateScreens`, `SubscribeScreen` · `ui/components/`, `ui/theme/`

## Config: `local.properties` (not in VCS, holds secrets)

```properties
google.webClientId=...apps.googleusercontent.com
appjs.baseUrl=http://10.0.2.2:8010     # default; the emulator's route to appjs-studio on the host
appjs.appKey=cak_...                   # blank → Api throws "no_app_key"
```

## Commands

```bash
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
./gradlew assembleDebug                                    # the only check; there are no unit tests
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

To run against a real backend, start `../studio` on :8010 first.

## Rules

- Keep the UI behind the `data/` interfaces. Backend changes shouldn't touch screens.
- If the API shape has to change, change appjs-studio (routes + `APPS_API.md`) first, then this client.
- Toolchain: minSdk 29, compile/target 37, AGP 9.4.1, Gradle 9.8.2, Kotlin 2.4.21. Don't bump these
  as a side effect.
