# CapCut Cinematic Cards & Subtitles (`v0.7.0`)

Language: **Tiếng Việt** | [English](README.en.md)

Engine thiết kế **thẻ chữ điện ảnh (Location / Time / Character / THE END)** và **phụ đề chuẩn phim (Cinematic Subtitles)** trực tiếp vào bản nháp CapCut macOS (`draft_info.json`) theo triết lý **YAGNI — Zero Canned Presets, AI Visual Art Direction** (`inspect` -> `probe` -> `apply` + `preview_sheet` đa luồng 16 workers trong `< 6s`).

---

## Điểm cốt lõi của `v0.7.0`

1. **16-Thread Parallel Pipeline (`< 6s` Cold Cache, `< 1.5s` Warm Cache) & Anti-Clone World Archetypes**:
   - Toàn bộ `inspect` (`0.4s`), `probe` (`0.4s–5.6s`), `apply + preview_pages` (`1.1s–3.4s`) chạy đa luồng (`ThreadPoolExecutor` 16 workers) kèm cache frame & cache font in-memory, loại bỏ hoàn toàn tình trạng nghẽn hay văng vào background task.
   - `inspect` tự động phân tích `sf-board.json` để sinh `recommended_style` theo **8 hệ mỹ thuật điện ảnh** (`coastal_lifeguard_rescue`, `rustic_heartland_americana`, `legal_corporate_dynasty`, `military_tactical_thriller`, `high_society_gala_drama`, `equestrian_heritage_estate`, `modern_prestige_drama`...) và tích hợp chốt chặn **Anti-Clone Guard** trong `apply`.

2. **Chuẩn hoá Phụ đề từ Kịch bản (`normalize_with_screenplay`) & Mặc định Vàng Cổ Điển (`Seravek-Medium` `4.2` `#E5CE6E`)**:
   - Khi user yêu cầu style phụ đề riêng, áp dụng theo đúng request; khi không yêu cầu, mặc định chuẩn vàng cổ điển (`Seravek-Medium`, `size: 4.2`, `text_size: 30`, `#E5CE6E`, `y: -0.78`, `stroke_width: 0.028`, `shadow_alpha: 0.82`, `shadow_smoothing: 2.58`, `shadow_distance: 1.8`, `check_flag: 47`).
   - Tự động đối chiếu từng câu sub `[start_s, end_s]` với thoại gốc trong `sf-board.json` / `*KICHBAN*.txt` để sửa từ ghép bị ASR tách đôi (`life Lord` -> `lifeguard`), từ nghe nhầm theo ngữ cảnh (`vacate this Jack` -> `vacate this shack`, `Coral Reef` -> `Coral Reach`), điều khoản (`claws 9` -> `Clause 9`) và tên riêng nhân vật (`lanira` -> `Lenora`, `alford` -> `Alford`).

3. **Multi-Span Editorial Rich Text (`styles[]`) & Ornamental Flankers**:
   - Tự động chia mảng `styles[]` đa sắc độ & đa kích cỡ ngay trong **1 layer text CapCut duy nhất**:
     - **Dòng Title**: Hạ tiền tố danh xưng (`Dr. `, `Lt. `, `Capt. `, `Judge `, `Sheikh `) và hậu tố tuổi (`, 74`) xuống `0.82–0.85x` cỡ chữ với màu `accent_color`, giữ tên chính ở `1.0x` màu `title_color`.
     - **Dòng Detail / Role / Time**: Highlight vế chức danh chính / danh hiệu bằng màu `detail_accent_color`, vế tổ chức/bối cảnh bằng màu `char_detail_color`, và đóng khung bằng ký hiệu trang trí điện ảnh (`~`, `—`, `•`, `|`, `::`, `◇`) có kiểm tra bảng `cmap` chống lỗi ô vuông `[]`.

4. **Tự động Né Vùng Chói (`score_frame_negative_space`) & Native CapCut `Fade In` + `Fade Out`**:
   - Tự động chấm điểm độ sáng & vùng chói (biển hiệu trắng, áo trắng, nắng gắt) ở cả 4 góc (`lower-left`, `lower-right`, `upper-left`, `upper-right`) để lật card sang góc tối sạch chữ nhất.
   - Gắn sẵn hiệu ứng gốc của CapCut (`Fade In`: `6724916044072227332`, `Fade Out`: `6724919382104871427`) với độ trễ dòng phụ `stagger_sec = 0.10s` và xuất `preview_<plan>_p1..pN.jpg`.

---

## Cài đặt nhanh (`v0.7.0`)

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.7.0/install.py | python3
```

---

## Cấu trúc thư mục

- [`skills/capcut-cinematic-cards/SKILL.md`](skills/capcut-cinematic-cards/SKILL.md) — Quy trình 4 bước cho Agent (`inspect` -> `probe` -> `apply` -> `preview_sheet`).
- [`skills/capcut-cinematic-cards/references/editing.md`](skills/capcut-cinematic-cards/references/editing.md) — Hệ thống chỉ đạo thẩm mỹ điện ảnh (5 Pillars: Font Pairing Matrix, Multi-Span Rich Text, Archetype Palette Accents, Stack Order & Stagger, Centered-Axis Symmetry).
- [`skills/capcut-cinematic-cards/references/subtitle-layout.md`](skills/capcut-cinematic-cards/references/subtitle-layout.md) — Kiến trúc phụ đề in-place 0ms lệch nhịp.
- [`skills/capcut-cinematic-cards/references/tool.md`](skills/capcut-cinematic-cards/references/tool.md) — Hướng dẫn CLI & schema `plan.json`.
- [`skills/capcut-cinematic-cards/scripts/cards.py`](skills/capcut-cinematic-cards/scripts/cards.py) — CLI hợp nhất (`inspect`, `fonts`, `fetch-font`, `probe`, `apply`, `clear`).
- [`skills/capcut-cinematic-cards/scripts/native_text.py`](skills/capcut-cinematic-cards/scripts/native_text.py) — Engine font, multi-span rich text, hình học pixel CapCut và WYSIWYG preview.
