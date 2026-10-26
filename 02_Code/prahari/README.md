# PRAHARI

Statewide CCTV intelligence plane from Yushu Excellence Technologies Pvt. Ltd. Hybrid architecture: registry + GIS, unified viewing + ANPR, thin event bus. Central VMS recording is a later phase, not this tree.

PRAHARI **consumes live streams** (RTSP-TCP, HLS, WHEP) from the catalogue `GET /cameras.json` (session cookie). It does **not** download lab footage. `/stream/<id>` range-requests are not a dataset.

## Operator guide

1. `cd 02_Code/prahari` then `.\run.ps1`
2. Open http://127.0.0.1:8080
3. Sign in as `judge` / `JUDGE_PASSWORD` from `.env` (default in `.env.example` is `set-this-before-submit`; change before a hosted demo)
4. Operations: Gujarat map, coloured health pins
5. Vehicle Track: plate `GJ01AB1234` → Reconstruct → Download CSV
6. Alerts: CRITICAL stolen queue, Ack
7. Onboard: ANPR this still, Analyse this still (objects / own-feed faces), or Operator confirm
8. Analytics & Gaps: Dahod offline, short retention
9. Do not expect raw `rtsp://` in the browser; tiles are tokenised
10. `SENTINEL_HOST` empty is valid: sample cameras still run

## Run

```powershell
cd 02_Code/prahari
.\run.ps1
```

Copy `.env.example` to `.env` and set `JUDGE_PASSWORD`. Set `SENTINEL_HOST`, `SENTINEL_PASSWORD`, and `SENTINEL_RTSP_HOST` after catalogue login. The app still boots on sample cameras if those are empty.

Tesseract OCR (optional; confirm path covers the demo): `choco install tesseract` or the UB Mannheim installer, then ensure `tesseract` is on PATH.

Optional vision engines (torch). Default path needs no GPU. Histogram FRS, Tesseract ANPR, and IoU `track_id` are the no-GPU path. FaceNet, YOLO, and ByteTrack sit behind `FACE_ENGINE` / `OBJECT_ENGINE` / `ANPR_ENGINE` / `TRACK_ENGINE` when `requirements-vision.txt` is installed. Faces still run only on Own cameras. Person detection is YOLO only: without the vision extras no people are detected, rather than guessed.

## Live ingest

Force TCP when you open a lab camera yourself:

```
ffplay -rtsp_transport tcp rtsp://<host>:8554/stream/cam04
```

HLS on the TLS host needs the access cookie and a browser User-Agent. If 8554 is blocked, use HLS.

| Ingest rule | Code |
|---|---|
| RTSP over TCP | `app/services/capture.py`, `scripts/grab_frame.py` |
| No CAP_PROP_FPS timing | `app/services/sampler.py`, `capture.py` |
| Gaps are not disconnects | `StreamSession.read` |
| Backoff 2–30 s | `backoff_sleep` |
| Decode warnings non-fatal | logged in `capture.py` |
| Catalogue `/cameras.json` | `app/services/catalogue.py` |
| Mixed codecs/resolutions | per-camera fields |
| Scene cut at loop | `detect_scene_cut` |

WHEP preview is a documented link-out, not a full WebRTC stack in this tree.

## P1 / P4 real-data instrumentation

```powershell
.\.venv\Scripts\python.exe scripts\instrument.py all --seconds 8 --frames 6 --k-frames 6 --seed-n 24 --k 1 2 4
```

Writes `09_Research/results/real/` (registry, JSONL events, invocation A vs B, audit CSV, K-frontier, retrial note). Does not archive raw video. Live RTSP needs `SENTINEL_HOST`. A 24h MEASURED capture is `--hours 24`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\run_experiments.py --suite smoke
```

Logs: `../../05_Output/experiments/`. Live-catalogue suite SKIPPED if `SENTINEL_HOST` is empty.
