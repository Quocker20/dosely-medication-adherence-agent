package com.remindrx.app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.firebase.messaging.FirebaseMessaging
import com.remindrx.app.data.repository.AuthRepository
import com.remindrx.app.navigation.RemindRxApp
import com.remindrx.app.ui.theme.RemindRxTheme
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    @Inject
    lateinit var authRepository: AuthRepository

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            Log.d("NOTIFICATION_PERMISSION", "POST_NOTIFICATIONS permission granted")
        } else {
            Log.w("NOTIFICATION_PERMISSION", "POST_NOTIFICATIONS permission denied by user")
        }
    }

    private fun askNotificationPermission() {
        // Only required for API level >= 33 (TIRAMISU)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(
                    this,
                    Manifest.permission.POST_NOTIFICATIONS
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                requestPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Xin quyền gửi thông báo trên Android 13+
        askNotificationPermission()

        // B1 & B2: Lấy FCM token → Đồng bộ lên Backend khi App mở
        // Đảm bảo mọi thiết bị luôn có token mới nhất trong user_devices
        FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
            if (!task.isSuccessful) {
                Log.e("FCM_TOKEN", "Fetching FCM registration token failed", task.exception)
                return@addOnCompleteListener
            }
            val token = task.result
            Log.d("FCM_TOKEN", "Token: $token")

            lifecycleScope.launch(Dispatchers.IO) {
                authRepository.registerDeviceToken(
                    fcmToken = token,
                    deviceName = android.os.Build.MODEL,
                )
            }
        }

        setContent {
            RemindRxTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    RemindRxApp()
                }
            }
        }
    }
}
