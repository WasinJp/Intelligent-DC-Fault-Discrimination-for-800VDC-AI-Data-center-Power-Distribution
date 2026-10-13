function R = run_rt_case(case_name, dt, mode, trip, uvlo_tol)
%RUN_RT_CASE  Run one check-(i) case through the fixed-step explicit model and score it with scripts/compare_simscape.py.
%   R = run_rt_case('step')                 pure-MATLAB loop at dt = 1 us (the reference grid)
%   R = run_rt_case('high_z_48', 10e-6)     same at 10 us (quasi-static rule active for stiff branches)
%   R = run_rt_case('bolted_48', 1e-6, 'slx')   through the Simulink wrapper dcsim_rt.slx (built if missing)
%   trip (optional, slx mode): struct with t (s, absolute), trip_f, trip_r columns -> drives the TRIP inports (demo).
%   uvlo_tol (optional, default 0): 0 = UVLO timers exactly as the Python core; 0.5 = grid-robust step counting (HIL).
%   Writes data/simscape/rt/dt_<x>us/sim_<case>.mat in the layout compare_simscape.py reads, runs the comparator
%   with the repo's .venv Python, and returns R.pass, R.worst_ex (worst excluded-RMS), R.txt (comparator output).
%   Nothing in this file touches the Simscape cross-check model or the Python core.
if nargin < 2 || isempty(dt), dt = 1e-6; end
if nargin < 3 || isempty(mode), mode = 'loop'; end
if nargin < 4, trip = []; end
if nargin < 5 || isempty(uvlo_tol), uvlo_tol = 0.0; end
P = project_paths();
[c, shared, ref] = load_case(case_name, P.data);           % also puts the case in the base workspace (harmless)
pv = dcsim_rt_pv(shared, c);
T = shared.T_record; t0 = c.t_event;
qs_dt_min = 1.5e-6;                                          % Python's floor: at 1 us the rule never fires (bit-identical)
outdir = fullfile(P.data, 'rt', sprintf('dt_%gus', dt * 1e6));
if ~exist(outdir, 'dir'), mkdir(outdir); end

switch mode
    case 'loop'
        n = round(T / dt);
        k_f  = round(t0 / dt); k_f_end = n;                  % fault_start_idx <= k < fault_end_idx, as run_uniform()
        f800 = double(c.fault_800V_active); f48 = double(c.fault_48V_active);
        [y, st] = dcsim_rt_init(c);
        t_abs = (0:n-1)' * dt;
        Pg = dcsim_rt_profile(c, shared, t_abs);
        obs = zeros(n, 15);
        tic;
        for k = 0:n-1
            f_on  = f800 * double(k >= k_f && k < k_f_end);
            f48on = f48  * double(k >= k_f && k < k_f_end);
            [y, st, o] = dcsim_rt_step(y, st, pv, dt, Pg(k+1), 0.0, f_on, f48on, 1.0, 1.0, qs_dt_min, uvlo_tol);
            obs(k+1, :) = o';
        end
        R.wall = toc;
        i_L = obs(:, 2); v_bus = obs(:, 3); i_rack = obs(:, 15); v_out = obs(:, 10);
        dbg = struct('dbg_i_f', obs(:, 4), 'dbg_i_f48', obs(:, 11), 'dbg_P_in', obs(:, 14), ...
                     'dbg_conv_on', obs(:, 6), 'dbg_load_on48', obs(:, 13), 'dbg_i_co', obs(:, 9), 'dbg_v_Cin', obs(:, 8));
    case 'slx'
        mdl = 'dcsim_rt';
        if ~exist(fullfile(P.root, 'simscape', [mdl '.slx']), 'file'), build_dcsim_rt(mdl, dt); end
        if ~bdIsLoaded(mdl), load_system(mdl); end
        set_param(mdl, 'FixedStep', num2str(dt), 'StopTime', num2str(T));
        assignin('base', 'pv', pv);
        assignin('base', 'cfg', [dt, qs_dt_min, 0.0, uvlo_tol]);   % [dt qs_dt_min brk_delay uvlo_tol]
        assignin('base', 'f800_on', double(c.fault_800V_active));
        assignin('base', 'f48_on', double(c.fault_48V_active));
        assignin('base', 't_event', t0);
        assignin('base', 'T_record', T);
        assignin('base', 'P_gpu_ts', [0, c.P0; t0 - 1e-9, c.P0; t0, c.P0; t0 + 2e-3, dcsim_rt_profile(c, shared, t0 + 2e-3); T, dcsim_rt_profile(c, shared, T)]);
        assignin('base', 'y0', dcsim_rt_init(c));
        if isempty(trip)
            set_param(mdl, 'LoadExternalInput', 'off');
        else
            assignin('base', 'ext_in', [trip.t(:), trip.trip_f(:), trip.trip_r(:)]);
            set_param(mdl, 'LoadExternalInput', 'on', 'ExternalInput', 'ext_in');
        end
        tic; simOut = sim(mdl, 'ReturnWorkspaceOutputs', 'on'); R.wall = toc;
        t_abs = simOut.get('t_abs'); i_L = simOut.get('i_L'); v_bus = simOut.get('v_bus');
        i_rack = simOut.get('i_rack'); v_out = simOut.get('v_out');
        dbg = struct('dbg_brk_f', simOut.get('brk_f'), 'dbg_brk_r', simOut.get('brk_r'), 'dbg_t_trip', simOut.get('t_trip'));
    otherwise
        error('run_rt_case:mode', 'mode must be ''loop'' or ''slx''');
end

% ---- window the record like run_case.m and save in the comparator's layout
m = (t_abs >= t0 - 0.2e-3 - 1e-9) & (t_abs <= t0 + 5e-3 + 1e-9);
S = struct('t', t_abs(m) - t0, 'i_L', i_L(m), 'v_bus', v_bus(m), 'i_rack', i_rack(m), 'v_out', v_out(m));
fn = fieldnames(dbg);
for q = 1:numel(fn)
    z = dbg.(fn{q});
    if size(z, 1) ~= numel(m) && size(z, 2) == numel(m), z = z.'; end
    if size(z, 1) == numel(m), S.(fn{q}) = z(m, :); end
end
simfile = fullfile(outdir, ['sim_' case_name '.mat']);
save(simfile, '-struct', 'S');

R.case = case_name; R.dt = dt; R.mode = mode; R.uvlo_tol = uvlo_tol; R.file = simfile;
if isempty(trip)
    % ---- open loop: score with the pre-registered comparator (unchanged criterion)
    py = P.python; if exist(py, 'file') ~= 2, py = 'python'; end
    cmd = sprintf('"%s" "%s" "%s" "%s"', py, P.compare, fullfile(P.data, ['ref_' case_name '.mat']), simfile);
    [~, txt] = system(cmd);
    R.txt = txt; R.pass = contains(txt, 'PASS') && ~contains(txt, 'FAIL');
    tok = regexp(txt, 'worst excluded ([0-9.e+-]+)', 'tokens', 'once');
    if isempty(tok), R.worst_ex = NaN; else, R.worst_ex = str2double(tok{1}); end
    fprintf('%-13s dt = %5.2f us  %-4s  %5.2f s  ->  %s\n%s', case_name, dt * 1e6, mode, R.wall, ternary(R.pass, 'PASS', 'FAIL'), txt);
else
    % ---- closed loop: the reference has no breaker, so the record is scored only UP TO the first breaker opening
    % (raw RMS per channel, p.u., on the reference grid). After the opening the two must differ — that is the demo.
    rf = load(fullfile(P.data, ['ref_' case_name '.mat']), 't', 'i_L', 'v_bus', 'i_rack', 'v_out');
    tb = [S.dbg_brk_f(:); S.dbg_brk_r(:)]; tt = [S.t(:); S.t(:)];
    kb = find(tb < 0.5, 1); if isempty(kb), t_open = S.t(end); else, t_open = tt(kb); end
    I_r = shared.P_rated / shared.V_ref; I48 = shared.P_rated / shared.V_ref48;
    sc = struct('i_L', I_r, 'v_bus', shared.V_ref, 'i_rack', I48, 'v_out', shared.V_ref48);
    w = rf.t(:) < t_open - 1e-6; R.worst_ex = 0; txt = '';
    for f = {'i_L', 'v_bus', 'i_rack', 'v_out'}
        b = interp1(S.t(:), S.(f{1})(:), rf.t(:));
        e = sqrt(mean((rf.(f{1})(w) - b(w)).^2)) / sc.(f{1}); R.worst_ex = max(R.worst_ex, e);
        txt = sprintf('%s  %-7s pre-trip RMS = %.2e\n', txt, f{1}, e);
    end
    R.pass = R.worst_ex <= 1e-2; R.txt = txt; R.t_open = t_open;
    fprintf('%-13s dt = %5.2f us  %-4s  %5.2f s  closed loop: breaker opens at %+.0f us; identical to the reference up to it -> %s (worst %.2e)\n%s', ...
        case_name, dt * 1e6, mode, R.wall, t_open * 1e6, ternary(R.pass, 'PASS', 'FAIL'), R.worst_ex, txt);
end
end

function s = ternary(c, a, b)
if c, s = a; else, s = b; end
end
