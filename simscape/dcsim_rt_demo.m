function dcsim_rt_demo(case_name, t_trip_after, which)
%DCSIM_RT_DEMO  Closed-loop demonstration on the desktop: the fixed-step plant runs, a scripted TRIP arrives
%   t_trip_after seconds after fault inception (default 0.35 ms = the pre-registered median of the relay), the model's
%   breaker opens, and the four HIL outputs plus the breaker state are plotted. This is the picture for Prof. Supachai
%   and the HIL owner: the plant the box will run, the signals it will output, the breaker closing the loop.
%   dcsim_rt_demo                       bolted_48, rack TRIP at +0.35 ms
%   dcsim_rt_demo('high_z', 0.36e-3, 'f')   high-Z 800 V fault, feeder TRIP at +0.36 ms
%   Writes simscape/rt_demo_<case>.png. Needs dcsim_rt.slx (built on first use).
if nargin < 1 || isempty(case_name), case_name = 'bolted_48'; end
if nargin < 2 || isempty(t_trip_after), t_trip_after = 0.35e-3; end
if nargin < 3 || isempty(which), if contains(case_name, '48'), which = 'r'; else, which = 'f'; end, end
P = project_paths();
[c, shared] = load_case(case_name, P.data);
dt = 1e-6; T = shared.T_record; t0 = c.t_event;
t = (0:dt:T)';
trip = struct('t', t, 'trip_f', zeros(size(t)), 'trip_r', zeros(size(t)));
on = t >= t0 + t_trip_after;
if which == 'f', trip.trip_f(on) = 1; else, trip.trip_r(on) = 1; end
R = run_rt_case(case_name, dt, 'slx', trip);                 % closed loop: scored only up to the breaker opening (see run_rt_case)
S = load(R.file);
I_r = shared.P_rated / shared.V_ref; I48 = shared.P_rated / shared.V_ref48;
tm = S.t * 1e3;
f = figure('Color', 'w', 'Position', [100 100 1100 750]);
sub = @(k) subplot(3, 2, k);
sub(1); plot(tm, S.i_L / I_r, 'LineWidth', 1.2); grid on; ylabel('i_L (p.u.)'); title(sprintf('%s — feeder node', strrep(case_name, '_', '\_')));
sub(2); plot(tm, S.i_rack / I48, 'LineWidth', 1.2, 'Color', [0.85 0.48 0.04]); grid on; ylabel('i_{rack} (p.u.)'); title('rack node');
sub(3); plot(tm, S.v_bus / shared.V_ref, 'LineWidth', 1.2); grid on; ylabel('v_{bus} (p.u.)');
sub(4); plot(tm, S.v_out / shared.V_ref48, 'LineWidth', 1.2, 'Color', [0.85 0.48 0.04]); grid on; ylabel('v_{out} (p.u.)');
sub(5); AO = [10 * S.i_L / (2.64 * I_r), 10 * S.v_bus / (1.45 * shared.V_ref), 10 * S.i_rack / (16.5 * I48), 10 * S.v_out / (1.45 * shared.V_ref48)];
plot(tm, min(max(AO, 0), 10), 'LineWidth', 1.1); grid on; ylabel('HIL AO1..AO4 (V)'); xlabel('t − t_{event} (ms)'); legend({'AO1 i_L','AO2 v_{bus}','AO3 i_{rack}','AO4 v_{out}'}, 'Location', 'best');
sub(6); stairs(tm, [S.dbg_brk_f, S.dbg_brk_r], 'LineWidth', 1.4); ylim([-0.1 1.1]); grid on; ylabel('breaker closed'); xlabel('t − t_{event} (ms)'); legend({'SSCB_f','SSCB_r'}, 'Location', 'best');
if isfield(S, 'dbg_t_trip') && size(S.dbg_t_trip, 2) == 2
    tt = S.dbg_t_trip(end, :);
else                                     % derive from the breaker states (first sample at 0), relative to the event
    tt = [-1 -1];
    kf = find(S.dbg_brk_f < 0.5, 1); if ~isempty(kf), tt(1) = S.t(kf); end
    kr = find(S.dbg_brk_r < 0.5, 1); if ~isempty(kr), tt(2) = S.t(kr); end
end
sgtitle(sprintf('dcsim\\_rt closed loop — %s, TRIP %s at +%.0f µs after inception; model-measured inception → breaker: f %.0f µs, r %.0f µs', ...
    strrep(case_name, '_', '\_'), which, t_trip_after * 1e6, tt(1) * 1e6, tt(2) * 1e6));
png = fullfile(fileparts(mfilename('fullpath')), ['rt_demo_' case_name '.png']);
exportgraphics(f, png, 'Resolution', 150);
fprintf('demo figure: %s\n', png);
end
