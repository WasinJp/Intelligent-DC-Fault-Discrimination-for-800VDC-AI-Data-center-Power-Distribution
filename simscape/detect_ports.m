function P = detect_ports()
%DETECT_PORTS  Find the Simscape port conventions of THIS MATLAB release by experiment and
%   write them to shelf_ports.m. Replaces hand-editing of shelf_ports.m.
%
%   Two stages, no guessing:
%   A. ROLE of each port (physical-signal vs electrical). add_line refuses to join a physical
%      signal port to an electrical port, so for every block that has a signal port we try each
%      port against a converter and keep the one that connects.
%   B. POLARITY of the electrical pair. The test circuits of test_conventions.m are built with a
%      tentative polarity, simulated once, and every reading with the wrong sign flips its entry.
%      The Controlled Voltage Source is the anchor (only relative signs matter to the shelf).
%   Then shelf_ports.m is written and test_conventions runs again from the file as confirmation.
%
%   Order of use:  probe_blocks -> detect_ports -> build_dcsim_shelf -> verify_build -> smoke_test
FL = 'fl_lib/Electrical/'; NU = 'nesl_utility/';
mdl = 'detect_tmp';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
nb = 0;

    function names = portnames(b)
        ph = get_param([mdl '/' b], 'PortHandles');
        names = {};
        for q = 1:numel(ph.LConn), names{end+1} = sprintf('LConn%d', q); end %#ok<AGROW>
        for q = 1:numel(ph.RConn), names{end+1} = sprintf('RConn%d', q); end %#ok<AGROW>
    end
    function ok = can_join(a, ap, b, bp)
        ok = true;
        try
            h = add_line(mdl, [a '/' ap], [b '/' bp]);
            delete_line(h);
        catch
            ok = false;
        end
    end
    function [sig, el] = classify(lib, kind)
        % kind 'in'  : block has a physical-signal INPUT  (tested against a Simulink-PS Converter output)
        % kind 'out' : block has a physical-signal OUTPUT (tested against a PS-Simulink Converter input)
        nb = nb + 1; b = sprintf('b%d', nb); add_block(lib, [mdl '/' b]);
        nb = nb + 1; c = sprintf('c%d', nb);
        if strcmp(kind, 'in'), add_block([NU 'Simulink-PS Converter'], [mdl '/' c]);
        else,                  add_block([NU 'PS-Simulink Converter'], [mdl '/' c]); end
        pn = portnames(b); hit = false(size(pn));
        for q = 1:numel(pn)
            if strcmp(kind, 'in'), hit(q) = can_join(c, 'RConn1', b, pn{q});
            else,                  hit(q) = can_join(b, pn{q}, c, 'LConn1'); end
        end
        fprintf('  %-62s signal port: %-7s electrical: %s\n', lib, strjoin(pn(hit), ','), strjoin(pn(~hit), ','));
        if nnz(hit) ~= 1 || nnz(~hit) ~= 2
            error('detect_ports:roles', 'Expected 1 signal + 2 electrical ports on %s. Send me this printout.', lib);
        end
        sig = pn{hit}; el = pn(~hit);
    end

% ------------------------------------------------------------------ stage A: roles
fprintf('\nStage A - port roles by trial connection\n');
[s, e] = classify([FL 'Electrical Sources/Controlled Voltage Source'], 'in');  P.cvs  = struct('ctl', s, 'p', e{1}, 'n', e{2});
[s, e] = classify([FL 'Electrical Sources/Controlled Current Source'], 'in');  P.ccs  = struct('ctl', s, 'p', e{1}, 'n', e{2});
[s, e] = classify([FL 'Electrical Elements/Switch'], 'in');                    P.sw   = struct('ctl', s, 'p', e{1}, 'n', e{2});
[s, e] = classify([FL 'Electrical Sensors/Current Sensor'], 'out');            P.isen = struct('out', s, 'p', e{1}, 'n', e{2});
[s, e] = classify([FL 'Electrical Sensors/Voltage Sensor'], 'out');            P.vsen = struct('out', s, 'p', e{1}, 'n', e{2});
close_system(mdl, 0);
% two-terminal blocks: one left port, one right port (probe_blocks confirmed); polarity in stage B
two = struct('p', 'LConn1', 'n', 'RConn1');
P.two = two; P.cap = two; P.ind = two; P.dio = two; P.dcs = two;
P.ref = 'LConn1'; P.solv = 'RConn1';
P.s2p = struct('in', '1', 'out', 'RConn1');
P.p2s = struct('in', 'LConn1', 'out', '1');

% ------------------------------------------------------------------ stage B: polarity
fprintf('\nStage B - polarity by simulation (tentative wiring; FAIL lines here are expected and get corrected)\n');
[~, r] = test_conventions(P);
if abs(abs(r.t1_v) - 10) > 0.5 || abs(abs(r.t1_i) - 10) > 0.5
    error('detect_ports:anchor', 'Anchor circuit T1 read v = %g, i = %g (expected +-10). Send me this printout.', r.t1_v, r.t1_i);
end
sv = sign(r.t1_v); si = sign(r.t1_i);
flipped = {};
if sv < 0,               P.vsen = swap(P.vsen); flipped{end+1} = 'vsen'; end
if si < 0,               P.isen = swap(P.isen); flipped{end+1} = 'isen'; end
if sv * r.t2_v > 0,      P.ccs  = swap(P.ccs);  flipped{end+1} = 'ccs';  end   % '+' must DRAW from its node
if sv * r.t3_v > 0,      P.dcs  = swap(P.dcs);  flipped{end+1} = 'dcs';  end
if sv * r.t4_v < 5,      P.dio  = swap(P.dio);  flipped{end+1} = 'dio';  end   % p must be the ANODE
if sv * r.t5_v < 0,      P.cap  = swap(P.cap);  flipped{end+1} = 'cap';  end
if si * r.t6_i < 0,      P.ind  = swap(P.ind);  flipped{end+1} = 'ind';  end
if isempty(flipped), fprintf('\nno polarity flips needed\n'); else, fprintf('\nflipped: %s\n', strjoin(flipped, ', ')); end

% ------------------------------------------------------------------ write shelf_ports.m
here = fileparts(mfilename('fullpath'));
fn = fullfile(here, 'shelf_ports.m');
fid = fopen(fn, 'w');
fprintf(fid, 'function P = shelf_ports()\n');
fprintf(fid, '%%SHELF_PORTS  Simscape port conventions for build_dcsim_shelf.m.\n');
fprintf(fid, '%%   GENERATED by detect_ports.m on %s (MATLAB %s). Do not edit by hand; re-run detect_ports.\n', char(datetime('now', 'Format', 'yyyy-MM-dd HH:mm')), version('-release'));
fprintf(fid, '%%   p/n meaning: sources and sensors as labelled by the numeric tests in test_conventions.m\n');
fprintf(fid, '%%   (ccs/dcs: current is DRAWN from the node on p; dio: p is the anode; cap: v = p - n; ind: i flows p -> n).\n');
w3 = @(name, a, b, c, sa, sb, sc) fprintf(fid, 'P.%s.%s = ''%s''; P.%s.%s = ''%s''; P.%s.%s = ''%s'';\n', name, a, sa, name, b, sb, name, c, sc);
w3('cvs',  'ctl', 'p', 'n', P.cvs.ctl,  P.cvs.p,  P.cvs.n);
w3('ccs',  'ctl', 'p', 'n', P.ccs.ctl,  P.ccs.p,  P.ccs.n);
w3('sw',   'ctl', 'p', 'n', P.sw.ctl,   P.sw.p,   P.sw.n);
w3('isen', 'out', 'p', 'n', P.isen.out, P.isen.p, P.isen.n);
w3('vsen', 'out', 'p', 'n', P.vsen.out, P.vsen.p, P.vsen.n);
for f = {'two', 'cap', 'ind', 'dio', 'dcs'}
    fprintf(fid, 'P.%s.p = ''%s''; P.%s.n = ''%s'';\n', f{1}, P.(f{1}).p, f{1}, P.(f{1}).n);
end
fprintf(fid, 'P.ref = ''%s''; P.solv = ''%s'';\n', P.ref, P.solv);
fprintf(fid, 'P.s2p.in = ''%s''; P.s2p.out = ''%s'';\n', P.s2p.in, P.s2p.out);
fprintf(fid, 'P.p2s.in = ''%s''; P.p2s.out = ''%s'';\n', P.p2s.in, P.p2s.out);
fprintf(fid, 'end\n');
fclose(fid);
evalin('base', 'clear shelf_ports'); rehash;          % drop the cached old version of the file
fprintf('\nwrote %s\n', fn);

% ------------------------------------------------------------------ confirmation from the file
fprintf('\nConfirmation - test_conventions from the generated shelf_ports.m (must be ALL PASS)\n');
Pf = shelf_ports();
if ~isequal(Pf, P), error('detect_ports:file', 'shelf_ports.m on disk does not match what was detected (stale copy on the path?).'); end
nfail = test_conventions(Pf);
if nfail == 0
    fprintf('\nDETECT PASS: run build_dcsim_shelf next, then verify_build, then smoke_test.\n');
else
    fprintf('\nDETECT FAIL: send me this whole printout.\n');
end
end

function s = swap(s)
t = s.p; s.p = s.n; s.n = t;
end
