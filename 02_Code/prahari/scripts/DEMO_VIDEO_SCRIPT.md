# PRAHARI — demo video script

About 3 minutes 40 seconds. It starts at the login screen and visits every page once,
in an order that tells one story: **set up → watch → catch → investigate → review**.

Each step has three lines:
- **DO:** what you click
- **SEE:** what appears
- **SAY:** read it out as written

Speak slowly. Let each result sit on screen for a second before you talk over it.

---

## Before you press record (off camera, 5 minutes)

1. **Reset the data:** stop the server, delete `02_Code\prahari\data\prahari.db`, and start it again with `.\run.ps1`.
2. **Log in and warm up:** open `http://127.0.0.1:8080`, press **Ctrl+Shift+R**, and sign in as `judge`.
3. **Warm up the plate reader:** go to **Onboard** → **ANPR this still** → upload
   `03_Data\samples\anpr_testset\easy\easy01_daylight.jpg.png`.
   The first read takes about 15 seconds; later reads take about a second. This image saves nothing, so your numbers stay clean.
4. **Sign out:** click **Operations**, then the **sign-out icon** (top right). You are back on the login screen.
5. **Set up the screen:** maximise the browser, close every other window, and start the screen recorder on the browser only.

---

## The script

### 1 · Login — 0:00 to 0:15
**DO:** Nothing yet. Let the login screen sit.
**SEE:** The PRAHARI sign-in page, with four capabilities listed on the left.
**SAY:**
> "Gujarat has thousands of CCTV cameras spread across twenty-six departments. Each one runs its own system, and none of them talk to each other. Stolen-vehicle lists exist, but no camera checks against them. PRAHARI fixes that. It sits on top of the cameras the state already owns."

**DO:** Type the password, press **Enter**.

---

### 2 · Operations — 0:15 to 0:40
**SEE:** The home screen. Five numbers across the top, a map of Gujarat, and four empty video slots.
**DO:** Move the mouse slowly across the five numbers.
**SAY:**
> "This is the control room. In one glance: how many cameras we have, what they've seen, how many alerts are waiting, who we're looking for, and where our coverage is weak."

**DO:** Move the mouse to the map and hover over a few pins.
**SAY:**
> "Every camera from every department, on one map. The red one is Dahod. It's offline, and PRAHARI has flagged it automatically."

---

### 3 · Cameras — 0:40 to 1:00
**DO:** Click **Cameras**.
**SEE:** A table of all 11 cameras: department, location, owner, health, video format, and how many days of footage each keeps.
**DO:** Click the **Home** filter button, then **All**. Type `OWN` in the search box.
**SAY:**
> "Here's the full registry: police, RTO, bus depots, private premises. Filter by department, or search in a second."

**DO:** Click **Open** on `CAM-OWN-001`.
**SEE:** It jumps back to Operations and the video starts playing with a red **LIVE** badge.
**SAY:**
> "One click and the feed is on the video wall. The stream goes through a short-lived secure token, so the camera's real address never reaches the browser."

---

### 4 · Watchlist and facial recognition — 1:00 to 1:25
**DO:** Click **Watchlist**.
**SEE:** A short list of cases. The top one is `GJ 01 AB 1234`, marked **STOLEN · CRITICAL**. One row has type **person** with gallery `WL-004`.
**SAY:**
> "This is who we're looking for: stolen vehicles, blacklisted vehicles, missing people. Remember this top one, GJ-01-AB-1234. It's stolen."

**DO:** Point at the **person** row, then scroll down to the **Enroll Missing/Wanted Person** form and hover over it. **Do not click Enroll.**
**SAY:**
> "PRAHARI also handles people. For a missing or wanted person, an officer enrols a consented photo into a face gallery right here. Then PRAHARI detects faces in camera frames and matches them against that gallery, and a match raises an alert, just like a stolen car."
>
> "Facial recognition is sensitive, so we built the rules in first. Face matching only runs on cameras we own, and the server blocks it outright on government cameras. That rule is enforced in code, not left to policy. The high-accuracy face model plugs in behind this and is our next integration."

*(Face identification is switched off until the real recogniser lands (Phase 2), so there is no face match to run.
If a judge asks, say: "the enrolment, detection and the own-camera rule work today; the production face model is the next integration.")*

---

### 5 · Onboard: catching the stolen car — 1:25 to 2:00 ★ the key moment
**DO:** Click **Onboard**. In the **ANPR this still** box, click the drop area and choose
`03_Data\samples\anpr_testset\easy\fixture_synthetic.jpg`.
**SEE:** In about a second:
- a **red banner: "Watchlist hit · CRITICAL · GJ01AB1234 · STOLEN"**
- a red pop-up in the corner
- the plate drawn three ways: **Raw OCR** `GJO1AB1234` → **Verified plate** `GJ 01 AB 1234`
- a green **Verified** badge and a confidence bar at **0.70**

**DO:** Point at the red banner first, then at the two plates from left to right.
**SAY:**
> "We give PRAHARI a frame. It finds the vehicle, finds the plate, reads it, and checks it against the watchlist. That's our stolen car, and a critical alert fires instantly."
>
> "And look at how it shows its work. On the left is exactly what the camera read: a letter O where a number should be. Indian plates follow a fixed pattern, so PRAHARI corrects that one character and underlines it, so the officer knows exactly what was changed."

*(If asked: this is a test image made for the demo. The next one is a real photo.)*

---

### 6 · Onboard: reading a real car — 2:00 to 2:20
**DO:** In the same box, choose `03_Data\samples\anpr_testset\hard\hard03_occluded.jpg.jpg`
(it's in the **hard** folder).
**SEE:** In about a second:
- the photo of a grey Range Rover on a road, and a close-up crop of its plate
- **Raw OCR** `MH01CT8020` → **Verified plate** `MH 01 CT 8020`
- a green **Verified** badge, confidence **0.99**, and "matches Indian plate format"

**DO:** Point at the car photo, then the plate crop, then the verified plate.
**SAY:**
> "Now a real photo: a moving car on a real road, the plate small in the frame. PRAHARI finds the plate, crops it, and reads MH-01-CT-8020, every character right, at ninety-nine percent confidence. Nothing needed correcting, and because this car isn't on the watchlist, no alert. It's simply logged."

---

### 7 · Onboard: when it's not sure — 2:20 to 2:40
**DO:** In the same box, choose `03_Data\samples\anpr_testset\easy\easy01_daylight.jpg.png`.
**SEE:**
- a yellow note: **"No plate accepted"**
- **Reads as · not accepted:** `MH 07 EE 2388`
- a yellow **Low confidence** badge and a short red bar at **0.33**
- **Verified plate:** none

**SAY:**
> "And here's another real car, where the frame is harder. The real plate is MH-01, but a 1 looks like a 7. PRAHARI sees that it's unsure, and it refuses to guess. No false alert, no innocent driver stopped. But the reading is kept as evidence."

---

### 8 · Alerts — 2:40 to 3:00
**DO:** Click **Alerts**.
**SEE:** The new **CRITICAL** alert for `GJ 01 AB 1234` at `CAM-OWN-001`, at the top of the list.
**SAY:**
> "The alert is waiting for an officer. If the same car passes again, the counter goes up instead of flooding the screen."

**DO:** Click **Ack** on that top row.
**SEE:** A pop-up: "Alert acknowledged. Audit row written." The row disappears.
**SAY:**
> "One click to acknowledge, and it's recorded who handled it and when."

**DO:** Scroll down to **Detection history**.
**SEE:** Your reads at the top, including `MH 01 CT 8020` with its plate crop.
**SAY:**
> "Every plate ever read is logged: time, camera, confidence, and a photo of the plate. Every decision can be traced back to its evidence."

---

### 9 · Vehicle Track — 3:00 to 3:20
**DO:** Click **Vehicle Track**. The plate `GJ01AB1234` is already filled in. Click **Reconstruct**.
**SEE:** **STOLEN**, the number of sightings, first seen and last seen, a numbered route on the map, and a timeline table.
**DO:** Trace the route on the map with the mouse, from Valsad up to Gandhinagar. Then point at **Download CSV**.
**SAY:**
> "Now the investigation. Type a plate and PRAHARI rebuilds its journey: first seen at the Valsad toll, up the highway through Surat and Ahmedabad to Gandhinagar, with exact times. One click exports it for the case file. And the sighting we just made is already on the list."

*(If asked: the highway sightings are sample records; the last one is our live detection.)*

---

### 10 · Analytics & Gaps — 3:20 to 3:27
**DO:** Click **Analytics & Gaps**.
**SEE:** Figures for offline cameras and short retention, and bar charts by department.
**SAY:**
> "Finally, it audits itself: which cameras are down, and which don't keep enough footage."

---

### 11 · Close — 3:27 to 3:40
**DO:** Click **Operations**. Stop moving the mouse.
**SAY:**
> "Today PRAHARI reads plates from camera frames. Next, it reads them directly from live video and checks each car across several frames, which removes exactly the doubt you saw earlier. PRAHARI turns the cameras the state already owns into one network that can find a stolen car, and shows its evidence instead of guessing. Thank you."

---

## If you go over time
- **First:** cut step 10, Analytics.
- **Second:** in step 3, skip the filter and search, and just click **Open**.
- **Third:** in step 4, keep only the second face paragraph (the privacy rule).
- **Never cut steps 5, 6 and 7.** They are the product.

## Never do on camera
- **Don't click "Next cameras"** on Vehicle Track. It shows a wrong distance.
- **Don't open any camera except `CAM-OWN-001`.** The others have no live feed on this machine.
- **Don't click Enroll.** Face identification is off until Phase 2, and enrolling permanently adds images.
- **Don't say "live video ANPR" or "connected to VAHAN".** Neither is built yet.
- **Don't claim face-recognition accuracy.** Talk about the enrolment and the own-camera rule only.
- **Don't say "X% accurate".** If asked, say *"on our 21-image test set, 61.5% of the plates we verified were correct, and we cut wrong plates from 9 to 5."*
