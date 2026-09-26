# ANPR test set

Drop images into the tier folders, then add one row per image to `ground_truth.csv`.

    filename,plate,tier
    easy/car1.jpg,GJ01AB1234,easy
    hard/angled2.jpg,GJ27XY0001,hard
    negative/wall.jpg,,negative

Leave `plate` empty for negative cases — images with no vehicle, no plate, or
non-plate text such as shop signage. Returning any plate for those is a false
positive, and a wrong plate is worse than no plate.

Type the plate exactly as a human reads it: uppercase, no spaces or dashes.

Suggested minimum: 5 easy, 5 hard, 2 negative. More is better, but the
before/after comparison works with any number.

    python scripts/anpr_benchmark.py --save baseline.json     # before a change
    python scripts/anpr_benchmark.py --compare baseline.json  # after

## Images are not in the repository

The real photos listed in `ground_truth.csv` are third-party images showing real
registration plates, so they are kept out of version control. Only
`easy/fixture_synthetic.jpg` (a generated plate) is published. To reproduce the
benchmark, supply your own images and list them in `ground_truth.csv`.
