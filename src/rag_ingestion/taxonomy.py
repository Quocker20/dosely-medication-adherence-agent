"""Canonical section taxonomy and OCR-tolerant aliases."""

SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "identity": ("tên chung quốc tế", "mã atc", "loại thuốc"),
    "forms_strengths": ("dạng thuốc và hàm lượng", "dạng bào chế và hàm lượng"),
    "pharmacodynamics": ("dược lực học",),
    "pharmacokinetics": ("dược động học",),
    "indications": ("chỉ định",),
    "contraindications": ("chống chỉ định",),
    "warnings": ("thận trọng", "cảnh báo và thận trọng"),
    "pregnancy": ("thời kỳ mang thai",),
    "lactation": ("thời kỳ cho con bú",),
    "adverse_effects": (
        "tác dụng không mong muốn",
        "tác dụng không mong muốn (adr)",
        "tác dụng phụ",
    ),
    "adverse_effect_management": ("hướng dẫn cách xử trí adr",),
    "dosage_administration": (
        "liều lượng và cách dùng",
        "liều dùng và cách dùng",
        "cách dùng và liều lượng",
    ),
    "interactions": ("tương tác thuốc", "tương tác"),
    "overdose": ("quá liều và xử trí", "quá liều",),
    "incompatibilities": ("tương kỵ",),
    "storage": ("bảo quản",),
    "updates": ("cập nhật lần cuối",),
}

SECTION_LABELS = {
    "identity": "Thông tin định danh",
    "forms_strengths": "Dạng thuốc và hàm lượng",
    "pharmacodynamics": "Dược lực học",
    "pharmacokinetics": "Dược động học",
    "indications": "Chỉ định",
    "contraindications": "Chống chỉ định",
    "warnings": "Thận trọng",
    "pregnancy": "Thời kỳ mang thai",
    "lactation": "Thời kỳ cho con bú",
    "adverse_effects": "Tác dụng không mong muốn",
    "adverse_effect_management": "Hướng dẫn xử trí ADR",
    "dosage_administration": "Liều lượng và cách dùng",
    "interactions": "Tương tác thuốc",
    "overdose": "Quá liều và xử trí",
    "incompatibilities": "Tương kỵ",
    "storage": "Bảo quản",
    "updates": "Cập nhật",
}
