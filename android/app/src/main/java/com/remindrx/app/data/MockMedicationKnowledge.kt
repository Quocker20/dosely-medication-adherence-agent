package com.remindrx.app.data

data class KnowledgeSource(val title: String, val url: String)

data class MedicationKnowledge(
    val summary: String,
    val howToUse: String,
    val commonEffects: List<String>,
    val importantWarnings: List<String>,
    val sources: List<KnowledgeSource>,
)

/**
 * RAG mock — chưa nối vào retrieval/knowledge-base API thật. Xem
 * android/README.md mục "Next steps": cần thay bằng production RAG khi có.
 */
object MockMedicationKnowledge {
    private val default = MedicationKnowledge(
        summary = "Chưa có thông tin tham khảo cho thuốc này trong dữ liệu demo.",
        howToUse = "Dùng đúng theo hướng dẫn trên đơn thuốc của bác sĩ.",
        commonEffects = emptyList(),
        importantWarnings = listOf("Không tự ý thay đổi liều hoặc ngừng thuốc khi chưa hỏi bác sĩ."),
        sources = emptyList(),
    )

    private val entries: Map<String, MedicationKnowledge> = mapOf(
        "metformin" to MedicationKnowledge(
            summary = "Metformin hỗ trợ kiểm soát đường huyết ở người tiểu đường type 2.",
            howToUse = "Uống cùng bữa ăn để giảm khó chịu tiêu hoá. Không tự bù gấp đôi nếu quên liều.",
            commonEffects = listOf("Buồn nôn", "Đầy bụng", "Tiêu chảy nhẹ giai đoạn đầu"),
            importantWarnings = listOf(
                "Không tự ý ngừng thuốc dù đường huyết đã ổn định.",
                "Báo bác sĩ nếu có dấu hiệu mệt mỏi bất thường, khó thở.",
            ),
            sources = listOf(KnowledgeSource("Hướng dẫn sử dụng thuốc — Bộ Y tế", "https://moh.gov.vn")),
        ),
        "losartan" to MedicationKnowledge(
            summary = "Losartan là thuốc hạ huyết áp nhóm ức chế thụ thể angiotensin II.",
            howToUse = "Uống đều đặn mỗi ngày vào cùng một giờ, dù huyết áp đã ổn định.",
            commonEffects = listOf("Chóng mặt nhẹ", "Mệt mỏi"),
            importantWarnings = listOf("Không tự dùng thêm kali hoặc muối thay thế chứa kali khi chưa hỏi bác sĩ."),
            sources = listOf(KnowledgeSource("Hướng dẫn sử dụng thuốc — Bộ Y tế", "https://moh.gov.vn")),
        ),
        "atorvastatin" to MedicationKnowledge(
            summary = "Atorvastatin giúp giảm cholesterol và nguy cơ tim mạch ở người phù hợp.",
            howToUse = "Thường uống một lần mỗi ngày, có thể uống vào buổi tối.",
            commonEffects = listOf("Đau cơ nhẹ", "Rối loạn tiêu hoá"),
            importantWarnings = listOf("Báo bác sĩ ngay nếu đau hoặc yếu cơ bất thường."),
            sources = listOf(KnowledgeSource("Hướng dẫn sử dụng thuốc — Bộ Y tế", "https://moh.gov.vn")),
        ),
    )

    fun find(medicationName: String): MedicationKnowledge {
        val key = entries.keys.firstOrNull { medicationName.contains(it, ignoreCase = true) }
        return key?.let(entries::getValue) ?: default
    }
}
