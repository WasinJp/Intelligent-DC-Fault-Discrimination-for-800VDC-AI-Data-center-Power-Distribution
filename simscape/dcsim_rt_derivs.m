function dy = dcsim_rt_derivs(y, pv, P_gpu, V_arc, fault_on, fault48_on, conv_on, load_on48, qs800, qs48)
%DCSIM_RT_DERIVS  Right-hand side of MODEL.md v0.4.4 — line-for-line port of dcsim.model_v04._derivs.
%   y  (11x1): v_c i_L v_C i_f i_Lin v_Cin P_cmd xi_v i_co v_out i_f48
%   pv (36x1): PARAM_KEYS order of dcsim/model_v04.py (see dcsim_rt_pv.m)
%   Flags are doubles 0/1 (codegen-friendly). The breaker element is applied one level up, in dcsim_rt_step,
%   by what it feeds in here (fault48_on, load_on48) and by holding i_L at zero.
%#codegen
V_ref = pv(1);  P_rated = pv(2);  R_droop = pv(3);  tau_c = pv(4);  C_bus = pv(5);  L_line = pv(6);
R_line = pv(7); R_esr = pv(8);    V_uvlo = pv(9);   I_lim = pv(12); R_f = pv(13);   L_f = pv(14);
arc_place = pv(15); L_in = pv(16); R_in = pv(17);   C_in = pv(18);  R_in_esr = pv(19);
smooth_on = pv(20); S_max = pv(21); tau_r = pv(22); p_fix = pv(23); k2 = pv(24);
V_ref48 = pv(25); C_out = pv(26); R_out_esr = pv(27); K_p = pv(28); K_i = pv(29); tau_i = pv(30);
I_lim_out = pv(31); V_uvlo48 = pv(32); R_f48 = pv(35); L_f48 = pv(36);

v_c = y(1); i_L = y(2); v_C = y(3); i_f = y(4); i_Lin = y(5); v_Cin = y(6);
P_cmd = y(7); xi_v = y(8); i_co = y(9); v_out = y(10); i_f48 = y(11);

if arc_place < 0.5, V_arc_load = V_arc; V_arc_line = 0.0; else, V_arc_load = 0.0; V_arc_line = V_arc; end

% ---- 48 V side
i_pol = 0.0;
if load_on48 > 0.5
    if v_out > V_uvlo48, i_pol = P_gpu / v_out; else, i_pol = P_gpu / V_uvlo48; end
end
if qs48 > 0.5 && fault48_on > 0.5
    i_f48 = (v_out + R_out_esr * (i_co - i_pol)) / (R_f48 + R_out_esr);
    if i_f48 < 0.0, i_f48 = 0.0; end
end
i_Cout = i_co - i_pol - i_f48;
v_out_node = v_out + R_out_esr * i_Cout;
if v_out_node < 0.0, v_out_node = 0.0; end
err = V_ref48 - v_out;
i_ref = K_p * err + K_i * xi_v;
sat = i_ref;
if sat > I_lim_out, sat = I_lim_out; end
if sat < 0.0, sat = 0.0; end
P_out_dem = v_out * sat;
if P_out_dem < 0.0, P_out_dem = 0.0; end
if conv_on > 0.5
    P_req = P_out_dem + (p_fix * P_rated + k2 * P_out_dem * P_out_dem / P_rated);
else
    P_req = 0.0;
end
dP_cmd = 0.0;
if smooth_on > 0.5
    r = (P_req - P_cmd) / tau_r;
    if r > S_max, r = S_max; end
    if r < -S_max, r = -S_max; end
    dP_cmd = r;
    if conv_on > 0.5, P_in_now = P_cmd; else, P_in_now = 0.0; end
    P_out_max = P_in_now - p_fix * P_rated;
    if P_out_max < 0.0, P_out_max = 0.0; end
    if v_out > 1.0, i_co_max = P_out_max / v_out; else, i_co_max = P_out_max / 1.0; end
    if sat > i_co_max, sat = i_co_max; end
else
    P_in_now = P_req;
end
if sat == i_ref, dxi = err; else, dxi = 0.0; end        % anti-windup: hold the integrator when clamped
if conv_on > 0.5, di_co = (sat - i_co) / tau_i; else, di_co = (0.0 - i_co) / tau_i; end
dv_out = i_Cout / C_out;
di_f48 = 0.0;
if fault48_on > 0.5 && qs48 < 0.5
    di_f48 = (v_out_node - R_f48 * i_f48) / L_f48;
    if v_out <= 0.0 && di_f48 < 0.0 && i_f48 <= 0.0, di_f48 = 0.0; end
end

% ---- input node
v_in_eff = v_Cin - V_arc_load;
if conv_on > 0.5
    if v_in_eff > V_uvlo, i_in = P_in_now / v_in_eff; else, i_in = P_in_now / V_uvlo; end
else
    i_in = 0.0;
end
i_Cin = i_Lin - i_in;
v_Cin_node = v_Cin + R_in_esr * i_Cin;

% ---- 800 V bus node
if qs800 > 0.5 && fault_on > 0.5
    i_f = (v_C + R_esr * (i_L - i_Lin)) / (R_f + R_esr);
    if i_f < 0.0, i_f = 0.0; end
end
i_C = i_L - i_Lin - i_f;
v_bus = v_C + R_esr * i_C;
if v_bus < 0.0, v_bus = 0.0; end

% ---- passive input filter with ORing
di_Lin = (v_bus - R_in * i_Lin - v_Cin_node) / L_in;
if i_Lin <= 0.0 && di_Lin < 0.0, di_Lin = 0.0; end
dv_Cin = i_Cin / C_in;

% ---- 800 V fault branch and feeder
di_f = 0.0;
if fault_on > 0.5 && qs800 < 0.5
    di_f = (v_bus - R_f * i_f) / L_f;
    if v_C <= 0.0 && di_f < 0.0 && i_f <= 0.0, di_f = 0.0; end
end
dv_c = (V_ref - R_droop * i_L - v_c) / tau_c;
di_L = (v_c - R_line * i_L - V_arc_line - v_bus) / L_line;
if i_L >= I_lim && di_L > 0.0, di_L = 0.0; end
if i_L <= 0.0 && di_L < 0.0, di_L = 0.0; end
dv_C = i_C / C_bus;

dy = [dv_c; di_L; dv_C; di_f; di_Lin; dv_Cin; dP_cmd; dxi; di_co; dv_out; di_f48];
end
