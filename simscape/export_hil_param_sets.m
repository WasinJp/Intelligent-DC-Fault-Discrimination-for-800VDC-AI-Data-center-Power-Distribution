function T = export_hil_param_sets(outfile)
%EXPORT_HIL_PARAM_SETS  The parameter sets we bring to the dSPACE session, as one table (CSV): the eight check-(i)
%   validation cases (workload off, fault from the case, benign step for the 'step' kind, fire with fault_trigger) and
%   the five-event live demo (workload on, inception on the next workload edge). Columns = ControlDesk parameter names
%   of dcsim_rt_hil (dcsim_rt_hil_params); one row per set. Also usable on the desktop: apply_hil_param_set(T, 'high_z').
%   Columns added 2026-10-16 (review #7, #12, #18): uvlo_tol (0 for the check-(i) rows = rt_sweep's reference column,
%   0.5 for the demo), conv_smooth (the case's regime for check (i); on for the demo), brk_delay (0 / 20 us).
%   T = export_hil_param_sets()            -> simscape/hil_param_sets.csv
if nargin < 1 || isempty(outfile), outfile = fullfile(fileparts(mfilename('fullpath')), 'hil_param_sets.csv'); end
P = project_paths();
cases = {'step','step_sm','high_z','high_z_sm','high_z_48','high_z_48_sm','bolted_48','bolted_48_sm'};
rows = {};
for j = 1:numel(cases)
    [c, shared] = load_case(cases{j}, P.data);
    ftype = 0; if c.fault_800V_active, ftype = 1; end; if c.fault_48V_active, ftype = 2; end
    stepdP = 0; if strcmp(c.kind, 'step'), stepdP = 0.4 * shared.P_rated; end
    rows(end+1, :) = {['check_i_' cases{j}], 'validation', ftype, c.R_f, c.L_f, c.R_f48, c.L_f48, 0, 0, stepdP, 2e-3, 0, c.P0, 0, 0.5e-3, 0, c.smooth_on, 0, ...
                      sprintf('check (i) case %s: workload off, P0 from the case, uvlo_tol 0 and conv_smooth from the case (as rt_sweep), fire fault_trigger, capture SIG 25-28 + SYNC, compare with ref_%s.mat', cases{j}, cases{j})}; %#ok<AGROW>
end
Pr = shared.P_rated;
demo = { ...
 'demo_1_benign_step',   0, 3.0, 2e-6, 20e-3, 0.5e-6, 0,  1, 0.4*Pr, 'no trip expected: a 0.4 P_rated load step on the running workload'; ...
 'demo_2_highz800_hard', 1, 8.0, 2e-6, 20e-3, 0.5e-6, 0,  1, 0.4*Pr, 'the core event: high-Z 800 V fault (8 ohm, +0.6 p.u.) hidden inside a load step -> feeder node trips; same final current as a step, different rise (us with ringing vs ms ramp) - a slow threshold waits for the level, a fast one trips on steps'; ...
 'demo_2b_highz800',     1, 3.0, 2e-6, 20e-3, 0.5e-6, 0,  1, 0.4*Pr, 'high-Z 800 V at 3 ohm (source current limit visible)'; ...
 'demo_3_highz48',       2, 3.0, 2e-6, 20e-3, 0.5e-6, 0,  1, 0,      'high-Z 48 V fault -> rack node trips; the feeder sees only a smooth rise that looks like a load step (why two nodes)'; ...
 'demo_4_bolted48',      2, 3.0, 2e-6, 0.5e-3, 0.2e-6, 0, 1, 0,      'bolted 48 V: with Layer 2 alone the rack current peaks ~17 p.u. (AO3 saturates), v_out falls to ~0.7, GPUs drop at ~0.27 ms before the 0.35 ms trip -> the case for the per-sample Layer 1 (rack current > 2x rated within ~70 us; firmware S1)'; ...
 'demo_5_arc',           3, 3.0, 2e-6, 20e-3, 0.5e-6, 25, 1, 0,      'series arc 25 V with 15 % pink noise (1-100 kHz, in-model) -> ALERT, no TRIP; demo only, rate not quoted'};
for j = 1:size(demo, 1)
    rows(end+1, :) = {demo{j,1}, 'demo', demo{j,2}, demo{j,3}, demo{j,4}, demo{j,5}, demo{j,6}, demo{j,7}, demo{j,8}, demo{j,9}, 2e-3, 1, 0.5*Pr, 0.15, 0.5e-3, 0.5, 1, 20e-6, demo{j,10}}; %#ok<AGROW>
end
T = cell2table(rows, 'VariableNames', {'set','kind','fault_type','fault_Rf','fault_Lf','fault_Rf48','fault_Lf48','fault_Varc', ...
                                        'fault_mode','step_dP','step_ramp','wl_on','wl_P0','fault_arc_m','fault_arc_ramp','uvlo_tol','conv_smooth','brk_delay','note'});
writetable(T, outfile);
fprintf('%d parameter sets -> %s\n', height(T), outfile);
end
