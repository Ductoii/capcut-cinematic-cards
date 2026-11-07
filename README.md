# CapCut Cinematic Cards & Subtitles (`v0.6.0`)

Language: **Tiếng Việt** | [English](README.en.md)

Engine thiết kế **thẻ chữ điện ảnh (Location / Time / Character / THE END)** và **phụ đề chuẩn phim (Cinematic Subtitles)** trực tiếp vào bản nháp CapCut macOS (`draft_info.json`) theo triết lý **YAGNI — Zero Canned Presets, AI Visual Art Direction** (`inspect` -> `probe` -> `apply` + `preview_sheet` trong `< 6s`).

---

## Điểm cốt lõi của `v0.6.0`

1. **Zero Canned Presets & Auto Google Fonts (`1,600+` Fonts)**:
   - Không bó cứng vào một vài template có sẵn. AI tự chỉ đạo nghệ thuật (cặp font, tỷ lệ, sắc độ, flankers) theo đúng thế giới kịch bản (`inspect` + `sf-board.json`).
   - Tự động tách font từ `.ttc` của macOS hoặc **tải trực tiếp bất kỳ font nào từ Google Fonts** (`PlayfairDisplay-Bold`, `CormorantGaramond-BoldItalic`, `Cinzel-Bold`, `BodoniModa-Bold`, `DMSerifDisplay-Regular`, `InstrumentSerif-Italic`, `Rye-Regular`, `BebasNeue-Regular`, `JetBrainsMono-SemiBold`...), chuẩn hoá `hhea`/`OS/2` vertical metrics (`1.20 * upm`) và cài thẳng vào CapCut Sandbox Container (`< 0.4s`).

2. **Multi-Span Editorial Rich Text (`styles[]`) & Ornamental Flankers**:
   - Tự động chia mảng `styles[]` đa sắc độ & đa kích cỡ ngay trong **1 layer text CapCut duy nhất**:
     - **Dòng Title**: Hạ tiền tố danh xưng (`Dr. `, `Lt. `, `Capt. `, `Judge `, `Sheikh `) và hậu tố tuổi (`, 74`) xuống `0.82–0.85x` cỡ chữ với màu `accent_color`, giữ tên chính ở `1.0x` màu `title_color`.
     - **Dòng Detail / Role / Time**: Highlight vế chức danh chính / danh hiệu (`$5M Champion`, `Stable Hand`, `Head Trainer`, `Morning`, `Six Months Later`) bằng màu `detail_accent_color`, vế tổ chức/bối cảnh bằng màu `char_detail_color`, và đóng khung bằng ký hiệu trang trí điện ảnh (`—`, `« »`, `·`, `[ ]`, `//`) có kiểm tra bảng `cmap` chống lỗi ô vuông `[]`.

3. **Cân Trục Tâm Tuyệt Đối (`align: "center"`) & Trim/Cut-Immune Timing**:
   - Khóa `x_title == x_detail` cùng trục tâm dọc trong khi neo mép ngoài ở `±0.88` (đo bằng độ rộng glyph thực tế `11.2 px/em/size` trên khung `1920x1080`), không bao giờ tràn màn hình hay lệch trục.
   - Bóc tách đệ quy `Compound Clips` (`materials.drafts`) có xét đúng phần cắt `source_timerange` & `speed`, ánh xạ `shot_breakdown` (`goc`) từ `sf-board.json` sang giây timeline thực tế sau khi cắt (`TL x-ys` vs `TRIMMED_OUT`), và khóa 2 đầu `[start_s, end_s]` vào đúng 1 cú máy `scdet` liên tục.

4. **Native CapCut `Fade In` + `Fade Out` (Staggered Entrance `0.10s`) & WYSIWYG Preview Sheet**:
   - Gắn sẵn hiệu ứng gốc của CapCut (`Fade In`: `6724916044072227332`, `Fade Out`: `6724919382104871427`, `start = segment_duration_us - fade_out_us`) với độ trễ dòng phụ `stagger_sec = 0.10s`.
   - Tự động xuất bảng ảnh `preview_<plan>.jpg` vẽ trực tiếp card lên frame video thực tế để Agent kiểm tra thị giác bằng `read_file`.

---

## Cài đặt nhanh (`v0.6.0`)

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.6.0/install.py | python3
```

---

## Cấu trúc thư mục

- [`skills/capcut-cinematic-cards/SKILL.md`](skills/capcut-cinematic-cards/SKILL.md) — Quy trình 4 bước cho Agent (`inspect` -> `probe` -> `apply` -> `preview_sheet`).
- [`skills/capcut-cinematic-cards/references/editing.md`](skills/capcut-cinematic-cards/references/editing.md) — Hệ thống chỉ đạo thẩm mỹ điện ảnh (5 Pillars: Font Pairing Matrix, Multi-Span Rich Text, Archetype Palette Accents, Stack Order & Stagger, Centered-Axis Symmetry).
- [`skills/capcut-cinematic-cards/references/subtitle-layout.md`](skills/capcut-cinematic-cards/references/subtitle-layout.md) — Kiến trúc phụ đề in-place 0ms lệch nhịp.
- [`skills/capcut-cinematic-cards/references/tool.md`](skills/capcut-cinematic-cards/references/tool.md) — Hướng dẫn CLI & schema `plan.json`.
- [`skills/capcut-cinematic-cards/scripts/cards.py`](skills/capcut-cinematic-cards/scripts/cards.py) — CLI hợp nhất (`inspect`, `fonts`, `fetch-font`, `probe`, `apply`, `clear`).
- [`skills/capcut-cinematic-cards/scripts/native_text.py`](skills/capcut-cinematic-cards/scripts/native_text.py) — Engine font, multi-span rich text, hình học pixel CapCut và WYSIWYG preview.
