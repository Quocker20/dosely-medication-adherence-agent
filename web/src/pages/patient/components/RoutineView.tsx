import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "../../../api";
import type { PatientRoutine, UpdatePatientRoutineRequest } from "../../../types";

const FIELDS: Array<{ key: keyof UpdatePatientRoutineRequest; label: string; help: string }> = [
  { key: "wake_time", label: "Giờ thức dậy", help: "Thời điểm bạn thường bắt đầu ngày mới" },
  { key: "breakfast_time", label: "Ăn sáng", help: "Dùng làm mốc cho thuốc liên quan bữa ăn" },
  { key: "lunch_time", label: "Ăn trưa", help: "Giờ ăn trưa thông thường" },
  { key: "dinner_time", label: "Ăn tối", help: "Giờ ăn tối thông thường" },
  { key: "sleep_time", label: "Giờ đi ngủ", help: "Mốc kết thúc lịch trong ngày" },
];

type FormValue = Record<keyof UpdatePatientRoutineRequest, string>;

function formFromRoutine(routine: PatientRoutine): FormValue {
  return Object.fromEntries(FIELDS.map(({ key }) => [key, routine[key]?.slice(0, 5) ?? ""])) as FormValue;
}

interface Props {
  patientId: string;
  accessToken: string;
  onScheduleChanged: () => void;
  onNotice: (message: string) => void;
}

export default function RoutineView({ patientId, accessToken, onScheduleChanged, onNotice }: Props) {
  const [saved, setSaved] = useState<PatientRoutine | null>(null);
  const [form, setForm] = useState<FormValue | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [remoteChanged, setRemoteChanged] = useState(false);

  const load = useCallback(async () => {
    const routine = await api.patientRoutine(patientId);
    setSaved(routine);
    setForm(formFromRoutine(routine));
    setRemoteChanged(false);
  }, [patientId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    load().catch((cause) => {
      if (!cancelled) setError(cause instanceof ApiError ? cause.message : "Không tải được lịch sinh hoạt.");
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [load]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = import.meta.env.VITE_WS_HOST || window.location.host;
    let retryId: number | undefined;
    let closed = false;
    let socket: WebSocket | null = null;
    const connect = () => {
      socket = new WebSocket(`${protocol}//${wsHost}/ws/patient?token=${encodeURIComponent(accessToken)}`);
      socket.onopen = () => { load().catch(() => {}); };
      socket.onmessage = (event) => {
        try {
          const frame = JSON.parse(event.data) as { event_type?: string };
          if (frame.event_type === "routine.updated") {
            setRemoteChanged(true);
            load().catch(() => setRemoteChanged(true));
          }
          if (frame.event_type === "schedule.updated") onScheduleChanged();
        } catch { /* The REST read is authoritative; ignore malformed frames. */ }
      };
      socket.onclose = () => {
        if (!closed) retryId = window.setTimeout(connect, 2_000);
      };
    };
    connect();
    return () => {
      closed = true;
      if (retryId) window.clearTimeout(retryId);
      socket?.close();
    };
  }, [accessToken, load, onScheduleChanged]);

  const changes = useMemo<UpdatePatientRoutineRequest>(() => {
    if (!saved || !form) return {};
    return FIELDS.reduce<UpdatePatientRoutineRequest>((result, { key }) => {
      const previous = saved[key]?.slice(0, 5) ?? "";
      if (form[key] !== previous) result[key] = form[key] || null;
      return result;
    }, {});
  }, [form, saved]);
  const allValid = form !== null && FIELDS.every(({ key }) => /^\d{2}:\d{2}$/.test(form[key]));
  const canSave = allValid && Object.keys(changes).length > 0 && !saving;

  async function save() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const routine = await api.updatePatientRoutine(patientId, changes);
      setSaved(routine);
      setForm(formFromRoutine(routine));
      setRemoteChanged(false);
      onNotice("Đã lưu lịch sinh hoạt. Lịch nhắc thuốc đang được cập nhật.");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Không lưu được lịch sinh hoạt.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p className="detail-empty">Đang tải lịch sinh hoạt…</p>;

  return <section className="routine-page web-card">
    <div className="routine-page-head">
      <div>
        <span className="section-eyebrow">ĐỒNG BỘ WEB & ỨNG DỤNG</span>
        <h2>Lịch sinh hoạt của bạn</h2>
        <p>Những mốc này giúp hệ thống chỉ tính lại giờ nhắc phù hợp với sinh hoạt hằng ngày.</p>
      </div>
      <span className="routine-sync"><i /> Đang đồng bộ</span>
    </div>
    <div className="routine-form">
      {FIELDS.map(({ key, label, help }) => <label key={key}>
        <span><b>{label}</b><small>{help}</small></span>
        <input type="time" value={form?.[key] ?? ""} onChange={(event) => setForm((current) => current ? { ...current, [key]: event.target.value } : current)} disabled={saving} />
      </label>)}
    </div>
    {remoteChanged && <div className="routine-remote-note">Lịch vừa được cập nhật từ thiết bị khác; các mốc mới nhất đã được tải lại.</div>}
    {error && <p className="routine-error">{error}</p>}
    <div className="routine-page-footer">
      <p>Thay đổi lịch sinh hoạt không thay đổi liều, số cữ, đường dùng hoặc thời gian điều trị.</p>
      <button className="btn primary" disabled={!canSave} onClick={save}>{saving ? "Đang lưu…" : "Lưu lịch sinh hoạt"}</button>
    </div>
  </section>;
}
