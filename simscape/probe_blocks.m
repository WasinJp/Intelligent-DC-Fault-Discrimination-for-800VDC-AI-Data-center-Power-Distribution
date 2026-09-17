%PROBE_BLOCKS  Before running build_dcsim_shelf: check that every library block and every
%   parameter name the builder uses exists in THIS MATLAB release, and print each block's
%   ports and full parameter list. Send the printed output back if anything says MISSING.
used = {
  'fl_lib/Electrical/Electrical Elements/Resistor',                {'R'}
  'fl_lib/Electrical/Electrical Elements/Capacitor',               {'c','r','g','vc','vc_specify','vc_priority'}
  'fl_lib/Electrical/Electrical Elements/Inductor',                {'l','r','g','i_L','i_L_specify','i_L_priority'}
  'fl_lib/Electrical/Electrical Elements/Diode',                   {'Vf','Ron','Goff'}
  'fl_lib/Electrical/Electrical Elements/Switch',                  {'Threshold','R_closed','G_open'}
  'fl_lib/Electrical/Electrical Elements/Electrical Reference',    {}
  'fl_lib/Electrical/Electrical Sources/DC Current Source',        {'i0'}
  'fl_lib/Electrical/Electrical Sources/Controlled Current Source', {}
  'fl_lib/Electrical/Electrical Sources/Controlled Voltage Source', {}
  'fl_lib/Electrical/Electrical Sensors/Current Sensor',           {}
  'fl_lib/Electrical/Electrical Sensors/Voltage Sensor',           {}
  'nesl_utility/Solver Configuration',                             {'UseLocalSolver'}
  'nesl_utility/Simulink-PS Converter',                            {}
  'nesl_utility/PS-Simulink Converter',                            {}
};
mdl = 'probe_tmp';
if bdIsLoaded(mdl), close_system(mdl, 0); end
new_system(mdl);
nbad = 0;
for k = 1:size(used, 1)
    lib = used{k,1};
    fprintf('\n=== %s\n', lib);
    try
        h = add_block(lib, sprintf('%s/b%d', mdl, k));
    catch e
        fprintf('  MISSING BLOCK: %s\n', e.message); nbad = nbad + 1; continue
    end
    ph = get_param(h, 'PortHandles');
    fprintf('  ports: LConn %d, RConn %d, Inport %d, Outport %d\n', ...
        numel(ph.LConn), numel(ph.RConn), numel(ph.Inport), numel(ph.Outport));
    dp = get_param(h, 'DialogParameters');
    if isempty(dp), names = {}; else, names = fieldnames(dp); end
    for i = 1:numel(names)
        try, v = get_param(h, names{i}); catch, v = '?'; end
        if ~ischar(v), v = mat2str(v); end
        fprintf('    %-26s = %s\n', names{i}, v);
    end
    for i = 1:numel(used{k,2})
        if ~any(strcmp(names, used{k,2}{i}))
            fprintf('  MISSING PARAMETER used by the builder: %s\n', used{k,2}{i}); nbad = nbad + 1;
        end
    end
end
close_system(mdl, 0);
fprintf('\n%d problem(s) found.\n', nbad);
