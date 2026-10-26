# PRAHARI: Face Recognition and Person Re-Identification Upgrade

## Developer Brief

**Repository:** github.com/amitduabits/PRAHARI (branch `engine-pack`)
**Goal:** Replace the current placeholder people-identification features with a research-backed, auditable pipeline that works on real CCTV footage, including when faces are unclear.

---

## 1. Context

PRAHARI is a hybrid CCTV/ANPR intelligence system built for the Gujarat Police Sentinel hackathon. A code review found the people-related features are not reliable:

1. **Person detection** uses YOLO, but a skin-colour fallback can invent a person when YOLO finds nothing.
2. **Face matching** compares colour histograms, not facial features. A score above 0.55 does not mean two faces are the same person.
3. **Intrusion alerts** depend on person detection, so false detections create false critical alerts.
4. **"Confirm face"** only records that an operator saw someone. It does no verification.
5. A **cartoon starter face** is used in the demo, which is misleading.

This brief replaces all of the above.

---

## 2. Before You Start

1. Commit the current working version and tag it `pre-face-upgrade` as a rollback point.
2. Make each change below as a **separate, small commit** so improvements can be demonstrated one by one.
3. Keep the existing tech stack and ANPR features intact. If anything in this brief conflicts with the existing architecture, flag it before building.

---

## 3. Phase 0: Remove the Unreliable Logic

| Task | Action |
|---|---|
| Skin-colour fallback | Delete it. Only YOLO person detections count. |
| Histogram face matching | Disable for all alerts. Remove once Phase 2 is live. |
| Cartoon starter face | Remove from code, assets, and demo data. |
| Manual "Confirm face" | Replace with the Match Review Queue (Section 7, Screen 3). |
| Intrusion alerts | Fire only on YOLO person detections above a confidence threshold. Test restricted-zone logic separately. |

**Acceptance:** A test set of empty rooms, walls, cars, and close-up faces produces zero invented person detections and zero false intrusion alerts.

---

## 4. Target Pipeline

```
CCTV frame
   │
   ├─► YOLO person detection ──► ByteTrack (track ID per person)
   │                                  │
   │                                  ├─► Body ReID embedding (OSNet)
   │                                  ├─► Attribute tags (clothing, bag, cap, etc.)
   │                                  └─► Carried-object detection (YOLO classes)
   │
   └─► SCRFD face detection ──► Face quality score
                                     │
                                     ├─► Best-frame selection per track
                                     └─► AdaFace embedding ──► FAISS watchlist search
                                                                    │
                                                                    ▼
                                                     Match Review Queue (human decides)
```

**Core principle:** Face recognition answers *who*. Body ReID answers *where the same person went*. A human always makes the final call.

---

## 5. Models and Components

| Stage | Model / Tool | Notes |
|---|---|---|
| Person detection | Existing YOLO | Person class only for people logic |
| Tracking | ByteTrack | Persistent track ID per person across frames |
| Face detection | SCRFD (InsightFace) | SCRFD-2.5G on CPU; SCRFD-10G if GPU available. Use 5-point landmarks for alignment |
| Face quality | Score from face size, blur, pose, brightness, plus AdaFace feature norm | Drives best-frame selection and alert routing |
| Face recognition | AdaFace (R50 default, R18 if CPU constrained) | Chosen over ArcFace for better performance on low-quality and surveillance images |
| Watchlist search | FAISS | Cosine similarity on normalised embeddings |
| Body ReID | OSNet (default) | CLIP-ReID as optional higher-accuracy upgrade if GPU available |
| Attributes | Pedestrian attribute recognition model | Upper/lower clothing colour, gender presentation, cap/helmet, backpack/bag, sleeve length |
| Carried objects | YOLO | Bag, backpack, suitcase, helmet, phone, and other relevant classes |
| Runtime | ONNX Runtime | Required for laptop performance. Use CUDA or CoreML providers when available |

**Licensing note:** Pretrained InsightFace weights are licensed for non-commercial research only. Acceptable for the hackathon. Document this in the README and keep the model layer swappable so weights can be replaced later.

---

## 6. Key Logic

### 6.1 Multi-frame face aggregation
- For each track, score every detected face for quality.
- Keep the top 3 to 5 frames by quality.
- Match using the quality-weighted average embedding of those frames, not a single frame.
- Re-run matching if a significantly better frame appears later in the track.

### 6.2 Quality-based routing (replaces any hard pixel cutoff)

| Quality band | Action |
|---|---|
| High | Automatic watchlist matching; alert if above match threshold |
| Medium | Matching runs; any hit goes to review queue as "Needs Review" |
| Low | No live matching; stored for retrospective search and ReID linking only |

### 6.3 Confidence bands
- Never show raw similarity scores to operators.
- Show **Strong / Needs Review / Weak**, with thresholds **calibrated on the evaluation set** (Section 10), not hard-coded guesses.
- Thresholds must be configurable in an admin settings file.

### 6.4 Face plus body linking
- Every track carries a body ReID embedding and attribute tags.
- Tracks across cameras are linked by ReID similarity and time/distance plausibility.
- When any linked track later yields a clear face match, the whole linked journey is upgraded from "same person as earlier sighting" to "possible identity match."
- Body ReID alone must **never** be presented as identity confirmation.

### 6.5 Detection frequency
- Run detectors every 2nd or 3rd frame; ByteTrack fills the gaps.
- Process faces at full source resolution (or tiled), not downscaled frames.

---

## 7. User Interface: Six Screens

### Screen 1: Live Camera Wall
- Grid of camera tiles with person and face boxes, track IDs, and quality badges.
- **Non-watchlist faces blurred by default.** Unblur requires an operator action and is logged.
- No names displayed on this screen.

### Screen 2: Watchlist Manager
- Each person: 3 to 5 reference photos, name/alias, **case/FIR reference (mandatory)**, added by, date added, **expiry date (mandatory)**.
- Enrollment quality check rejects unusable photos with a clear reason ("face too small", "eyes not visible").
- Entries auto-expire unless renewed.

### Screen 3: Match Review Queue
- Alert card: best CCTV crop beside reference photo, 5-second clip, camera, time, confidence band.
- Show **top 3 candidates**, not a single forced answer.
- Buttons: **Confirm / Reject / Escalate**. Reason required on Confirm.
- Rejections stored for threshold tuning.
- No automatic downstream action without human confirmation.

### Screen 4: Search
Three entry points, same results view:
1. **Photo search:** upload a face photo.
2. **Description search:** select attributes (e.g. black hoodie, grey bag, male, cap).
3. **Click to follow:** select a person in any footage.

Inputs: cameras and time window. Output: ranked sightings with thumbnails; click to jump to the clip. **Case reference required for every search.**

### Screen 5: Journey Map
- Map of all linked sightings for a confirmed person, with timestamps and camera names.
- Show which sightings are face-matched versus ReID-linked (different marker styles).
- Integrate ANPR: show vehicle plates detected near the person's last sightings.

### Screen 6: Audit and Accuracy Panel
- Log of every search, unblur, confirmation, rejection, and watchlist change: user, time, case reference.
- Display current measured accuracy at active thresholds: false match rate and miss rate, from the latest evaluation run.

---

## 8. Data Model (minimum)

| Entity | Key fields |
|---|---|
| WatchlistPerson | id, name/alias, case_ref, added_by, added_at, expires_at, status |
| ReferenceImage | id, person_id, image_path, quality_score, embedding |
| Track | id, camera_id, start_time, end_time, best_face_frames, face_embedding, reid_embedding, attributes |
| TrackLink | track_a, track_b, reid_similarity, plausibility_score |
| Alert | id, track_id, candidates (top 3 with bands), status, reviewed_by, decision, reason, timestamp |
| AuditLog | id, user, action, target, case_ref, timestamp |

---

## 9. Privacy and Governance Controls

- Face recognition runs only on cameras marked `Own` in configuration. Note in the README that this is a technical control and does not by itself establish legal authority or consent.
- Blur non-watchlist faces by default.
- Mandatory case reference for watchlist entries and searches.
- Watchlist expiry enforced.
- Full audit log, not editable from the UI.
- Test and demo data must use **consented** images only (team members) plus public research benchmarks.

---

## 10. Evaluation Plan

1. **Own footage set:** record team members (with consent) on the project cameras at varying distance, angle, lighting, with and without caps, masks, and clothing changes.
2. **Public benchmarks:** a low-resolution face set (such as TinyFace or SCface) and a ReID set (such as Market-1501), within their licence terms.
3. **Measure:**
   - Person detection: missed people, false detections.
   - Face recognition: true match rate and false match rate at each confidence band.
   - ReID: rank-1 accuracy for cross-camera linking.
4. **Before/after comparison for the demo:** single-frame histogram matching vs single-frame AdaFace vs multi-frame AdaFace, on the same footage.
5. Use results to set the Strong / Needs Review / Weak thresholds.

---

## 11. Performance Targets (laptop)

- 1 to 2 live feeds in near real time on CPU only.
- More feeds when a GPU or Apple Silicon is available.
- Any model fine-tuning (for example AdaFace on degraded CCTV-style data) is done on Colab or Kaggle GPUs, then exported to ONNX for local use.

---

## 12. Milestones and Deliverables

| Phase | Deliverable | Acceptance |
|---|---|---|
| 0 | Unreliable logic removed | Zero invented detections on negative test set |
| 1 | SCRFD + ByteTrack + quality scoring live on Screen 1 | Stable track IDs, quality badges visible, blur on |
| 2 | AdaFace + FAISS + watchlist + review queue (Screens 2, 3) | Calibrated bands, top-3 candidates, Confirm/Reject/Escalate working |
| 3 | Body ReID + attributes + carried objects | Cross-camera linking working on own footage |
| 4 | Search, Journey Map with ANPR, Audit panel (Screens 4, 5, 6) | All three search modes working; every action logged |
| 5 | Evaluation report and demo video | Before/after metrics table and walkthrough of the chain-snatching scenario |

**Demo scenario to support end to end:** A witness describes "black hoodie, grey bag, ran towards the station." The officer runs a description search, selects the right candidate, ReID follows him across cameras, a clear face at one camera produces a watchlist match for review, the officer confirms, and the Journey Map shows the route plus the vehicle plate from ANPR.

---

## 13. Questions to Answer Before Building

1. What is the current backend and frontend stack, and where does each new module fit?
2. Is a GPU available for development and demo?
3. What camera resolutions and frame rates are we working with?
4. Which existing modules depend on the current face-matching or "Confirm face" code?
