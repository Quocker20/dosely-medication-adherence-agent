# Graded Adherence Response

**Dosely · Feature proposal · Awaiting approval**

Today the platform has one way to react when a patient stops taking their
medication: page a doctor. This proposal adds the steps in between — and uses
a language model to explain *why* a patient is struggling, without ever
letting it decide how urgent that patient is.

---

## The problem: one volume knob

The system currently detects two adherence problems, and both produce the
same maximum-severity response — a red alert to the doctor. A patient who
misses three doses of a cholesterol tablet triggers exactly what a patient
who misses three doses of a blood thinner triggers.

Everything below that bar produces nothing at all. A patient sliding from 90%
adherence to 55% over two weeks is invisible until they hit a three-dose
streak. The database already reserves a lower-severity `WARNING` alert type
for exactly this purpose; no code has ever created one.

The result is predictable in both directions: doctors get paged for things
that did not need a page, and get nothing for patients who are quietly
deteriorating.

| | |
|---|---|
| **Detection rules today** | 2 — missed-dose streak, severe symptom on a survey |
| **Severity levels produced** | 1 — red alert. Nothing quieter exists |
| **Distinction by drug risk** | None — a vitamin and a blood thinner alert identically |
| **Explanation given to doctor** | None — the count, with no indication of cause |

---

## The proposal: rules decide how loud, the model explains why

Every night, the system reviews each patient once. Deterministic rules —
ordinary code, no AI — score how serious that patient's adherence situation
is and assign one of four levels. Most patients score *none* and the review
stops there.

Only patients who fail a real rule are passed to the language model, and the
model is asked a narrower question than "is this bad?" — it is asked *what
kind of problem is this?* It picks one cause from a fixed list of six and
writes a short explanation citing the numbers it was given. It cannot change
the severity the rules already assigned.

The severity determines who is told and how urgently. The cause determines
what the message says. A patient missing every evening dose of one drug, who
also reported nausea, produces a different message from a patient missing
doses at random across all their medications — even when both sit at the
same adherence percentage.

---

## How one nightly review runs

**Stage 1 · Database — measure the patient.**
One query per patient produces two separate packages of numbers, answering
two different questions.

**Package A (→ rules): how bad is it?**
- Adherence rate over the window
- Week-over-week trend
- Longest run of missed doses
- How many missed doses were high-risk drugs

**Package B (→ model): what kind of problem is it?**
- Which time of day is missed
- Which medication is missed
- Deliberately skipped vs. silently missed
- Snooze count and lateness pattern
- Symptoms reported on health surveys

**Stage 2 · Deterministic code — assign severity** (none / mild / moderate /
severe). Plain thresholds, no AI. Reproducible and auditable: the same
numbers always produce the same level, and the level does not change when a
model version changes. Patients with too little dose history to judge are
excluded rather than guessed at.

> **Gate.** Scored *none* → review ends. No alert, no message, no model call.
> This is the majority of patients on any given night. Everyone else
> continues, with package B.

**Stage 3 · Language model — classify the cause and write the explanation.**
Receives the already-fixed severity and package B. Returns one cause from a
fixed list, a short explanation for the doctor citing the specific numbers,
and — only where the severity routes to the patient — a plain-language
nudge.

**Stage 4 · Stored history — check how long this has been going on.** A
patient stuck at the same level for five nights despite reminders is a
different problem from one who dropped there yesterday. Escalation is driven
by non-response, not by badness alone — which is only possible because each
night's review is recorded.

**Stage 5 · Action — notify the patient, warn the doctor, or page the
doctor.** Severity and days-at-that-level pick the channel. The cause picks
the wording.

---

## The safety question: who is allowed to decide what

This is a clinical product, so the important question is not what the AI
does but what it is structurally prevented from doing. Authority is split
three ways, and the split is enforced by the shape of the system rather than
by instructions in a prompt.

### Deterministic rules — code, no AI
**Decides:**
- How serious this patient is
- Whether anyone is told at all
- Whether the doctor is paged
- Whether the model is called

**Cannot:** explain a cause, or write anything a human reads.

### Language model — constrained output
**Decides:**
- Which of six causes best fits
- A short explanation, citing the numbers it was given
- A plain-language nudge for the patient, where routed

**Cannot:** change severity, invent an action outside the fixed list, reach a
patient the rules did not route to it, or alter any prescription, schedule
or dose.

### Doctor — human in the loop
**Decides:**
- Every clinical decision, unchanged
- Whether to act on an alert
- Prescription and dosage changes

**Unchanged by this feature.** No clinical authority moves anywhere. The
feature only changes what reaches the doctor's attention and when.

Two consequences worth stating plainly. First, because severity is computed
before the model runs and cannot be revised by it, a model that misreads a
case produces a wrong *explanation*, never a wrong *urgency* — a doctor
reading a mistaken cause still sees a correctly-graded case. Second, every
review stores the numbers that produced its level, so any alert can be
reconstructed after the fact.

---

## The six causes: a fixed list, including permission to say "unclear"

| Cause | Recognised by | Points toward |
|---|---|---|
| **Timing mismatch** | Misses concentrate in one time slot | Adjusting the schedule to the patient's real day |
| **Suspected side effect** | Misses concentrate on one drug, with symptoms reported | Doctor reviewing that specific medication |
| **Deliberate refusal** | Patient actively marks doses as skipped | A conversation, not a louder reminder |
| **Disengagement** | Doses missed silently, no pattern, no symptoms | Re-engagement, caregiver involvement |
| **External disruption** | Sudden drop with no prior history | Likely temporary — travel, illness, hospitalisation |
| **Unclear** | Nothing dominates | Honest uncertainty instead of a plausible guess |

The last one matters more than it looks. Without an explicit way to decline,
a language model asked for a cause will always produce one — and a
confident, fabricated explanation shown to a doctor is worse than no
explanation at all.

---

## Escalation: what happens, and when

Mild cases are handled with the patient first; the doctor is only brought in
if that does not work. Severe cases go straight to the doctor. The day
counts below are a starting point, to be tuned once we can see real volumes.

| Severity | First night | Still there day 3 | Still there day 5+ |
|---|---|---|---|
| **Mild** | patient nudge | patient nudge | doctor warning |
| **Moderate** | patient nudge + doctor warning | doctor warning | doctor warning |
| **Severe** | doctor alert | doctor alert | doctor alert |

A patient whose adherence improves drops out of the ladder and receives
nothing. Silence is the correct response to someone getting better.

---

## High-risk medication: the immediate path stays immediate

A nightly cycle is right for analysing a slow-moving trend, but wrong for a
patient who has just missed their third consecutive dose of a blood thinner.
Waiting until morning for that is not acceptable.

So prescriptions gain a way for the prescribing doctor to mark individual
medications as high-risk. The existing every-fifteen-minutes check survives,
but narrowed: it pages a doctor only for a missed streak on a medication the
doctor themselves flagged. Everything else moves to the nightly review.

One honest note: the flag defaults to off, so this fast path covers nobody
on the day it ships and grows as doctors begin using it. If uptake is poor
we can seed defaults from the medication catalogue — but we should measure
before building that.

---

## What changes in practice

### For the doctor
- Stops being paged for missed doses of low-risk medication
- Gains a quieter warning tier for patients worth watching but not worth interrupting for
- Each alert names a likely cause and cites the numbers behind it, instead of reporting a count
- Patients needing attention still sort to the top of the dashboard — the ordering is being changed so warnings cannot bury genuine alerts

### For the patient
- Hears from the app before their doctor is involved, where the situation allows it
- Messages are specific — "you often miss your evening dose" rather than "your adherence is low"
- Nothing is sent at night; patient messages are held for daytime hours
- No message contains clinical advice, dosage guidance, or anything that reads as a diagnosis

---

## Scope: what this feature does not do

- **It does not change any prescription.** No dose, schedule, or medication is altered by this system. Suggestions go to people; people act.
- **It does not reschedule automatically.** Where a timing problem is identified, the outcome is a suggestion that the patient or doctor chooses to act on.
- **It does not give medical advice.** Patient-facing text is limited to reminders and prompts to talk to their doctor.
- **It does not run in real time.** Adherence is a trend measured over a week; analysing it continuously would produce noise, not insight.
- **It does not remove the existing safety net.** Severe-symptom alerts and high-risk missed-dose alerts continue to fire immediately.

---

## Risks: what could go wrong, and what contains it

| Risk | Containment |
|---|---|
| **Alert fatigue** | The failure mode that kills features like this — and it is dangerous here, because ignored warnings share a channel with genuine emergencies. Contained by the escalation ladder, a cooldown per patient, severity-weighted dashboard ordering, and starting with conservative thresholds. |
| **The model invents a cause** | It can only pick from six, must cite the numbers it was given, and has an explicit "unclear" option. Because severity is already fixed, a wrong cause never becomes a wrong urgency. |
| **Patient-facing tone** | The lowest-severity tier carries the highest product risk: badly worded, patients mute notifications and lose the dose reminders that already work. Message templates get reviewed before launch; nothing is sent outside daytime hours. |
| **Model cost** | Only patients failing a rule reach the model — one call each, at most once a night. A hard cap per run, ordered by severity, bounds the worst case and reports when it is hit. |
| **Thresholds set wrong** | Near-certain on the first attempt. Doctors' responses to alerts are recorded from day one, so tuning is done against evidence rather than opinion. |
| **New alerts silently dropped from the live feed** | The doctor dashboard's realtime channel now re-checks every event against the doctor-patient relationship before delivery, and discards anything without a patient identifier attached. New alert events from this feature must carry that identifier or they will never reach a connected doctor's screen — a requirement, not an assumption, confirmed against the current codebase. |

---

## Build: roughly two weeks, in a useful order

Five workstreams. The order matters: the first two deliver a working
graded-alert system *with no AI involved at all*. If the model step were
dropped entirely, that foundation still solves the original problem — it
simply produces generic messages instead of explained ones.

| Workstream | Delivers | Size |
|---|---|---|
| **1 · Measurements** | The new database queries behind both number packages | 2 days |
| **2 · Rules and escalation** | Severity levels, the ladder, the stored review history | 2–3 days |
| **3 · Model step** | Cause classification and explanation text | 2 days |
| **4 · Nightly job and delivery** | The batch run, alerts, patient messages, daytime gating | 2 days |
| **5 · High-risk flag** | Prescription marking, narrowed fast path, dashboard ordering fix | 2 days |
| **Testing and tuning** | Validation, first-week threshold adjustment | 2–3 days |

Estimate assumes one backend engineer and no change to the existing
prescription or scheduling logic, which this feature reads but never writes.

---

## Status: settled, and still to settle

### Decided
- **Rules alone assign severity.** The model classifies cause only and cannot revise urgency.
- **Six fixed causes**, including an explicit "unclear" so the model can decline rather than fabricate.
- **One review per patient per night**, at most one model call each. Specific medications and times are named inside the message, not split into separate alerts.
- **Escalation is driven by non-response**, which requires storing each night's review.
- **Doctors flag high-risk medications**; the immediate alert path is narrowed to those, and the general missed-streak page is retired.
- **Doctor responses are recorded** from launch, so thresholds can be tuned against outcomes.
- **Dashboard ordering becomes severity-weighted**, so the new warning tier cannot bury genuine alerts.

### Open — to be tuned with real data
- **Exact severity thresholds.** Starting from the percentage bands already used on the doctor dashboard, so the numbers stay consistent across screens.
- **Escalation spacing.** The day 1 / 3 / 5 ladder is a starting point.
- **Run time and daytime window** for holding patient messages.
- **Per-night model call cap.**
- **Which health-survey fields** are passed to the model as symptom evidence.

---

## The ask

Approval to build as described — specifically, approval of the authority
split: that deterministic code decides urgency and routing, that the
language model is confined to classifying a cause from a fixed list and
writing explanatory text, and that no clinical authority moves away from the
doctor.

The open items above are tuning decisions that need real data to answer
well; they do not change the shape of the system and can be settled during
the first week of operation.
