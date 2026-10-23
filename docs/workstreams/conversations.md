# Workstream: conversations, phones and dating apps

Owner request (2026-10-22, `claude_conversation_layers_prompt.md` in the project thread): follow synthetic people with
the continuity of a character drama while the world stays an explicit behavioral simulation. Three connected
experiences (**Listen in**, **Phone**, **Dating apps**), plus **perspectives and aftermath** and a small
**developing stories** view. The engine decides what is communicated, how it is read and what follows; a model may
only vary the wording.

## Audit: what existed (main @ 70ae464)

| Piece | Where | Verdict |
|---|---|---|
| Structured messaging acts (invite, check-in, reply, silence, news, plan change), group chats with membership history, attention, KnowledgeStore | `engine/systems/messaging.py` | **keep + extend**: replies now keep the link to the check-in they answer (`reply_to`, it was computed but the ids were discarded with the decision ids); delayed replies, decline messages, clarifications and support exchanges added |
| Invitations with seen/answer/attendance and decisions | `engine/ledger.py` OccasionBook, `systems/occasions.py` | **keep**: the phone reads invitation rows directly (no duplicate store); a decline's message (explained or brief) is the one new record |
| Silence interpretation (`felt_ignored` / `assumed_busy`), left-out FOMO, `assumed_not_interested` | `messaging.py` | **replaced deliberately**: the reading of a silence and of being left out now comes from evidence (prior replies, a known shift, how often they declined) through the new attribution step, which owns the hurt/belief update (no second effect is applied); `assumed_not_interested` is emitted only when the host actually holds that belief |
| Romantic perception beliefs (`bel_lh`, `bel_hl`), expectations, intentions, coping, memory | `mind.py`, `plans.py`, `coping.py`, `memory.py` | **reuse**: belief about a crush stays on the tie; the new sparse belief store holds only social propositions about a particular person that the tie columns cannot express |
| Encounters (valence, conflict, disclosure, trust) | `systems/encounters.py::apply` | **extend**: an observational capture of in-person conversations (deterministic thinning, no random numbers) and the place where open concerns get raised or avoided |
| App matches converted straight into dates (`romance.app.date_conversion`) | `romance.py::_app` | **replaced** by a bounded app-conversation stage (opener, reply/delay/none, chat, invitation, decline/fade/ghost) feeding the same date queue |
| Scenes, illustrative line banks, narration with a beat checker | `analysis/script.py`, `scenes.py`, `llm/talk/narrate.py`, `web/src/views/valley/Scene.tsx` | **extend**: pair scripts read the exchange ledger (as-of snapshots, not today's tie); the scene player gains Listen in (live append) and a perspective switch |
| Chats tool | `web/src/bench/tools/Chats.tsx` | **keep**; the new Phone tool is the person-centred view |

## Keep / extend / add

**Add (engine)** — `engine/social.py`:
* `ExchangeLog` (one typed table for in-person, text, group-chat and app exchanges): id, day, block, seq, channel,
  thread (group chat id, app thread id or −1 for a DM), pair key, occasion/place, speaker, to (−1 = the whole
  thread), act (finite vocabulary below), topic kind + topic ref, reply_to, decision, event, intent, withheld,
  ambiguity, tone, and an as-of snapshot (closeness, hurt, trust, both moods) — float16, a few bytes each.
* `ReadLog` — each participant's interpretation of an exchange: reader, read (support, rejection, busy, not
  interested, excluded, obligation, warm, ambiguous, unknown), confidence, what they expected, belief formed.
* `BeliefStore` — sparse, bounded (≤ 6 per owner) beliefs about a particular person: owner, about, proposition
  (`not_interested`, `excluded_me`, `ignoring_me`, `busy`, `cares`, and the one second-order
  `thinks_im_not_interested`), confidence, formed/updated day, evidence exchange, revised-by exchange.
* `ConcernLedger` — open situations (unanswered text, left out, misunderstood declines, unmet support, promise of a
  next time, boundary): owner, other, kind, subject ref, evidence, importance, opened, deadline, status (open,
  clarified, repaired, fulfilled, abandoned, worsened), resolution exchange.

**Acts** (`social.ACTS`): small_talk, coordinate, invite, accept, decline_explained, decline_brief, checkin, reply,
late_reply, no_reply (a *record of absence*, never shown as a message the silent person sent), disclose, deflect,
support, ask_clarify, clarify, reassure, apologize, withdraw, flirt, opener, app_reply, app_chat, ask_date,
date_yes, date_no, fade, warm_moment, tension, introduce, boundary.

**Mechanisms (each a decision kind with factors, params in `config/mechanisms/21_social.yaml`):**
1. *Declining an invitation*: explain (with the real reason when a shift/class/clash decided it) or decline briefly
   (`decline_message`). The host reads each decline (`read_decline`): an explained clash → busy; a brief decline
   reads as not interested with a chance rising with how many times this person declined lately and with the
   host's rejection sensitivity, falling with closeness. A not-interested belief lowers that person's invitation
   score in `occasions._invite` (a factor, recorded) — fewer invitations follow.
2. *Being left out*: the attribution uses evidence — someone who declined the host several times lately reads it as
   "they think I'm not interested" (second-order belief); otherwise "excluded me", weighted by rejection
   sensitivity. The left-out person may then choose among clarify (text the host), withdraw, or let it go
   (`left_out_response`); a clarification revises the host's belief and resolves the concern.
3. *Unanswered texts*: reading the silence uses evidence (they know the friend works then; this friend usually
   answers) → busy / ignoring me / not sure. An "ignoring me" read opens a concern; the friend may reply late
   (`late_reply`, with an apology when close), which revises the belief and resolves it; the next contact choice
   for an owner of an open concern weighs check in again, ask what's up, or withdraw (`concern_next`).
4. *Support*: a struggling friend who gets a check-in discloses or deflects (`disclose_struggle`: closeness,
   trust, how private the struggle is, not wanting to burden); a disclosure adds a *confided* knowledge row (not
   passed on as gossip) and the friend's support raises perceived support a little (the existing coping
   `supported` channel, not a second effect).
5. *Raising a concern in person*: when the two people of an open concern talk (encounters), the owner raises it
   or avoids it (`raise_concern`); raising leads to repair or (rarely) to a worse read; avoiding keeps it open.
6. *Dating apps*: matched → opener (who, whether) → reply now / late / never → chat → ask → yes (the existing date
   queue, one date per pair) / explicit no / fade / ghost. All draws are `Streams.keyed_uniform` per pair and stage.

**Add (presentation)** — `analysis/dialogue.py` (content plans and the deterministic fallback, with a stable
communication *style* per person: brevity, warmth, emoji, lowercase, formality — presentation only, labelled style,
never a psychological trait), `analysis/phone.py` (inbox, DM threads normalized by pair, group threads with the
audience at message time, date windows, gap notes), `analysis/stories.py` (developing stories), `llm/talk/dialogue.py`
(model realization with a semantic checker and a cache shared by every view), API `routes_phone.py`, workbench tool
`Phone`, scene player Listen in + perspectives, valley "Developing" tab.

## Retention and scale
* In-person capture records every consequential exchange (a conflict, a raised concern, a disclosure, a
  clarification) and a deterministic hash-thinned sample of ordinary talk among people who know each other:
  `social.capture.ordinary_every` = 6 (one pair-block in six; couples and first meetings at get-togethers one in
  three). Volume grows with people, not with pairs. No random numbers are drawn; nothing in behavior reads the
  exchange log, so the sample size can change without changing any life.
* Ordinary talk older than 14 days thins away (Listen in is about now); consequential exchanges, app messages,
  readings, closed concerns and revised beliefs stay for `sim.detail_days` (120). Beliefs fade (half-life 35 days)
  and are capped at 6 per person.
* Viewing, generating wording or cancelling never touches a world (tested: a world watched every day ends identical
  to one never watched).

## Model wording (llm/talk/dialogue.py)
* A view's planned lines (who, to whom, act, licensed facts) are fixed by the records; the model only words them.
  `DialogueChecker` judges meaning per line: polarity, reasons kept back, names, numbers, days and times, and no
  invitation, promise, accusation, relationship, secret, condition or psychologizing the plan doesn't license. One
  repair round; lines that still fail keep the structured wording.
* Cache key: (world lineage, content hash of the planned lines, schema). Lineage is a uuid set when a world is built
  and kept by forks and undo; a branch whose lines differ gets a different content hash. 600 entries, LRU.
* Queue: one worker, a bounded priority heap (24), deduplicated by key, cancellable; the plan is built under the
  world lock, the model runs without it. Routing: Settings → Models → "Words of texts and conversations" (a model on
  this computer is recommended; Off keeps the plain wording).

## Engine adoption decisions (research list)
| Candidate | Decision | Why |
|---|---|---|
| PsychSim | **defer** | the needed theory of mind is one level deep and per-dyad; native NumPy beliefs are simpler and run for 60k people. A bounded comparison stays possible later on the same fixtures. |
| Ensemble / Comme il Faut | **adapt (design only)** | the act vocabulary with conditions/effects follows its social-action idea; no JS engine in the loop. |
| Versu / Praxish | **adapt (design only)** | roles (host, roommate, partner, match) condition which acts are available. |
| Talk of the Town | **adapt (design only)** | beliefs carry evidence, source and revision; confidences are not gossip. |
| FAtiMA / GAMA BEN | **defer** | the existing appraisal (sim.appraise) and coping cover the needed concepts. |
| Winnow | **adapt** | developing-stories patterns are incremental, partial-match sifting over the ledgers, read-only. |
| SALib | **adopt, opt-in** | `scripts/sensitivity.py` (Morris screening of a few social parameters, replicated seeds) when SALib is installed; not a dependency of the app. |
| pyABC, Concordia, AgentSociety, AgentTorch, FLAME GPU, Neighborly | **defer** | no informative data or measured need yet. |

## Acceptance (from the request) and where each is tested
All in `tests/test_conversations.py` (fake model only): 1 observation invariance, 2 historical integrity, 3 both
phones and group audiences, 4 cache across undo/fork/new worlds, 5 differentiation, 6 checker cases, bad model
output and the queue, 7 ordinary and positive life, 8 live append, 9 dating integrity, 11 belief revision, 12
promises, 13 developing stories, 14 ablations (no explained declines, no clarifying), plus the API end to end. 10
(scale) is the speed budget (`tests/test_speed_budget.py`) and the measurements in the HANDOFF session log.
