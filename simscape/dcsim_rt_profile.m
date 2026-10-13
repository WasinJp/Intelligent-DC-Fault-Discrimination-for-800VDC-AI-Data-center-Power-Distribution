function P = dcsim_rt_profile(c, shared, t)
%DCSIM_RT_PROFILE  GPU power demand of a cross-check case at time t (s, absolute), exactly as scripts/simscape_cases.py:
%   step: P0 + 0.4 P_rated * clip((t - t_event) / 2 ms, 0, 1); every other case: P0.
P = c.P0 * ones(size(t));
if strcmp(c.kind, 'step')
    r = (t - c.t_event) / 2e-3;
    r(r < 0) = 0; r(r > 1) = 1;
    P = c.P0 + 0.4 * shared.P_rated * r;
end
end
