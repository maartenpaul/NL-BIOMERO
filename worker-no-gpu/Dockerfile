FROM openmicroscopy/omero-server:5.6.8

COPY worker-no-gpu/ice.config worker-no-gpu/worker.cfg /opt/omero/server/OMERO.server/etc/templates/

USER root

# Improve python environment
ENV VIRTUAL_ENV=/opt/omero/server/venv3
ENV PATH=/opt/ice-3.6.5-0.3.0/bin:$VIRTUAL_ENV/bin/:$PATH
RUN python3 -m venv $VIRTUAL_ENV
RUN python -m pip install scikit-image scipy

# Adjust processor code
COPY processor.py /opt/omero/server/venv3/lib/python3.6/site-packages/omero/

# Replace the default startup scripts
RUN rm /startup/60-database.sh
COPY worker-no-gpu/99-run.sh /startup/99-run.sh
USER omero-server
