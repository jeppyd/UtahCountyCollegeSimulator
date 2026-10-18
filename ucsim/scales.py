"""What a variable's numbers mean, for people reading the workstation: its range and units in words, anchors (3–5
points along the range, each with words), how the model measures it, and how to read standardized traits, survey
answers and percentages. Served with the registry (`VarSpec.to_dict()["scale"]`) and, with the live population
distribution, by `/api/scales` (`api/routes_scales.py`).

Sources of the words, in order: survey answer wording (`ingest/survey_spec.py`, matched through the variable's
`copula <survey>.<item>` init), the hand-written anchors below, then generic rules by range and units. Anchor words for
model scales are a reading guide written for this model (`basis: "guide"`), not measurements; the card says so."""
from __future__ import annotations

import re
from functools import lru_cache

# ------------------------------------------------------------------------------------------------ anchor words
# (value, short words[, longer words]) — short words fit under a ruler tick; longer words show on hover and in cards.
A = tuple[float, str] | tuple[float, str, str]

ANCHORS: dict[str, list[A]] = {
    # ---- feelings the model composes each day
    "mood": [(0, "very unhappy", "miserable; nothing feels good"), (0.25, "low", "down more than up"),
             (0.5, "so-so", "an ordinary, mixed day"), (0.75, "happy", "upbeat; things feel good"),
             (1, "very happy", "as good as days get")],
    "stress": [(0, "calm", "nothing weighing on them"), (0.25, "a little stressed", "manageable pressure"),
               (0.5, "stressed", "feels the pressure most days"), (0.75, "very stressed", "struggling to keep up"),
               (1, "overwhelmed", "can't keep up at all")],
    "loneliness": [(0, "not lonely", "has people and feels connected"), (0.25, "lonely now and then"),
                   (0.5, "often lonely"), (0.75, "lonely most days"),
                   (1, "extremely lonely", "isolated nearly all the time")],
    "anxiety": [(0, "at ease", "relaxed, little worry"), (0.25, "a little on edge"), (0.5, "anxious", "worries often"),
                (0.75, "very anxious", "worry gets in the way"), (1, "extremely anxious", "worried nearly all the time")],
    "belonging": [(0, "an outsider", "doesn't feel they fit anywhere here"), (0.25, "on the edges"),
                  (0.5, "somewhat belongs", "fits in some places"), (0.75, "belongs", "has their places and people"),
                  (1, "fully belongs", "completely at home here")],
    "self_esteem": [(0, "very low confidence", "thinks little of themselves"), (0.25, "unsure of themselves"),
                    (0.5, "middling confidence"), (0.75, "confident"), (1, "very high confidence", "sure of their worth")],
    "guilt": [(0, "no guilt", "at peace with their choices"), (0.25, "a twinge of guilt"),
              (0.5, "guilty", "it weighs on them"), (0.75, "strong guilt", "often on their mind"),
              (1, "overwhelming guilt", "consumed by it")],
    "fatigue": [(0, "fully rested"), (0.25, "a little tired"), (0.5, "tired"), (0.75, "worn out"),
                (1, "exhausted", "running on empty")],
    "purpose": [(0, "aimless", "no sense of direction"), (0.25, "drifting"), (0.5, "some direction"),
                (0.75, "purposeful", "knows what they are working toward"),
                (1, "strong sense of purpose", "life feels meaningful and directed")],
    "financial_stress": [(0, "no money worries"), (0.25, "watches money", "careful, but fine"),
                         (0.5, "money is tight", "worries about bills"), (0.75, "struggling", "hard to cover the basics"),
                         (1, "severe money stress", "can't make ends meet")],
    "academic_pressure": [(0, "no pressure", "not in school, or school feels easy"), (0.25, "some pressure", "a normal load"),
                          (0.5, "pressured", "deadlines and exams weigh on them"),
                          (0.75, "heavy pressure", "behind, or afraid of falling behind"), (1, "crushing pressure")],
    "romantic_longing": [(0, "no longing", "content as things are, or partnered"), (0.25, "would like someone", "a passing wish"),
                         (0.5, "longs for a partner", "thinks about it often"),
                         (0.75, "strong longing", "being single hurts"), (1, "intense longing", "consumed by it")],
    "life_satisfaction": [(0, "completely dissatisfied", "the worst possible life for them"), (2.5, "dissatisfied"),
                          (5, "mixed", "neither good nor bad"), (7.5, "satisfied"),
                          (10, "completely satisfied", "the best possible life for them")],
    "outsider": [(0, "part of the mainstream", "fits in with Utah County's Latter-day Saint majority, or doesn't feel apart"),
                 (0.25, "a little apart"), (0.5, "often feels apart"), (0.75, "an outsider"), (1, "a complete outsider")],
    "coping_need": [(0, "coping fine", "strain within what they can take"), (0.15, "a little strained",
                    "below this a hard stretch ends"), (0.4, "struggling", "above this for two days, a coping episode starts"),
                    (0.7, "barely coping"), (1, "overwhelmed")],
    "coping_relief": [(0, "no relief"), (0.25, "a little relief"), (0.5, "real relief"), (0.75, "strong relief"),
                      (1, "full relief")],
    # ---- inner life
    "rumination": [(0, "lets things go"), (0.25, "moves on fairly quickly"), (0.5, "dwells sometimes"),
                   (0.75, "dwells a lot"), (1, "dwells on everything", "replays bad moments over and over")],
    "routine_strength": [(0, "no routine", "every week is different"), (0.25, "a few habits"),
                         (0.5, "a fairly settled week"), (0.75, "a settled routine"),
                         (1, "fully automatic week", "the same things in the same slots, without thinking")],
    "expect_social": [(0, "expects coldness", "assumes people will be unfriendly"), (0.25, "wary"),
                      (0.5, "unsure what to expect"), (0.75, "expects warmth", "people are usually kind"),
                      (1, "expects great warmth", "sure people will welcome them")],
    "self_eff_academic": [(0, "doubts they can do it"), (0.25, "unsure about school"), (0.5, "somewhat confident"),
                          (0.75, "confident in school"), (1, "sure they can do it")],
    "perceived_support": [(0, "no one to turn to"), (0.25, "a little support"), (0.5, "some support"),
                          (0.75, "good support"), (1, "plenty of support", "many people would help")],
    "support_actual": [(0, "no real support", "no close, warm ties present"), (0.25, "a little support"),
                       (0.5, "some support"), (0.75, "good support"), (1, "plenty of support")],
    "perceived_friend_belief": [(0, "thinks friends don't believe"), (0.25, "thinks friends mostly doubt"),
                                (0.5, "thinks friends are mixed"), (0.75, "thinks friends mostly believe"),
                                (1, "thinks friends fully believe")],
    "friend_belief_actual": [(0, "friends don't believe"), (0.25, "friends mostly doubt"), (0.5, "friends are mixed"),
                             (0.75, "friends mostly believe"), (1, "friends fully believe")],
    "memory_tone": [(-1, "mostly painful memories"), (-0.5, "more bad than good"), (0, "balanced"),
                    (0.5, "more good than bad"), (1, "mostly happy memories")],
    "sat_fun": [(0, "no fun lately", "far less than they want"), (0.25, "a little"), (0.5, "half of what they want"),
                (0.75, "most of what they want"), (1, "as much as they want")],
    "sat_health": [(0, "no exercise lately", "far less than they want"), (0.25, "a little"), (0.5, "half of what they want"),
                   (0.75, "most of what they want"), (1, "as much as they want")],
    "expect_accept": [(0, "expects a no", "sure every ask will be turned down"), (0.25, "expects mostly no's"),
                      (0.5, "a coin flip"), (0.75, "expects mostly yes"), (1, "sure of a yes")],
    # ---- faith
    "faith_belief": [(0, "doesn't believe", "rejects core doctrine"), (0.25, "mostly doubts"),
                     (0.5, "unsure", "believes some, doubts some"), (0.75, "believes", "believes, with some questions"),
                     (1, "fully believes", "believes all core doctrine")],
    "faith_certainty": [(0, "very unsure", "beliefs feel unsettled, whatever they are"), (0.25, "unsure"),
                        (0.5, "somewhat sure"), (0.75, "sure"), (1, "completely certain")],
    "religious_identity": [(0, "not part of who they are"), (0.25, "a small part"), (0.5, "an important part"),
                           (0.75, "central"), (1, "the core of who they are")],
    "institutional_trust": [(0, "no trust in church leaders"), (0.25, "little trust"), (0.5, "some trust"),
                            (0.75, "trusts leaders"), (1, "complete trust")],
    "orthodoxy": [(0, "rejects specific teachings", "disagrees with the contested teachings"), (0.25, "accepts few"),
                  (0.5, "accepts some"), (0.75, "accepts most"), (1, "accepts every teaching")],
    "moral_autonomy": [(0, "standards are never optional"), (0.25, "rarely optional"), (0.5, "it depends"),
                       (0.75, "own conscience usually wins"), (1, "own conscience overrides standards")],
    "practice_habit": [(0, "no habit"), (0.25, "a weak habit"), (0.5, "a habit"), (0.75, "a strong habit"),
                       (1, "fully automatic", "goes without thinking about it")],
    "private_practice": [(0, "no prayer or study"), (0.25, "occasional prayer or study"), (0.5, "regular prayer and study"),
                         (0.75, "prays and studies most days"), (1, "devoted daily practice")],
    "own_religiosity": [(0, "doesn't matter to them", "or nonreligious"), (0.25, "matters a little"), (0.5, "matters"),
                        (0.75, "matters a lot"), (1, "central to their life")],
    "history_struggle": [(0, "no struggle"), (0.5, "some struggle"), (1, "severe struggle")],
    "lgbtq_tension": [(0, "no tension", "or not a sexual-minority member"), (0.25, "some tension"), (0.5, "real tension"),
                      (0.75, "hard to reconcile"), (1, "severe tension", "faith and identity feel impossible to reconcile")],
    "family_expectation": [(0, "no family pressure"), (0.25, "a little expectation"), (0.5, "some expectation"),
                           (0.75, "strong expectation"), (1, "family expects it absolutely")],
    "chastity_commitment": [(0, "no commitment"), (0.25, "weak commitment"), (0.5, "committed, with reservations"),
                            (0.75, "committed"), (1, "complete commitment")],
    "porn_incongruence": [(0, "no distress", "no use, or use without conflict"), (0.25, "some unease"),
                          (0.5, "distressed"), (0.75, "strong distress"), (1, "severe distress")],
    "home_faith_culture": [(0, "not observant", "few residents attend services"), (0.25, "a little observant"),
                           (0.5, "mixed"), (0.75, "observant"), (1, "very observant", "nearly everyone attends")],
    # ---- dating and relationships
    "dating_motivation": [(0, "not interested in dating"), (0.25, "open to it"), (0.5, "wants to date"), (0.75, "eager"),
                          (1, "very eager to date")],
    "relationship_satisfaction": [(0, "very unhappy together"), (0.25, "unhappy together"), (0.5, "mixed"),
                                  (0.75, "happy together"), (1, "very happy together")],
    "relationship_commitment": [(0, "ready to leave", "or not in a relationship"), (0.25, "wavering"),
                                (0.5, "committed for now"), (0.75, "committed"), (1, "fully committed")],
    "rejections_recent": [(0, "none lately"), (0.5, "one fading no"), (1, "a recent no"), (3, "several recent no's"),
                          (6, "many recent no's")],
    "dating_propensity": [(0, "doesn't date"), (1, "about once a month"), (4, "about once a week"), (8, "twice a week"),
                          (20, "almost every day")],
    "dates_30d": [(0, "no dates"), (1, "one date"), (4, "about one a week"), (8, "two a week"), (15, "every other day")],
    "dates_total": [(0, "none"), (1, "one"), (5, "a few"), (20, "many"), (100, "a great many")],
    "first_dates_total": [(0, "none"), (1, "one"), (3, "a few"), (10, "many"), (30, "a great many")],
    "app_hours": [(0, "doesn't use apps"), (1, "about an hour a week"), (3, "a few hours a week"), (7, "an hour a day"),
                  (14, "two hours a day")],
    "n_relationships": [(0, "never in one"), (1, "one"), (3, "a few"), (8, "many")],
    "n_breakups": [(0, "none"), (1, "one"), (3, "a few"), (6, "many")],
    "imp_spirituality": "rank", "imp_physical": "rank", "imp_personality": "rank", "imp_shared_interests": "rank",
    "min_height_req": [(60, "5′0″", "no real minimum"), (64, "5′4″"), (68, "5′8″"), (72, "6′0″"), (76, "6′4″")],
    "max_older": [(0, "same age or younger only"), (2, "two years"), (5, "five years"), (10, "ten years"), (20, "twenty years")],
    "max_younger": [(0, "same age or older only"), (2, "two years"), (5, "five years"), (10, "ten years"), (20, "twenty years")],
    "age_at_marriage": [(19, "19"), (21, "21"), (23, "23"), (26, "26"), (30, "30")],
    # ---- friends and social life
    "n_friends": [(0, "no friends yet"), (2, "a couple"), (5, "a handful"), (10, "a wide circle"), (20, "very many")],
    "n_close_friends": [(0, "none"), (1, "one"), (3, "a few"), (6, "several"), (12, "many")],
    "n_acquaintances": [(0, "knows no one"), (10, "a few faces"), (50, "a good many"), (150, "about 150", "roughly the number of relationships people can keep up (Dunbar)"),
                        (500, "a huge number")],
    "degree": [(0, "knows no one"), (10, "a few faces"), (50, "a good many"), (150, "about 150", "roughly the number of relationships people can keep up (Dunbar)"),
               (500, "a huge number")],
    "new_friends_90d": [(0, "none"), (1, "one"), (3, "a few"), (6, "many")],
    "social_hours_week": [(0, "alone all week"), (10, "a little each day"), (25, "a few hours a day"),
                          (45, "much of the day"), (70, "with people almost constantly")],
    "close_contact_hours": [(0, "none", "no time with friends, partner or liked roommates"), (5, "under an hour a day"),
                            (15, "about two hours a day"), (30, "four hours a day"), (50, "most free time")],
    "social_events_month": [(0, "none"), (2, "a couple"), (6, "one or two a week"), (12, "about three a week"),
                            (25, "almost daily")],
    "n_groups": [(0, "none"), (1, "one"), (2, "two"), (3, "three", "a club, a team and an institute class")],
    "roommate_cohesion": [(0, "roommates dislike each other"), (0.25, "some friction"),
                          (0.5, "neutral", "or lives without roommates"), (0.75, "like each other"), (1, "roommates are close")],
    "ward_belonging": [(0, "an outsider in the ward"), (0.25, "on the edges of the ward"), (0.5, "somewhat at home"),
                       (0.75, "at home in the ward"), (1, "fully at home in the ward")],
    "home_social_culture": "zplace",
    # ---- values and intimacy
    "kids_wanted": [(0, "none"), (2, "two"), (4, "four"), (6, "six"), (10, "ten")],
    "ideal_months_engaged": [(3, "three months"), (6, "six months"), (12, "a year"), (24, "two years"), (48, "four years")],
    "n_kissed": [(0, "none"), (1, "one"), (5, "a few"), (20, "many"), (100, "a great many")],
    "n_ncmo": [(0, "none"), (1, "one"), (5, "a few"), (20, "many"), (100, "a great many")],
    "n_sex_partners": [(0, "none"), (1, "one"), (3, "a few"), (10, "many"), (30, "a great many")],
    "bishop_meetings": [(0, "never"), (1, "once"), (3, "several times"), (6, "many times")],
    # ---- school, work, money, home
    "gpa": [(1, "D average"), (2, "C average"), (3, "B average"), (3.5, "B+ / A−"), (4, "straight A's")],
    "gpa_term": [(1, "D average"), (2, "C average"), (3, "B average"), (3.5, "B+ / A−"), (4, "straight A's")],
    "credits_done": [(0, "just starting"), (30, "about a year"), (60, "about two years"), (90, "about three years"),
                     (120, "about a degree", "a bachelor's degree takes about 120 credits")],
    "credits_term": [(0, "not enrolled"), (6, "part-time"), (12, "full-time", "12 credits is the full-time minimum"),
                     (15, "a typical full load"), (18, "a heavy load")],
    "study_hours": [(0, "none"), (5, "under an hour a day"), (15, "about two hours a day"), (30, "a full-time job's worth"),
                    (45, "very heavy")],
    "class_attendance": [(0, "never goes to class"), (0.5, "misses half"), (0.75, "misses one in four"),
                         (0.9, "rarely misses"), (1, "never misses")],
    "work_hours": [(0, "not working"), (10, "a few shifts"), (20, "part-time"), (40, "full-time"), (60, "very long hours")],
    "wage": [(7.25, "minimum wage", "Utah follows the federal minimum, $7.25"), (15, "a typical student job"),
             (25, "a skilled job"), (40, "professional pay"), (80, "high professional pay")],
    "monthly_income": [(0, "none"), (500, "$500"), (1500, "$1,500", "about a part-time job"), (4000, "$4,000", "about a full-time job"),
                       (10000, "$10,000")],
    "parental_support": [(0, "none"), (200, "$200"), (500, "$500"), (1000, "$1,000"), (3000, "$3,000")],
    "savings": [(-5000, "behind", "owes more on savings than they hold"), (0, "nothing saved"), (1000, "$1k", "a small cushion"),
                (5000, "$5k", "a few months' cushion"), (25000, "$25k", "well cushioned")],
    "debt": [(0, "none"), (1000, "$1k", "small"), (10000, "$10k", "moderate"), (30000, "$30k", "large"),
             (100000, "$100k", "very large")],
    "rent": [(0, "pays no rent", "lives with family or owns"), (400, "$400", "a shared student room"),
             (700, "$700", "a private room"), (1200, "$1,200", "an apartment of their own"), (2000, "$2,000", "a family home")],
    "rent_burden": [(0, "no rent"), (0.3, "30% of income", "the usual line for 'rent-burdened'"), (0.5, "half of income"),
                    (1, "all of income"), (2, "twice their income", "others pay the rest")],
    "commute_min": [(5, "next door"), (15, "short"), (30, "half an hour"), (45, "three quarters of an hour"), (60, "an hour")],
    "dist_campus_km": [(0.5, "next to campus"), (1.5, "walking distance"), (5, "a bike ride"), (15, "a drive"), (30, "far away")],
    # ---- habits
    "sleep_hours": [(4, "very short"), (6, "short"), (7, "enough", "7 or more hours is the usual recommendation"),
                    (8, "well rested"), (10, "long")],
    "workouts_week": [(0, "never"), (2, "twice a week"), (4, "four times a week"), (7, "daily"), (14, "twice a day")],
    "social_media_hours": [(0, "none"), (1, "an hour a day"), (2, "two hours a day"), (4, "four hours a day"),
                           (8, "eight hours a day")],
    "soda_shop_week": [(0, "never"), (0.5, "every other week"), (1, "weekly"), (3, "a few times a week"), (7, "daily")],
    "scripture_minutes": [(0, "none"), (5, "a few minutes"), (15, "a quarter hour"), (30, "half an hour"), (60, "an hour")],
    "temple_per_year": [(0, "never"), (1, "once a year"), (12, "monthly"), (52, "weekly"), (100, "twice a week")],
    "attend_rate": [(0, "never goes"), (0.25, "about one Sunday a month"), (0.5, "every other Sunday"),
                    (0.75, "most Sundays"), (1, "every Sunday")],
    "service_attend": [(0, "never goes", "or has no congregation"), (0.25, "about once a month"), (0.5, "every other week"),
                       (0.75, "most weeks"), (1, "every week")],
    "ward_activity_rate": [(0, "never goes"), (0.25, "now and then"), (0.5, "about half of them"), (0.75, "most of them"),
                           (1, "whenever there is one")],
    "perceived_norm": [(0, "no one around them attends"), (0.25, "a few attend"), (0.5, "about half attend"),
                       (0.75, "most attend"), (1, "everyone around them attends")],
    # ---- background and body
    "age": [(18, "18", "freshman age"), (22, "22", "a typical graduating senior"), (26, "26"), (35, "35"), (60, "60")],
    "height_in": [(60, "5′0″"), (64, "5′4″"), (68, "5′8″"), (72, "6′0″"), (76, "6′4″")],
    "weight_lb": [(100, "100 lb"), (150, "150 lb"), (200, "200 lb"), (250, "250 lb"), (300, "300 lb")],
    "bmi": [(17, "underweight", "below 18.5"), (21.5, "healthy weight", "18.5 to 25"), (27.5, "overweight", "25 to 30"),
            (33, "obese", "30 to 40"), (42, "severely obese", "40 or more")],
    "children": [(0, "none"), (1, "one"), (3, "three"), (6, "a large family")],
    "languages": [(1, "one language"), (2, "two", "often from a foreign-language mission"), (3, "three"), (6, "six")],
    "n_memories": [(0, "none"), (5, "a few"), (15, "a good many"), (30, "many"), (40, "the most kept", "memory keeps at most 40")],
    "plans_kept": [(0, "none"), (1, "one"), (5, "a few"), (20, "many"), (60, "a great many")],
    "plans_abandoned": [(0, "none"), (1, "one"), (5, "a few"), (20, "many"), (60, "a great many")],
    # survey items whose answer words need a little context
    "prefers_rm": [(0, "much worse", "a returned missionary seems a much worse match"), (1, "somewhat worse"),
                   (2, "about the same", "a mission makes no difference"), (3, "somewhat better"),
                   (4, "much better", "strongly prefers someone who served")],
}

# Standard-score traits: words for −2, −1, +1, +2 (0 is "average").
Z_WORDS: dict[str, tuple[str, str, str, str]] = {
    "extraversion": ("very reserved", "reserved", "outgoing", "very outgoing"),
    "agreeableness": ("very critical", "tough-minded", "warm", "very warm"),
    "conscientiousness": ("very disorganized", "easygoing", "organized", "very disciplined"),
    "neuroticism": ("very even-keeled", "calm", "worries easily", "very emotionally reactive"),
    "openness": ("very conventional", "practical", "curious", "very open to new ideas"),
    "sensation_seeking": ("avoids any risk", "cautious", "likes thrills", "thrill-seeker"),
    "self_control": ("very impulsive", "impulsive", "self-disciplined", "very self-controlled"),
    "rejection_sensitivity": ("shrugs off rejection", "thick-skinned", "sensitive to rejection", "dreads rejection"),
    "attachment_anxiety": ("very secure in love", "secure", "worries about being left", "fears abandonment"),
    "attachment_avoidance": ("very comfortable with closeness", "comfortable with closeness", "keeps some distance",
                             "uneasy with closeness"),
    "social_anxiety": ("socially fearless", "at ease with people", "socially nervous", "very socially anxious"),
    "conformity": ("very independent-minded", "independent", "goes with the group", "follows the group closely"),
    "empathy": ("rarely attuned to others", "less attuned", "empathetic", "deeply empathetic"),
    "attractiveness": ("far below average to most", "below average to most", "above average to most",
                       "far above average to most"),
    "academic_ability": ("far below average", "below average", "above average", "far above average"),
    "social_skill": ("very awkward", "a bit awkward", "socially skilled", "very socially skilled"),
}
Z_SHARE = {-2: "lower than about 98% of people", -1: "lower than about 84% of people", 0: "the middle of the population",
           1: "higher than about 84% of people", 2: "higher than about 98% of people"}

# Low and high ends in words for 0–1 scales without hand-written anchors (the generic rule fills the middle).
ENDS = {
    "cares": ("doesn't matter to them", "matters most"),
    "drive": ("no pull right now", "strongest pull"),
}

# ------------------------------------------------------------------------------------------------ how it's measured
SURVEY_TITLE = {"provostats": "ProvoStats", "college_life": "College Life", "dating": "Dating", "culture": "Culture & Lifestyle"}

HOW: dict[str, str] = {
    "mood": "A feeling the model composes each day: a personal set-point (from extraversion and neuroticism) plus loneliness, "
            "stress, their relationship, sense of purpose, sleep, exercise, the season and friends' moods, plus the fading "
            "effects of recent events.",
    "stress": "A feeling the model composes each day from a personal set-point (neuroticism), academic pressure, money "
              "stress, fatigue, their relationship and faith struggles, cushioned by the support they believe they have.",
    "loneliness": "A feeling the model composes each day from time with close people compared with how much contact this "
                  "person needs (extraverts need more), their close friends, the support they believe they have, a partner, "
                  "their ward and roommates — it is contact relative to need, not contact alone.",
    "anxiety": "A feeling the model composes each day from a personal set-point (neuroticism and any anxiety diagnosis), "
               "stress and social anxiety, plus the fading effects of recent events.",
    "belonging": "A feeling the model composes each day from friends, roommates, ward or congregation, loneliness and "
                 "feeling a religious outsider.",
    "self_esteem": "A feeling the model composes each day from a personal set-point, recent romantic rejections and "
                   "successes, being in a relationship and grades.",
    "guilt": "A feeling that rises when the person acts against standards they hold (coffee, alcohol, chastity, "
             "pornography), in proportion to their own commitment, and falls with confession, time or a change of belief.",
    "fatigue": "A state the model composes from sleep, work, study and class load and young children.",
    "purpose": "A feeling the model composes from conscientiousness, faith and religious identity, progress in school or "
               "work, and marriage and children.",
    "financial_stress": "A feeling the model composes from savings measured in months of expenses (sharply worse below about a "
                        "month), debt and how much of their income rent takes.",
    "academic_pressure": "A feeling the model composes from credit load, exam weeks, the gap between their grades and their "
                         "standards, and academic standing; 0 for people not in school.",
    "romantic_longing": "A feeling the model composes for single people who want a relationship, rising with the age-graded "
                        "marriage norm and long stretches without dates; it eases while they are talking to someone.",
    "life_satisfaction": "A slow average of how life has felt over the last month — mood, purpose, relationship and money "
                         "security and the tone of their memories — on the usual 0–10 'ladder' used in wellbeing surveys.",
    "outsider": "A feeling for people outside the Latter-day Saint mainstream: rises with mostly-LDS friends and roommates and "
                "with being proselytized, falls with friends who share their outlook.",
    "coping_need": "How far stress, low mood and loneliness sit above what this person can tolerate today; a coping episode "
                   "starts when it stays above 0.4 for two days and ends after three days below 0.15.",
    "coping_relief": "Relief from the current way of coping, fading over days; it only comes if what the strategy relies on "
                     "(supportive friends, faith, activities) is actually there.",
    "rumination": "A stable tendency, mostly from neuroticism; it keeps bad memories active, which prolongs low moods.",
    "routine_strength": "The average habit strength of their weekly free-time routine: doing the same thing in the same "
                        "time slot week after week makes it automatic (about two months to settle).",
    "expect_social": "Learned from how their interactions at gatherings, venues, dances, clubs and hangouts actually went; "
                     "socially anxious people learn more from bad experiences.",
    "expect_accept": "Learned from the person's own asks: each yes or no nudges what they expect next time; "
                     "rejection-sensitive people learn more from a no.",
    "self_eff_academic": "Belief in their own academic ability, updated each term by how their grades compare with "
                         "classmates'; it can differ from their real ability.",
    "perceived_support": "Built from their real close, warm ties, seen through a personal lens and biased by neuroticism, "
                         "attachment anxiety and loneliness.",
    "support_actual": "Closeness times warmth, added up over close friends and partner who are around, with diminishing returns.",
    "perceived_friend_belief": "What their friends seem to believe: friends who aren't close show the belief they express, "
                               "pulled toward the local norm; close friends who have confided show their real belief.",
    "friend_belief_actual": "The closeness-weighted average of their friends' real belief, for comparison with what they see.",
    "memory_tone": "The balance of good and bad memories they still hold, weighted by how strong each memory is.",
    "faith_belief": "Starts from the Culture & Lifestyle and ProvoStats survey items on believing all doctrine and supporting "
                    "the teachings; the model then moves it weekly through friends, spiritual experiences, faith challenges "
                    "and the gap between belief and behavior.",
    "faith_certainty": "Starts from survey items on having struggled with faith, struggling with church history and being "
                       "in a faith crisis now; spiritual experiences raise it and faith challenges lower it.",
    "religious_identity": "Built from attendance, garments, a temple recommend, youth conferences (EFY), a mission and belief; "
                          "it changes slowly, so people can stay 'in' while belief falls.",
    "institutional_trust": "Built from survey items on supporting church teachings, experiences with bishops and expecting a "
                           "policy change; moved by announcements and bishop meetings.",
    "orthodoxy": "The average agreement with five contested teachings in the Culture & Lifestyle survey (plural marriage, "
                 "women and the priesthood, same-sex marriage policy, R-rated movies, traditional roles).",
    "moral_autonomy": "From the Culture & Lifestyle survey item 'it is okay to break church standards if it feels internally "
                      "acceptable' (strongly disagree … strongly agree, spread over 0–1).",
    "practice_habit": "How automatic Sunday attendance has become: it grows with each week attended and fades slowly with absence.",
    "attend_rate": "The share of Sundays at sacrament meeting over the last eight weeks, started from the Culture & Lifestyle "
                   "survey's attendance answer.",
    "private_practice": "Prayers per day and minutes of personal scripture study (Culture & Lifestyle survey) combined; 1 means "
                        "at least five prayers and half an hour of study a day.",
    "dating_motivation": "Recomputed daily from wanting a relationship, the pull of partnership against competing concerns, age "
                         "and marriage norms, mission status, confidence and availability.",
    "relationship_satisfaction": "For married people it starts from the Culture & Lifestyle survey's marriage-satisfaction "
                                 "answer; the model then moves it with attraction, pair chemistry, shared faith, conflict and "
                                 "time together. Empty for people not in a relationship.",
    "relationship_commitment": "The investment model of commitment: rises with satisfaction and what the couple has built "
                               "together, falls with attractive alternatives; 0 when not in a relationship.",
    "ward_belonging": "Composed from friends in the ward, attendance, callings and fit with the ward's culture.",
    "roommate_cohesion": "How much the people who live together like each other on average (0.5 is neutral, and the value for "
                         "people who live without roommates).",
    "n_friends": "Counted from their ties: a friend is someone they have spent about 90 leisure-equivalent hours with and "
                 "like (after Hall 2019).",
    "n_close_friends": "Counted from their ties: about 200 leisure-equivalent hours together, high liking and closeness.",
    "close_contact_hours": "Smoothed hours per week with friends, partner and well-liked roommates — the input to loneliness.",
    "social_hours_week": "Smoothed hours per week with other people in any setting, including class and work.",
    "social_events_month": "Social events attended in the last 30 days (gatherings, dances, ward and family home evening "
                           "activities, clubs and teams); compared with the ProvoStats survey's events per month.",
    "home_social_culture": "How social their apartment is compared with other occupied apartments: gatherings hosted and "
                           "friends dropping by, with memory, so it outlasts the residents who built it.",
    "home_faith_culture": "How many residents of their complex attend church or services, with slow inertia.",
    "politics": "Drawn from the ProvoStats survey's political orientation for people of the same faith, activity and sex; "
                "it stays as drawn.",
    "n_breakups": "Counted in the simulation: breakups since the world started.",
    "dates_30d": "A running count of dates over about the last month (older dates fade out).",
    "dates_total": "Counted in the simulation: dates since the world started.",
    "first_dates_total": "Counted in the simulation: first dates since the world started.",
    "n_acquaintances": "Counted from their ties: everyone they would recognize (weak ties they stop remembering drop out).",
    "degree": "Counted from their ties: everyone they would recognize (weak ties they stop remembering drop out).",
    "new_friends_90d": "Counted from their ties: people who became friends in the last 90 days.",
    "credits_done": "Credits completed so far, started from class standing and added each finished term.",
    "credits_term": "Credits they are taking this term (0 when not enrolled).",
    "gpa": "Starts from the GPA reported in the ProvoStats survey; each finished term's grades are averaged in.",
    "gpa_term": "Last term's grades, produced from ability, study effort, class attendance and course load.",
    "study_hours": "Smoothed hours a week spent studying, from course load, conscientiousness, academic confidence and "
                   "competing pulls on their time.",
    "class_attendance": "The share of their class meetings they actually attend.",
    "work_hours": "Hours a week at their job, started from the ProvoStats survey's work hours; 0 when not employed.",
    "monthly_income": "Earnings plus money from family and other sources, per month.",
    "parental_support": "Money from parents each month (rent, tuition, insurance, a car), from parental income and the "
                        "College Life survey's 'parents pay for' items.",
    "savings": "Money in hand: income in, rent and living costs out, month by month (can go negative).",
    "debt": "Student loans and other debt.",
    "rent": "Their share of the rent each month.",
    "rent_burden": "Rent divided by their monthly income including family help (2 when they pay rent with no income).",
    "commute_min": "Minutes to campus or work by their usual way of getting there.",
    "dist_campus_km": "Straight-line distance from home to their campus.",
    "age": "Their age today, from their birthday and the simulation's date; the starting mix of ages comes from the surveys.",
    "age_at_marriage": "How old they were at their (first) wedding; empty if never married.",
    "own_religiosity": "How much a person's own non-LDS religion matters to them (near 0 for the nonreligious); it drives "
                       "attending their own services.",
    "service_attend": "The share of recent weeks (about eight) a person of another faith attended their own services.",
    "sat_fun": "Recent outings (gatherings, dates, venues, the outdoors, clubs) compared with their appetite for fun; 1 means "
               "as much as they want.",
    "sat_health": "Recent workouts compared with how much they want to exercise; 1 means as much as they want.",
    "porn_use": "Not asked in the supplied surveys: drawn from broad research on how common it is by sex, lowered by "
                "commitment to chastity — treat it as a rough assumption.",
    "chastity_commitment": "Built from orthodoxy, church activity, modesty norms and (lower) interest in NCMOs.",
    "rejections_recent": "A count of recent romantic rejections that fades over the following weeks; it weighs on confidence "
                         "in asking someone out.",
    "history_struggle": "From the Culture & Lifestyle survey's agree–disagree item on struggling to reconcile church history "
                        "with faith.",
    "lgbtq_tension": "For sexual-minority Latter-day Saints, from the Culture & Lifestyle survey item on how hard it is to "
                     "reconcile being LGBTQ with their faith (spread over 0–1); 0 for everyone else.",
    "bishop_meetings": "From the Culture & Lifestyle survey's question on adult meetings with a bishop as part of repentance "
                       "(never, for one thing, for several).",
    "weight_lb": "Body weight, from body-mass index and height.",
    "bmi": "Drawn by sex and age (a median near 23 for women and 24.5 for men at age 20, rising with age), shifted slightly "
           "lower for this population; it feeds weakly into how attractive others find them.",
    "children": "How many children they have (children belong to the household; they are not simulated as people).",
    "parent_income": "From the ProvoStats survey's parents' income brackets, by whether they grew up in Utah; it shapes how "
                     "much money family sends.",
    "n_groups": "How many weekly groups they belong to: a campus club, an intramural team, an institute class.",
    "perceived_norm": "How often the people around them (roommates, friends, ward) attend church, weighted by closeness — "
                      "the local norm they perceive.",
    "family_expectation": "How much they feel their family expects them to stay active in church (higher when raised in "
                          "Utah, raised Latter-day Saint, or with family nearby).",
    "n_memories": "How many memories of important events they still hold (memories fade unless re-lived; at most 40).",
}

# Survey-started fields that the simulation actually changes (checked on a 40-day run; the registry's `update` field is
# aspirational for many survey items, which stay as drawn).
SURVEY_MOVES = {"faith_belief", "attend_rate", "scripture_minutes", "temple_per_year", "n_kissed", "n_ncmo",
                "n_sex_partners", "app_hours", "relationship_satisfaction", "sleep_hours", "coffee", "alcohol", "work_hours",
                "wage", "gpa", "n_relationships"}

# what "unmet" means for each concern (drives are importance × unmet)
DRIVE_UNMET = {"connection": "how disconnected they feel", "partnership": "romantic longing, or an unhappy relationship",
               "achievement": "academic pressure beyond their confidence", "security": "money stress",
               "faith": "the gap between their convictions and how they live", "rest": "fatigue",
               "fun": "few outings lately compared with their appetite", "health": "too few workouts compared with what they want"}

# ------------------------------------------------------------------------------------------------ units in words
UNIT_WORDS = {
    "years": "years", "inches": "inches", "lb": "pounds", "kg/m²": "body-mass index (kg/m²)", "minutes/day": "minutes a day",
    "visits/year": "visits a year", "children": "children", "months": "months", "people": "people",
    "dates/month": "dates a month", "dates": "dates in the last 30 days", "hours/week": "hours a week",
    "hours": "hours a night", "credits": "credit hours", "USD/hour": "dollars an hour", "USD/month": "dollars a month",
    "USD": "dollars", "share of income": "share of monthly income", "minutes": "minutes one way", "km": "kilometers",
}
UNIT_BY_ID = {
    "languages": "languages", "children": "children", "bishop_meetings": "meetings", "n_relationships": "relationships",
    "n_breakups": "breakups", "dates_total": "dates", "first_dates_total": "first dates", "rejections_recent": "recent no's (fading)",
    "n_friends": "friends", "n_close_friends": "close friends", "n_acquaintances": "people", "degree": "people",
    "new_friends_90d": "new friends", "n_groups": "groups", "workouts_week": "workouts a week",
    "social_media_hours": "hours a day", "soda_shop_week": "visits a week", "gpa": "grade points (A = 4)",
    "gpa_term": "grade points (A = 4)", "plans_kept": "intentions", "plans_abandoned": "intentions",
    "social_events_month": "events in the last 30 days", "n_memories": "memories", "life_satisfaction": "points on a 0–10 ladder",
    "imp_spirituality": "rank among six qualities", "imp_physical": "rank among six qualities",
    "imp_personality": "rank among six qualities", "imp_shared_interests": "rank among six qualities",
    "memory_tone": "balance from −1 (all bad) to 1 (all good)", "home_social_culture": "standard score among apartments",
    "dates_30d": "dates in the last 30 days", "sleep_hours": "hours a night", "age_at_marriage": "years old at the wedding",
}

# Shown on a log-like axis (long right tails: most people near 0, a few far out).
LOG_AXIS = {"monthly_income": 300, "parental_support": 100, "savings": 1000, "debt": 1000, "n_kissed": 1, "n_ncmo": 1,
            "n_sex_partners": 1, "n_acquaintances": 5, "degree": 5, "temple_per_year": 1, "dates_total": 1,
            "first_dates_total": 1, "plans_kept": 1, "plans_abandoned": 1}
# Display window when the declared range is much wider than real values (values outside are drawn at the edge).
VIEW = {"weight_lb": (80, 320), "bmi": (15, 45), "age": (16, 70), "children": (0, 8), "bishop_meetings": (0, 6),
        "n_relationships": (0, 12), "n_breakups": (0, 8), "dates_30d": (0, 16), "rejections_recent": (0, 6),
        "app_hours": (0, 16), "n_friends": (0, 25), "n_close_friends": (0, 12), "new_friends_90d": (0, 8),
        "kids_wanted": (0, 10), "ideal_months_engaged": (0, 48), "max_older": (0, 20), "max_younger": (0, 20),
        "monthly_income": (0, 20000), "parental_support": (0, 5000), "savings": (-10000, 200000), "debt": (0, 150000),
        "rent": (0, 2500), "rent_burden": (0, 2), "commute_min": (0, 60), "dist_campus_km": (0, 30), "wage": (0, 80),
        "scripture_minutes": (0, 60), "social_media_hours": (0, 10), "soda_shop_week": (0, 8), "age_at_marriage": (17, 40),
        "n_memories": (0, 40), "plans_kept": (0, 100), "plans_abandoned": (0, 100), "n_acquaintances": (0, 600),
        "degree": (0, 600), "home_social_culture": (-3, 3), "dating_propensity": (0, 20), "social_events_month": (0, 30),
        "study_hours": (0, 50), "dates_total": (0, 200), "first_dates_total": (0, 60), "n_kissed": (0, 150),
        "n_ncmo": (0, 150), "n_sex_partners": (0, 60)}

BASIS_WORDS = {
    "survey": "The words along this scale are the survey's own answer options.",
    "guide": "The words along this scale are a reading guide written for this model scale; they are not measured.",
    "standard": "A standard score: the words say how far this is from the average person.",
    "amount": "Plain amounts.",
    "share": "A share, shown as a percentage.",
}

# Shares and probabilities: shown as percentages.
PERCENT = re.compile(r"(^|_)(rate|share|prob)($|_)|attend$")
PERCENT_DESC = re.compile(r"\b(share|probability|chance|rate) of\b|\bshare of\b", re.I)
PERCENT_IDS = {"expect_accept"}
NOT_SCALES = {"home_lon", "home_lat", "loc_lon", "loc_lat", "institute_class"}


@lru_cache(maxsize=1)
def _survey_levels() -> dict[str, list[str]]:
    """'<survey>.<item>' -> the answer wording for each code 0..k-1 (question metadata only, never responses)."""
    try:
        from .ingest.survey_spec import SPEC
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for survey, spec in SPEC.items():
        for entry in (spec.get("vars") or {}).values():
            if len(entry) >= 3 and entry[1] == "ord" and isinstance(entry[2], dict) and entry[2].get("levels"):
                for alias in {survey, survey.replace("-", "_"), survey.split("-")[0]}:    # copula names use short forms
                    out[f"{alias}.{entry[0]}"] = list(entry[2]["levels"])
    return out


def _levels_for(v) -> list[str] | None:
    if v.ordinal:
        return list(v.ordinal)
    m = re.match(r"\s*copula\s+([\w]+\.[\w]+)", v.init or "")
    if not m or "reversed" in (v.init or ""):
        return None
    lv = _survey_levels().get(m.group(1))
    if lv and v.range and v.range[0] == 0 and v.range[1] == len(lv) - 1:
        return lv
    return None


def _anchor(at: float, label: str, more: str | None = None) -> dict:
    d = {"at": float(at), "label": label}
    if more:
        d["more"] = more
    return d


def _from_tuples(rows) -> list[dict]:
    return [_anchor(*r) for r in rows]


def _even(lo: float, hi: float, words: list[str]) -> list[dict]:
    k = len(words) - 1
    return [_anchor(lo + (hi - lo) * j / k, w) for j, w in enumerate(words)]


def _survey_name(v) -> str | None:
    m = re.match(r"\s*copula\s+([a-z_]+)\.", v.init or "")
    return SURVEY_TITLE.get(m.group(1)) if m else None


def _how(v, kind: str, levels: list[str] | None = None) -> str:
    """One sentence on how the model measures the field."""
    if v.id in HOW:
        return HOW[v.id]
    fixed = v.id not in SURVEY_MOVES
    survey = _survey_name(v)
    if survey and "reversed" in (v.init or ""):
        return (f"From the {survey} survey's ranking of six partner qualities, turned around so 5 means ranked first; "
                "it stays as drawn.")
    if survey:
        tail = "it stays as drawn." if fixed else "the model then moves it as their life unfolds."
        if kind == "levels" and levels and v.id.startswith("fd_"):
            return (f"Each person starts with an answer to the {survey} survey's first-date idea “{v.label.split(': ')[-1]}” "
                    f"({levels[0]} … {levels[-1]}), drawn so answers go together as they did in the survey; {tail}")
        if kind == "levels" and levels:
            lab = v.label if v.label[:2].isupper() else v.label[0].lower() + v.label[1:]
            return (f"Each person starts with an answer to the {survey} survey's question on “{lab}” "
                    f"({levels[0]} … {levels[-1]}), drawn so answers go together as they did in the survey; {tail}")
        return (f"Each person starts with a value drawn from the {survey} survey, keeping how answers go together with "
                f"their other answers; {tail}")
    if kind == "z":
        parts = [w for w, hit in (("built from their other traits", "derived" in (v.init or "").lower()),
                                  ("matched to survey answers", re.search(r"copula|conditioned|self-rating", v.init or "", re.I)))
                 if hit]
        how = f" ({' and '.join(parts)})" if parts else ""
        return f"A standard score{how}: 0 is the average person, and most people fall between −2 and +2; it stays as drawn."
    prefix, _, concern = v.id.partition("_")
    if prefix == "cares" and concern in DRIVE_UNMET:
        noun = v.label.split("about ", 1)[-1].lower()
        frm = next((x.strip().rstrip(".") for x in re.split(r"(?<=\.)\s", v.desc or "") if x.startswith("From ")), "")
        frm = re.sub(r";\s*drifts slowly$", "", frm)
        return f"How much they care about {noun}" + (f", {frm[0].lower()}{frm[1:]}" if frm else "") + \
            "; it drifts slowly as their identity and life stage change."
    if prefix == "drive" and concern in DRIVE_UNMET:
        noun = v.label.split(": ", 1)[-1].lower()
        return (f"How much they care about {noun} times how unmet it feels right now ({DRIVE_UNMET[concern]}); the "
                "strongest drive becomes their top priority and steers free time, asks and reaching out.")
    first = _first_sentence(v.desc or "")
    if first:
        return first
    src = _composed_from(v)
    if v.kind == "state" and src:
        noun = "feeling" if v.domain == "social_emotion" else "state"
        return f"A {noun} the model composes from {src}."
    if v.id.startswith("fd_"):
        return "From the Dating survey's first-date ideas: how much they agree it would be a good first date."
    return "Tracked by the model."


def _first_sentence(d: str) -> str:
    """The first sentence of a description, without citations and range notes in parentheses."""
    d = re.sub(r"\s*\((?:[^()]*\b(?:et al|19\d\d|20\d\d)\b[^()]*|[−-]?\d+(?:\.\d+)?\s*(?:-|–|to)\s*\d+)\)", "", d.strip())
    if not d:
        return ""
    first = re.split(r"(?<=[.!?])\s+(?=[A-Z])", d, maxsplit=1)[0].strip()
    return first if first.endswith((".", "!", "?")) else first + "."


def _composed_from(v) -> str:
    """Plain list of the main inputs of the mechanisms that set this field (labels of the source variables)."""
    try:
        from .registry import get_registry
        reg = get_registry()
    except Exception:  # noqa: BLE001
        return ""
    labels: list[str] = []
    for m in reg.mechanisms_targeting(v.id):
        if m.system in ("whatif",) or m.id.startswith(("appraisal.", "whatif.")) or m.id.endswith(".intervention"):
            continue
        for s in m.sources:
            sv = reg.variables.get(s)
            if s == v.id or sv is None:
                continue
            lab = sv.label.split(" (")[0].lower()
            if lab not in labels:
                labels.append(lab)
    if not labels:
        return ""
    labels = labels[:5]
    return (", ".join(labels[:-1]) + " and " + labels[-1]) if len(labels) > 1 else labels[0]


def _unit(v, kind: str) -> str:
    if v.id in UNIT_BY_ID:
        return UNIT_BY_ID[v.id]
    if kind == "z":
        return "standard score (0 = average)"
    if kind == "levels":
        return "survey answer"
    if kind == "percent":
        return "percent"
    if v.units in UNIT_WORDS:
        return UNIT_WORDS[v.units]
    if v.units:
        return v.units
    lo, hi = (v.range or [None, None])[:2]
    if lo == 0 and hi == 1:
        return "0–1 model scale (not a percentage)"
    return "points"


def scale_of(v) -> dict | None:
    """The scale of a numeric person variable, or None:
    {min, max, unit, low, high, anchors: [{at, label, more?}], how, basis, view?, axis?, levels?, percent?, z?, note?}."""
    if (v.dtype in ("bool", "cat", "str") or v.categories or v.id.endswith(("_id", "_day", "_until")) or v.id in NOT_SCALES
            or not v.range):
        return None
    lo, hi = (v.range or [None, None])[:2]
    out: dict = {"min": lo, "max": hi}
    if v.units == "z":
        words = Z_WORDS.get(v.id)
        lows = [f"{words[0]}", f"{words[1]}", "average", f"{words[2]}", f"{words[3]}"] if words else \
            ["far below average", "below average", "average", "above average", "far above average"]
        anchors = [_anchor(z, w, Z_SHARE[z]) for z, w in zip((-2, -1, 0, 1, 2), lows)]
        out.update(z=True, low=lows[0], high=lows[-1], anchors=anchors, view=[-3, 3], basis="standard", unit=_unit(v, "z"),
                   how=_how(v, "z"),
                   note="A standard score: 0 is the average student; −1 and +1 are lower or higher than about 5 in 6 people; ±2 is rare.")
        return out
    levels = _levels_for(v)
    if levels:
        hand = ANCHORS.get(v.id)
        if isinstance(hand, list):
            anchors = _from_tuples(hand)
        elif len(levels) <= 7:
            anchors = [_anchor(lo + k, w) for k, w in enumerate(levels)]
        else:                       # long answer lists (income brackets): the ends and three between
            ks = sorted({0, len(levels) - 1, *(round(j * (len(levels) - 1) / 4) for j in (1, 2, 3))})
            anchors = [_anchor(lo + k, levels[k]) for k in ks]
        out.update(levels=levels, low=levels[0], high=levels[-1], anchors=anchors, basis="survey",
                   unit=_unit(v, "levels"), how=_how(v, "levels", levels),
                   note=f"Survey answer scale: {lo:g} = “{levels[0]}” … {hi:g} = “{levels[-1]}”. In-between values are averages or "
                        "drift between answers.")
        return out
    if lo == 0 and hi == 1 and (v.id in PERCENT_IDS or PERCENT.search(v.id) or PERCENT_DESC.search(v.desc or "")
                                or v.label.lower().endswith(" rate") or "mean attendance" in (v.desc or "")):
        hand = ANCHORS.get(v.id)
        anchors = _from_tuples(hand) if isinstance(hand, list) else _even(0, 1, ["0%", "25%", "50%", "75%", "100%"])
        out.update(percent=True, low=anchors[0]["label"], high=anchors[-1]["label"], anchors=anchors, basis="share",
                   unit=_unit(v, "percent"), how=_how(v, "percent"))
        return out
    hand = ANCHORS.get(v.id)
    if hand == "rank":
        anchors = [_anchor(0, "ranked last", "sixth of six"), _anchor(1, "5th of 6"), _anchor(2.5, "middle of the six"),
                   _anchor(4, "2nd of 6"), _anchor(5, "ranked first", "the quality they care about most")]
        basis = "survey"
    elif hand == "zplace":
        anchors = [_anchor(-2, "very quiet", "far quieter than most apartments"), _anchor(-1, "quieter than most"),
                   _anchor(0, "typical"), _anchor(1, "more social than most"),
                   _anchor(2, "the hangout spot", "far more social than most apartments")]
        basis = "standard"
    elif isinstance(hand, list):
        anchors = _from_tuples(hand)
        basis = "amount" if (v.units or v.id in UNIT_BY_ID) and v.id not in ("life_satisfaction", "memory_tone") else "guide"
    elif lo == 0 and hi == 1:
        prefix = v.id.split("_")[0]
        e0, e1 = ENDS.get(prefix, ("lowest", "highest"))
        if prefix == "cares":
            anchors = [_anchor(0, e0), _anchor(0.25, "matters a little"), _anchor(0.5, "matters"),
                       _anchor(0.75, "matters a lot"), _anchor(1, e1)]
        elif prefix == "drive":
            anchors = [_anchor(0, e0, "fulfilled, or doesn't matter to them"), _anchor(0.25, "a mild pull"),
                       _anchor(0.5, "a strong pull"), _anchor(0.75, "a very strong pull"),
                       _anchor(1, e1, "matters most and feels completely unmet")]
        else:
            anchors = [_anchor(0, e0), _anchor(0.25, "low"), _anchor(0.5, "moderate"), _anchor(0.75, "high"), _anchor(1, e1)]
        basis = "guide"
    else:                           # an amount without hand-written words: its ends and middle as numbers
        a, b = VIEW.get(v.id, (lo, hi))
        anchors = [_anchor(a, f"{a:g}"), _anchor((a + b) / 2, f"{(a + b) / 2:g}"), _anchor(b, f"{b:g}")]
        basis = "amount"
    if v.id in VIEW:
        out["view"] = list(VIEW[v.id])
    if v.id in LOG_AXIS:
        out.update(axis="log", log_c=LOG_AXIS[v.id])
    out.update(low=anchors[0]["label"], high=anchors[-1]["label"], anchors=anchors, basis=basis, unit=_unit(v, "num"),
               how=_how(v, "num"))
    if lo == 0 and hi == 1 and basis == "guide":
        out["note"] = f"0 = {out['low']}, 1 = {out['high']}. A model scale, not a percentage: read it with the words along " \
                      "the ruler and against other people."
    else:
        out["note"] = f"{anchors[0]['at']:g} = {anchors[0]['label']}, {anchors[-1]['at']:g} = {anchors[-1]['label']}."
    return out


# ------------------------------------------------------------------------------------------------ relationships
# The tie (edge) fields shown in the interface. Keys are EdgeStore columns; directed pairs share one scale.
EDGE_SCALES: dict[str, dict] = {
    "closeness": {"min": 0, "max": 1, "unit": "0–1 model scale", "basis": "guide",
                  "anchors": [(0, "not close", "barely know each other"), (0.3, "friend level", "friends need at least this"),
                              (0.5, "close-friend level", "close friends need at least this"), (0.75, "very close"),
                              (1, "as close as it gets")],
                  "how": "Grows with time together in leisure settings and with liking; fades without contact over months."},
    "liking": {"min": -1, "max": 1, "unit": "−1 to 1 model scale", "basis": "guide",
               "anchors": [(-1, "can't stand each other"), (-0.4, "dislike each other"), (0, "neutral"),
                           (0.4, "like each other", "close friends need at least this"), (1, "like each other a great deal")],
               "how": "An average of how their interactions felt, with recent ones counting more."},
    "trust": {"min": 0, "max": 1, "unit": "0–1 model scale", "basis": "guide",
              "anchors": [(0, "no trust"), (0.25, "wary"), (0.5, "some trust"), (0.75, "trusts them"), (1, "complete trust")],
              "how": "Grows slowly with good interactions; damaged by conflict, cheating and ghosting."},
    "conflict": {"min": 0, "max": 1, "unit": "0–1 model scale", "basis": "guide",
                 "anchors": [(0, "no recent conflict"), (0.25, "some friction"), (0.5, "real conflict"),
                             (0.75, "a lot of conflict"), (1, "constant conflict")],
                 "how": "Recent bad interactions, fading with time."},
    "attraction": {"min": -1, "max": 1, "unit": "−1 to 1 model scale", "basis": "guide",
                   "anchors": [(-1, "repelled"), (-0.5, "not attracted"), (0, "neutral"), (0.5, "attracted", "a crush"),
                               (1, "strongly attracted")],
                   "how": "One person's romantic attraction to the other: mostly specific to the pair, plus how attractive "
                          "most people find them; it grows or fades with dates and time together."},
    "belief": {"min": -1, "max": 1, "unit": "−1 to 1 model scale", "basis": "guide",
               "anchors": [(-1, "sure they're not interested"), (-0.5, "thinks they're not interested"), (0, "can't tell"),
                           (0.5, "thinks they're interested"), (1, "sure they're interested")],
               "how": "What one person believes the other's attraction to them is — a noisy read of each interaction, "
                      "mixed with their own feelings; asks, dates and kisses reveal much more."},
    "disclosure": {"min": 0, "max": 1, "unit": "0–1 model scale", "basis": "guide",
                   "anchors": [(0, "share nothing personal"), (0.25, "small talk"), (0.5, "share some real things"),
                               (0.75, "confide in each other"), (1, "share everything")],
                   "how": "Grows through warm contact between friends and support in hard times, fades without contact; it "
                          "decides how much of each other's real beliefs friends see."},
    "support": {"min": 0, "max": 5, "unit": "support exchanged (adds up)", "basis": "guide",
                "anchors": [(0, "none yet"), (0.5, "a little"), (1.5, "some"), (3, "a lot"), (5, "a great deal")],
                "how": "Adds up each time one of them, going through a hard stretch, reached out and the other was there."},
    "hurt": {"min": 0, "max": 1, "unit": "0–1 model scale", "basis": "guide",
             "anchors": [(0, "no hurt"), (0.25, "a sore spot"), (0.5, "hurt"), (0.75, "badly hurt"), (1, "deeply wounded")],
             "how": "Injury from serious conflict, betrayal or a breakup that hasn't been repaired; heals with warm contact."},
    "chemistry": {"min": -3, "max": 3, "unit": "standard score for the pair", "basis": "standard",
                  "anchors": [(-2, "clash"), (-1, "a poor fit"), (0, "ordinary"), (1, "click"), (2, "click unusually well")],
                  "how": "A fixed, pair-specific compatibility: two similar people can still clash and two different "
                         "people can click."},
    "familiarity": {"min": -10, "max": 5, "view": [-5, 3], "unit": "memory strength", "basis": "guide",
                    "anchors": [(-3.4, "about to be forgotten", "weak ties below this are dropped"), (-1.5, "a vague face"),
                                (0, "familiar"), (2, "very familiar")],
                    "how": "How available the person is in the other's memory: grows with each meeting, fades with time "
                           "(the ACT-R memory model)."},
    "hours": {"min": 0, "max": 10000, "view": [0, 400], "axis": "log", "log_c": 5, "unit": "hours", "basis": "amount",
              "anchors": [(0, "none"), (10, "10 hours"), (50, "50 hours", "about when people become casual friends"),
                          (90, "90 hours", "about when people become friends"),
                          (200, "200 hours", "about when people become close friends")],
              "how": "Hours they have spent together in any setting."},
    "hours_leisure": {"min": 0, "max": 10000, "view": [0, 400], "axis": "log", "log_c": 5, "unit": "leisure-equivalent hours",
                      "basis": "amount",
                      "anchors": [(0, "none"), (10, "10 hours"), (50, "50 hours", "about when people become casual friends"),
                                  (90, "90 hours", "about when people become friends"),
                                  (200, "200 hours", "about when people become close friends")],
                      "how": "Hours together weighted by setting (leisure counts fully, ward 0.6, class or work 0.3), "
                             "after Hall (2019)."},
    "dates": {"min": 0, "max": 1000, "view": [0, 100], "axis": "log", "log_c": 1, "unit": "dates", "basis": "amount",
              "anchors": [(0, "none"), (1, "one"), (5, "a few"), (20, "many"), (100, "a great many")],
              "how": "Dates they have been on together."},
    "shared": {"min": 0, "max": 30000, "view": [0, 300], "axis": "log", "log_c": 1, "unit": "days", "basis": "amount",
               "anchors": [(0, "none"), (3, "a few"), (20, "a good many"), (100, "many"), (300, "a great many")],
               "how": "Days with a shared experience (a party, a game, a hike, a date, family home evening) rather than "
                      "passing contact."},
    "stage": {"min": 0, "max": 4, "unit": "stage", "basis": "guide",
              "levels": ["strangers", "acquaintances", "casual friends", "friends", "close friends"],
              "anchors": [(0, "strangers"), (1, "acquaintances"), (2, "casual friends"), (3, "friends"), (4, "close friends")],
              "how": "Moves up with leisure hours together, liking and closeness (about 50, 90 and 200 hours, after Hall "
                     "2019) and back down when they drift apart."},
}
EDGE_ALIASES = {"attraction_lh": "attraction", "attraction_hl": "attraction", "belief_lh": "belief", "belief_hl": "belief"}


def edge_scale_of(v) -> dict | None:
    """The scale of a tie field (an EdgeStore column), or None."""
    key = EDGE_ALIASES.get(v.id, v.id)
    sc = EDGE_SCALES.get(key)
    if sc is None:
        return None
    out = {k: (list(x) if isinstance(x, tuple) else x) for k, x in sc.items() if k != "anchors"}
    out["anchors"] = _from_tuples(sc["anchors"])
    out["low"], out["high"] = out["anchors"][0]["label"], out["anchors"][-1]["label"]
    out["note"] = f"{out['anchors'][0]['at']:g} = {out['low']}, {out['anchors'][-1]['at']:g} = {out['high']}."
    return out


def scale_for(v) -> dict | None:
    """The scale of any registry variable (person or tie field)."""
    if v.entity == "person":
        return scale_of(v)
    if v.entity == "edge":
        return edge_scale_of(v)
    return None


def anchor_words(sc: dict, x: float) -> str:
    """The anchor words nearest to x (for captions)."""
    if not sc or not sc.get("anchors") or x is None:
        return ""
    best = min(sc["anchors"], key=lambda a: abs(a["at"] - x))
    return best["label"]
