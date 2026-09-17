---
name: shot-list
description: Write the shot list for a beat — 4 to 6 literal, filmable shots in the card's sector world, each with a Pexels phrasing and a Pixabay tag phrasing, plus a must-not list. Use for every scene that has no `shots`, after intake or on request.
---

# Shot list

A shot list turns what the viewer hears into what the camera sees. Stock engines only
find pictures they have words for, so every shot is a concrete noun phrase: a subject,
an action, a setting, a scale. Never a feeling, never a metaphor, never the beat's message.

## Inputs
Run `python3 tools/shot_list.py show <slug>` — prints every scene: id, spoken line,
brief, on-screen text, sector, lesson title, and whether shots already exist.
Then run `python3 tools/sectors.py <slug>` and write to THAT world and THAT never-list.
Never work from memory of the two original clients: `office` is built on the desks and
meetings `edenrise` bars, and a sector's own `seeds` in `sectors.json` show the house
phrasing for its standard beats.

## Rules
1. **Literal.** "A complaint is a gift" → "hotel receptionist listening calmly to an
   upset guest at the front desk". "Process becomes simpler" → "hands sorting loose
   screws into labelled jars on a workbench".
2. **In the sector's world.** Take it from `sectors.json`, never from habit — e.g.
   edenrise: land, garden, greenhouse, small repair, hands; belong: farmhouse hotel,
   reception, farm table, kitchen, Alentejo fields; office: desks, small meetings,
   whiteboards, one-to-ones; healthcare: bedside, ward handover, clinic reception.
   The same spoken line gets a different shot list in each sector — that is the point.
3. **Match the valence.** Negative lines get neutral or troubled frames; lines about
   being seen or thanked need a face; openers are warm establishing shots.
4. **Vary the scale.** Across the 4 to 6 shots: at least one wide establishing, one
   medium with people, one close-up of hands or objects.
5. **Two phrasings per shot.** `pexels`: a natural 4–8 word phrase ("receptionist
   listening to upset guest"). `pixabay`: 2–4 comma-free tag words ("hotel reception
   guest"). No brand names, no adjectives the engines cannot see ("calm", "dignified").
6. **Must-not list.** 3 to 8 concrete things that would be wrong for this beat, beyond
   the sector's standing never-list (e.g. "smiling crew" on a negative line).
7. **On-screen text is not a shot.** Diagrams and lists live in the composition; the
   shot list covers the footage behind or beside them.

## Output
Write one JSON file per lesson and apply it:

```json
{"S03": {"shots": [
   {"id": "A", "text": "hotel receptionist listening calmly to an upset guest at the front desk",
    "pexels": "receptionist listening to upset guest", "pixabay": "hotel reception guest", "scale": "medium"},
   {"id": "B", "text": "waiter at a farmhouse table apologising and writing a note", "pexels": "waiter taking note at table",
    "pixabay": "waiter table notebook", "scale": "medium"},
   {"id": "C", "text": "close-up of hands writing a guest comment into a logbook", "pexels": "hands writing in logbook",
    "pixabay": "hand writing notebook pen", "scale": "close"},
   {"id": "D", "text": "wide shot of a quiet farmhouse reception in morning light", "pexels": "small hotel reception morning",
    "pixabay": "guesthouse reception interior", "scale": "wide"}],
  "must_not": ["face masks", "corporate lobby", "angry shouting", "call centre headset"]}}
```

```
python3 tools/shot_list.py apply <slug> <file.json>
```
The tool validates (3–6 shots, both phrasings, scale ∈ wide|medium|close, must_not ≤ 8),
writes `shots`, `must_not`, `shots_by`, `shots_at` on each scene, and never touches clips.
Commit as `[intake-bot] shot lists: <slug>` (or with the intake commit).
