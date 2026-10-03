package com.dosely.app.data.repository

import com.dosely.app.data.local.dao.PatientCacheDao
import javax.inject.Inject

interface PatientReadableCacheCleaner {
    suspend fun clearReadableCache(patientId: String)
}

object NoOpPatientReadableCacheCleaner : PatientReadableCacheCleaner {
    override suspend fun clearReadableCache(patientId: String) = Unit
}

class RoomPatientReadableCacheCleaner @Inject constructor(
    private val patientCacheDao: PatientCacheDao,
) : PatientReadableCacheCleaner {
    override suspend fun clearReadableCache(patientId: String) {
        patientCacheDao.deleteReadableCacheForPatient(patientId)
    }
}
