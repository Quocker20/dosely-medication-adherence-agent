from src.rag_ingestion.pipeline import (
    PageText,
    build_chunks,
    detect_drug_header,
    filter_chunks,
    fuzzy_section,
    is_invalid_drug_name,
    normalize_page,
    parse_sections,
    process_review_chunks,
)


def test_normalize_page_removes_watermark_and_keeps_content() -> None:
    raw = "DTQGVN 3\nhttps://trungtamthuoc.com\nTương tác thuốc\nNội dung"
    normalized = normalize_page(raw)
    assert "trungtamthuoc" not in normalized
    assert "DTQGVN" not in normalized
    assert "Tương tác thuốc" in normalized


def test_fuzzy_section_tolerates_common_diacritic_ocr_error() -> None:
    section, score = fuzzy_section("TƯƠNG TÁC THUÓC")
    assert section == "interactions"
    assert score >= 0.82


def test_drug_header_requires_identity_marker() -> None:
    lines = ["ACID ASCORBIC", "Tên chung quốc tế: Ascorbic acid.", "Mã ATC: A11GA01."]
    drug, confidence = detect_drug_header(lines, 0)
    assert drug == "ACID ASCORBIC"
    assert confidence >= 0.95
    assert detect_drug_header(["BAN BIÊN TẬP", "Nguyễn Văn A"], 0)[0] is None
    assert detect_drug_header(["TẬP II", "Mã ATC: A01AA01"], 0)[0] is None
    assert detect_drug_header(["DTQGVN", "ACICLOVIR", "Tên chung quốc tế: Aciclovir"], 0)[0] is None
    assert is_invalid_drug_name("PHÂN LOẠI")
    assert is_invalid_drug_name("EEE")


def test_state_parser_never_crosses_drug_or_section_boundaries() -> None:
    page = PageText(
        page=1,
        source_file="part-001-pages-001-015.txt",
        raw_text="",
        normalized_text=(
            "ACID ASCORBIC\nTên chung quốc tế: Ascorbic acid.\n"
            "Tương tác thuốc\nTương tác A.\n"
            "ACICLOVIR\nTên chung quốc tế: Aciclovir.\n"
            "Chỉ định\nĐiều trị B."
        ),
        ocr_confidence=0.95,
    )
    blocks, _ = parse_sections([page])
    chunks = build_chunks(blocks, [page], max_tokens=500, overlap_tokens=100)
    assert any(chunk.drug_name == "ACID ASCORBIC" and chunk.section == "interactions" for chunk in chunks)
    assert any(chunk.drug_name == "ACICLOVIR" and chunk.section == "indications" for chunk in chunks)
    assert all(not ("Tương tác A" in chunk.content and "Điều trị B" in chunk.content) for chunk in chunks)


def test_metadata_filter_excludes_review_chunks() -> None:
    page = PageText(1, "part.txt", "", "ACID ASCORBIC\nTên chung quốc tế: Ascorbic acid.\nTương tác thuốc\n" + "Nội dung tương tác. " * 30, 0.95)
    blocks, _ = parse_sections([page])
    chunks = build_chunks(blocks, [page])
    result = filter_chunks(chunks, drug_name="acid ascorbic", section="interactions")
    assert result
    assert all(chunk.review_status == "approved" for chunk in result)


def test_review_merge_stays_within_same_drug_and_section() -> None:
    text = "Nội dung tương tác có ích và cần kiểm tra. " * 20
    page = PageText(
        1, "part.txt", "",
        "ACICLOVIR\nTên chung quốc tế: Aciclovir.\nTương tác thuốc\n" + text,
        0.7,
    )
    blocks, _ = parse_sections([page])
    chunks = build_chunks(blocks, [page], max_tokens=80, overlap_tokens=20)
    review = [chunk for chunk in chunks if chunk.needs_review]
    groups = process_review_chunks(review)
    assert groups
    assert all(group["source_chunk_count"] <= 3 for group in groups)
    assert all(group["drug_name"] == "ACICLOVIR" for group in groups)
    interaction_groups = [group for group in groups if group["section"] == "interactions"]
    assert interaction_groups
    assert all(group["section"] == "interactions" for group in interaction_groups)


def test_state_parser_joins_multiline_drug_header() -> None:
    page = PageText(
        1,
        "part.txt",
        "",
        (
            "TIMOLOL MALEAT\n(THUỐC NHỎ MẮT)\n"
            "Tên chung quốc tế: Timolol maleate.\nMã ATC: S01ED01.\n"
            "Dược lực học\nNội dung chuyên luận."
        ),
        0.95,
    )
    blocks, _ = parse_sections([page])
    assert blocks
    assert {block.drug_name for block in blocks} == {
        "TIMOLOL MALEAT (THUỐC NHỎ MẮT)"
    }


def test_state_parser_stops_before_appendices() -> None:
    drug_page = PageText(
        1,
        "part.txt",
        "",
        (
            "ZOLPIDEM\nTên chung quốc tế: Zolpidem.\n"
            "Dược lực học\nNội dung thuốc."
        ),
        0.95,
    )
    appendix_page = PageText(
        2,
        "part.txt",
        "",
        "Sưu tầm và biên soạn bởi\nCÁC PHỤ LỤC\nNội dung không thuộc chuyên luận.",
        0.95,
    )
    blocks, _ = parse_sections([drug_page, appendix_page])
    combined = " ".join(line.text for block in blocks for line in block.lines)
    assert "Nội dung thuốc" in combined
    assert "Nội dung không thuộc chuyên luận" not in combined


def test_build_chunks_removes_exact_ocr_duplicates() -> None:
    pages = [
        PageText(
            1,
            "part.txt",
            "",
            "PARACETAMOL\nTên chung quốc tế: Paracetamol.\nChỉ định\nGiảm đau.",
            0.95,
        ),
        PageText(2, "part.txt", "", "Chỉ định\nGiảm đau.", 0.95),
    ]
    blocks, _ = parse_sections(pages)
    chunks = build_chunks(blocks, pages)
    assert [chunk.content for chunk in chunks].count("Giảm đau.") == 1
