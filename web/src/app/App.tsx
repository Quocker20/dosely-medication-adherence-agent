import { useEffect, useState } from "react";

import LoginScreen from "../components/auth/LoginScreen";
import HomePage from "../components/shared/HomePage";
import AdminPortal from "../pages/admin/AdminPortal";
import DoctorPortal from "../pages/doctor/DoctorPortal";
import PatientPortal from "../pages/patient/PatientPortal";
import { getSession, setSession, subscribe, type Session } from "../session";

/**
 * Router cấp cao nhất: chọn portal theo role. Không có thư viện router nào —
 * pathname chỉ được đồng bộ cho đẹp URL, mọi điều hướng trong portal là state.
 */
export default function App() {
  const [session, setLocalSession] = useState<Session | null>(getSession);
  const [, setPathname] = useState(() => window.location.pathname);
  // Cổng trước đăng nhập: trang chủ trước, form đăng nhập chỉ hiện sau khi bấm nút.
  const [showLogin, setShowLogin] = useState(false);

  // api/client.ts tự xoá phiên khi refresh token hết hạn — App phải nghe để quay về màn đăng nhập.
  useEffect(() => subscribe(setLocalSession), []);

  // Session rớt về null (hết hạn hoặc logout) thì luôn quay lại trang chủ,
  // không văng thẳng vào form đăng nhập.
  useEffect(() => {
    if (!session) setShowLogin(false);
  }, [session]);

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (!session) return;
    const expected = session.user.role === "ADMIN" ? "/admin/" : session.user.role === "PATIENT" ? "/patient/" : "/doctor/";
    if (window.location.pathname !== expected) {
      window.history.replaceState({}, "", expected);
      setPathname(expected);
    }
  }, [session, setPathname]);

  if (!session) {
    return showLogin ? (
      <LoginScreen onBack={() => setShowLogin(false)} />
    ) : (
      <HomePage onLogin={() => setShowLogin(true)} />
    );
  }
  if (session.user.role === "ADMIN") return <AdminPortal session={session} />;
  if (session.user.role === "DOCTOR") return <DoctorPortal session={session} />;
  if (session.user.role === "PATIENT") return <PatientPortal session={session} />;
  // Role không hợp lệ nhưng vẫn có session (vd. dữ liệu localStorage cũ) —
  // xoá phiên và quay lại trang chủ thay vì render vỡ.
  return <HomePage onLogin={() => setSession(null)} />;
}
