# Negative set: images with no person in them

Used by `02_Code/prahari/scripts/negative_person_check.py` (Phase 0 acceptance).
Every image here must produce **zero person detections and zero intrusion
alerts**. The script also always runs built-in synthetic negatives (walls, a
skin-toned wall, noise, a drawn face shape).

Add images of: empty rooms, walls, corridors, parked vehicles with nobody in
frame. Use only images you have the right to use. The images are git-ignored;
only this README is tracked.

    python scripts/negative_person_check.py --out ../../05_Output/experiments/phase0_negatives.json

Open question: the brief also lists "close-up faces" as negatives. A close-up
face is a real person, and YOLO correctly detects one (0.84 on a consented
team photo), so close-up faces are not included here until that criterion is
clarified.
