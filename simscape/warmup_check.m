% warmup_check.m — run warmup_48v_fault.slx and compare the fault current
% with the exact series-RLC capacitor discharge (overdamped, zeta ~ 1.77).
warmup_init;
mdl = 'warmup_48v_fault';
out = sim(mdl);

% --- pull logged signals (To Workspace, Save format: Timeseries)
get_ts = @(name) deal(out.get(name).Time, squeeze(out.get(name).Data));
[t_i, i_f] = get_ts('i_f48');
[t_c, v_C] = get_ts('v_C');
[t_n, v_n] = get_ts('v_node');

% --- uniform 1 us grid after the switch closes (unique() drops the duplicate
%     time points the solver inserts at the switching instant)
tu = (0:1e-6:5e-3)';
[ti, k] = unique(t_i - p.t_sw, 'last');  i_u = interp1(ti, i_f(k), tu);
[tc, k] = unique(t_c - p.t_sw, 'last');  vC_u = interp1(tc, v_C(k), tu);
[tn, k] = unique(t_n - p.t_sw, 'last');  vn_u = interp1(tn, v_n(k), tu);

% --- analytic: L di/dt + R i + (1/C) int i = V0, i(0) = 0
R = p.R_out_esr + p.R_f48;  L = p.L_f48;  C = p.C_out;
a = R / (2*L);  w0 = 1 / sqrt(L*C);  d = sqrt(a^2 - w0^2);
s1 = -a + d;  s2 = -a - d;
i_a = p.V0 / (L*(s1 - s2)) * (exp(s1*tu) - exp(s2*tu));

err = sqrt(mean((i_u - i_a).^2)) / max(i_a);
[pk, kp] = max(i_u);
fprintf('peak fault current %.0f A at %.3f ms (analytic 32865 A at 1.093 ms)\n', pk, tu(kp)*1e3);
fprintf('at 1 ms: v_C = %.2f V (43.55), v_node = %.2f V (33.71)\n', ...
        interp1(tu, vC_u, 1e-3), interp1(tu, vn_u, 1e-3));
fprintf('normalised RMS vs analytic = %.2e  ->  %s\n', err, ...
        string(ifelse(err <= 1e-3, "PASS", "FAIL")));

figure('Name', 'warm-up: C_out into bolted 48 V fault');
subplot(2,1,1); plot(tu*1e3, i_a/1e3, 'k', tu*1e3, i_u/1e3, 'r--'); grid on;
ylabel('i_{f48} (kA)'); legend('analytic', 'Simscape');
subplot(2,1,2); plot(tu*1e3, vC_u, tu*1e3, vn_u); grid on;
xlabel('time after switch closes (ms)'); ylabel('V'); legend('v_C (capacitor)', 'v_{node} (bus, with ESR)');

function y = ifelse(c, a, b)
    if c, y = a; else, y = b; end
end
