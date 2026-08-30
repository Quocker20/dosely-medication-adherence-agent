import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "../../../api";
import Icon from "./Icon";

export default function SosView({ patientId, onDone }: { patientId: string; onDone: (message: string) => void }) {
  const [holding, setHolding] = useState(false);
  const [holdProgress, setHoldProgress] = useState(0);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const animFrameRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);

  useEffect(() => {
    if (!holding || busy || sent) {
      setHoldProgress(0);
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
      return;
    }

    const DURATION = 3000;
    startTimeRef.current = performance.now();

    const frame = (now: number) => {
      if (!startTimeRef.current) return;
      const elapsed = now - startTimeRef.current;
      const progress = Math.min(100, (elapsed / DURATION) * 100);
      setHoldProgress(progress);

      if (elapsed < DURATION) {
        animFrameRef.current = requestAnimationFrame(frame);
      } else {
        setHolding(false);
        setBusy(true);
        api
          .triggerSos(patientId)
          .then(() => setSent(true))
          .catch((cause) => setError(cause instanceof ApiError ? cause.message : "Không gửi được cảnh báo SOS"))
          .finally(() => setBusy(false));
      }
    };

    animFrameRef.current = requestAnimationFrame(frame);

    return () => {
      if (animFrameRef.current !== null) {
        cancelAnimationFrame(animFrameRef.current);
        animFrameRef.current = null;
      }
    };
  }, [holding, busy, sent, patientId]);

  const radius = 75;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (holdProgress / 100) * circumference;

  return (
    <section className="sos-page">
      <div className="sos-info-panel">
        <span className="sos-shield">
          <Icon name="shield" size={28} />
        </span>
        <h2>Hỗ trợ khẩn cấp</h2>
        <p>Giữ nút SOS trong 3 giây. Hệ thống sẽ gửi cảnh báo tới đội ngũ chăm sóc và bác sĩ phụ trách.</p>
        <ul>
          <li>
            <Icon name="check" size={17} /> Ghi nhận cảnh báo trên hệ thống
          </li>
          <li>
            <Icon name="check" size={17} /> Thông báo tới bác sĩ phụ trách
          </li>
          <li>
            <Icon name="check" size={17} /> Theo dõi trạng thái xử lý
          </li>
        </ul>
        <div className="sos-disclaimer">
          <Icon name="alert" size={18} />
          <span>
            <b>Trong tình huống nguy hiểm tính mạng</b>Hãy gọi ngay số cấp cứu 115. SOS trong ứng dụng không thay thế
            dịch vụ cấp cứu.
          </span>
        </div>
      </div>
      <div className="sos-action-panel">
        <div
          className={`sos-button-wrapper ${holding ? "holding" : ""}`}
          onPointerDown={() => {
            if (!busy && !sent) setHolding(true);
          }}
          onPointerUp={() => setHolding(false)}
          onPointerLeave={() => setHolding(false)}
          onPointerCancel={() => setHolding(false)}
        >
          {holding && <div className="sos-pulse-ring" />}
          <svg className="sos-progress-svg" viewBox="0 0 172 172" aria-hidden="true">
            <circle
              className="sos-progress-fill"
              cx="86"
              cy="86"
              r={radius}
              style={{
                strokeDasharray: circumference,
                strokeDashoffset: holding ? strokeDashoffset : circumference,
              }}
            />
          </svg>
          <button className={`sos-button ${holding ? "holding" : ""}`} disabled={busy || sent} type="button">
            <span>{sent ? "ĐÃ GỬI" : busy ? "ĐANG GỬI" : "SOS"}</span>
            <small>
              {sent ? "CẢNH BÁO SOS" : busy ? "VUI LÒNG ĐỢI" : holding ? "ĐANG XÁC NHẬN" : "GIỮ ĐỂ GỬI"}
            </small>
          </button>
        </div>
        <h1>
          {sent
            ? "Cảnh báo SOS đã được gửi tới hệ thống"
            : busy
            ? "Đang gửi cảnh báo SOS…"
            : "Giữ nút 3 giây để gửi cảnh báo SOS"}
        </h1>
        <p>
          {sent
            ? "Hệ thống đã ghi nhận cảnh báo. Ứng dụng không tự gọi cấp cứu hoặc chia sẻ vị trí."
            : "Yêu cầu sẽ được chuyển tới hệ thống chăm sóc sau khi bạn xác nhận."}
        </p>
        {error && <b className="sos-error">{error}</b>}
        <button className="sos-cancel" onClick={() => onDone(sent ? "Đã gửi cảnh báo SOS" : "")}>
          {sent ? "Đóng" : "Huỷ"}
        </button>
      </div>
    </section>
  );
}


