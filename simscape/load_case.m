function [c, shared, ref] = load_case(case_name, datadir)
%LOAD_CASE  Put one cross-check case's parameters, initial conditions and P_gpu profile into the
%   base workspace, where dcsim_shelf reads them by name. Used by run_case and verify_build.
if nargin < 2, P = project_paths(); datadir = P.data; end
shared = jsondecode(fileread(fullfile(datadir, 'params.json')));
cases  = jsondecode(fileread(fullfile(datadir, 'cases.json')));
c = cases.(case_name);
ref = load(fullfile(datadir, ['ref_' case_name '.mat']));

names = {'V_ref','P_rated','R_droop','tau_c','C_bus','L_line','R_line','R_esr','V_uvlo','I_lim', ...
         'L_in','R_in','C_in','R_in_esr','S_max','tau_r','p_fix','k2','V_ref48','C_out','R_out_esr', ...
         'tau_i','I_lim_out','V_uvlo48','t_uvlo48','V_hyst48','K_p','K_i','T_record'};
for k = 1:numel(names), assignin('base', names{k}, shared.(names{k})); end
assignin('base', 'R_f',  c.R_f);   assignin('base', 'L_f',  c.L_f);
assignin('base', 'R_f48', c.R_f48); assignin('base', 'L_f48', c.L_f48);
assignin('base', 't_event', c.t_event);
assignin('base', 'f800_on', double(c.fault_800V_active));
assignin('base', 'f48_on',  double(c.fault_48V_active));
ic = c.initial_state;
for f = {'v_c','i_L','v_C','i_Lin','v_Cin','P_cmd','xi_v','i_co','v_out'}
    assignin('base', ['ic_' f{1}], ic.(f{1}));
end
% prm vector consumed by the MATLAB Function blocks (order fixed in build_dcsim_shelf)
prm = [shared.V_ref, shared.P_rated, shared.V_uvlo, c.smooth_on, shared.S_max, shared.tau_r, ...
       shared.p_fix, shared.k2, shared.V_ref48, shared.K_p, shared.K_i, shared.tau_i, shared.I_lim_out, ...
       shared.V_uvlo48, 1.0, shared.t_uvlo48, shared.V_hyst48];          % prm(15) = conv_on (input UVLO never trips here)
assignin('base', 'prm', prm);
% GPU demand: the reference window starts 0.2 ms before the event; before that hold P0
t_ref = ref.t(:) + c.t_event;
P_gpu_ts = [0, c.P0; t_ref(1) - 1e-9, c.P0; t_ref, ref.P_gpu(:)];
assignin('base', 'P_gpu_ts', P_gpu_ts);
end
