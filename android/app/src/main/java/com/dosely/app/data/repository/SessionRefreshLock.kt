package com.dosely.app.data.repository

import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.sync.Mutex

/**
 * One lock for every refresh-token rotation (OkHttp Authenticator and realtime
 * sync's refreshSession), so a single-use refresh token is never spent twice.
 */
@Singleton
class SessionRefreshLock @Inject constructor() {
    val mutex = Mutex()
}
