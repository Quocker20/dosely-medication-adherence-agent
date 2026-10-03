package com.dosely.app.data.repository

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SessionStoreTest {
    @Test
    fun `session survives store recreation and exposes every auth field`() {
        val persistence = FakeSessionPersistence()
        val expected = testSession()

        SessionStore(persistence).update(expected)
        val recreated = SessionStore(persistence)

        assertEquals(expected, recreated.session.value)
        assertEquals(expected.accessToken, recreated.accessToken)
        assertEquals(expected.refreshToken, recreated.refreshToken)
        assertEquals(expected.patientId, recreated.requirePatientId())
        assertEquals(expected.mustChangePassword, recreated.mustChangePassword)
        assertEquals(expected.needOnboarding, recreated.needOnboarding)
        assertEquals(expected.phone, recreated.phone)
    }

    @Test
    fun `clear removes both observable and persisted session`() {
        val persistence = FakeSessionPersistence(testSession())
        val store = SessionStore(persistence)

        store.clear()

        assertNull(store.session.value)
        assertNull(SessionStore(persistence).session.value)
    }
}

internal class FakeSessionPersistence(
    initial: AuthSession? = null,
) : SessionPersistence {
    private var stored = initial

    override fun read(): AuthSession? = stored

    override fun write(session: AuthSession) {
        stored = session
    }

    override fun clear() {
        stored = null
    }
}

internal fun testSession(
    accessToken: String = "access-old",
    refreshToken: String = "refresh-old",
    patientId: String = "patient-1",
    mustChangePassword: Boolean = true,
    needOnboarding: Boolean = true,
    phone: String = "+84901234567",
): AuthSession = AuthSession(
    accessToken = accessToken,
    refreshToken = refreshToken,
    patientId = patientId,
    mustChangePassword = mustChangePassword,
    needOnboarding = needOnboarding,
    phone = phone,
)
