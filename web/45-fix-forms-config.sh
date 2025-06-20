#!/bin/bash
set -eu

omero=/opt/omero/web/venv3/bin/omero
ROOTPASS="${ROOTPASS:-omero}"
OMEROHOST=${OMEROHOST:-}


# Now handle config file updates
echo "Updating OMERO.forms configuration..."
TEMP_DIR="/tmp/forms-config"
mkdir -p $TEMP_DIR
chmod 777 $TEMP_DIR

envsubst < /opt/omero/web/config/01-default-webapps.omero > $TEMP_DIR/01-default-webapps.omero

if [ -f "$TEMP_DIR/01-default-webapps.omero" ]; then
    cp $TEMP_DIR/01-default-webapps.omero /opt/omero/web/config/01-default-webapps.omero
fi

rm -rf $TEMP_DIR