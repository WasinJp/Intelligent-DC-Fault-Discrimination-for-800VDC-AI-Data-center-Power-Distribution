function apply_hil_param_set(T, name)
%APPLY_HIL_PARAM_SET  Put one row of hil_param_sets.csv into the base-workspace Simulink.Parameter objects
%   (the model, or dcsim_rt_hil_params, must have created them).
%   apply_hil_param_set('demo_2_highz800_hard')               reads hil_param_sets.csv next to this file
%   apply_hil_param_set('path\hil_param_sets.csv', 'demo_3_highz48')
%   apply_hil_param_set(T, 'demo_3_highz48')                  T from read_hil_param_sets
%   2026-10-16: reads the CSV with read_hil_param_sets (readtable's auto-detection lost the 'set' column).
if nargin == 1, name = T; T = read_hil_param_sets(); end
if ischar(T) || isstring(T), T = read_hil_param_sets(char(T)); end
r = T(strcmp(T.set, name), :);
if isempty(r)
    error('apply_hil_param_set:name', 'no set named %s; available: %s', name, strjoin(T.set', ', '));
end
for k = {'fault_type','fault_Rf','fault_Lf','fault_Rf48','fault_Lf48','fault_Varc','fault_mode','step_dP','step_ramp','wl_on','wl_P0','fault_arc_m','fault_arc_ramp','uvlo_tol','conv_smooth','brk_delay'}
    p = evalin('base', k{1}); p.Value = r.(k{1}); assignin('base', k{1}, p);
end
fprintf('%s: %s\n', name, char(r.note));
end
