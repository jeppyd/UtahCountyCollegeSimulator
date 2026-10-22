# Design review and rebuild (2026-10-22)

The owner asked for a full evaluation of the simulator as a game: what makes it good, what is noise, what should be
cleaned up, with freedom to rebuild. His answers to the opening questions set the frame:

* It is a **sandbox and a game**, for him alone. Realism is there for fun and richness, not research.
* The heart: watch a miniature Utah County live their lives, follow along, make changes and see how they play out,
  with **cause and effect** visible from one life to the whole valley.
* He hasn't used much of it: "it's not clear where to go." He keeps trying to perfect it before engaging.
* The moment he wants: making changes and watching things shift, in parallel worlds **and** directly in his own
  world ("just choosing what people do"). Following people, ideally down to watching a text conversation, a group
  date, roommates getting caught.

## The verdict

The engine is excellent and unusually honest: every event has a mechanism and a parent, every choice keeps its
reasons as shares of the push, occasions have real invitations, travel and lateness, and the world runs on real BYU
and UVU schedules, a real calendar and real housing. That is rare and worth protecting.

The experience around it was built in layers that never got a spine. The game shell of iterations 4–5 (World,
People, Relationships, Places, Events, Explore), the research desk, the iteration 6 workbench and the What-if all
coexist, and none of them is a place to *start*. The app opened on an empty bench. The best material (a person's
page, the reasons behind a moment, the scene of a dinner) sat two or three clicks deep, behind tools you first had to
know about. "Trying to perfect it before engaging" is the classic symptom of a sandbox without a core loop: there is
always more to build because there is nothing pulling you into play.

The fix is not more features. It is a loop, and a home that runs it:

> **Follow a few lives → let time run → see what happened to them, and why → watch the scene → make something
> happen → let time run again.**

## What contributes to a good experience (keep, and put up front)

| Strength | Why it matters for play |
|---|---|
| Recorded reasons ("because outgoing 61%, a social apartment 30%") | This is the magic: the world explains itself. It was shown in tools; now every moment in the story carries it. |
| Occasions as real plans (invitations by channel, seen/not seen, answers with reasons, rides, lateness, who met whom) | This is where stories live. It was only visible as a table in the Occasion tool. It is now a scene you can watch. |
| The person page | The best page in the app. Kept as "Their life". |
| Real Provo grounding (class schedules, buildings, calendar, weather, housing) | Gives texture: a date at the Creamery, a dinner in Heritage Halls, a game night after a devotional. |
| The What-if with common random numbers | Genuinely clever. Kept, and now joined by acting in your own world. |
| The living map | Beautiful when it shows someone you care about. It now follows whoever you focus. |

## What is not working

### 1. Three interfaces, no home
Counted at the start of this review: **20 pages** (17 under "Classic views" plus the workbench, the What-if and the
guide), **27 workbench tools**, the What-if's 4 tabs, and settings. Many show the same thing twice:

| Same thing | Shown by |
|---|---|
| The map | the Map tool (3D), the "Flat map (backup)" page, the World page's hero map |
| A list of people | the People page, the People tool, search |
| Events | the Events page, the Events tool, the World page's headlines |
| A field over time | the Explore page, Vital signs, the Measure tool, the Scales tool |
| A life as sentences | the person page's Story tab, the Story tool, the Life tool |
| What caused what | Trace, Ripple, Why and Chains (four readers of the same ledger) |
| Asking in words | the What-if's "Describe it", the Ask tool |
| Diagnostics | Logs and Speed sat on the player's shelf next to Map and Trace |

### 2. A blank canvas as the first screen
The empty bench was a principled answer to "no pre-built dashboards", but an empty canvas is the hardest possible
start for a sandbox. Good sandboxes (The Sims, Dwarf Fortress, Crusader Kings) open on *someone*: a character or a
place with something already going on, and the tools appear when you need them.

### 3. Agency only through a copy of the world
Every change went into a What-if. Splitting worlds is a great experiment, but it is not how you *play*: in a sandbox
you want to make Lydia throw a dinner tonight and see who comes, in your world.

### 4. Stories without scenes
The data for "watch a group date" already existed (who was invited and how, who said what and why, who arrived when
and how, who is drawn to whom, who was introduced, what happened after), but it was only ever rendered as rows.

### 5. Noise
From a 180-day run at 10% scale (7,341 people, 369,541 events), per person per year: plans formed 16.6, dates 11.8,
asking out 9.2, hosting a get-together 7.6, new friends 5.5. Raw lists drown in these. Specific problems:

* **Bookkeeping events in the story**: a new term (8,354), added to / left / muted a group chat (16,846), a renewed
  temple recommend, "assumed busy", low turnout, hosting strain.
* **Two-sided duplicates**: the World page's headlines showed "Sarah was broken up with by Brigham" *and* "Brigham
  broke up with Sarah" (the de-duplication only matched identical event types).
* **`went_home` and `time_with_family` are the same rows every time** (11,757 each, identical people and days).
* **Repeats**: one person hosted 62 get-togethers in 180 days; dealbreaker found → overlooked → found again with the
  same partner (35 of 272 pairs).

## Simulation findings worth fixing in the engine (not changed in this round)

1. **Sunday batching.** Most life-changing systems tick weekly on Sunday night (`sim._end_of_day`, `wd == 6`):
   679 of 683 depressive episodes start on a Sunday, every faith crisis and every dealbreaker too. In a story it reads
   as "everyone's depression lifted on Sunday." Fix: run each weekly system on a rotating seventh of the population
   every day (same weekly rate, spread across the week). Needs a recalibration pass, so it's a separate piece of work.
2. **Synchronized shocks.** 1,036 of 7,341 people "started coping with a hard time" on the same day (day 135, the
   start of Winter semester) and 818 on day 1. Real stress builds; consider spreading onset by personal threshold.
3. **Depression flicker.** The median episode is 35 days, but 10% last exactly one weekly tick (7 days) and some
   people start and end seven episodes in six months. Add a minimum duration or hysteresis.
4. **Said no, came anyway.** Roommates who decline a party in their own apartment are counted as attending (they are
   home). The scene now says so honestly ("said no, but it's their place too"), but turnout numbers include them.
5. **Long walks, on time.** Someone walked 62 minutes to a party and arrived on time.
6. **Placeholder names leak** into the story: "works at BYU campus dept 93".
7. **Provenance gaps** show up as "no recorded push" in the story: a bishop meeting to repent, illness, NCMO (also
   listed in HANDOFF.md).

## What I built

All on branch `claude/project-thread-q87n1i`. Nothing was deleted; every earlier page is under **More**.

### The valley (new home)
`web/src/views/valley/Valley.tsx`, `ucsim/analysis/valley.py`, `ucsim/api/routes_valley.py`

* **Your people** (left): the lives you follow, each with what they're doing right now, happy / lonely / stressed,
  their latest moment, and **their plans**: "today 8:30 pm · Jacob's party · said yes", "yesterday 3 pm · Date with
  Dallin ▶ watch". With fewer than three followed, **lives worth following**: one person per kind of life (a freshman
  in the dorms, just home from a mission, newly engaged, married students, a UVU student living at home, from far
  away, not a Latter-day Saint in Provo, quietly struggling, questioning their faith), each with a one-line hook.
* **The map** (middle): the existing living map, unchanged, following whoever you focus. A focus card shows the
  person with **Make it happen**, **Texts with** their partner, **Their life**, **Follow**.
* **The story** (right): what happened to your people (or, on the other tab, the biggest moments in the valley),
  grouped by day, curated: bookkeeping left out, both sides of a moment shown once, the two halves of a breakup as one,
  repeats folded ("hosted a get-together ×3"), a few of each kind valley-wide. Every moment carries its reasons.
  *Why, and what it led to* opens the full push and the ripple inline; *watch the scene* plays it; *their story* plays
  the two people's history.

### Scenes you can watch
`web/src/views/valley/Scene.tsx`, `ucsim/analysis/script.py`

A get-together, a date, or two people's history, played beat by beat like a phone screen and a stage: the host
deciding to have people over (with why), invitations as texts or asked in person, answers as bubbles (with the reason
under each: "tired 26%, reserved 10%"), "sees it and doesn't answer", arrivals with how they got there and how late,
the two old friends who end up in the corner, the one who keeps glancing at someone who doesn't notice, the person
who knows no one and hangs back, introductions, tension, the events that followed, and the wind-down. Dates read
differently: who worked up the nerve to ask, whether the conversation is easy or full of pauses. Two people's history
shows how they met, every occasion they were both at (each one watchable), check-ins and silences and how they were
read, asking out, first dates, engagements and breakups.

**What happens is always recorded; the words people say are illustrative** (fixed lines chosen by a hash of the
moment, so the same scene always reads the same). Every beat names the record it comes from.

### Make it happen, in your own world
`web/src/views/valley/MakeItHappen.tsx`, `ucsim/api/routes_act.py`, `ucsim/engine/systems/social_actions.py`

Focus anyone and choose: throw a get-together, start a weekly tradition, get in touch with someone, meet someone new,
or **fall for someone** (new `spark` action: the world editor raises one person's attraction to someone they know;
the model's own crushes, asking out and answers take it from there). It happens **in your world** by default
(`/api/act` with `"world": "original"`), or in a What-if if you'd rather compare. Check shows who is free and who is
busy before you commit. Tested end to end: Lydia threw a Thursday dinner for her friends, nine were free, one came,
plus an uninvited friend; the scene plays it.

### Navigation
**Valley · Workbench · What-if · More ▾ · How it works.** The old "World" page is now "Overview" under More. Logs and
Speed moved to an "Under the hood" group at the bottom of the shelf. The guide has a new first section.

## Proposed removals (not done; for the owner to decide)

Reversible plan: delete in one PR so it can be reverted in one click.

* "Flat map (backup)" page (the Map tool replaces it; keep its months replay as a Map tool mode first).
* The People page (search and the cast cover it).
* The Story tool (the person page's Story tab and the valley's story cover it).
* Ripple and Why as separate tools (both open inline on any moment; Trace keeps the full graph).
* The World/Overview page's hero map and headlines (the valley has both).

## Next steps, ranked by fun per hour

1. **Narrate a scene with your Claude login**: send the scene's beats (the fact sheet) and get prose with inner
   thoughts and real dialogue, checked against the beats the way Interview's answers are. This is the "watch a text
   conversation play out" vision.
2. **Live scenes**: while time runs, "Lydia's dinner is starting — watch live", beats revealed as the clock passes.
3. **More verbs**: ask someone out now, break up, move apartments, go home for the weekend, quit a job, a snowstorm
   tonight, a ward activity.
4. **Stagger the weekly systems** (finding 1), then the other engine findings.
5. **Remove the duplicates** listed above.
6. **A checkpoint before you meddle**: acting in your own world has no undo (the owner said no savable worlds; a
   single in-memory checkpoint would be enough).

## Round 2 (same day): the recommendations, done

The owner approved the rest. On branch `claude/project-thread-q87n1i`, in separate commits:

* **Removals** (one commit, revert it to bring everything back): the Story, Ripple and Why workbench tools; the People
  page from the live app's menus (the read-only snapshot keeps it; Cross-tabs' "show these people" opens the People
  tool); the Overview's hero map and headlines (the snapshot keeps them). **Not removed:** the flat map, renamed
  "Neighborhood map": it is the only home for complexes and wards colored by a measure and for the day and months
  replays, and several pages link to it.
* **Story noise:** `went_home` carries the time-with-family effects and `time_with_family` is gone; work groups have
  names ("the Creamery", "a dental office") instead of "BYU campus dept 93"; NCMO records its decision, ghosting points
  at the date, homesickness at the trip (salient events with a recorded reason: 94% → 99%); the valley says "life
  happens" for things that happen to people.
* **Engine:** depression, faith crises and each couple's week (engagement, breakups, dealbreakers) run on each
  person's or couple's own weekday (`sim.my_turn`), same weekly rate; a depressive episode lasts at least two weeks;
  starting to cope is a daily chance once strain crosses the line (no 1,000-person mornings); housemates who said no
  don't count toward a party's turnout. The 62-minute walk was not a bug: they left an hour early.
* **Play:** ask someone out, end it, go home (Make it happen); **Undo** your last change in your own world;
  **watch live** for today's get-togethers; **Tell it as a story** (your Claude login writes the scene as prose,
  checked against the beats).

Still open: world events as verbs (a snowstorm tonight, a ward activity), the Sunday-night systems that remain
weekly (network, culture, norms, honor, plans, academics), and a recalibration pass after the stagger.
