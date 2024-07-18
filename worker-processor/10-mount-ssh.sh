#!/usr/bin/env bash
set -e

# Using `-v $HOME/.ssh:/opt/omero/server/.ssh:ro` produce permissions error while in the container
# when working from Linux and maybe from Windows.
# To prevent that we offer the strategy to mount the `.ssh` folder with
# `-v $HOME/.ssh:/tmp/.ssh:ro` thus this entrypoint will automatically handle problem.

if [[ -d /tmp/.ssh ]]; then
  # TODO: error on windows ? this didn't copy 'config'
  cp -R /tmp/.ssh /opt/omero/server/.ssh
  chmod 700 /opt/omero/server/.ssh
  chmod 600 /opt/omero/server/.ssh/* || true
  chmod 644 /opt/omero/server/.ssh/*.pub || true
  chmod 644 /opt/omero/server/.ssh/known_hosts || true
fi

exec "$@"