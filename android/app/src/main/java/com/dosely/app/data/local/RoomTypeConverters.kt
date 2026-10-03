package com.dosely.app.data.local

import androidx.room.TypeConverter
import com.dosely.app.data.DosePeriod
import com.dosely.app.data.DoseStatus
import com.dosely.app.data.MealRelation
import com.dosely.app.data.local.entity.OutboxActionType
import com.dosely.app.data.local.entity.OutboxStatus

class RoomTypeConverters {
    @TypeConverter
    fun doseStatusToString(value: DoseStatus): String = value.name

    @TypeConverter
    fun stringToDoseStatus(value: String): DoseStatus = DoseStatus.valueOf(value)

    @TypeConverter
    fun mealRelationToString(value: MealRelation): String = value.name

    @TypeConverter
    fun stringToMealRelation(value: String): MealRelation = MealRelation.valueOf(value)

    @TypeConverter
    fun dosePeriodToString(value: DosePeriod): String = value.name

    @TypeConverter
    fun stringToDosePeriod(value: String): DosePeriod = DosePeriod.valueOf(value)

    @TypeConverter
    fun outboxActionTypeToString(value: OutboxActionType): String = value.name

    @TypeConverter
    fun stringToOutboxActionType(value: String): OutboxActionType = OutboxActionType.valueOf(value)

    @TypeConverter
    fun outboxStatusToString(value: OutboxStatus): String = value.name

    @TypeConverter
    fun stringToOutboxStatus(value: String): OutboxStatus = OutboxStatus.valueOf(value)
}
