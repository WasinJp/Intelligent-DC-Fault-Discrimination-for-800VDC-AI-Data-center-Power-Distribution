function P = shelf_ports()
%SHELF_PORTS  Simscape port conventions for build_dcsim_shelf.m, in one place.
%   test_conventions.m proves these numerically in your MATLAB release before the
%   shelf is built. If a test fails, change the entry here, nowhere else.
P.two.p = 'LConn1'; P.two.n = 'RConn1';                        % R, L, C, Diode (+ = anode), DC Current Source
P.sw.p  = 'LConn1'; P.sw.n  = 'RConn1'; P.sw.ctl = 'LConn2';   % Switch: +, -, PS control
P.ccs.ctl = 'LConn1'; P.ccs.p = 'RConn1'; P.ccs.n = 'RConn2';  % Controlled Current Source: PS in, +, -
P.cvs.ctl = 'LConn1'; P.cvs.p = 'RConn1'; P.cvs.n = 'RConn2';  % Controlled Voltage Source: PS in, +, -
P.isen.p = 'LConn1'; P.isen.n = 'RConn1'; P.isen.out = 'RConn2';   % Current Sensor: +, -, I
P.vsen.p = 'LConn1'; P.vsen.n = 'RConn1'; P.vsen.out = 'RConn2';   % Voltage Sensor: +, -, V
P.ref  = 'LConn1';                                             % Electrical Reference
P.solv = 'RConn1';                                             % Solver Configuration
P.s2p.in = '1';      P.s2p.out = 'RConn1';                     % Simulink-PS Converter
P.p2s.in = 'LConn1'; P.p2s.out = '1';                          % PS-Simulink Converter
end
