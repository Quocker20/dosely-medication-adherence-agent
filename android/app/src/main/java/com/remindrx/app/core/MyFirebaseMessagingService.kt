package com.remindrx.app.core

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.remindrx.app.MainActivity
import com.remindrx.app.data.repository.AuthRepository
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MyFirebaseMessagingService : FirebaseMessagingService() {

    @Inject
    lateinit var authRepository: AuthRepository

    // -------------------------------------------------------------------------
    // B2. Firebase cấp / đổi token → Gửi lên Backend ngay lập tức
    // -------------------------------------------------------------------------
    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d("FCM_TOKEN", "FCM Token mới: $token")

        CoroutineScope(Dispatchers.IO).launch {
            authRepository.registerDeviceToken(
                fcmToken = token,
                deviceName = android.os.Build.MODEL,
            )
        }
    }

    // -------------------------------------------------------------------------
    // B6. Worker gửi FCM → Android hiển thị thông báo nhắc uống thuốc
    // -------------------------------------------------------------------------
    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)
        Log.d("FCM_MSG", "Nhận notification từ: ${remoteMessage.from}")

        val title = remoteMessage.notification?.title
            ?: remoteMessage.data["title"]
            ?: "Nhắc nhở uống thuốc"
        val body = remoteMessage.notification?.body
            ?: remoteMessage.data["body"]
            ?: "Đến giờ uống thuốc rồi!"

        ensureNotificationChannel()
        showNotification(title, body)
    }

    private fun ensureNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Nhắc nhở uống thuốc",
            NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Thông báo nhắc nhở lịch uống thuốc từ RemindRx"
            enableVibration(true)
        }
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.createNotificationChannel(channel)
    }

    private fun showNotification(title: String, body: String) {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .build()

        NotificationManagerCompat.from(this)
            .notify(NOTIFICATION_ID, notification)
    }

    companion object {
        private const val CHANNEL_ID = "remindrx_reminders"
        private const val NOTIFICATION_ID = 1001
    }
}
