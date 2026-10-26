# Printed faces: a documented test, not a gate

Faces that are not people: posters, billboards, printed photos on walls, faces
on phone or laptop screens. A person detector can fire on these. This folder
records what PRAHARI's detector does with them.

    python scripts/printed_face_check.py --out ../../05_Output/experiments/printed_faces.json

This is **not** a pass/fail check and **not** a suppression rule. Nothing is
filtered out because of these results; they are documented so operators and
reviewers know the behaviour. They are kept out of the Phase 0 negative set,
which is scenes with no humans only.

## Recorded result (YOLOv8n, 26 Oct 2026)

| Image | Person detections | Intrusion if a zone covered it |
|---|---|---|
| `poster.webp`: missing-person poster on a pole, street scene, no one in frame | 1 (0.62, on the poster photo) | Yes |

**What it means:** a printed face can be detected as a person and, inside a
restricted zone, could raise an intrusion alert. A human review step (Phase 2
review queue) and zone placement that avoids posters and screens are the
mitigations, not a filter.

## Rules for images here

Images are git-ignored; only this README is tracked. `poster.webp` is a
watermarked stock photo of a real missing-person poster: use it for local
testing only, never in a demo, screenshot or commit. Replace it with posters or
screens you photograph yourself before sharing any results that show images.
