FROM openmicroscopy/omero-server:5.6.3

COPY worker-gpu/ice.config worker-gpu/worker.cfg /opt/omero/server/OMERO.server/etc/templates/

USER root

## Default Python environment
ENV VIRTUAL_ENV=/opt/omero/server/venv3
ENV PATH=/opt/ice-3.6.5-0.3.0/bin:$VIRTUAL_ENV/bin/:$PATH
RUN python3 -m venv $VIRTUAL_ENV

## Create extra Python environments
# There is no clone with 'venv' so we have to reinstall from requirements file instead
RUN python -m pip freeze > requirements.txt
# Create Python environment for Cellpose
ARG VIRTUAL_ENV_CP
ENV VIRTUAL_ENV_CP=${VIRTUAL_ENV_CP}
RUN python3 -m venv $VIRTUAL_ENV_CP
RUN $VIRTUAL_ENV_CP/bin/python -m pip install --upgrade pip
RUN $VIRTUAL_ENV_CP/bin/python -m pip install -r requirements.txt
RUN $VIRTUAL_ENV_CP/bin/python -m pip install mxnet-mkl
RUN $VIRTUAL_ENV_CP/bin/python -m pip install matplotlib
RUN $VIRTUAL_ENV_CP/bin/python -m pip install cellpose
# # Create Python environment for Stardist
ARG VIRTUAL_ENV_SD
ENV VIRTUAL_ENV_SD=${VIRTUAL_ENV_SD}
RUN python3 -m venv $VIRTUAL_ENV_SD
RUN $VIRTUAL_ENV_SD/bin/python -m pip install --upgrade pip
RUN $VIRTUAL_ENV_SD/bin/python -m pip install -r requirements.txt
RUN $VIRTUAL_ENV_SD/bin/python -m pip install tensorflow 
RUN $VIRTUAL_ENV_SD/bin/python -m pip install stardist

## Adjust processor code with AMC Processor
COPY processor.py /opt/omero/server/venv3/lib/python3.6/site-packages/omero/

## Replace the default startup scripts
RUN rm /startup/60-database.sh
COPY worker-gpu/99-run.sh /startup/99-run.sh
USER omero-server
