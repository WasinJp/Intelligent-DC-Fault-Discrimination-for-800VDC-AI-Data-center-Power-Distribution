%% run_hil_handover.m — desktop checks + handover package for dcsim_rt_hil (2026-10-16 revision)
%  Run as a SCRIPT from <repo>\simscape (the Constant blocks resolve pv / y0 / parameters in the base workspace).
%% 0. setup
cd('<repo>\simscape')
P  = project_paths();
[c, shared] = load_case('high_z', P.data);
dt = 5e-6;

%% 1. loop check: 8/8, worst values identical to the 15 Oct run (breaker fix inert with breakers closed)
T1 = rt_hil_check(dt, 'loop')
writetable(T1, fullfile(P.root, 'simscape', 'rt_hil_check_loop_5us.csv'));

%% 2. build at the design point, demo regime (conv_smooth 1); the build writes dcsim_rt_hil_data.mat
%     (pv, y0, 38 parameters) and sets the model's PreLoadFcn — nothing else to save by hand
pv    = dcsim_rt_pv(shared, c);
pv_y0 = pv;  pv_y0(20) = 1;                                   % y0 with smoothing on
y0    = dcsim_rt_hil_y0(pv_y0, 0.5 * shared.P_rated, dt);
build_dcsim_rt_hil('dcsim_rt_hil', dt, shared);
T2 = rt_hil_check(dt, 'slx')                                  % 8/8; uses sim() options, the model stays clean
writetable(T2, fullfile(P.root, 'simscape', 'rt_hil_check_slx_5us.csv'));

%% 2b. proof that the .slx opens on its own (fresh workspace)
bdclose all; clear;
load_system('dcsim_rt_hil'); set_param('dcsim_rt_hil', 'SimulationCommand', 'update');   % no "undefined variable"
P = project_paths();

%% 3. parameter sets + the six demos (each ~1 min: 4 s of model time at 5 us)
T = export_hil_param_sets();                                  % 14 rows, 19 columns
for s = {'benign', 'highz800_hard', 'highz48', 'bolted48', 'bolted48_l1', 'arc'}
    D.(s{1}) = dcsim_rt_hil_demo(s{1});
    exportgraphics(gcf, fullfile(P.root, 'simscape', ['rt_hil_demo_' s{1} '.png']), 'Resolution', 150);
end
% expected on the console (handover review H2): every "workload check" PASS (7.5e-04 P_rated per step; +5e-04 with a
% burst, +1e-03 for benign); highz800_hard: TRIP scripted at +355 us, clear_f_us 380, v_bus ~0.5 p.u. at +3 ms and
% lower than at +1 ms; highz48 / bolted48: TRIP at +350, clear_r_us 375; bolted48_l1: i_rack crosses +2 p.u. at ~25 us,
% TRIP at ~+45-50 us, clear_r_us ~70-75; benign / arc: -1 / -1

%% 4. once the alumni name their release (example R2023b): SAME file name, in a subfolder, data file beside it
rel = 'R2023b'; out = fullfile(P.root, 'simscape', 'handover', rel); if ~exist(out, 'dir'), mkdir(out); end
try
    Simulink.exportToVersion('dcsim_rt_hil', fullfile(out, 'dcsim_rt_hil.slx'), rel);
catch ME                                                      % H3: refused under the loaded model's name -> export, rename
    warning('exportToVersion under the same name refused (%s); exporting as _export and renaming', ME.message);
    Simulink.exportToVersion('dcsim_rt_hil', fullfile(out, 'dcsim_rt_hil_export.slx'), rel);
    movefile(fullfile(out, 'dcsim_rt_hil_export.slx'), fullfile(out, 'dcsim_rt_hil.slx'));
end
copyfile(fullfile(P.root, 'simscape', 'dcsim_rt_hil_data.mat'), out);
S = load(fullfile(P.root, 'simscape', 'dcsim_rt_hil_data.mat'), 'pv', 'y0');   % H4: numbers-only fallback for an older release
save(fullfile(out, 'dcsim_rt_hil_pv_y0.mat'), '-struct', 'S', '-v7');
for f = {'dcsim_rt_hil_plant.m', 'dcsim_rt_step.m', 'dcsim_rt_derivs.m', 'dcsim_rt_hil_params.m', 'hil_param_sets.csv', 'apply_hil_param_set.m', 'HIL_MODEL_INTERFACE.md'}
    copyfile(fullfile(P.root, 'simscape', f{1}), out);
end
fid = fopen(fullfile(out, 'README.txt'), 'w');
fprintf(fid, ['dcsim_rt_hil - exported for MATLAB %s (built in R2026a). Keep all files in one folder; open dcsim_rt_hil.slx.\n' ...
    'The model loads dcsim_rt_hil_data.mat (pv, y0, 38 Simulink.Parameter objects) in its PreLoadFcn.\n' ...
    'If that file does not load on your release:\n' ...
    '    load dcsim_rt_hil_pv_y0.mat\n' ...
    '    dcsim_rt_hil_params(struct(''P_rated'', 132e3), 5e-6)   %% recreates the 38 parameters at their defaults\n' ...
    'then open dcsim_rt_hil.slx. Solver: FixedStepDiscrete, step = hil_dt (5e-6). Ports and parameters: HIL_MODEL_INTERFACE.md.\n' ...
    'Parameter sets for the validation cases and the demo: hil_param_sets.csv (apply_hil_param_set.m on the desktop).\n'], rel);
fclose(fid);
% hand over the folder; the rest of rulebook section 7 (ref_*.mat, comparator) is for the box validation session
