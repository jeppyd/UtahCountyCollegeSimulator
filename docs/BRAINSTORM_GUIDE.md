# Brainstorming guide: the building blocks of the world

A quick reference for dreaming up new things to add. It names every kind of building block in the simulation,
says in plain words what each does and how they connect, and ends with a template for writing an idea down so an
agent can build it. You never need to know the file formats — describe the idea, and the agent turns it into config
and code. (File paths are listed for the curious.)

## How a simulated day works

Every simulated person lives the same loop, one day at a time, in four blocks (morning, afternoon, evening, late
evening):

1. **Who they are** (traits, values, history) and **how they feel right now** (states like mood, stress,
   loneliness) push on **choices**: go to class, study, the gym, eat out, drop by a friend's place, ask someone out.
2. Choices put people in **places** with other people. Being in the same place makes **encounters**, and
   encounters build **relationships** (strangers → acquaintances → friends → close friends; talking → dating →
   engaged → married).
3. Things that happen are logged as **events** ("went on a first date", "was ghosted", "met with their bishop").
   Each event nudges feelings for a while (a bad date: self-esteem down a bit for a week), more or less depending on
   who it happened to.
4. Slower **rules** (mechanisms) run daily or weekly: faith shifts, burnout builds up, couples get engaged or break
   up, people move apartments.
5. **The calendar and the world** (semesters, finals, holidays, weather, rent, policies) sit around all of it.

Everything is random, but repeatable: the same seed gives the same world, and a What-if world shares every coin
flip with the original, so differences come from your change, not luck.

---

## The building blocks

### 1. People's variables (what a person *is* and *feels*) — about 200
`ucsim/config/variables/*.yaml` · browse them in the app's Variables view and `docs/VARIABLE_CATALOG.md`

Each variable has a **kind** that says how it behaves:

| Kind | What it is | Changes? | Examples |
|---|---|---|---|
| **attribute** | Facts about a person | Rarely (birthdays, graduation) | age, sex, school, major, home town |
| **trait** | Personality | Never (in the timespan simulated) | Big Five (extraversion, neuroticism…), attractiveness |
| **value / belief** | What they hold true or good | Slowly | faith_belief, chastity_commitment, orthodoxy, moral_autonomy |
| **preference** | What they like | Rarely | ideal age gap, favourite date types, ideal months before engagement |
| **habit** | Regular behaviour, with momentum | Slowly, by repetition | workouts a week, scripture minutes, eating out, church attendance |
| **state** (feelings) | How they feel now | Daily; drifts back to their baseline | mood, stress, loneliness, guilt, belonging, fatigue, romantic longing |
| **history / counter** | What has happened to them | Only goes up | number of dates, NCMOs, breakups, bishop meetings |
| **derived** | Calculated from others | Recomputed | number of friends, GPA |
| **structural** | Where they sit in the world | When they move/join | apartment, ward, employer, club, partner |

*Brainstorm with:* a new feeling ("FOMO"), a new trait ("competitiveness"), a new habit ("thrifting"), a new fact
("has a car"). Say where it comes from at the start (survey question? a guess by sex/age?), what moves it, and what
it should change.

### 2. Relationship variables (what's between two people)
`ucsim/config/variables/20_edges.yaml`

Every pair who have met has a tie with: stage (acquaintance → close friend), hours spent together, closeness,
attraction each way, chemistry, conflict, how they met (class, ward, app, party…), and flags (kissed, NCMO,
app match, roommates…).

*Brainstorm with:* a new kind of tie (study partner, ex), something that builds or erodes ties (inside jokes,
borrowed money never repaid).

### 3. Events (things that happen) — about 120 kinds
`ucsim/config/events.yaml`, `ucsim/config/events/*.yaml`

An event is a logged moment with a person (and often a second person), a time, a place and a cause. Each kind has a
plain-language story line ("{a} was ghosted by {b}"), a **salience** (how memorable, 0–1) and **effects** on
feelings: how big, how long it lasts (half-life in days), and **moderators** — who it hits harder (a rejection
stings more for someone high in rejection sensitivity).

*Brainstorm with:* "getting stood up", "a roommate fight over dishes", "a great conversation at the institute".
Say who it happens to, how often, what triggers it, and how it feels (and for whom more strongly).

### 4. Rules / mechanisms (how things change over time) — about 210
`ucsim/config/mechanisms/*.yaml` · shown in the app with their formulas and sources

A mechanism is a rule with dials (**parameters**) that a What-if can turn. "Each week a dating couple gets
engaged with a chance that rises with commitment, both being active members, and how long they've dated compared
with what they consider ideal." Each is tagged with its evidence: *empirical* (from a survey or study),
*calibrated* (tuned to match real numbers), or *hypothetical* (a reasoned guess).

*Brainstorm with:* "stress makes people skip the gym", "a good roommate relationship makes people less likely to
move". Say what pushes it up, what pushes it down, and roughly how often it happens.

### 5. Decisions (choices a person makes, with reasons) — about 55 kinds
`ucsim/config/decisions/*.yaml`

The important choices (ask someone out, say yes, break up, go to a party, stop going to church, move out) are
recorded with every factor that pushed them and by how much ("attraction +1.2, low confidence −0.6, it's
Monday ×1.2"). This is what lets you click any event and see *why*.

*Brainstorm with:* a new choice ("switch majors", "go home for the weekend") and the reasons that would feed it.

### 6. Occasions (planned get-togethers)
`ucsim/config/occasions/*.yaml`

Someone hosts or organizes something — a dinner, game night, party, study group, ward activity, service project, club social, dance, football game, devotional, Friendsgiving —
invites people, and those who come meet each other there. Each kind has how many get invited, how long people talk,
cost, latest start, and whether make-outs can happen there.

*Brainstorm with:* "ward break-the-fast", "a ski trip", "FHE groups". Say who hosts, who comes,
when, and what it leads to.

### 7. Places
Apartment complexes (with real names, contracted-housing status and real wards from the 2026–27 listings), wards
and meetinghouses, campuses, venues (restaurants, soda shops, gyms, trails), employers, clubs and teams.

*Brainstorm with:* a new place type ("the climbing gym"), a specific place ("Y Mountain"), or a property of places
("complexes with a pool are more social").

### 8. The calendar
`ucsim/config/calendar/*.yaml`

The real 2026–27 BYU and UVU calendars (terms, finals, breaks, holidays), General Conference, devotionals, and
real Provo weather by day. Calendar items can change behaviour (finals: more stress, less dating).

*Brainstorm with:* a date that matters ("Homecoming week", "Valentine's", "mission call season").

### 9. World switches and What-if presets
`ucsim/config/variables/30_places_world.yaml` (switches) · `ucsim/config/interventions.yaml` (presets)

Big dials for the whole world: rent level, tuition, how attractive dating apps are, marriage norm, whether the
Honor Code is enforced, whether coffee is permitted. A preset packages one or more switches into a What-if
("Rent +20%", "Coffee allowed"), with start date and ramp.

*Brainstorm with:* "what if BYU dropped the endorsement requirement", "what if a new apartment complex opened".

### 10. Policies
`ucsim/config/policies/campus.yaml` · the app's Policies page

Real BYU and UVU rules (Honor Code, housing, endorsement, conduct codes) with sources, and whether each one is
*modelled* (changes behaviour), *data* (shown only), or *not binding* (true, but never matters in the model).

### 11. Institutions
Counseling centers (with real capacity and waitlists), bishops (always available; follow-ups after confessions),
clubs with officers who adapt when turnout is low, employers with shift flexibility.

### 12. Survey-drawn starting values
`ucsim/priors/survey_priors.json` (aggregates only, never individual answers)

Many variables start from your surveys (dating, culture and lifestyle, LDS sexuality): each simulated person's
answers are drawn so that the mix matches the survey, by sex, school and church activity, with the right
correlations between questions. A new survey question can become a new variable this way.

---

## Writing an idea down

Copy this and fill in what you know; leave the rest blank — the agent will propose numbers and say which are
guesses.

```
Idea: (one line)
Kind: feeling / trait / habit / event / rule / decision / occasion / place / calendar item / world switch / policy
Who it applies to: (everyone, BYU students, active members, men 18–25, married couples…)
What causes it / how often:
What it changes (and for whom more strongly):
How it shows up in the app: (an event in someone's story, a chart line, a map colour…)
Evidence: (survey question, article, "from experience", or "a guess")
```

**Example.** *Idea:* Sunday "break the fast" dinners after Fast Sunday. *Kind:* occasion. *Who:* YSA ward
members. *Causes:* first Sunday of each month, hosted by a ward member, invites 8. *Changes:* belonging up a little,
new acquaintances in the ward, slightly more dating within the ward. *Shows up:* "Joan went to a break-the-fast
dinner at Emma's" in stories. *Evidence:* from experience.

## Ideas that fit the world well
- Things people already do but the model treats as one lump (e.g. different kinds of hanging out).
- Moments that change feelings: small wins and embarrassments, roommate friction, family calls from home.
- Turning points: mission calls, switching majors, leaving or returning to church, moving home.
- Real local places and dates (Y Mountain hikes, Rooftop concerts, Homecoming).
- Survey questions not yet used — ask an agent for the list.
