# CapCut Cinematic Cards & Subtitles (`v0.5.0`)

Language: [Tiếng Việt](README.md) | **English**

An AI Agent skill for designing and applying **film-matched Location, Time, Character, and `THE END` title cards** plus **zero-drift in-place cinematic subtitles** directly inside macOS CapCut Desktop drafts (`draft_info.json`), distilled from production passes across projects `1026`, `1029`, `1014`, and `1030`.

---

## Core Standards in `v0.5.0`

1. **Mandatory Pre-Task Intake When Underspecified**:
   When a user gives a brief prompt (e.g., *"create cards for project 1030"*), the Agent **must ask for 3 items before executing**:
   - **Screenplay / Script (`Kịch bản`)** *(required)* — source of truth for character names, ages, roles, locations, and chronological time jumps.
   - **Card Style (`Phong cách Card mong muốn`)** *(optional — automatically matched to the script's genre and tone if omitted: `warm-heritage`, `southern-copper`, `christmas-hearth`, `modern-thriller`)*.
   - **Subtitle Reference Image (`Ảnh mẫu Subtitle`)** *(optional — defaults to the **Classic White Cinematic Boxless** preset `white-cinematic-boxless`: `#FFFDF8` Warm Paper White, `Menlo-Regular.ttf`, `size = 4.2`, `y = -0.74`, `check_flag = 15`, dark stroke + shadow)*.

2. **Default `THE END` Card**:
   - Automatically places a `THE END` card (`type = "ending"`) on the closing hold unless explicitly disabled by the user (`include_ending: false`).

3. **Default Native CapCut `Fade In` + `Fade Out` on Every Card**:
   - Every card (`Main`, `Detail`, and `THE END`) receives native CapCut `sticker_animation` entries in `materials.material_animations`:
     - **Fade In**: `id = "6724916044072227332"` (`0.7s` = `700,000 us`)
     - **Fade Out**: `id = "6724919382104871427"` (`0.5s` = `500,000 us`)
   - Keeps `common_keyframes = []` so fades remain editable in CapCut's `Animation -> In/Out` tab.

4. **Story-Jump Anchoring (Independent of Timeline Black Fades)**:
   - Time and Location cards are anchored to **actual story time jumps and scene changes in the script**, never dependent on timeline black fade transitions.

5. **Sandbox `.ttc -> .ttf` Font Extraction & Zero-Drift In-Place Subtitle Styling**:
   - Extracts desired font faces from macOS `.ttc` collections into standalone `.ttf` files in both `~/Library/Fonts/` and `~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts/`.
   - Styles existing CapCut Auto-Captions **in-place** (100% preserved `target_timerange`), synchronizes `content == base_content`, corrects ASR typos against the script, and cleans `mini_draft.json` / `patch.json` delta patches.

---

## Quick Install (`v0.5.0`)

```bash
curl -fsSL https://raw.githubusercontent.com/Ductoii/capcut-cinematic-cards/v0.5.0/install.py | python3
```
