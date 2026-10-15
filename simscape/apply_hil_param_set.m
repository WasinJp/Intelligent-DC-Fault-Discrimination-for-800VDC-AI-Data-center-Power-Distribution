function apply_hil_param_set(T, name)
%APPLY_HIL_PARAM_SET  Put one row of export_hil_param_sets into the base-workspace Simulink.Parameter objects
%   (dcsim_rt_hil_params must have run). apply_hil_param_set(T, 'demo_2_highz800_hard')
r = T(strcmp(T.set, name), :);
if isempty(r), error('apply_hil_param_set: no set named %s', name); end
for k = {'fault_type','fault_Rf','fault_Lf','fault_Rf48','fault_Lf48','fault_Varc','fault_mode','step_dP','step_ramp','wl_on','wl_P0','fault_arc_m','fault_arc_ramp','uvlo_tol','conv_smooth','brk_delay'}
    p = evalin('base', k{1}); p.Value = r.(k{1}); assignin('base', k{1}, p);
end
fprintf('%s: %s\n', name, char(r.note));
end
