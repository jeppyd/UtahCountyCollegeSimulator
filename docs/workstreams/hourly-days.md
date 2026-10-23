# Workstream: Hour-by-hour days

> Status and where the code is: docs/HANDOFF.md. Shared rules: docs/workstreams/README.md. Contract: docs/EVOLUTION.md.

The owner asked (2026-10-23) for days that are decided hour by hour, with as much realism as the variables allow and
no rigid slots: only scheduled things keep their times (classes, shifts, church, devotionals, games, dances, planned
dinners and dates); everything else, sleep included, can happen at any hour, just more or less likely. People who
follow rules can still break them in the moment (the owner's example: staying past visiting hours on a night when
sex drive or the moment wins). Slower runs are fine; quality first.

## The day

- `engine/clock.py`: 24 hourly steps from 6 am to 6 am (`N_BLOCKS = 24`, `SLOTS_PER_WEEK = 168`). Minutes past 1440
  are the small hours of the same simulated day (1 am Friday night = minute 1500 of Friday); `day_minute` maps clock
  times onto the day. `block_mask` is the vectorized `main_blocks` (a bit per hour).
- Records (events, decisions, messages, conversations) carry the **part of the day** (`clock.PARTS`: morning 6–12,
  afternoon 12–5, evening 5–8, late evening 8–midnight, night midnight–6), not the hour. `PART_HOUR` gives a
  representative hour for words.
- `LEGACY_SHARE` keeps encounter calibration: ambient time is a fifth of an old block per daytime hour and a sixth
  per hour from 5:30 pm, so an old-style day adds up to the contact the rates were fitted to; the new hours (early
  mornings, after midnight) add contact only for people who are awake and together.
- `Simulation.PHASES`: start (6 am), block0 … block23 (each at the start of its hour), end (6 am next day).

## Sleep (`engine/systems/sleep.py`, mechanisms `sleep.*` in `config/mechanisms/22_time.yaml`)

- Body clock (`chronotype`, hours later than typical): age (latest around 20), conscientiousness, sensation seeking,
  extraversion, gaming, social media, marriage, children, plus individual spread.
- Going to bed is one of the hour's options: sleep pressure (hours awake), the 24-hour sleepiness curve shifted by
  chronotype, tomorrow's alarm (the first class, shift or church meeting), sleep debt, fatigue, illness, bedtime
  procrastination (social media vs self-control), and a penalty for daytime naps.
- Falling asleep takes longer with stress, anxiety and coffee. Natural wake = need (the habit from ProvoStats +
  `need_gap`, + catch-up on debt) after falling asleep; alarms ring before the first commitment and can be slept
  through (conscientiousness, debt, depression), which makes people miss class (`overslept`).
- `sleep_hours` is now what they actually slept last night; `bedtime`, `wake_time`, `late_nights_week` are new.

## The hourly choice (`engine/systems/activity.py`)

Every hour, in order: asleep people stay asleep; then fixed commitments (church at the ward's meeting time, a class
meeting, a shift, an occasion they're attending, FHE and ward activities, groups); everyone else makes the free-time
choice among home, campus, gym, eating out, outdoors, visiting a friend, the complex, going to bed and time with a
partner. Each option's utility keeps all the earlier terms (drives, habits, coping, plans, What-if nudges, weather,
Sabbath) and adds:

- a 24-hour time-of-day curve (going-out curves read later for night owls and an hour later on Friday and Saturday
  nights; what's open: campus 7–11 pm and not Sunday);
- carrying on: the option they're already doing gets a pull that fades after its usual length (`activity.hourly`);
- sleep from the sleep system; partner time for dating and engaged couples when the partner is free and awake;
- visiting hours: a guest in an opposite-sex BYU-contracted apartment after midnight (1:30 am Friday nights) feels the
  rule (conformity, religious identity, self-control) against the heat of the moment for a partner (sex drive,
  attraction, hours together tonight, damped by self-control) — a choice, recorded as `past_visiting_hours`.

Two-person parts: time with a partner needs both to be free and the other willing; a visit needs a friend who is home
and awake (the friend becomes the host); someone heading out for food, a hike or the gym can ask their partner or a
close friend, who comes if that outing with them beats their own plan (`activity.together`; after 10 pm recorded as
`late_night_plan` and the event `late_night_out`).

Skipping class: at the start of each class meeting the attendance logit drops when something better is going on
(`activity.skip`), recorded as `skip_class` and `skipped_class`.

Intimacy: hours alone with a partner after 10 pm since the couple's last weekly turn push the next physical step
(`intimacy.step.late`, decision factor `late_nights`).

## Calibration (scale 0.08, 60 days, seed 1; before → after)

Friends 6.37 → 6.44, loneliness 0.274 → 0.262, dates in 30 days 2.73 → 2.75, first dates 4152 → 4316, NCMOs 1226 →
1266, conflicts 49 → 48, sleep 6.82 → 6.86 h, class attendance 0.804 → 0.788, social hours a week 32.6 → 34.4,
social events a month 8.4 → 10.9 (more evening hours to drop by a friend's place), weekday bedtimes mostly 11 pm–1 am
(about 45% asleep at midnight, 82% by 2 am; later on weekends).

## Open issues

- The building-occupancy table (`geo/schedule.py`, committed parquet) is still by the old four blocks, read as parts.
- `social_events_month` runs about 25% above the old model; visits count as social events every time.
- About twice the time per simulated day (hourly utilities and encounters); the budget was re-recorded.
- Early shifts (custodial 4–6 am) aren't drawn yet.
