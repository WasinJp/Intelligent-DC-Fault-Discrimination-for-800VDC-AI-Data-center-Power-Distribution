function [y0, st0, info] = dcsim_rt_hil_y0(pv, P0, dt, T_settle)
%DCSIM_RT_HIL_Y0  Steady state of the plant at constant GPU power P0, found by running the validated core itself (no
%   fault, breakers closed) from a rough analytic start until the states stop moving. For the check-(i) cases use
%   dcsim_rt_init (exact initial_state from cases.json); this is for the demo design point and any other P0 / seed.
%   pv: dcsim_rt_pv vector; dt: step [s] (default 5e-6); T_settle: run time [s] (default 0.3 s; the voltage loop is
%   20 Hz - 2 kHz, so 0.3 s covers the slowest). Returns y0 (11x1), st0 (4x1 healthy) and info.drift = max relative
%   state change over the last 10 % of the run (should be < 1e-6).
if nargin < 3 || isempty(dt), dt = 5e-6; end
if nargin < 4 || isempty(T_settle), T_settle = 0.3; end
V_ref = pv(1); V_ref48 = pv(25); R_droop = pv(3); R_line = pv(7); p_fix = pv(23); k2 = pv(24); P_rated = pv(2);
P_in = P0 + p_fix * P_rated + k2 * P0 * P0 / P_rated;
i_L = P_in / V_ref;
y = [V_ref - R_droop * i_L; i_L; V_ref - (R_droop + R_line) * i_L; 0.0; i_L; V_ref - (R_droop + R_line) * i_L; ...
     P_in; 0.0; P0 / V_ref48; V_ref48; 0.0];
st = [1.0; 1.0; 0.0; 0.0];
n = round(T_settle / dt); n_tail = max(round(0.1 * n), 1);
ymax = zeros(11, 1); ymin = inf(11, 1);
for k = 1:n
    [y, st] = dcsim_rt_step(y, st, pv, dt, P0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.5e-6, 0.5);
    if k > n - n_tail
        ymax = max(ymax, y); ymin = min(ymin, y);
    end
end
y0 = y; st0 = st;
info.drift = max((ymax - ymin) ./ max(abs(y0), 1e-9));
info.conv_on = st(1); info.load_on48 = st(2);
if st(1) < 0.5 || st(2) < 0.5
    warning('dcsim_rt_hil_y0:uvlo', 'UVLO tripped during settling at P0 = %.0f W - check P0 / pv', P0);
end
end
