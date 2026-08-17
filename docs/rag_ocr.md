# OCR Dược thư Quốc gia cho RAG

File Dược thư hiện tại có 890 trang và khoảng 818 MB. Nó có một lớp text nhỏ
chứa watermark, còn nội dung chính là ảnh scan. Vì vậy `pdftotext` không lấy
được nội dung thuốc; cần OCR trước khi chunk và embedding.

## Cài công cụ

Tool `scripts/ocr_pdf.py` dùng OCRmyPDF, Tesseract OCR, Ghostscript và bộ ngôn
ngữ tiếng Việt `vie`. Sau khi cài, kiểm tra:

```powershell
ocrmypdf --version
tesseract --list-langs
```

Danh sách ngôn ngữ phải có cả `vie` và `eng`.

## Chạy thử trước

Không OCR cả 890 trang ngay. Chạy thử 10 trang, kiểm tra PDF và file text:

```powershell
python scripts/ocr_pdf.py `
  "..\Duoc-thu-quoc-gia-viet-nam-2022-quyen-1-trungtamthuoc.pdf" `
  "data\ocr\duoc-thu-q1-pages-1-10.pdf" `
  --pages 1-10 --jobs 2
```

Kết quả:

- `data/ocr/duoc-thu-q1-pages-1-10.pdf`: giữ ảnh trang gốc và thêm lớp text để
  tìm kiếm/copy.
- `data/ocr/duoc-thu-q1-pages-1-10.txt`: text UTF-8 phù hợp làm đầu vào cho
  bước làm sạch, chunk và embedding.

## Chạy toàn bộ

```powershell
python scripts/ocr_pdf.py `
  "..\Duoc-thu-quoc-gia-viet-nam-2022-quyen-1-trungtamthuoc.pdf" `
  "data\ocr\duoc-thu-quoc-gia-2022-q1-searchable.pdf" `
  --jobs 2
```

File nguồn không bao giờ bị sửa. Với máy ít RAM, giữ `--jobs 2`. Nếu tiến trình
bị gián đoạn, chia thành các dải 100 trang bằng `--pages 1-100`, `101-200`, ...;
mỗi dải dùng một tên output riêng. Chỉ ingest vào RAG sau khi kiểm tra thủ công
một số chuyên luận có bảng, ký hiệu liều, tiếng Việt và tên hoạt chất.

`--force-ocr` được dùng có chủ đích: PDF đã có watermark dạng text nên chế độ
`--skip-text` có thể hiểu nhầm trang là đã OCR và bỏ qua nội dung ảnh.
