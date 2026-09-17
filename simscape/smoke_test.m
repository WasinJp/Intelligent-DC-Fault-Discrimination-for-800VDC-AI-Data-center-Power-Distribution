%SMOKE_TEST  First run after building: the step case must sit EXACTLY at the Python steady state
%   before the event (t < 0). Any wrong sign, diode direction or initial condition shows up here
%   as a drift or a jump, long before the comparison against the reference.
P = project_paths();
if ~exist('dcsim_shelf.slx', 'file'), build_dcsim_shelf('dcsim_shelf'); end
out = run_case('step', P.data, 'dcsim_shelf');
cases = jsondecode(fileread(fullfile(P.data, 'cases.json')));
ic = cases.step.initial_state;
pre = out.t < 0;
expect = struct('i_L', ic.i_L, 'v_bus', ic.v_C, 'i_rack', ic.i_co, 'v_out', ic.v_out);
scale  = struct('i_L', 165, 'v_bus', 800, 'i_rack', 2640, 'v_out', 50);   % per-unit bases
ok = true;
fprintf('\npre-event check (t = -0.2 .. 0 ms), expected vs worst deviation:\n');
for f = fieldnames(expect)'
    k = f{1}; x = out.(k)(pre);
    dev = max(abs(x - expect.(k))) / scale.(k);
    fprintf('  %-7s expected %10.4f   first sample %10.4f   worst deviation %.1e p.u.\n', ...
        k, expect.(k), x(1), dev);
    ok = ok && dev < 1e-4;
end
if ok, fprintf('SMOKE TEST PASS: flat at the Python steady state.\n');
else,  fprintf('SMOKE TEST FAIL: see README "Reading a failure"; send me this printout.\n'); end
