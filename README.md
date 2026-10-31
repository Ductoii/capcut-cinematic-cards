# CapCut Cinematic Cards & Subtitles (`v0.5.0`)

Language: **Tiếng Việt** | [English](README.en.md)

Skill dành cho Agent AI để thiết kế và gắn **thẻ chữ điện ảnh (Location / Time / Character / THE END)** cùng **phụ đề chuẩn phim (Cinematic Subtitles)** trực tiếp vào bản nháp CapCut trên máy (`draft_info.json`), dựa trên quy trình thực chiến đã kiểm chứng qua các dự án `1026`, `1029`, `1014`, `1030`.

---

## Điểm cốt lõi của chuẩn `v0.5.0`

1. **Mandatory Intake khi yêu cầu chưa rõ**:
   Khi người dùng chỉ yêu cầu ngắn gọn (ví dụ: *"tạo card cho prj abc"*), Agent **bắt buộc hỏi lại 3 thông tin** trước khi chạy:
   - **Kịch bản (`Screenplay / Script`)** *(bắt buộc)* — để lấy đúng tên nhân vật, tuổi, vai trò, địa điểm và các mốc nhảy thời gian.
   - **Phong cách Card mong muốn (`Card Style`)** *(không truyền thì tự động điều chỉnh font + bảng màu theo thể loại kịch bản: `warm-heritage`, `southern-copper`, `christmas-hearth`, `modern-thriller`)*.
   - **Ảnh mẫu Subtitle (`Subtitle Reference Image`)** *(không truyền thì mặc định dùng chuẩn **Trắng Điện Ảnh Không Khung Xám** `white-cinematic-boxless`: `#FFFDF8`, `Menlo-Regular.ttf`, `size = 4.2`, `y = -0.74`, `check_flag = 15`, có viền đen mảnh + đổ bóng)*.

2. **Mặc định luôn làm `THE END`**:
   - Tự động đặt thẻ `THE END` ở cảnh kết phim (`type = "ending"`), trừ khi người dùng dặn rõ không làm `THE END` (`include_ending: false`).

3. **Mặc định mọi Card đều có Native `Fade In` + `Fade Out`**:
   - Tất cả thẻ (`Main`, `Detail`, `THE END`) đều gắn sẵn hiệu ứng gốc của CapCut trong `materials.material_animations`:
     - **Fade In**: `id = "6724916044072227332"` (`0.7s` = `700,000 us`)
     - **Fade Out**: `id = "6724919382104871427"` (`0.5s` = `500,000 us`)
   - Giữ `common_keyframes = []` để người dùng có thể chỉnh trực tiếp trong tab `Animation -> In/Out` của CapCut.

4. **Không phụ thuộc vào mờ đen (`Fade In / Fade Out`) trên timeline CapCut**:
   - Đặt thẻ Thời gian / Địa điểm theo **bước nhảy thời gian và bối cảnh thực tế trong kịch bản** (`30 YEARS LATER — CHRISTMAS DAY`, `CHRISTMAS EVE — 11:45 PM`, `TEN YEARS LATER...`), tuyệt đối không lấy hiệu ứng mờ đen trên timeline làm mốc duy nhất.

5. **Tự động tách Font `.ttc -> .ttf` vào CapCut Sandbox Container & Chỉnh phụ đề In-Place (0ms lệch nhịp)**:
   - Tự động tách mặt chữ từ `.ttc` của macOS (`Menlo.ttc`, `Seravek.ttc`, `Baskerville.ttc`, `Optima.ttc`, `Avenir Next.ttc`, `Didot.ttc`) thành file `.ttf` độc lập trong cả `~/Library/Fonts/` và `~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts/`.
   - Chỉnh style phụ đề **in-place** ngay trên track Auto-Caption của CapCut (`target_timerange` giữ nguyên 100%, không lệch nhịp ở cuối phim), đồng bộ `content == base_content`, sửa lỗi chính tả ASR theo kịch bản và xoá các file delta patch (`mini_draft.json`, `patch.json`).

---

## Cài đặt nhanh (`v0.5.0`)

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.5.0/install.py | python3
```

---

## Các Preset dựng sẵn

### Phong cách Card (`theme`)
| Preset | Font Chính (`Main` / `THE END`) | Màu Chính | Font Phụ (`Detail`) | Màu Phụ | Phù hợp với |
|---|---|---|---|---|---|
| `warm-heritage` | `Didot-Bold` | `#F6EFE2` (Warm Cream) | `AvenirNext-DemiBold` | `#E5B869` (Burnished Gold) | Phim gia đình, tâm lý, di sản (`1026`, `1014`) |
| `southern-copper` | `Baskerville-SemiBold` | `#FAF3E6` (Warm Ivory) | `AvenirNext-Medium` | `#E0A958` (Amber Gold) | Phim miền Nam, hoài niệm, quê hương (`1029`) |
| `christmas-hearth` | `Baskerville-Bold` | `#FCE8B2` (Candlelight Gold) | `Optima-Bold` (`✦  `) | `#F4F7EE` (Frosted Cream) | Phim Giáng sinh, mùa đông (`1030`) |
| `modern-thriller` | `AvenirNext-Bold` | `#F2F5F8` (Ice White) | `Menlo-Bold` | `#D9A441` (Steel Amber) | Phim hình sự, điều tra, hiện đại |

### Phong cách Phụ đề (`subtitles.preset`)
| Preset | Font | Size | Màu chữ | Vị trí `y` | Khung nền (`check_flag`) |
|---|---|---|---|---|---|
| `white-cinematic-boxless` *(Mặc định)* | `Menlo-Regular.ttf` | `4.2` | `#FFFDF8` | `-0.74` | Không khung (`check_flag = 15`), viền đen `0.016` + bóng |
| `yellow-cinema-boxless` | `Seravek-Medium.ttf` | `4.4` | `#E5CE6E` | `-0.78` | Không khung (`check_flag = 15`), viền đen `0.012` + bóng |
| `boxed-monospaced` | `Menlo-Regular.ttf` | `4.1` | `#FFFDF8` | `-0.74` | Khung tối bo góc (`check_flag = 23`, `offset = 0.0, 0.0`) |

---

## Cấu trúc thư mục

- [`skills/capcut-cinematic-cards/SKILL.md`](skills/capcut-cinematic-cards/SKILL.md) — Quy trình vận hành đầy đủ cho Agent.
- [`skills/capcut-cinematic-cards/references/editing.md`](skills/capcut-cinematic-cards/references/editing.md) — Tiêu chuẩn thiết kế Card, vị trí góc trên (`y > 0`), kiểm tra cắt cảnh (`scdet`) và chống tràn lề (`PIL.ImageFont`).
- [`skills/capcut-cinematic-cards/references/subtitle-layout.md`](skills/capcut-cinematic-cards/references/subtitle-layout.md) — Kiến trúc phụ đề in-place, bitmask `check_flag`, tách font `.ttc -> .ttf` trong CapCut Sandbox.
- [`skills/capcut-cinematic-cards/references/tool.md`](skills/capcut-cinematic-cards/references/tool.md) — Hướng dẫn CLI & schema `version: 3`.
- [`skills/capcut-cinematic-cards/scripts/`](skills/capcut-cinematic-cards/scripts/) — Bộ công cụ Python (`cards.py`, `styles.py`, `native_text.py`, `media.py`, `preview.py`).
