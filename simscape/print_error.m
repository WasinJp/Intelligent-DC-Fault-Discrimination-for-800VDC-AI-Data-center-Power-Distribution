function print_error(e, indent)
%PRINT_ERROR  Print an MException with its whole cause tree. Simulink/Simscape put the real reason
%   (block name, parameter, equation) in nested causes; e.message alone is only the headline.
if nargin < 2, indent = ''; end
msg = regexprep(e.message, '<a [^>]*>|</a>', '');            % strip hyperlinks
fprintf('%s- [%s] %s\n', indent, e.identifier, strrep(msg, newline, [newline indent '    ']));
if isprop(e, 'handles') && ~isempty(e.handles)               % Simulink errors carry the blocks involved
    for h = e.handles(:)'
        try, fprintf('%s    block: %s\n', indent, getfullname(h{1})); catch, end
    end
end
for k = 1:numel(e.cause), print_error(e.cause{k}, [indent '    ']); end
end
