function T = rt_hil_check(dt, mode, names)
%RT_HIL_CHECK  Check (i) through the HIL model: the eight cross-check cases run with the workload generator OFF, P0 from
%   the case, the fault scenario set from the case (type / R_f / L_f or R_f48 / L_f48; the 'step' cases as a benign step
%   of 0.4 P_rated over 2 ms), inception fired by FAULT_CMD at t_event, breakers never tripped — then scored by the
%   unchanged comparator (scripts/compare_simscape.py). Pass = identical to dcsim_rt within the pre-registered tolerance.
%   This is the built-in test of the fault-scenario block: if the wrapper is right, nothing changes.
%     T = rt_hil_check                 dt = 5 us, pure-MATLAB loop around dcsim_rt_hil_plant (fast; no Simulink)
%     T = rt_hil_check(5e-6, 'slx')    through dcsim_rt_hil.slx (built if missing) — what dSPACE compiles
%     T = rt_hil_check(1e-6, 'loop', {'step','high_z_48'})
%   Writes data/simscape/rt_hil/dt_<x>us/sim_<case>.mat and prints the PASS/FAIL table.
if nargin < 1 || isempty(dt), dt = 5e-6; end
if nargin < 2 || isempty(mode), mode = 'loop'; end
if nargin < 3 || isempty(names)
    names = {'step','step_sm','high_z','high_z_sm','high_z_48','high_z_48_sm','bolted_48','bolted_48_sm'};
end
P = project_paths();
outdir = fullfile(P.data, 'rt_hil', sprintf('dt_%gus', dt * 1e6));
if ~exist(outdir, 'dir'), mkdir(outdir); end
rows = cell(0, 5);
for j = 1:numel(names)
    [c, shared, ~] = load_case(names{j}, P.data);
    pv = dcsim_rt_pv(shared, c);
    [y0, ~] = dcsim_rt_init(c);
    T_rec = shared.T_record; t0 = c.t_event;
    % ---- parameters: workload off, fault from the case, benign step for the 'step' kind
    dcsim_rt_hil_params(shared, dt);
    setp('wl_on', 0); setp('wl_P0', c.P0);
    ftype = 0; if c.fault_800V_active, ftype = 1; end; if c.fault_48V_active, ftype = 2; end
    setp('fault_type', ftype); setp('fault_Rf', c.R_f); setp('fault_Lf', c.L_f); setp('fault_Rf48', c.R_f48); setp('fault_Lf48', c.L_f48);
    setp('fault_mode', 0); setp('fault_trigger', 0); setp('rearm_cmd', 0); setp('run_enable', 1);
    if strcmp(c.kind, 'step'), setp('step_dP', 0.4 * shared.P_rated); else, setp('step_dP', 0); end
    setp('step_ramp', 2e-3); setp('uvlo_tol', 0.0);                 % 0 = exactly the Python core, as rt_sweep's default
    setp('hil_dt', dt); setp('brk_delay', 0); setp('sync_width', 20e-6); setp('ao_fs_V', 10.0);
    fp = getv({'fault_type','fault_Rf','fault_Lf','fault_Rf48','fault_Lf48','fault_Varc','fault_mode','fault_trigger','step_dP','step_ramp'});
    wp = getv({'wl_on','wl_P0','wl_dP1','wl_T1','wl_duty1','wl_ramp1','wl_jit1','wl_dP2','wl_T2','wl_duty2','wl_ramp2','wl_jit2','wl_seed'});
    cp = getv({'hil_dt','qs_dt_min','brk_delay','uvlo_tol','sync_width','ao_fs_V','rearm_cmd','run_enable','ao_pu_1','ao_pu_2','ao_pu_3','ao_pu_4'});
    n = round(T_rec / dt); k_f = round(t0 / dt);
    switch mode
        case 'loop'
            clear dcsim_rt_hil_plant                                 % reset the persistent state
            t_abs = (0:n-1)' * dt; obs = zeros(n, 4); sync = zeros(n, 1);
            tic;
            for k = 0:n-1
                fc = double(k >= k_f && k < k_f + 2);                % FAULT_CMD edge at t_event
                [~, sy, ~, ~, sig] = dcsim_rt_hil_plant(0.0, 0.0, fc, 0.0, pv, fp, wp, cp, y0);
                obs(k+1, :) = sig(25:28)';                           % physical units, unclipped (SIG 25..28)
                sync(k+1) = sy;
            end
            wall = toc;
        case 'slx'
            mdl = 'dcsim_rt_hil';
            if ~exist(fullfile(P.root, 'simscape', [mdl '.slx']), 'file'), build_dcsim_rt_hil(mdl, dt, shared); end
            if ~bdIsLoaded(mdl), load_system(mdl); end
            assignin('base', 'pv', pv); assignin('base', 'y0', y0);
            t_in = (0:n-1)' * dt; u = zeros(n, 4); u(k_f+1:min(k_f+2, n), 3) = 1.0;      % FAULT_CMD edge at t_event
            assignin('base', 'ext_in', [t_in, u]);
            set_param(mdl, 'StopTime', num2str(T_rec), 'LoadExternalInput', 'on', 'ExternalInput', 'ext_in', ...
                      'SaveOutput', 'on', 'SaveTime', 'on', 'SaveFormat', 'Array');
            tic; simOut = sim(mdl, 'ReturnWorkspaceOutputs', 'on'); wall = toc;
            t_abs = simOut.get('tout'); yout = simOut.get('yout');     % columns: AO1..4, SYNC, BRK_F, BRK_R, SIG(1..28)
            obs = yout(:, 7 + (25:28));                                 % SIG 25..28 = i_L v_bus i_rack v_out, physical units
            sync = yout(:, 5);
        otherwise
            error('rt_hil_check:mode', 'mode must be ''loop'' or ''slx''');
    end
    % ---- window and save in the comparator's layout (as run_rt_case)
    m = (t_abs >= t0 - 0.2e-3 - 1e-9) & (t_abs <= t0 + 5e-3 + 1e-9);
    S = struct('t', t_abs(m) - t0, 'i_L', obs(m, 1), 'v_bus', obs(m, 2), 'i_rack', obs(m, 3), 'v_out', obs(m, 4), 'dbg_sync', sync(m));
    simfile = fullfile(outdir, ['sim_' names{j} '.mat']); save(simfile, '-struct', 'S');
    py = P.python; if exist(py, 'file') ~= 2, py = 'python'; end
    [~, txt] = system(sprintf('"%s" "%s" "%s" "%s"', py, P.compare, fullfile(P.data, ['ref_' names{j} '.mat']), simfile));
    pass = contains(txt, 'PASS') && ~contains(txt, 'FAIL');
    tok = regexp(txt, 'worst excluded ([0-9.e+-]+)', 'tokens', 'once');
    if isempty(tok), worst = NaN; else, worst = str2double(tok{1}); end
    k_sync = find(sync > 0.5, 1); t_sync = NaN; if ~isempty(k_sync), t_sync = (t_abs(k_sync) - t0) * 1e6; end
    fprintf('%-13s dt = %5.2f us  %-4s  %6.1f s  SYNC at %+.1f us  ->  %s (worst %.2e)\n', names{j}, dt * 1e6, mode, wall, t_sync, tern(pass, 'PASS', 'FAIL'), worst);
    rows(end+1, :) = {names{j}, dt * 1e6, mode, worst, pass}; %#ok<AGROW>
end
T = cell2table(rows, 'VariableNames', {'case', 'dt_us', 'mode', 'worst_excluded_rms', 'pass'});
fprintf('\nrt_hil_check: %d / %d PASS at %g us (%s). Scored on SIG 25..28 (physical units, unclipped); the AO outports are the same\nsignals scaled to ao_fs_V and saturated at the node full scale (16.5 / 2.64 / 1.45 p.u.).\n', sum(T.pass), height(T), dt * 1e6, mode);
end

function setp(name, val)
p = evalin('base', name); p.Value = val; assignin('base', name, p);
end
function v = getv(names)
v = zeros(numel(names), 1);
for i = 1:numel(names), p = evalin('base', names{i}); v(i) = p.Value; end
end
function s = tern(c, a, b)
if c, s = a; else, s = b; end
end
