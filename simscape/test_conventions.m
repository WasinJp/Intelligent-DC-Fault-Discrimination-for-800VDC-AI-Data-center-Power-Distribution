function test_conventions()
%TEST_CONVENTIONS  README check 1, proven numerically: the port conventions in shelf_ports.m.
%   Builds a throw-away model 'conv_test' of small one-resistor circuits wired with the SAME
%   port struct the shelf builder uses, simulates 1 ms, and compares every reading with what
%   the convention predicts.
%   - A wrong port INDEX fails loudly while building (add_line refuses to join a physical
%     port to a signal port): read the error, fix shelf_ports.m.
%   - A wrong POLARITY builds fine and only shows as a wrong sign. That is what the
%     readings below catch, before it can hide inside the full shelf model.
%   Only relative signs matter to the shelf (the physics is symmetric under a global flip),
%   so a FAIL names the pair of entries involved.
P = shelf_ports();
mdl = 'conv_test';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl); open_system(mdl);
set_param(mdl, 'StopTime', '1e-3', 'Solver', 'ode23t', 'MaxStep', '1e-5');
FL = 'fl_lib/Electrical/'; NU = 'nesl_utility/'; SL = 'simulink/';
CVS  = [FL 'Electrical Sources/Controlled Voltage Source'];
ISEN = [FL 'Electrical Sensors/Current Sensor'];
nb = 0;  notes = {};

    function bname = blk(lib, name, varargin)
        bname = [mdl '/' name];
        col = mod(nb, 10); rw = floor(nb / 10); nb = nb + 1;
        add_block(lib, bname, 'Position', [30+110*col, 30+90*rw, 70+110*col, 70+90*rw]);
        for q = 1:2:numel(varargin), set_param(bname, varargin{q}, varargin{q+1}); end
    end
    function setp(name, pv)                    % parameters whose names may differ by release
        for q = 1:2:numel(pv)
            try, set_param([mdl '/' name], pv{q}, pv{q+1});
            catch, notes{end+1} = sprintf('%s: could not set parameter ''%s'' (see probe_blocks output)', name, pv{q}); end %#ok<AGROW>
        end
    end
    function ln(src, sp, dst, dp)
        add_line(mdl, [src '/' sp], [dst '/' dp], 'autorouting', 'on');
    end
    function sname = cmd(tag, value)           % Simulink constant -> physical signal
        blk([SL 'Sources/Constant'], [tag '_k'], 'Value', num2str(value));
        sname = [tag '_s2p'];
        blk([NU 'Simulink-PS Converter'], sname);
        ln([tag '_k'], '1', sname, P.s2p.in);
    end
    function meas(src, port, var)              % physical signal -> workspace variable
        blk([NU 'PS-Simulink Converter'], [var '_p2s']);
        blk([SL 'Sinks/To Workspace'], [var '_tw'], 'VariableName', var, 'SaveFormat', 'Array');
        ln(src, port, [var '_p2s'], P.p2s.in);
        ln([var '_p2s'], P.p2s.out, [var '_tw'], '1');
    end
    function res(name, src, sp, value)         % resistor from (src, sp) to ground
        blk([FL 'Electrical Elements/Resistor'], name, 'R', value);
        ln(src, sp, name, P.two.p); ln(name, P.two.n, 'GND', P.ref);
    end
    function vsen(name, src, sp, var)          % voltage sensor from (src, sp) to ground
        blk([FL 'Electrical Sensors/Voltage Sensor'], name);
        ln(src, sp, name, P.vsen.p); ln(name, P.vsen.n, 'GND', P.ref);
        meas(name, P.vsen.out, var);
    end

blk([FL 'Electrical Elements/Electrical Reference'], 'GND');
blk([NU 'Solver Configuration'], 'SolverCfg');
ln('SolverCfg', P.solv, 'GND', P.ref);

% T1  controlled voltage source (+10 V) -> current sensor -> 1 ohm
s = cmd('t1', 10);
blk(CVS, 'T1_cvs'); ln(s, P.s2p.out, 'T1_cvs', P.cvs.ctl); ln('T1_cvs', P.cvs.n, 'GND', P.ref);
blk(ISEN, 'T1_isen'); ln('T1_cvs', P.cvs.p, 'T1_isen', P.isen.p);
res('T1_R', 'T1_isen', P.isen.n, '1');
meas('T1_isen', P.isen.out, 't1_i');
vsen('T1_vs', 'T1_cvs', P.cvs.p, 't1_v');

% T2  controlled current source (+1 A), '+' on a node with 1 ohm to ground
s = cmd('t2', 1);
blk([FL 'Electrical Sources/Controlled Current Source'], 'T2_ccs');
ln(s, P.s2p.out, 'T2_ccs', P.ccs.ctl); ln('T2_ccs', P.ccs.n, 'GND', P.ref);
res('T2_R', 'T2_ccs', P.ccs.p, '1');
vsen('T2_vs', 'T2_ccs', P.ccs.p, 't2_v');

% T3  DC current source (1 A), '+' on a node with 1 ohm to ground
blk([FL 'Electrical Sources/DC Current Source'], 'T3_dcs'); setp('T3_dcs', {'i0', '1'});
ln('T3_dcs', P.two.n, 'GND', P.ref);
res('T3_R', 'T3_dcs', P.two.p, '1');
vsen('T3_vs', 'T3_dcs', P.two.p, 't3_v');

% T4  +10 V -> diode (P.two.p toward the source) -> 1 ohm   (default diode parameters)
s = cmd('t4', 10);
blk(CVS, 'T4_cvs'); ln(s, P.s2p.out, 'T4_cvs', P.cvs.ctl); ln('T4_cvs', P.cvs.n, 'GND', P.ref);
blk([FL 'Electrical Elements/Diode'], 'T4_d'); ln('T4_cvs', P.cvs.p, 'T4_d', P.two.p);
res('T4_R', 'T4_d', P.two.n, '1');
vsen('T4_vs', 'T4_d', P.two.n, 't4_v');

% T5  capacitor 1 F with initial voltage 10 V, 1e9 ohm across it
blk([FL 'Electrical Elements/Capacitor'], 'T5_c'); setp('T5_c', {'c', '1', 'v0', '10', 'v0_priority', 'High'});
ln('T5_c', P.two.n, 'GND', P.ref);
res('T5_R', 'T5_c', P.two.p, '1e9');
vsen('T5_vs', 'T5_c', P.two.p, 't5_v');

% T6  inductor 1 H with initial current 1 A (p -> n), '-' into a current sensor, 1 mOhm loop
blk([FL 'Electrical Elements/Inductor'], 'T6_L'); setp('T6_L', {'l', '1', 'i0', '1'});
ln('T6_L', P.two.p, 'GND', P.ref);
blk(ISEN, 'T6_isen'); ln('T6_L', P.two.n, 'T6_isen', P.isen.p);
res('T6_R', 'T6_isen', P.isen.n, '1e-3');
meas('T6_isen', P.isen.out, 't6_i');

% T7  +10 V -> switch (control 1 = closed / 0 = open) -> 1 ohm
s = cmd('t7', 10); son = cmd('t7on', 1); soff = cmd('t7off', 0);
blk(CVS, 'T7_cvs'); ln(s, P.s2p.out, 'T7_cvs', P.cvs.ctl); ln('T7_cvs', P.cvs.n, 'GND', P.ref);
blk([FL 'Electrical Elements/Switch'], 'T7_swA'); blk([FL 'Electrical Elements/Switch'], 'T7_swB');
ln(son, P.s2p.out, 'T7_swA', P.sw.ctl); ln(soff, P.s2p.out, 'T7_swB', P.sw.ctl);
ln('T7_cvs', P.cvs.p, 'T7_swA', P.sw.p); ln('T7_cvs', P.cvs.p, 'T7_swB', P.sw.p);
res('T7_RA', 'T7_swA', P.sw.n, '1'); res('T7_RB', 'T7_swB', P.sw.n, '1');
vsen('T7_vA', 'T7_swA', P.sw.n, 't7_on'); vsen('T7_vB', 'T7_swB', P.sw.n, 't7_off');

so = sim(mdl, 'ReturnWorkspaceOutputs', 'on');

% name, reading must satisfy, expected text, entries implicated if it does not
checks = {
 't1_v',   @(x) abs(x - 10) < 0.5,  '+10',      'P.cvs.p/n vs P.vsen.p/n'
 't1_i',   @(x) abs(x - 10) < 0.5,  '+10',      'P.cvs.p/n vs P.isen.p/n'
 't2_v',   @(x) abs(x + 1) < 0.05,  '-1',       'P.ccs.p/n: a current source must DRAW from the node on its + port'
 't3_v',   @(x) abs(x + 1) < 0.05,  '-1',       'DC Current Source ports (P.two.p/n) or its i0 name'
 't4_v',   @(x) x > 5,              '> 5 (conducting)', 'P.two.p/n on the Diode: P.two.p must be the ANODE'
 't5_v',   @(x) abs(x - 10) < 0.5,  '+10',      'Capacitor P.two.p/n, or its initial-voltage parameter names'
 't6_i',   @(x) abs(x - 1) < 0.05,  '+1',       'Inductor P.two.p/n, or its initial-current parameter names'
 't7_on',  @(x) abs(x - 10) < 0.5,  '+10',      'P.sw.p/n/ctl (closed at control 1)'
 't7_off', @(x) abs(x) < 0.05,      '0',        'P.sw.ctl (open at control 0)'
};
nfail = 0;
fprintf('\n%-7s %12s   %-18s %s\n', 'test', 'reading', 'expected', 'result');
for kk = 1:size(checks, 1)
    v = so.get(checks{kk,1}); x = double(v(end));
    pass = checks{kk,2}(x);
    if pass, verdict = 'PASS'; else, verdict = ['FAIL -> ' checks{kk,4}]; nfail = nfail + 1; end
    fprintf('%-7s %12.4g   %-18s %s\n', checks{kk,1}, x, checks{kk,3}, verdict);
end
for kk = 1:numel(notes), fprintf('NOTE  %s\n', notes{kk}); end
if nfail == 0 && isempty(notes)
    fprintf('\nALL PASS: shelf_ports.m is correct for this release.\n');
else
    fprintf('\n%d failure(s), %d note(s). Send me this printout (and probe_blocks output if there are notes).\n', nfail, numel(notes));
end
end
