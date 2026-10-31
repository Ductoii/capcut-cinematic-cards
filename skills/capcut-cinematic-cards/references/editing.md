# Cinematic Card Design & Editorial Placement

Every rule below is derived from real production passes on macOS CapCut Desktop (`1026` Warm Heritage, `1029` Southern Copper & Warm Ivory, `1014` Warm Heritage, `1030` Christmas Hearth & Pine).

---

## 1. Mandatory Pre-Task Intake

When a user request is underspecified (e.g., *"làm card cho prj 1030"* or *"create cards for project X"*), **always ask the user for these 3 inputs before modifying the CapCut draft**:

1. **Kịch bản (`Screenplay / Script`)** *(Required)* — Needed for exact character names, ages, roles, locations, and chronological time jumps.
2. **Phong cách Card mong muốn (`Card Style`)** *(Optional — auto-adjust to script genre if omitted)* — Ask if they want a specific aesthetic (e.g., Christmas, Vintage 1970s, Southern Drama, Thriller); if the user says "tuỳ chỉnh theo phim" or does not specify, automatically design the font + color palette to match the script's genre and tone.
3. **Ảnh mẫu Subtitle (`Subtitle Reference Image`)** *(Optional — defaults to Classic White Cinematic Boxless)* — Ask if they have a reference screenshot for subtitle styling; if not specified, default to the **Classic White Cinematic Boxless** preset (`#FFFDF8` Warm Paper White, `Menlo-Regular.ttf`, `size = 4.2`, `y = -0.74`, `check_flag = 15`, no grey/black box, subtle dark stroke + drop shadow).

---

## 2. Core Editorial Rules

### 2.1 Story-Jump Anchoring (Never Depend on Timeline Black Fades)
- **Never** rely on CapCut timeline black fades (`fade in` / `fade out` transitions) to decide when or whether to place a Time or Location card.
- Many cuts have no black fade even when the story jumps years, days, or hours forward, and some black fades are purely dramatic pauses within the same scene.
- Always track **time jumps** (`SIX YEARS LATER`, `DECEMBER 24 — 3:00 PM`, `CHRISTMAS EVE — 11:45 PM`, `CHRISTMAS MORNING`, `TEN YEARS LATER`) and **location changes** (`MAIN DINING ROOM`, `24-HOUR ROADSIDE DINER`) directly from the **script + spoken dialogue cues + visual scene changes**.

### 2.2 Default `THE END` Card
- **Always** place a `THE END` card (`type = ending`) on the closing hold of the film by default.
- Only omit `THE END` when the user explicitly requests no ending card (e.g., *"kịch bản này không cần làm the end"* -> `include_ending: false`).
- Keep `THE END` centered (`x = 0.0`, `y = 0.0` or `0.02`) with a generous hold (`3.0s–4.5s`) before the timeline ends.

### 2.3 Default Native CapCut `Fade In` + `Fade Out` on Every Card
- **Every card** (`Main`, `Detail`, and `THE END`) must have native CapCut **Fade In (`0.7s` = `700,000 us`) + Fade Out (`0.5s` = `500,000 us`)** in `materials.material_animations` (`type = "sticker_animation"`), linked via `segment.extra_material_refs = [anim_id]` with `segment.common_keyframes = []`.
- Verified CapCut resource IDs:
  - **In (`Fade In`)**: `id = "6724916044072227332"`, `resource_id = "6724916044072227332"`, `name = "Fade In"`, `duration = 700000`, `start = 0`.
  - **Out (`Fade Out`)**: `id = "6724919382104871427"`, `resource_id = "6724919382104871427"`, `name = "Fade Out"`, `duration = 500000`, `start = card_duration_us - 500000`.
- Why native `material_animations` instead of `common_keyframes` (`KFTypePositionY` / `KFTypeAlpha`):
  - Combining `KFTypePositionY` slide-up keyframes with `KFTypeAlpha` causes cards to jump or clip near shot cuts and prevents users from tweaking fade durations in CapCut's `Animation -> In/Out` inspector tab.

### 2.4 Upper-Corner Card Placement (`y > 0`) & Coexistence with Subtitles
- Subtitles sit at the bottom center (`y = -0.74` to `-0.78`).
- Place **Location / Time / Character cards** in the **upper corners (`y = +0.50` to `+0.76`)** or upper screen zones so they **never collide with bottom subtitles**.
- Because upper-corner cards do not overlap bottom subtitles, **never delay a character card past the character's shot just to wait for dialogue to stop**. A character card must appear while that character's face is actually on screen.
- When a card consists of **Main** (`Track A`) + **Detail** (`Track B`):
  - Keep vertical gap `Δy ≈ 0.10–0.13` so multi-line Main titles never overlap Detail lines (`gap >= 30 px`).
  - Stagger Detail entry by `+180ms` (`180,000 us`) after Main entry; end both together so they fade out cleanly as a unit.

### 2.5 Shot-Boundary Verification (`ffmpeg scdet`)
- Before finalizing any Character or Location card timestamp, run `ffmpeg -vf "scdet=threshold=12" -f null -` on the source video or inspect frames at `start + 0.3s`, `mid`, and `end - 0.3s`.
- Ensure the card ends at least `0.15s–0.20s` before the camera cuts away to another character or angle.
- Hold durations:
  - **Location / Time cards**: `3.0s–4.2s`
  - **Character introductions**: `2.6s–3.8s` (clamped to the character's actual on-screen shot)
  - **Ending (`THE END`)**: `3.0s–4.5s`

---

## 3. Film-Matched Card Themes & Palettes

When the user does not specify a custom card style, choose or adapt the preset below that best matches the script's genre and visual palette:

### 3.1 `warm-heritage` (Family / Institutional / Period Drama — e.g., `1026`, `1014`)
- **Primary (`Main` / `THE END`)**: `Didot-Bold` (`Didot-Bold.ttf`), Warm Cream `#F6EFE2` (`[0.965, 0.937, 0.886]`), stroke `#100B08` (`width = 0.018`).
- **Secondary (`Detail`)**: `AvenirNext-DemiBold` (`AvenirNext-DemiBold.ttf`), Burnished Gold `#E5B869` (`[0.898, 0.722, 0.412]`), stroke `#100B08` (`width = 0.016`).

### 3.2 `southern-copper` (Southern / Rural / Nostalgic Drama — e.g., `1029` *The Sunday Chair*)
- **Primary (`Main` / `THE END`)**: `Baskerville-SemiBold` (`Baskerville-SemiBold.ttf`), Warm Ivory `#FAF3E6` (`[0.980, 0.953, 0.902]`), stroke `#120C07` (`width = 0.018`).
- **Secondary (`Detail`)**: `AvenirNext-Medium` (`AvenirNext-Medium.ttf`), Burnished Amber Gold `#E0A958` (`[0.878, 0.663, 0.345]`), stroke `#120C07` (`width = 0.016`).

### 3.3 `christmas-hearth` (Holiday / Winter / Christmas Drama — e.g., `1030` *One More Bowl*)
- **Primary (`Main`)**: `Baskerville-Bold` (`Baskerville-Bold.ttf`), Warm Candlelight Gold `#FCE8B2` (`[0.988, 0.910, 0.698]`), stroke `#1A0D08` (`width = 0.018`).
- **Secondary (`Detail`)**: `Optima-Bold` (`Optima-Bold.ttf`), Frosted Holly Cream `#F4F7EE` (`[0.957, 0.969, 0.933]`), stroke `#1A0D08` (`width = 0.016`), prefixed with `✦  ` for festive elegance.

### 3.4 `modern-thriller` (Crime / Investigative / Neo-Noir)
- **Primary (`Main` / `THE END`)**: `AvenirNext-Bold` (`AvenirNext-Bold.ttf`), Crisp Ice White `#F2F5F8` (`[0.949, 0.961, 0.973]`), stroke `#080B10` (`width = 0.018`).
- **Secondary (`Detail`)**: `Menlo-Bold` (`Menlo-Bold.ttf`), Steel Amber `#D9A441` (`[0.851, 0.643, 0.255]`), stroke `#080B10` (`width = 0.016`).

---

## 4. Pixel-Accurate Overflow & Safe-Zone Math (`PIL.ImageFont`)

CapCut maps font `size` on a `1920x1080` canvas at approximately:
- `px_size ≈ size * 13.0` (e.g., `size = 6.2` -> `~81 px`; `size = 4.2` -> `~55 px`).
- Horizontal coordinate `x` in `[-1.0, +1.0]` maps to `center_x_px = (x + 1.0) * 0.5 * 1920`.
- Left/right edges of a centered text block (`alignment = 1`) with measured pixel width `w`:
  - `left_px = center_x_px - w / 2`
  - `right_px = center_x_px + w / 2`
- **Mandatory Safe Margin**:
  - `left_px >= 65` and `right_px <= 1855` (`>= 65 px` from both canvas edges).
  - If a corner card placed at `x = ±0.52` has a wide title (e.g., `30 YEARS LATER — CHRISTMAS DAY` or `THE VALE HOUSEHOLD`), either wrap the title across 2 lines (`\n`) or shift `x` inward (`±0.44` to `±0.48`) until `left_px >= 65` and `right_px <= 1855`.
