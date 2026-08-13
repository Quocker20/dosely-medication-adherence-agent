package com.remindrx.app.data

data class Medication(
    val name: String,
    val doseLabel: String,
    val times: List<String>,
    val remainingDaysLabel: String,
)
