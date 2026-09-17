function P = project_paths()
%PROJECT_PATHS  Absolute paths for the Simscape cross-check, derived from this file's location.
%   Lives in <repo>\simscape\. Every script uses it, so nothing depends on MATLAB's current folder.
here      = fileparts(mfilename('fullpath'));      % <repo>\simscape
P.root    = fileparts(here);                       % <repo>
P.data    = fullfile(P.root, 'data', 'simscape');
P.python  = fullfile(P.root, '.venv', 'Scripts', 'python.exe');
P.compare = fullfile(P.root, 'scripts', 'compare_simscape.py');
P.cases   = fullfile(P.root, 'scripts', 'simscape_cases.py');
end
