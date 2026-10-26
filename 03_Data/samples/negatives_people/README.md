# Negative set: images with no person in them

Used by `02_Code/prahari/scripts/negative_person_check.py` (Phase 0 acceptance).
Every image here must produce **zero person detections and zero intrusion
alerts**. The script also always runs built-in synthetic negatives (walls, a
skin-toned wall, noise, a drawn face shape).

Add images of: empty rooms, walls, corridors, parked vehicles with nobody in
frame. Use only images you have the right to use. The images are git-ignored;
only this README is tracked.

    python scripts/negative_person_check.py --out ../../05_Output/experiments/phase0_negatives.json

**Scenes with no humans only.** A close-up face is a real person and is
correctly detected (0.84 on a consented team photo), so it does not belong
here. Printed faces (posters, phone or laptop screens) are a separate
documented test: see `../printed_faces/README.md` and
`scripts/printed_face_check.py`.
