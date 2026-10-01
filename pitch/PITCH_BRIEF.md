# PITCH_BRIEF.md — Delta Cup 2026 online pitch, 21 Sep 2026

Content for the slides is in **English** (copy it onto the slides as written). Guidance on how to organise and present is in **Thai**. Format: 10 min presentation + 5 min Q&A, five mandatory sections. Every number here comes from the repo (MODEL.md 0.4.4, RESULTS_v04.md, RUNBOOK.md §E, crosscheck log of 18 Sep); sources for outside facts are in §9.

---

## 0. วิธีใช้เอกสารนี้ (อ่านก่อน)

- เอกสารนี้คือ "วัตถุดิบ" สำหรับทำสไลด์ ไม่ใช่สคริปต์ที่ต้องท่อง ข้อความใต้หัวข้อ **On the slide** ให้วางลงสไลด์ได้เลย ส่วน **Speaker says** เป็นแนวพูด ปรับสำนวนเป็นของตัวเองได้ แต่ **ห้ามเปลี่ยนตัวเลข**
- โครงสร้าง: 11 สไลด์ + เดโม HTML 1 ช่วง ตามหัวข้อบังคับ 5 ข้อของ Delta เรียงตามลำดับเดิม กรรมการจะให้คะแนนตามหัวข้อ จึงควรใส่ชื่อหัวข้อของ Delta ไว้มุมสไลด์ให้เห็นว่าเราตอบครบ
- งบเวลา (รวม 10:00):

| ช่วง | หัวข้อ Delta | สไลด์ | เวลา |
|---|---|---|---|
| 1 | Project Overview & Problem Statement | 1–2 | 1:30 |
| 2 | Proposed Solution & System Architecture | 3–5 | 2:30 |
| 3 | Prototype / Demonstration & Proof of Concept | เดโม HTML + 6–7 | 3:15 |
| 4 | Innovation, Environmental Impact & Business Value | 8–9 | 1:30 |
| 5 | Project Roadmap & Development Plan | 10–11 | 1:15 |

- หลักการออกแบบสไลด์: หนึ่งสไลด์ = หนึ่งข้อความหลัก (เขียนเป็นประโยคที่หัวสไลด์ ไม่ใช่แค่ชื่อหัวข้อ), ตัวเลขใหญ่ไม่เกิน 3 ตัวต่อสไลด์, ตัวอักษรไม่เล็กกว่า 20 pt เพราะนำเสนอผ่านการแชร์หน้าจอ, ใช้สีให้ตรงกับเดโม: **น้ำเงิน = Feeder node, ส้ม = Rack node, เขียว = HOLD, แดง = TRIP** ตลอดทั้งเด็ค
- ช่วงเดโมคือหัวใจของการพิตช์ ใช้ไฟล์ `pitch/two_node_explainer.html` เปิดใน Chrome/Edge กด F11 แล้วแชร์หน้าต่างนั้น กด → เพื่อไปขั้นถัดไป กด N เพื่อดูโน้ตผู้พูด (ปิดโน้ตก่อนแชร์จอ) **ซ้อมสลับจากสไลด์ไปเบราว์เซอร์และกลับอย่างน้อย 3 รอบ**
- ความซื่อสัตย์ของตัวเลขคือจุดแข็งของทีม กรรมการจาก Delta เป็นวิศวกร ถ้าเราพูดเกินจริงหนึ่งจุด ความน่าเชื่อถือของทั้งงานจะหายไป ดูรายการ "ห้ามพูด" ใน §7

---

## 1. The story in one breath (everyone on the team should be able to say this)

> AI training makes a rack's power jump by half its rating in milliseconds, thousands of times a day. To a DC breaker that looks like a fault, so operators must choose between nuisance trips that kill a training run and loose settings that miss real faults. We show that a relay on the 800 V feeder *cannot* see faults on the rack's 48 V side, because the converter turns them into ordinary load steps. With a second low-cost sensing node on the rack busbar, and a relay that learns the rhythm of the training job, false trips below 0.1 % on 30 000 normal events; about 0.3 % missed faults on each side; decision window 0.25 ms, with the physics reproduced independently in Simscape.

Three numbers to remember: **false trips below 0.1 % on 30 000 normal events; about 0.3 % missed faults on each side; decision window 0.25 ms · 8 of 8 Simscape cases within 1 %.**

---

## 2. Slide by slide

### Section 1 — Project Overview & Problem Statement (1:30)

**Slide 1 — Title**
- *On the slide:* Intelligent DC Fault Discrimination for 800 VDC AI Data Center Power Distribution · Team [TEAM NAME] · Energy Track · Thailand · [UNIVERSITY] · advisor Prof. Supachai [SURNAME] · team members
- *Visual:* `figures/architecture.png` or the single-line diagram from the demo (screenshot of step 1).
- *Speaker says (15 s):* who we are, one sentence: "We work on the protection relay for the next generation of AI data centers."
- *แนวทาง:* ไม่ต้องอ่านชื่อทุกคน แนะนำทีมสั้น ๆ แล้วเข้าเรื่องทันที

**Slide 2 — "Normal AI work looks like a fault, and the industry says so"**
- *On the slide:*
  - AI racks are moving to 800 VDC: up to 5 % better end-to-end efficiency, racks from 100 kW to over 1 MW (NVIDIA). Delta already ships an 800 VDC 660 kW power rack.
  - Every GPU in a training job steps its power in lockstep, every 0.3–10 s. Oracle: these synchronized swings "can trip upstream protections".
  - A nuisance trip stops a synchronous job: "a single GPU failure may require a restart of the entire job" (Meta, Llama 3: 419 unexpected interruptions in 54 days on 16 384 GPUs).
  - A missed fault on a bus backed by farads of storage is a fire.
  - NVIDIA's own 800 VDC article: fault detection in VDC systems "is a key area for innovation".
- *Visual:* left, a measured-style square-wave rack power trace (use `figures/benign_vs_fault.png` or demo step 2); right, the target market line: **hyperscale AI data centers in Thailand's EEC; rack power-shelf and solid-state-breaker vendors.**
- *Speaker says (75 s):* the dilemma: set the breaker tight and it trips on the customer's own workload; set it loose and weak faults hide. "With thresholds at the edge of normal behaviour, 72 % of high-impedance faults hide inside the normal envelope in our data."
- *แนวทาง:* สไลด์นี้ต้องทำให้กรรมการรู้สึกว่า "ปัญหานี้จริงและเป็นปัญหาของ Delta เอง" ใช้คำพูดของ NVIDIA/Oracle/Meta เป็นหลักฐาน ไม่ใช่ความเห็นของเรา พูดให้ช้าและชัดตรงประโยค 72 %

### Section 2 — Proposed Solution & System Architecture (2:30)

**Slide 3 — "A relay on the feeder cannot see a fault behind the converter"** (core concept)
- *On the slide:*
  - The rack converter stands between the fault and the feeder. A 48 V fault reaches the feeder as a **load step** (high-impedance fault) or an **idle drop** (bolted fault). No fault signature survives.
  - So protection needs a second sensor on the rack busbar, downstream of the storage.
  - Value proposition: **no nuisance trips on real workload, no blind spot on the 48 V side, decision in 0.25 ms.**
- *Visual:* the real-waveform figure `figures/fig5_simscape_overlay.png` (top two rows), or demo screenshot of step 5/6 side by side: feeder = smooth 1.4 ms ramp, rack = 1.4 p.u. in 0.06 ms.
- *แนวทาง:* นี่คือ "ข้อค้นพบ" ของงาน ไม่ใช่แค่ไอเดีย เน้นว่าเป็นผลจากแบบจำลอง และยืนยันซ้ำด้วย Simscape

**Slide 4 — System architecture (block diagram, mandatory)**
- *On the slide (diagram):* Source → **Feeder Relay Node (FRN)** on i_L, v_bus → 800 V bus → rack converter → storage bank → **Rack Sensing Node (RSN)** on busbar current and v_out → 48 V bus → GPUs. Isolated CAN / EtherCAT link between the nodes; trip outputs to the solid-state breaker (feeder) and the shelf breaker (rack); telemetry upstream.
- *Three layers (put as a strip under the diagram):*
  - **Layer 1, microseconds:** analog thresholds for bolted faults. No ML needed there, and we say so.
  - **Layer 2, 0.25 ms:** gradient-boosted trees on observable-only features: early current rise, voltage lead, dynamic resistance, spectral floor, and *was this step scheduled?*
  - **Layer 3, workload timescale:** hold-and-monitor for the ambiguous residue (schedule violation or I²t). Designed, not yet simulated.
- *Data flow:* 500 kSa/s fast stream → onset detection → causal features over time windows → classifier → TRIP / HOLD / ALERT. 5 kSa/s slow stream → cadence learner (iteration period and phase) running continuously.
- *แนวทาง:* ใช้ `figures/fig3_sensing_architecture.png` เป็นฐานแล้ววาดใหม่ให้สีตรงกับเดโม อย่าใส่สมการ ให้เห็น input / output / การตัดสินใจ ตามที่ Delta กำหนดว่า "inputs, outputs, control loops, data flow"

**Slide 5 — Product & hardware integration**
- *On the slide (one node = one small PCB):*

| Block | Choice | Why |
|---|---|---|
| Current sensing | shunt + isolated amplifier (48 V busbar); Hall/fluxgate transducer (800 V feeder) | bandwidth ≥ 200 kHz |
| Voltage sensing | divider + isolated amplifier | same |
| ADC | 14-bit SAR, 500 kSa/s, 2 channels | our sweep: 12–16 bits and 100 kSa/s–2 MSa/s made **no measurable difference** to the decision; this spec is margin |
| MCU | STM32H7-class (Cortex-M7, 480–550 MHz) | fixed-point tree inference; design estimate tens of µs, **to be measured** |
| Link | isolated CAN-FD (EtherCAT as option) | combined decision + schedule check |
| Output | trip line to SSCB gate driver / shelf breaker | the decision, not the breaker, is the bottleneck |

- *Say clearly:* "The node is a design. Firmware and the 48 V testbed are the next phase." Where it fits Delta: it goes **inside the power shelf Delta already ships**; adjacency, not critique.
- *แนวทาง:* ตารางนี้พอแล้ว ไม่ต้องใส่เบอร์ชิ้นส่วนละเอียด ถ้ากรรมการถามค่อยตอบจาก §4

### Section 3 — Demonstration & Proof of Concept (3:15)

**Demo — `two_node_explainer.html` (about 2:15, 8 steps)**
- Suggested pacing: step 1 (15 s) → 2 (20 s) → 3 (20 s) → 4 (15 s, let the sweep play) → 5 (25 s) → 6 (20 s) → 7 (20 s) → 8 is the same content as Slide 6, so **either stop the demo at step 7 and show Slide 6, or end on step 8 and skip Slide 6.** Do not show both.
- The traces are real simulation output, the same cases the Simscape model reproduced. Say so once: "These are not drawings; they are the simulated waveforms, replayed about 600 times slower."
- *แนวทาง:* ให้คนเดียวเป็นทั้งคนกดและคนพูดในช่วงนี้ จะได้จังหวะตรงกัน ถ้าการแชร์จอมีปัญหา ให้ใช้ภาพสกรีนช็อต 8 ภาพที่เตรียมไว้ในสไลด์สำรองท้ายเด็ค (ต้องเตรียม)

**Slide 6 — Validation & performance data** (skip if the demo ended on step 8)

| Relay | False trips on normal work | Missed 800 V faults | Missed 48 V faults |
|---|---|---|---|
| Feeder node alone | TBD | TBD | cannot see them |
| Rack node alone | TBD | TBD | TBD |
| **Feeder + rack** | **0.09 %** | **0.33 %** | **0.29 %** |

- Footer: 36 000 simulated events (30 000 normal, 6 000 faults), segments 100 kW–1 MW, 5-fold cross-validation × 10 seeds, threshold calibrated on held-out data at a 0.1 % budget. Missed high-impedance 800 V faults 0.99 %. Same result at the 0.25 ms decision window.
- *แนวทาง:* ชี้ให้เห็นว่า "แต่ละโหนดมีจุดบอดของตัวเอง รวมกันแล้วปิดจุดบอดได้" คือประโยคเดียวที่ต้องพูดกับตารางนี้

**Slide 7 — "How do we know the simulator is right?" + scaling assumptions**
- *On the slide, left (proof):*
  - 9 validation checks against analytic solutions must pass before any data is generated.
  - **Independent re-implementation in Simscape Electrical: 8 of 8 cases within the 1 % criterion, worst 0.4 %; breaker-edge timing matched to 0.00 µs.** (figure: `fig5_simscape_overlay.png`, bottom row with the ±1 % band)
  - Predictions are written down before every run. Two of our own modelling errors and one numerical defect were caught this way, and are recorded, not hidden.
- *On the slide, right (scaling, mandatory):*
  - All quantities are per-unit of the segment rating; the dataset sweeps 100 kW–1 MW and about 30 other system parameters.
  - Train on segments below 400 kW, test above: the workload-aware relay keeps its advantage (directional test).
  - The planned bench testbed (48 V → 12 V, a few hundred watts) keeps the same dimensionless ratios: fault time constant vs sampling, fault resistance vs V/I_limit, storage energy vs load step.
- *แนวทาง:* สไลด์นี้คือคำตอบล่วงหน้าของคำถาม "เป็นแค่ simulation เชื่อได้อย่างไร" อาจารย์ศุภชัยให้ความสำคัญกับ Simscape มากที่สุด ให้เวลากับภาพ overlay ประมาณ 20 วินาที

### Section 4 — Innovation, Environmental Impact & Business Value (1:30)

**Slide 8 — Key innovations vs existing solutions**

| Existing approach | Limit | What we add |
|---|---|---|
| Magnitude / di/dt thresholds | 72 % of high-Z faults inside the normal envelope at zero false trips; still 57 % at 0.26 % false trips | physics features in the first 0.25 ms |
| Faster solid-state breakers | fast, but blind: speed does not tell a load step from a fault | the decision that tells the breaker when |
| Ask the GPU / scheduler | GPU telemetry latency 1–100 ms, too slow for protection | cadence learned from the bus current itself |
| Feeder-only protection | cannot see 48 V faults through the converter | the two-node architecture, quantified |

- One line under the table: **Method is part of the innovation: pre-registered predictions, an independent Simscape cross-check, failures published.**

**Slide 9 — Sustainability, energy and cost**
- *On the slide:*
  - **Unlocks 800 VDC:** up to 5 % end-to-end efficiency (NVIDIA). For a 10 MW AI hall that is about 4.4 GWh and roughly 2 000 tCO₂ per year on the Thai grid. Trustworthy protection is a condition for deploying it.
  - **Avoided waste per nuisance trip** (illustrative): E = P_job × (checkpoint interval / 2 + restart time). A 10 MW synchronous job, 30 min checkpoints, 10 min restart → about 4 MWh and about 1.9 tCO₂ thrown away per trip.
  - **The alternative costs energy:** hiding workload swings by holding a GPU power floor at 90 % costs 10.5 % extra energy on a measured trace (Choukse et al.). A relay that tolerates real workload reduces the pressure to do that.
  - **Cost:** estimated BOM about US$100–200 per node in prototype quantity (§4), against a rack worth millions of baht.
- *แนวทาง:* ต้องพูดคำว่า "illustrative" หรือ "ตัวอย่างการคำนวณ" ให้ชัด เพราะตัวเลข 4 MWh มาจากสมมติฐานของเรา ไม่ใช่ค่าที่วัดได้ ส่วน 5 % และ 10.5 % เป็นตัวเลขจากแหล่งอ้างอิง เชื่อมกับวิสัยทัศน์ "Smarter. Greener. Together." ในประโยคปิดสไลด์

### Section 5 — Roadmap & Development Plan (1:15)

**Slide 10 — Roadmap to the Regional Final (14 Nov 2026)**

| Weeks | Work | Output |
|---|---|---|
| 22 Sep – 4 Oct | regenerate dataset on core 0.4.4; 30 000-normal-event run to bound the false-trip rate below 0.1 %; Layer 3 study; professor's review | RESULTS_final.md |
| 5 – 18 Oct | order parts; sensing node on an STM32H7 board; port feature extraction and tree inference to C | firmware v0, latency measured |
| 19 Oct – 1 Nov | bench testbed (48 V → 12 V converter, storage bank, switched load, fault injection); replay simulated waveforms into the node through a DAC (hardware-in-the-loop) | measured vs simulated features |
| 2 – 8 Nov | record real normal steps and faults on the bench; compare with the simulator | one table: simulation vs bench |
| 9 – 14 Nov | video, live demo, rehearsal | final pitch |

- Risk line: "If the bench slips, hardware-in-the-loop replay still proves the firmware makes the decision in 0.25 ms."

**Slide 11 — Use of the US$500 grant + close**

| Item | US$ |
|---|---|
| Rack sensing node prototype: STM32H7 board, 14-bit 500 kSa/s ADC, current sense, PCB | 155 |
| Second node (feeder side), same design | 100 |
| Converter between "feeder" and "rack bus" (48 V → 12 V, ~300 W) | 40 |
| Storage bank (electrolytic, scaled) | 55 |
| Switched load that imitates GPU power steps (MOSFETs, driver, power resistors, heatsink) | 60 |
| Fault injection (MOSFET switch + low-ohm power resistors) | 40 |
| Safety and wiring: fuses, enclosure, emergency stop, connectors | 50 |
| **Total** | **500** |

- Closing line on the slide: **"Two low-cost nodes, one decision in 0.25 ms: no nuisance trips on AI workload, no blind spot behind the converter."**
- *แนวทาง:* ราคาเป็นค่าประมาณ ให้เพื่อนในทีมเช็กราคาจริงจากร้านในไทย/DigiKey ก่อนวันพิตช์ และปรับให้ผลรวมเท่ากับ 500 พอดี สมมติว่าห้องแล็บมีแหล่งจ่ายไฟ 48 V และออสซิลโลสโคปอยู่แล้ว ถ้าไม่มีต้องปรับตาราง

---

## 3. Numbers sheet (the only numbers allowed on slides)

| Quantity | Value | Source |
|---|---|---|
| Decision time | 0.25 ms after onset | RUNBOOK §E, window table |
| Two-node relay, threshold calibrated on held-out data (0.1 % budget) | 0.09 ± 0.01 % false trips; 0.33 ± 0.06 % missed 800 V; 0.29 ± 0.06 % missed 48 V; 0.99 ± 0.17 % missed high-Z | RUNBOOK §E |
| Two-node relay, default threshold, 0.25 ms window | 0.03 % false trips; 0.42 % missed 800 V; 1.25 % high-Z; 0.63 % missed 48 V | RUNBOOK §E, window table |
| Same at 1 ms | 0.04 / 0.46 / 1.36 / 0.53 % | RUNBOOK §E |
| Feeder alone (800 V duty) | TBD — v1xl6k node study | node study |
| Rack alone | TBD — v1xl6k node study | node study |
| Gray zone, 800 V high-Z faults, conventional thresholds | 57.8 % / 39.6 % at the 99.9th / 99th percentile of the benign envelope | Gate 2 percentile rows |
| Dataset | 36 000 events: 30 000 normal, 6 000 faults; 100 kW–1 MW | v1xl6k |
| Feeder vs rack view of the same 48 V fault | feeder 90 % in 1.4 ms; rack 90 % in 0.06 ms (normal step: 3.3 ms / 1.8 ms) | reference case high_z_48 |
| Simscape cross-check | 8 of 8 within 1 %; worst 0.42 %; UVLO edge at 0.00 µs | crosscheck_log 18 Sep |
| Front end | bits (12–16) and rate (100 kSa/s–2 MSa/s) not limiting | OPEN-12 |
| Alibi check | recovers about a third of laundered 48 V faults at the feeder | RESULTS_v04 §5 |

---

## 4. BOM detail (estimates, prototype quantity; verify prices before the pitch)

| Part | RSN (48 V busbar) | FRN (800 V feeder) |
|---|---|---|
| MCU board / MCU (STM32H7-class) | $15–30 | $15–30 |
| 14-bit 500 kSa/s SAR ADC, 2 ch | $10–20 | $10–20 |
| Current sensing | shunt + isolated amp, $10–20 | Hall / fluxgate transducer, $30–80 |
| Voltage sensing (divider + isolated amp) | $6–10 | $10–15 (HV divider) |
| Anti-alias filters, references, op-amps | $5–10 | $5–10 |
| Isolated CAN-FD + digital isolation | $7–10 | $7–10 |
| Isolated supply, regulators | $8–12 | $8–12 |
| 4-layer PCB, passives, connectors, housing | $25–35 | $25–35 |
| **Per node** | **about $90–150** | **about $110–220** |

In volume these fall substantially; we do not quote a volume price because we have not costed it.

## 5. Sustainability arithmetic (so anyone can defend it)

- 5 % of a 10 MW hall = 0.5 MW continuous = 4 380 MWh per year. At 0.45 tCO₂/MWh (Thai grid, TGO demand-side factor 0.44–0.48) ≈ 2 000 tCO₂ per year. This is the benefit of 800 VDC, which our work helps make deployable; it is **not** a saving we produce ourselves.
- One nuisance trip: 10 MW × (30 min / 2 + 10 min) = 10 MW × 0.417 h ≈ 4.2 MWh ≈ 1.9 tCO₂. The 30 min and 10 min are our assumptions; say so.

## 6. Hard questions (5 min Q&A)

1. **"0.06 % of what? How many false trips per day is that?"** Per detected event, on a deliberately hard Monte Carlo set: random systems, steps of 10–80 % of rating, ramps down to 0.5 ms, unscheduled drops. Only 8 of 5 001 normal events ever tripped, most in one of six seeds, and they sit at the fastest ramp in the sweep (0.5 ms). GPU power-smoothing features (GB200/GB300) program the ramp rate, so that corner should be rare on a real site. We do **not** yet have a per-day figure for one site; that needs the 30 000-event run, Layer 3 for the residue, and the testbed. This is the honest gap.
2. **"It is only simulation."** Yes. Nine analytic checks, an independent Simscape build that agrees within 1 % on 8 of 8 cases, predictions written before every run, failures recorded. Hardware is the next phase and the grant pays for it.
3. **"Why machine learning?"** For bolted faults we do not need it; Layer 1 thresholds handle them. ML is for the ambiguous ones: 72 % of high-impedance faults are inside the normal envelope.
4. **"Why not ask the GPU scheduler?"** Telemetry latency is 1–100 ms; the decision is needed in under 1 ms. The bus current is the only place the schedule is visible at protection speed.
5. **"Does Delta's battery backup on the 800 V bus change this?"** Yes, and we measured the direction: storage on the bus side feeds a bus fault and hides it from the feeder (gray zone 61 % → 71 %); storage behind the ORing stage does not. How Delta's BBU behaves into a fault is a question we would like to ask Delta.
6. **"Will it run on a microcontroller in 0.25 ms?"** Features are causal and time-windowed; tree inference is a few thousand comparisons. Our estimate is tens of microseconds on a Cortex-M7; measuring it is the first firmware milestone.
7. **"Series arcs?"** Reported as ALERT, not TRIP. Busbar arcs 91 % flagged, rack-path arcs 51 %: a stated weakness.
8. **"±400 V bipolar (OCP Mount Diablo)?"** Not modelled yet; listed as an open item.

*แนวทางช่วงถาม–ตอบ:* ตอบสั้น ตอบตรง ถ้าไม่รู้ให้บอกว่า "ยังไม่ได้ทำ และอยู่ในแผน" คำถามข้อ 1 มีโอกาสถูกถามสูงที่สุด ให้คนที่เข้าใจข้อมูลดีที่สุดเป็นคนตอบ

## 7. ห้ามพูด / Do not say

| Do not say | Say instead |
|---|---|
| "meets the 0.1 % target" | "0.06 % on 5 001 events; the 95 % interval reaches 0.18 %" |
| "under 1 % missed" | "about 0.4 % on the 800 V side and about 1 % on the 48 V side" |
| "bus capacitance hides faults" | "storage on the bus side hides them; storage behind the ORing stage does not" |
| "the feature separates normal from fault" | "it separates scheduled from unscheduled" |
| "we built / we tested the device" | "simulated; the node is designed; hardware is the next phase" |
| "Simscape proves the results" | "Simscape independently reproduces the physics the results are built on" |
| "saves 5 % energy" | "800 VDC saves up to 5 %; dependable protection is a condition for deploying it" |

## 8. Assets and who needs what

| Asset | Where | Status |
|---|---|---|
| Animated explainer | `pitch/two_node_explainer.html` | done; works offline |
| Python vs Simscape overlay | `figures/fig5_simscape_overlay.png` | done |
| Gray zone, discriminator, architecture, latency | `figures/fig1…fig4`, `architecture.png` | exist (dataset v1); fig1 still valid as an illustration, say "earlier dataset" if shown |
| 8 demo screenshots as backup slides | to make: open the HTML, screenshot each step | **to do** |
| Team name, university, member names, logo | Slide 1 | **to fill** |
| Prices checked | Slide 11, §4 | **to do** |

## 9. Sources for outside facts

- NVIDIA, *800 VDC Architecture Will Power the Next Generation of AI Factories* (developer blog): up to 5 % end-to-end efficiency; 100 kW to over 1 MW racks; "fault detection and serviceability in VDC systems is a key area for innovation".
- Meta, *The Llama 3 Herd of Models*, arXiv:2407.21783, §3.3.4: 16 384 GPUs, 54 days, 419 unexpected interruptions, > 90 % effective training time, "a single GPU failure may require a restart of the entire job".
- Choukse et al., *Power Stabilization for AI Training Datacenters*, arXiv:2508.14318: lockstep power swings; GPU telemetry latency 1–100 ms; 10.5 % energy overhead at a 90 % power floor.
- Oracle Cloud Infrastructure engineering blog (Mar 2026): synchronized swings "can trip upstream protections".
- Delta Electronics at NVIDIA GTC 2026: 800 VDC in-row 660 kW power rack with embedded battery backup.
- TGO (Thailand Greenhouse Gas Management Organization): grid emission factor 0.44–0.48 tCO₂/MWh (2020–2021 values; check the latest before the pitch).
- Everything else: this repository (EVIDENCE.md lists the workload sources in full).

---

## 10. เช็กลิสต์ก่อนวันที่ 21

- [ ] เติมข้อมูลทีมในสไลด์ 1 และตรวจตัวสะกดชื่ออาจารย์
- [ ] ทำสไลด์ตาม §2 ใช้สีตามเดโม ตัวอักษร ≥ 20 pt
- [ ] ตรวจราคาอุปกรณ์ ปรับตารางงบ 500 USD ให้ตรง
- [ ] ตรวจค่า emission factor ล่าสุดของ อบก. (TGO)
- [ ] สกรีนช็อตเดโม 8 ขั้น ใส่เป็นสไลด์สำรอง
- [ ] ซ้อมจับเวลา 3 รอบ เป้าหมาย 9:30 (เผื่อ 30 วินาทีสำหรับการสลับหน้าจอ)
- [ ] ทดสอบแชร์หน้าจอด้วยโปรแกรมประชุมที่จะใช้จริง: เบราว์เซอร์เต็มจอ เสียง และความลื่นของแอนิเมชัน
- [ ] แบ่งคนตอบคำถามใน §6 ล่วงหน้า
- [ ] ทุกคนพูด "เรื่องเล่าในหนึ่งลมหายใจ" (§1) ได้โดยไม่ดูโพย
