function mdl = build_dcsim_shelf(mdl)
%BUILD_DCSIM_SHELF  Programmatically build the single-shelf cross-check model
%   (MODEL.md v0.4.2, check (i)) in Simscape Electrical (Foundation library)
%   plus Simulink control. One-to-one with dcsim/model_v04.py _derivs.
%
%   mdl = build_dcsim_shelf('dcsim_shelf')
%
%   Written without MATLAB access; revised 2026-09-17 (limiter diode direction,
%   converter-output source direction, source lag as an integrator, 1 us delay on
%   load_on48, UVLO update method, switch/diode conductances). Order of use:
%     probe_blocks -> test_conventions -> build_dcsim_shelf -> verify_build -> smoke_test
%   Port conventions live in shelf_ports.m (shared with test_conventions.m).
%
%   Electrical topology (all Simscape Foundation):
%     source: CVS (droop+lag command) -> Diode (i_L>=0) -> limiter (DC I_lim || Diode)
%             -> R_line -> L_line -> CurrentSensor(i_L) -> BUS
%     BUS:   C_bus (ideal) + R_esr to ground; fault800: Switch+R_f+L_f to ground
%     BUS -> L_in -> R_in -> Diode (ORing) -> INPUT node
%     INPUT: C_in (ideal) + R_in_esr to ground; CCS i_in (INPUT -> ground)
%     48 V:  CCS i_co (ground -> V48 node); C_out (ideal) + R_out_esr to ground;
%            CurrentSensor(i_rack) -> {CCS i_pol (-> ground), fault48: Switch+R_f48+L_f48 (-> ground)}
%   Control (Simulink): MATLAB Function 'ctrl' (pure algebra) + 4 Integrators
%   (v_c, xi_v, P_cmd, i_co) + discrete MATLAB Function 'uvlo48' (Ts = 1 us).

if nargin < 1, mdl = 'dcsim_shelf'; end
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl); open_system(mdl);
set_param(mdl, 'StopTime', '7e-3', 'Solver', 'ode23t', 'RelTol', '1e-6', 'AbsTol', '1e-6', ...
    'MaxStep', '1e-6', 'ZeroCrossControl', 'UseLocalSettings');

% ---------------------------------------------------------------- port conventions
% Single source of truth in shelf_ports.m, proven by test_conventions.m before this runs.
P = shelf_ports();

FL = 'fl_lib/Electrical/';
NU = 'nesl_utility/';
SL = 'simulink/';

% ---------------------------------------------------------------- helpers
    function b = blk(lib, name, pos, varargin)
        b = [mdl '/' name];
        add_block(lib, b, 'Position', pos);
        for i = 1:2:numel(varargin), set_param(b, varargin{i}, varargin{i+1}); end
    end
    function ln(src, sp, dst, dp)
        % connect source port sp of block src to port dp of block dst; ports are
        % 'LConnN' / 'RConnN' for physical, or a number string for Simulink ports
        add_line(mdl, [src '/' sp], [dst '/' dp], 'autorouting', 'on');
    end
    function set_script(name, txt)
        rt = sfroot; ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [mdl '/' name]);
        ch.Script = txt;
    end

x = 30; y = 30; dy = 80;
% ---------------------------------------------------------------- Simscape scaffolding
ground = blk([FL 'Electrical Elements/Electrical Reference'], 'GND', [x y+12*dy x+30 y+12*dy+30]);
solver = blk([NU 'Solver Configuration'], 'SolverCfg', [x y+13*dy x+40 y+13*dy+30], 'UseLocalSolver', 'off');
ln('SolverCfg', P.solv, 'GND', P.ref);

% ---------------------------------------------------------------- source and feeder
blk([FL 'Electrical Sources/Controlled Voltage Source'], 'Vsrc', [x+100 y x+130 y+40]);
blk([FL 'Electrical Elements/Diode'], 'Dsrc', [x+160 y x+190 y+30], 'Vf', '0', 'Ron', '1e-6', 'Goff', '1e-8');
blk([FL 'Electrical Sources/DC Current Source'], 'Ilim', [x+220 y-40 x+250 y-10], 'i0', 'I_lim');      % limiter: I_lim || diode
blk([FL 'Electrical Elements/Diode'], 'Dlim', [x+220 y+20 x+250 y+50], 'Vf', '0', 'Ron', '1e-6', 'Goff', '1e-8');
blk([FL 'Electrical Elements/Resistor'], 'Rline', [x+280 y x+310 y+30], 'R', 'R_line');
blk([FL 'Electrical Elements/Inductor'], 'Lline', [x+340 y x+370 y+30], 'l', 'L_line', 'i0', 'ic_i_L', 'r', '0', 'g', '0');
blk([FL 'Electrical Sensors/Current Sensor'], 'IsenL', [x+400 y x+430 y+30]);
% wiring: Vsrc(+) -> Dsrc -> [Ilim || Dlim] -> Rline -> Lline -> IsenL -> BUS ; Vsrc(-) -> GND
ln('Vsrc', P.cvs.p, 'Dsrc', P.two.p);
ln('Dsrc', P.two.n, 'Ilim', P.two.p);   ln('Dsrc', P.two.n, 'Dlim', P.two.n);     % limiter input node  (Dlim CATHODE)
ln('Ilim', P.two.n, 'Rline', P.two.p);  ln('Dlim', P.two.p, 'Rline', P.two.p);    % limiter output node (Dlim ANODE)
% Dlim carries (I_lim - i_L) from the OUTPUT node back to the INPUT node, so it points the
% OPPOSITE way to Dsrc (which conducts forward, source -> feeder). With both diodes wired the
% same way the branch would be forced to i_L >= I_lim. Whatever the port mapping turns out to
% be, Dsrc and Dlim must stay opposite. Ilim carries I_lim in the direction of i_L (+ -> -).
ln('Rline', P.two.n, 'Lline', P.two.p);
ln('Lline', P.two.n, 'IsenL', P.isen.p);
ln('Vsrc', P.cvs.n, 'GND', P.ref);

% ---------------------------------------------------------------- 800 V bus node
blk([FL 'Electrical Elements/Capacitor'], 'Cbus', [x+480 y+2*dy x+510 y+2*dy+30], 'c', 'C_bus', 'v0', 'ic_v_C', 'v0_priority', 'High', 'r', '0', 'g', '0');
blk([FL 'Electrical Elements/Resistor'], 'Resr', [x+480 y+dy x+510 y+dy+30], 'R', 'R_esr');
blk([FL 'Electrical Sensors/Voltage Sensor'], 'VsenBus', [x+540 y+dy x+570 y+dy+30]);
ln('IsenL', P.isen.n, 'Resr', P.two.p);  ln('Resr', P.two.n, 'Cbus', P.two.p);  ln('Cbus', P.two.n, 'GND', P.ref);
ln('IsenL', P.isen.n, 'VsenBus', P.vsen.p); ln('VsenBus', P.vsen.n, 'GND', P.ref);
% 800 V fault branch
blk([FL 'Electrical Elements/Switch'], 'SW800', [x+600 y+dy x+630 y+dy+30], 'Threshold', '0.5', 'R_closed', '1e-6', 'G_open', '1e-8');
blk([FL 'Electrical Elements/Resistor'], 'Rf', [x+600 y+2*dy x+630 y+2*dy+30], 'R', 'R_f - 1e-6');      % switch R_closed is part of R_f
blk([FL 'Electrical Elements/Inductor'], 'Lf', [x+600 y+3*dy x+630 y+3*dy+30], 'l', 'L_f', 'i0', '0', 'r', '0', 'g', '0');
ln('IsenL', P.isen.n, 'SW800', P.sw.p); ln('SW800', P.sw.n, 'Rf', P.two.p); ln('Rf', P.two.n, 'Lf', P.two.p); ln('Lf', P.two.n, 'GND', P.ref);

% ---------------------------------------------------------------- rack input filter + ORing + input node
blk([FL 'Electrical Elements/Inductor'], 'Lin', [x+700 y x+730 y+30], 'l', 'L_in', 'i0', 'ic_i_Lin', 'r', '0', 'g', '0');
blk([FL 'Electrical Elements/Resistor'], 'Rin', [x+760 y x+790 y+30], 'R', 'R_in');
blk([FL 'Electrical Elements/Diode'], 'Dor', [x+820 y x+850 y+30], 'Vf', '0', 'Ron', '1e-6', 'Goff', '1e-8');
blk([FL 'Electrical Elements/Capacitor'], 'Cin', [x+900 y+2*dy x+930 y+2*dy+30], 'c', 'C_in', 'v0', 'ic_v_Cin', 'v0_priority', 'High', 'r', '0', 'g', '0');
blk([FL 'Electrical Elements/Resistor'], 'Rinesr', [x+900 y+dy x+930 y+dy+30], 'R', 'R_in_esr');
blk([FL 'Electrical Sensors/Voltage Sensor'], 'VsenCin', [x+960 y+2*dy x+990 y+2*dy+30]);   % across the CAPACITOR (control reads the state)
blk([FL 'Electrical Sources/Controlled Current Source'], 'CCSin', [x+960 y x+990 y+40]);   % converter input draw
ln('IsenL', P.isen.n, 'Lin', P.two.p); ln('Lin', P.two.n, 'Rin', P.two.p); ln('Rin', P.two.n, 'Dor', P.two.p);
ln('Dor', P.two.n, 'Rinesr', P.two.p); ln('Rinesr', P.two.n, 'Cin', P.two.p); ln('Cin', P.two.n, 'GND', P.ref);
ln('Rinesr', P.two.n, 'VsenCin', P.vsen.p); ln('VsenCin', P.vsen.n, 'GND', P.ref);         % capacitor-side node
ln('Dor', P.two.n, 'CCSin', P.ccs.p); ln('CCSin', P.ccs.n, 'GND', P.ref);                  % current INTO the source = draw from node

% ---------------------------------------------------------------- 48 V side
blk([FL 'Electrical Sources/Controlled Current Source'], 'CCSco', [x+1100 y x+1130 y+40]);  % converter output: ground -> V48 node
blk([FL 'Electrical Elements/Capacitor'], 'Cout', [x+1180 y+2*dy x+1210 y+2*dy+30], 'c', 'C_out', 'v0', 'ic_v_out', 'v0_priority', 'High', 'r', '0', 'g', '0');
blk([FL 'Electrical Elements/Resistor'], 'Routesr', [x+1180 y+dy x+1210 y+dy+30], 'R', 'R_out_esr');
blk([FL 'Electrical Sensors/Voltage Sensor'], 'VsenCout', [x+1240 y+2*dy x+1270 y+2*dy+30]); % across the CAPACITOR
blk([FL 'Electrical Sensors/Voltage Sensor'], 'VsenV48', [x+1240 y+dy x+1270 y+dy+30]);     % node (with ESR) -> logging + UVLO
blk([FL 'Electrical Sensors/Current Sensor'], 'IsenRack', [x+1300 y x+1330 y+30]);          % i_rack = i_pol + i_f48
blk([FL 'Electrical Sources/Controlled Current Source'], 'CCSpol', [x+1380 y x+1410 y+40]);
blk([FL 'Electrical Elements/Switch'], 'SW48', [x+1380 y+dy x+1410 y+dy+30], 'Threshold', '0.5', 'R_closed', '1e-6', 'G_open', '1e-8');
blk([FL 'Electrical Elements/Resistor'], 'Rf48', [x+1380 y+2*dy x+1410 y+2*dy+30], 'R', 'R_f48 - 1e-6');  % 1 uOhm extra alone costs 5e-3 on bolted_48 i_rack
blk([FL 'Electrical Elements/Inductor'], 'Lf48', [x+1380 y+3*dy x+1410 y+3*dy+30], 'l', 'L_f48', 'i0', '0', 'r', '0', 'g', '0');
% Simscape convention: a positive source current flows + -> - THROUGH the source, i.e. it enters at
% '+' and leaves at '-'. CCSin and CCSpol ('+' on the node) therefore DRAW from their nodes; the
% converter output must INJECT, so its '-' faces the 48 V node and '+' goes to ground.
ln('CCSco', P.ccs.p, 'GND', P.ref);
ln('CCSco', P.ccs.n, 'Routesr', P.two.p); ln('Routesr', P.two.n, 'Cout', P.two.p); ln('Cout', P.two.n, 'GND', P.ref);
ln('Routesr', P.two.n, 'VsenCout', P.vsen.p); ln('VsenCout', P.vsen.n, 'GND', P.ref);
ln('CCSco', P.ccs.n, 'VsenV48', P.vsen.p);   ln('VsenV48', P.vsen.n, 'GND', P.ref);
ln('CCSco', P.ccs.n, 'IsenRack', P.isen.p);
ln('IsenRack', P.isen.n, 'CCSpol', P.ccs.p); ln('CCSpol', P.ccs.n, 'GND', P.ref);
ln('IsenRack', P.isen.n, 'SW48', P.sw.p); ln('SW48', P.sw.n, 'Rf48', P.two.p); ln('Rf48', P.two.n, 'Lf48', P.two.p); ln('Lf48', P.two.n, 'GND', P.ref);

% ---------------------------------------------------------------- PS <-> Simulink converters
yc = y + 6*dy;
conv = {'s2p_vsrc','s2p_iin','s2p_ico','s2p_ipol','s2p_sw800','s2p_sw48'};
for k = 1:numel(conv), blk([NU 'Simulink-PS Converter'], conv{k}, [x+100+150*(k-1) yc x+140+150*(k-1) yc+30]); end
sens = {'p2s_iL','p2s_vbus','p2s_vCin','p2s_vCout','p2s_v48','p2s_irack'};
for k = 1:numel(sens), blk([NU 'PS-Simulink Converter'], sens{k}, [x+100+150*(k-1) yc+dy x+140+150*(k-1) yc+dy+30]); end
ln('s2p_vsrc', P.s2p.out, 'Vsrc', P.cvs.ctl);   ln('s2p_iin', P.s2p.out, 'CCSin', P.ccs.ctl);
ln('s2p_ico', P.s2p.out, 'CCSco', P.ccs.ctl);   ln('s2p_ipol', P.s2p.out, 'CCSpol', P.ccs.ctl);
ln('s2p_sw800', P.s2p.out, 'SW800', P.sw.ctl);  ln('s2p_sw48', P.s2p.out, 'SW48', P.sw.ctl);
ln('IsenL', P.isen.out, 'p2s_iL', P.p2s.in);    ln('VsenBus', P.vsen.out, 'p2s_vbus', P.p2s.in);
ln('VsenCin', P.vsen.out, 'p2s_vCin', P.p2s.in); ln('VsenCout', P.vsen.out, 'p2s_vCout', P.p2s.in);
ln('VsenV48', P.vsen.out, 'p2s_v48', P.p2s.in); ln('IsenRack', P.isen.out, 'p2s_irack', P.p2s.in);

% ---------------------------------------------------------------- control (Simulink)
yk = y + 9*dy;
blk([SL 'Sources/From Workspace'], 'Pgpu', [x yk x+60 yk+30], 'VariableName', 'P_gpu_ts', 'Interpolate', 'on');
blk([SL 'Sources/Constant'], 'prm', [x yk+dy x+60 yk+dy+30], 'Value', 'prm');
blk([SL 'Sources/Step'], 'fault800', [x yk+2*dy x+60 yk+2*dy+30], 'Time', 't_event', 'Before', '0', 'After', 'f800_on');
blk([SL 'Sources/Step'], 'fault48', [x yk+3*dy x+60 yk+3*dy+30], 'Time', 't_event', 'Before', '0', 'After', 'f48_on');
blk([SL 'Continuous/Integrator'], 'int_xi', [x+400 yk x+430 yk+30], 'InitialCondition', 'ic_xi_v');
blk([SL 'Continuous/Integrator'], 'int_Pcmd', [x+400 yk+dy x+430 yk+dy+30], 'InitialCondition', 'ic_P_cmd');
blk([SL 'Continuous/Integrator'], 'int_ico', [x+400 yk+2*dy x+430 yk+2*dy+30], 'InitialCondition', 'ic_i_co');
blk([SL 'User-Defined Functions/MATLAB Function'], 'ctrl', [x+200 yk x+300 yk+3*dy]);
blk([SL 'User-Defined Functions/MATLAB Function'], 'uvlo48', [x+200 yk+4*dy x+300 yk+5*dy]);
% source lag tau_c dv_c/dt = V_ref - R_droop*i_L - v_c, as an explicit integrator so the IC is v_c itself
blk([SL 'Math Operations/Gain'], 'droop', [x+480 yk x+520 yk+30], 'Gain', '-R_droop');
blk([SL 'Math Operations/Sum'], 'sum_src', [x+530 yk-40 x+550 yk-20], 'Inputs', '++-');
blk([SL 'Sources/Constant'], 'Vref', [x+480 yk-60 x+520 yk-40], 'Value', 'V_ref');
blk([SL 'Math Operations/Gain'], 'inv_tauc', [x+560 yk-40 x+590 yk-20], 'Gain', '1/tau_c');
blk([SL 'Continuous/Integrator'], 'int_vc', [x+610 yk-40 x+640 yk-10], 'InitialCondition', 'ic_v_c');

set_script('ctrl', ctrl_script());
set_script('uvlo48', uvlo_script());
try, rt = sfroot; ch = rt.find('-isa','Stateflow.EMChart','Path',[mdl '/uvlo48']); ch.ChartUpdate = 'DISCRETE'; ch.SampleTime = '1e-6';
catch, warning('uvlo48: set Update method = Discrete and Sample time = 1e-6 by hand'); end
% v48_node depends instantly on i_pol (through R_out_esr), i_pol on load_on48, and uvlo48's output on
% v48_node -> an algebraic loop. A 1 us delay breaks it; Python likewise decides the flag from the
% state at the start of the step. The edge moves by at most 1 us (check (i) edge tolerance: 5 us).
blk([SL 'Discrete/Unit Delay'], 'z_uvlo', [x+320 yk+4*dy x+350 yk+4*dy+30], 'InitialCondition', '1', 'SampleTime', '1e-6');

% ctrl inputs: 1 v_Cin, 2 v_out_cap, 3 xi_v, 4 P_cmd, 5 i_co, 6 P_gpu, 7 load_on48, 8 prm
% ctrl outputs: 1 i_in, 2 d_xi, 3 d_Pcmd, 4 d_ico, 5 i_pol
ln('p2s_vCin', P.p2s.out, 'ctrl', '1');  ln('p2s_vCout', P.p2s.out, 'ctrl', '2');
ln('int_xi', '1', 'ctrl', '3');  ln('int_Pcmd', '1', 'ctrl', '4');  ln('int_ico', '1', 'ctrl', '5');
ln('Pgpu', '1', 'ctrl', '6');  ln('uvlo48', '1', 'z_uvlo', '1');  ln('z_uvlo', '1', 'ctrl', '7');  ln('prm', '1', 'ctrl', '8');
ln('ctrl', '1', 's2p_iin', P.s2p.in);
ln('ctrl', '2', 'int_xi', '1');  ln('ctrl', '3', 'int_Pcmd', '1');  ln('ctrl', '4', 'int_ico', '1');
ln('int_ico', '1', 's2p_ico', P.s2p.in);
ln('ctrl', '5', 's2p_ipol', P.s2p.in);
% uvlo48 inputs: 1 v48_node, 2 v_out_cap, 3 prm ; output: load_on48
ln('p2s_v48', P.p2s.out, 'uvlo48', '1');  ln('p2s_vCout', P.p2s.out, 'uvlo48', '2');  ln('prm', '1', 'uvlo48', '3');
% source: v_cmd = V_ref - R_droop*i_L -> lag -> CVS
ln('p2s_iL', P.p2s.out, 'droop', '1'); ln('droop', '1', 'sum_src', '2'); ln('Vref', '1', 'sum_src', '1');
ln('int_vc', '1', 'sum_src', '3'); ln('sum_src', '1', 'inv_tauc', '1'); ln('inv_tauc', '1', 'int_vc', '1');
ln('int_vc', '1', 's2p_vsrc', P.s2p.in);
% faults
ln('fault800', '1', 's2p_sw800', P.s2p.in);  ln('fault48', '1', 's2p_sw48', P.s2p.in);

% ---------------------------------------------------------------- logging
logs = {'p2s_iL','i_L'; 'p2s_vbus','v_bus'; 'p2s_irack','i_rack'; 'p2s_v48','v_out'};
for k = 1:size(logs,1)
    b = blk([SL 'Sinks/To Workspace'], ['log_' logs{k,2}], [x+800+120*(k-1) yk+4*dy x+860+120*(k-1) yk+4*dy+30], ...
        'VariableName', logs{k,2}, 'SaveFormat', 'Array', 'SampleTime', '-1');
    ln(logs{k,1}, P.p2s.out, ['log_' logs{k,2}], '1');
end
blk([SL 'Sources/Clock'], 'clk', [x+800 yk+5*dy x+830 yk+5*dy+30]);
blk([SL 'Sinks/To Workspace'], 'log_t', [x+860 yk+5*dy x+920 yk+5*dy+30], 'VariableName', 't_abs', 'SaveFormat', 'Array', 'SampleTime', '-1');
ln('clk', '1', 'log_t', '1');
save_system(mdl);
end

% ---------------------------------------------------------------- MATLAB Function scripts
function s = ctrl_script()
s = sprintf([ ...
'function [i_in, d_xi, d_Pcmd, d_ico, i_pol] = ctrl(v_Cin, v_out, xi_v, P_cmd, i_co, P_gpu, load_on48, prm)\n' ...
'%% One-to-one with dcsim/model_v04.py _derivs (control part). Pure algebra;\n' ...
'%% the three integrators live outside. v_Cin and v_out are CAPACITOR voltages.\n' ...
'V_ref=prm(1); P_rated=prm(2); V_uvlo=prm(3); smooth_on=prm(4); S_max=prm(5); tau_r=prm(6);\n' ...
'p_fix=prm(7); k2=prm(8); V_ref48=prm(9); K_p=prm(10); K_i=prm(11); tau_i=prm(12); I_lim_out=prm(13);\n' ...
'V_uvlo48=prm(14); conv_on=prm(15);\n' ...
'%% ---- POL load (48 V constant power with UVLO floor)\n' ...
'i_pol = 0;\n' ...
'if load_on48 > 0.5, i_pol = P_gpu / max(v_out, V_uvlo48); end\n' ...
'%% ---- voltage loop demand\n' ...
'err = V_ref48 - v_out;\n' ...
'i_ref = K_p*err + K_i*xi_v;\n' ...
'sat = min(max(i_ref, 0), I_lim_out);\n' ...
'P_out_dem = max(v_out*sat, 0);\n' ...
'P_req = 0; if conv_on > 0.5, P_req = P_out_dem + p_fix*P_rated + k2*P_out_dem^2/P_rated; end\n' ...
'%% ---- converter-input ramp limiter (one state: P_cmd)\n' ...
'd_Pcmd = 0; P_in = P_req;\n' ...
'if smooth_on > 0.5\n' ...
'    d_Pcmd = min(max((P_req - P_cmd)/tau_r, -S_max), S_max);\n' ...
'    if conv_on > 0.5, P_in = P_cmd; else, P_in = 0; end\n' ...
'    P_out_max = max(P_in - p_fix*P_rated, 0);\n' ...
'    i_co_max = P_out_max / max(v_out, 1);\n' ...
'    if sat > i_co_max, sat = i_co_max; end\n' ...
'end\n' ...
'%% ---- anti-windup: freeze whenever the FINAL command differs from i_ref (no sign test)\n' ...
'if sat == i_ref, d_xi = err; else, d_xi = 0; end\n' ...
'%% ---- inner current loop\n' ...
'if conv_on > 0.5, d_ico = (sat - i_co)/tau_i; else, d_ico = -i_co/tau_i; end\n' ...
'%% ---- converter input draw from the input capacitor\n' ...
'i_in = 0; if conv_on > 0.5, i_in = P_in / max(v_Cin, V_uvlo); end\n' ...
'end\n']);
end

function s = uvlo_script()
s = sprintf([ ...
'function load_on48 = uvlo48(v48_node, v_out_cap, prm)\n' ...
'%% POL UVLO state machine, sampled at 1 us (block Sample time). Compares the\n' ...
'%% NODE voltage (with ESR) for the trip, the CAPACITOR voltage for recovery,\n' ...
'%% as dcsim/model_v04.py simulate() does.\n' ...
'V_ref48=prm(9); V_uvlo48=prm(14); t_uvlo48=prm(16); V_hyst48=prm(17); Ts=1e-6;\n' ...
'persistent tmr on\n' ...
'if isempty(tmr), tmr = 0; on = true; end\n' ...
'if v48_node < V_uvlo48\n' ...
'    tmr = tmr + Ts;\n' ...
'    if tmr >= t_uvlo48, on = false; end\n' ...
'else\n' ...
'    tmr = 0;\n' ...
'    if ~on && v_out_cap > V_uvlo48 + V_hyst48, on = true; end\n' ...
'end\n' ...
'load_on48 = double(on);\n' ...
'end\n']);
end
