# How to demo PRAHARI to a hackathon judge

Everything in this guide was run against the current build on 26 Sep 2026, on a
freshly reset database. Where a result is quoted, it is what the software actually
returned. Anything not built is marked **NOT IMPLEMENTED / FUTURE WORK**.

Part A explains the product. Part B is the 3-minute recording plan. Part C is the
checklist to run before you record.

---

# PART A — The walkthrough

## 1. What PRAHARI does, in one paragraph

Gujarat has thousands of CCTV cameras spread across ~26 departments (police, RTO,
GSRTC, food supplies, private premises). Each department runs its own system, and
nobody has one view of them all. Watchlists of stolen vehicles and wanted people
exist, but the cameras never check against them.

**PRAHARI sits on top of those existing systems rather than replacing them.** It
keeps one registry of every camera, reads number plates, checks each plate against
a watchlist, raises an alert when it finds a match, and rebuilds the route a vehicle
took across cameras. Its guiding rule is honesty about evidence: it always shows what
the OCR actually read next to what the system accepted, and it refuses to "verify" a
plate it is unsure of.

## 2. Features that work today

| Feature | What it does | Status |
|---|---|---|
| Sign-in with roles | Operator login; a viewer account is blocked from write actions | ✅ Working |
| Camera registry | 11 sample cameras across 6 departments, with ownership, codec, resolution, retention, health | ✅ Working |
| Add camera / CSV import | Register a new camera by form or by CSV, with a consent flag | ✅ Working |
| Gujarat map | Every camera with coordinates is a pin, coloured by health | ✅ Working |
| Video wall | Up to 4 tiles; a 5th is refused. Streams are tokenised and the raw `rtsp://` address never reaches the browser | ✅ Working (see limits) |
| **ANPR on a still image** | Upload a photo → finds the plate → reads it → validates it as an Indian plate → verified or not | ✅ Working |
| Raw OCR vs verified plate | Shows the raw read, the corrected reading, and the verified plate side by side, with corrected characters underlined | ✅ Working |
| Confidence and status | Confidence bar plus one of four statuses: Verified / Low confidence / Failed validation / No text | ✅ Working |
| Watchlist matching | A verified plate on the watchlist raises an alert immediately | ✅ Working |
| Alert de-duplication | The same plate on the same camera within 2 minutes adds to a counter (×2, ×3…) instead of a new alert | ✅ Working |
| Acknowledge alerts | Ack button; the acknowledgement is recorded server-side | ✅ Working |
| Detection history | Every detection with time, raw OCR, verified plate, source, confidence and crop | ✅ Working |
| Vehicle Track | Type a plate → route on a map, timeline, first/last seen, CSV export | ✅ Working |
| Operator confirm | A human records a sighting by hand. Labelled "Operator confirm", never passed off as ANPR | ✅ Working |
| Face-match privacy rule | Face matching runs only on the organisation's own cameras and is refused on government cameras | ✅ The **rule** works (see the warning below) |
| Analytics & Gaps | Offline cameras, short retention, unmapped cameras, private cameras without consent, charts | ✅ Working |

## 3. Every screen, explained

The top bar shows system health (`ok`), camera and detection counts, whether live
updates are connected (`WS connected`), the IST clock and who is signed in.

**Operations** (home screen)
- **Five headline tiles:** cameras by health, detections, open alerts, watchlist size, coverage gaps.
- **Camera map of Gujarat:** grey pins are health "unknown", the red pin is offline (Dahod). Click a pin → **Open**.
- **Video wall:** four slots. An open feed shows a red **LIVE** badge and an on-screen timestamp.
- **Priority alerts** and **Latest plate reads:** short live feeds of the newest activity.

**Cameras**
- **Registry table:** department filter chips and a search box. Each row has ownership, health, codec, resolution, retention and an **Open** button.
- **Opening a camera from here** jumps you to the Operations video wall.

**Vehicle Track**
- **Search:** type a plate → **Reconstruct**.
- **Summary strip:** the plate, its watchlist category, number of sightings, first seen, last seen and total time span.
- **Map:** numbered route pins, green for the first sighting and red for the last.
- **Timeline table:** every sighting in order. **Download CSV** exports it as evidence.

**Alerts**
- **Alert table:** priority badge, plate, category (e.g. STOLEN), camera, age, repeat counter and **Ack**.
- **Detection history** (scroll down): every detection, with raw OCR beside the verified plate.

**Watchlist**
- **The list:** stolen, blacklisted and missing-person cases, modelled on VAHAN / eGujCop records.
- **Forms:** add a new entry, or enrol a person's photo into a gallery.

**Onboard**
- **Left column:** Add camera, CSV import, and Operator confirm (plate).
- **Right column:** **ANPR this still** is the main feature. **Analyse this still** runs plates, objects and (own cameras only) faces.

**Analytics & Gaps**
- **Headline tiles** for coverage gaps.
- **Charts:** cameras by department, camera health, detections by type.
- **Gap register table** and the raw gap report.

## 4. How to test it yourself (user side)

The test images are all in:
`C:\Users\Admin\PRAHARI\03_Data\samples\anpr_testset\`

### Test 1 — a verified plate that is on the watchlist (the headline test)
1. Go to **Onboard**. Leave Camera ID as `CAM-OWN-001`.
2. In **ANPR this still**, click the drop zone and choose `easy\fixture_synthetic.jpg`.
3. **Expect**, in the same card, within about 1 second once the models are loaded:
   - a red banner: **Watchlist hit · CRITICAL · GJ01AB1234 · STOLEN at CAM-OWN-001**
   - a red pop-up in the bottom-right corner
   - Raw OCR `GJO1AB1234` → Verified plate `GJ 01 AB 1234`, with the `0` underlined
   - status **Verified**, confidence **0.70**
   - a note: "Characters were corrected to fit the plate format. Treat as weaker evidence."
4. **How to read it:** OCR read a letter **O** where a digit belongs. The system knows
   the third position of an Indian plate must be a digit, so it changed O→0, and it
   tells you so. It then found the plate on the watchlist and raised the alert.
5. **Be honest about the image:** it is a **synthetic** plate image made for testing,
   not a real camera photo.

### Test 2 — a real photo, verified with one correction
- **Upload** `easy\easy04_daylight.jpg.png`.
- **Expect:** raw `6J16CB1012` → verified `GJ 16 CB 1012`, confidence **0.87**, status **Verified**, with the `G` underlined. No alert, because it is not on the watchlist.

### Test 3 — a real photo the system refuses to verify
- **Upload** `easy\easy01_daylight.jpg.png`.
- **Expect:** a yellow note, "No plate accepted…". Raw `MHOTEE2388` → "Reads as · not accepted" `MH 07 EE 2388`. Status **Unverified / Low confidence**, confidence **0.33**, red bar. Verified plate: **none**.
- **How to read it:** the real plate is **MH01EE2388**, and OCR confused **1 with 7**. Confidence was below the 0.35 threshold, so PRAHARI **declined to verify it**. Nothing was written to detections, so no false alert was raised. This is the system being correctly cautious.

### Test 4 — a foreign plate
- **Upload** `medium\medium01_golf.jpg.png`. It takes about 11 seconds.
- **Expect:** raw `34CLC327`, confidence 0.99, status **Unverified / Failed validation**, detail "does not fit the Indian plate pattern".
- **How to read it:** OCR was confident, but the plate is not Indian, so it is rejected rather than forced into an Indian format.

### Test 5 — alerts, counter and acknowledgement
1. Upload `fixture_synthetic.jpg` a **second time** within 2 minutes.
2. Go to **Alerts**. The top alert is GJ01AB1234 at CAM-OWN-001, with the counter showing **×2**.
3. Click **Ack**. **Expect:** the pop-up "Alert acknowledged. Audit row written." and the row disappears.
4. Scroll to **Detection history**. Your uploads are at the top, with raw OCR beside the verified plate, the source `ANPR` and a plate crop thumbnail.

### Test 6 — vehicle route reconstruction
1. Go to **Vehicle Track**. The plate box holds `GJ01AB1234`. Click **Reconstruct**.
2. **Expect:** status STOLEN, and sightings starting at **Valsad NH-48 Toll** at 06:12 on 31 Aug, then Surat → Narol → SG Highway → Koba Circle → Gandhinagar, then your new CAM-OWN-001 sightings.
3. The map shows the route along the NH-48 corridor, numbered in order. Click **Download CSV** for the evidence file.
4. **Note:** the six Valsad→Gandhinagar sightings are **seeded sample data**, not real ANPR reads. Only the CAM-OWN-001 rows come from your uploads.

### Test 7 — video wall
1. **Cameras** → find `CAM-OWN-001` → **Open**. It jumps to Operations and the clip plays with a LIVE badge.
2. **Do not open the government cameras** (CAM-AHD-001 etc.). This machine has no live source for them and they return "stream error".

### Test 8 — face identification is switched off (Phase 0 of the face upgrade)
Face identification is **off** until a real recogniser is built (Phase 2). The old
colour-histogram "matching" and its cartoon starter face were removed because they could not
identify anyone. There is nothing to demo here yet.
- **Analyse this still** on `CAM-OWN-001` with any photo produces **no face identity and no face alert**.
- The privacy rule still holds: face processing never runs on government cameras.
- "Person" results now come **only from YOLO**. The old skin-colour "person 0.50" rows are gone.

### Test 9 — coverage gaps
- **Analytics & Gaps:** Dahod GSRTC depot is **offline**, and 8 cameras keep under 15 days of recording.

## 5. Full end-to-end flow for a judge (about 5 minutes)

1. **Sign in:** `judge` and your password.
2. **Operations:** point out the five tiles and the map pins.
3. **Open the video:** Cameras → `CAM-OWN-001` → Open, and watch the video play.
4. **Watchlist:** WL-001 is `GJ01AB1234`, STOLEN.
5. **Onboard → ANPR:** upload `fixture_synthetic.jpg`. You get a Verified plate, a correction and a CRITICAL watchlist hit.
6. **Onboard → ANPR:** upload `easy01`. It is refused as low confidence (the 1-vs-7 case).
7. **Alerts:** the new CRITICAL alert is at the top → **Ack**. Scroll to Detection history.
8. **Vehicle Track:** Reconstruct `GJ01AB1234` → route map → Download CSV.
9. **Analytics & Gaps:** show Dahod offline and the retention gaps.

## 6. What is real vs what is not built yet

### ✅ Genuinely implemented
- **ANPR on uploaded still images:** vehicle detection, a dedicated plate detector, EasyOCR, format repair, and Indian state-code validation.
- **Plate validation:** the four-way status and the confidence gate, and raw OCR is always kept.
- **Watchlist and alerts:** watchlist matching, CRITICAL/HIGH alerts, the 2-minute repeat counter, and acknowledgement.
- **Evidence views:** vehicle route reconstruction, CSV export, and detection history with crops.
- **Camera registry:** add, CSV import, the consent flag, and the gap report.
- **Viewing:** a tokenised video wall capped at 4 tiles, with the raw stream address hidden from the browser.
- **Privacy rule:** face matching is refused on government cameras.
- **Tests:** an automated suite of 108 passing tests.

### ⚠️ Works, but with an important limit
- **Only one video plays: `CAM-OWN-001`.** It is a local recorded clip, not a live CCTV feed. Government cameras need a live stream source and ffmpeg, which this machine does not have.
- **Camera health is "unknown"** for most cameras after a reset. Health is only probed on live streams.
- **Face matching is a colour-histogram placeholder.** The privacy rule is real; the face recognition is not. A FaceNet engine exists as an option but is **not enabled**.
- **The "person" objects on uploaded stills** come from a skin-colour heuristic with a fixed 0.50 score.
- **Watchlist, route and alert history are seeded sample data** modelled on VAHAN / eGujCop records. They are not connected to the real systems.
- **The live catalogue sync (Sentinel)** is coded and configured, but it depends on the lab network. After a reset only the 11 sample cameras show.
- **"Next cameras" prediction runs but gives meaningless results.** It currently reports "8224.5 km" because CAM-OWN-001 has no coordinates. **Do not show it.**
- **The audit log is written but not visible in the UI**, and the judge account cannot read it through the API.
- **Licence:** the plate-detector weights are AGPL-3.0. That is fine for R&D, but the licence must be resolved before any commercial or hosted deployment.

### ❌ NOT IMPLEMENTED / FUTURE WORK
- **ANPR on live video streams.** ANPR today runs only on stills you upload. Live stream ingest exists in the code (RTSP over TCP with reconnection), but it is **not connected to ANPR**.
- **Multi-frame plate voting:** reading a plate across several frames and voting per character. This is designed but not built.
- **Tracking a vehicle across frames:** the tracker is not verified to work.
- **Real VAHAN / SARTHI / eGujCop / AFIS integrations.**
- **Real face recognition** in the default build.
- **Central VMS recording** (a later phase by design).
- **Full WebRTC (WHEP) viewing and ONVIF discovery.**
- **Statewide scale.** "80,000 cameras at 1 fps" is a **DESIGN TARGET**, not measured. The ₹5–6 Cr/year cost is an **estimate**.

## 7. The ANPR pipeline in plain words

Think of it as five steps, each one a filter:

1. **Find the vehicle.** A general object detector (YOLOv8) finds cars and bikes in the photo.
2. **Find the plate.** A second, plate-specific detector draws a box around the number plate. It checks the whole photo and each vehicle, so it catches small plates too.
3. **Read the characters.** The plate crop is cleaned up in several ways (contrast, sharpening, resizing). EasyOCR reads each version, and the best reading wins.
4. **Repair using plate grammar.** An Indian plate always has the same shape: **2 letters (state) · 1–2 digits (district) · 1–3 letters (series) · 3–4 digits (number)**. If OCR puts a letter where a digit must be, it is fixed (O→0, I→1, G→6 and so on). At most **2 characters** can be changed, and the result **must start with a real Indian state code** (GJ, MH, DL…). Without that rule, random text could be "repaired" into a fake plate.
5. **Decide.** Each reading gets one of four statuses:
   - **Verified:** valid format, real state code, confidence ≥ 0.35. Only this becomes a detection and can raise an alert.
   - **Low confidence:** looks like a plate, but OCR was unsure. Shown, not trusted.
   - **Failed validation:** OCR read text that is not an Indian plate.
   - **No text:** nothing was readable.

**The one-line answer for a judge:** *"We detect the plate, read it several ways, fix
only the mistakes the plate format allows, require a real state code, and refuse to
verify anything below our confidence threshold. And we always show you what the OCR
actually saw."*

## 8. Results so far, and how to state them honestly

### Plate-location improvement (the dedicated plate detector)
On the **5-image development set**:

| | Before (Tesseract only) | After (plate detector + EasyOCR) |
|---|---|---|
| Plate found and read | 20% (1 of 5) | **100% (5 of 5)** |
| Exact plate correct | 20% | **40%** |
| Character error rate | 0.80 | **0.12** |

⚠️ Only 5 images, and they were used during development. This shows the direction of
the improvement, not accuracy.

### Latest benchmark (21 images, 19 scorable)

| | Before state-code validation | After (current build) |
|---|---|---|
| Plates returned as verified | 17 | 13 |
| Of those, correct | 8 | 8 |
| **Precision (a verified plate is right)** | 47.1% | **61.5%** |
| **Wrong plates returned** | 9 | **5** |
| Exact match (out of 19) | 42.1% | 42.1% |
| Images where any plate was returned | 89.5% | 68.4% |

**What this means:** the latest change did not make PRAHARI read more plates
correctly. The number correct stayed at 8. What it did was make PRAHARI **decline**
readings it could not validate, which cut wrong plates from 9 to 5. For a
stolen-vehicle system, a wrong plate is worse than no plate, so this is the right
trade-off.

### How NOT to state the results
- ❌ "PRAHARI is 61.5% accurate." ✅ Say: "On our 21-image test set, 61.5% of the plates we verified were correct."
- ❌ "Blind test." The set includes the 5 development images, and the state-code change was made after seeing results on it. Call it **"our 21-image test set"**.
- ❌ Any real-world accuracy claim. This is **21 still images**, not live traffic video.
- ❌ "No false positives." The test set contains **no images without plates**, so that has never been measured.
- ⚠️ The system can still verify a wrong plate. One low-light image reads as `GJ11N1016` instead of `GJ17N1016` at 0.93 confidence. Multi-frame voting is the planned fix.

---

# PART B — The 3-minute recording plan

**Before recording, complete the Part C checklist.** The screen should show the
browser only, maximised, at **http://127.0.0.1:8080**, already signed in, on
**Operations**, with `CAM-OWN-001` already playing in the video wall.

Keep the file chooser pointed at
`C:\Users\Admin\PRAHARI\03_Data\samples\anpr_testset\easy\` so each upload is two clicks.

---

### 0:00–0:15 · Opening
- **On screen:** Operations. Don't click anything.
- **Say:**
  > "Gujarat has thousands of CCTV cameras across twenty-six departments, and none of them talk to each other. Stolen-vehicle watchlists exist, but no camera checks against them. This is PRAHARI, an intelligence layer that sits on top of existing camera systems instead of replacing them."

### 0:15–0:40 · Operations dashboard
- **Do:** move the mouse across the five headline tiles, then over the map, then to the playing video tile.
- **You will see:** 11 cameras, 6 detections, 6 open alerts, 5 watchlist entries, 1 coverage gap. The map shows pins across Gujarat with Dahod in red. The video tile shows a LIVE badge and a timestamp.
- **Say:**
  > "One registry for every camera, government, private and our own, on one map. Pins are coloured by health: Dahod is offline. The video wall streams through short-lived tokens, so the browser never sees a raw camera address, and it's capped at four tiles."

### 0:40–1:20 · Core ANPR: a real watchlist hit
- **Do:** click **Onboard** → click the **ANPR this still** drop zone → choose `fixture_synthetic.jpg`.
- **You will see, within about a second:** the red **Watchlist hit · CRITICAL · GJ01AB1234 · STOLEN** banner, a red pop-up, raw OCR `GJO1AB1234` → verified plate `GJ 01 AB 1234` with the `0` underlined, a **Verified** badge, and confidence **0.70**.
- **Point at each part in order** (raw → verified → underline → confidence) while you speak.
- **Say:**
  > "Here's the core flow. We upload a frame. PRAHARI finds the vehicle, then the plate, then reads it. On the left is exactly what OCR saw: the letter O where a digit belongs. Indian plates have a fixed grammar, so we correct that one character, underline it so the operator knows, and require a real state code. It's verified at 0.70, it's on the stolen list, and a critical alert fires immediately. This test image is synthetic. The next one is a real photo."

### 1:20–1:50 · Refusing to guess
- **Do:** drop zone → choose `easy01_daylight.jpg.png`.
- **You will see:** a yellow "No plate accepted" note, raw `MHOTEE2388`, "Reads as · not accepted" `MH 07 EE 2388`, the **Unverified / Low confidence** badge, a red bar at **0.33**, and Verified plate **none**.
- **Say:**
  > "This is a real car. The true plate is MH-01, but OCR can't tell a 1 from a 7 in this frame, and its confidence is 0.33. PRAHARI refuses to verify it. Nothing is written as a detection and no false alert fires, but the raw reading is kept as evidence. For a stolen-vehicle system, a wrong plate is worse than no plate."

### 1:50–2:15 · Alerts and history
- **Do:** click **Alerts**. Hover over the top row, then click **Ack**. Scroll down to **Detection history**.
- **You will see:** the new CRITICAL alert for GJ01AB1234 at CAM-OWN-001 at the top, the pop-up "Alert acknowledged. Audit row written.", and in the history your upload at the top with raw OCR beside the verified plate, the source **ANPR**, and a crop thumbnail.
- **Say:**
  > "The alert is waiting for an operator. Repeat sightings within two minutes fold into a counter instead of flooding the screen. Acknowledging it is recorded. And every detection keeps its raw OCR, its confidence and its crop, so any decision can be traced back to the evidence."

### 2:15–2:40 · Vehicle route reconstruction
- **Do:** click **Vehicle Track** → **Reconstruct**. Hover over the map route, then point at **Download CSV**. Don't click "Next cameras".
- **You will see:** STOLEN, first seen at Valsad NH-48 Toll, a numbered route up NH-48 to Gandhinagar, and a timeline table.
- **Say:**
  > "Give it a plate and it rebuilds the route: first seen at the Valsad toll, north through Surat and Ahmedabad to Gandhinagar, with timestamps, exportable as CSV for a case file. The highway sightings here are sample records. The latest one is the detection we just made."

### 2:40–2:50 · What's still in development
- **Do:** click **Analytics & Gaps** and let the tiles show.
- **Say:**
  > "It also audits coverage: offline cameras and short retention. Honestly, what's still ahead: today ANPR runs on still frames. Next we connect it to live streams and vote across several frames per vehicle, which fixes exactly the 1-versus-7 case you just saw."

### 2:50–3:00 · Close
- **Do:** click **Operations**.
- **Say:**
  > "PRAHARI turns cameras the state already owns into one searchable, accountable network, and it shows its evidence instead of guessing. Thank you."

### If you have to cut time
Cut section 2:40–2:50 down to one sentence first, then shorten Vehicle Track. **Never
cut 0:40–1:50.** That is the product.

---

# PART C — Checklist before you record

1. **Reset the demo database** so the numbers match this guide:
   - stop the server (Ctrl+C in its window)
   - delete `C:\Users\Admin\PRAHARI\02_Code\prahari\data\prahari.db`
   - start it again with `.\run.ps1` in `02_Code\prahari`

   This reseeds 11 cameras, 6 detections, 5 watchlist rows and 6 CRITICAL alerts. It
   deletes every detection and alert you have made so far, plus any cameras from the
   Sentinel sync.
2. **Run the preflight** in a second window: `.\scripts\preflight_demo.ps1`. It must end with `PASS`.
3. **Open http://127.0.0.1:8080**, press **Ctrl+Shift+R** once, and sign in as `judge`.
4. **Warm up the models off camera.** The first plate read after start-up takes ~15 seconds.
   Upload `easy01_daylight.jpg.png` once in **ANPR this still**. It writes nothing to the
   database, so the counts stay correct.
5. **Open the video:** Cameras → `CAM-OWN-001` → **Open**. Leave it playing on Operations.
6. **Maximise the browser** (at least 1280 px wide) and close anything showing `.env` or passwords.
7. **Record the browser only** (Win+G).

### Do not do these on camera
| Don't | Why |
|---|---|
| Click **Next cameras** | It shows "8224.5 km" nonsense (CAM-OWN-001 has no coordinates) |
| Open a government camera tile | No live source on this machine, so it shows "stream error" |
| Upload the Golf photo during the take | It takes ~11 seconds |
| Claim live-video ANPR, real face recognition, or VAHAN integration | Not built |
| Say "X% accurate" | Say "on our 21-image test set" instead |
