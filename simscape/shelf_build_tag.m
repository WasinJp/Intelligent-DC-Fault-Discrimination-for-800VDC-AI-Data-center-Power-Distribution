function tag = shelf_build_tag()
%SHELF_BUILD_TAG  Version of the builder. Stored in the model's Description; crosscheck rebuilds
%   dcsim_shelf.slx when it does not match (a stale model is the quietest way to fail check (i)).
tag = 'dcsim_shelf build 2026-09-18h (control states integrated explicitly at 1 us in ctrl_d)';
end
