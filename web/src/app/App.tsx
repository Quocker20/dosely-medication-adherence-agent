import { useEffect, useRef, useState } from "react";

import LoginScreen from "../components/auth/LoginScreen";
import HomePage from "../components/shared/HomePage";
import AdminPortal from "../pages/admin/AdminPortal";
import DoctorPortal from "../pages/doctor/DoctorPortal";
import PatientPortal from "../pages/patient/PatientPortal";
import { getPathname, navigate, subscribe as subscribeToRoute } from "../router";
import { getSession, setSession, subscribe, type Session } from "../session";

const roleRoutes = {
  ADMIN: { prefix: "admin", defaultTab: "overview" },
  DOCTOR: { prefix: "doctor", defaultTab: "dashboard" },
  PATIENT: { prefix: "patient", defaultTab: "dashboard" },
} as const;

const portalPrefixes: Set<string> = new Set(Object.values(roleRoutes).map(({ prefix }) => prefix));

function pathSegments(pathname: string): [string | undefined, string | undefined] {
  const [prefix, tab] = pathname.split("/").filter(Boolean);
  return [prefix, tab];
}

/** Router cấp cao nhất cho home, login và ba portal. */
export default function App() {
  const [session, setLocalSession] = useState<Session | null>(getSession);
  const [pathname, setPathname] = useState(getPathname);
  const previousSession = useRef<Session | null>(session);
  const [prefix, requestedTab] = pathSegments(pathname);
  const roleRoute = session ? roleRoutes[session.user.role as keyof typeof roleRoutes] : undefined;
  const isProtectedPortalRoute = prefix !== undefined && portalPrefixes.has(prefix);

  // api/client.ts tự xoá phiên khi refresh token hết hạn — App phải nghe để quay về màn đăng nhập.
  useEffect(() => subscribe(setLocalSession), []);
  useEffect(() => subscribeToRoute(setPathname), []);

  useEffect(() => {
    const previous = previousSession.current;
    previousSession.current = session;

    if (!previous && session && roleRoute) {
      navigate(`/${roleRoute.prefix}/${roleRoute.defaultTab}`);
    } else if (previous && !session) {
      // Logout/hết phiên luôn trở về trang chủ, không tự mở lại form đăng nhập.
      navigate("/");
    }
  }, [roleRoute, session]);

  useEffect(() => {
    if (session && !roleRoute) setSession(null);
  }, [roleRoute, session]);

  useEffect(() => {
    if (session && roleRoute && prefix !== roleRoute.prefix && prefix !== "login") {
      navigate(`/${roleRoute.prefix}/${roleRoute.defaultTab}`, { replace: true });
    }
  }, [prefix, roleRoute, session]);

  useEffect(() => {
    if (!session && isProtectedPortalRoute) navigate("/login", { replace: true });
  }, [isProtectedPortalRoute, session]);

  if (!session) {
    return pathname === "/login" || isProtectedPortalRoute ? (
      <LoginScreen onBack={() => navigate("/")} />
    ) : (
      <HomePage onLogin={() => navigate("/login")} />
    );
  }

  // Back từ portal về login vẫn hiển thị login thay vì tự động đá người dùng
  // quay lại portal; Forward sẽ đưa họ đến entry portal trước đó.
  if (pathname === "/login") return <LoginScreen onBack={() => navigate("/")} />;

  if (session.user.role === "ADMIN") {
    const view = requestedTab === "doctors" || requestedTab === "audit" ? requestedTab : "overview";
    return <AdminPortal session={session} view={view} onViewChange={(tab) => navigate(`/admin/${tab}`)} />;
  }
  if (session.user.role === "DOCTOR") {
    const view = ["dashboard", "patients", "alerts", "surveys", "rx"].includes(requestedTab ?? "")
      ? requestedTab as "dashboard" | "patients" | "alerts" | "surveys" | "rx"
      : "dashboard";
    return <DoctorPortal session={session} view={view} onViewChange={(tab) => navigate(`/doctor/${tab}`)} />;
  }
  if (session.user.role === "PATIENT") {
    const tab = ["dashboard", "schedule", "assistant", "survey", "sos"].includes(requestedTab ?? "")
      ? requestedTab as "dashboard" | "schedule" | "assistant" | "survey" | "sos"
      : "dashboard";
    return <PatientPortal session={session} tab={tab} onTabChange={(nextTab) => navigate(`/patient/${nextTab}`)} />;
  }

  // Role không hợp lệ nhưng vẫn có session (vd. dữ liệu localStorage cũ) —
  // xoá phiên và quay lại trang chủ thay vì render vỡ.
  return <HomePage onLogin={() => navigate("/login")} />;
}
