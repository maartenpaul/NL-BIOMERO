FROM openmicroscopy/omero-server:5.6.13

ARG BIOMERO_VERSION

# Upload scripts for omero-server user
# COPY --chown=omero-server:omero-server scripts/slurm/* /opt/omero/server/OMERO.server/lib/scripts/slurm/
USER root
RUN yum -y install git 
USER omero-server

# Configuration file
ADD server/01-ldap-config.omero /opt/omero/server/config/

# Invalidate cache for development builds
# ADD "https://api.github.com/repos/NL-BioImaging/biomero-scripts/commits?per_page=1" latest_comm
# Now just pulling released / tagged versions
RUN  cd /opt/omero/server/OMERO.server/lib/scripts/ && \
    git clone --depth 1 --branch database https://github.com/NL-BioImaging/biomero-scripts.git biomero
    # git clone --depth 1 https://github.com/NL-BioImaging/biomero-scripts.git biomero

# Overwrite ICE configuration
# COPY ice.config /opt/omero/server/OMERO.server/etc/templates/
# Overwrite startup run
# COPY 99-run.sh /startup/99-run.sh

# entrypoint from omero-server dockerfile: 
# run all /startup/* scripts in alphabetic/numerical order.
