function ensure_cases(datadir)
%ENSURE_CASES  Make sure the Python reference data exists (params.json, cases.json, ref_*.mat).
%   They are written by scripts/simscape_cases.py and are NOT in git. If they are missing this runs
%   the script with the repo's .venv Python (falls back to 'python' on PATH).
P = project_paths();
if nargin < 1, datadir = P.data; end
need = [{'params.json', 'cases.json'}, strcat('ref_', {'step','step_sm','high_z','high_z_sm', ...
        'high_z_48','high_z_48_sm','bolted_48','bolted_48_sm'}, '.mat')];
missing = need(~cellfun(@(f) exist(fullfile(datadir, f), 'file') == 2, need));
if isempty(missing), return, end
fprintf('reference data missing (%d files) - running scripts/simscape_cases.py ...\n', numel(missing));
py = P.python; if exist(py, 'file') ~= 2, py = 'python'; end
old = cd(P.root); back = onCleanup(@() cd(old));
[st, txt] = system(sprintf('"%s" "%s" "%s"', py, P.cases, datadir));
fprintf('%s\n', txt);
missing = need(~cellfun(@(f) exist(fullfile(datadir, f), 'file') == 2, need));
if st ~= 0 || ~isempty(missing)
    error('ensure_cases:failed', ['Could not create the reference data. In a terminal at the repo root run:\n' ...
          '    .venv\\Scripts\\python scripts\\simscape_cases.py\nthen try again.']);
end
end
