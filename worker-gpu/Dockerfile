FROM openmicroscopy/omero-server:5.6.8


COPY worker-gpu/ice.config worker-gpu/worker.cfg /opt/omero/server/OMERO.server/etc/templates/

USER root

## Default Python environment
ENV VIRTUAL_ENV=/opt/omero/server/venv3
ENV PATH=/opt/ice-3.6.5-0.3.0/bin:$VIRTUAL_ENV/bin/:$PATH
RUN yum -y update \
    && yum -y install git 

RUN python3 -m venv $VIRTUAL_ENV \
    && python3 -m pip install --upgrade pip \ 
    # TODO: add version to slurm client after release
    && python3 -m pip install 'git+https://github.com/NL-BioImaging/omero-slurm-client@v0.1.2-alpha' \
    && python3 -m pip install ezomero==1.1.1 tifffile==2020.9.3

# SSH library fabric and omero-slurm-client

## Create extra Python environments
# There is no clone with 'venv' so we have to reinstall from requirements file instead
RUN python3 -m pip freeze > requirements.txt
# Create Python environment for Cellpose
ARG VIRTUAL_ENV_CP
ENV VIRTUAL_ENV_CP=${VIRTUAL_ENV_CP}
RUN python3 -m venv $VIRTUAL_ENV_CP
RUN $VIRTUAL_ENV_CP/bin/python -m pip install --upgrade pip \
    && $VIRTUAL_ENV_CP/bin/python -m pip install -r requirements.txt \ 
    && $VIRTUAL_ENV_CP/bin/python -m pip install mxnet-mkl==1.6.0 matplotlib==3.3.4 opencv-python-headless==4.6.0.66 cellpose==0.0.3.1

# # Create Python environment for Stardist
ARG VIRTUAL_ENV_SD
ENV VIRTUAL_ENV_SD=${VIRTUAL_ENV_SD}
RUN python3 -m venv $VIRTUAL_ENV_SD
ENV SETUPTOOLS_SCM_PRETEND_VERSION=1
RUN $VIRTUAL_ENV_SD/bin/python -m pip install --upgrade pip \
    && $VIRTUAL_ENV_SD/bin/python -m pip install -r requirements.txt \
    && $VIRTUAL_ENV_SD/bin/python -m pip install tensorflow==2.6.2 stardist==0.8.3

## Adjust processor code with AMC Processor
COPY processor.py /opt/omero/server/venv3/lib/python3.6/site-packages/omero/

## Replace the default configuration files
COPY worker-gpu/ice.config worker-gpu/worker.cfg /opt/omero/server/OMERO.server/etc/templates/

## Install SSH client
RUN yum install -y openssh-clients
COPY worker-gpu/10-mount-ssh.sh /startup/10-mount-ssh.sh
RUN chmod +x /startup/10-mount-ssh.sh
## Setup slurm-config for omero-slurm-client
COPY worker-gpu/slurm-config.ini /etc/slurm-config.ini

## Setup OME ZARR & TIFF modules for data export
RUN python3 -m pip install omero-cli-zarr==0.5.3
RUN yum install -y blosc-devel

# Sadly can't do this in Dockerfile:
# ENV JAVA_HOME=$(readlink -f /usr/bin/java | sed "s:/bin/java::")
ENV JAVA_HOME=/usr/lib/jvm/java-11-openjdk-11.0.20.0.8-1.el7_9.x86_64

RUN wget https://github.com/glencoesoftware/raw2ometiff/releases/download/v0.5.0/raw2ometiff-0.5.0.zip \
    ; unzip -d /opt raw2ometiff-0.5.0.zip \
    && rm raw2ometiff-0.5.0.zip
ENV PATH="$PATH:/opt/raw2ometiff-0.5.0/bin"
# ENV PATH=/opt/ice-3.6.5-0.3.0/bin:$VIRTUAL_ENV/bin/:$PATH

RUN wget https://github.com/glencoesoftware/bioformats2raw/releases/download/v0.7.0/bioformats2raw-0.7.0.zip \
    ; unzip -d /opt bioformats2raw-0.7.0.zip \
    && rm bioformats2raw-0.7.0.zip
ENV PATH="$PATH:/opt/bioformats2raw-0.7.0/bin"

## OMERO: Replace the default startup scripts
RUN rm /startup/60-database.sh
COPY worker-gpu/99-run.sh /startup/99-run.sh
USER omero-server
