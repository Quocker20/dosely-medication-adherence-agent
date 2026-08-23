package com.remindrx.app

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

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
