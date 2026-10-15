function out = hil_quickstart(action, varargin)
%HIL_QUICKSTART  Everyday commands for dcsim_rt_hil on a desktop MATLAB. Keep this file in the model folder.
%
%   hil_quickstart('open')                         load model + data, update the diagram, print a summary
%   hil_quickstart('params')                       list the 38 tunable parameters with their current values
%   hil_quickstart('sets')                         list the parameter sets in hil_param_sets.csv
%   hil_quickstart('apply', 'demo_3_highz48')      apply one set to the parameters (base workspace)
%   hil_quickstart('defaults')                     reload dcsim_rt_hil_data.mat: every parameter back to its default
%   hil_quickstart('scaling')                      AO volts <-> physical units at the current ao_fs_V, + idle readings
%   R = hil_quickstart('sim', 'demo_2_highz800_hard')
%                                                  desktop run of the .slx: fault fired through FAULT_CMD at 20 ms,
%                                                  the node emulated by a scripted TRIP 0.35 ms after inception
%   R = hil_quickstart('sim', 'demo_4_bolted48', 'trip_after', 50e-6)      e.g. a Layer-1-like trip
%   R = hil_quickstart('sim', 'demo_1_benign_step', 'T_end', 0.03)         options: T_fire, T_end, trip_after,
%                                                                           trip ('auto' | 'feeder' | 'rack' | 'none')
%   hil_quickstart('check')                        the 8 reference cases through the .slx (needs the project repo)
%   hil_quickstart('export', 'R2023b')             save for an older release into .\handover\R2023b (+ data, files)
%
%   Notes. 'sim' always fires the fault at a fixed time (fault_mode forced to 0 for the run, restored after), on a flat
%   load, so the plot is short and repeatable; on the box the demo uses fault_mode 1 (inception on a workload edge).
%   'sim' passes inputs and run options to sim() only — the model itself is not modified.
%   2026-10-16, for the dSPACE handover (HIL_HANDOVER_README.md).
if nargin < 1 || isempty(action), action = 'open'; end
mdl  = 'dcsim_rt_hil';
here = fileparts(mfilename('fullpath'));
addpath(here);                                   % the PreLoadFcn finds the data file through which(mdl)
out  = [];
switch lower(action)

    case 'open'
        ensure_loaded(mdl, here);
        set_param(mdl, 'SimulationCommand', 'update');
        fprintf('%s loaded and updated: solver %s, step hil_dt = %g us, %d tunable parameters\n', mdl, ...
                get_param(mdl, 'Solver'), getp('hil_dt') * 1e6, numel(param_names()));
        fprintf('ports in : TRIP_feeder TRIP_rack FAULT_CMD RE_ARM   (0/1)\n');
        fprintf('ports out: AO1..AO4 [V]  SYNC  BRK_F  BRK_R  (0/1)  SIG (28 signals, ControlDesk only)\n');

    case 'params'
        ensure_loaded(mdl, here);
        nm = param_names();
        for i = 1:numel(nm)
            p = evalin('base', nm{i});
            fprintf('%-16s %-14.6g %s\n', nm{i}, p.Value, p.Description);
        end

    case 'sets'
        T = read_hil_param_sets(fullfile(here, 'hil_param_sets.csv'));
        for i = 1:height(T), fprintf('%-24s %-10s %s\n', T.set{i}, T.kind{i}, T.note{i}); end
        out = T;

    case 'apply'
        ensure_loaded(mdl, here);
        apply_hil_param_set(fullfile(here, 'hil_param_sets.csv'), varargin{1});

    case 'defaults'
        evalin('base', sprintf('load(''%s'');', strrep(fullfile(here, [mdl '_data.mat']), '''', '''''')));
        fprintf('all parameters, pv and y0 reloaded from %s_data.mat\n', mdl);

    case 'scaling'
        ensure_loaded(mdl, here);
        pv = evalin('base', 'pv'); fs = getp('ao_fs_V');
        base = [pv(2) / pv(1), pv(1), pv(2) / pv(25), pv(25)];         % I_rated, V_ref, I_out_rated, V_ref48
        pu = [getp('ao_pu_1'), getp('ao_pu_2'), getp('ao_pu_3'), getp('ao_pu_4')];
        idle = [0.514 * base(1), 0.997 * base(2), 0.5 * base(3), 1.0 * base(4)];   % design point at 0.5 P_rated
        nm = {'AO1 i_L   ', 'AO2 v_bus ', 'AO3 i_rack', 'AO4 v_out '}; un = {'A', 'V', 'A', 'V'};
        fprintf('ao_fs_V = %g V\n', fs);
        for i = 1:4
            FS = pu(i) * base(i);
            fprintf('%s  full scale %9.1f %s = %5.2f p.u.   %8.4f mV/%s   idle reading ~ %.2f V\n', ...
                    nm{i}, FS, un{i}, pu(i), 1e3 * fs / FS, un{i}, fs * idle(i) / FS);
        end

    case 'sim'
        ensure_loaded(mdl, here);
        o = struct('T_fire', 20e-3, 'T_end', [], 'trip_after', 0.35e-3, 'trip', 'auto');
        set_name = '';
        if ~isempty(varargin) && mod(numel(varargin), 2) == 1, set_name = varargin{1}; varargin = varargin(2:end); end
        for i = 1:2:numel(varargin), o.(varargin{i}) = varargin{i + 1}; end
        if isempty(o.T_end), o.T_end = o.T_fire + 5e-3; end
        if ~isempty(set_name)
            apply_hil_param_set(fullfile(here, 'hil_param_sets.csv'), set_name);
        end
        fm0 = getp('fault_mode'); setp('fault_mode', 0);
        cleanup = onCleanup(@() setp('fault_mode', fm0));                % restore even if sim() errors
        dt = getp('hil_dt'); n = round(o.T_end / dt); t = (0:n-1)' * dt; k_f = round(o.T_fire / dt);
        u = zeros(n, 4); u(k_f+1:min(k_f+2, n), 3) = 1.0;               % FAULT_CMD rising edge at T_fire
        ft = getp('fault_type'); col = 0;
        switch lower(o.trip)
            case 'auto',   if ft == 1, col = 1; elseif ft == 2, col = 2; end   % arc / benign: no trip
            case 'feeder', col = 1;
            case 'rack',   col = 2;
        end
        if col > 0 && o.trip_after > 0
            k_t = k_f + round(o.trip_after / dt); u(min(k_t+1, n):n, col) = 1.0;   % scripted node TRIP, held
        end
        assignin('base', 'hil_qs_in', [t, u]);
        simOut = sim(mdl, 'StopTime', num2str((n - 1) * dt, 17), 'LoadExternalInput', 'on', 'ExternalInput', 'hil_qs_in', ...
                     'SaveOutput', 'on', 'SaveTime', 'on', 'SaveFormat', 'Array', 'ReturnWorkspaceOutputs', 'on');
        y = simOut.get('yout'); tt = simOut.get('tout');                 % AO1..4, SYNC, BRK_F, BRK_R, SIG(1..28)
        S = @(i) y(:, 7 + i);
        pv = evalin('base', 'pv'); I_r = pv(2) / pv(1); I48 = pv(2) / pv(25);
        R = struct('t', tt, 'AO', y(:, 1:4), 'sync', y(:, 5), 'brk', y(:, 6:7), 'i_L', S(25), 'v_bus', S(26), ...
                   'i_rack', S(27), 'v_out', S(28), 'clear_f_us', y(end, 7 + 7), 'clear_r_us', y(end, 7 + 8), 'set', set_name);
        fprintf('%s: inception at %.1f ms, clearing feeder %.1f us / rack %.1f us (-1 = breaker closed); peak i_L %.2f p.u., peak i_rack %.2f p.u., min v_out %.2f p.u.\n', ...
                tern(isempty(set_name), '(current parameters)', set_name), o.T_fire * 1e3, R.clear_f_us, R.clear_r_us, ...
                max(R.i_L) / I_r, max(R.i_rack) / I48, min(R.v_out(R.brk(:, 2) > 0.5)) / pv(25));
        w = tt >= o.T_fire - 0.5e-3; tm = (tt(w) - o.T_fire) * 1e3;
        figure('Name', ['dcsim_rt_hil: ' set_name]);
        subplot(4, 1, 1); plot(tm, y(w, 1:4)); grid on; ylabel('AO [V]'); legend('AO1 i_L', 'AO2 v_{bus}', 'AO3 i_{rack}', 'AO4 v_{out}', 'Location', 'eastoutside');
        title(sprintf('%s — clearing f %.0f / r %.0f us', strrep(set_name, '_', '\_'), R.clear_f_us, R.clear_r_us));
        subplot(4, 1, 2); plot(tm, R.i_L(w) / I_r, tm, R.i_rack(w) / I48); grid on; ylabel('current [p.u.]'); legend('i_L', 'i_{rack}', 'Location', 'eastoutside');
        subplot(4, 1, 3); plot(tm, R.v_bus(w) / pv(1), tm, R.v_out(w) / pv(25)); grid on; ylabel('voltage [p.u.]'); legend('v_{bus}', 'v_{out}', 'Location', 'eastoutside');
        subplot(4, 1, 4); stairs(tm, [R.brk(w, :), R.sync(w)]); ylim([-0.1 1.1]); grid on; ylabel('state'); xlabel('ms after inception');
        legend('BRK_F', 'BRK_R', 'SYNC', 'Location', 'eastoutside');
        out = R;

    case 'check'
        if exist('rt_hil_check', 'file') ~= 2 || exist('project_paths', 'file') ~= 2
            error('hil_quickstart:check', ['the reference check needs the project repo (data/simscape/ref_*.mat, ' ...
                  'scripts/compare_simscape.py): run it on the project laptop, rt_hil_check(5e-6, ''slx'')']);
        end
        out = rt_hil_check(getp('hil_dt'), 'slx');

    case 'export'
        rel = varargin{1};
        ensure_loaded(mdl, here);
        dst = fullfile(here, 'handover', rel); if ~exist(dst, 'dir'), mkdir(dst); end
        try
            Simulink.exportToVersion(mdl, fullfile(dst, [mdl '.slx']), rel);
        catch ME                                                       % same name as the loaded model refused
            warning('hil_quickstart:export', 'export under the model name refused (%s): exporting as _export and renaming', ME.message);
            Simulink.exportToVersion(mdl, fullfile(dst, [mdl '_export.slx']), rel);
            movefile(fullfile(dst, [mdl '_export.slx']), fullfile(dst, [mdl '.slx']));
        end
        copyfile(fullfile(here, [mdl '_data.mat']), dst);
        D = load(fullfile(here, [mdl '_data.mat']), 'pv', 'y0');       % numbers-only fallback for an older release
        save(fullfile(dst, [mdl '_pv_y0.mat']), '-struct', 'D', '-v7');
        files = {'dcsim_rt_hil_plant.m', 'dcsim_rt_step.m', 'dcsim_rt_derivs.m', 'dcsim_rt_hil_params.m', ...
                 'apply_hil_param_set.m', 'read_hil_param_sets.m', 'hil_param_sets.csv', 'hil_quickstart.m', 'HIL_HANDOVER_README.md', 'HIL_MODEL_INTERFACE.md'};
        for i = 1:numel(files)
            f = fullfile(here, files{i});
            if exist(f, 'file'), copyfile(f, dst); else, warning('hil_quickstart:export', 'missing %s (not copied)', files{i}); end
        end
        fprintf('handover folder ready: %s\n', dst);

    otherwise
        error('hil_quickstart:action', 'unknown action ''%s'' — see help hil_quickstart', action);
end
end

% ---------------------------------------------------------------------------------------------------------------------
function ensure_loaded(mdl, here)
if ~bdIsLoaded(mdl), load_system(fullfile(here, [mdl '.slx'])); end
end
function nm = param_names()
w = evalin('base', 'whos');
nm = {w(strcmp({w.class}, 'Simulink.Parameter')).name};
end
function v = getp(name)
p = evalin('base', name); v = p.Value;
end
function setp(name, val)
p = evalin('base', name); p.Value = val; assignin('base', name, p);
end
function s = tern(c, a, b)
if c, s = a; else, s = b; end
end
