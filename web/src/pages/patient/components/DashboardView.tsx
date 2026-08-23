import type { ScheduledDoseRow } from "../../../types";
import DoseCard, { NextDose } from "./DoseCard";
import Icon, { type IconName } from "./Icon";
import { prettyTime, type DoseAction } from "./utils";

export default function DashboardView({ today, adherence, completed, doses, nextDose, error, busyId, onRetry, onAction, onOpenSchedule, onOpenSurvey }: { today: string; adherence: number; completed: number; doses: ScheduledDoseRow[]; nextDose?: ScheduledDoseRow; error: string | null; busyId: string | null; onRetry: () => Promise<void>; onAction: DoseAction; onOpenSchedule: () => void; onOpenSurvey: () => void }) {
  const readableDate = new Date(`${today}T12:00:00`).toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
  const missed = doses.filter((dose) => ["SKIPPED", "MISSED"].includes(dose.status.toUpperCase())).length;
  return <>
    <section className="web-welcome"><div><span>Xin chào 👋</span><h2>Chúc bạn một ngày khỏe mạnh</h2><p>{readableDate}</p></div><button onClick={onOpenSurvey}><Icon name="heart" size={18}/> Cập nhật sức khỏe</button></section>
    {error && <section className="patient-error"><b>Không thể đồng bộ dữ liệu</b><span>{error}</span><button onClick={() => void onRetry()}>Thử lại</button></section>}
    <section className="patient-kpi-grid">
      <Kpi icon="calendar" tone="blue" label="CỮ THUỐC HÔM NAY" value={doses.length} detail={`${completed} cữ đã hoàn thành`}/>
      <Kpi icon="check" tone="green" label="TUÂN THỦ 7 NGÀY" value={`${adherence}%`} detail={adherence >= 80 ? "Bạn đang làm rất tốt" : "Cố gắng duy trì đều đặn"}/>
      <Kpi icon="clock" tone="amber" label="LIỀU TIẾP THEO" value={nextDose ? prettyTime(nextDose.current_scheduled_at) : "—"} detail={nextDose?.medication_name ?? "Đã hoàn thành hôm nay"}/>
      <Kpi icon={missed ? "alert" : "shield"} tone={missed ? "red" : "green"} label="CẦN LƯU Ý" value={missed} detail={missed ? "cữ đã bỏ qua hoặc bị lỡ" : "Không có cảnh báo"}/>
    </section>
    <section className="dashboard-columns">
      <div className="web-card next-web-card"><CardHead eyebrow="NHẮC THUỐC" title="Liều tiếp theo" action="Xem lịch đầy đủ →" onAction={onOpenSchedule}/>{nextDose ? <NextDose dose={nextDose} busy={busyId === nextDose.scheduled_dose_id} onAction={onAction}/> : <div className="patient-complete"><b><Icon name="check"/> Bạn đã hoàn thành lịch hôm nay</b><span>Không còn cữ thuốc nào đang chờ.</span></div>}</div>
      <div className="web-card adherence-web-card"><CardHead eyebrow="TIẾN ĐỘ" title="Tuân thủ điều trị"/><div className="adherence-visual"><div className="progress-ring" style={{ "--progress": `${adherence * 3.6}deg` } as React.CSSProperties}><b>{adherence}%</b></div><div><strong>{adherence >= 80 ? "Rất tốt!" : "Tiếp tục cố gắng"}</strong><p>Đã uống {completed}/{doses.length} cữ hôm nay.</p></div></div><div className="adherence-legend"><span><i className="done"/> Đã uống <b>{completed}</b></span><span><i className="pending"/> Đang chờ <b>{Math.max(0, doses.length - completed - missed)}</b></span><span><i className="missed"/> Đã lỡ <b>{missed}</b></span></div></div>
    </section>
    <section className="web-card today-preview"><CardHead eyebrow="HÔM NAY" title="Lịch uống thuốc"/><div className="dose-table-head"><span>THỜI GIAN</span><span>THUỐC & LIỀU DÙNG</span><span>TRẠNG THÁI</span><span>THAO TÁC</span></div><div className="dose-list web-list">{doses.length ? doses.slice(0, 4).map((dose) => <DoseCard key={dose.scheduled_dose_id} dose={dose} busy={busyId === dose.scheduled_dose_id} onAction={onAction}/>) : <div className="patient-empty">Hôm nay chưa có lịch thuốc.</div>}</div></section>
    <p className="patient-safety-note"><Icon name="shield" size={15}/> Không tự ý đổi liều hoặc uống bù. Nếu có vấn đề, hãy liên hệ bác sĩ điều trị.</p>
  </>;
}

function Kpi({ icon, tone, label, value, detail }: { icon: IconName; tone: string; label: string; value: string | number; detail: string }) { return <article><span className={`kpi-icon ${tone}`}><Icon name={icon}/></span><div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div></article>; }

function CardHead({ eyebrow, title, action, onAction }: { eyebrow: string; title: string; action?: string; onAction?: () => void }) { return <div className="web-card-head"><div><span className="section-eyebrow">{eyebrow}</span><h2>{title}</h2></div>{action && <button onClick={onAction}>{action}</button>}</div>; }
