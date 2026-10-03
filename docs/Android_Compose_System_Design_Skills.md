# Tổng hợp Skill System Design App Mobile — Kotlin + Jetpack Compose

**Nguồn gốc:** [Android Basics with Compose](https://developer.android.com/courses/android-basics-compose/course?hl=vi) — khoá chính thức Google, 8 Unit / 19 Pathway / ~110 giờ.

**Mục đích file này:** không phải chép lại giáo trình, mà rút ra **skill nào dùng để thiết kế hệ thống app** (không chỉ viết UI), sắp theo tầng kiến trúc, kèm ánh xạ vào [android/](../android/) của Dosely.

---

## 0. Bản đồ nhanh — Unit khoá học ↔ Tầng hệ thống

| Unit | Nội dung khoá | Tầng hệ thống chi phối | Skill system-design rút ra |
|---|---|---|---|
| 1 | Kotlin cơ bản, Android Studio, layout đầu tiên | — | Nền ngôn ngữ, build/tooling |
| 2 | Kotlin nâng cao, state, unit test | UI layer | State hoisting, recomposition, testability |
| 3 | Collections, list cuộn, Material Design | UI layer | Danh sách hiệu năng, design system, a11y |
| 4 | Lifecycle, ViewModel, StateFlow, Navigation, adaptive layout | **UI + Domain** | UDF, tách state khỏi View, điều hướng, đa kích thước màn hình |
| 5 | Coroutines, Retrofit, Coil, Repository, DI | **Data layer (remote)** | Bất đồng bộ, contract API, repository, DI |
| 6 | SQL, Room, Flow, DataStore | **Data layer (local)** | Persistence, single source of truth, offline |
| 7 | WorkManager | **Background layer** | Tác vụ nền bền vững, constraint, retry |
| 8 | View system, interop Compose ↔ View | Migration | Chiến lược nâng cấp app legacy |

**Đường xương sống cho system design nằm ở Unit 4 → 5 → 6 → 7.** Unit 1–3 là kỹ năng thi công, Unit 8 là kỹ năng di trú.

---

## 1. Kiến trúc tổng thể (Unit 4 — Pathway "Thành phần cấu trúc")

Skill lõi nhất của toàn khoá. Google dạy đúng 3 tầng:

```
UI Layer          Composable  ←  UI State  ←  ViewModel
                       │                          ▲
                    events ─────────────────────┘
Domain Layer      (optional) UseCase — logic nghiệp vụ tái dùng
Data Layer        Repository → DataSource (remote: Retrofit / local: Room, DataStore)
```

### Skill 1.1 — Unidirectional Data Flow (UDF)
State chảy xuống, event chảy lên. Composable không tự sửa dữ liệu nguồn; nó gọi lambda do ViewModel cấp.

- Composable = hàm thuần của state, không giữ dữ liệu nghiệp vụ.
- ViewModel giữ `StateFlow<UiState>`, expose `asStateFlow()` (read-only).
- Mọi mutation đi qua hàm public của ViewModel.

```kotlin
data class DashboardUiState(
    val isLoading: Boolean = true,
    val upcomingDoses: List<Dose> = emptyList(),
    val error: String? = null,
)

class DashboardViewModel(private val repo: DoseRepository) : ViewModel() {
    private val _uiState = MutableStateFlow(DashboardUiState())
    val uiState: StateFlow<DashboardUiState> = _uiState.asStateFlow()

    fun markTaken(doseId: String) = viewModelScope.launch { repo.markTaken(doseId) }
}
```

### Skill 1.2 — Phân biệt 3 loại "state"
Thiết kế sai chỗ đặt state là lỗi kiến trúc phổ biến nhất.

| Loại | Ví dụ | Đặt ở đâu | Sống qua config change? |
|---|---|---|---|
| UI element state | trạng thái mở/đóng của dropdown, scroll position | `remember` trong Composable | `rememberSaveable` mới sống |
| Screen UI state | danh sách liều thuốc, loading, error | ViewModel `StateFlow` | Có |
| App/Persisted state | token đăng nhập, preference | DataStore / Room | Có, sống qua cả process death |

Quy tắc: **hoist state lên tổ tiên chung thấp nhất** cần đọc nó. Không hoist quá cao (làm recompose thừa), không để quá thấp (không share được).

### Skill 1.3 — Lifecycle & config change
- Activity lifecycle: `onCreate/onStart/onResume/onPause/onStop/onDestroy`.
- Xoay màn hình = huỷ + tạo lại Activity → `remember` mất, ViewModel sống.
- Process death → cả ViewModel cũng mất → cần `SavedStateHandle` hoặc persistence.
- Compose có vòng đời riêng: **Composition → Recomposition → Decomposition**, không trùng lifecycle Activity.

### Skill 1.4 — Kiểm soát recomposition (hiệu năng)
- Compose gọi lại composable khi state nó đọc thay đổi. Đọc state càng gần chỗ dùng càng tốt.
- Truyền lambda thay vì object mới mỗi lần render.
- `key` trong `LazyColumn` để tránh recompose/re-create item sai.
- Dùng `derivedStateOf` khi state phái sinh đổi ít hơn state nguồn.

### Skill 1.5 — Test ViewModel
ViewModel không phụ thuộc Android framework → test JVM thuần, nhanh. Repository là interface → fake được. Đây là lý do kiến trúc tách tầng đáng giá.

---

## 2. Điều hướng & cấu trúc màn hình (Unit 4 — Navigation)

### Skill 2.1 — Thiết kế navigation graph
- `NavHost` + `NavController` là **single source of truth cho back stack**.
- Route định nghĩa bằng enum/sealed class, không rải string literal.
- Argument truyền qua route (`"reminder/{doseId}"`), không truyền object nặng.
- ViewModel scope theo NavBackStackEntry khi state chỉ thuộc 1 màn hình; scope theo Activity khi cần share.

### Skill 2.2 — Nguyên tắc điều hướng
- `popUpTo` + `inclusive` để dọn back stack (vd. sau login không quay lại được màn login).
- Deep link để push notification mở thẳng màn hình đích.
- Không cho Composable giữ `NavController` — truyền lambda `onNavigateTo...` xuống, giữ Composable test được và tái dùng được.

### Skill 2.3 — Adaptive layout (đa kích thước màn hình)
- `WindowSizeClass`: Compact / Medium / Expanded → chọn kiểu điều hướng:
  - Compact → Bottom navigation
  - Medium → Navigation rail
  - Expanded → Permanent navigation drawer + list-detail 2 pane
- Thiết kế theo **breakpoint + canonical layout**, không hardcode `dp` theo thiết bị.

---

## 3. Tầng dữ liệu — Remote (Unit 5)

### Skill 3.1 — Coroutines & concurrency
- `suspend fun` cho tác vụ chờ; không block main thread.
- `viewModelScope` tự huỷ khi ViewModel chết → tránh leak.
- `Dispatchers.IO` cho network/disk; repository nên tự quyết dispatcher, không bắt caller lo.
- Structured concurrency: cha huỷ → con huỷ.

### Skill 3.2 — Retrofit + serialization
- Định nghĩa API bằng interface + annotation (`@GET`, `@POST`, `@Path`, `@Body`).
- DTO tách khỏi domain model — đổi API không lan vào UI.
- Singleton Retrofit instance, base URL từ config, không hardcode rải rác.

### Skill 3.3 — Repository pattern
Repository là **ranh giới**: UI/ViewModel chỉ biết interface, không biết dữ liệu từ mạng hay DB.

```kotlin
interface DoseRepository {
    fun observeUpcoming(): Flow<List<Dose>>
    suspend fun markTaken(doseId: String)
}
```

Lợi ích hệ thống: thay nguồn dữ liệu (mock → REST → cache) không đụng UI; test được bằng fake.

### Skill 3.4 — Dependency Injection
- Khoá dạy DI thủ công (`AppContainer` + `CreationExtras` factory) trước khi tới Hilt.
- Nguyên tắc: **class không tự tạo dependency của nó**; nhận qua constructor.
- Đây là điều kiện cần để test và để swap implementation.

### Skill 3.5 — Xử lý lỗi & trạng thái tải
Chuẩn hoá state màn hình thành sealed: `Loading | Success(data) | Error(cause)`. Mọi lỗi mạng phải map thành state hiển thị được, không để crash.

### Skill 3.6 — Ảnh (Coil)
`AsyncImage` + placeholder + error drawable. Ảnh là I/O — phải có state tải riêng, không chặn UI.

---

## 4. Tầng dữ liệu — Local & Persistence (Unit 6)

### Skill 4.1 — Mô hình hoá dữ liệu quan hệ
SQL cơ bản (SELECT/INSERT/UPDATE/DELETE, WHERE, JOIN) → thiết kế bảng, khoá chính, quan hệ.

### Skill 4.2 — Room
3 thành phần: `@Entity` (bảng) — `@Dao` (truy vấn) — `@Database` (holder, singleton).

- DAO trả `Flow<List<T>>` → UI tự cập nhật khi DB đổi. Đây là cơ chế **reactive**, không cần refresh thủ công.
- Ghi là `suspend`, đọc reactive là `Flow`.
- Migration bắt buộc khi đổi schema — `fallbackToDestructiveMigration()` chỉ dùng dev.

### Skill 4.3 — Single Source of Truth (SSOT)
Mẫu chuẩn cho app có mạng + offline: **DB là nguồn sự thật, mạng chỉ để cập nhật DB.**

```
UI ← Flow ← Room ← ghi ← Repository ← fetch ← Retrofit
```

UI không bao giờ đọc thẳng từ network. App mở là có dữ liệu ngay dù offline.

### Skill 4.4 — DataStore
Preference dạng key-value (theme, onboarding đã xong, user setting). Bất đồng bộ, dựa Flow, thay thế SharedPreferences. **Không dùng cho dữ liệu quan hệ hoặc dữ liệu lớn.**

### Skill 4.5 — Flow operators
`map`, `filter`, `combine`, `stateIn` — biến stream dữ liệu tầng data thành UiState tầng UI.

```kotlin
val uiState = repo.observeUpcoming()
    .map { DashboardUiState(isLoading = false, upcomingDoses = it) }
    .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), DashboardUiState())
```

---

## 5. Tầng nền (Unit 7 — WorkManager)

### Skill 5.1 — Chọn đúng công cụ chạy nền

| Nhu cầu | Dùng gì |
|---|---|
| Việc chỉ cần khi UI sống | `viewModelScope` + coroutine |
| Việc phải hoàn tất kể cả app bị kill / máy reboot | **WorkManager** |
| Việc đúng thời điểm chính xác, đánh thức máy | `AlarmManager` (exact alarm) |
| Việc do server đẩy xuống | FCM push |

### Skill 5.2 — WorkManager
- `Worker` / `CoroutineWorker` chứa logic; `WorkRequest` mô tả khi nào chạy.
- `Constraints`: cần mạng, đang sạc, pin không thấp, storage đủ.
- `OneTimeWorkRequest` vs `PeriodicWorkRequest` (tối thiểu 15 phút).
- Chuỗi công việc: `beginWith().then()`.
- `enqueueUniqueWork` + policy (`KEEP`/`REPLACE`) — chống trùng job.
- Quan sát trạng thái qua `WorkInfo` (LiveData/Flow) để phản hồi lên UI.
- Retry: `Result.retry()` + backoff policy.

### Skill 5.3 — Giới hạn thực tế cần thiết kế quanh
WorkManager **không đảm bảo thời điểm chính xác** (Doze mode, battery optimization của OEM). App cần nhắc đúng giờ thì phải kết hợp exact alarm hoặc push từ server, không dựa mình WorkManager.

---

## 6. UI Layer — thi công & chất lượng (Unit 2, 3)

### Skill 6.1 — Design system
- Material 3 theme: `ColorScheme`, `Typography`, `Shapes` — định nghĩa 1 chỗ (`ui/theme/`), Composable chỉ tiêu thụ token.
- Dark theme + dynamic color.
- Không hardcode màu/size trong màn hình.

### Skill 6.2 — Danh sách hiệu năng
`LazyColumn` / `LazyRow` / `LazyVerticalGrid` — chỉ compose item hiển thị. Bắt buộc `key = { it.id }` khi list có thể thay đổi thứ tự.

### Skill 6.3 — Component tái dùng
Tách atom dùng chung (`ui/components/`) — nút, chip, thanh dưới. Composable nhận state + lambda, không đọc ViewModel trực tiếp → tái dùng và preview được.

### Skill 6.4 — Accessibility
`contentDescription`, kích thước chạm tối thiểu 48dp, tương phản màu, hỗ trợ TalkBack. Test bằng Accessibility Scanner.

### Skill 6.5 — Animation
`animate*AsState`, `AnimatedVisibility`, `Modifier.animateContentSize()` — animation là state-driven, không phải imperative.

### Skill 6.6 — Test
- Unit test (JVM): ViewModel, repository, logic thuần.
- UI test (`createComposeRule`): `onNodeWithText().performClick().assertExists()`.
- Navigation test: điều khiển `TestNavHostController`, kiểm tra route hiện tại.

---

## 7. Interop & di trú (Unit 8)

- App legacy XML/View: nhúng Compose bằng `ComposeView`.
- Cần View chưa có bản Compose (MapView, AdView, WebView): nhúng ngược bằng `AndroidView`.
- Chiến lược di trú: **từ lá lên gốc** — đổi từng màn hình/từng component, không viết lại toàn app.

---

## 8. Checklist thiết kế một app Compose mới

Dùng làm quy trình khi bắt đầu module/màn hình mới:

1. **Vẽ luồng màn hình** → xác định route + argument + back stack behavior.
2. **Định nghĩa UI State** cho từng màn hình (data class hoặc sealed).
3. **Xác định nguồn dữ liệu**: remote-only / local-only / SSOT (Room + network).
4. **Viết interface Repository trước**, implement mock trước, thật sau.
5. **Chọn scope coroutine** cho từng tác vụ; việc nào phải sống ngoài UI → WorkManager.
6. **Đặt state đúng tầng** theo bảng ở Skill 1.2.
7. **Thiết kế token theme trước khi viết màn hình** — tránh hardcode.
8. **Viết test ViewModel** ngay khi state ổn định.
9. **Kiểm accessibility + adaptive layout** trước khi coi màn hình là xong.
10. **Xử lý error/empty/loading** — 3 state này bị quên nhiều nhất.

---

## 9. Ánh xạ vào Dosely ([android/](../android/))

> ⚠️ **Cập nhật:** đoạn mô tả trạng thái bên dưới đã lỗi thời — viết từ giai đoạn app còn
> mock data. Thực tế hiện tại (xem [android/README.md](../android/README.md)): app đã gọi
> FastAPI backend thật qua Retrofit cho dashboard, lịch sinh hoạt, đơn thuốc, thao tác cữ
> thuốc, khảo sát và SOS; đã build/cài/verify trên emulator. `data/MockRepository.kt`
> không còn tồn tại trong repo.

Trạng thái hiện tại (đã verify lại so với code thật):

| Skill trong file này | Áp dụng vào Dosely | Trạng thái |
|---|---|---|
| 1.1 UDF + ViewModel | Mỗi màn hình cần `XxxViewModel` + `XxxUiState` | ✅ có — `AuthViewModel`, `PatientViewModel`, `AssistantViewModel` (`ui/feature/*/`) |
| 2.1 Navigation graph | `navigation/DoselyNavHost.kt` — 8 route đã có | ✅ |
| 2.2 Deep link | Push nhắc thuốc phải mở thẳng `reminder/{doseId}` | ❌ chưa có |
| 3.2 Retrofit | Client gọi `/api/v1` thật | ✅ có — `data/repository/Remote*RepositoryImpl.kt` gọi `DoselyApiService` |
| 3.3 Repository | Interface + implementation thật (không còn mock) | ✅ |
| 3.4 DI | Swap implementation qua Hilt module | ✅ có — `di/{DatabaseModule,NetworkModule,RepositoryModule,ConnectivityModule,RealtimeModule}.kt` |
| 4.2/4.3 Room + SSOT | Lịch uống thuốc **phải đọc được offline** — bệnh nhân mất mạng vẫn phải thấy lịch | ✅ có — `data/local/DoselyDatabase.kt` + `data/local/dao/`, cộng cơ chế outbox riêng (xem `docs/outbox-replay-contract.md`) |
| 4.4 DataStore | Onboarding routine + settings đang là in-memory `remember` | ❌ chưa xác nhận lại — không nằm trong phạm vi audit lần này |
| 5.1/5.2 WorkManager | Đồng bộ lịch, gửi báo cáo tuân thủ khi có mạng lại | ✅ có — `sync/OutboxSyncWorker.kt` (`@HiltWorker`) + `sync/WorkManagerOutboxSyncScheduler.kt` |
| 5.3 Giới hạn WorkManager | **Nhắc uống thuốc đúng giờ không được dựa WorkManager** — dùng exact alarm hoặc FCM | ⚠️ điểm thiết kế phải chốt |
| 6.1 Design system | `ui/theme/` đã khớp mockup | ✅ |
| 6.3 Component | `ui/components/Components.kt` đã tách atom | ✅ |
| 6.4 Accessibility | Bệnh nhân mạn tính nhiều người cao tuổi → font scale lớn, tương phản cao, chạm ≥48dp là **yêu cầu chức năng**, không phải nice-to-have | ⚠️ chưa kiểm |

### Ràng buộc Dosely đè lên mọi skill trên

Theo [CLAUDE.md](../CLAUDE.md):

- **HITL**: đơn thuốc là read-only phía bệnh nhân. Repository phía client **không được có** hàm `updateDose(...)`/`updateFrequency(...)`. Thiết kế interface đã phải chặn từ đầu, không đợi runtime.
- Màn Reminder chỉ được báo `taken` / `late` / `skipped`. Không API nào khác từ màn này.
- Không log plaintext OTP/token/PHI — kể cả `Log.d` khi debug network. Interceptor log của Retrofit phải tắt ở release build.

---

## 10. Thứ tự học đề xuất (nếu mục tiêu là system design, không phải làm hết khoá)

1. **Unit 4 Pathway 1** (Architecture, ViewModel, StateFlow) — bắt buộc, nền của mọi thứ.
2. **Unit 5** (Coroutines, Retrofit, Repository, DI) — tầng data remote.
3. **Unit 6** (Room, Flow, DataStore) — persistence + SSOT.
4. **Unit 4 Pathway 2** (Navigation) — cấu trúc màn hình.
5. **Unit 7** (WorkManager) — tác vụ nền.
6. **Unit 4 Pathway 3** (Adaptive layout) — khi cần hỗ trợ tablet.
7. Unit 1–3: tra khi thiếu; Unit 8: chỉ khi phải đụng app legacy XML.

---

## 11. Tài liệu tham khảo ngoài khoá (đọc sau khi xong Unit 4–6)

- Guide to app architecture — developer.android.com/topic/architecture
- Now in Android (app mẫu chuẩn kiến trúc của Google) — github.com/android/nowinandroid
- Compose performance — developer.android.com/develop/ui/compose/performance
- Background work guide — developer.android.com/develop/background-work/background-tasks
