function T = rt_sweep(dts, names, mode, uvlo_tol)
%RT_SWEEP  Check (i) for the fixed-step explicit model over a set of steps: the plant half of HIL plan check (k).
%   T = rt_sweep                       dts = [1 2 5 10 20] us, all eight cases, pure-MATLAB loop
%   T = rt_sweep([1 10]*1e-6)          two steps
%   T = rt_sweep(1e-6, {'step'}, 'slx') one case through the Simulink wrapper
%   T = rt_sweep([], [], 'loop', 0.5)   grid-robust UVLO timers (step counting) — the HIL setting
%   Prints one table (worst excluded-RMS per case and step, PASS/FAIL), writes simscape/rt_sweep.csv and
%   appends to simscape/rt_sweep_log.txt. Pre-registered expectation (MODEL_READINESS_2026-10-10.md §2):
%   at 1 us all eight pass with excluded-RMS of order 3e-4 or better (same scheme as the Python core at a coarser
%   step than its 50 ns event window; the Python 1 us-vs-50 ns difference is <= 2e-4); at 10 us the step cases pass
%   and the stiff fault cases rely on the quasi-static rule — report both, do not tune.
% dt as exact literals: 5*1e-6 is one ulp below 5e-6 and moves the UVLO edge by one step (see dcsim_rt_step, uvlo_tol)
if nargin < 1 || isempty(dts), dts = [1e-6 2e-6 5e-6 1e-5 2e-5]; end
if nargin < 2 || isempty(names)
    names = {'step','step_sm','high_z','high_z_sm','high_z_48','high_z_48_sm','bolted_48','bolted_48_sm'};
end
if nargin < 3 || isempty(mode), mode = 'loop'; end
if nargin < 4 || isempty(uvlo_tol), uvlo_tol = 0.0; end
here = fileparts(mfilename('fullpath'));
rows = {};
for i = 1:numel(dts)
    for j = 1:numel(names)
        R = run_rt_case(names{j}, dts(i), mode, [], uvlo_tol);
        rows(end+1, :) = {names{j}, dts(i) * 1e6, mode, R.worst_ex, R.pass, R.wall}; %#ok<AGROW>
    end
end
T = cell2table(rows, 'VariableNames', {'case', 'dt_us', 'mode', 'worst_excluded_rms', 'pass', 'wall_s'});
fprintf('\n%-13s', 'case'); for i = 1:numel(dts), fprintf('%12s', sprintf('%g us', dts(i) * 1e6)); end; fprintf('\n');
for j = 1:numel(names)
    fprintf('%-13s', names{j});
    for i = 1:numel(dts)
        r = T(strcmp(T.case, names{j}) & T.dt_us == dts(i) * 1e6, :);
        fprintf('%9.1e %s', r.worst_excluded_rms, ternary(r.pass, 'P ', 'F '));
    end
    fprintf('\n');
end
writetable(T, fullfile(here, 'rt_sweep.csv'));
fid = fopen(fullfile(here, 'rt_sweep_log.txt'), 'a');
fprintf(fid, '\n==== rt_sweep %s  mode %s  uvlo_tol %g  MATLAB %s\n', datestr(now, 'yyyy-mm-dd HH:MM'), mode, uvlo_tol, version);
for k = 1:height(T)
    fprintf(fid, '%-13s %6.2f us  worst excluded %9.2e  %s  (%.2f s)\n', T.case{k}, T.dt_us(k), T.worst_excluded_rms(k), ternary(T.pass(k), 'PASS', 'FAIL'), T.wall_s(k));
end
fclose(fid);
end

function s = ternary(c, a, b)
if c, s = a; else, s = b; end
end
