---
name: capcut-cinematic-cards
description: Use when adding or styling cinematic character introduction cards, time/location cards, THE END cards, and cinema subtitles in a local CapCut project without computer use. Enforces mandatory user intake when requests are underspecified, defaults to including THE END and native Fade In/Out animations on all cards, places time/location cards at actual story time/location jumps (never relying on timeline black fades), and styles subtitles in-place with exact font/container/base_content synchronization.
---

# CapCut Cinematic Cards & Subtitles

Work directly through local files and terminal scripts (Python 3.10+, FFmpeg/ffprobe, `fontTools`, `Pillow`). Never use GUI Computer Use. Always preserve the user's compound clips, video edits, audio tracks, and timeline duration.

Read [the editorial & styling guide](references/editing.md), [the subtitle reference & layout guide](references/subtitle-layout.md), and [the helper CLI/script reference](references/tool.md).

---

## 0. Mandatory Pre-Task Intake (Khi User Request Chưa Rõ Yêu Cầu)

When the user gives a short or underspecified request (e.g., *"tạo card cho prj 1031"*, *"làm card cho project abc"* without specifying the details below), **you MUST ask the user to provide or confirm these 3 inputs before executing**:

1. **Kịch bản phim (`Screenplay / Script`)** *(Required)*:
   - Path to the script file (`.txt` / `.md`) or pasted script text so you can verify exact character names, established roles (`detail`), true story time/location jumps, and canonical dialogue spelling.
2. **Phong cách Card mong muốn (`Card Style Direction`)** *(Optional — auto-adjust to the script if not specified)*:
   - Ask if the user wants a specific visual style (e.g. Christmas, warm heritage drama, southern copper, modern thriller).
   - **Default if not specified**: Automatically design and adapt the card font pairing, color palette, stroke, and shadow to match the genre, setting, and emotional tone of the screenplay.
3. **Ảnh mẫu Subtitle (`Subtitle Reference Image`)** *(Optional — default to the classic White Cinematic Boxless subtitle if not specified)*:
   - Ask if the user has a reference screenshot for subtitles.
   - **If the user provides a reference image**: Analyze its exact font family/weight, character width ratio, text color, font size, presence/absence of a background box, stroke width, drop shadow softness, vertical position `y`, and 2-line balanced wrapping to reproduce it 100% faithfully.
   - **If the user does not specify / does not provide an image**: Default to the approved **White Cinematic Boxless Subtitle (`#FFFDF8` `Menlo-Regular.ttf`, `size = 4.2`, `y = -0.74`, `check_flag = 15`, zero grey/black background box, crisp black stroke + soft drop shadow)**.

*(If the user's initial prompt already supplies the script and specifies or delegates the card/subtitle style, proceed directly end-to-end without unnecessary questions.)*

---

## 1. Three Core Defaults (Luật Mặc Định Bất Di Bất Dịch)

1. **Default `THE END` Card (`Mặc định LUÔN làm THE END`)**:
   - Always place a `THE END` (or `— THE END —`) card on the closing hold of the film (`x = 0.0, y = 0.65..0.68`, centered, with native Fade In / Fade Out), **unless** the user explicitly says *"kịch bản này không cần làm the end"*.
2. **Default Native `Fade In` + `Fade Out` on Every Card (`Mặc định MỌI Card đều có Fade In / Fade Out`)**:
   - Every card segment (`Cinematic Cards · Main`, `Cinematic Cards · Detail`, and `THE END`) **must** have a native CapCut `sticker_animation` entry in `materials.material_animations` attached via `seg["extra_material_refs"] = [anim_id]` (and `seg["common_keyframes"] = []`):
     - **Fade In**: `id = "6724916044072227332"`, `category_id = "ruchang"`, `name = "Fade In"`, `type = "in"`, `start = 0`, `duration = 700000` (`0.7s`).
     - **Fade Out**: `id = "6724919382104871427"`, `category_id = "chuchang"`, `name = "Fade Out"`, `type = "out"`, `start = max(0, dur_us - 500000)`, `duration = 500000` (`0.5s`).
   - Do not wait for or depend on an existing text animation in the target draft—create/inject the native `material_animations` entries automatically for every card segment.
3. **Never Depend on Timeline Black Fades (`KHÔNG phụ thuộc vào mờ đen trong timeline CapCut`)**:
   - Never use CapCut timeline black fades as the trigger or anchor for cards.
   - Place Time and Location cards strictly where the **story jumps in time or setting** (e.g., *"One hour later"*, *"That evening"*, *"Monday morning"*, *"Three months later"*, *"One year later"*, *"Christmas Eve · Basement"*, *"Meanwhile · Manager's Office"*).
   - Anchor each time/location card near the start of the new scene (`0.2s–0.5s` after the scene cut), lasting `3.0s–4.0s` inside that scene.

---

## 2. Detailed Font, Subtitle & Card Configuration (Chuẩn Kỹ Thuật)

### 2.1. Font Extraction (`.ttc` → Standalone `.ttf`) & CapCut Sandbox Container
- On macOS, CapCut (`com.lemon.lvoverseas`) runs inside an App Sandbox and frequently fails to render `.ttc` (TrueType Collection) files disguised with a `.ttf` extension or fonts stored outside allowed directories.
- Whenever a chosen font comes from a macOS `.ttc` bundle (e.g., `Menlo.ttc`, `Baskerville.ttc`, `Seravek.ttc`, `Optima.ttc`, `Avenir.ttc`), extract the exact face index using `fontTools.ttLib.TTCollection` into a standalone `.ttf` binary (`true` / `00 01 00 00` magic bytes) and copy it to **both**:
  1. `~/Library/Fonts/<FontPostScriptName>.ttf`
  2. `~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts/<FontPostScriptName>.ttf`
- For standalone system `.ttf` fonts (such as `/System/Library/Fonts/Supplemental/Georgia.ttf`, `Georgia Italic.ttf`, `Times New Roman.ttf`), also copy them into `~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts/` and set `font_path` to the container path.
- **Dual Payload Rule (`content == base_content`)**: In every `materials.texts` entry (both cards and subtitles), always write `mat["base_content"] = mat["content"]` identically. If `base_content` is left stale, CapCut ignores `content` and falls back to `Arial` size `6.0`/`7.0`.

### 2.2. Subtitle Timing & Styling Rules
- **In-Place Styling on Existing CapCut Auto-Captions (Zero Timing Drift)**:
  - When a project already has a CapCut Auto-Caption subtitle track (`m["type"] == "subtitle"`), **always style and clean those segments in-place**, preserving 100% of every segment's `id`, `material_id`, `target_timerange`, `source_timerange`, and `words`.
  - **Why external Whisper-to-video-span mapping drifts on Compound Clips**: Inside a Compound Clip (`materials.drafts[0].draft`), the editor cuts and shifts the audio tracks (`tracks[1..N]`) independently from the video track (`tracks[0]`). Mapping external `.mp4` Whisper timestamps through video segments (`v_spans`) causes a `1–3s` offset. Always prefer CapCut's native Auto-Caption track (or, if generating captions when no subtitle track exists, map strictly through the compound clip's rendered **audio** track segments).
  - **Text Cleanup & Balanced 2-Line Wrapping**:
    - Fix ASR misspellings of character names and proper nouns against the screenplay (e.g., `Mr Veal` / `Mister Veil` → `Mr. Vale`, `Coraline` / `Karine` → `Corinne`, `Amani` → `Imani`).
    - Ensure proper sentence capitalization and terminal punctuation.
    - Wrap lines longer than `38–42` characters into **at most 2 balanced lines** (preferring natural punctuation/clause breaks).
    - If CapCut ASR hallucinated garbage words on silent/music B-roll shots (e.g., `"Jesus Jesus Jesus"`, `"hers hers"`), remove those noise segments and also remove their `segment_id`s from `common_attachment/attachment_action_scene.json`.
- **Default Subtitle Style — White Cinematic Boxless (`1029` / `1014` Standard)**:
  - `font_path`: `~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts/Menlo-Regular.ttf` (`font_name = "Menlo-Regular"`, `font_title = "Menlo"`)
  - `text_color`: `#FFFDF8` (`rgb = [1.0, 0.992157, 0.972549]`), `font_size = 4.2`, `letter_spacing = 0.01`, `line_spacing = 0.02`, `alignment = 1`
  - `seg["clip"]["transform"]`: `{"x": 0.0, "y": -0.74}` (raised slightly to clear the YouTube playback bar), `scale = 1.0`, `uniform_scale = {"on": True, "value": 1.0}`
  - **Boxless (`Không viền xám xung quanh`)**: `background_style = 0`, `background_alpha = 0.0`, `background_color = ""`, `single_char_bg_enable = False`, **`check_flag = 15`** (`1|2|4|8` — never set bit `16`!)
  - **Stroke & Drop Shadow**:
    - Stroke: `border_color = "#000000"`, `border_width = 0.032`, `border_alpha = 0.90`, `border_mode = 0`
    - Shadow: `has_shadow = True`, `shadow_color = "#000000"`, `shadow_alpha = 0.82`, `shadow_distance = 2.0`, `shadow_smoothing = 0.14` (`diffuse = 0.14, feather = 0.14`), `shadow_angle = -45.0`
- **Reference-Matched Subtitle Profiles**:
  - **Warm Cinema Yellow Boxless (`1030` Reference)**:
    - Font: `Seravek-Medium.ttf` (extracted from `/System/Library/Fonts/Seravek.ttc` face index `3`)
    - Color & Size: `#E5CE6E` (`[0.898039, 0.807843, 0.431373]`), `font_size = 4.2`, `letter_spacing = 0.0`, `y = -0.78`, `check_flag = 15`, `background_style = 0`, `background_alpha = 0.0`
    - Stroke & Shadow: Stroke `#0A0C0E` (`width = 0.028`, `alpha = 0.95`) + Shadow `#050608` (`alpha = 0.82`, `distance = 1.8`, `smoothing = 0.20`, `angle = -45.0`)
  - **Translucent Dark Box Monospace (`1026` Reference)**:
    - Font: `Menlo-Regular.ttf`, Color `#FFFFFF`, `font_size = 4.0`, `y = -0.73`, `check_flag = 23` (`15 | 16`), `background_style = 1`, `background_color = "#000000"`, `background_alpha = 0.60`, `background_width = 0.14`, `background_height = 0.14`, `background_round_radius = 0.08`, **`background_horizontal_offset = 0.0`, `background_vertical_offset = 0.0`** *(never `0.5, 0.5`, which offsets the box up-right off the text!)*.

### 2.3. Cinematic Cards Architecture, Placement & Film-Matched Themes
- **Two Dedicated Editable Tracks**:
  - `Cinematic Cards · Main`: Primary line (Character Name, Time Jump, or `THE END`).
  - `Cinematic Cards · Detail`: Secondary line (Concise Character Role or Location/Context).
- **Upper-Corner Placement (`y > 0`) & Shot-Cut Verification (`ffmpeg scdet`)**:
  - Place cards in the upper-left (`x = -0.38 .. -0.48`) or upper-right (`x = +0.38 .. +0.48`), with `y_main = +0.62 .. +0.72` and `y_detail = +0.49 .. +0.57`.
  - Because cards sit in the upper corners while subtitles sit at the bottom (`y = -0.74 .. -0.78`), **cards never collide with subtitles and do NOT need to dodge speech**.
  - Introduce each principal character at their **first clear recognizable appearance** (`0.3s–0.6s` after the shot begins), even while they are speaking.
  - Extract video frames and run `ffmpeg -vf scdet=threshold=12` across each card window (accounting for compound clip trims and speed, e.g. `t_tl = clip_start + (t_src - src_start) / speed`) to:
    1. Pick left (`x < 0`) or right (`x > 0`) opposite the character's head/face in that shot.
    2. End the card **before** an internal shot cut switches to another person or a close-up insert (hands/props/shoes).
- **Scale Synchronization & Pixel Overflow Guard (`Zero Clipping`)**:
  - Always set `seg["clip"]["scale"] = {"x": s, "y": s}` AND `seg["uniform_scale"] = {"on": True, "value": s}` to the exact same value `s`.
  - In CapCut `1920x1080`, `1.0` native `font_size` unit renders at roughly `28–30 px` before multiplying by `scale`.
  - Measure every card's Main and Detail line using `PIL.ImageFont.truetype(font_path, int(round(font_size * 28.5 * scale)))` (including letter spacing). Ensure `left_px >= 96` and `right_px <= 1824` (`5%` safe margin). If a long line approaches the border, pull `abs(x)` inward (`±0.36 .. ±0.42`) or break into 2 balanced lines.
- **Film-Matched Card Style Presets (Adaptable per Script)**:
  1. **Warm Heritage / Drama (`1026` / `1029`)**:
     - Font: `Georgia.ttf`
     - Main: Warm Cream `#FFF4DF` (`size = 7.2..7.5`, `scale = 1.22`, `spacing = 0.05..0.08`)
     - Detail: Honey Gold `#E0C080` (`size = 3.8`, `scale = 1.22`, `spacing = 0.06..0.12`)
     - `THE END`: `#FFF4DF` (`size = 5.8`, `scale = 1.0`, `spacing = 0.26`, `x = 0.0, y = 0.68`)
  2. **Southern / Copper Soul (`1014`)**:
     - Main Font: `Times New Roman.ttf` — Character Name in Alabaster `#FFF8EE` (`size = 7.4`, `scale = 1.22`), Time/Location in Antique Brass `#F4CD88` (`size = 7.2`, `scale = 1.20`)
     - Detail Font: `Georgia Italic.ttf` in Warm Copper `#E5A968` (`size = 3.9`, `scale = 1.20`, `italic = True`)
     - Stroke & Shadow: Espresso `#1A110B` (`width = 0.024`, `alpha = 0.78`) + soft black shadow (`alpha = 0.85, distance = 2.2, smoothing = 0.12`)
  3. **Christmas / Festive Hearth (`1030`)**:
     - Main Font: `Baskerville-SemiBold.ttf` (`size = 6.2`, `scale = 1.0`, `spacing = 0.02`)
     - Detail Font: `Baskerville-SemiBoldItalic.ttf` (`size = 4.4`, `scale = 1.0`, `spacing = 0.01`, `italic = True`)
     - Colors: Time/Location Main Candlelight Gold `#FCE29C` / Detail Warm Spiced Holly `#F4B886`; Character Main Snow Alabaster `#FFFDF7` / Detail Champagne Gold `#F5CE78`
     - Stroke & Shadow: Deep Evergreen Pine `#142219` (`width = 0.055`, `alpha = 0.96`) + Warm Hearth Shadow `#1A0E0A` (`alpha = 0.88, distance = 2.2, smoothing = 0.28`)
  4. **Modern Thriller / Urban Cool**:
     - Main Font: `Optima-Regular.ttf` (`#F4F7FA`, `size = 6.5`, `scale = 1.15`), Detail `#9CC2DF` (`size = 4.0`, `scale = 1.15`), dark slate stroke `#0A1018` (`width = 0.035`).

### 2.4. Draft Mirror Synchronization & Delta-Patch Cleanup
- Always back up `<PROJECT>/draft_info.json` (and any `Timelines/*/attachment/patch/*` files) to a timestamped folder outside the CapCut project directory before writing.
- Write the updated JSON identically to `<PROJECT>/draft_info.json` and `<PROJECT>/Timelines/<MAIN_UUID>/draft_info.json` (plus any existing `draft_content.json` / `template-2.tmp` mirrors).
- **Crucial Delta-Patch Rule**: Check `<PROJECT>/Timelines/<MAIN_UUID>/attachment/patch/mini_draft.json` and `patch.json`. If `mini_draft.json` is a CapCut delta-patch object (`{"base_mini_draft_has_ack": ..., "mini_draft_data": ...}`), back up and remove both `mini_draft.json` and `patch.json` so CapCut loads the updated `draft_info.json` directly instead of replaying stale delta patches over your tracks.
