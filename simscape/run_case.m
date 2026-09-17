function out = run_case(case_name, datadir, mdl)
%RUN_CASE  Load one cross-check case, simulate on the 1 us reference grid, export sim_<case>.mat.
%   run_case('high_z_48')   uses <repo>/data/simscape (project_paths.m) and model 'dcsim_shelf'
if nargin < 2 || isempty(datadir), P = project_paths(); datadir = P.data; end
if nargin < 3, mdl = 'dcsim_shelf'; end
[c, shared] = load_case(case_name, datadir);

if ~bdIsLoaded(mdl), load_system(mdl); end
set_param(mdl, 'StopTime', num2str(shared.T_record));
% output on the reference grid so the comparison needs no interpolation
set_param(mdl, 'OutputOption', 'SpecifiedOutputTimes', 'OutputTimes', 'linspace(0, T_record, round(T_record/1e-6)+1)');
simOut = sim(mdl, 'ReturnWorkspaceOutputs', 'on');
t_abs = simOut.get('t_abs'); i_L = simOut.get('i_L'); v_bus = simOut.get('v_bus');
i_rack = simOut.get('i_rack'); v_out = simOut.get('v_out');
m = (t_abs >= c.t_event - 0.2e-3 - 1e-9) & (t_abs <= c.t_event + 5e-3 + 1e-9);
t = t_abs(m) - c.t_event; i_L = i_L(m); v_bus = v_bus(m); i_rack = i_rack(m); v_out = v_out(m);
save(fullfile(datadir, ['sim_' case_name '.mat']), 't', 'i_L', 'v_bus', 'i_rack', 'v_out');
out = struct('t', t, 'i_L', i_L, 'v_bus', v_bus, 'i_rack', i_rack, 'v_out', v_out);
fprintf('sim_%s.mat written (%d samples)\n', case_name, numel(t));
end
