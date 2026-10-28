# Editorial guide

## Necessity before decoration

An explicit jump such as "three months later" can need a card. A walk into another room usually does not. Let a clear establishing shot speak. Combine time and location when they convey one transition. Use only facts established by the script, captions, audio or a supplied reference. A project filename is not a story date.

Existing Black Fade transitions are candidate anchors, not instructions to label every fade. In this schema the transition is commonly referenced by the outgoing segment; its cut is that segment's target end. Transition duration is not an automatically safe reading interval. Do not replace, lengthen or duplicate the fade.

For a necessary scene-change card, review the outgoing fade, the cut and the incoming shot together before defaulting to a timestamp several seconds later. A restrained lower-third can begin in the fade and continue into negative space in the new shot. Record the actual cut, the full text interval and the reason if dialogue, an entrance or a reveal requires postponing it. The opaque part of the transition need not contain the whole title. A cut without an existing fade remains a cut.

If 1.5 seconds of fade is too short, show a quiet 3.2-second lower-third over confirmed empty space after the transition. Never create 3.2 seconds of black by hiding the outgoing reaction or incoming scene. If the whole display window is busy, move within the same scene, shorten the wording or omit the card. Do not shift it across another story beat merely to satisfy duration.

## Character introductions

- Read the character list and match identities against supplied portraits, scene metadata or unambiguous on-screen/dialogue evidence. A face alone is insufficient to infer a real or fictional identity.
- Review the timeline from the start up to the candidate, using scene metadata to narrow frames. Distinguish first voice, first glimpse, disguise and first recognizable appearance. Do not claim first appearance from one isolated window.
- Introduce principal characters once. Default to name plus a short established role, such as "Restorer", "Hotel owner" or "Father"; use the film's language. The role identifies a job or relationship, not a label such as villain or future redemption. Avoid biographies, spoilers and invented credentials. For explicit names-only requests, unknown roles or mystery-sensitive introductions, omit the role and record `evidence.role_omission_reason` rather than guessing.
- Account for the entire principal cast in `character_review`: confirmed name/ID, linked card or an explicit omission reason. Review a later quiet beat in the same continuous scene when the first entrance is busy. A shared pair card lists both IDs and established roles. Report both the number of character cards and the number of people they introduce, so a pair is not mistaken for a missing introduction. The ledger checks consistency, not the truth of an identity or completeness of a screenplay the assistant has not read.
- Start usually 0.4–1 second after the face is clearly recognizable. A small name/role identifier may appear during dialogue; do not wait several seconds solely for the speaker to finish. Defer for an actual identity reveal, demanding story beat or visual obstruction, recording the reason.
- Place each name/role pair on or beside its actual person, with an unambiguous association throughout the hold. An empty corner beside somebody else is an incorrect placement. Preserve manually corrected timing and positions.
- When two people are introduced in a clear two-shot, separate name/role pairs near the respective people can be clearer than sequential labels or a combined name line. Synchronize their display and fades when appropriate, without repeating an earlier introduction. Declare a reviewed `simultaneous_group`, one person per card, separate full-label `bounds`, identity association and a complete principal ledger. The helper keeps each label on independent editable tracks and rejects other overlaps.
- Keep labels away from faces, eyelines, meaningful hands/props and the full subtitle text/background bounds. Reserve the subtitle reading band first, then place the name/role near its person elsewhere. Review cuts and movement across the complete hold; anchor coordinates alone do not prove that two rendered boxes are separate.
- Preserve mystery: do not disclose an identity before the film does. Distinguish same-name characters with established information only.

## A style for this film

First infer genre, period, emotional temperature, lighting palette, pace and existing titles from actual material. Select one installed font and one consistent system. Do not automatically force capitals: Vietnamese names and mixed-case roles often read better as written.

| Starting theme | Local font direction | Treatment |
|---|---|---|
| `heritage-drama` | Baskerville, Georgia or similar serif | Warm ivory; deliberate 0.4s opacity fade |
| `modern-thriller` | Restrained sans or condensed face | Cool white; tighter size and 0.28s fade |
| `documentary` | Neutral readable sans | Minimal spacing; factual hierarchy; 0.25s fade |
| `intimate-romance` | Soft serif with full language support | Warm pale color; gentle 0.6s fade |
| `noir` | Period-appropriate serif or restrained sans | Off-white; clear contrast; 0.35s fade |

Themes are starting values, not automatic genre detection. Choose `--font` explicitly when the default serif does not suit the film. Override color, size, spacing, fade and position within documented bounds. No fonts are distributed. Check font glyph coverage on the local machine and inspect longer names at the proposed size.

Derive the treatment from this film: for example, a recording-studio drama may suit compact sans headings and a restrained copper secondary line rather than another warm serif preset. Check punctuation as well as names: a font can contain all English letters but lack a middle-dot separator. Replace an unsupported decorative separator or choose a fully supported font; never silently render missing glyphs.

Default 16:9 time/location placement is lower-left, x=-0.52, primary y=-0.66, detail y=-0.79. Character cards with a role use primary y=-0.64, role y=-0.77, sizes 6.2/3.8 in native units, and a warmer, legible secondary color for heritage drama. Explicit plan style/position wins. Keep both lines visible for the same interval; shorten roles before adding reading pressure. A shared card can introduce an established pair when appropriate, rather than crowding an entrance with consecutive labels.

Coordinates are CapCut normalized anchors, not bounding boxes: text can extend beyond them. Other aspect ratios, captions or long text require fresh layout review and adjusted size/position. Centered type is reserved for an actual quiet/negative-space interval, not an excuse to obscure a subject. Hardcoded safe coordinates cannot replace frame review.

For user-supplied subtitle styling and combined title/caption layouts, read [subtitle references and layout](subtitle-layout.md). A supplied reference takes precedence over generic subtitle styling, while the film-specific character-card system remains separate unless the user asks to match it too.

Use a soft black shadow and restrained opacity ramps. The helper generates editable typography and opacity ramps; optional native entry reuse is described below. Glitch, tracking animation, moving titles, freeze frames, matte backgrounds and external effect packs are outside this version. Do not invent effect IDs. If a request depends on unsupported effects, explain the limit and use an appropriate supported treatment only within the user's intent.

Opacity ramps and CapCut's native animation tab are different. An explicit `native_fade_in` option can reuse an existing, reviewed local entry animation already attached to a text segment. Pin its resource files and apply the same entry to title and role together. It does not download effects or generate effect IDs. Existing different animations cause refusal instead of being discarded. Preserve the user's current animation when restyling after a CapCut save.

For a requested `THE END`, use `kind: ending` on a quiet existing final shot after the last meaningful line. Put it away from the final face, gesture and prop. Keep the timeline length and picture intact. If no readable hold exists, report that limit rather than inventing extra black or covering the final reveal.

## Evidence and limits

Inspect frames before, at and throughout the card, not only a thumbnail. Review all audible stems: a voice can start before the picture cut. FFmpeg source frames do not reproduce CapCut compositing, motion, crop, masks, subtitles or transitions. Inspect those draft properties too; if they prevent confident placement, defer. Local ASR can miss soft dialogue, music lyrics or overlapping speech. Do not mark a region silent solely because a model produced no words.

Stage and verify are structural checks. A successful JSON round trip proves neither font rendering nor CapCut playback. State this distinction in delivery. Exact ownership hashes may change when CapCut saves its normalized representation; stop and reconcile those changes without deleting or replacing user work.

`inspect.ownership` reports exact current hashes, changed IDs and missing IDs. For a deliberate restyle, compare against the last staged draft and record the findings with those fresh hashes. `restyle` preserves saved wording (unless `replace_text: true`), timing, layout, keyframes, rich-text properties, effects and unknown defaults. It may add a missing reviewed character card, but cannot reclaim a removed ID or silently overlap an unlisted existing card. The ownership review itself is never written into the project before the guarded transaction.

Probe JPEG output explicitly uses a compatible full-range pixel format. When a requested boundary lies inside the final video sample, the manifest records that sample's actual PTS. A video/audio tail shorter than one frame is separately marked `last_available_video_frame` with a warning; it is available source evidence, not proof of how CapCut holds or composites it. Larger overshoots remain errors. Never treat a source-tail warning as silence or verified black, and defer a title whose placement depends on unresolved native behavior.


## Preventing title overflow without locking the art direction

A font size in the draft is a **native text unit**, not a pixel size. There is no universal px/native conversion: use the actual selected font, canvas, scale, tracking and a locally calibrated conservative measurement. A count of characters or a safe anchor does not establish that text fits. Include both lines, shadow/stroke, native animation excursions and any background in the full-hold bounds. Source-font diagrams are estimates, not native rendering proof.

Use a local font appropriate to this film (`--font`, root `font`, or per-card `font`); no family is mandatory or bundled. Presets are optional starting values. On `restyle`, only explicitly supplied style fields change; an explicit theme resets the preset typography. Omit the font override to preserve current fonts, including independently styled roles. Saved timing, positions, effects, wording and defaults stay intact unless an explicit repair is requested.

For long labels, use up to two intentional lines, shorten established role wording only when authorized, or adjust size/spacing/position after reviewing the actual layout. Native `text_layout` options are explicit and per card: `scale` synchronizes clip and uniform scale; `line_max_width` enables native width limiting; `fixed_width` uses reviewed native width units, never an assumed pixel conversion. `title_x/y` and `detail_x/y` repair a saved placement only with fresh bounds and layout findings. Do not copy another project's Georgia/Avenir/font sizes/coordinates into all films.

`bounds` and `exclusion_zones` are reviewed rectangles `[left, bottom, right, top]` in normalized canvas coordinates (x rightward, y upward), covering the entire hold and both name/role extents. The helper checks these declared rectangles against the 5% safe margin and each other; it cannot infer rendered text bounds or who a face belongs to. For a moving shot, use conservative unions across all reviewed frames. A single character label still needs clear association with its own person; an empty corner beside somebody else is incorrect.
