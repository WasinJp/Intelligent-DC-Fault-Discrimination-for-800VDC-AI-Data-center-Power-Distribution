function simfile = ctrldesk_to_simmat(capture, case_name, outdir, map)
%CTRLDESK_TO_SIMMAT  Turn a ControlDesk measurement of dcsim_rt_hil running on the box into the sim_<case>.mat layout
%   that scripts/compare_simscape.py scores — check (i) on the real-time target.
%     simfile = ctrldesk_to_simmat('capture_high_z.mat', 'high_z')
%     simfile = ctrldesk_to_simmat('capture.csv', 'bolted_48', 'data/simscape/rt_hil/box')
%   capture: a .mat exported by ControlDesk (its usual layout: variables with .X.Data (time) and .Y(i).Data / .Y(i).Name,
%            or one struct holding them) or a .csv with a header row (time column + signal columns);
%   map:     optional struct naming the capture's signals: fields t, i_L, v_bus, i_rack, v_out, sync
%            (default: these exact names; the model's SIG test points are named so). Any case-insensitive substring
%            match is accepted ("i_L", "Model Root/.../i_L", ...).
%   Alignment: t = 0 at the SYNC rising edge (= fault inception in the model), so the record lines up with the reference
%   window (-0.2 .. +5 ms). Then:  python scripts/compare_simscape.py data/simscape/ref_<case>.mat <simfile>
if nargin < 3 || isempty(outdir), P = project_paths(); outdir = fullfile(P.data, 'rt_hil', 'box'); end
if nargin < 4 || isempty(map), map = struct('t', 't', 'i_L', 'i_L', 'v_bus', 'v_bus', 'i_rack', 'i_rack', 'v_out', 'v_out', 'sync', 'SYNC'); end
if ~exist(outdir, 'dir'), mkdir(outdir); end
[~, ~, ext] = fileparts(capture);
sig = struct();
if strcmpi(ext, '.csv')
    T = readtable(capture, 'VariableNamingRule', 'preserve');
    vn = T.Properties.VariableNames;
    for f = fieldnames(map)'
        j = find(contains(lower(vn), lower(map.(f{1}))), 1);
        if isempty(j), error('ctrldesk_to_simmat: column for %s (%s) not found in %s', f{1}, map.(f{1}), capture); end
        sig.(f{1}) = T{:, j};
    end
else
    S = load(capture);
    % ControlDesk .mat: find a struct with X and Y
    fn = fieldnames(S); M = [];
    for i = 1:numel(fn)
        v = S.(fn{i});
        if isstruct(v) && isfield(v, 'X') && isfield(v, 'Y'), M = v; break; end
    end
    if isempty(M), error('ctrldesk_to_simmat: no X/Y measurement struct found in %s', capture); end
    sig.t = double(M.X(1).Data(:));
    names = arrayfun(@(y) char(y.Name), M.Y, 'UniformOutput', false);
    for f = {'i_L', 'v_bus', 'i_rack', 'v_out', 'sync'}
        j = find(contains(lower(names), lower(map.(f{1}))), 1);
        if isempty(j), error('ctrldesk_to_simmat: signal for %s (%s) not found; available: %s', f{1}, map.(f{1}), strjoin(names, ', ')); end
        sig.(f{1}) = double(M.Y(j).Data(:));
    end
end
k0 = find(sig.sync > 0.5, 1);
if isempty(k0), error('ctrldesk_to_simmat: no SYNC edge in the capture'); end
t = sig.t - sig.t(k0);
m = (t >= -0.2e-3 - 1e-9) & (t <= 5e-3 + 1e-9);
out = struct('t', t(m), 'i_L', sig.i_L(m), 'v_bus', sig.v_bus(m), 'i_rack', sig.i_rack(m), 'v_out', sig.v_out(m), 'dbg_sync', sig.sync(m));
simfile = fullfile(outdir, ['sim_' case_name '.mat']);
save(simfile, '-struct', 'out');
dtc = median(diff(t));
fprintf('%s: %d samples in the window, capture step %.2f us (the comparator interpolates onto the reference grid)\n', simfile, nnz(m), dtc * 1e6);
end
