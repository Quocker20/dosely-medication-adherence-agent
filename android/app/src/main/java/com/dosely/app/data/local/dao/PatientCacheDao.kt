package com.dosely.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import com.dosely.app.data.DoseStatus
import com.dosely.app.data.local.entity.AdherenceSummaryEntity
import com.dosely.app.data.local.entity.DoseTodayEntity
import com.dosely.app.data.local.entity.MedicationEntity
import com.dosely.app.data.local.entity.RoutineItemEntity

@Dao
abstract class PatientCacheDao {
    @Query("SELECT * FROM routine_items WHERE patientId = :patientId ORDER BY key")
    abstract suspend fun getRoutine(patientId: String): List<RoutineItemEntity>

    @Query("SELECT * FROM doses_today WHERE patientId = :patientId AND scheduleDate = :scheduleDate ORDER BY time")
    abstract suspend fun getDoses(patientId: String, scheduleDate: String): List<DoseTodayEntity>

    @Query("SELECT * FROM medications WHERE patientId = :patientId ORDER BY name")
    abstract suspend fun getMedications(patientId: String): List<MedicationEntity>

    @Query(
        """
        SELECT * FROM adherence_summaries
        WHERE patientId = :patientId AND fromDate = :fromDate AND toDate = :toDate
        LIMIT 1
        """,
    )
    abstract suspend fun getAdherenceSummary(
        patientId: String,
        fromDate: String,
        toDate: String,
    ): AdherenceSummaryEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertRoutine(items: List<RoutineItemEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertDoses(doses: List<DoseTodayEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertMedications(medications: List<MedicationEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insertAdherenceSummary(summary: AdherenceSummaryEntity)

    @Query("DELETE FROM routine_items WHERE patientId = :patientId")
    abstract suspend fun deleteRoutine(patientId: String)

    @Query("DELETE FROM doses_today WHERE patientId = :patientId AND scheduleDate = :scheduleDate")
    abstract suspend fun deleteDoses(patientId: String, scheduleDate: String)

    @Query("DELETE FROM medications WHERE patientId = :patientId")
    abstract suspend fun deleteMedications(patientId: String)

    @Query("DELETE FROM adherence_summaries WHERE patientId = :patientId")
    abstract suspend fun deleteAdherenceSummaries(patientId: String)

    @Query("DELETE FROM routine_items WHERE patientId = :patientId")
    abstract suspend fun deleteAllRoutineForPatient(patientId: String)

    @Query("DELETE FROM doses_today WHERE patientId = :patientId")
    abstract suspend fun deleteAllDosesForPatient(patientId: String)

    @Query("DELETE FROM medications WHERE patientId = :patientId")
    abstract suspend fun deleteAllMedicationsForPatient(patientId: String)

    @Query("UPDATE doses_today SET status = :status WHERE patientId = :patientId AND id = :doseId")
    abstract suspend fun updateDoseStatus(patientId: String, doseId: String, status: DoseStatus)

    @Transaction
    open suspend fun replaceHomeCache(
        patientId: String,
        scheduleDate: String,
        routine: List<RoutineItemEntity>,
        doses: List<DoseTodayEntity>,
        medications: List<MedicationEntity>,
        adherenceSummary: AdherenceSummaryEntity,
    ) {
        deleteRoutine(patientId)
        deleteDoses(patientId, scheduleDate)
        deleteMedications(patientId)
        deleteAdherenceSummaries(patientId)
        insertRoutine(routine)
        insertDoses(doses)
        insertMedications(medications)
        insertAdherenceSummary(adherenceSummary)
    }

    @Transaction
    open suspend fun replaceRoutine(patientId: String, routine: List<RoutineItemEntity>) {
        deleteRoutine(patientId)
        insertRoutine(routine)
    }

    @Transaction
    open suspend fun deleteReadableCacheForPatient(patientId: String) {
        deleteAllRoutineForPatient(patientId)
        deleteAllDosesForPatient(patientId)
        deleteAllMedicationsForPatient(patientId)
        deleteAdherenceSummaries(patientId)
    }
}
