# Editorial guide

## Necessity before decoration

An explicit jump such as "three months later" can need a card. A walk into another room usually does not. Let a clear establishing shot speak. Combine time and location when they convey one transition. Use only facts established by the script, captions, audio or a supplied reference. A project filename is not a story date.

Existing Black Fade transitions are candidate anchors, not instructions to label every fade. In this schema the transition is commonly referenced by the outgoing segment; its cut is that segment's target end. Transition duration is not an automatically safe reading interval. Do not replace, lengthen or duplicate the fade.

If 1.5 seconds of fade is too short, show a quiet 3.2-second lower-third over confirmed empty space after the transition. Never create 3.2 seconds of black by hiding the outgoing reaction or incoming scene. If the whole display window is busy, move within the same scene, shorten the wording or omit the card. Do not shift it across another story beat merely to satisfy duration.

## Character introductions

- Read the character list and match identities against supplied portraits, scene metadata or unambiguous on-screen/dialogue evidence. A face alone is insufficient to infer a real or fictional identity.
- Review the timeline from the start up to the candidate, using scene metadata to narrow frames. Distinguish first voice, first glimpse, disguise and first recognizable appearance. Do not claim first appearance from one isolated window.
- Introduce principal characters once. Default to name plus a short established role, such as "Restorer", "Hotel owner" or "Father"; use the film's language. The role identifies a job or relationship, not a label such as villain or future redemption. Avoid biographies, spoilers and invented credentials. For explicit names-only requests, unknown roles or mystery-sensitive introductions, omit the role and record `evidence.role_omission_reason` rather than guessing.
- Start usually 0.4–1 second after the face is clearly recognizable. A small name/role identifier may appear during dialogue; do not wait several seconds solely for the speaker to finish. Defer for an actual identity reveal, demanding story beat or visual obstruction, recording the reason.
- Place each name/role pair on or beside its actual person, with an unambiguous association throughout the hold. An empty corner beside somebody else is an incorrect placement. Preserve manually corrected timing and positions.
- When two people are introduced in a clear two-shot, separate name/role pairs near the respective people can be clearer than sequential labels or a combined name line. Synchronize their display and fades when appropriate, without repeating an earlier introduction. The current helper rejects overlapping card intervals: this layout is an editorial target, not a supported plan option. Do not bypass that validator or ownership checks to obtain it.
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

Default 16:9 time/location placement is lower-left, x=-0.52, primary y=-0.66, detail y=-0.79. Character cards with a role use primary y=-0.64, role y=-0.77, sizes 6.2/3.8 in native units, and a warmer, legible secondary color for heritage drama. Explicit plan style/position wins. Keep both lines visible for the same interval; shorten roles before adding reading pressure. A shared card can introduce an established pair when appropriate, rather than crowding an entrance with consecutive labels.

Coordinates are CapCut normalized anchors, not bounding boxes: text can extend beyond them. Other aspect ratios, captions or long text require fresh layout review and adjusted size/position. Centered type is reserved for an actual quiet/negative-space interval, not an excuse to obscure a subject. Hardcoded safe coordinates cannot replace frame review.

For user-supplied subtitle styling and combined title/caption layouts, read [subtitle references and layout](subtitle-layout.md). A supplied reference takes precedence over generic subtitle styling, while the film-specific character-card system remains separate unless the user asks to match it too.

Use a soft black shadow and restrained opacity ramps. The helper implements editable typography and opacity only. Glitch, tracking animation, moving titles, freeze frames, matte backgrounds and external effect packs are outside this version. Do not invent effect IDs. If a request depends on unsupported effects, explain the limit and use an appropriate supported treatment only within the user's intent.

## Evidence and limits

Inspect frames before, at and throughout the card, not only a thumbnail. Review all audible stems: a voice can start before the picture cut. FFmpeg source frames do not reproduce CapCut compositing, motion, crop, masks, subtitles or transitions. Inspect those draft properties too; if they prevent confident placement, defer. Local ASR can miss soft dialogue, music lyrics or overlapping speech. Do not mark a region silent solely because a model produced no words.

Stage and verify are structural checks. A successful JSON round trip proves neither font rendering nor CapCut playback. State this distinction in delivery. Exact ownership hashes may change when CapCut saves its normalized representation; stop and reconcile those changes without deleting or replacing user work.
