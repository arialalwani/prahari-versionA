# PRAHARI

**P**latform for **R**eal-time **A**lerts and **H**eterogeneous **A**sset **R**egistry **I**ntegration

A statewide CCTV intelligence plane from [Yushu Excellence Technologies Pvt. Ltd.](https://yushuexcellence.in/). One camera registry, one operations view, ANPR, object and intrusion analytics, a lawful enrolled-gallery face path on Own cameras, watchlist alerts, and multi-camera vehicle tracks. PRAHARI sits on top of the Video Management Systems that departments already run. It does not replace those systems.

**Repository:** https://github.com/amitduabits/PRAHARI  
**Company:** [yushuexcellence.in](https://yushuexcellence.in/)  
**Collaborator:** Amit Dua

| Artefact | File |
|---|---|
| High-level design | [PRAHARI_HLD.md](04_Documents/PRAHARI_HLD.md) |
| Stakeholder slides | [PRAHARI-Slides.pdf](04_Documents/PRAHARI-Slides.pdf) |
| Technical notes | [PRAHARI-Notes.pdf](04_Documents/PRAHARI-Notes.pdf) |
| TeX sources | [04_Documents/tex/](04_Documents/tex/) |

Build the PDFs from `04_Documents/tex` with `pdflatex slides.tex` and `pdflatex notes.tex`.

---

## Why this design

Departments operate independent CCTV estates across about 1,000 km. Vendors, retention (7 vs 15 days), analog and IP, cloud and local NVR all differ. Watchlists already exist (VAHAN, SARTHI, eGujCop, AFIS, NAFIS) and are unused by the cameras that could match them. There is no statewide camera census.

PRAHARI is a hybrid intelligence plane:

| Layer | Stance |
|---|---|
| Camera census, GIS, health, gap analysis | Built |
| Unified viewing and ANPR on reachable streams | Built |
| Detection-event bus, watchlist match, cross-camera track | Built |
| Central VMS recording of every frame | Roadmap, selected cameras only |

A new departmental VMS is one adapter (RTSP / HLS / WHEP / ONVIF). The detection JSON does not change if the bus later becomes Kafka.

---

## What the running platform does

1. Onboards government and private-permitted cameras (CSV, form, REST, catalogue sync).
2. Plots them on a Leaflet map of Gujarat with health colouring.
3. Opens up to four tokenised live tiles (HLS or own-feed file). Raw RTSP never reaches the browser.
4. Runs ANPR on a still or a 1 fps sampled stream. Indian plates are normalised to `^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$`.
5. Matches plates in O(1) against a representative watchlist. Stolen / wanted raises a CRITICAL alert. Same plate + same camera within 120 s collapses to one card with a counter.
6. Reconstructs a designated vehicle path (`GET /api/track/{plate}`) and exports CSV.
7. Runs object detection and godown ROI intrusion. Lawful face matching runs only on Own cameras against an enrolled gallery.

Seeded demonstration plate: **GJ01AB1234** (watchlist category STOLEN), six cameras Valsad to Gandhinagar. Live catalogue hits append to the same track.

---

## Repository layout

```
PRAHARI/
  README.md                          this file
  LICENSE                            proprietary licence
  01_Overview/                       product brief
  02_Code/prahari/                   runnable application
  03_Data/samples/                   cameras.csv, watchlist.csv, seeded detections
  03_Data/sentinel_catalogue/        catalogue schema and fixture
  04_Documents/                      HLD, slides, notes
  05_Output/deliverables/            track CSV and operator artefacts
  docs/                              GitHub Pages index
```

Application source lives only under `02_Code/prahari/`.

---

## Stack

| Piece | This tree | Later swap |
|---|---|---|
| API | FastAPI + Uvicorn | same contract |
| UI | Leaflet + vanilla JS | React if needed |
| Store | SQLite | PostgreSQL + PostGIS |
| Capture | OpenCV + FFmpeg, RTSP over TCP | DeepStream on regional GPUs |
| ANPR | OpenCV morphology + Tesseract | YOLO plate detector + PaddleOCR behind `recognize()` |
| Objects | OpenCV blob / optional YOLO | YOLO11 on regional GPUs |
| Faces | Histogram gallery / optional FaceNet | dedicated FRS cameras, human confirm |
| Alerts | in-process WebSocket | Redis / Kafka |
| Auth | HTTP Basic + signed cookie | department SSO |

Do not introduce Kafka, Kubernetes, or Ceph in this tree.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | 3.11 used in development |
| pip | `run.ps1` / `run.sh` create a venv |
| Tesseract OCR | Optional. Without it, use **Operator confirm** so a readable plate still produces a detection row. Windows: [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) or `choco install tesseract`, then put `tesseract` on PATH. |
| FFmpeg | Optional. Needed only to remux live RTSP into HLS tiles. |
| VLC or ffplay | Optional. Manual TCP check: `ffplay -rtsp_transport tcp rtsp://<host>:8554/stream/<id>` |

Hardware for the laptop PoC: any recent Windows or Linux machine. A GPU is not required.

---

## Quick start

```powershell
git clone https://github.com/amitduabits/PRAHARI.git
cd PRAHARI\02_Code\prahari
copy .env.example .env
# edit .env: set JUDGE_PASSWORD and SECRET_KEY before any public demo
.\run.ps1
```

Linux / macOS:

```bash
git clone https://github.com/amitduabits/PRAHARI.git
cd PRAHARI/02_Code/prahari
cp .env.example .env
chmod +x run.sh
./run.sh
```

Open http://127.0.0.1:8080

Sign in as `judge` / value of `JUDGE_PASSWORD` (default in `.env.example` is `set-this-before-submit`; change it before a hosted demo).

| User | Role | Sees |
|---|---|---|
| `judge` | soc_operator | all cameras, ack, confirm, sessions |
| `admin` | superadmin | all |
| `home.viewer` | dept_viewer, department Home | Home cameras only; no private-permitted mall |
| `auditor` | auditor | GET only |

---

## Operator walkthrough

1. Operations: Gujarat map, health-coloured pins. Dahod GSRTC is seeded offline on purpose.
2. Click a pin, Open tile (own-feed needs `03_Data/recordings/own_feed.mp4`; without that file the tile states the gap honestly).
3. Vehicle Track: plate `GJ01AB1234` then Reconstruct. Download CSV.
4. Alerts: CRITICAL queue for the stolen plate. Ack writes an audit row.
5. Onboard: upload a still for ANPR, or Operator confirm `GJ01AB1234`.
6. Analytics and Gaps: short-retention Food and Civil Supplies cameras, Dahod offline.

---

## Configuration (`.env`)

Copy from `.env.example`. Never commit `.env`.

| Key | Default | Meaning |
|---|---|---|
| `APP_HOST` / `APP_PORT` | 127.0.0.1 / 8080 | Bind address |
| `JUDGE_PASSWORD` | set-this-before-submit | SOC operator login |
| `SECRET_KEY` | change-me | Cookie and stream-token HMAC |
| `SENTINEL_HOST` | empty | Lab catalogue host after login |
| `SENTINEL_CATALOGUE_PATH` | `/cameras.json` | Live catalogue path |
| `SENTINEL_PASSWORD` | empty | Catalogue access password; never commit |
| `SENTINEL_RTSP_HOST` | empty | Public RTSP IP |
| `RTSP_TRANSPORT` | tcp | Forced in every capture client |
| `RECONNECT_MIN_S` / `RECONNECT_MAX_S` | 2 / 30 | Backoff |
| `MAX_OPEN_CAPTURES` | 4 | Pace load; fifth session is rejected |
| `ANPR_MIN_CONFIDENCE` | 0.35 | Drop junk OCR |
| `ANPR_ENGINE` | tesseract | Set `yolo` only when that engine is wired |
| `FACE_ENGINE` | histogram | Set `facenet` only with vision extras |
| `OBJECT_ENGINE` | yolo | Person detection, YOLO only. Any other value turns it off |
| `TRACK_ENGINE` | iou | Set `bytetrack` only with vision extras |
| `DB_PATH` | data/prahari.db | SQLite file |
| `CROP_DIR` | data/crops | Plate crops |

If `SENTINEL_HOST` is empty, `POST /api/cameras/sync-catalogue` returns HTTP 400 with that fact. Sample cameras still load.

---

## Camera grid

Every live camera is an RTP/RTSP stream. One second of video takes one second to arrive. There is no file download. `/stream/<id>` answers range requests for a player; `curl`/`wget` of that path is not a dataset.

| Protocol | Pattern | Use in PRAHARI |
|---|---|---|
| RTSP | `rtsp://<host>:8554/stream/<id>` | Inference (`StreamSession`, TCP) |
| WHEP | `http://<host>:8889/stream/<id>/whep` | Documented; not a full WebRTC stack in this tree |
| HLS | `http://<host>/live/stream/<id>/index.m3u8` | Dashboard tiles; fallback if 8554 is blocked |

Catalogue `GET /cameras.json` (after password login) is the live contract. Camera ids change. Do not invent ids. `/api/ingest` is 404 on the lab host.

Ingest rules encoded in `app/services/capture.py` and `tests/test_integrator_laws.py`:

- RTSP over TCP always (`OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp` before `import cv2`).
- Event time is PTS (`CAP_PROP_POS_MSEC`), never packet arrival time and never the declared frame rate.
- Inter-frame gaps are not treated as a disconnect.
- Reconnect backoff starts at 2 s and caps at 30 s.
- Decoder warnings at join (`Error constructing the frame RPS`) are logged, not fatal.
- Mixed H.264 / H.265 and mixed resolutions; buffers come from catalogue fields.
- Feeds loop; a PTS rewind or gap above 5 s is a scene cut.
- Consume only. No publish, no gateway control API.

After login, set `SENTINEL_HOST` and call `POST /api/cameras/sync-catalogue` (as `judge` or `admin`). Probe sequentially. Do not open all live RTSP sessions at once.

---

## HTTP API (port 8080)

`/api/health` is public. Everything else requires login (HTTP Basic or session cookie).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Process + counts + whether catalogue host is set |
| POST | `/api/login` | Sets `prahari_session` cookie |
| GET | `/api/me` | Current user |
| GET/POST | `/api/cameras` | Registry list / manual onboard |
| POST | `/api/cameras/import` | CSV multipart |
| GET | `/api/cameras/export.csv` | Census export |
| POST | `/api/cameras/sync-catalogue` | Pull `/cameras.json` |
| GET | `/api/cameras/{id}` | One camera; playback token, never raw RTSP |
| POST/DELETE | `/api/sessions` | Open/close a tile (max 4) |
| GET | `/api/stream/{id}?token=` | File or HLS proxy |
| POST | `/api/ingest/frame` | Still image ANPR |
| POST | `/api/ingest/analyse` | Multi-engine still |
| POST | `/api/ingest/confirm` | Operator override |
| GET | `/api/detections` | Filter by plate / camera |
| GET/POST/DELETE | `/api/watchlist` | Representative watchlist; `WL-001` cannot be deleted |
| POST | `/api/faces/enroll` | Enrolled gallery |
| GET | `/api/faces/gallery` | Ids and counts, never embeddings |
| GET | `/api/alerts` | Open queue |
| POST | `/api/alerts/{id}/ack` | Operator ack, audited |
| WS | `/ws/alerts` | Push on new CRITICAL/HIGH |
| GET | `/api/track/{plate}` | Chronological GIS points |
| GET | `/api/track/{plate}/report.csv` | Operator artefact |
| GET | `/api/predict/{plate}` | Next-camera frequency + distance |
| POST | `/api/query` | Keyword filter (`engine=keyword_rules`) |
| GET | `/api/gap-report` | Offline, short retention, missing coords |
| GET | `/api/audit` | superadmin and auditor |

Detection event fields are frozen: `event_id`, `plate`, `plate_raw`, `confidence`, `camera_id`, `lat`, `lon`, `ts`, `pts_ms`, `crop_uri`, `category`, `priority`, `source_case_id`. Additive fields: `entity_type`, `face_id`, `object_class`, `source`.

---

## Tests

From `02_Code/prahari`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\run_experiments.py --suite smoke
```

Expect the suite green. One test skips if the Tesseract binary is missing; `POST /api/ingest/confirm` still inserts a real detection row. Experiment logs: `05_Output/experiments/EXPERIMENT_LOG.md`. Live-catalogue suite SKIPPED if `SENTINEL_HOST` is empty.

---

## Documents

- High-level design: [`04_Documents/PRAHARI_HLD.md`](04_Documents/PRAHARI_HLD.md)
- Sample track CSV: [`05_Output/deliverables/track_GJ01AB1234.csv`](05_Output/deliverables/track_GJ01AB1234.csv)

Statewide bandwidth and cost figures in the HLD are **design targets** for an intelligence plane of about 45,000 public-domain cameras at 1 fps, five regional GPU sites, roughly ₹5–6 Cr per year. They are not a quote to replace 26 VMS contracts, and they are not measured laptop throughput.

---

## Security and privacy

- Roles: `superadmin`, `soc_operator`, `dept_viewer`, `auditor`.
- Stream URLs are short-lived HMAC tokens (60 s). RTSP is not shipped to the browser.
- Private-permitted cameras require `consent=true` or onboard is rejected.
- Face matching runs only on Own cameras against an enrolled gallery of consented adults or synthetic fixtures. It is not AFIS, not NAFIS, and not a live ministry biometric pipe. Government CCTV of unknown people is refused.
- Audit rows: onboard, watchlist edit, alert ack, report download, operator confirm. Stream URLs are not stored in audit detail.
- Raw lab video is consumed live and not archived as files.

Change every default password before a hosted URL is shared.

---

## Contact

Yushu Excellence Technologies Pvt. Ltd.  
Amit Dua  
https://yushuexcellence.in/  
mail.amitdua@gmail.com  
+91-9521752333
