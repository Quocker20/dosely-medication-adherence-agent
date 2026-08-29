package com.remindrx.app.data.repository

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.annotation.VisibleForTesting
import dagger.hilt.android.qualifiers.ApplicationContext
import java.nio.ByteBuffer
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Persists the authenticated patient session and exposes it as observable state.
 *
 * Session values are encrypted with an AES-GCM key held by Android Keystore. The
 * preference file only contains ciphertext, so process death does not log the
 * patient out and restoring a copied preference file on another device cannot
 * reveal or reuse its tokens.
 */
@Singleton
class SessionStore @VisibleForTesting internal constructor(
    private val persistence: SessionPersistence,
) {
    @Inject
    constructor(@ApplicationContext context: Context) : this(
        AndroidKeystoreSessionPersistence(context.applicationContext),
    )

    private val mutableSession = MutableStateFlow(persistence.read())
    val session: StateFlow<AuthSession?> = mutableSession.asStateFlow()

    val accessToken: String?
        get() = mutableSession.value?.accessToken

    val refreshToken: String?
        get() = mutableSession.value?.refreshToken

    val patientId: String?
        get() = mutableSession.value?.patientId

    val mustChangePassword: Boolean?
        get() = mutableSession.value?.mustChangePassword

    val needOnboarding: Boolean?
        get() = mutableSession.value?.needOnboarding

    val phone: String?
        get() = mutableSession.value?.phone

    @Synchronized
    fun update(session: AuthSession) {
        persistence.write(session)
        mutableSession.value = session
    }

    /**
     * Atomically rotates a token pair only while [expected] is still the active
     * session. A logout or a newer login therefore always wins over an older
     * in-flight refresh response.
     */
    @Synchronized
    internal fun updateIfCurrent(expected: AuthSession, updated: AuthSession): Boolean {
        if (mutableSession.value != expected) return false
        persistence.write(updated)
        mutableSession.value = updated
        return true
    }

    /**
     * Always clears the in-process session, even if the backing preference file
     * is temporarily unavailable. This prevents a rejected token being reused.
     */
    @Synchronized
    fun clear() {
        runCatching { persistence.clear() }
        mutableSession.value = null
    }

    /** Clears a rejected session without deleting credentials written by a newer login. */
    @Synchronized
    internal fun clearIfCurrent(expected: AuthSession): Boolean {
        if (mutableSession.value != expected) return false
        runCatching { persistence.clear() }
        mutableSession.value = null
        return true
    }

    fun requirePatientId(): String =
        patientId ?: error("Chưa đăng nhập: không có patientId trong phiên làm việc.")
}

@VisibleForTesting
internal interface SessionPersistence {
    fun read(): AuthSession?
    fun write(session: AuthSession)
    fun clear()
}

private class AndroidKeystoreSessionPersistence(
    context: Context,
) : SessionPersistence {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    override fun read(): AuthSession? {
        if (!preferences.contains(KEY_ACCESS_TOKEN)) return null

        return runCatching {
            AuthSession(
                accessToken = requireValue(KEY_ACCESS_TOKEN),
                refreshToken = requireValue(KEY_REFRESH_TOKEN),
                patientId = requireValue(KEY_PATIENT_ID),
                mustChangePassword = requireValue(KEY_MUST_CHANGE_PASSWORD).toBooleanStrict(),
                needOnboarding = requireValue(KEY_NEED_ONBOARDING).toBooleanStrict(),
                phone = requireValue(KEY_PHONE),
            )
        }.getOrElse {
            // A partial/corrupt restore must never leave a half-valid session.
            preferences.edit().clear().commit()
            null
        }
    }

    override fun write(session: AuthSession) {
        // Encrypt everything before editing so the preference update is atomic.
        val encrypted = mapOf(
            KEY_ACCESS_TOKEN to encrypt(KEY_ACCESS_TOKEN, session.accessToken),
            KEY_REFRESH_TOKEN to encrypt(KEY_REFRESH_TOKEN, session.refreshToken),
            KEY_PATIENT_ID to encrypt(KEY_PATIENT_ID, session.patientId),
            KEY_MUST_CHANGE_PASSWORD to encrypt(KEY_MUST_CHANGE_PASSWORD, session.mustChangePassword.toString()),
            KEY_NEED_ONBOARDING to encrypt(KEY_NEED_ONBOARDING, session.needOnboarding.toString()),
            KEY_PHONE to encrypt(KEY_PHONE, session.phone),
        )
        val editor = preferences.edit()
        encrypted.forEach(editor::putString)
        check(editor.commit()) { "Không thể lưu phiên đăng nhập an toàn." }
    }

    override fun clear() {
        check(preferences.edit().clear().commit()) { "Không thể xóa phiên đăng nhập." }
    }

    private fun requireValue(name: String): String {
        val encrypted = requireNotNull(preferences.getString(name, null))
        return decrypt(name, encrypted)
    }

    private fun encrypt(name: String, plaintext: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        cipher.updateAAD(name.toByteArray(Charsets.UTF_8))
        val ciphertext = cipher.doFinal(plaintext.toByteArray(Charsets.UTF_8))
        val payload = ByteBuffer.allocate(2 + cipher.iv.size + ciphertext.size)
            .put(FORMAT_VERSION)
            .put(cipher.iv.size.toByte())
            .put(cipher.iv)
            .put(ciphertext)
            .array()
        return Base64.encodeToString(payload, Base64.NO_WRAP)
    }

    private fun decrypt(name: String, encoded: String): String {
        val payload = Base64.decode(encoded, Base64.NO_WRAP)
        require(payload.size >= 2) { "Dữ liệu phiên không hợp lệ." }
        val buffer = ByteBuffer.wrap(payload)
        require(buffer.get() == FORMAT_VERSION) { "Phiên bản dữ liệu phiên không được hỗ trợ." }
        val ivSize = buffer.get().toInt() and 0xff
        require(ivSize in 12..16 && buffer.remaining() > ivSize) { "Dữ liệu phiên không hợp lệ." }
        val iv = ByteArray(ivSize).also(buffer::get)
        val ciphertext = ByteArray(buffer.remaining()).also(buffer::get)

        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
        cipher.updateAAD(name.toByteArray(Charsets.UTF_8))
        return cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
    }

    private fun getOrCreateKey(): SecretKey = synchronized(KEY_LOCK) {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey) ?: KeyGenerator
            .getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
            .apply {
                init(
                    KeyGenParameterSpec.Builder(
                        KEY_ALIAS,
                        KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                    )
                        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                        .setKeySize(256)
                        .setRandomizedEncryptionRequired(true)
                        .build(),
                )
            }
            .generateKey()
    }

    private companion object {
        const val PREFERENCES_NAME = "remindrx_encrypted_session"
        const val KEY_ALIAS = "remindrx_session_aes_key_v1"
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val GCM_TAG_BITS = 128
        const val KEY_ACCESS_TOKEN = "access_token"
        const val KEY_REFRESH_TOKEN = "refresh_token"
        const val KEY_PATIENT_ID = "patient_id"
        const val KEY_MUST_CHANGE_PASSWORD = "must_change_password"
        const val KEY_NEED_ONBOARDING = "need_onboarding"
        const val KEY_PHONE = "phone"
        val FORMAT_VERSION: Byte = 1
        val KEY_LOCK = Any()
    }
}
