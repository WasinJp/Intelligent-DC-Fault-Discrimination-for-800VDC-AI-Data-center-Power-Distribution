%VERIFY_BUILD  README checks 2 and 3 on the built model, proven before any simulation:
%   (2) both MATLAB Function blocks actually contain the injected code,
%   (3) uvlo48 and its delay run at a discrete 1 us sample time,
%   plus: the model compiles with algebraic loops treated as errors.
mdl = 'dcsim_shelf';
if ~bdIsLoaded(mdl), load_system(mdl); end
ok = true;

% ---- check 2: script injection
rt = sfroot;
want = {'ctrl',   {'function [i_in, d_xi, d_Pcmd, d_ico, i_pol]', 'sat == i_ref', 'd_Pcmd = min(max('};
        'uvlo48', {'function load_on48 = uvlo48', 'persistent tmr on', 'v_out_cap > V_uvlo48 + V_hyst48'}};
for k = 1:size(want, 1)
    ch = rt.find('-isa', 'Stateflow.EMChart', 'Path', [mdl '/' want{k,1}]);
    if isempty(ch)
        fprintf('check 2  %-7s MATLAB Function block not found\n', want{k,1}); ok = false; continue
    end
    miss = want{k,2}(~cellfun(@(s) contains(ch.Script, s), want{k,2}));
    if isempty(miss)
        fprintf('check 2  %-7s code present\n', want{k,1});
    else
        fprintf('check 2  %-7s MISSING: %s  -> paste the script by hand\n', want{k,1}, strjoin(miss, ' | ')); ok = false;
    end
end

% ---- check 3 + algebraic loops: compile with the step case's parameters
load_case('step');
oldmsg = get_param(mdl, 'AlgebraicLoopMsg');
set_param(mdl, 'AlgebraicLoopMsg', 'error');
try
    feval(mdl, [], [], [], 'compile');
    fprintf('compile  no algebraic loops\n');
    for b = {'uvlo48', 'z_uvlo', 'ctrl'}
        ts = get_param([mdl '/' b{1}], 'CompiledSampleTime');
        if iscell(ts), ts = ts{1}; end
        fprintf('check 3  %-7s compiled sample time [%g %g]', b{1}, ts(1), ts(2));
        if any(strcmp(b{1}, {'uvlo48', 'z_uvlo'}))
            if abs(ts(1) - 1e-6) < 1e-12, fprintf('  OK\n'); else, fprintf('  WRONG, must be [1e-06 0]\n'); ok = false; end
        else
            fprintf('  (continuous expected: [0 0])\n');
        end
    end
    feval(mdl, [], [], [], 'term');
catch e
    try, feval(mdl, [], [], [], 'term'); catch, end
    fprintf('compile  FAILED: %s\n', e.message); ok = false;
end
set_param(mdl, 'AlgebraicLoopMsg', oldmsg);
if ok, fprintf('\nVERIFY PASS: run smoke_test next.\n'); else, fprintf('\nVERIFY FAIL: send me this printout.\n'); end
