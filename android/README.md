# Dosely — Android app (MVP kết nối FastAPI)

Native Android (Kotlin + Jetpack Compose, Material3) client, generated from the
design mockup. Covers all 8 core
screens. Dashboard, lịch sinh hoạt, đơn thuốc, thao tác cữ thuốc, khảo sát và
SOS đã gọi FastAPI backend trong `src/` qua Retrofit.

## Status

Built, installed, and verified on an emulator. Luồng `TAKEN/LATE/SKIPPED` dùng
`Idempotency-Key`; khảo sát `SEVERE` và SOS tạo Red Alert trên portal bác sĩ.

## Local setup (already done on this machine)

- **SDK**: `D:\setup\Android\SDK` (pre-existing Android Studio install at
  `D:\setup\Android\Android Studio`). Recorded in `local.properties`, which is
  gitignored — teammates need their own.
- **Env vars** (set user-level via `setx`): `ANDROID_HOME`, `ANDROID_SDK_ROOT`
  pointing at the SDK, plus `ANDROID_AVD_HOME=D:\setup\Android\avd`.
- **Emulator**: AVD `Pixel_8_Pro` — Android 16 (API 36.1),
  `google_apis_playstore/x86_64`. Stored on D: to keep it off the nearly-full
  C: drive.
- **Gradle**: no Gradle was installed, so 8.7 was downloaded to
  `D:\setup\Android\tools\gradle-8.7` and used once to generate the wrapper.
  `GRADLE_USER_HOME` is `D:\setup\Android\gradle-home` (also on D: for space).

## Run it

Open `android/` in Android Studio and hit Run, or from the command line:

```bash
cd D:/Android/dosely-medication-adherence-agent/android && ./gradlew.bat installDebug
```

Start the emulator first — launch it detached, otherwise it gets killed when
the parent shell exits:

```bash
D:/setup/Android/SDK/emulator/emulator.exe -avd Pixel_8_Pro -gpu auto
```

Then launch the app:

```bash
D:/setup/Android/SDK/platform-tools/adb.exe shell am start -n com.dosely.app/.MainActivity
```

## What's here

```
app/src/main/java/com/dosely/app/
  DoselyApplication.kt        # @HiltAndroidApp entry point
  MainActivity.kt                # @AndroidEntryPoint, sets DoselyTheme + DoselyApp
  navigation/DoselyNavHost.kt  # 8 routes, bottom bar + SOS FAB visibility
  ui/theme/                      # Color/Type/Theme.kt — tokens match the mockup
  ui/components/Components.kt    # shared atoms: chips, buttons, bottom bar, SOS FAB
  ui/screens/                    # one file per screen
  ui/PatientViewModel.kt         # state dùng chung, gọi PatientRepository
  data/                          # domain models + mock fallback cho preview
  data/remote/                   # Retrofit API + DTO khớp Pydantic backend
  data/repository/               # remote repositories cho patient/routine
  di/                             # NetworkModule (OkHttp/Retrofit/Gson), RepositoryModule (Hilt bindings)
  core/state/UiState.kt          # generic Loading/Success/Error wrapper for future ViewModels
```

Screens: Login (6-digit PIN), compulsory first-login PIN change, Onboarding
(routine), Dashboard, medication list/detail (RAG mock), AI assistant with chat
history, Reminder (interruptive push), Health survey, SOS (hold-3s), Settings.

## Kết nối backend

Hilt + Retrofit/OkHttp/Gson được dùng ở runtime qua `PatientRepository` và
`PatientViewModel`. Khởi động backend trước khi đi qua onboarding:

```bash
cd D:/Android/dosely-medication-adherence-agent
.venv/python.exe -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

- `data/remote/ApiConfig.kt` — `BASE_URL = "http://10.0.2.2:8000/api/v1/"`
  (10.0.2.2 is how the emulator reaches the host's `make run`; a real device
  needs the host's LAN IP or the deployed URL instead).
- `data/remote/DoselyApiService.kt` — PIN login/change, routine, schedule,
  prescription, adherence, dose action, health survey và SOS; path/method khớp
  backend FastAPI.
- `ui/AuthViewModel.kt` — validates the six-digit PIN and routes first-login
  users through compulsory PIN change and routine setup. Returning users enter
  the dashboard directly.
- `data/repository/RoutineRepository.kt` — interface returning
  `List<RoutineItem>`, the exact shape `MockRepository.routine` already
  returns, so swapping the implementation doesn't touch any screen.
  `MockRoutineRepositoryImpl` giữ lại cho preview/test;
  `RemoteRoutineRepositoryImpl` gọi API thật và
  maps the DTO back into `List<RoutineItem>`.
- `data/repository/RemotePatientRepository.kt` — map DTO backend sang model UI
  và phát khóa idempotency cho dose action/SOS.
- `di/RepositoryModule.kt` — runtime bind vào implementation remote.

### Tài khoản demo (debug)

Khi chạy bản debug mà backend chưa bật, có thể đăng nhập bằng:

- Số điện thoại: `0900000000`
- Mã PIN ban đầu: `123456`

Tài khoản này luôn bắt đầu ở trạng thái đăng nhập lần đầu. Sau khi đổi PIN,
nó tiếp tục vào màn hình thiết lập lịch sinh hoạt. Dữ liệu mock chỉ ở bộ nhớ
và sẽ trở về PIN ban đầu khi khởi động lại app; bản release không có tài khoản này.

## Next steps to make this a real MVP

- **Persist auth session.** PIN login and first-login PIN change call the real
  auth endpoints, but tokens are kept in memory only. Store them with encrypted
  local storage and add refresh/logout handling before production.
- **Replace AI/RAG mock.** Medication detail and assistant chat currently use
  local, safety-labelled demo data. Replace `MockMedicationKnowledge` and
  `AssistantViewModel.answerFor` with the production retrieval/chat APIs while
  preserving source citations and clinical guardrails.
- **Push notifications.** `ReminderScreen` is reachable today only by tapping
  an upcoming dose on the dashboard. Real delivery needs FCM (or whatever the
  backend's Web Push equivalent is for native) triggering a notification that
  deep-links into `reminder/{doseId}`.
- **SOS permissions.** The hold-to-confirm gesture is implemented, but actually
  placing a call / reading location needs `CALL_PHONE` and
  `ACCESS_FINE_LOCATION` runtime permission requests — not added yet since
  there's no real call/location logic to gate behind them.
- **Persist onboarding + settings.** Currently in-memory `remember` state;
  needs DataStore/Room once there's something real to persist.

## Guardrails this UI must keep respecting

Per [`CLAUDE.md`](../CLAUDE.md): prescriptions are doctor-approved and
read-only to the patient (see the guardrail note on `PrescriptionScreen`),
and the Reminder screen may only report dose-taken/late/skipped — it must
never let the patient (or any future client code) edit dose, frequency, or
schedule directly.
