# Prescription PDF Export — Implementation Plan

**Branch:** `feat/export-pdf`
**Status:** Approved for implementation, not yet started
**Scope:** `backend` + `web` portal. No Android work in this slice.

---

## 1. Feature summary

A doctor approves an electronic prescription. Immediately after `POST /prescriptions/{id}/approve`
returns 200, the portal shows a **"Tải đơn thuốc (PDF)"** button. Clicking it downloads a PDF laid
out according to **Phụ lục I of Thông tư 26/2025/TT-BYT** (the Vietnamese Ministry of Health
outpatient prescription form).

Fields the database actually holds are read through existing joins. Fields the form requires but
that have no column anywhere are filled from hardcoded simulation constants in `Settings`.

---

## 2. Regulatory context

**Thông tư 26/2025/TT-BYT**, effective 01/07/2025, fully replaces TT 52/2017/TT-BYT and its
amendments. It ships three form templates: Phụ lục I (ordinary prescription — the one we implement),
Phụ lục II ("N", narcotics), Phụ lục III ("H", psychotropics and precursors). Only Phụ lục I is in
scope.

Mandatory content per the circular: drug name, concentration/strength, dosage, route of
administration, number of days of use; the patient's personal identification number, residential
address, and body weight; and for children under 72 months, age in months and weight. A drug may be
prescribed for at most 30 days (up to 90 for chronic conditions listed in Phụ lục VII). Electronic
prescriptions carry the same legal weight as paper ones when properly created, digitally signed,
stored and shared.

**This export is a simulation and must never present itself as a legally valid prescription.** See
§5 (watermark and seeding rules).

Sources:

- [Thông tư 26/2025/TT-BYT — thuvienphapluat.vn](https://thuvienphapluat.vn/van-ban/The-thao-Y-te/Thong-tu-26-2025-TT-BYT-don-thuoc-va-viec-ke-don-thuoc-hoa-duoc-trong-dieu-tri-ngoai-tru-643684.aspx)
- [Bản gốc — vanban.chinhphu.vn](https://vanban.chinhphu.vn/?pageid=27160&docid=214386&classid=1&orggroupid=4)
- [Tóm tắt — Viện Y học phóng xạ và U bướu Quân đội](https://vienyhpxubqd.vn/tom-tat-thong-tu-26-2025-tt-byt-quy-dinh-moi-ve-don-thuoc-va-ke-don-thuoc-trong-dieu-tri-ngoai-tru/)

---

## 3. Decisions taken

| Question | Decision |
|---|---|
| Layout standard | Phụ lục I, TT 26/2025/TT-BYT |
| Missing data | Join for everything the DB has; hardcode-seed the rest |
| Export precondition | `prescription.status == "APPROVED"` |
| When the button appears | Immediately on `approve()` returning 200 |
| Download limit | **Frontend affordance only** — button shown once, no backend block |
| Schema change | **None.** No migration, no model change, no DI change |

### Why the button is not gated on schedule generation

`_dispatch_schedule_generation` (`src/modules/prescriptions/service.py:150`) is a fire-and-forget
`celery_app.send_task`; the approve response carries no `agent_run_id`, and the dispatch is
deliberately fail-open. Gating the PDF button on schedule completion would mean a broker hiccup
permanently hides the button for a perfectly valid approved prescription — and the PDF reads nothing
from `scheduled_doses` in the first place.

### Why there is no backend download block

A hard one-shot block needs either a new `prescriptions.pdf_exported_at` column (migration) or an
unindexed `audit_logs` probe. Both were considered and deferred. The accepted consequence: a page
refresh brings the button back and the endpoint can be called again. `GET` stays idempotent, which
is also what HTTP expects.

If a hard block is wanted later, the correct shape is a nullable `pdf_exported_at` column with the
same optimistic guard `approve_if_draft` already uses:

```sql
UPDATE prescriptions SET pdf_exported_at = NOW()
WHERE id = :id AND status = 'APPROVED' AND pdf_exported_at IS NULL
RETURNING *
```

Note the trade-off before adopting it: a mid-download network failure would cost the patient the
document permanently.

---

## 4. Data sources

### 4.1 From the database (existing repository methods — no new joins to write)

| Source | Method | Fields used |
|---|---|---|
| `PatientProfile ⨝ User` | `PatientRepository.get_patient_with_user` (`src/modules/patients/repository.py:96`) | `name`, `dob`, `sex`, `phone`, `timezone`, `emergency_note` |
| `DoctorProfile ⨝ User` | `DoctorRepository.get_doctor_with_user` (`src/modules/admin/repository.py:38`) | `name`, `license_no`, `specialty` |
| `prescriptions` | `PrescriptionRepository.get_by_id` | `id`, `diagnosis_note`, `approved_at`, `status` |
| `prescription_items` | `PrescriptionRepository.get_items` | `display_name`, four dose columns, `dose_unit`, `route`, `meal_relation`, `start_date`, `end_date`, `instructions`, `is_critical` |
| `medications` | **new** `MedicationRepository.list_by_ids` | `composition`, `manufacturer` |

`emergency_note` is currently unused elsewhere; it maps onto the form's allergy/history note area.

### 4.2 Hardcoded simulation seeds

The form requires these and no table holds them: clinic name / address / phone / code, personal
identification number (CCCD), residential address, health-insurance card number, body weight,
follow-up instruction.

### 4.3 Columns that exist but may be NULL — never seeded

`dob`, `sex`, `diagnosis_note`, `end_date`. These render as `(chưa cập nhật)`. A seeded value here
would hide the fact that a record is incomplete, which is different from filling a field the system
was never designed to hold.

### 4.4 Guardian field is dropped

There is no `caregiver_profiles` table. A caregiver is a `users` row (role `CAREGIVER`) plus a
`caregiver_links` row — **the caregiver's name is stored nowhere**, only phone and relationship
label. The circular marks the guardian field "when necessary", so the row is omitted rather than
half-rendered.

---

## 5. Sheet layout

```
+- PHÒNG KHÁM ĐA KHOA MÔ PHỎNG REMINDRX ---------- Mã CSKCB: SIM-00000
|  Số 1, Đường Mô Phỏng, Phường Demo, Hà Nội           ĐT: 1900 0000
+----------------------------------------------------------------------
|                        ĐƠN THUỐC                     Số: a3f9c21b
+----------------------------------------------------------------------
|  Họ tên: Nguyễn Văn A             Ngày sinh: 12/03/1958  (68 tuổi)
|  Giới tính: Nam                   Cân nặng: 60 kg
|  Số định danh: 000000000000       Số thẻ BHYT: SIM0000000000000
|  Địa chỉ: Số 1, Đường Mô Phỏng, Phường Demo, Hà Nội
|  Điện thoại: 0912xxxxxx
|  Lưu ý / tiền sử:  <- emergency_note
+----------------------------------------------------------------------
|  Chẩn đoán: ...
+----------------------------------------------------------------------
|  01. Paracetamol 500 (Paracetamol)             (theo nhãn thuốc)
|      SL: 60 viên | Uống | Sau ăn
|      Sáng 1 | Trưa 1 | Chiều 1 | Tối -
|      21/09/2026 -> 20/10/2026 (30 ngày)
|      Ghi chú: uống nhiều nước
|  02. [!] ...
+----------------------------------------------------------------------
|  Lời dặn: Tái khám theo lịch hẹn của bác sĩ.
|  Đơn có giá trị mua, lĩnh thuốc trong 30 ngày kể từ ngày kê.
|                                      Ngày 21 tháng 09 năm 2026
|                                      BÁC SĨ KÊ ĐƠN
|                                      (Ký điện tử — bản mô phỏng)
|                                      BS. Trần Thị B
|                                      CCHN: 001234/HN-CCHN | Nội khoa
+-  [!] Bản mô phỏng phục vụ học thuật — không có giá trị pháp lý
```

Item numbering uses `01, 02, ...` (the circular requires a leading zero below 10). `is_critical`
items get a warning marker plus a footnote under the table.

### Seeding safety rules

1. **Seeds must look obviously synthetic.** `000000000000`, not a validly-formatted random 12-digit
   CCCD. `SIM-00000`, not a plausible facility code.
2. **A diagonal watermark `MÔ PHỎNG — KHÔNG CÓ GIÁ TRỊ PHÁP LÝ` on every page.** A Phụ lục I layout
   with plausible identifiers and no watermark produces a sheet usable as a real prescription.
3. **The signature block must say `(Ký điện tử — bản mô phỏng)`.** Do not simulate a digital
   signature; under TT 26/2025 the digital signature is what confers legal validity.
4. **Do not seed strength/concentration.** Render `(theo nhãn thuốc)`. Every other seeded field is
   administrative; a fabricated `500mg` is a clinically wrong number on a prescription-shaped
   document.

### Known layout caveat

The schema permits an arbitrary `end_date`, so an item may span more than the 30 days the footer
line claims. This is best addressed by a warning in the prescribing UI, not in the PDF layer. Out of
scope here; recorded so it is not mistaken for a rendering bug.

---

## 6. Implementation steps

### Step 1 — Fonts and dependency

```
assets/fonts/NotoSans-Regular.ttf
assets/fonts/NotoSans-Bold.ttf
```

fpdf2's built-in core fonts are Latin-1 only; Vietnamese diacritics render as garbage without an
embedded Unicode TTF. Noto Sans is OFL-licensed and safe to vendor. Add `assets/` to the Docker
image copy list, and confirm `.gitignore` does not exclude `*.ttf`.

`requirements.txt`:

```
fpdf2>=2.8.0
```

Chosen over WeasyPrint (needs system GTK — painful on Windows dev machines) and over client-side
jsPDF (the Android app will eventually need the same document, so it has to be a server endpoint).

### Step 2 — Configuration seeds

Append to `Settings` in `src/core/config.py`:

```python
# Simulated prescription-form fields. The DB has no column for any of
# these; values are deliberately obvious placeholders so an exported
# sheet can never be mistaken for a real clinical document.
clinic_name: str = "PHÒNG KHÁM ĐA KHOA MÔ PHỎNG REMINDRX"
clinic_address: str = "Số 1, Đường Mô Phỏng, Phường Demo, Hà Nội"
clinic_phone: str = "1900 0000"
clinic_code: str = "SIM-00000"
sim_patient_id_number: str = "000000000000"
sim_patient_address: str = "Số 1, Đường Mô Phỏng, Phường Demo, Hà Nội"
sim_patient_insurance_no: str = "SIM0000000000000"
sim_patient_weight: str = "60 kg"
sim_followup_note: str = "Tái khám theo lịch hẹn của bác sĩ."
pdf_max_free_text_chars: int = Field(default=2000, ge=100, le=20000)
```

### Step 3 — Repository: the one new method

`MedicationRepository` only exposes `get_medication_by_id` (single row). Calling it per item is the
N+1 this plan must avoid. Add to `src/modules/prescriptions/repository.py`:

```python
async def list_by_ids(
    self, medication_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Medication]:
    """Bulk-resolve medications for PDF rendering. Returns a dict so the
    caller can look up per item without a second pass. Callers must dedupe
    and drop None ids first; an empty input short-circuits so we never emit
    a degenerate `IN ()`.
    """
    if not medication_ids:
        return {}
    stmt = select(Medication).where(Medication.id.in_(medication_ids))
    result = await self._db.execute(stmt)
    return {m.id: m for m in result.scalars().all()}
```

Mirrors the existing `get_items_for_prescriptions` idiom. `medications.id` is the PK, so the `IN` is
an index scan. **No other repository changes.**

### Step 4 — Pure renderer: `src/modules/prescriptions/pdf.py`

No DB, no session, no `await` — same discipline as `agents/planner.py`. Takes a frozen input
dataclass, returns `bytes`.

```python
@dataclass(frozen=True)
class PdfPatient:
    name: str
    dob: date | None
    sex: str | None
    phone: str
    timezone: str
    emergency_note: str | None

@dataclass(frozen=True)
class PdfDoctor:
    name: str
    license_no: str
    specialty: str | None

@dataclass(frozen=True)
class PdfItem:
    display_name: str
    composition: str | None       # None when medication_id is null/deleted
    dose_unit: str
    morning: Decimal | None
    noon: Decimal | None
    evening: Decimal | None
    bedtime: Decimal | None
    route: str
    meal_relation: str | None
    start_date: date
    end_date: date | None
    instructions: str | None
    is_critical: bool

@dataclass(frozen=True)
class PrescriptionPdfData:
    prescription_id: uuid.UUID
    approved_at: datetime
    diagnosis_note: str | None
    patient: PdfPatient
    doctor: PdfDoctor | None      # doctor_id is ON DELETE SET NULL
    items: tuple[PdfItem, ...]

def render_prescription_pdf(data: PrescriptionPdfData, seeds: PdfSeeds) -> bytes: ...
```

#### Dirty-data handling

Each row is a defect the current schema can actually produce. Implement each as a small pure helper
with its own unit test.

| Case | Source | Handling |
|---|---|---|
| `name == "NULL"` | `_resolve_or_create_patient` placeholder | render `(chưa cập nhật)` — never print `NULL` |
| `dob is None` | nullable column | `(chưa cập nhật)`; skip age and months derivation |
| `sex` unknown value | free-text `String(20)` | map `MALE`/`FEMALE`/`OTHER`; unknown falls through to raw value, never `KeyError` |
| `doctor is None` | `ondelete="SET NULL"` | signature block renders `(không xác định)` |
| `composition is None` | `medication_id` has **no FK** — row may be deleted | fall back to `display_name` alone |
| `Decimal("1.000")` | `Numeric(10,3)` | `normalize()` then strip exponent -> `1`; format `0.5` as `0,5` (VN decimal comma) |
| dose `0` vs `None` | both mean "no dose this slot" | render `-` for both |
| `end_date is None` | nullable | duration and quantity both `(dùng liên tục)` |
| `end_date < start_date` | no CHECK constraint exists | guard; render `(không xác định)`, never a negative count |
| `approved_at` in UTC | `DateTime(timezone=True)` | convert to `patient.timezone` via `zoneinfo` before formatting — a 20:00 UTC approval otherwise prints the wrong calendar day |
| invalid `timezone` string | free-text `String(50)` | `try/except ZoneInfoNotFoundError` -> fall back to `Asia/Ho_Chi_Minh` |
| unbounded `Text` | `diagnosis_note`, `instructions` | `multi_cell` wrapping **and** truncate at `pdf_max_free_text_chars` with an ellipsis — otherwise one pasted essay yields a 400-page PDF |
| `route` / `meal_relation` | free-text | dict lookup with `.get(value, value)` fallback |

Quantity derivation:

```
days  = (end_date - start_date).days + 1
total = (morning + noon + evening + bedtime) * days
```

Sum only non-null slots. Render as `{total} {dose_unit}`.

### Step 5 — Service: `PrescriptionService.export_pdf`

```python
async def export_pdf(
    self,
    prescription_id: uuid.UUID,
    actor_payload: dict,
    ip_address: Optional[str] = None,
) -> bytes:
```

#### 5a. Access — reuse, do not reimplement

```python
role = actor_payload.get("role")
actor_id = None if role == "ADMIN" else uuid.UUID(actor_payload["sub"])
prescription = await self._rx_repo.get_by_id(prescription_id, actor_id=actor_id)
if prescription is None:
    raise NotFoundException(message="Prescription not found")
```

Identical to `get_prescription`. The self / doctor-prescribed / active-caregiver predicates are
folded into the same statement by `_access_filter`, so an out-of-scope prescription is
indistinguishable from a nonexistent one. **Write no new access logic** — a second, parallel rule is
how the two drift apart.

#### 5b. Status gate

```python
if prescription.status != "APPROVED":
    raise ValidationException(
        message="Only an approved prescription can be exported"
    )   # -> 422
```

Placed **after** the access check, so a stranger probing UUIDs gets 404 for everything and cannot
learn that a given id exists but is still a draft.

#### 5c. Data fetch — a fixed five queries

```python
items = await self._rx_repo.get_items(prescription_id)              # Q2

patient_row = await self._patient_repo.get_patient_with_user(       # Q3
    prescription.patient_id, requesting_doctor_id=None
)
if patient_row is None:
    raise NotFoundException(message="Prescription not found")

doctor_row = None
if prescription.doctor_id is not None:
    doctor_row = await self._doctor_repo.get_doctor_with_user(      # Q4
        prescription.doctor_id
    )

med_ids = {i.medication_id for i in items if i.medication_id is not None}
medications = await self._med_repo.list_by_ids(tuple(med_ids))      # Q5
```

`requesting_doctor_id=None` is deliberate: authorisation already passed in 5a, and re-applying the
doctor scope here would break the patient and caregiver paths, which have no `doctor_id` to scope by.

**Index coverage — every predicate:**

| Query | Predicate | Index |
|---|---|---|
| Q1 prescription | `prescriptions.id` | PK |
| Q1 access subquery | `(doctor_id, patient_id)` | `idx_prescriptions_doctor_patient` |
| Q1 access subquery | `(patient_id, caregiver_user_id)` | `uq_caregiver_links_patient_caregiver` |
| Q2 items | `prescription_items.prescription_id` | `idx_prescription_items_prescription_id` (migration 0006) |
| Q3 patient | `patient_profiles.user_id` ⨝ `users.id` | both PK |
| Q4 doctor | `doctor_profiles.user_id` ⨝ `users.id` | both PK |
| Q5 medications | `medications.id IN (...)` | PK |

No sequential scan anywhere. The count is constant in the number of items — `med_ids` is a set, so
two items sharing a medication still cost one row.

#### 5d. Render off the event loop

```python
pdf_bytes = await anyio.to_thread.run_sync(
    render_prescription_pdf, pdf_data, seeds
)
```

fpdf2 is synchronous and CPU-bound; called directly it stalls the whole event loop for the duration.
Construct the `FPDF` instance **inside** the worker function — never share one across requests, it
is stateful and not thread-safe.

#### 5e. Audit write — mind the autobegin trap

Five reads have already run on this session, so an implicit transaction is open. Entering
`async with self._db.begin():` without closing it raises
`InvalidRequestError: A transaction is already begun on this Session` — the recurring bug called out
in `CLAUDE.md`.

```python
if self._db.in_transaction():
    await self._db.commit()

try:
    async with self._db.begin():
        await self._audit_repo.create_audit_log(
            action="EXPORT_PRESCRIPTION_PDF",
            entity_type="PRESCRIPTION",
            actor_user_id=uuid.UUID(actor_payload["sub"]),
            entity_id=prescription_id,
            ip_address=ip_address,
        )
except Exception:
    logger.exception(
        "Audit write failed for PDF export of prescription %s; export proceeds",
        prescription_id,
    )

return pdf_bytes
```

Ordered **after** rendering so a render failure leaves no audit row claiming an export that never
happened. Fail-open on the audit write is deliberate: an audit-table problem should not withhold a
patient's own approved prescription. The exception is logged so the gap stays visible.

`audit_logs` is append-only with no unique constraint on `(entity_id, action)`, so concurrent
exports simply insert two rows — no race, no lock contention. Never log the patient's name, phone,
or diagnosis; `entity_id` only.

### Step 6 — Router

```python
@prescriptions_router.get(
    "/prescriptions/{prescription_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def export_prescription_pdf(
    prescription_id: uuid.UUID,
    request: Request,
    current_user: AuthenticatedUserDep,
    service: PrescriptionServiceDep,
) -> Response:
    """Export an APPROVED prescription as a PDF laid out per Phụ lục I of
    Thông tư 26/2025/TT-BYT. Access matches get_prescription exactly.

    The only endpoint in the API that does not return the standard JSON
    envelope — a PDF body cannot be wrapped in one. Error paths still
    return the envelope via the global exception handlers.
    """
    pdf_bytes = await service.export_pdf(
        prescription_id=prescription_id,
        actor_payload=current_user,
        ip_address=get_client_ip(request),
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="don-thuoc-{prescription_id.hex[:8]}.pdf"',
            "Cache-Control": "no-store",
        },
    )
```

The filename uses the hex id only. Interpolating a patient name would put user-controlled UTF-8 into
a response header — header injection plus encoding breakage. `Cache-Control: no-store` keeps PHI out
of intermediate caches.

Status codes:

| Situation | Response |
|---|---|
| OK | `200` · `application/pdf` |
| Not `APPROVED` | `422` |
| Nonexistent or out of scope | `404` (identical, by design) |

### Step 7 — Frontend HTTP client

`request<T>` in `web/src/api/client.ts` always calls `unwrap()`, which does `response.json()`. Add a
sibling that keeps the 401-refresh behaviour but returns a blob:

```ts
export async function requestBlob(
  path: string, options: RequestOptions = {}
): Promise<Blob> {
  let response = await rawRequest(path, options);

  if (response.status === 401 && !options.anonymous && getSession()) {
    const refreshed = await refreshSession();
    if (!refreshed) {
      throw new ApiError(401, "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại");
    }
    response = await rawRequest(path, options);
  }

  // Error paths still return the JSON envelope.
  if (!response.ok) {
    const envelope = await response.json().catch(() => null);
    throw new ApiError(
      envelope?.code ?? response.status,
      envelope?.message ?? "Không tải được đơn thuốc",
      envelope?.errors ?? null,
    );
  }
  return response.blob();
}
```

Reusing `rawRequest` keeps the single-flight refresh guard intact — a hand-rolled `fetch` here would
sidestep it and could burn the rotating refresh token.

In `prescriptionsApi`:

```ts
downloadPrescriptionPdf: (prescriptionId: string) =>
  requestBlob(`/prescriptions/${prescriptionId}/pdf`),
```

### Step 8 — `PrescriptionView.tsx`

Add state:

```ts
const [pdfOffered, setPdfOffered] = useState(false);
```

In `approve()`, immediately after `setPrescription(approved)` (~line 310) and **before** the
`generateSchedule` call, so a scheduling failure never hides the button:

```ts
setPdfOffered(true);
```

Render inside the existing `approve-bar` block (~line 686):

```tsx
{pdfOffered && (
  <button className="btn" onClick={downloadPdf} disabled={busy}>
    Tải đơn thuốc (PDF)
  </button>
)}
```

```ts
async function downloadPdf() {
  if (!prescription) return;
  setBusy(true);
  let url: string | null = null;
  try {
    const blob = await api.downloadPrescriptionPdf(prescription.id);
    url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `don-thuoc-${prescription.id.slice(0, 8)}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setPdfOffered(false);          // one-shot affordance
    onToast("Đã tải đơn thuốc");
  } catch (error) {
    onToast(error instanceof ApiError ? error.message : "Không tải được đơn thuốc");
    // button stays visible so a transient failure is retryable
  } finally {
    if (url) URL.revokeObjectURL(url);
    setBusy(false);
  }
}
```

Two details that matter: `setPdfOffered(false)` runs only on success, so a network blip does not
consume the one offer; and `revokeObjectURL` in `finally` prevents the blob leaking for the tab's
lifetime.

### Step 9 — Documentation

- `.claude/rules/api-contract.md`, Slice 5 — add the endpoint row; state explicitly that this is the
  sole non-envelope endpoint, that error paths still use the envelope, and that `422` means "not
  APPROVED".
- `.claude/rules/schema.md`, §5 — note that the export has no response DTO (binary), and list which
  form fields are config-seeded versus DB-derived.

### Step 10 — Tests

`tests/test_api/test_prescriptions.py`:

| Test | Asserts |
|---|---|
| approved export | `200`, `content-type: application/pdf`, body starts with `%PDF-` |
| draft export | `422` |
| cancelled export | `422` |
| other doctor | `404` (not 403) |
| unrelated patient | `404` |
| nonexistent id | `404` — same shape as out-of-scope |
| patient exports own | `200` |
| active caregiver | `200` |
| inactive caregiver | `404` |

`tests/test_services/test_prescription_pdf.py` — pure-renderer unit tests covering every row of the
Step 4 dirty-data table: `"NULL"` name, null `dob`/`sex`/`diagnosis_note`/`end_date`,
`end_date < start_date`, missing medication, `Decimal("1.000")` and `Decimal("0.5")`, a 50,000-char
`instructions`, a bogus timezone string, `doctor is None`. Each asserts no exception plus the
expected substring.

**The N+1 guard, as an executable test rather than a claim:**

```python
@pytest.mark.asyncio
async def test_pdf_export_query_count_is_constant(...):
    """20 items must cost the same number of queries as 2."""
    counts = []
    for item_count in (2, 20):
        rx = await _seed_prescription(items=item_count)
        statements = []
        event.listen(sync_engine, "before_cursor_execute",
                     lambda *a, **k: statements.append(a[2]))
        await client.get(f"/api/v1/prescriptions/{rx.id}/pdf", headers=doctor_auth)
        event.remove(sync_engine, "before_cursor_execute", ...)
        counts.append(len(statements))
    assert counts[0] == counts[1]
```

This is what stops a later refactor from quietly reintroducing a per-item `get_medication_by_id`.

---

## 7. Execution order

```
1.  requirements.txt + assets/fonts/                    # deps
2.  src/core/config.py                                  # seeds
3.  src/modules/prescriptions/repository.py             # list_by_ids
4.  src/modules/prescriptions/pdf.py                    # pure renderer + unit tests
5.  src/modules/prescriptions/service.py                # export_pdf
6.  src/modules/prescriptions/router.py                 # endpoint
7.  tests/test_api/test_prescriptions.py                # integration + N+1 guard
8.  web/src/api/client.ts + web/src/api/prescriptions.ts
9.  web/src/pages/doctor/components/PrescriptionView.tsx
10. .claude/rules/api-contract.md, .claude/rules/schema.md
```

Steps 1–7 are independently verifiable before any frontend work — the endpoint can be exercised
through Swagger at `/docs` and the resulting PDF opened directly.

**No Alembic migration. No model change. No new dependency-injection wiring.**

---

## 8. Non-goals

- Phụ lục II ("N") and Phụ lục III ("H") controlled-substance forms.
- A real digital signature (which is what makes an electronic prescription legally valid).
- Android download support — the same endpoint will serve it, but the client work is a separate
  slice.
- Any backend enforcement of a single download.
- New columns for weight, drug strength, or dispensed quantity. These are the three fields where a
  seeded value is clinically wrong rather than merely cosmetic; if the project later wants a
  faithful form, they should become real columns rather than better fakes.
