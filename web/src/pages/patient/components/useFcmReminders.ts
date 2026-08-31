import { useCallback, useEffect, useRef, useState } from "react";
import { getToken, onMessage, type Unsubscribe } from "firebase/messaging";

import { api } from "../../../api";
import { FIREBASE_VAPID_KEY, getMessagingIfSupported } from "../../../firebase";

export interface DoseReminder {
  id: string;
  title: string;
  body: string;
  firedAt: string;
  read?: boolean;
}

const STORAGE_KEY_PREFIX = "remindrx_notif_history_";
const TOKEN_CACHE_KEY_PREFIX = "remindrx_fcm_token_";

function loadStoredHistory(patientId: string): DoseReminder[] {
  try {
    const raw = window.localStorage.getItem(`${STORAGE_KEY_PREFIX}${patientId}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveStoredHistory(patientId: string, history: DoseReminder[]): void {
  try {
    window.localStorage.setItem(`${STORAGE_KEY_PREFIX}${patientId}`, JSON.stringify(history.slice(0, 50)));
  } catch {
    /* Ignore localStorage quota or private mode issues */
  }
}

export function useFcmReminders(patientId: string, accessToken?: string) {
  const [active, setActive] = useState<DoseReminder[]>([]);
  const [history, setHistory] = useState<DoseReminder[]>(() => loadStoredHistory(patientId));
  const [unreadCount, setUnreadCount] = useState<number>(() => {
    const initial = loadStoredHistory(patientId);
    return initial.filter((item) => !item.read).length;
  });

  const isRegisteringRef = useRef(false);

  // Sync history changes to localStorage
  useEffect(() => {
    saveStoredHistory(patientId, history);
  }, [patientId, history]);

  const dismiss = useCallback((id: string) => {
    setActive((prev) => prev.filter((item) => item.id !== id));
  }, []);

  const markAllRead = useCallback(() => {
    setUnreadCount(0);
    setHistory((prev) =>
      prev.map((item) => (item.read ? item : { ...item, read: true })),
    );
  }, []);

  const registerToken = useCallback(async (forcedGranted?: boolean) => {
    if (isRegisteringRef.current) return;
    if (typeof window === "undefined" || !("Notification" in window)) return;
    const isGranted = forcedGranted || Notification.permission === "granted";
    if (!isGranted) return;
    if (!("serviceWorker" in navigator)) return;

    isRegisteringRef.current = true;
    try {
      const messaging = await getMessagingIfSupported();
      if (!messaging) return;

      const swRegistration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");
      const token = await getToken(messaging, {
        vapidKey: FIREBASE_VAPID_KEY || undefined,
        serviceWorkerRegistration: swRegistration,
      });

      if (token) {
        const cacheKey = `${TOKEN_CACHE_KEY_PREFIX}${patientId}`;
        const lastRegisteredToken = window.sessionStorage.getItem(cacheKey);
        if (lastRegisteredToken !== token) {
          const deviceName = `web-${navigator.userAgent.slice(0, 40)}`;
          await api.registerDeviceToken(token, deviceName, accessToken);
          window.sessionStorage.setItem(cacheKey, token);
        }
      }
    } catch {
      // Gracefully handle missing VAPID key / unsupported environment
    } finally {
      isRegisteringRef.current = false;
    }
  }, [patientId, accessToken]);

  const requestPermissionAndRegister = useCallback(async () => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    try {
      const permission = await Notification.requestPermission();
      if (permission === "granted") {
        await registerToken(true);
      }
    } catch {
      // User dismissed or blocked permission
    }
  }, [registerToken]);


  // Initial registration if permission was already granted
  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
      registerToken().catch(() => {});
    }
  }, [registerToken]);

  // Listen for foreground push messages
  useEffect(() => {
    let unsubscribe: Unsubscribe | null = null;
    let isMounted = true;

    getMessagingIfSupported().then((messaging) => {
      if (!messaging || !isMounted) return;

      unsubscribe = onMessage(messaging, (payload) => {
        const title = payload.notification?.title || payload.data?.title || "Nhắc nhở uống thuốc";
        const body = payload.notification?.body || payload.data?.body || "Đã đến giờ uống thuốc theo lịch của bạn.";
        const id = payload.messageId || `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
        const firedAt = new Date().toISOString();

        const reminder: DoseReminder = {
          id,
          title,
          body,
          firedAt,
          read: false,
        };

        setActive((prev) => [reminder, ...prev]);
        setHistory((prev) => [reminder, ...prev]);
        setUnreadCount((prev) => prev + 1);
      });
    }).catch(() => {});

    return () => {
      isMounted = false;
      if (unsubscribe) {
        unsubscribe();
      }
    };
  }, []);

  return {
    active,
    history,
    unreadCount,
    dismiss,
    markAllRead,
    requestPermissionAndRegister,
  };
}
