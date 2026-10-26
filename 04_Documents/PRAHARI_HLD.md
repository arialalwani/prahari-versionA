# PRAHARI High-Level Design
**Yushu Excellence Technologies Pvt. Ltd.**  
Collaborator: Amit Dua · https://yushuexcellence.in/  
Architecture: **hybrid intelligence plane** (registry + GIS, unified viewing + ANPR, thin event bus)  
PoC target: seeded registry plus live catalogue cameras  
DESIGN TARGET: ~80,000 statewide cameras. MEASURED PoC is the seeded registry plus live catalogue sync.

Working tree: `02_Code/prahari/`

---

## 1. Problem reading (what we are not building)

Departments already own VMS, AMC contracts, NVRs and storage. Replacing them in a first deployment is neither feasible nor cost-effective. A central VMS ingesting every frame for 15 days would require statewide dark fibre, petabytes of hot storage and a GPU farm this PoC does not claim.

PRAHARI therefore **does not rip and replace**. It adds a statewide intelligence plane on top of what already exists.

## 2. Chosen model and justification

| Layer | Why |
|---|---|
| Camera census, GIS, health, gap analysis | Zero disturbance to departmental VMS. Unlocks planning immediately. |
| Unified viewing + ANPR on accessible streams | Direct RTSP / ONVIF / HLS / WHEP on cameras the department already paid for. |
| Event / metadata bus, correlation, alerts | Watchlist matching and cross-camera tracks without a federation SDK zoo. |
| Central recording + full VMS | Roadmap, selected cameras only, not all 80k (DESIGN TARGET). Not faked in this PoC. |

This is vendor-neutral: adapters speak open protocols. A new VMS is one connector, not a redesign.

## 3. Logical architecture

```
Dept VMS / NVR / raw camera / private-permitted RTSP
        │  RTSP-TCP · HLS · WHEP · ONVIF · vendor API
        ▼
┌───────────────────────────────────────────┐
│  Ingest adapters + stream session control │  viewing layer
└─────────────────────┬─────────────────────┘
                      │ 1 fps sampled frame (not 25 fps video)
                      ▼
┌───────────────┐    ┌─────────────────────┐
│ Registry+GIS  │    │ analyse(): ANPR +   │
│ PostGIS later │    │ objects + lawful FRS│
└───────┬───────┘    └──────────┬──────────┘
        │                       │ detection event
        │                       ▼
        │            ┌─────────────────────┐
        └────────────┤ Event bus (Redis/   │  event layer
                     │ Kafka statewide)    │
                     └──────────┬──────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
        Watchlist           Vehicle path      Alert / SOC
        matcher             store             dashboard
        VAHAN/SARTHI        GIS replay        RBAC + audit
        eGujCop/AFIS
```

PoC implementation uses SQLite + in-process WebSocket instead of Kafka. The contract (detection event JSON) is the same object that would go on Kafka later.

## 4. Heterogeneous onboarding

Each camera record carries: id, department, owner (Gov / private-permitted), lat/lon, protocol, URL, retention, type, health.

Onboarding paths:
1. Bulk CSV / Excel (Model 1 deliverable).
2. Manual form for a single node.
3. REST API for departmental inventory systems.
4. Sentinel sandbox endpoints published as RTSP / WHEP / HLS.

If RTSP/UDP dies across NAT (official Integrator Guide), the adapter retries with `rtsp_transport=tcp`, then HLS. Health probe flips the pin red after 3 failures.

Private society / mall cameras are first-class rows with `ownership=Private-Permitted` and a legal-consent flag. They never land in a public viewer role.

## 5. Video path and bandwidth math (80k DESIGN TARGET)

Full-HD 25 fps everywhere is the wrong design.

Numbers in this section are **DESIGN TARGET** (statewide intelligence plane), not MEASURED PoC throughput. The laptop PoC camera count is MEASURED from the seeded registry (11 rows) plus any catalogue sync.

Assumption used in cost model (DESIGN TARGET):
- 80,000 cameras
- Only **public-domain + checkpoint** cameras (assume 45,000) run analytics
- Analytics uses **1 frame per second**, 720p JPEG crop ~80 KB
- Metadata event ~500 bytes

Edge / regional worker traffic for analytics:

`45,000 × 80 KB × 1 fps ≈ 3.6 GB/s peak` if naively centralised.

With regional aggregation (5 regions: Ahmedabad, Surat, Rajkot, Vadodara, Bhuj):

`3.6 GB/s / 5 ≈ 720 MB/s per regional GPU site`. Feasible on existing SWAN / GSWAN plus leased wavelengths.

Control-room operators do **not** pull 45k live streams. They pull:
- a video wall of 16–64 selected cameras via HLS/WebRTC
- metadata + crops for everything else

Low-bandwidth sites (Dahod, border outposts): on-camera or on-NVR sampling; only events go upstream.

Hot / warm / cold storage (Phase-2, selected cameras only):
- Hot: 7 days, object store local to region
- Warm: 8–30 days, erasure-coded Ceph / S3
- Cold: 31–90 days, Glacier-class, legal hold only

PoC stores crops + metadata, not full GOP archives.

PoC mean JPEG from own-feed stills MEASURED 41 KB on 04 Sep 2026. Statewide 80 KB remains DESIGN TARGET.

## 6. AI / analytics

`analyse(frame, camera, pts_ms)` is the only worker entry. Engines are selected per camera.

Phase-1 implemented (CPU, no GPU required):

- **ANPR.** Sampled frame → plate box → Tesseract (or empty if the binary is absent) → Indian-plate normaliser (`^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{3,4}$`) → event with `source=anpr`. Operator confirm writes `source=operator_confirm`, confidence 1.0. Confirm is never labelled ANPR.
- **Object detection.** Person, car, motorcycle, bus, truck, bicycle. OpenCV DNN when weights exist; deterministic skin-tone blob fallback so tests and the demo do not need a GPU. CSV: `GET /api/objects/report.csv`.
- **Intrusion.** Person-in-ROI on `CAM-FCS-001` (Food & Civil Supplies godown). Wrapper on object boxes, not a fourth network. CRITICAL alert, 120 s dedupe.
- **Lawful FRS.** Enrolled gallery of consented adults or synthetic fixtures, Own cameras only (`CAM-OWN-001`). Manual confirm-face was removed (Phase 0 of the face upgrade); a review queue replaces it in Phase 2. **Never** on government CCTV of unknown people (`cam04` and any `ownership=Gov`). Not AFIS, not NAFIS, not a live ministry biometric pipe.

Cross-camera vehicle tracking in the PoC is plate sightings (`GET /api/track/{plate}`). Optional object `track_id` is per camera and resets on a scene cut.

Optional vision engines: FaceNet when `FACE_ENGINE=facenet`; YOLO when `OBJECT_ENGINE` or `ANPR_ENGINE=yolo`; ByteTrack when `TRACK_ENGINE=bytetrack`. Default remains histogram + blob + Tesseract + IoU. GPU count MEASURED 0 unless a later bench says otherwise. Next-camera `GET /api/predict/{plate}` is frequency plus distance, not Kalman. `POST /api/query` is a keyword filter (`engine=keyword_rules`), not a language model. Branded reconstruction models are not in this PoC.

Production swap (same functions): YOLO plate + PaddleOCR behind `recognize()`; YOLO11 on regional GPUs at 1 fps; dedicated FRS cameras with human confirm; AFIS/NAFIS as later APIs, not pixels. This repository is the production tree: https://github.com/amitduabits/PRAHARI.

### 6.1 Engine contract

Env defaults (CPU-only workstation, no GPU):

| Env | Default | Optional |
|---|---|---|
| `ANPR_ENGINE` | `tesseract` | `yolo` (vehicle crop then Tesseract, then full-frame fallback) |
| `OBJECT_ENGINE` | `opencv` | `yolo` (COCO person+vehicle; blob fallback) |
| `FACE_ENGINE` | `histogram` | `facenet` (MTCNN + 512-d, Own cameras only) |
| `TRACK_ENGINE` | `iou` | `bytetrack` (per-camera `track_id`; scene cut still resets) |
| `ANALYTICS_ENGINES` | `anpr,objects` | add `faces` only for `ownership=Own` |

`requirements.txt` stays FastAPI / OpenCV / Tesseract / pytest. Torch extras live in `requirements-vision.txt`. Importing `app.engines` must not import torch. FaceAnalyzer is constructed only after `engines_for()` has allowed faces.

### 6.2 FRS law

`engines_for()` drops `faces` when `ownership != Own` or `camera_id` matches `cam` plus digits. Log line `frs_refused`. Tests post a face-like still to `cam04` and assert zero `entity_type=person` events and zero FaceAnalyzer constructions. `POST /api/ingest/frame` remains ANPR-only. `POST /api/ingest/analyse` is the multi-engine door.

Gallery JSON (`GET /api/faces/gallery`) returns ids and counts, never embeddings. Not AFIS, not NAFIS, not a live ministry biometric pipe.

### 6.3 Crop honesty

Detections always write `crop_uri` and `crop_uri_original`. Optional `crop_uri_enhanced` is cubic upscale of a low-FFT crop, labelled `enhancement_method=none|cubic_upscale`. Matcher uses original pixels. `is_ai_reconstructed=1` on a face inserts alert `status=pending_review` and does not auto-notify CRITICAL. Branded reconstructor names are not in `app/`.

### 6.4 Predict and query

`GET /api/predict/{plate}` ranks next cameras by historical transition frequency, else GIS neighbours. Method is frequency plus distance, not Kalman, not Re-ID. `POST /api/query` is a regex keyword filter. Response includes `engine: keyword_rules`. It is not a language model.

## 7. Watchlist correlation and alerts

Watchlist tables (PoC: local Postgres/SQLite; production: read-replicas / APIs):

| Source | Entity |
|---|---|
| VAHAN | stolen / flagged vehicles |
| SARTHI | suspect licence linkage |
| eGujCop / CCTNS | wanted, missing, unidentified dead |
| AFIS / NAFIS | biometric cases (Phase-2) |

Every detection event is matched in O(1) against an in-memory plate set, refreshed from the source APIs every 60 seconds.

Alert object:

```
plate, camera_id, lat, lon, ts, crop_uri, category, priority, source_case_id
```

Priority: CRITICAL (stolen / wanted) → audible + red queue; HIGH → amber; LOW → log only.

Operator ack is audited. Duplicate suppression: same plate + same camera within 120 seconds collapses to one alert with a counter. Face hits match on `face_id` / `gallery_id` (`WL-004`) without a plate. Reconstructed face crops insert `pending_review` instead of an open CRITICAL card.

## 8. Multi-camera vehicle track

`GET /api/track/{plate}` returns chronological sightings joined to camera GIS.

Route reconstruction is a time-ordered polyline. No Kalman filter in PoC; Phase-2 adds:
- camera graph (adjacency by road network)
- travel-time sanity window so a plate cannot “teleport”
- interpolation on the road network, not as-the-crow-flies

CSV / PDF report is the operator artefact.

## 9. Security

- RBAC: `superadmin`, `soc_operator`, `dept_viewer`, `auditor`. Dept viewers see only their cameras.
- Stream URLs never shipped to the browser without a short-lived token.
- TLS on UI and APIs. mTLS between regional workers and the bus.
- Network segmentation: analytics VLAN ≠ enterprise VLAN ≠ camera VLAN.
- Audit table for onboard, watchlist edit, alert ack, report download.
- Privacy: raw video stays in the department that owns it. Centre stores events + crops for watchlist hits. Crops older than retention are purged.
- No public internet exposure of RTSP.

## 10. Scale, HA, operations

| Concern | PoC | Statewide |
|---|---|---|
| Compute | 1 laptop / 1 VM | 5 regional GPU nodes (8×L40S or equivalent) + 2 central API |
| Bus | WebSocket | Kafka 3-az |
| DB | SQLite | PostgreSQL + PostGIS + Redis |
| HA | none | active-active API, regional isolated failure domains |
| DR | git + DB file | daily object-store backup, RPO 15 min metadata, RTO 1 h |
| Observability | `/api/health` | Prometheus, camera-health SLO 99%, alert lag p95 < 5 s |

Horizontal scale unit = regional worker. Adding cameras is a registry row + worker subscription, not a platform rewrite.

## 11. Prerequisites from departments (need this on Day 1 of a real PoC)

- Camera inventory export (CSV) with lat/lon
- Protocol + reachable URL or jump-host
- Whether ONVIF profile S is enabled
- AMC vendor contact for firewall holes
- Retention policy and legal owner
- Written consent for private-permitted feeds
- Watchlist API contract / sample dump from SCRB

## 12. Cost sketch (order-of-magnitude, INR / year, statewide intelligence plane only)

| Item | Assumption | INR |
|---|---|---|
| 5 regional GPU inferencing nodes | capex amortised 3 yr | 1.8–2.4 Cr / yr |
| Object storage for crops + selected video | 2 PB usable | 0.8–1.2 Cr / yr |
| SWAN / leased bandwidth top-up | regional | 0.6–1.0 Cr / yr |
| Integration + SOC software ops | 12 engineers | 1.5 Cr / yr |
| **Total intelligence plane** | | **~5–6 Cr / yr** |

This is *not* the cost of replacing 26 departmental VMS estates. That is the point of the hybrid model.

## 12a. Live ingest contract

Gated by `02_Code/prahari/tests/test_integrator_laws.py` plus live soak when `SENTINEL_HOST` is set.

| Ingest rule | Implementation |
|---|---|
| RTSP over TCP | `OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp` before `import cv2`; FFmpeg `-rtsp_transport tcp` |
| No CAP_PROP_FPS / arrival-time metrics | Event time = `CAP_PROP_POS_MSEC`; sampler uses PTS deltas |
| Inter-frame gaps are not disconnects | `StreamSession.read` continues; scene-cut callback on PTS jump |
| Reconnect backoff 2–30 s | `backoff_sleep` |
| Decoder warnings at join are non-fatal | logged, not raised |
| Catalogue is `/cameras.json` | `app/services/catalogue.py`; ids from JSON. Live host has no `/api/ingest`. |
| Mixed H.264 / H.265 and resolutions | per-camera codec/width/height from catalogue |
| Scene discontinuity at loop | `detect_scene_cut` |

Consume only. No publish, no gateway control API, no file download of `/stream/<id>`.

## 13. Capability map

| Capability | Where it lives |
|---|---|
| Onboard government + own feeds | `POST /api/cameras`, `POST /api/cameras/import`, `POST /api/cameras/sync-catalogue`, Onboard tab |
| Unified viewing | Operations Leaflet map, `POST /api/sessions`, tokenised `GET /api/stream/{id}` (no RTSP in the browser) |
| ANPR + timestamps | `POST /api/ingest/frame`, `POST /api/ingest/confirm`, `GET /api/detections` |
| Objects + intrusion + lawful FRS | `POST /api/ingest/analyse`, `GET /api/objects/report.csv` |
| Designated vehicle path | `GET /api/track/GJ01AB1234` + `GET /api/track/{plate}/report.csv` |
| Watchlist + realtime alert | `GET/POST /api/watchlist`, `GET /api/alerts`, `POST /api/alerts/{id}/ack`, `WS /ws/alerts` |
| 80k readiness | §5 (DESIGN TARGET) and §10 of this HLD |
| GIS / gaps / private feeds | Registry + `GET /api/gap-report` |
| Next-camera | `GET /api/predict/{plate}` |
| Keyword filter | `POST /api/query` (`engine=keyword_rules`) |

## 14. HTTP surface (PoC)

Auth: HTTP Basic (judge / admin / home.viewer / auditor). Write routes 403 for viewer and auditor.

| Method | Path | Role |
|---|---|---|
| GET | `/api/health` | public |
| POST | `/api/login` | public |
| GET | `/api/cameras` | any role; viewer filtered by department |
| POST | `/api/cameras`, `/import`, `/sync-catalogue` | write |
| POST | `/api/sessions` | write; fifth live session 429 |
| GET | `/api/stream/{id}` | HMAC token |
| POST | `/api/ingest/frame` | write, ANPR-only |
| POST | `/api/ingest/analyse` | write, multi-engine |
| POST | `/api/ingest/confirm` | write, `source=operator_confirm` |
| GET | `/api/detections` | any role |
| GET | `/api/objects/report.csv` | any role |
| GET/POST | `/api/watchlist` | GET any; POST write; WL-001 cannot be deleted |
| POST | `/api/faces/enroll` | write |
| GET | `/api/faces/gallery` | any; no embeddings |
| GET | `/api/track/{plate}` + `/report.csv` | any |
| GET | `/api/predict/{plate}` | any |
| POST | `/api/query` | any |
| GET | `/api/alerts` | any |
| POST | `/api/alerts/{id}/ack` | write |
| WS | `/ws/alerts` | cookie |

## 15. Tests and honesty gate

Default pytest (04 Sep 2026, no torch): 88 passed, 4 skipped (Tesseract binary, FaceNet extras, YOLO weights, ByteTrack). `scripts/audit_gate.py` must print PASS: path jail, HLS origin pin, full HMAC, vendored `hls.min.js`, no live-ministry needles, 80k labelled DESIGN TARGET.

Vision pack tests live under `02_Code/prahari/tests/`. Optional engines skip with an explicit reason. They must not fail a CPU-only workstation that skipped `requirements-vision.txt`.
