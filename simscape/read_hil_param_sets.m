function T = read_hil_param_sets(file)
%READ_HIL_PARAM_SETS  Read hil_param_sets.csv into a table with the header names exactly as written
%   (set, kind, fault_type, ..., note). readtable's automatic import detection can misread this file — the long
%   quoted notes with commas make it guess the header wrong, so T.set does not exist — therefore read the raw cells
%   and build the table from the first row. Numbers come back as doubles, text as char.
%   T = read_hil_param_sets()                       -> hil_param_sets.csv next to this file
%   T = read_hil_param_sets('path\hil_param_sets.csv')
if nargin < 1 || isempty(file), file = fullfile(fileparts(mfilename('fullpath')), 'hil_param_sets.csv'); end
C = readcell(file, 'Delimiter', ',', 'NumHeaderLines', 0);
hdr = cellfun(@char, C(1, :), 'UniformOutput', false);
body = C(2:end, :);
for j = 1:size(body, 2)                              % a missing text cell comes back as <missing>: make it ''
    for i = 1:size(body, 1)
        if isa(body{i, j}, 'missing'), body{i, j} = ''; end
    end
end
T = cell2table(body, 'VariableNames', hdr);
if ~ismember('set', hdr)
    error('read_hil_param_sets:header', 'no ''set'' column in %s (header: %s)', file, strjoin(hdr, ', '));
end
end
