# EVIDENCE.md — published measurements behind the workload model and the sensing-floor argument

Compiled 2026-09-08. Purpose: every assumption in MODEL.md §5 (workload) and every industry-direction claim in RESULTS.md should trace to a source here. Numbers below are what the sources say; the "→ model" lines are what they imply for dataset v1 and the pitch.

---

## 1. The lockstep-periodicity premise is measured, not assumed

**Primary source.** Choukse et al. (Microsoft, OpenAI, NVIDIA), *Power Stabilization for AI Training Datacenters*, arXiv:2508.14318, Aug 2025. https://arxiv.org/abs/2508.14318
- Figure 1 is a measured power trace from an at-scale training job on DGX-H100 racks. This is the citable real-world waveform.
- Every participating GPU runs in lockstep under bulk-synchronous parallelism; compute phases near TDP, all-reduce/communication phases near idle.
- Iteration-level swing period: "ranging from once per second or less, to once every tens of seconds, depending on the scale of the job."
- FFT energy of the measured trace is concentrated at 0.2–3 Hz (Figure 3).
- The paper's frequency-domain utility spec covers 0.1–20 Hz.

**Corroborating.**
- Oracle Cloud engineering blog, Mar 2026: single-GPU bulk-synchronous power "can look like a square wave (compute, pause, compute, pause)"; synchronized fluctuations stack across co-located nodes and "can trip upstream protections." https://blogs.oracle.com/cloud-infrastructure/behind-the-scenes-gpu-power-smoothing-ai-training
- arXiv:2606.22096 (grid resonance screening): "Every GPU in the job transitions between compute and idle in lockstep, so the aggregate power traces a square wave at the training iteration period. Production iteration periods of one to ten seconds."
- arXiv:2512.08076 (hybrid ESS mitigation): measured GPU-level trace with "quasi-periodic fluctuations" at ≈0.05 Hz plus "higher-frequency sub-fluctuations and stochastic variations"; "full-range transitions between idle and peak."
- arXiv:2508.16457 (wide-area oscillations): inter-iteration variability from GPU runtime jitter and kernel-scheduling delays — i.e. the jitter model has a physical basis, and it is *interval* jitter on a phase-locked cadence, not independent per-edge drift.

**→ model.** Two-tier cadence (OPEN-9):
- Tier 1, *iteration*: period 0.3–10 s (log-uniform), duty 0.3–0.7, full-range amplitude (idle → near TDP). This is the tier `phase_err` was conceived for.
- Tier 2, *sub-iteration*: the existing 20–200 ms sweep, physically the EDP-peak / micro-batch / pipeline-stage structure riding on tier 1 (see §2).
- Jitter (OPEN-10): interval jitter on a phase-locked cadence, ≤ 1–2 % of period, replacing independent per-edge ±5 %.
- Slow-stream history must cover ≥ 2.5 iterations: at 10 s that is 25 s. 5 kSa/s is sufficient for ms-scale edge timing; keep 50 kSa/s only for the last ~200 ms.

## 2. The sub-iteration tier has a name: EDP peaks

Choukse et al. §III-C: datacenter GPUs "allow power overshoots at shorter time-scales (50 ms), called electrical design power (EDP) peaks … while still maintaining the TDP at a granularity of 1 second." EDP minimum on GB200 is 1.1× TDP. "Usually the systems are designed such that the EDP peaks should not be visible beyond the rack power supply units (PSUs), depending on the system design, this may change."

**→ model.** The 20–200 ms sweep is not invented; it is the EDP-peak tier. Amplitude bound ≈ 1.1× TDP over the floor. Note the last clause: in an 800 VDC direct-to-rack architecture the AC-DC PSU that used to absorb EDP peaks is gone or moved, so **EDP peaks are more likely to be visible on the DC bus** — the tier matters more at 800 VDC than at 54 V.

## 3. GPU power smoothing bounds benign edges — helps discrimination

Choukse et al. §IV-B (GB200 feature, co-developed with Microsoft): programmable ramp-up / ramp-down rate (W/s), Minimum Power Floor (MPF) up to 90 % of TDP, stop delay. With MPF at 90 % and EDP at 1.1×, the GPU-level dynamic range is ≥ 20 % of TDP. Energy overhead at MPF 90 %: 10.5 % on the measured waveform.

NVIDIA GB300 NVL72 (developer blog / press, Jul 2025): startup power cap raises limits gradually; "GPU burn" ramps down smoothly at job end; same features backported to GB200.

**→ model.** Add a *smoothed* benign sub-population alongside the current *unsmoothed* one: step amplitude 0.10–0.35 p.u. (dynamic range 20–35 % of rating), ramp rate programmed rather than free. Smoothing is optional and configurable, so both regimes are realistic; the unsmoothed one is the harder case and stays. **The residual false trips in v0.2.2 (≥ 0.4 p.u. in < 1 ms) are exactly the events smoothing removes** — say so.

## 4. GPU telemetry cannot resolve the protection timescale

Choukse et al. §IV-A: NVIDIA datacenter GPUs expose in-band power/activity readings "at a minimum of 1–100 ms latency"; the reliable 100 ms counters are "too slow" even for the paper's own 20 Hz smoothing use-case.

**→ pitch.** A relay cannot ask the scheduler or the GPU whether the transient it is seeing is scheduled. At 0.25–1 ms decision windows, the *only* information source is the bus waveform itself. Learning the cadence from the bus current (which is what `phase_err` does) is not a convenience; it is the only place the cadence is observable at protection speed.

## 5. The industry paper asks for exactly this architecture

Choukse et al. §IV-E, "Fast telemetry-based backstop": a system that "continuously monitors power waveforms across the datacenter," uses "fine-grained, low-latency telemetry and real-time spectral analysis," and initiates "tiered responses" from soft throttling up to "circuit-level power shedding or coordinated disconnects."

**→ pitch.** That is a three-layer protection architecture described from the hyperscaler side: waveform monitoring (Layer 1/2 observables), spectral analysis (the `spec_i` / `spec_v` features), tiered response (TRIP / HOLD / ALERT). The paper's call to action §V-3 asks for OCP-level standards for "telemetry, load signaling, and sub-synchronous oscillation mitigation." The project's stated gap — no published, benchmarked, workload-aware discriminator — is the gap the paper's authors are asking someone to fill.

## 6. Energy storage on the DC bus is the direction, and it is the sensing floor

**NVIDIA GB300 NVL72 power shelf (LITEON), Jul 2025.** Electrolytic energy storage occupies half the shelf volume; ~65 J per GPU; charges during low-demand phases, discharges during peaks; a charge-management controller handles the cycling; 30 % reduction in grid-facing peak. Coming to GB200 NVL72 as well. https://developer.nvidia.com/blog/how-new-gb300-nvl72-features-provide-steady-power-for-ai/

**Choukse et al. §IV-C.** Rack level is the optimal placement for energy storage ("the AC-DC converters are present at the rack-level already, making that an optimal place for a DC block energy storage"). Requirements include the ability to "directly measure the load" and "switch modes between charging and discharging quickly."

**Delta Electronics, GTC 2026 (Mar 2026).** 800 VDC In-Row 660 kW Power Rack: six 110 kW power shelves, each with an embedded 80 kW Battery Backup Unit (480 kW BBU per rack); AC-DC efficiency up to 98 %. Microgrid stack with Solid State Transformer (MV AC → 800 VDC, 98.5 %) designed to "handle step-load changes on millisecond scales while maintaining tight voltage regulation." https://www.prnewswire.com/news-releases/delta-exhibits-energy-saving-solutions-for-800-vdc-in-next-gen-ai-factories-and-digital-twin-applications-built-on-omniverse-at-nvidia-gtc-2026-302715850.html

**→ model (OPEN-13).** Stored energy on the DC side — capacitor shelf or BBU — is a managed source that will feed a downstream fault for as long as its controller sees a load. Model as a controlled current source on the C_bus node with a droop/limit characteristic, in addition to the passive capacitance. The v0.2.2 C_bus finding (high-Z misses 1.5 % → 19 % across terciles) is the passive case; the managed case is expected to be worse for the feeder.

**→ pitch.** Delta's own 800 VDC rack puts 480 kW of battery backup on the bus. The sensing floor the project measured is a property of Delta's architecture. The per-rack sensing node is therefore an adjacency to a product Delta already ships, not an external critique of it.

## 7. Reference configuration for dataset v1 and the testbed scaling note

A "Delta-class" segment for the sweep and for figures: 660 kW rack, six 110 kW shelves, 800 VDC (bipolar ±400 V per OCP Mount Diablo is the alternative topology, OPEN-4), embedded storage on the bus. P_rated = 660 kW sits in the range the sanity gate currently under-samples (OPEN-11) — one more reason to fix the marginal.

## Open questions this evidence does not settle

- Absolute jitter of the iteration edge at rack level (ms? tens of ms?). The papers give qualitative descriptions; no number. Treat ≤ 1–2 % of period as the working assumption and mark it.
- Whether EDP peaks are visible on the 800 VDC bus in Vera Rubin / Kyber-class racks. The Choukse remark ("depending on the system design, this may change") is the only statement.
- The BBU controller's behaviour under a bus fault (does it current-limit, fold back, or hold voltage?). Determines OPEN-13 model form. Ask Delta if the finalist round gives access.
