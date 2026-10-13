function [y, st, obs] = dcsim_rt_step(y, st, pv, dt, P_gpu, V_arc, f_on, f48_on, brk_f, brk_r, qs_dt_min, uvlo_tol)
%DCSIM_RT_STEP  One fixed step of MODEL.md v0.4.4 — the loop body of dcsim.model_v04.simulate, same operation order.
%   Adds the breaker element (MODEL.md 0.4.5 proposal): brk_f = 0 opens the feeder SSCB (i_L held at zero, the bus
%   discharges into whatever is on it); brk_r = 0 opens the rack SSCB between the storage bank and the load-side busbar
%   (load and 48 V fault branch isolated: i_pol = 0, i_f48 = 0, downstream node reads 0). Both closed = the published core.
%
%   y   (11x1) states                    st (4x1) [conv_on load_on48 uvlo_t uvlo48_t]
%   obs (15x1) the Python `out` row, same order: v_c i_L v_bus i_f i_in conv_on i_Lin v_Cin i_co v_out_node i_f48 i_pol
%              load_on48 P_in i_rack — i.e. the observables recorded for THIS step (state at the start of the step),
%              exactly as simulate() records them before advancing.
%   qs_dt_min: 1.5e-6 reproduces Python bit-for-bit at any dt (the quasi-static rule needs dt >= qs_dt_min AND
%              dt > 0.5 * tau_f). A real-time box with a step below 1.5 us never uses the rule; above it, the rule is
%              what keeps stiff fault branches finite.
%   uvlo_tol:  UVLO timers trip when the accumulated time >= t_uvlo - uvlo_tol*dt. 0 = exactly the Python core
%              (accumulate-and-compare; the trip lands one step late whenever the float sum of dt falls an ulp short of
%              t_uvlo — e.g. 101 us at dt = 1 us, 105 us at dt = 5*1e-6). 0.5 = half-step tolerance = step counting,
%              robust to the float value of dt (use on the HIL). Found 2026-10-10 by the rt_sweep ulp discrepancy.
%#codegen
R_esr = pv(8); V_uvlo = pv(9); t_uvlo_delay = pv(10); V_hyst = pv(11); R_f = pv(13); L_f = pv(14);
arc_place = pv(15); R_in_esr = pv(19); smooth_on = pv(20); p_fix = pv(23); k2 = pv(24); P_rated = pv(2);
R_out_esr = pv(27); V_uvlo48 = pv(32); t_uvlo48 = pv(33); V_hyst48 = pv(34); R_f48 = pv(35); L_f48 = pv(36);
qs_ratio = 0.5;

conv_on = st(1); load_on48 = st(2); uvlo_t = st(3); uvlo48_t = st(4);

% ---- breaker element: what the physics sees this step
if brk_f < 0.5, y(2) = 0.0; end                       % feeder SSCB open: no feeder current
f48_eff = f48_on; load_eff = load_on48;
if brk_r < 0.5, f48_eff = 0.0; load_eff = 0.0; y(11) = 0.0; end   % rack SSCB open: load and 48 V fault isolated

% ---- v0.4.4: quasi-static fault branches in coarse steps
q8 = 0.0; q4 = 0.0;
if f_on > 0.5 && dt >= qs_dt_min && dt > qs_ratio * L_f / (R_f + R_esr), q8 = 1.0; end
if f48_eff > 0.5 && dt >= qs_dt_min && dt > qs_ratio * L_f48 / (R_f48 + R_out_esr), q4 = 1.0; end
if q8 > 0.5
    y(4) = (y(3) + R_esr * (y(2) - y(5))) / (R_f + R_esr);
    if y(4) < 0.0, y(4) = 0.0; end
end
if q4 > 0.5
    i_pq = 0.0;
    if load_eff > 0.5
        if y(10) > V_uvlo48, i_pq = P_gpu / y(10); else, i_pq = P_gpu / V_uvlo48; end
    end
    y(11) = (y(10) + R_out_esr * (y(9) - i_pq)) / (R_f48 + R_out_esr);
    if y(11) < 0.0, y(11) = 0.0; end
end

% ---- observables for the supervisory logic (state at the start of the step)
i_pol0 = 0.0;
if load_eff > 0.5
    if y(10) > V_uvlo48, i_pol0 = P_gpu / y(10); else, i_pol0 = P_gpu / V_uvlo48; end
end
v_out_obs = y(10) + R_out_esr * (y(9) - i_pol0 - y(11));
if v_out_obs < 0.0, v_out_obs = 0.0; end
P_out0 = y(10) * y(9);
if P_out0 < 0.0, P_out0 = 0.0; end
if conv_on > 0.5, P_req0 = P_out0 + (p_fix * P_rated + k2 * P_out0 * P_out0 / P_rated); else, P_req0 = 0.0; end
if conv_on > 0.5
    if smooth_on > 0.5, P_in0 = y(7); else, P_in0 = P_req0; end
else
    P_in0 = 0.0;
end
if arc_place < 0.5, v_in_eff0 = y(6) - V_arc; else, v_in_eff0 = y(6); end
if conv_on > 0.5
    if v_in_eff0 > V_uvlo, i_in0 = P_in0 / v_in_eff0; else, i_in0 = P_in0 / V_uvlo; end
else
    i_in0 = 0.0;
end
v_bus_obs = y(3) + R_esr * (y(2) - y(5) - y(4));
if v_bus_obs < 0.0, v_bus_obs = 0.0; end
v_Cin_obs = y(6) + R_in_esr * (y(5) - i_in0);

% ---- UVLO state machines
if v_Cin_obs < V_uvlo
    uvlo_t = uvlo_t + dt;
    if uvlo_t >= t_uvlo_delay - uvlo_tol * dt, conv_on = 0.0; end
else
    uvlo_t = 0.0;
    if conv_on < 0.5 && y(6) > V_uvlo + V_hyst, conv_on = 1.0; end
end
if v_out_obs < V_uvlo48
    uvlo48_t = uvlo48_t + dt;
    if uvlo48_t >= t_uvlo48 - uvlo_tol * dt, load_on48 = 0.0; end
else
    uvlo48_t = 0.0;
    if load_on48 < 0.5 && y(10) > V_uvlo48 + V_hyst48, load_on48 = 1.0; end
end
if brk_r < 0.5, load_eff = 0.0; else, load_eff = load_on48; end

% ---- record (Python `out` order)
i_rack = i_pol0 + y(11);
v_out_rec = v_out_obs;
if brk_r < 0.5, i_rack = 0.0; v_out_rec = 0.0; end     % downstream of an open rack SSCB
obs = [y(1); y(2); v_bus_obs; y(4); i_in0; conv_on; y(5); y(6); y(9); v_out_rec; y(11); i_pol0; load_on48; P_in0; i_rack];

% ---- RK4
k1 = dcsim_rt_derivs(y,                 pv, P_gpu, V_arc, f_on, f48_eff, conv_on, load_eff, q8, q4);
k2_ = dcsim_rt_derivs(y + 0.5 * dt * k1, pv, P_gpu, V_arc, f_on, f48_eff, conv_on, load_eff, q8, q4);
k3 = dcsim_rt_derivs(y + 0.5 * dt * k2_, pv, P_gpu, V_arc, f_on, f48_eff, conv_on, load_eff, q8, q4);
k4 = dcsim_rt_derivs(y + dt * k3,       pv, P_gpu, V_arc, f_on, f48_eff, conv_on, load_eff, q8, q4);
y = y + (dt / 6.0) * (k1 + 2.0 * k2_ + 2.0 * k3 + k4);
if f_on < 0.5, y(4) = 0.0; end
if f48_eff < 0.5, y(11) = 0.0; end
if brk_f < 0.5, y(2) = 0.0; end
if y(3) < 0.0, y(3) = 0.0; end
if y(10) < 0.0, y(10) = 0.0; end
if y(6) < 0.0, y(6) = 0.0; end

st = [conv_on; load_on48; uvlo_t; uvlo48_t];
end
