# Connected CapCut workspace and source-aware dialogue leveling

Status: implement directly. The user explicitly delegated the audio method and asked to stop approval/recheck/300-source verification loops. This instruction supersedes the previous approval and verification gates below. Supersedes the finite-command and separate-card-skill decisions of the v0.2.0 design. Existing backup, stale-project, editor-closed and exact Undo invariants remain requirements.

## User intent

In a fresh local Codex desktop chat, invoking `$capcut-harness` starts one workspace in the adjacent panel. The workspace offers cinematic cards and dialogue balancing, and a free-text box sends requests to that same chat. The current Codex agent interprets requests, selects tools and reports results. There is no second LLM, API key, new chat or shell parser masquerading as Codex.

The unified skill owns necessary time/location cards and first-appearance character introductions, including established roles and film-specific typography. Preserve the user's compound edits, important shots, dialogue and transitions. No Computer Use.

Dialogue from hundreds of source clips with different levels must be made consistently audible. A master peak ceiling alone is not normalization. Results must account for each source, including very quiet sources that the old detector missed.

## Evidence and approaches

- v0.2.0 sends `/api/command` into `parse_command`, a finite regex registry; no Codex connection exists.
- Native `send_message_to_thread` successfully sent a diagnostic to this exact chat and the chat received it. However, that proves a model-owned tool call only. Both an external Python client and a newly launched bundled app-tools MCP process were disconnected by the desktop native pipe. Local app source confirms socket-peer authorization. Do not bypass it or ship a direct pipe adapter as though this test had succeeded.
- `codex queue` is documented, but its default shared control socket is absent on this desktop instance. Starting another daemon or resuming the rollout in a separate process does not prove delivery to the app chat and is rejected as the default approach.
- A passive inbox would require the agent to remain in a polling turn and would stop waking it after that turn ends. It is not an equivalent replacement for the requested connection.
- An existing-backend experiment concatenated four copies of one spoken take with gains 0.004, 0.8, 0.03, 0.35. Input clip loudness was −58.87, −12.76, −41.28, −19.92 LUFS. Old output was −62.18, −13.25, −39.42, −17.92 LUFS. Only two speech spans were reported. Global VAD and a 12 dB gain cap cannot satisfy this case.

The selected recommendation is a **local plugin with an MCP App UI**, using the standard host-mediated `ui/message` bridge. It meets the same-chat requirement without taking over the app server, polling a model forever or bypassing native socket-peer authorization. The HTTP-only browser UI can remain a diagnostic fallback, visibly disconnected from chat; it is not the delivered primary workspace.

References: [official UI/plugin guidance](https://developers.openai.com/plugins/build/chatgpt-ui), [native Codex queue](https://learn.chatgpt.com/docs/developer-commands#codex-queue), [app-server lifecycle](https://learn.chatgpt.com/docs/app-server), [EBU streaming](https://tech.ebu.ch/docs/r/r128s2.pdf), [EBU cinematic loudness](https://tech.ebu.ch/files/live/sites/tech/files/shared/r/r128s4.pdf). Official UI guidance explicitly maps follow-up messages to MCP Apps `ui/message`. The EBU documents distinguish dialogue, programme loudness and true peak. No single measurement constitutes a universal “million-view YouTube film” standard.

## Connection and request lifecycle

1. The installer registers one local plugin, its self-contained `capcut-harness` skill, and a local stdio MCP server. In a fresh desktop chat the skill invokes the workspace-open tool, which returns a `text/html;profile=mcp-app` resource with `_meta.ui.resourceUri`. The component initializes through the host MCP Apps bridge, discovers its capabilities and requests an available expanded presentation beside the conversation. It does not rely on Computer Use or clicks to expose the workspace.
2. The host owns conversation routing. UI follow-ups use `ui/message` in the hosting chat; the UI does not choose arbitrary destination chats or call private native sockets. Each workspace has a durable random connection identifier, separate selected-project state, and a server-issued binding from the MCP invocation context. Multiple instances must not steal one another's selection or response records. Cross-host remote chats are outside this local version; the normal new-chat workflow on this Mac is required.
3. Display separate states for host UI bridge available, request saved, follow-up accepted by host, agent acknowledged, working and complete/blocked. A successfully opened HTTP port is not a chat connection. If the host requests message confirmation, preserve that native confirmation; never bypass it or claim a canceled message was sent.
4. Every user submit is persisted through a narrow MCP tool before `ui/message`: client-generated request UUID, original natural-language text, selected project/path, optional selected job/card context and workspace connection. Repeated submits with the same UUID are idempotent. Text is structured data, not shell interpolation, a command vocabulary or `eval`.
5. The follow-up visibly identifies its UI request UUID and contains the exact user request plus an instruction to retrieve the authoritative request context. Raw request text cannot choose another workspace's target or access backend-private credentials. Host/tool permission handling continues to apply.
6. On receipt, the same Codex agent retrieves and acknowledges the request using a structured MCP tool (or the equivalent authenticated CLI for diagnostics), works with normal tools and permissions, and publishes concise progress/result with relevant jobs/stages. The unified skill documents this handling for new chats and deduplicates already completed requests. Agent acknowledgment requires an explicit receipt; it is not inferred from successful host submission.
7. The browser renders server-persisted request events (UUID, monotonically increasing sequence, state, agent-published text, job/stage links) as inert text. Event reads are bounded and resumable by sequence. UI refresh reads those events; it does not scrape an unrelated chat history. Terminal transitions are complete, blocked, failed or canceled. Progress updates renew a working status without claiming completion.
8. Host rejection/cancel before dispatch stays unsent and retryable. A transport timeout after dispatch is `delivery_uncertain`, with no automatic resend. An explicit retry reuses the UUID, and agent handling checks stored state before any mutation. Closing and reopening the app preserves request records and job results.
9. UI card/audio request buttons use the same request channel with structured context. Playback, navigation, sliders and exclusions remain immediate UI actions. Apply/Undo retain the existing deterministic executor guards and authorization; a click explicitly requests the indicated action.
10. Data tools and rendering are separate: only workspace-open/refresh presentation tools carry UI metadata. The component calls narrow local MCP data/action tools, not an arbitrary HTTP proxy. Audio remains on loopback; return scoped read-only media capabilities to the UI through private tool metadata, with exact resource/connect CSP origins. Do not embed full PCM audio into model-visible tool results or upload it to a public server. Reuse existing HTTP range playback with a scoped media route if required by the host's UI sandbox. Verify real sandbox playback, not just a browser mock.

No account, model, reasoning, permissions or app-server configuration is silently changed. The installed host must actually support local MCP App rendering and `ui/message`. If it does not, that is an unresolved requirement to report and investigate; an unconnected browser/inbox is not acceptable completion. A mocked host is useful for tests but cannot prove native same-chat delivery.

Official [conversation-panel extension guidance](https://developers.openai.com/plugins/build/extensions) supplies the specific side-panel entrypoint: the render tool declares `_meta.ui.resourceUri` and `_meta["openai/ui"].entrypoints: [{"type":"thread"}]`. Use this host-supported conversation-panel surface for the requested adjacent UI, rather than assuming standard fullscreen means a side panel. Probe both panel presentation and `ui/message` in the installed desktop host; documentation alone is not a native acceptance result.

## Unified skill and card capability

- Install a self-contained `capcut-harness` skill in the local plugin containing shared startup/connection instructions and conditional references for dialogue and cards. Move canonical card scripts and references beneath that skill or the installed package; no dependency on a separately installed sibling skill.
- Preserve existing standalone card commands for backward compatibility. The previous skill may remain a minimal compatibility entrypoint, but the harness installation presents and documents a single primary skill. Never remove an unmanaged user skill during migration.
- Cards view offers time/location/character request choices and film/style instructions, and shows proposals, staged results and existing cards. Codex determines necessity/first appearance/verified role from source evidence; the deterministic backend validates and writes the plan. Merely listing existing text is insufficient.
- Keep evidence review, protected ranges, restrained readable timing, separate native text tracks and exact stage/apply/verify/restore behavior from the existing card workflow. Do not invent identity, role, date or place.

## Source-aware audio architecture

### Inventory and analysis

Keep existing strict timeline mapping (nested compounds, trims, constant speed, fades, gains and separated-audio ownership). Preserve hashes and all unsupported-source guards.

Decode and analyze each audible source segment before summation, with stable source-instance IDs including the compound ancestry. Gain-independent VAD uses a bounded, documented analysis-only level adjustment on each source; processing/rendered audio remains unmodified by that detector preparation. Pure silence stays silence. Record the detector adjustment and reliability flags. Never claim VAD isolates a voice from music or proves that noise/singing is dialogue.

Measure speech on the actual mapped source (timeline volume, speed and fades included), identify source boundaries explicitly and avoid merging speech across cuts. Record every source as speech candidate, no detected speech, excluded or unsupported. Very quiet sources and low-confidence/music-like candidates remain visible for Codex review; they cannot disappear from the denominator of a success claim.

Retain source data for re-rendering with changed targets/exclusions without losing provenance. Source selections and protected non-dialogue audio can be changed by Codex from available evidence; optional user controls do not require the user to repair a plan manually.

### Leveling and mastering

Default product preset: `Online film dialogue`, speech target −16 LUFS, final ceiling −1.5 dBTP, stereo 48 kHz PCM24. These are product choices, not a claimed YouTube delivery certification. The initial release needs this one default and editable targets; a second cinema preset is not required (YAGNI).

Use speech-anchored per-source correction, with a large explicit correction budget (up to 48 dB by default) to handle the demonstrated 46 dB range. Do not let the old 12 dB cap silently leave half the project quiet. Silence/noise detection, low-confidence flags and the measured required correction accompany large boosts.

Preserve intraphrase performance dynamics rather than forcing every short frame to one level. Support gentle residual phrase leveling within each source and controlled dynamics when source crest factor prevents the target under the ceiling. Do not turn a global final limiter into the primary leveling method. Report compression/limiting and remaining target misses; do not promise restoration of pre-existing clipped/distorted audio.

Render corrected source instances before mixing so a speech gain on one clip does not modulate an independent music/SFX track. A source whose speech and background are already baked together changes as a unit, and this is disclosed. Sources without accepted dialogue retain their original mapped audio. Sum corrected sources, apply final peak protection, measure again, and report any loudness loss from simultaneous sources or final limiting rather than treating premix measurements as final results.

The algorithm must be evaluated against actual output at each source's mapped dialogue ranges. `target_met` requires isolated corrected speech within ±1 LU of the selected target; also measure non-overlapping corresponding ranges in the final master with ±2 LU tolerance. If final protection causes a miss, flag that source even if its isolated result passed. For overlapping speech, report isolated attribution and an explicitly mixed final measurement, without claiming individually verified final levels. Include before/after source-level results, source coverage, gain/crest/peak flags, speech loudness spread, final programme loudness/true peak, retained sample count and target exceptions. Report overlapping-source measurements as mixed/ambiguous where individual attribution cannot be proved. The denominator includes every audible source instance: accepted speech, uncertain candidate, no detected speech, excluded and unsupported. Unknown/low-confidence sources remain unresolved until reviewed; only reviewed no-speech/excluded sources leave the dialogue eligibility denominator. Unsupported audible semantics stop rendering. A job with missed/unmeasurable quiet clips is not “all normalized.”

Apply continues to add an external root audio master and mute the known original root audio participants, preserving compound contents, video, text and timing. Backups, editor-closed guards, freshness, revision checks and exact Undo remain mandatory. A/B is source-reconstructed audio until editor playback/export is actually verified.

## Delivery scope after user correction

Implement the unified local plugin and same-chat UI, source-aware film/online dialogue processing, and update/install the public package. Do not run a 300-source exercise, repeat whole-film 1027 analysis, or start another approval/review cycle. Retain the existing guarded Apply/Undo code; no actual project mutation is needed to deliver the tool update. Do only packaging/build checks needed to produce a runnable install. Do not claim native playback or listening acceptance that did not occur.

Audio method is delegated to the builder: speech anchoring per source before summation, gentle dynamics to tame protruding syllables, and final peak protection. The meter's yellow area is a useful peak cue, not a substitute for equal perceived speech loudness. Preserve quieter/louder performance within a line and leave separate non-dialogue tracks unchanged before final peak protection.

## Builder-owned choices

Module layout, MCP implementation details, storage migration details, cache sizes, DSP implementation and UI composition are builder decisions within these contracts. Prefer the existing Python/stdlib HTTP stack and local dependencies; avoid a new framework, additional model, cloud upload or unrelated editor features. Host MCP Apps capability checks and safe failures are required, not an excuse to ship an unconnected inbox as the final outcome.

## Builder review dispositions

- The direct native-pipe proposal was rejected after recon, not approved by the user. The recommended MCP App uses the documented host UI bridge; real host integration remains an implementation/release gate.
- Request/response correlation and uncertain delivery are specified above; no conversation scraping or inferred acknowledgment.
- Source and final-mix tolerance and full-source denominator are pinned above.
- Each UI instance belongs to its hosting local chat; no cross-host target selection. macOS is the verified release platform; other hosts must report capability gaps honestly.
- 1027 path is pinned above and available locally; prepare read-only analysis/A/B before editor-close coordination, never make native render claims from file tests.
- No additional cinema preset is required in this release.
