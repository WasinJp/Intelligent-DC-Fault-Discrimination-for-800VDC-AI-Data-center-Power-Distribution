function build_dcsim_rt_hil(mdl, dt, shared)
%BUILD_DCSIM_RT_HIL  Build dcsim_rt_hil.slx — the dSPACE-ready demo model: dcsim_rt_hil_plant (validated core + fault
%   scenario + workload generator + re-arm + SYNC + AO scaling) in one discrete MATLAB Function block, every tunable as a
%   Simulink.Parameter (ExportedGlobal), top-level ports only, fixed-step discrete, code-generation clean.
%     inports   1 TRIP_feeder  2 TRIP_rack  3 FAULT_CMD  4 RE_ARM             (box DI, 0/1 doubles)
%     outports  1..4 AO1..AO4  5 SYNC  6 BRK_F  7 BRK_R                      (box AO / DO)
%               8 SIG (28x1, ControlDesk signals, see dcsim_rt_hil_plant)    (no hardware; log / display)
%   Base-workspace variables (dcsim_rt_hil_params creates the parameters; pv and y0 come from the case / design point):
%     pv (36x1) MODEL.md parameter vector, y0 (11x1) initial state, plus the parameters of dcsim_rt_hil_params.
%   Usage:  [c, shared] = load_case('step');  pv = dcsim_rt_pv(shared, c);  y0 = dcsim_rt_hil_y0(pv, 0.5*shared.P_rated, 5e-6);
%           assignin('base','pv',pv); assignin('base','y0',y0);
%           build_dcsim_rt_hil('dcsim_rt_hil', 5e-6, shared);  rt_hil_check(5e-6, 'slx')
if nargin < 1 || isempty(mdl), mdl = 'dcsim_rt_hil'; end
if nargin < 2 || isempty(dt), dt = 5e-6; end
if nargin < 3, shared = []; end
here = fileparts(mfilename('fullpath'));
slx = fullfile(here, [mdl '.slx']);
names = dcsim_rt_hil_params(shared, dt);           % parameters into the base workspace
if bdIsLoaded(mdl), close_system(mdl, 0); end
if exist(slx, 'file'), delete(slx); end
new_system(mdl); open_system(mdl);
set_param(mdl, 'SolverType', 'Fixed-step', 'Solver', 'FixedStepDiscrete', 'FixedStep', 'hil_dt', ...
          'StopTime', 'inf', 'SaveFormat', 'Array', 'SaveTime', 'off', 'SaveOutput', 'off', ...
          'Description', 'dcsim_rt_hil build 2026-10-16 (MODEL.md 0.4.4 + breaker element rev 2, HIL wrapper rev 2: review fixes #1-#13)');
try, set_param(mdl, 'DefaultParameterBehavior', 'Inlined'); catch, end     % Simulink.Parameter ExportedGlobal stays tunable
SL = 'simulink/';
x = 40; y = 40; dy = 40;
    function b = blk(lib, name, pos, varargin)
        b = add_block(lib, [mdl '/' name], 'Position', pos, varargin{:});
    end
    function h = ln(src, sp, dst, dp, nm)
        h = add_line(mdl, sprintf('%s/%s', src, sp), sprintf('%s/%s', dst, dp), 'autorouting', 'on');
        if nargin > 4 && ~isempty(nm), set_param(h, 'Name', nm); end
    end
    function mux_group(gname, list, ypos)
        n = numel(list);
        blk([SL 'Signal Routing/Mux'], ['mux_' gname], [x+150 ypos x+155 ypos+n*18], 'Inputs', num2str(n));
        for i = 1:n
            blk([SL 'Sources/Constant'], list{i}, [x ypos+(i-1)*18 x+90 ypos+(i-1)*18+14], 'Value', list{i}, 'SampleTime', 'hil_dt');
            ln(list{i}, '1', ['mux_' gname], num2str(i));
        end
    end

% ---- inputs
inp = {'TRIP_feeder', 'TRIP_rack', 'FAULT_CMD', 'RE_ARM'};
for k = 1:4
    blk([SL 'Sources/In1'], inp{k}, [x y+(k-1)*dy x+70 y+(k-1)*dy+20], 'Port', num2str(k), 'SampleTime', 'hil_dt');
end
blk([SL 'Sources/Constant'], 'pv_c', [x y+5*dy x+90 y+5*dy+20], 'Value', 'pv', 'VectorParams1D', 'on', 'SampleTime', 'hil_dt');
yg = y + 7 * dy;
mux_group('fp', names.fp, yg);                 yg = yg + numel(names.fp) * 18 + 30;
mux_group('wp', names.wp, yg);                 yg = yg + numel(names.wp) * 18 + 30;
mux_group('cp', names.cp, yg);                 yg = yg + numel(names.cp) * 18 + 30;
blk([SL 'Sources/Constant'], 'y0_c', [x yg x+90 yg+20], 'Value', 'y0', 'VectorParams1D', 'on', 'SampleTime', 'hil_dt');

% ---- the plant
blk([SL 'User-Defined Functions/MATLAB Function'], 'plant', [x+300 y x+480 yg+30]);
set_script('plant', sprintf([ ...
 'function [AO, sync, brk_f, brk_r, sig] = plant(trip_f, trip_r, fault_cmd, rearm_in, pv, fp, wp, cp, y0)\n' ...
 '%%#codegen\n' ...
 '[AO, sync, brk_f, brk_r, sig] = dcsim_rt_hil_plant(trip_f, trip_r, fault_cmd, rearm_in, pv, fp, wp, cp, y0);\n' ...
 'end\n']));
srcs = {'TRIP_feeder', 'TRIP_rack', 'FAULT_CMD', 'RE_ARM', 'pv_c', 'mux_fp', 'mux_wp', 'mux_cp', 'y0_c'};
for k = 1:numel(srcs), ln(srcs{k}, '1', 'plant', num2str(k)); end

% ---- outputs
blk([SL 'Signal Routing/Demux'], 'demux_ao', [x+560 y x+565 y+100], 'Outputs', '4');
ln('plant', '1', 'demux_ao', '1', 'AO');
ao_names = {'AO1_iL', 'AO2_vbus', 'AO3_irack', 'AO4_vout'};
for k = 1:4
    blk([SL 'Sinks/Out1'], sprintf('AO%d', k), [x+640 y+(k-1)*25 x+690 y+(k-1)*25+16], 'Port', num2str(k));
    ln('demux_ao', num2str(k), sprintf('AO%d', k), '1', ao_names{k});
end
blk([SL 'Sinks/Out1'], 'SYNC',  [x+640 y+120 x+690 y+136], 'Port', '5'); ln('plant', '2', 'SYNC', '1', 'SYNC');
blk([SL 'Sinks/Out1'], 'BRK_F', [x+640 y+150 x+690 y+166], 'Port', '6'); ln('plant', '3', 'BRK_F', '1', 'BRK_F');
blk([SL 'Sinks/Out1'], 'BRK_R', [x+640 y+180 x+690 y+196], 'Port', '7'); ln('plant', '4', 'BRK_R', '1', 'BRK_R');
blk([SL 'Sinks/Out1'], 'SIG',   [x+640 y+210 x+690 y+226], 'Port', '8'); ln('plant', '5', 'SIG', '1', 'SIG');
% named test points for ControlDesk / logging (SIG elements by name)
sig_names = {'k','t','P_gpu','event_active','fault_pending','t_inception','clear_f_us','clear_r_us','trip_f_steps', ...
             'trip_r_steps','wl_edge','wl_phase','conv_on','load_on48','i_f','i_f48','v_Cin','P_in','i_co','v_c', ...
             'fault_type_active','V_arc','rearm_count','n_faults','i_L','v_bus','i_rack','v_out'};
blk([SL 'Signal Routing/Demux'], 'demux_sig', [x+560 y+260 x+565 y+260+numel(sig_names)*14], 'Outputs', num2str(numel(sig_names)));
ln('plant', '5', 'demux_sig', '1');
for k = 1:numel(sig_names)
    blk([SL 'Sinks/Terminator'], ['tp_' sig_names{k}], [x+640 y+260+(k-1)*14 x+660 y+260+(k-1)*14+10]);
    h = ln('demux_sig', num2str(k), ['tp_' sig_names{k}], '1', sig_names{k});
    try, set_param(h, 'TestPoint', 'on', 'DataLogging', 'on'); catch, end
end
for k = 1:4, try, set_param(find_system(mdl, 'FindAll', 'on', 'Type', 'line', 'Name', ao_names{k}), 'DataLogging', 'on'); catch, end, end

% ---- the model's data travels with it (2026-10-16): the Constant blocks refer to pv, y0 and the parameter objects by
% name, and an .slx does not store workspace variables. Save them next to the model and load them whenever it opens, so
% a fresh MATLAB session or the dSPACE PC never sees "undefined variable". pv / y0 are taken from the base workspace
% as they are NOW (set them to the design point before building; rt_hil_check overwrites them per case afterwards,
% which no longer matters). The loader keys on the model name: export to another release under the SAME file name
% (a subfolder), not 'dcsim_rt_hil_R20xx.slx'.
datafile = fullfile(here, [mdl '_data.mat']);
if evalin('base', 'exist(''pv'', ''var'') && exist(''y0'', ''var'')')
    vars = [{'pv', 'y0'}, names.fp, names.wp, names.cp];
    evalin('base', sprintf('save(''%s'', %s);', strrep(datafile, '''', ''''''), strjoin(cellfun(@(v) ['''' v ''''], vars, 'UniformOutput', false), ', ')));
    % tolerant loader (final-fixes F2): the model must open even if the data file fails on another release, so the
    % README fallback (load the numbers-only .mat, recreate the parameters) can run before the first update
    set_param(mdl, 'PreLoadFcn', sprintf(['try, load(fullfile(fileparts(which(''%s'')), ''%s_data.mat'')); ' ...
        'catch e, warning(''%s: data file not loaded (%%s) - see README.txt'', e.message); end'], mdl, mdl, mdl));
    fprintf('%s saved (pv, y0 and %d parameters); the model loads it in its PreLoadFcn\n', datafile, numel(vars) - 2);
else
    warning('build_dcsim_rt_hil:nodata', 'pv / y0 not in the base workspace: %s not written, the model will need them defined by hand', datafile);
end
save_system(mdl, slx, 'OverwriteIfChangedOnDisk', true);
fprintf('%s saved (fixed-step discrete, hil_dt = %g us, %d tunable parameters). Validate: rt_hil_check(%g, ''slx'')\n', ...
        slx, dt * 1e6, numel(names.fp) + numel(names.wp) + numel(names.cp), dt);

    function set_script(name, txt)
        try
            rt = sfroot; ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [mdl '/' name]);
            ch.Script = txt;
        catch
            cfgo = get_param([mdl '/' name], 'MATLABFunctionConfiguration');
            cfgo.FunctionScript = txt;
        end
    end
end
