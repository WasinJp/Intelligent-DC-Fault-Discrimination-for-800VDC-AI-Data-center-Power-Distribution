function [AO, sync, brk_f, brk_r, sig] = dcsim_rt_hil_plant(trip_f, trip_r, fault_cmd, rearm_in, pv, fp, wp, cp, y0)
%DCSIM_RT_HIL_PLANT  One fixed step of the HIL demo model: the validated dcsim_rt_step core (MODEL.md 0.4.4 + breaker
%   element) wrapped with everything the real-time box needs and the desktop model had from the workspace:
%   a fault-scenario block, an in-model workload generator, re-arm, SYNC as a step count, AO scaling, ControlDesk signals.
%   The same function body runs in a plain MATLAB loop (rt_hil_check 'loop') and inside the MATLAB Function block of
%   dcsim_rt_hil.slx (build_dcsim_rt_hil), so the loop test IS the model test.
%
%   Revision 2026-10-16 (HIL model review): tier-1 jitter decided one edge ahead so an edge never steps P_gpu (#1);
%   tier-2 bursts phase-locked to the compute phase and never cut by it (#4); re-arm waits for an idle phase and ignores
%   a TRIP line still held high (#5, #6); conv_smooth tunable (#7, cp 13); brk_delay exact (#9); hold mode outputs the
%   last computed values (#10); arc band capped at 0.4/dt (#13); SIG 4 is event_active (#11).
%
%   Inputs (all doubles; the vectors are fixed-size — codegen):
%     trip_f, trip_r   node TRIP lines (0/1), sampled every step
%     fault_cmd        FAULT_CMD digital input (0/1); OR-ed with the ControlDesk parameter fp(8)
%     rearm_in         RE_ARM digital input (0/1); OR-ed with cp(7)
%     pv (36x1)        MODEL.md parameter vector, dcsim_rt_pv order (fault R/L entries 13 14 35 36 OVERRIDDEN by fp;
%                      smooth_on entry 20 OVERRIDDEN by cp(13))
%     fp (12x1)        fault scenario:  1 type (0 none | 1 800 V branch | 2 48 V branch | 3 series arc)
%                                        2 R_f [ohm]  3 L_f [H]  4 R_f48 [ohm]  5 L_f48 [H]  6 V_arc [V]
%                                        7 inception mode (0 now | 1 next tier-1 rising edge)   8 fault_trigger (ControlDesk, 0/1)
%                                        9 step_dP [W] benign load step applied at the trigger (0 = none; type 0 + step_dP = pure benign step)
%                                       10 step_ramp [s]
%                                       11 arc_m  noise modulation of V_arc (MODEL.md 5.4: 0.05-0.25; 0 = DC arc only)
%                                       12 arc_ramp [s] ignition ramp of V_arc (0.1e-3 .. 2e-3)
%                    Series-arc noise on the HIL: MODEL.md uses 1/f-weighted noise from 1 kHz to f_hi (up to 1 MHz),
%                    generated offline by FFT. A real-time box cannot do that, so the model makes a pink-like band
%                    (1 kHz .. min(100 kHz, 0.4/dt)) online: three independent unit-white sources (xorshift, 4-uniform
%                    sums) -> one-pole low-passes at 1 / 10 / min(100 kHz, 0.4/dt), each scaled to unit rms by the
%                    analytic one-pole variance, summed -> one-pole high-pass at 1 kHz -> fixed gain for unit rms.
%                    Approximation for the demo; the ALERT class rate is NOT quoted from the HIL (README_RT check (k)
%                    note 2b).
%     wp (13x1)        workload generator (MODEL.md 5.1, two tiers):  1 on (0/1)  2 P0 [W]  3 dP1 [W]  4 T1 [s]  5 duty1
%                                        6 ramp1 [s]  7 jit1 (fraction of T1)  8 dP2 [W] (0 = tier 2 off)  9 T2 [s]  10 duty2
%                                       11 ramp2 [s]  12 jit2 (fraction of T2)  13 seed (integer > 0)
%                    Tier 1: rising edges on a phase-locked grid (T1), each perturbed by U(-jit1, jit1)*T1 decided one
%                    edge ahead, so when an edge fires the ramp starts at that step (never a jump); the falling edge is
%                    duty1*T1 later with its own jitter. Tier 2: whole ramped bursts (duty2*T2 on, period T2 + jitter)
%                    phase-locked to each compute phase, first one 2-10 % of T1 after the edge, placed only if the burst
%                    ends before the phase ramps down (events.py two_tier_profile). max |dP_gpu| per step = dP/ramp*dt.
%     cp (13x1)        configuration:   1 dt [s]  2 qs_dt_min [s] (1.5e-6)  3 brk_delay [s]  4 uvlo_tol (0.5 on the HIL)
%                                        5 sync_width [s] (>= 20e-6)  6 AO full scale [V] (10 | 4.5 | 3.28)
%                                        7 rearm_cmd (ControlDesk, 0/1)  8 run_enable (0 = hold states, outputs held)
%                                        9..12 AO full scale in p.u. for AO1..AO4 (2.64 1.45 16.5 1.45)
%                                       13 conv_smooth (0/1): converter ramp-rate front end (MODEL.md 4.7 smooth_on)
%     y0 (11x1)        initial / re-arm state (dcsim_rt_hil_y0 or dcsim_rt_init)
%
%   Outputs:
%     AO (4x1)   i_L v_bus i_rack v_out scaled to [0, AO_fs] V   -> box AO1..AO4
%     sync       1 for sync_width after fault inception          -> box DO1
%     brk_f, brk_r   breaker states (1 closed, 0 open)           -> ControlDesk / BRK outports
%     sig (28x1) ControlDesk signals:
%        1 k (step count)   2 t [s]   3 P_gpu [W]   4 event_active (fault OR benign step started)   5 fault_pending
%        6 t_inception [s] (-1 none)   7 clear_f [us] (inception -> feeder breaker open, -1 none)   8 clear_r [us]
%        9 trip_f_seen (steps TRIP_f high)   10 trip_r_seen   11 wl_edge (1 on a tier-1 rising edge)
%       12 wl_phase (0 idle | 1 compute)   13 conv_on   14 load_on48   15 i_f [A]   16 i_f48 [A]   17 v_Cin [V]
%       18 P_in [W]   19 i_co [A]   20 v_c [V]   21 fault_type_active   22 V_arc applied [V]   23 rearm_count   24 n_faults
%       25 i_L [A]   26 v_bus [V]   27 i_rack [A]   28 v_out [V]   (physical units, unclipped — ControlDesk plots, check (i))
%
%   Fault lifetime: once active the fault stays on (the breaker isolates it) until RE_ARM. RE_ARM is latched and executed
%   at the next idle phase of the workload (immediately when the workload is off, or in the idle phase already): states
%   <- y0, supervisory state healthy, breakers closed, fault off, timers cleared; the workload generator keeps running so
%   the nodes keep their learned cadence. A TRIP line still high at re-arm is ignored until it has been seen low once.
%   Breaker: TRIP seen high for brk_delay (as whole steps, round(brk_delay/dt)) -> opens on the step after that count;
%   brk_delay = 0 -> opens on the step the TRIP is first seen.
%#codegen
persistent y st k brkf brkr tmr_f tmr_r k_inc k_tf k_tr nsync fault_on pending ftype_act ...
           wl_grid1 wl_k_r1 wl_k_f1 wl_next_r1 wl_k_r2 wl_k_f2 wl_next_r2 rng_s prev_trig prev_rearm rearm_pend ...
           n_rearm n_faults trip_f_ok trip_r_ok AO_last sig_last arc_lp arc_hp_x arc_hp_y
dt = cp(1);
if isempty(y)
    y = y0; st = [1.0; 1.0; 0.0; 0.0]; k = 0.0; brkf = 1.0; brkr = 1.0; tmr_f = 0.0; tmr_r = 0.0;
    k_inc = -1.0; k_tf = -1.0; k_tr = -1.0; nsync = 0.0; fault_on = 0.0; pending = 0.0; ftype_act = 0.0;
    rng_s = uint32(2463534242); n_rearm = 0.0; n_faults = 0.0; prev_trig = 0.0; prev_rearm = 0.0; rearm_pend = 0.0;
    trip_f_ok = 1.0; trip_r_ok = 1.0;
    arc_lp = zeros(3, 1); arc_hp_x = 0.0; arc_hp_y = 0.0;
    % workload: first tier-1 rising edge in the second half of the first period (the nodes see >= 1 idle phase first);
    % the jitter of every edge is drawn when the previous one fires (never applied backwards)
    rng_s = xs_seed(rng_s, wp(13));
    [wl_grid1, rng_s] = first_edge(wp(4), rng_s);
    [j0, rng_s] = xs_unif(rng_s);
    wl_next_r1 = wl_grid1 + (2.0 * j0 - 1.0) * wp(7) * wp(4);
    wl_k_r1 = -1e18; wl_k_f1 = -1e18;
    wl_next_r2 = 1e18; wl_k_r2 = -1e18; wl_k_f2 = -1e18;            % no burst before the first compute phase
    % hold-mode outputs before the first step: the initial state
    [AO_last, sig_last] = outputs(y, st, pv, cp, 0.0, dt, wp(2), 0.0, 0.0, -1.0, -1.0, -1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ...
                                  y0(2), y0(3), wp(2) / max(y0(10), 1.0), y0(10), zeros(15, 1));
end
if cp(8) < 0.5
    % run_enable off: states frozen, outputs held at the last computed values (wiring checks)
    AO = AO_last; sig = sig_last; sync = 0.0; brk_f = brkf; brk_r = brkr;
    return
end
t = k * dt;

% ---- workload generator (tier 1 iteration cadence, tier 2 bursts inside the compute phase) — before the re-arm block,
%      which needs this step's phase
P_gpu = wp(2); wl_edge = 0.0; wl_phase = 0.0;
if wp(1) > 0.5
    if t >= wl_next_r1
        wl_k_r1 = t;                                                   % the ramp starts now: no jump at the edge
        [jf, rng_s] = xs_unif(rng_s);
        wl_k_f1 = wl_k_r1 + wp(5) * wp(4) + (2.0 * jf - 1.0) * wp(7) * wp(4);
        wl_grid1 = wl_grid1 + wp(4);                                   % phase-locked grid (interval jitter, not drift)
        [jr, rng_s] = xs_unif(rng_s);
        wl_next_r1 = wl_grid1 + (2.0 * jr - 1.0) * wp(7) * wp(4);      % jitter of the NEXT edge, decided now
        wl_edge = 1.0;
        [u2, rng_s] = xs_unif(rng_s);
        wl_next_r2 = wl_k_r1 + (0.02 + 0.08 * u2) * wp(4);             % first burst 2-10 % of T1 into the phase
    end
    P_gpu = P_gpu + wp(3) * (ramp(t - wl_k_r1, wp(6)) - ramp(t - wl_k_f1, wp(6)));
    if t >= wl_k_r1 && t < wl_k_f1, wl_phase = 1.0; end
    if wp(8) > 0.0
        if t >= wl_next_r2
            if t + wp(10) * wp(9) + wp(11) <= wl_k_f1                  % the whole burst ends before the phase ramps down
                wl_k_r2 = t; wl_k_f2 = t + wp(10) * wp(9);
                [j2, rng_s] = xs_unif(rng_s);
                wl_next_r2 = max(wl_next_r2 + wp(9) + (2.0 * j2 - 1.0) * wp(12) * wp(9), wl_k_f2 + wp(11));
            else
                wl_next_r2 = 1e18;                                     % no more bursts in this phase
            end
        end
        P_gpu = P_gpu + wp(8) * (ramp(t - wl_k_r2, wp(11)) - ramp(t - wl_k_f2, wp(11)));
    end
end
idle = 1.0;
if wp(1) > 0.5 && (wl_phase > 0.5 || t < wl_k_f1 + wp(6)), idle = 0.0; end   % idle = compute phase over and ramped down

% ---- re-arm: latched on the edge (DI OR ControlDesk), executed in an idle phase so y0 (steady state at wl_P0) matches the load
rearm = 0.0; if rearm_in > 0.5 || cp(7) > 0.5, rearm = 1.0; end
if rearm > 0.5 && prev_rearm < 0.5, rearm_pend = 1.0; end
prev_rearm = rearm;
if rearm_pend > 0.5 && idle > 0.5
    y = y0; st = [1.0; 1.0; 0.0; 0.0]; brkf = 1.0; brkr = 1.0; tmr_f = 0.0; tmr_r = 0.0;
    k_inc = -1.0; k_tf = -1.0; k_tr = -1.0; nsync = 0.0; fault_on = 0.0; pending = 0.0; ftype_act = 0.0;
    trip_f_ok = 0.0; trip_r_ok = 0.0;                                  % a TRIP still held high must not reopen the breaker
    rearm_pend = 0.0; n_rearm = n_rearm + 1.0;
end
if trip_f < 0.5, trip_f_ok = 1.0; end
if trip_r < 0.5, trip_r_ok = 1.0; end

% ---- fault scenario: trigger (edge of DI OR ControlDesk) -> pending -> inception now / on the next rising edge
trig = 0.0; if fault_cmd > 0.5 || fp(8) > 0.5, trig = 1.0; end
if trig > 0.5 && prev_trig < 0.5 && fault_on < 0.5 && pending < 0.5
    pending = 1.0;
end
prev_trig = trig;
if pending > 0.5
    fire = 0.0;
    if fp(7) < 0.5 || wp(1) < 0.5, fire = 1.0; elseif wl_edge > 0.5, fire = 1.0; end
    if fire > 0.5
        pending = 0.0; fault_on = 1.0; ftype_act = fp(1); k_inc = k; n_faults = n_faults + 1.0;
        nsync = max(1.0, round(cp(5) / dt));
    end
end
% the benign step (if any) rides on the workload from inception, same ramp rule as the check-(i) step case
if k_inc >= 0.0 && fp(9) ~= 0.0
    P_gpu = P_gpu + fp(9) * ramp((k - k_inc) * dt, fp(10));
end
f_on = 0.0; f48_on = 0.0; V_arc = 0.0;
if fault_on > 0.5
    if ftype_act == 1.0, f_on = 1.0; end
    if ftype_act == 2.0, f48_on = 1.0; end
    if ftype_act == 3.0
        V_arc = fp(6) * ramp((k - k_inc) * dt, fp(12));
        if fp(11) > 0.0
            [eta, rng_s, arc_lp, arc_hp_x, arc_hp_y] = arc_pink(rng_s, arc_lp, arc_hp_x, arc_hp_y, dt);
            V_arc = V_arc * (1.0 + fp(11) * eta);
        end
    end
end
pv_eff = pv; pv_eff(13) = fp(2); pv_eff(14) = fp(3); pv_eff(35) = fp(4); pv_eff(36) = fp(5);
pv_eff(20) = 0.0; if cp(13) > 0.5, pv_eff(20) = 1.0; end

% ---- breakers: TRIP seen high for brk_delay steps -> open on the step after, latched until re-arm
n_dly = round(cp(3) / dt);
if trip_f * trip_f_ok > 0.5
    tmr_f = tmr_f + 1.0;
    if tmr_f > n_dly && brkf > 0.5, brkf = 0.0; k_tf = k; end
else
    tmr_f = 0.0;
end
if trip_r * trip_r_ok > 0.5
    tmr_r = tmr_r + 1.0;
    if tmr_r > n_dly && brkr > 0.5, brkr = 0.0; k_tr = k; end
else
    tmr_r = 0.0;
end

% ---- the physics (validated core + breaker element)
[y, st, o] = dcsim_rt_step(y, st, pv_eff, dt, P_gpu, V_arc, f_on, f48_on, brkf, brkr, cp(2), cp(4));

% ---- outputs
sync = 0.0;
if nsync > 0.0, sync = 1.0; nsync = nsync - 1.0; end
brk_f = brkf; brk_r = brkr;
event_on = fault_on; if k_inc >= 0.0, event_on = 1.0; end
[AO, sig] = outputs(y, st, pv, cp, k, dt, P_gpu, event_on, pending, k_inc, k_tf, k_tr, tmr_f, tmr_r, wl_edge, wl_phase, ...
                    ftype_act, V_arc, n_rearm, n_faults, o(2), o(3), o(15), o(10), o);
AO_last = AO; sig_last = sig;
k = k + 1.0;
end

% ======================================================================================================================
function [AO, sig] = outputs(y, st, pv, cp, k, dt, P_gpu, event_on, pending, k_inc, k_tf, k_tr, tmr_f, tmr_r, wl_edge, wl_phase, ...
                             ftype_act, V_arc, n_rearm, n_faults, i_L, v_bus, i_rack, v_out, o)
%#codegen
I_r = pv(2) / pv(1); I48 = pv(2) / pv(25);
fs = cp(6);
AO = [fs * i_L / (cp(9) * I_r); fs * v_bus / (cp(10) * pv(1)); fs * i_rack / (cp(11) * I48); fs * v_out / (cp(12) * pv(25))];
AO = min(max(AO, 0.0), fs);
t_inc = -1.0; cf = -1.0; cr = -1.0;
if k_inc >= 0.0
    t_inc = k_inc * dt;
    if k_tf >= 0.0, cf = (k_tf - k_inc) * dt * 1e6; end
    if k_tr >= 0.0, cr = (k_tr - k_inc) * dt * 1e6; end
end
sig = [k; k * dt; P_gpu; event_on; pending; t_inc; cf; cr; tmr_f; tmr_r; wl_edge; wl_phase; st(1); st(2); ...
       o(4); o(11); o(8); o(14); o(9); y(1); ftype_act; V_arc; n_rearm; n_faults; i_L; v_bus; i_rack; v_out];
end

function [eta, s, lp, hx, hy] = arc_pink(s, lp, hx, hy, dt)
%ARC_PINK  One sample of unit-rms pink-like noise, 1 kHz .. min(100 kHz, 0.4/dt), see header.
%   2026-10-16: each band gets its OWN white sample. With one shared sample the three low-passed bands are correlated
%   and the sum came out at 1.27 rms (19 % modulation at arc_m 0.15 — visible in the first arc demo plot). Independent
%   bands sum to unit rms; the 1 kHz high-pass then leaves 0.88, restored by the fixed gain 1.135 (rms 1.01 / 1.00 /
%   0.97 at 2 / 5 / 10 us, measured on the Python transliteration).
%#codegen
fc = [1e3; 1e4; min(1e5, 0.4 / dt)]; eta = 0.0;
for i = 1:3
    u = 0.0;
    for m = 1:4, [v, s] = xs_unif(s); u = u + v; end
    w = (u - 2.0) * 1.7320508075688772;                   % 4-uniform sum -> unit variance, near-gaussian
    a = exp(-2.0 * pi * fc(i) * dt);
    lp(i) = a * lp(i) + (1.0 - a) * w;
    g = sqrt((1.0 + a) / (1.0 - a));                      % one-pole LP of unit white has variance (1-a)/(1+a)
    eta = eta + g * lp(i);
end
eta = eta * (1.135 / 1.7320508075688772);                 % three independent equal-rms bands -> unit rms after the HP
ahp = exp(-2.0 * pi * 1e3 * dt);                          % one-pole high-pass at 1 kHz
hy = ahp * (hy + eta - hx); hx = eta; eta = hy;
end

function r = ramp(x, tr)
%#codegen
if tr <= 0.0
    if x >= 0.0, r = 1.0; else, r = 0.0; end
else
    r = x / tr; if r < 0.0, r = 0.0; end; if r > 1.0, r = 1.0; end
end
end

function [tn, s] = first_edge(T, s)
%#codegen
[u, s] = xs_unif(s);
tn = T * (0.5 + 0.5 * u);          % first rising edge somewhere in the second half of the first period
end

function s = xs_seed(s, seed)
%#codegen
sd = uint32(max(1.0, floor(seed)));
s = bitxor(s, sd);
if s == uint32(0), s = uint32(2463534242); end
for i = 1:8, [~, s] = xs_unif(s); end
end

function [u, s] = xs_unif(s)
%XS_UNIF  xorshift32 (Marsaglia), uniform in [0, 1). Deterministic, codegen-safe, no library calls.
%#codegen
s = bitxor(s, bitshift(s, 13));
s = bitxor(s, bitshift(s, -17));
s = bitxor(s, bitshift(s, 5));
u = double(s) / 4294967296.0;
end
