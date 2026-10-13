function [y0, st0] = dcsim_rt_init(c)
%DCSIM_RT_INIT  Exact steady-state initial condition of a cross-check case (cases.json initial_state, the same
%   arithmetic as model_v04.simulate's initialisation), and the supervisory state [conv_on load_on48 uvlo_t uvlo48_t].
ic = c.initial_state;
y0 = [ic.v_c; ic.i_L; ic.v_C; ic.i_f; ic.i_Lin; ic.v_Cin; ic.P_cmd; ic.xi_v; ic.i_co; ic.v_out; ic.i_f48];
st0 = [1; 1; 0; 0];
end
