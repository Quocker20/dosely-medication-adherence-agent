import { useState } from "react";

import { ApiError, api } from "../../api";
import PinDotInput from "./PinDotInput";
import { delay, MIN_STEP_DELAY_MS } from "./delay";
import { cleanPhoneNumber } from "./phone";
import { sessionFromTokens, setSession } from "../../session";
import type { AuthTokenResponse } from "../../types";

type Step = "phone" | "pin" | "changePin";

interface Props {
  /** Chỉ dùng ở bước "phone" — quay lại trang chủ. */
  onBack: () => void;
}

/**
 * Luồng đăng nhập 2 bước (số điện thoại -> mã PIN) + đổi PIN lần đầu.
 *
 * Backend không có endpoint tra số điện thoại riêng — POST /auth/login xác
 * thực phone+PIN cùng lúc trong một lời gọi (src/modules/auth/service.py),
 * và trả về đúng một thông báo lỗi chung cho cả hai trường hợp sai số/sai
 * PIN. Nên việc tách 2 bước ở đây thuần là UI phía client: dữ liệu chỉ thật
 * sự gửi lên backend ở bước nhập PIN.
 */
export default function LoginScreen({ onBack }: Props) {
  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Backend đánh dấu must_change_password: phải đổi PIN trước khi dùng portal.
  const [pendingTokens, setPendingTokens] = useState<AuthTokenResponse | null>(null);
  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");

  async function submitPhone(event: React.FormEvent) {
    event.preventDefault();
    const result = cleanPhoneNumber(phone);
    if (!result.ok) {
      setError(result.error);
      return;
    }

    setBusy(true);
    setError(null);
    await delay(MIN_STEP_DELAY_MS);
    setPhone(result.cleaned!);
    setStep("pin");
    setBusy(false);
  }

  function backToPhone() {
    setPin("");
    setError(null);
    setStep("phone");
  }

  async function submitPin(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      const [tokens] = await Promise.all([api.login(phone, pin), delay(MIN_STEP_DELAY_MS)]);

      if (tokens.user.role !== "DOCTOR" && tokens.user.role !== "ADMIN" && tokens.user.role !== "PATIENT") {
        setError("Tài khoản này chưa có quyền truy cập web RemindRx.");
        return;
      }

      if (tokens.must_change_password) {
        // Giữ token trong màn hình; commit session sau khi PIN mới thành công
        // để App không unmount LoginScreen giữa chừng.
        setPendingTokens(tokens);
        setStep("changePin");
        return;
      }

      setSession(sessionFromTokens(tokens));
    } catch (err) {
      if (err instanceof ApiError) {
        setPin("");
        setError(err.message);
      } else if (err instanceof TypeError) {
        setError("Không thể kết nối máy chủ, vui lòng kiểm tra kết nối và thử lại.");
      } else {
        setPin("");
        setError("Không đăng nhập được, vui lòng thử lại.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function submitChangePin(event: React.FormEvent) {
    event.preventDefault();
    const tokens = pendingTokens;
    if (!tokens) return;
    if (newPin !== confirmPin) {
      setError("Mã PIN nhập lại không khớp");
      return;
    }

    setBusy(true);
    setError(null);

    try {
      await api.changePassword(pin, newPin, tokens.access_token);
      setSession(sessionFromTokens(tokens));
      setPendingTokens(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không đổi được mã PIN");
    } finally {
      setBusy(false);
    }
  }

  if (step === "changePin" && pendingTokens) {
    return (
      <div className="login-wrap">
        <form className="card login-card" onSubmit={submitChangePin}>
          <div className="card-head">
            <h2>Đổi mã PIN lần đầu</h2>
          </div>
          <div className="card-body">
            <p className="rail-note">
              Tài khoản <b>{pendingTokens.user.phone}</b> đang dùng mã PIN tạm. Đặt mã mới (6 chữ số) để tiếp tục.
            </p>

            <label>
              Mã PIN mới
              <input
                type="password"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                required
                value={newPin}
                onChange={(event) => setNewPin(event.target.value)}
              />
            </label>

            <label>
              Nhập lại mã PIN mới
              <input
                type="password"
                inputMode="numeric"
                pattern="\d{6}"
                maxLength={6}
                required
                value={confirmPin}
                onChange={(event) => setConfirmPin(event.target.value)}
              />
            </label>

            {error && (
              <div className="errors">
                <b>{error}</b>
              </div>
            )}

            <div className="row-actions">
              <button className="btn primary" type="submit" disabled={busy}>
                {busy ? "Đang lưu…" : "Lưu mã PIN & vào portal"}
              </button>
              <button
                className="btn ghost"
                type="button"
                onClick={() => {
                  setSession(null);
                  setPendingTokens(null);
                  setError(null);
                  setStep("phone");
                  setPhone("");
                  setPin("");
                }}
              >
                Huỷ
              </button>
            </div>
          </div>
        </form>
      </div>
    );
  }

  if (step === "pin") {
    return (
      <div className="login-wrap">
        <form className="card login-card" onSubmit={submitPin}>
          <div className="card-head">
            <h2>Nhập mã PIN</h2>
          </div>
          <div className="card-body">
            <div className="login-phone-display">
              <span>{phone}</span>
              <button className="link-btn" type="button" onClick={backToPhone}>
                Đổi số khác
              </button>
            </div>

            <label htmlFor="pin-input">Mã PIN</label>
            <PinDotInput id="pin-input" value={pin} onChange={setPin} autoFocus disabled={busy} />

            <span className="link-btn" aria-disabled="true">Quên mật khẩu?</span>

            {error && (
              <div className="errors">
                <b>{error}</b>
              </div>
            )}

            <div className="row-actions">
              <button className="btn primary" type="submit" disabled={pin.length < 6 || busy}>
                {busy ? "Đang đăng nhập…" : "Đăng nhập"}
              </button>
            </div>
          </div>
        </form>
      </div>
    );
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submitPhone}>
        <div className="card-head">
          <h2>RemindRx</h2>
        </div>
        <div className="card-body">
          <p className="rail-note">Nhập số điện thoại đã đăng ký để tiếp tục.</p>

          <label>
            Số điện thoại
            <input
              type="tel"
              autoComplete="username"
              placeholder="0901234567"
              autoFocus
              required
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </label>

          {error && (
            <div className="errors">
              <b>{error}</b>
            </div>
          )}

          <div className="row-actions">
            <button className="btn primary" type="submit" disabled={busy}>
              Tiếp tục
            </button>
          </div>

          <button className="link-btn login-back" type="button" onClick={onBack}>
            ← Trang chủ
          </button>
        </div>
      </form>
    </div>
  );
}
