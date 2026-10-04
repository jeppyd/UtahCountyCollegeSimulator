# The inner life: a bridge between state and behavior

Iteration 5 adds a cognitive and social layer between who people are and what they do. Before it, most of
the engine could be summarized as

```text
traits + current state + context + probability → action
```

Each behavioral subsystem turned state straight into action through its own coefficients. That made the model
explainable but shallow: people were omniscient (asks used the other person's true attraction, norms were true
means), nothing they lived through changed what they expected next time, concerns never competed, hard times
had direct scripted consequences, and nobody tried to do anything. The layer below keeps everything explicit,
vectorized and registered with evidence labels, and routes behavior through the steps people actually go
through:

```text
traits / values / identity / habits             cares_* (how much each concern matters)         mind.py
        ↓
objective world  ─►  perceived world             perceived support, friends' belief,             mind.py
        ↓                                         believed romantic interest (per tie)
memory and learned experience                    episodic memory; expectations; confidence        memory.py, mind.py
        ↓
needs / priorities                               drives = cares × unmet; the top priority         mind.py
        ↓
plans / commitments / routines                   weekly intentions; slot routines                 plans.py, routine.py
        ↓
bounded choice → action                          activity choice, asks, contact, study, church…   existing systems
        ↓
outcome → appraisal → emotion → coping           relevance × coping potential; coping episodes    sim.appraise, coping.py
        ↓
learning                                         expectations, coping values, routines, memory    all of the above
```

It does not use a language model. Every quantity is a column in the person table or edge store, every rule is
a registered mechanism with parameters, ranges and an evidence label, and every change that matters is an event
with a cause.

## What each piece is, and why it is there

| Piece | What it does | Replaces / adds | Evidence |
|---|---|---|---|
| **Motives** (`cares_*`, 8 concerns) | How much friendship, partnership, school/career, money, faith, rest, fun and fitness matter to someone, from traits, values and circumstances; drifts weekly toward its target, so priorities change when identity or life stage does | A shared currency instead of hundreds of disconnected arrows | structural (SDT, fundamental motives) |
| **Drives** (`drive_*`, `top_priority`) | importance × how unmet the concern feels (felt states, or recent experience for fun and fitness) | Behavior reads drives: free time, dating motivation (with competing drives), reaching out | structural |
| **Expectations** | `expect_accept` (a yes when asking), `expect_social` (warmth of people), learned by prediction error from one's own outcomes; rejection-sensitive and socially anxious people learn more from bad outcomes | Replaces "recent rejections × rejection sensitivity → fewer asks" and the fixed loneliness → withdrawal split | literature (Rescorla–Wagner; Downey & Feldman; Cacioppo & Hawkley) |
| **Academic confidence** | `self_eff_academic` updated by class rank of term grades; raises study effort, lowers dropout; affects GPA only through effort | New mediator between grades and persistence | literature (Bandura; Multon et al. 1991) |
| **Perceived support** | Built from actual close, warm ties through a personal lens and trait biases (r ≈ .4–.6 with actual) | Loneliness and stress read the perceived figure (stress buffering is an interaction) | literature (Haber et al. 2007; Cohen & Wills 1985) |
| **Pluralistic ignorance** | Members who doubt present more belief than they hold; close friends who have confided see each other's real belief; faith influence reads the perceived figure | Faith influence no longer sees true beliefs | literature (Prentice & Miller 1993; Miller & McFarland 1987) |
| **Believed romantic interest** (`bel_*` per tie) | Each interaction is a noisy read of the other's real attraction, mixed with projection of one's own feelings, a liking gap with strangers and men's over-reading of women's interest; asks, dates and kisses reveal much more | Asks depend on believed interest, so crushes can be unrequited and connections missed | literature (Boothby et al. 2018; Haselton & Buss 2000; Lemay et al. 2007) |
| **Episodic memory** | Salient events become memory rows (who, how it felt, how important — scaled by appraisal relevance); power-law forgetting, rehearsal, a per-person cap, core memories kept; retrieval by recency × importance × relevance | Continuity without text: rumination re-lives negative memories; memory tone feeds life satisfaction; lessons cite memories | literature (Wixted & Ebbesen 1991; Generative Agents' retrieval idea) |
| **Appraisal** | Each event's emotional effects scale with how much the person cares about the concern it touches; harmful effects grow when coping potential (perceived support, self-esteem, low stress) is low | The same rejection hurts more for someone desperate for a partner and alone | literature (Lazarus & Folkman 1984; Scherer 2001) |
| **Coping** | Persistent strain starts an episode; strategy from traits, availability and what has worked before (support, active, religious, distraction, withdrawal); strategies change behavior and bring relief only if what they rely on is there; outcomes are learned | `event → appraisal → emotion → coping need → repertoire → behavior → outcome → learning` instead of `breakup → behavior X` | literature for the families and outcome ordering; hypothetical magnitudes |
| **Intentions** | Weekly, from drives and situation: ask someone out, reconnect, meet people, study more, find work, return to church; follow-through by conscientiousness and self-control; a ledger records target, motive and how it ended (kept / abandoned — target gone or priorities changed / lapsed) | "What they were trying to do" and "why their plans changed" are real records | literature (BDI; Sheeran 2002) |
| **Routines** | Per weekly slot, the habitual free-time option and its habit strength (asymptotic learning) adds to that option's utility | Week-to-week continuity of daily life (MATSim-style plan memory) | literature (Lally et al. 2010; Wood & Neal 2007) |
| **Relationship histories** | Ties carry shared experiences, confiding, support exchanged and unrepaired hurt (conflict, betrayal, breakups) that heals with warm contact; friends bring friends (triadic closure) | Closeness is built from history; hurt makes plans fall through and raises breakup risk | literature (Laurenceau et al. 1998; Gottman; Kossinets & Watts) |
| **Place cultures** | Apartments, complexes and wards develop sociability, observance and warmth with inertia; cultures feed hosting, invitation acceptance, perceived norms, who moves in and how fast newcomers belong | The micro → meso → macro → micro loop | structural / hypothetical strengths (Schneider 1987 ASA) |

## How a hard stretch now unfolds (traced from a run)

From one person's page in a test run (scale 0.04, seed 1, fall semester): an early-returned missionary whose
strongest concern is faith becomes sexually active with his girlfriend in late September. The event raises guilt
(a registered effect, scaled by how much he cares about faith — appraisal relevance), and his faith drive —
importance × the gap between his convictions and his practice — becomes his top priority. Within days his strain
passes his tolerance and a coping episode starts; the episode's recorded cause is that event. With friends
available he copes by reaching out, which raises his contact with close friends, deepens their disclosure and
logs support on those ties; relief depends on whether those friends are warm. A week later he meets with his
bishop (the confession pathway), and four days after that she breaks up with him. Both events are core memories;
his tendency to ruminate re-lives them (8× and 4×), which keeps a negative mood term alive. Over these weeks he
comes to expect less support (0.76 → 0.64) and slightly more warmth from people at gatherings (0.67 → 0.76), and
he still believes he has more support than he does (0.68 vs 0.53). All of it is on his page (Inner life tab), and
every step links to the event and rule that produced it.

## Between-person and within-person

Each new quantity has a slow, between-person part (how much someone cares; their trait-based starting
expectations; their personal lens on support; their tendency to ruminate) and a fast, within-person part (how
fulfilled each concern feels; learned expectations; current coping; current intention). The validation report's
longitudinal section estimates within-person cross-lagged effects separately from between-person correlations
on the simulated panel (`analysis/panel.py`), so the model is ready to be confronted with real multi-wave data.

## Performance

At ~10k agents the full engine runs ≈ 0.23 s per simulated day (from 0.18 s before this layer). Per-agent
memory is capped (≈ 23 bytes per memory row, at most 40 per person), routines are two n × 21 arrays, intentions
live in a pruned ledger. Edge inserts were rewritten as an O(n) merge.

## What is deliberately not here

No language model decides anything. Motives, strategies and intentions are a small fixed vocabulary rather than
free text. Gossip and reputation between individuals, jealousy and social media as a second network remain out
of scope until they can be modeled credibly. The strengths of most new mechanisms are hypothetical and carry
ranges; uncertainty ensembles (`scripts/uncertainty.py`, the Experiments page) draw them, together with an
alternative mechanism form for faith influence, so a conclusion that depends on them says so.
