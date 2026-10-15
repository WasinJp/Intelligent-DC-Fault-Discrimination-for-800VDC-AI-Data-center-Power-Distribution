function D = dcsim_rt_hil_demo(scenario, dt, T_run)
%DCSIM_RT_HIL_DEMO  Desktop run of the HIL model (pure-MATLAB loop around dcsim_rt_hil_plant) with the workload ON and a
%   fault fired on the next workload edge; the nodes are emulated by a scripted TRIP at onset + 0.25 ms + 96 us (the
%   relay's budget), so the clearing time the model logs is what the box will log when the real nodes behave as budgeted.
%   The five-event demo sequence of HIL_DSPACE_UPDATE 3b:
%     'benign'    load step only (type 0, step_dP 0.4 P_rated)                 -> no trip expected
%     'highz800'  high-Z 800 V fault (R_f 3 ohm) inside a load step            -> feeder TRIP (source hits its current limit)
%     'highz800_hard'  the same with R_f 8 ohm: the fault's extra current is the size of the load step -> the demo's core event
%     'highz48'   high-Z 48 V fault (R_f48 20 mohm)                           -> rack TRIP
%     'bolted48'  bolted 48 V fault (R_f48 0.5 mohm)                           -> rack TRIP (Layer 1 class)
%     'arc'       series arc 25 V                                              -> ALERT, no TRIP (scripted none)
%   D = dcsim_rt_hil_demo('highz800')  (dt 5 us, 4 s run: ~2 workload periods before the fault)
%   Plots i_L, v_bus, i_rack, v_out (p.u.) and P_gpu around the inception, and prints the logged clearing time.
if nargin < 1 || isempty(scenario), scenario = 'highz800'; end
if nargin < 2 || isempty(dt), dt = 5e-6; end
if nargin < 3 || isempty(T_run), T_run = 4.0; end
P = project_paths();
[c, shared, ~] = load_case('high_z', P.data);        % any case: pv's shared part is what we need
pv = dcsim_rt_pv(shared, c);
dcsim_rt_hil_params(shared, dt);
P0 = 0.5 * shared.P_rated;
y0 = dcsim_rt_hil_y0(pv, P0, dt);
setp('wl_on', 1); setp('wl_P0', P0); setp('fault_mode', 1); setp('uvlo_tol', 0.5); setp('hil_dt', dt);
trip_node = 0;                                      % 0 none, 1 feeder, 2 rack
switch scenario
    case 'benign',   setp('fault_type', 0); setp('step_dP', 0.4 * shared.P_rated);
    case 'highz800', setp('fault_type', 1); setp('fault_Rf', 3.0); setp('fault_Lf', 2e-6); setp('step_dP', 0.4 * shared.P_rated); trip_node = 1;
    case 'highz800_hard', setp('fault_type', 1); setp('fault_Rf', 8.0); setp('fault_Lf', 2e-6); setp('step_dP', 0.4 * shared.P_rated); trip_node = 1;  % extra current ~0.3 p.u. = the load step itself
    case 'highz48',  setp('fault_type', 2); setp('fault_Rf48', 20e-3); setp('fault_Lf48', 0.5e-6); setp('step_dP', 0); trip_node = 2;
    case 'bolted48', setp('fault_type', 2); setp('fault_Rf48', 0.5e-3); setp('fault_Lf48', 0.2e-6); setp('step_dP', 0); trip_node = 2;
    case 'arc',      setp('fault_type', 3); setp('fault_Varc', 25.0); setp('step_dP', 0);
    otherwise, error('unknown scenario %s', scenario);
end
fp = getv({'fault_type','fault_Rf','fault_Lf','fault_Rf48','fault_Lf48','fault_Varc','fault_mode','fault_trigger','step_dP','step_ramp'});
wp = getv({'wl_on','wl_P0','wl_dP1','wl_T1','wl_duty1','wl_ramp1','wl_jit1','wl_dP2','wl_T2','wl_duty2','wl_ramp2','wl_jit2','wl_seed'});
cp = getv({'hil_dt','qs_dt_min','brk_delay','uvlo_tol','sync_width','ao_fs_V','rearm_cmd','run_enable','ao_pu_1','ao_pu_2','ao_pu_3','ao_pu_4'});
n = round(T_run / dt); k_trig = round(0.5 * T_run / dt);        % press the button halfway; the fault waits for the next edge
clear dcsim_rt_hil_plant
t = (0:n-1)' * dt; X = zeros(n, 5); AOl = zeros(n, 4); sy = zeros(n, 1); brk = ones(n, 2);
trip_f = 0.0; trip_r = 0.0; k_inc = -1; k_on = -1; k_trip = -1;
n_budget = round((0.25e-3 + 96e-6) / dt);
I_r = pv(2) / pv(1); I48 = pv(2) / pv(25);
tic;
for k = 0:n-1
    fc = double(k >= k_trig && k < k_trig + 2);
    [AO, s, bf, br, sig] = dcsim_rt_hil_plant(trip_f, trip_r, fc, 0.0, pv, fp, wp, cp, y0);
    X(k+1, :) = [sig(25), sig(26), sig(27), sig(28), sig(3)]; AOl(k+1, :) = AO'; sy(k+1) = s; brk(k+1, :) = [bf, br];
    if k_inc < 0 && sig(4) > 0.5, k_inc = k; end
    % emulated node: "onset" 10 us after inception (feeder) / 5 us (rack), TRIP after the budget, held
    if k_inc >= 0 && trip_node > 0 && k_on < 0
        k_on = k_inc + round((10e-6 * (trip_node == 1) + 5e-6 * (trip_node == 2)) / dt);
    end
    if k_on >= 0 && k >= k_on + n_budget
        if trip_node == 1, trip_f = 1.0; else, trip_r = 1.0; end
        if k_trip < 0, k_trip = k; end
    end
end
D.wall = toc; D.t = t; D.X = X; D.AO = AOl; D.sync = sy; D.brk = brk; D.k_inc = k_inc; D.clear_us = [sig(7), sig(8)];
fprintf('%s: inception at %.4f s (fired on the next workload edge), SYNC %d steps, TRIP scripted at inception + %.0f us, box-logged clearing time feeder %.1f us / rack %.1f us, %.1f s wall\n', ...
        scenario, k_inc * dt, sum(sy), (k_trip - k_inc) * dt * 1e6, sig(7), sig(8), D.wall);
% ---- figure around the inception
if k_inc >= 0
    w = (t >= (k_inc * dt) - 0.5e-3) & (t <= (k_inc * dt) + 3e-3); tt = (t(w) - k_inc * dt) * 1e3;
    figure('Name', ['dcsim_rt_hil demo: ' scenario]);
    subplot(3, 1, 1); plot(tt, X(w, 1) / I_r, tt, X(w, 3) / I48); grid on; ylabel('current (p.u.)'); legend('i_L feeder', 'i_{rack}'); title(sprintf('%s — SYNC at 0, breaker(s) open at %.1f / %.1f us', scenario, sig(7), sig(8)));
    subplot(3, 1, 2); plot(tt, X(w, 2) / pv(1), tt, X(w, 4) / pv(25)); grid on; ylabel('voltage (p.u.)'); legend('v_{bus}', 'v_{out}');
    subplot(3, 1, 3); plot(tt, X(w, 5) / pv(2), tt, brk(w, 1), tt, brk(w, 2), tt, sy(w)); grid on; ylabel('P_{gpu} / brk / sync'); xlabel('ms after inception'); legend('P_{gpu}', 'BRK_F', 'BRK_R', 'SYNC');
end
end

function setp(name, val)
p = evalin('base', name); p.Value = val; assignin('base', name, p);
end
function v = getv(names)
v = zeros(numel(names), 1);
for i = 1:numel(names), p = evalin('base', names{i}); v(i) = p.Value; end
end
