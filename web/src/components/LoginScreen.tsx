import { useState } from "react";

import { ApiError, api } from "../api";
import { sessionFromTokens, setSession } from "../session";
import type { AuthTokenResponse } from "../types";

/**
 * Cổng đăng nhập của portal. Mọi endpoint trong api-contract.md (trừ
 * /auth/login và /auth/refresh) đều đòi Bearer token, nên chưa đăng nhập thì
 * portal không gọi được gì — App chỉ render phần còn lại sau khi có phiên.
 */
export default function LoginScreen() {
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Backend đánh dấu is_first_login: phải đổi PIN trước khi dùng portal.
  const [pendingTokens, setPendingTokens] = useState<AuthTokenResponse | null>(null);
  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");

  async function submitLogin(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      const tokens = await api.login(phone.trim(), password);

      if (tokens.user.role !== "DOCTOR" && tokens.user.role !== "ADMIN" && tokens.user.role !== "PATIENT") {
        setError("Tài khoản này chưa có quyền truy cập web RemindRx.");
        return;
      }

      if (tokens.is_first_login) {
        // Giữ token trong màn hình; commit session sau khi PIN mới thành công
        // để App không unmount LoginScreen giữa chừng.
        setPendingTokens(tokens);
        return;
      }

      setSession(sessionFromTokens(tokens));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không đăng nhập được");
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
      await api.changePassword(password, newPin, tokens.access_token);
      setSession(sessionFromTokens(tokens));
      setPendingTokens(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không đổi được mã PIN");
    } finally {
      setBusy(false);
    }
  }

  if (pendingTokens) {
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

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submitLogin}>
        <div className="card-head">
          <h2>RemindRx</h2>
        </div>
        <div className="card-body">
          <p className="rail-note">Đăng nhập bằng số điện thoại và mã PIN được cấp.</p>

          <label>
            Số điện thoại
            <input
              type="tel"
              autoComplete="username"
              placeholder="0901234567"
              required
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
            />
          </label>

          <label>
            Mã PIN
            <input
              type="password"
              autoComplete="current-password"
              inputMode="numeric"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {error && (
            <div className="errors">
              <b>{error}</b>
            </div>
          )}

          <div className="row-actions">
            <button className="btn primary" type="submit" disabled={busy}>
              {busy ? "Đang đăng nhập…" : "Đăng nhập"}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
