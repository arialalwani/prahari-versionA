# PRAHARI — full demo script

> **Superseded.** Use `DEMO_VIDEO_SCRIPT.md` and `DEMO_GUIDE.md`. The face steps below (`a.png`, the 0.92 match, Confirm face) no longer work: the cartoon gallery and histogram face matching were removed in Phase 0 of the face upgrade.

Every claim below was executed against the running app on 2026-09-05 and matched.
Numbers marked *(pristine)* assume you ran the database reset in Part 0.

---

## Corrections to the earlier draft

| Earlier draft said | Actually true |
|---|---|
| "Four `PASS` lines" | **Five.** `health 200`, `detections>=6`, `cameras>=11`, `WL-001 present`, `UI PRAHARI`, then a final `PASS`. |
| "Click any pin, then Open tile" for the video wall | `CAM-OWN-001` has **no coordinates** and therefore **no map pin**. It is the only camera that plays. Open it from the **Cameras tab table**. |
| Analyse a still from `05_Output/experiments/own_stills` | Those stills produce **zero events** — an empty box. Use `data/faces/WL-004/a.png` instead: it returns a real face match at **0.92** and lets you show the government-camera refusal side by side. This is the strongest thirty seconds in the app and the draft skips it. |
| Track shows "six rows" | Six *(pristine)*. It is **7** right now — earlier operator-confirms appended real rows. Read the count off the line under the toolbar rather than saying a memorised number. |
| The tripwire is in `preflight_demo.ps1` | It is in `scripts/_env_helpers.ps1`, thrown by `Get-JudgeBasicHeader`. It surfaces as `JUDGE_PASSWORD still the example value. Rotate it (A01).` followed by `FAIL watchlist`. **Already satisfied** — your `.env` no longer holds the example value. |

Two more things you should know before you plan the take:

- **Do not press "Next cameras."** It currently reports *"geographically close (8224.5 km)"*, because the last detection sits on `CAM-OWN-001`, whose coordinates are `0,0`. It reads as a broken feature on camera. Pristine, this is still a proximity fallback, but with sane distances.
- **My verification runs left rows behind.** The database now holds 17 detections instead of 6, `WL-004` is named `Rep Person` instead of `Ramesh K`, and the `WL-004` gallery holds 10 images instead of 2. The Part 0 reset undoes all of it.

---

## Part 0 — before you start the server

### 0.1 Reset to pristine *(strongly recommended)*

Stop the server first, then:

```bash
del data\prahari.db
```

The next start reseeds from `03_Data/samples/`: **11 cameras, 6 detections, 5 watchlist rows**, and six `CRITICAL` alerts rebuilt from those detections. This is what makes every number in Part 2 true.

It also wipes the audit log and any watchlist row you added by hand. Nothing else is lost — cameras, watchlist and detections all come back from the CSV/JSON seeds.

### 0.2 Trim the face gallery *(optional, cosmetic)*

Retried enrolments left eight extra images in the gallery. To get back to the clean pair:

```bash
cd C:\Users\Admin\PRAHARI\02_Code\prahari\data\faces\WL-004 && del 3.jpg 4.jpg 5.jpg 6.jpg 7.jpg 8.jpg 9.jpg 10.jpg
```

`a.png` and `b.png` survive, and the app regenerates them if they ever go missing. Only do this if you plan to show the enrolment beat.

### 0.3 Already done — no action

- **`JUDGE_PASSWORD`** is set to a real value. The preflight tripwire is satisfied.
- **`own_feed.mp4`** exists — 6.1 MB, at `03_Data/recordings/`. Verified serving over HTTP 200 as `video/mp4`.
- **Port 8080** is now held by the correct build. It was previously an old copy from `C:\Users\Admin\PRAHARI-3.0`, which is why the enrolment box stayed empty.

---

## Part 1 — set the stage (recorder off)

**1. Clear the screen.** Quit Slack, mail, Telegram. Close any window showing `.env` or an `rtsp://` URL. Maximise the browser — below about 1280px the map and video wall stack instead of sitting side by side.

**2. Start the server.**

```bash
cd C:\Users\Admin\PRAHARI\02_Code\prahari
```

```bash
.\run.ps1
```

Wait for `Uvicorn running on http://127.0.0.1:8080`. Leave the window open.

If you see `error while attempting to bind`, something else holds 8080 — run `Get-NetTCPConnection -LocalPort 8080 -State Listen` and stop it. This has already happened once on this machine.

**3. Preflight, in a second window.**

```bash
cd C:\Users\Admin\PRAHARI\02_Code\prahari
```

```bash
.\scripts\preflight_demo.ps1
```

**Must see: five `PASS` lines, then a final line that is exactly `PASS`.** If the last line is `FAIL`, do not record.

**4. Sign in.** Go to `http://127.0.0.1:8080`, press **Ctrl+Shift+R** once. User is prefilled as `judge`; type your password.

**Must see:** seven tabs — Operations, Cameras, Vehicle Track, Alerts, Watchlist, Onboard, Analytics & Gaps — and a header strip reading `ok · 11 cameras · 6 detections · WS connected`.

**5. Open the one tile that plays.** Go to **Cameras**, find `CAM-OWN-001` in the table, click **Open**. The clip appears in the Operations video wall. Leave it playing — you will cut to it at 0:20 without fumbling.

Do this now, off camera. `CAM-OWN-001` is not on the map, and hunting for it live costs you fifteen seconds.

**6. Optional — enrol the two photos.** Watchlist → *Enroll Missing/Wanted Person*. Gallery ID `WL-004` and Camera ID `CAM-OWN-001` are prefilled. Under Photo choose `a.png` from `data\faces\WL-004`, click **Enroll**, then repeat with `b.png`.

**Must see:** `Enrolled 1 image(s) into gallery WL-004.`

Note these are `.png` files in the app's own data folder — not `03_Data`, and not `.jpg`. Click Enroll exactly once per photo; every click appends another copy permanently and nothing on screen shows the running total. Skipping this step costs you nothing — the built-in gallery already works.

---

## Part 2 — the take (3:00 hard cap)

Press **Win+G**, record the browser only. Times are a budget, not a countdown. If you drift, take it out of Vehicle Track — it has the most slack.

### 0:00 · Operations — the map

Click **Operations**. Gujarat fills the left, video wall on the right with `CAM-OWN-001` already playing.

> "This is PRAHARI, a hybrid intelligence plane. Departments keep their own video management systems — we sit above them and correlate."

**Must see:** pins on a drawn map. A blank grey rectangle means OpenStreetMap tiles did not load — stop and restart the take.

Ten pins, not eleven. The eleventh camera is the own-feed clip, which has no coordinates.

### 0:15 · Registry — coverage and its gaps

Click the **Dahod** pin, east of the state. Its health reads `offline`.

> "This is the camera registry — eleven cameras across Home, GSRTC, RTO, Food and Civil Supplies, and one permitted private mall. Dahod is offline on purpose. We show the gaps, not just the coverage."

Click **Cameras**. Point at the department filter chips along the top, then at the health dots in the table.

**Must see:** a table of eleven rows with coloured health dots, and filter chips reading All / Home / GSRTC / RTO / Food & Civil Supplies / Private / Own.

### 0:40 · Vehicle Track — rebuild the journey

Click **Vehicle Track**. The plate box already holds `GJ01AB1234`. Click **Reconstruct**.

**Must see:** a line drawn across the map, and six rows *(pristine)* — Valsad, Surat, two in Ahmedabad, two in Gandhinagar. The line under the toolbar reads `6 points · STOLEN`. Read that number rather than reciting one.

> "A designated vehicle, reconstructed from Valsad to Gandhinagar across six cameras and four hours. Live hits append to this same track."

Click **Download CSV**. Chrome shows the download bar. Keep that file — it is a submission deliverable.

Do **not** press *Next cameras*. See the note in Corrections.

### 1:05 · Alerts — priority and deduplication

Click **Alerts**.

**Must see:** six red `CRITICAL` cards for `GJ01AB1234`, sorted above anything else. Never the `No open alerts` message.

> "A stolen plate raises CRITICAL automatically, one alert per camera. Repeat sightings inside two minutes fold into a counter instead of spamming the operator — that's the times-N you see on the card. Every one of these has an Acknowledge button and an audit row behind it."

Click **Watchlist** and point at `WL-001`.

> "A representative VAHAN and eGujCop-style watchlist, not a live ministry feed. WL-001 is the entry that fired those alerts, and it cannot be deleted."

### 1:30 · The compliance beat — same face, two cameras

This is the most important thirty seconds. Click **Onboard**, scroll to **Analyse this still**.

Leave Camera ID as `CAM-OWN-001`. Choose `a.png` from `C:\Users\Admin\PRAHARI\02_Code\prahari\data\faces\WL-004`.

**Must see:** a result table containing a row `person · WL-004 · faces · 0.92`, alongside three `object · person · objects · 0.5` rows.

> "That is our own camera. The enrolled-gallery face matcher runs, finds WL-004, and raises a HIGH alert."

Now change Camera ID to `CAM-AHD-001` — a government camera — and choose the **same file** again.

**Must see:** object rows only. **No `person` row, no `WL-004`, no gallery identity.**

> "Same photograph, government camera. The browser still asks for face matching; the server refuses it and logs the refusal. Objects yes, identity never. Face recognition runs on our own cameras only — that is enforced server-side, not by hiding a button."

This is the claim judges actually test. You are demonstrating it rather than asserting it.

### 2:05 · Operator confirm — the human in the loop

Still on Onboard, scroll to **Operator confirm**. Camera reads `CAM-OWN-001`, plate reads `GJ01AB1234`. Click **Confirm plate**.

> "An operator confirm — a human writing a real detection row at confidence one. It is not automatic plate recognition and we do not label it as one."

Skip the **ANPR this still** box above it. Tesseract is genuinely not installed on this machine; it returns an empty result and burns twenty seconds showing nothing.

**Must see:** the Alerts list updates. If you have five spare seconds, click back to Vehicle Track and press **Reconstruct** — the track is now seven rows, proving the "live hits append" line you delivered at 0:40.

### 2:25 · Analytics & Gaps — and the footer

Click **Analytics & Gaps**. Expand **Gap report**.

**Must see:** JSON listing `offline: ["CAM-GSRTC-DAHOD"]`, a `short_retention` array of eight cameras at seven days, `missing_coords`, `private_without_consent`, and `counts_by_department`.

> "The gap report is a procurement document. Dahod offline, eight cameras holding only seven days of footage, and any permitted-private camera missing a consent flag."

Scroll so the grey footer bar is fully in frame. Hold it.

> "Eighty thousand cameras is a design target, and it is labelled as one on screen. We sample one frame per second at the region. The measured limit on this laptop is four open tiles — and we show you that number rather than hide it."

**Must see:** the footer sentence legible on camera.

### 3:00 · Cut

Stop at or before 3:00. Save as:

```
C:\Users\Admin\PRAHARI\05_Output\deliverables\own_feed_demo.mp4
```

Watch it back once at speed, checking one thing only: no password, no `.env` window, no `rtsp://` address in any frame.

---

## Part 3 — the extended cut (5:00)

If the submission allows five minutes, keep everything above and insert these. Each is verified working.

### A. The four-tile cap, demonstrated (+25s, after 0:15)

On **Cameras**, click **Open** on four different rows, then a fifth.

**Must see:** `Fifth live session rejected. Close a tile first.` in red above the wall. The server returns HTTP 429 with `MAX_OPEN_CAPTURES=4 reached.`

> "The four-tile cap is not a slide. It is a real limit, measured on this hardware, and the fifth request is refused."

**Cost:** the three government tiles will be black rectangles — their RTSP sources are not reachable from this laptop. Only show this if you are comfortable saying so out loud: *"three of these have no reachable source from this laptop, which is exactly what the registry health column is telling you."*

### B. Confirm face — a person alert, created live (+20s, after 2:05)

Onboard → **Confirm face** form, below Operator confirm. Camera `CAM-OWN-001`, Gallery `WL-004`. Click **Confirm face**, then switch to Alerts.

**Must see:** a new `HIGH` card, entity `WL-004`, category `MISSING_ASSOCIATE`.

> "The same human-in-the-loop path for a missing person. Gallery WL-004, our own camera. The server rejects this outright on a government camera."

### C. Camera onboarding (+30s)

Onboard → top form. Fill Camera ID `CAM-OWN-002`, leave the rest, note the **consent** checkbox, click **Add camera**. Return to Cameras — the row is there.

> "Departments onboard cameras with ownership and a consent flag. Consent is a first-class field, and a permitted-private camera without it appears in the gap report."

### D. Deduplication counter, live (+15s)

Click **Confirm plate** twice within two minutes, then open Alerts.

**Must see:** one card, not two, with the counter reading `×2`.

> "Two sightings, two minutes, one alert. The counter increments; the operator is not spammed."

### E. Alert acknowledge (+10s)

On any card click **Ack**. It leaves the open list.

---

## Appendix A — every feature, and how to show it

| # | Feature | Where | Shown by | In the 3:00 take |
|---|---|---|---|---|
| 1 | Camera registry, 11 cameras, 6 departments | Operations map / Cameras | Map pins + table | Yes, 0:00 |
| 2 | Health states (`live` / `degraded` / `offline` / `unknown`) | Cameras table dots | Dahod is `offline` | Yes, 0:15 |
| 3 | Department filter chips | Cameras | Click a chip | Yes, 0:15 |
| 4 | Video wall, tokenised playback | Operations | `CAM-OWN-001` tile | Yes, pre-opened |
| 5 | Four-tile session cap, HTTP 429 | Operations | Open a fifth tile | Extended A |
| 6 | Short-TTL stream tokens (RTSP URL never reaches the browser) | — | Say it over the tile | Verbal |
| 7 | Vehicle track reconstruction | Vehicle Track | Reconstruct | Yes, 0:40 |
| 8 | Track CSV export, audited | Vehicle Track | Download CSV | Yes, 0:40 |
| 9 | Teleport / speed-plausibility flags (>180 km/h) | Vehicle Track | Only fires on implausible data | Not shown — no flags in seed |
| 10 | Next-camera prediction | Vehicle Track | **Avoid** — see Corrections | No |
| 11 | Watchlist match → automatic alert | Alerts | Six CRITICAL cards | Yes, 1:05 |
| 12 | Priority ranking CRITICAL → HIGH → LOW | Alerts | Card order | Yes, 1:05 |
| 13 | 120-second dedupe counter | Alerts | `×N` on a card | Extended D |
| 14 | Acknowledge | Alerts | Ack button | Extended E |
| 15 | Live WebSocket alert push | Header | `WS connected` chip | Verbal |
| 16 | `pending_review` status for AI-reconstructed evidence | Alerts | Not reachable in this seed | Verbal only |
| 17 | Watchlist CRUD, WL-001 delete-protected | Watchlist | Point at WL-001 | Yes, 1:05 |
| 18 | Face enrolment into a gallery | Watchlist | Enroll form | Part 1, step 6 |
| 19 | **Enrolled-gallery face match on own cameras** | Onboard → Analyse | `a.png` on `CAM-OWN-001` → 0.92 | **Yes, 1:30** |
| 20 | **Server-side FRS refusal on government cameras** | Onboard → Analyse | same file on `CAM-AHD-001` | **Yes, 1:30** |
| 21 | Object detection (person / car / bus / truck / bike) | Onboard → Analyse | object rows at 0.5 | Yes, 1:30 |
| 22 | Object track IDs | Analyse raw JSON | `track_id: CAM-AHD-001-1` | Expand *raw* |
| 23 | Operator confirm — plate | Onboard | Confirm plate | Yes, 2:05 |
| 24 | Operator confirm — face, Own-only | Onboard | Confirm face | Extended B |
| 25 | Camera onboarding with consent flag | Onboard | Add camera | Extended C |
| 26 | Camera CSV import | Onboard | File picker | Skip — slow |
| 27 | Intrusion detection, person-in-ROI | `CAM-FCS-001` godown | Needs an ROI-configured frame | Verbal only |
| 28 | Entity-type counts | Analytics & Gaps | Counts table | Yes, 2:25 |
| 29 | Object CSV export | Analytics & Gaps | Download link | Mention |
| 30 | Gap report — offline, retention, coords, consent, per-department | Analytics & Gaps | Expand it | Yes, 2:25 |
| 31 | Audit log of every write and every gate decision | `/api/audit` | No UI — say it | Verbal |
| 32 | RBAC: `superadmin` / `soc_operator` / `dept_viewer` | Login | A `dept_viewer` sees only their department | Verbal |
| 33 | Keyword query engine, honestly labelled `keyword_rules` | `/api/query` | No UI | Verbal |
| 34 | Sentinel catalogue sync | `/api/cameras/sync-catalogue` | Needs `SENTINEL_HOST` | Not configured |
| 35 | Camera CSV export, audited | `/api/cameras/export.csv` | No UI | Verbal |

**Features 31, 32 and 33 have no user interface.** If a judge asks "how do I know face recognition was refused?", the answer is the audit log: every enrolment and every gate decision writes a row like `face_enroll camera_id=CAM-AHD-001 action=enroll gate_result=blocked reason=ownership_not_own`. Say that sentence — do not open a terminal on camera to prove it.

---

## Appendix B — what will fail on camera, and why

| Do not do this | What happens |
|---|---|
| Open a tile for any camera except `CAM-OWN-001` | HTTP 503, black rectangle. Their RTSP sources are unreachable and ffmpeg has no input. |
| Look for `CAM-OWN-001` on the map | It has coordinates `0,0` and is deliberately not plotted. Use the Cameras table. |
| Use **ANPR this still** | Tesseract is not installed. Returns `No plate.` every time. |
| Press **Next cameras** | Reports distances around 8,225 km, because the last detection has null coordinates. |
| Analyse a file from `05_Output/experiments/own_stills` | Zero events. An empty result box. |
| Analyse `own_feed_frame.jpg` | Also zero events. |
| Recite a row count from memory | Operator confirms append permanently. Read the count off the screen. |
| Delete `WL-001` | Refused by design — but it is a dead-end on camera. |

---

## Appendix C — recovery moves

| Symptom | Fix |
|---|---|
| Grey rectangle instead of a map | OSM tiles failed. Check the network, reload, restart the take. |
| `No open alerts` on the Alerts tab | The database was reset but the server was not restarted. Restart it — alerts rebuild from detections at startup. |
| Enrolment box stays empty | You are on a stale server. Confirm the page shows the **Gallery ID** and **Camera ID** fields; the old build has neither. |
| `401` and `FAIL watchlist` in preflight | `.env` was edited while the server was running. The app reads it once, at startup. Restart the server. |
| Video tile black | You opened a government camera. Close it and open `CAM-OWN-001` from the Cameras table. |
| Wrong numbers everywhere | Stop the server, delete `data\prahari.db`, start again. |

---

## The four sentences that matter

If the recording goes wrong and you have thirty seconds to salvage it, these are the claims that differentiate the submission:

1. *"Departments keep their own VMS. We sit above them and correlate."*
2. *"Same photograph — identified on our own camera, refused on a government camera. Enforced server-side."*
3. *"An operator confirm is a human writing a real row. It is not automatic plate recognition and we do not label it as one."*
4. *"Eighty thousand cameras is a design target and it says so on screen. The measured cap on this laptop is four tiles, and we show you that number rather than hide it."*
