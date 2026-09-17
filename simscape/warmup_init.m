% warmup_init.m — parameters for the Simscape warm-up circuit
% C_out bank (with separate ESR) discharging into a bolted 48 V fault branch.
% Values match PARAMS_BASELINE / the bolted_48 case in simscape_cases.py.
p = struct();
p.C_out     = 3.7;      % F, rack energy storage
p.R_out_esr = 0.3e-3;   % ohm, storage ESR (separate Resistor block)
p.R_f48     = 1e-3;     % ohm, bolted_48 fault resistance
p.L_f48     = 0.5e-6;   % H, fault loop inductance
p.V0        = 50.0;     % V, initial capacitor voltage (= V_ref48)
p.t_sw      = 1e-3;     % s, switch closing time
disp('warm-up parameters loaded into struct p');
