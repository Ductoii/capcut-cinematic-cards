# Tooling & Plan Schema (`cards.py`, `styles.py`, `native_text.py`)

The helper scripts in `scripts/` support both **streamlined direct execution (`version: 3`)** — our recommended workflow from production passes `1026`, `1029`, `1014`, and `1030` — and legacy `version: 1` / `version: 2` plans for backward compatibility.

---

## 1. CLI Commands

Always run with a Python 3 environment that includes `fontTools` and `Pillow` (e.g., `/Users/daho100/miniconda3/bin/python3`):

```bash
# 1. Inspect project timeline, compound clip spans, and existing subtitle track
/Users/daho100/miniconda3/bin/python3 scripts/cards.py inspect "<PROJECT_OR_DRAFT_PATH>"

# 2. Extract needed .ttc faces into standalone .ttf files in both ~/Library/Fonts and CapCut sandbox
/Users/daho100/miniconda3/bin/python3 scripts/cards.py ensure-fonts --theme warm-heritage --subtitle-preset white-cinematic-boxless

# 3. Validate a plan (checks overflow, durations, default THE END, and native fades)
/Users/daho100/miniconda3/bin/python3 scripts/cards.py validate "<PROJECT_OR_DRAFT_PATH>" --plan "<PLAN.json>"

# 4. Apply cards + in-place subtitle styling directly to all synced draft files (and clean delta patches)
/Users/daho100/miniconda3/bin/python3 scripts/cards.py apply "<PROJECT_OR_DRAFT_PATH>" --plan "<PLAN.json>"

# 5. Remove managed card tracks (if resetting cards)
/Users/daho100/miniconda3/bin/python3 scripts/cards.py clear "<PROJECT_OR_DRAFT_PATH>"
```

---

## 2. Streamlined `version: 3` Plan Schema (Recommended)

`version: 3` plans remove the bureaucratic multi-file subagent review lockstep (`probe.json` / `bundle.json` / `verdict.json`) while enforcing the real production invariants:
- **Default `THE END` card**: Required unless `"include_ending": false` is set on the plan.
- **Default Native CapCut `Fade In` (`0.7s`) + `Fade Out` (`0.5s`)**: Automatically attached to every card (`Main`, `Detail`, and `THE END`) via `materials.material_animations` (`type = "sticker_animation"`), with `common_keyframes = []`.
- **Upper-Corner Card Placement (`y > 0`)**: Coexists cleanly with bottom subtitles (`y = -0.74` / `-0.78`) without blocking cards during dialogue.
- **Automatic `.ttc -> .ttf` Sandbox Font Extraction**: Extracts required font faces to both `~/Library/Fonts/` and `~/Library/Containers/com.lemon.lvoverseas/Data/Library/Fonts/`.
- **In-Place Subtitle Styling**: Styles existing CapCut Auto-Captions (`type = "subtitle"`) in-place with zero timing drift, supports ASR typo fixes (`text_overrides`) and noise hallucination removal (`remove_segment_ids`), and cleans `mini_draft.json` / `patch.json`.

### Example `version: 3` Plan JSON

```json
{
  "version": 3,
  "theme": "southern-copper",
  "include_ending": true,
  "fade_in_us": 700000,
  "fade_out_us": 500000,
  "subtitles": {
    "preset": "white-cinematic-boxless",
    "y": -0.74,
    "wrap_width": 42,
    "text_overrides": {
      "SEG_ID_OPTIONAL": "Corrected dialogue line\nwrapped cleanly"
    },
    "remove_segment_ids": []
  },
  "cards": [
    {
      "id": "card_01",
      "type": "location",
      "start_s": 0.35,
      "end_s": 4.20,
      "x": -0.50,
      "y": 0.72,
      "dy": 0.11,
      "main": "HARLAN COUNTY, KENTUCKY",
      "detail": "AUTUMN — PRESENT DAY"
    },
    {
      "id": "card_02",
      "type": "character",
      "start_s": 9.40,
      "end_s": 13.00,
      "x": -0.52,
      "y": 0.72,
      "dy": 0.11,
      "main": "CALEB MERCER, 34",
      "detail": "THE PRODIGAL SON"
    },
    {
      "id": "card_end",
      "type": "ending",
      "start_s": 1411.50,
      "end_s": 1415.30,
      "x": 0.0,
      "y": 0.02,
      "main": "THE END",
      "detail": ""
    }
  ]
}
```

---

## 3. Built-In Card Themes & Subtitle Presets (`scripts/styles.py`)

### Card Themes (`theme`)
- `warm-heritage`: `Didot-Bold` (`#F6EFE2` Warm Cream) + `AvenirNext-DemiBold` (`#E5B869` Burnished Gold)
- `southern-copper`: `Baskerville-SemiBold` (`#FAF3E6` Warm Ivory) + `AvenirNext-Medium` (`#E0A958` Burnished Amber Gold)
- `christmas-hearth`: `Baskerville-Bold` (`#FCE8B2` Warm Candlelight Gold) + `Optima-Bold` (`#F4F7EE` Frosted Holly Cream)
- `modern-thriller`: `AvenirNext-Bold` (`#F2F5F8` Crisp Ice White) + `Menlo-Bold` (`#D9A441` Steel Amber)

### Subtitle Presets (`subtitles.preset`)
- `white-cinematic-boxless` *(Default)*: `Menlo-Regular.ttf`, `size = 4.2`, `#FFFDF8` Warm Paper White, `y = -0.74`, `check_flag = 15` (boxless), dark stroke (`0.016`) + shadow.
- `yellow-cinema-boxless`: `Seravek-Medium.ttf`, `size = 4.4`, `#E5CE6E` Warm Cinema Yellow, `y = -0.78`, `check_flag = 15` (boxless), dark stroke (`0.012`) + shadow.
- `boxed-monospaced`: `Menlo-Regular.ttf`, `size = 4.1`, `#FFFDF8`, `y = -0.74`, `check_flag = 23` (boxed), translucent dark pill `#14110E` (`alpha = 0.62`, `offset = 0.0, 0.0`).

---

## 4. Multi-Draft Synchronization & Delta-Patch Cleanup

When `apply` writes a project, it automatically:
1. Creates a timestamped backup in `<PROJECT>/.cards-backups/<timestamp>/`.
2. Writes identical updated state to all active draft files:
   - `<PROJECT>/draft_info.json`
   - `<PROJECT>/draft_content.json` (if present)
   - `<PROJECT>/Timelines/<Timeline>/draft_info.json` (if present)
   - `<PROJECT>/Timelines/<Timeline>/attachment_action_scene.json` (cleaned when noise subtitle segments are removed)
3. Deletes stale `mini_draft.json` and `patch.json` files inside `<PROJECT>` and `<PROJECT>/Timelines/<Timeline>/` so CapCut loads the full `draft_info.json` instead of re-applying cached delta patches.
