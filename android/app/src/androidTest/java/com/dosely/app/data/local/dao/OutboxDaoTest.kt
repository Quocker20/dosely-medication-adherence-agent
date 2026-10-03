package com.dosely.app.data.local.dao

import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import com.dosely.app.data.local.DoselyDatabase
import com.dosely.app.data.local.entity.OutboxActionEntity
import com.dosely.app.data.local.entity.OutboxActionType
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

class OutboxDaoTest {
    private lateinit var database: DoselyDatabase
    private lateinit var dao: OutboxDao

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, DoselyDatabase::class.java).build()
        dao = database.outboxDao()
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun enqueue_coalescesPendingRoutineUpdatesPerPatient() = runBlocking {
        dao.enqueue(testAction("routine-1", OutboxActionType.UPDATE_ROUTINE, """{"wake":"06:30"}"""))
        dao.enqueue(testAction("routine-2", OutboxActionType.UPDATE_ROUTINE, """{"wake":"07:00"}"""))
        dao.enqueue(testAction("dose-1", OutboxActionType.RECORD_DOSE_ACTION, """{"dose":"dose-1"}"""))

        val pending = dao.observePending("patient-1").first()

        assertEquals(2, pending.size)
        assertEquals("routine-2", pending.first { it.actionType == OutboxActionType.UPDATE_ROUTINE }.id)
        assertEquals("dose-1", pending.first { it.actionType == OutboxActionType.RECORD_DOSE_ACTION }.id)
        assertEquals(2, dao.observePendingCount("patient-1").first())
    }

    private fun testAction(
        id: String,
        actionType: OutboxActionType,
        payloadJson: String,
    ) = OutboxActionEntity(
        id = id,
        patientId = "patient-1",
        actionType = actionType,
        payloadJson = payloadJson,
        createdAt = System.currentTimeMillis(),
    )
}
