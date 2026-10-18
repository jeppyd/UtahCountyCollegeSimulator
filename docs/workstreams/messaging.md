# Workstream: Messaging and group chats (wave 2)

> Status: docs/HANDOFF.md. Rules: README.md. Contract: docs/EVOLUTION.md §6. Needs `time-occasions` merged (it leaves the hook `occasions.deliver(inv_ids, channel)`).

People coordinate their social lives by text and group chat. Model that as **structured communication** — no
generated text inside the simulation — so invitations, replies, silence and news become traceable records.

1. `ucsim/engine/systems/messaging.py` (registered in sim.py): **threads** — apartment/roommate chats, friend-group
   chats (form from cliques of close friends; they split when a clique does), club/team chats, ward chats, family
   chats (with kin from the family workstream when it exists), direct threads per active tie (implicit, not stored
   until used). Membership changes are events (added to / left / quietly muted a chat).
2. **Messages** are typed acts: invite (an occasion), reply (yes/no/maybe), check-in (support), news (a salient event
   about someone they know), plan change (rescheduled/cancelled), and silence. Store individual records only for
   salient acts; keep per-thread daily volume counts for the rest.
3. **Attention.** Each person checks messages a few times a day (phone/app use, busyness); a message is noticed with a
   chance that falls as a busy thread fills up and rises if it mentions them. Invitations sent to group chats go
   through this, so "saw it late" and "never saw it" happen. Record `seen_day` on invitations.
4. **Replies and silence.** Reply speed and likelihood from closeness, responsiveness (a trait you may derive from
   conscientiousness/agreeableness) and mood. Unanswered messages are *interpreted*: rejection-sensitive people read
   silence as being ignored (a belief on the tie, hurt, loneliness), secure people as busy. Being left out — learning
   (via news or a shared chat) that friends got together without you — raises hurt and lowers belonging; friends who
   assumed you weren't interested hold the opposite belief. Both sides are records.
5. **Who knows what.** A `KnowledgeStore` (person, event, source person, day, channel) for salient events about
   people they know (engagements, breakups, faith changes, job loss…); news spreads along ties and chats with source
   and delay. Distributed beliefs/reputation (what people believe about someone, and how much they trust the
   source) can build on it later; no universal reputation score.
6. Decisions (`config/decisions/50_messaging.yaml`): reply or not, share news or not, add someone to a chat, leave a
   chat. Events (`config/events/50_messaging.yaml`) with causes.
7. API `ucsim/api/routes_messaging.py`: a person's threads and recent acts; a thread's members and acts; who knows
   about an event and how it spread. Workbench tool `web/src/bench/tools/Chats.tsx`: a person's or group's threads as
   timelines of typed acts (invites, replies, silences flagged), clickable to occasions and Trace; a "how the news
   spread" view for an event (a small spreading tree over time).
8. Tests: attention and noticing, silence interpretation by rejection sensitivity, exclusion records, news spread
   reaches friends before strangers, determinism. Performance: bounded per-day cost at full scale (60k).
