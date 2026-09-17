function run_all_cases(names)
%RUN_ALL_CASES  Run cross-check cases and score each with the Python comparator.
%   run_all_cases({'step'})   one case (do this first)
%   run_all_cases             all eight
%   Builds the model only if dcsim_shelf.slx does not exist yet, so layout edits made for the
%   video are not overwritten. Uses the repo's .venv Python, not whatever 'python' is on PATH.
P = project_paths();
if nargin < 1
    names = {'step','step_sm','high_z','high_z_sm','high_z_48','high_z_48_sm','bolted_48','bolted_48_sm'};
end
if ~exist(fullfile(P.root, 'simscape', 'dcsim_shelf.slx'), 'file'), build_dcsim_shelf('dcsim_shelf'); end
for k = 1:numel(names)
    run_case(names{k}, P.data, 'dcsim_shelf');
    cmd = sprintf('"%s" "%s" "%s" "%s"', P.python, P.compare, ...
        fullfile(P.data, ['ref_' names{k} '.mat']), fullfile(P.data, ['sim_' names{k} '.mat']));
    [~, txt] = system(cmd); fprintf('%s\n%s\n', names{k}, txt);
end
end
