function build_dcsim_rt(mdl, dt)
%BUILD_DCSIM_RT  Build dcsim_rt.slx — the HIL-ready form of MODEL.md v0.4.4: one discrete MATLAB Function block that
%   advances the 11 states with the same explicit RK4 as the Python core (dcsim_rt_step / dcsim_rt_derivs), no Simscape,
%   no continuous states, no algebraic loops, fixed-step discrete solver. Plus the breaker element and the HIL I/O:
%     inports   1 TRIP_feeder  2 TRIP_rack                          (3.3 V logic from the nodes -> HIL DI1/DI2)
%     outports  1..4 AO1..AO4 = i_L v_bus i_rack v_out as 0-10 V    (HIL AO1..AO4 -> the nodes' replay inputs)
%               5 SYNC (one-step pulse at fault inception)          (HIL DO1)
%               6 BRK_F  7 BRK_R (breaker states, for the dashboard)
%   Base-workspace variables it reads (run_rt_case sets them): pv (36x1), cfg = [dt qs_dt_min brk_delay uvlo_tol], y0 (11x1),
%   P_gpu_ts (From Workspace table), t_event, f800_on, f48_on, T_record.
%   Saved next to this file. Validate with run_rt_case(<case>, dt, 'slx') / rt_sweep(dt, [], 'slx').
if nargin < 1 || isempty(mdl), mdl = 'dcsim_rt'; end
if nargin < 2 || isempty(dt), dt = 1e-6; end
here = fileparts(mfilename('fullpath'));
slx = fullfile(here, [mdl '.slx']);
if bdIsLoaded(mdl), close_system(mdl, 0); end
if exist(slx, 'file'), delete(slx); end
new_system(mdl); open_system(mdl);
set_param(mdl, 'StopTime', 'T_record', 'SolverType', 'Fixed-step', 'Solver', 'FixedStepDiscrete', ...
          'FixedStep', num2str(dt), 'SaveFormat', 'Array', 'Description', 'dcsim_rt build 2026-10-10 (MODEL.md 0.4.4 + breaker element)');
SL = 'simulink/';
x = 40; y = 40; dy = 70;
    function b = blk(lib, name, pos, varargin)
        b = add_block(lib, [mdl '/' name], 'Position', pos, varargin{:});
    end
    function ln(src, sp, dst, dp)
        add_line(mdl, sprintf('%s/%s', src, sp), sprintf('%s/%s', dst, dp), 'autorouting', 'on');
    end

% ---- sources (inputs of the plant block, in argument order)
blk([SL 'Sources/From Workspace'], 'Pgpu', [x y x+70 y+30], 'VariableName', 'P_gpu_ts', 'Interpolate', 'on', 'OutputAfterFinalValue', 'Holding final value');
blk([SL 'Sources/Constant'], 'Varc', [x y+dy x+70 y+dy+30], 'Value', '0');
blk([SL 'Sources/Step'], 'fault800', [x y+2*dy x+70 y+2*dy+30], 'Time', 't_event', 'Before', '0', 'After', 'f800_on', 'SampleTime', num2str(dt));
blk([SL 'Sources/Step'], 'fault48',  [x y+3*dy x+70 y+3*dy+30], 'Time', 't_event', 'Before', '0', 'After', 'f48_on',  'SampleTime', num2str(dt));
blk([SL 'Sources/In1'], 'TRIP_feeder', [x y+4*dy x+70 y+4*dy+30], 'Port', '1', 'SampleTime', num2str(dt));
blk([SL 'Sources/In1'], 'TRIP_rack',   [x y+5*dy x+70 y+5*dy+30], 'Port', '2', 'SampleTime', num2str(dt));
blk([SL 'Sources/Constant'], 'pv_c',  [x y+6*dy x+70 y+6*dy+30], 'Value', 'pv',  'VectorParams1D', 'on');
blk([SL 'Sources/Constant'], 'cfg_c', [x y+7*dy x+70 y+7*dy+30], 'Value', 'cfg', 'VectorParams1D', 'on');
blk([SL 'Sources/Constant'], 'y0_c',  [x y+8*dy x+70 y+8*dy+30], 'Value', 'y0',  'VectorParams1D', 'on');

% ---- the plant
blk([SL 'User-Defined Functions/MATLAB Function'], 'plant', [x+200 y x+360 y+8*dy+30]);
set_script('plant', plant_script());
ins = {'Pgpu','Varc','fault800','fault48','TRIP_feeder','TRIP_rack','pv_c','cfg_c','y0_c'};
for k = 1:numel(ins), ln(ins{k}, '1', 'plant', num2str(k)); end

% ---- outputs: 1 i_L 2 v_bus 3 i_rack 4 v_out 5 AO(4x1) 6 brk_f 7 brk_r 8 t_trip(2x1) 9 sync
logs = {'i_L','v_bus','i_rack','v_out'};
for k = 1:4
    blk([SL 'Sinks/To Workspace'], ['log_' logs{k}], [x+460 y+(k-1)*dy x+530 y+(k-1)*dy+30], 'VariableName', logs{k}, 'SaveFormat', 'Array', 'SampleTime', '-1');
    ln('plant', num2str(k), ['log_' logs{k}], '1');
end
blk([SL 'Signal Routing/Demux'], 'demux_ao', [x+460 y+4*dy x+470 y+4*dy+110], 'Outputs', '4');
ln('plant', '5', 'demux_ao', '1');
for k = 1:4
    blk([SL 'Sinks/Out1'], sprintf('AO%d', k), [x+520 y+4*dy+(k-1)*30 x+560 y+4*dy+(k-1)*30+20], 'Port', num2str(k));
    ln('demux_ao', num2str(k), sprintf('AO%d', k), '1');
end
blk([SL 'Sinks/To Workspace'], 'log_brk_f', [x+460 y+6*dy x+530 y+6*dy+30], 'VariableName', 'brk_f', 'SaveFormat', 'Array', 'SampleTime', '-1'); ln('plant', '6', 'log_brk_f', '1');
blk([SL 'Sinks/To Workspace'], 'log_brk_r', [x+460 y+7*dy x+530 y+7*dy+30], 'VariableName', 'brk_r', 'SaveFormat', 'Array', 'SampleTime', '-1'); ln('plant', '7', 'log_brk_r', '1');
blk([SL 'Sinks/To Workspace'], 'log_t_trip', [x+460 y+8*dy x+530 y+8*dy+30], 'VariableName', 't_trip', 'SaveFormat', 'Array', 'SampleTime', '-1'); ln('plant', '8', 'log_t_trip', '1');
blk([SL 'Sinks/Out1'], 'SYNC',  [x+600 y+6*dy x+640 y+6*dy+20], 'Port', '5'); ln('plant', '9', 'SYNC', '1');
blk([SL 'Sinks/Out1'], 'BRK_F', [x+600 y+7*dy x+640 y+7*dy+20], 'Port', '6'); ln('plant', '6', 'BRK_F', '1');
blk([SL 'Sinks/Out1'], 'BRK_R', [x+600 y+8*dy x+640 y+8*dy+20], 'Port', '7'); ln('plant', '7', 'BRK_R', '1');
blk([SL 'Sources/Clock'], 'clk', [x+460 y+9*dy x+490 y+9*dy+30]);
blk([SL 'Sinks/To Workspace'], 'log_t', [x+520 y+9*dy x+590 y+9*dy+30], 'VariableName', 't_abs', 'SaveFormat', 'Array', 'SampleTime', '-1');
ln('clk', '1', 'log_t', '1');

save_system(mdl, slx, 'OverwriteIfChangedOnDisk', true);
fprintf('%s saved (fixed-step discrete, %g us). Validate: run_rt_case(''step'', %g, ''slx'')\n', slx, dt * 1e6, dt);

    function set_script(name, txt)
        try
            rt = sfroot; ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [mdl '/' name]);
            ch.Script = txt;
        catch
            cfgo = get_param([mdl '/' name], 'MATLABFunctionConfiguration');   % newer API
            cfgo.FunctionScript = txt;
        end
    end
end

function s = plant_script()
s = sprintf([ ...
'function [i_L, v_bus, i_rack, v_out, AO, brk_f, brk_r, t_trip, sync] = plant(P_gpu, V_arc, f_on, f48_on, trip_f, trip_r, pv, cfg, y0)\n' ...
'%%#codegen\n' ...
'%% MODEL.md v0.4.4 plant, one fixed step per call (dcsim_rt_step), plus the breaker element and HIL scaling.\n' ...
'persistent y st brkf brkr tmr_f tmr_r t_now t_inc t_tf t_tr\n' ...
'if isempty(y)\n' ...
'    y = y0; st = [1;1;0;0]; brkf = 1.0; brkr = 1.0; tmr_f = 0.0; tmr_r = 0.0; t_now = 0.0; t_inc = -1.0; t_tf = -1.0; t_tr = -1.0;\n' ...
'end\n' ...
'dt = cfg(1); qs = cfg(2); dly = cfg(3); utol = cfg(4);\n' ...
'sync = 0.0;\n' ...
'if t_inc < 0.0 && (f_on > 0.5 || f48_on > 0.5), t_inc = t_now; sync = 1.0; end\n' ...
'if trip_f > 0.5\n' ...
'    tmr_f = tmr_f + dt;\n' ...
'    if tmr_f >= dly, if brkf > 0.5, t_tf = t_now; end, brkf = 0.0; end\n' ...
'else\n' ...
'    tmr_f = 0.0;\n' ...
'end\n' ...
'if trip_r > 0.5\n' ...
'    tmr_r = tmr_r + dt;\n' ...
'    if tmr_r >= dly, if brkr > 0.5, t_tr = t_now; end, brkr = 0.0; end\n' ...
'else\n' ...
'    tmr_r = 0.0;\n' ...
'end\n' ...
'[y, st, o] = dcsim_rt_step(y, st, pv, dt, P_gpu, V_arc, f_on, f48_on, brkf, brkr, qs, utol);\n' ...
'i_L = o(2); v_bus = o(3); i_rack = o(15); v_out = o(10);\n' ...
'I_r = pv(2) / pv(1); I48 = pv(2) / pv(25);\n' ...
'AO = [10.0 * i_L / (2.64 * I_r); 10.0 * v_bus / (1.45 * pv(1)); 10.0 * i_rack / (16.5 * I48); 10.0 * v_out / (1.45 * pv(25))];\n' ...
'AO = min(max(AO, 0.0), 10.0);\n' ...
'brk_f = brkf; brk_r = brkr;\n' ...
't_trip = [t_tf; t_tr];\n' ...
'if t_inc >= 0.0, t_trip = t_trip - t_inc; end\n' ...
't_now = t_now + dt;\n' ...
'end\n']);
end
