import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { getMessaging, isSupported, type Messaging } from "firebase/messaging";

export const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "dosely-13aad.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "dosely-13aad",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "dosely-13aad.firebasestorage.app",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "943248823390",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "",
};

export const FIREBASE_VAPID_KEY = import.meta.env.VITE_FIREBASE_VAPID_KEY || "";

let appInstance: FirebaseApp | null = null;

export function getFirebaseApp(): FirebaseApp | null {
  if (appInstance) return appInstance;
  if (!firebaseConfig.apiKey || !firebaseConfig.projectId) {
    return null;
  }
  const existing = getApps();
  if (existing.length > 0) {
    appInstance = existing[0];
  } else {
    appInstance = initializeApp(firebaseConfig);
  }
  return appInstance;
}

export async function getMessagingIfSupported(): Promise<Messaging | null> {
  try {
    const supported = await isSupported();
    if (!supported) return null;
    const app = getFirebaseApp();
    if (!app) return null;
    return getMessaging(app);
  } catch {
    return null;
  }
}
