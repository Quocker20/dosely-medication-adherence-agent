import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../../../api";
import type { CaregiverLinkDetail } from "../../../types";
import Icon from "./Icon";

interface Props {
  patientId: string;
  onNotice: (message: string) => void;
}

export default function CaregiverView({ patientId, onNotice }: Props) {
  const [caregivers, setCaregivers] = useState<CaregiverLinkDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [phone, setPhone] = useState("");
  const [relationship, setRelationship] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [createdInvite, setCreatedInvite] = useState<{
    linkCode: string;
    telegramDeepLink: string | null;
    phone: string;
    relationship: string | null;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const loadCaregivers = useCallback(async () => {
    try {
      const data = await api.getCaregivers(patientId);
      setCaregivers(data);
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Không tải được danh sách người chăm sóc.");
    }
  }, [patientId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadCaregivers().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [loadCaregivers]);

  const normalizedPhone = phone.trim().replace(/\s+/g, "");
  const canAdd = /^\+?[0-9]{9,15}$/.test(normalizedPhone) && !adding;

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!canAdd) return;
    setAdding(true);
    setError(null);
    try {
      const created = await api.createCaregiver(patientId, {
        caregiver_phone: normalizedPhone,
        relationship: relationship.trim() || null,
      });
      setPhone("");
      setRelationship("");
      if (created.link_code) {
        setCreatedInvite({
          linkCode: created.link_code,
          telegramDeepLink: created.telegram_deep_link,
          phone: created.phone,
          relationship: created.relationship,
        });
      }
      onNotice("Đã tạo liên kết người chăm sóc thành công.");
      await loadCaregivers();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Không thêm được người chăm sóc.");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(linkId: string) {
    if (!window.confirm("Bạn có chắc chắn muốn gỡ liên kết người chăm sóc này không? Người thân sẽ không còn nhận được thông báo.")) {
      return;
    }
    setDeletingId(linkId);
    try {
      await api.deleteCaregiver(patientId, linkId);
      onNotice("Đã gỡ người chăm sóc.");
      await loadCaregivers();
    } catch (cause) {
      onNotice(cause instanceof ApiError ? cause.message : "Không gỡ được người chăm sóc.");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleCopy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      onNotice("Đã sao chép link mời Telegram vào bộ nhớ tạm!");
      setTimeout(() => setCopied(false), 2500);
    } catch {
      onNotice("Không thể tự động sao chép, vui lòng bôi đen và sao chép thủ công.");
    }
  }

  return (
    <div className="caregiver-page" style={{ display: "flex", flexDirection: "column", gap: "20px", maxWidth: "920px" }}>
      {/* Header card */}
      <section className="web-card" style={{ padding: "24px 28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <span className="section-eyebrow">NGƯỜI GIÁM HỘ & BẢO HỘ SỨC KHỎE</span>
            <h2 style={{ fontSize: "21px", marginTop: "4px", color: "var(--p-ink)" }}>Người chăm sóc của bạn</h2>
            <p style={{ color: "var(--p-muted)", fontSize: "13px", marginTop: "4px", maxWidth: "600px", lineHeight: "1.5" }}>
              Liên kết người thân để tự động nhận thông báo cảnh báo khẩn cấp (SOS), báo cáo tuân thủ dùng thuốc định kỳ và cảnh báo khi quên liều qua Telegram Bot.
            </p>
            <p style={{ color: "var(--p-primary)", fontSize: "12.5px", fontWeight: 600, marginTop: "10px", margin: "10px 0 0" }}>
              💡 <b>Cách liên kết nhanh:</b> 1. Nhập SĐT người thân ➔ 2. Lấy link mời ➔ 3. Gửi cho người thân bấm START trên bot để kích hoạt.
            </p>
          </div>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 14px",
              borderRadius: "999px",
              background: "var(--p-primary-tint)",
              color: "var(--p-primary)",
              fontSize: "12px",
              fontWeight: 700,
              border: "1px solid var(--p-border)",
            }}
          >
            <Icon name="send" size={16} />
            <span>Kênh: Telegram Bot (@Dosely_bot)</span>
          </div>
        </div>
      </section>

      {/* Invite newly created banner */}
      {createdInvite && (
        <section
          className="web-card"
          style={{
            padding: "24px",
            background: "var(--p-primary-tint)",
            border: "1px solid var(--p-primary)",
            position: "relative",
          }}
        >
          <button
            onClick={() => setCreatedInvite(null)}
            style={{
              position: "absolute",
              top: "14px",
              right: "14px",
              border: 0,
              background: "transparent",
              color: "var(--p-muted)",
              cursor: "pointer",
              fontSize: "16px",
              fontWeight: 700,
            }}
            title="Đóng thông báo này"
          >
            ✕
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", color: "var(--p-primary)" }}>
            <Icon name="send" size={20} />
            <strong style={{ fontSize: "16px" }}>Mã liên kết Telegram mới được tạo</strong>
          </div>
          <p style={{ color: "var(--p-ink)", fontSize: "13px", margin: "8px 0 16px" }}>
            Hãy gửi liên kết này cho <b>{createdInvite.relationship || "người thân"}</b> ({createdInvite.phone}). Người thân chỉ cần mở link và bấm <b>START</b> trên Telegram để bắt đầu nhận thông báo.
          </p>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "14px",
              padding: "12px 18px",
              background: "var(--surface, #ffffff)",
              border: "1px solid var(--p-border)",
              borderRadius: "10px",
              flexWrap: "wrap",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
              <span style={{ fontSize: "12px", color: "var(--p-muted)", fontWeight: 600 }}>Mã kết nối:</span>
              <span
                style={{
                  fontFamily: "var(--mono, monospace)",
                  fontSize: "20px",
                  fontWeight: 800,
                  letterSpacing: "0.1em",
                  color: "var(--p-primary)",
                }}
              >
                {createdInvite.linkCode}
              </span>
            </div>

            {createdInvite.telegramDeepLink && (
              <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                <a
                  href={createdInvite.telegramDeepLink}
                  target="_blank"
                  rel="noreferrer"
                  className="btn primary sm"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    textDecoration: "none",
                  }}
                >
                  <Icon name="external-link" size={14} />
                  <span>Mở Telegram</span>
                </a>
                <button
                  type="button"
                  onClick={() => handleCopy(createdInvite.telegramDeepLink!)}
                  className="btn ghost sm"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <Icon name="copy" size={14} />
                  <span>{copied ? "Đã sao chép!" : "Sao chép link mời"}</span>
                </button>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Add form */}
      <section className="web-card" style={{ padding: "24px 28px" }}>
        <h3 style={{ fontSize: "16px", color: "var(--p-ink)", marginBottom: "16px" }}>Thêm người chăm sóc mới</h3>
        <form onSubmit={handleAdd} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr)) auto", gap: "14px", alignItems: "end" }}>
          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 700, color: "var(--p-muted)", marginBottom: "6px" }}>
              Số điện thoại <span style={{ color: "var(--p-danger)" }}>*</span>
            </label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Ví dụ: 0901234567"
              disabled={adding}
              style={{
                width: "100%",
                padding: "10px 14px",
                borderRadius: "9px",
                border: "1px solid var(--p-border)",
                background: "var(--surface, #ffffff)",
                color: "var(--p-ink)",
                fontSize: "13.5px",
                fontFamily: "inherit",
              }}
            />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 700, color: "var(--p-muted)", marginBottom: "6px" }}>
              Mối quan hệ
            </label>
            <input
              type="text"
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
              placeholder="Ví dụ: Con gái, Vợ, Chồng..."
              disabled={adding}
              style={{
                width: "100%",
                padding: "10px 14px",
                borderRadius: "9px",
                border: "1px solid var(--p-border)",
                background: "var(--surface, #ffffff)",
                color: "var(--p-ink)",
                fontSize: "13.5px",
                fontFamily: "inherit",
              }}
            />
          </div>
          <button
            type="submit"
            className="btn primary"
            disabled={!canAdd}
            style={{
              height: "42px",
              padding: "0 22px",
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              fontWeight: 700,
              fontSize: "13px",
              whiteSpace: "nowrap",
            }}
          >
            {adding ? "Đang tạo liên kết…" : "Thêm người chăm sóc"}
          </button>
        </form>
        {error && (
          <p style={{ color: "var(--p-danger)", fontSize: "12.5px", marginTop: "12px", background: "var(--p-danger-tint)", padding: "8px 12px", borderRadius: "8px" }}>
            {error}
          </p>
        )}
      </section>

      {/* Caregivers List */}
      <section className="web-card" style={{ padding: "24px 28px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "18px" }}>
          <h3 style={{ fontSize: "16px", color: "var(--p-ink)", margin: 0 }}>Danh sách người thân đã liên kết</h3>
          <span style={{ fontSize: "12px", color: "var(--p-muted)" }}>{caregivers.length} người</span>
        </div>

        {loading ? (
          <p style={{ color: "var(--p-muted)", fontSize: "13px", padding: "20px 0", textAlign: "center" }}>
            Đang tải danh sách người chăm sóc…
          </p>
        ) : caregivers.length === 0 ? (
          <div
            style={{
              padding: "36px 20px",
              textAlign: "center",
              borderRadius: "12px",
              border: "1px dashed var(--p-border)",
              color: "var(--p-muted)",
              fontSize: "13px",
            }}
          >
            <div style={{ display: "inline-grid", placeItems: "center", width: "48px", height: "48px", borderRadius: "50%", background: "var(--p-primary-tint)", color: "var(--p-primary)", marginBottom: "10px" }}>
              <Icon name="users" size={24} />
            </div>
            <p style={{ fontWeight: 600, color: "var(--p-ink)", margin: "0 0 4px" }}>Chưa có người chăm sóc nào</p>
            <p style={{ margin: 0 }}>Điền số điện thoại ở trên để tạo liên kết Telegram gửi cho người thân.</p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {caregivers.map((cg) => {
              const isActive = cg.status === "ACTIVE";
              const isBlocked = cg.status === "BLOCKED";
              const isPending = cg.status === "PENDING";

              return (
                <div
                  key={cg.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "16px 20px",
                    borderRadius: "12px",
                    border: "1px solid var(--p-border)",
                    background: "var(--surface, #ffffff)",
                    gap: "16px",
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
                    <div
                      style={{
                        width: "42px",
                        height: "42px",
                        borderRadius: "10px",
                        display: "grid",
                        placeItems: "center",
                        background: isActive
                          ? "var(--p-success-tint)"
                          : isBlocked
                          ? "var(--p-danger-tint)"
                          : "var(--p-warning-tint)",
                        color: isActive
                          ? "var(--p-success)"
                          : isBlocked
                          ? "var(--p-danger)"
                          : "var(--p-warning)",
                      }}
                    >
                      <Icon name="users" size={20} />
                    </div>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                        <strong style={{ fontSize: "14.5px", color: "var(--p-ink)" }}>
                          {cg.relationship || "Người chăm sóc"}
                        </strong>
                        <span
                          style={{
                            fontSize: "11px",
                            fontWeight: 700,
                            padding: "3px 8px",
                            borderRadius: "999px",
                            background: isActive
                              ? "var(--p-success-tint)"
                              : isBlocked
                              ? "var(--p-danger-tint)"
                              : "var(--p-warning-tint)",
                            color: isActive
                              ? "var(--p-success)"
                              : isBlocked
                              ? "var(--p-danger)"
                              : "var(--p-warning)",
                            border: `1px solid ${
                              isActive
                                ? "var(--ok-line, #c2e6d1)"
                                : isBlocked
                                ? "var(--crit-line, #f5c6c0)"
                                : "var(--warn-line, #f0dbab)"
                            }`,
                          }}
                        >
                          {isActive
                            ? "Đang hoạt động"
                            : isBlocked
                            ? "Đã chặn bot"
                            : "Chờ người thân bấm Start"}
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: "16px", marginTop: "4px", fontSize: "12px", color: "var(--p-muted)", flexWrap: "wrap" }}>
                        <span>SĐT: <b style={{ color: "var(--p-ink)" }}>{cg.phone}</b></span>
                        <span>Kênh: <b>Telegram Bot</b></span>
                        {cg.telegram_bound_at ? (
                          <span>Đã kết nối: {new Date(cg.telegram_bound_at).toLocaleDateString("vi-VN")}</span>
                        ) : (
                          <span>Tạo lúc: {new Date(cg.created_at).toLocaleDateString("vi-VN")}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    {isPending && cg.telegram_deep_link && (
                      <button
                        type="button"
                        onClick={() => handleCopy(cg.telegram_deep_link!)}
                        className="btn ghost sm"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          fontSize: "12px",
                        }}
                        title="Sao chép lại link mời Telegram"
                      >
                        <Icon name="copy" size={14} />
                        <span>Sao chép link</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDelete(cg.id)}
                      disabled={deletingId === cg.id}
                      className="btn ghost sm"
                      style={{
                        color: "var(--p-danger)",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "6px",
                        fontSize: "12px",
                      }}
                      title="Gỡ liên kết người chăm sóc"
                    >
                      <Icon name="trash" size={15} />
                      <span>{deletingId === cg.id ? "Đang gỡ…" : "Gỡ liên kết"}</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
