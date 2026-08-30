// Service worker for handling background FCM push notifications
importScripts('https://www.gstatic.com/firebasejs/10.13.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.13.0/firebase-messaging-compat.js');

firebase.initializeApp({
  apiKey: "AIzaSyDg2RFd1p1D9oNoV1g0hwyV34uICeYhO_k",
  authDomain: "remindrx-13aad.firebaseapp.com",
  projectId: "remindrx-13aad",
  storageBucket: "remindrx-13aad.firebasestorage.app",
  messagingSenderId: "943248823390",
  appId: "1:943248823390:web:remindrx",
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title = payload.notification?.title || "Nhắc nhở uống thuốc";
  const options = {
    body: payload.notification?.body || "Đã đến giờ uống thuốc theo lịch của bạn.",
    icon: "/favicon.ico",
    badge: "/favicon.ico",
    data: payload.data || {},
  };
  self.registration.showNotification(title, options);
});
