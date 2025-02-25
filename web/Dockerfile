FROM openmicroscopy/omero-web-standalone:5.28.0

USER root

# Create L-Drive directory and set permissions
RUN mkdir -p /L-Drive && \
    chown omero-web:omero-web /L-Drive && \
    chmod 755 /L-Drive

# Add volume mount point for L-Drive
VOLUME ["/L-Drive"]

### Pretty Login ###
COPY web/local_omeroweb_edits/pretty_login/get_images_for_login_page.py /script/
COPY web/local_omeroweb_edits/pretty_login/login.html /script/
COPY web/local_omeroweb_edits/pretty_login/institution_banner /images/
### ###


### Section for developing with local repos ###
# git clone the desiered repo(s) in web/local_omeroweb_edits
# Uncomment the equivalent paths below (both ADD and RUN commands):
# ADD ../../omero-boost /opt/omero/web/omero-boost
### ###

# OMERO applications
RUN /opt/omero/web/venv3/bin/pip install \
        'django-cors-headers' \
        omero-figure \
        omero-iviewer \
        omero-fpbioimage \
        omero-mapr \
        omero-parade \
        omero-webtagging-autotag \
        omero-webtagging-tagsearch \
        whitenoise
        # omero-script-menu-widget==1.2.0

# Implement the script menu widget, replacing the native functionality of the script button in the header
# RUN /opt/omero/web/venv3/bin/omero-script-menu-widget-setup

# Install biomero
# RUN /opt/omero/web/venv3/bin/pip install biomero
# Install psycopg2 system prerequisites for postgres interaction
RUN yum install -y python3-devel postgresql-devel gcc
# Update PATH manually based on known locations
ENV PATH="/usr/pgsql-12/bin:/usr/pgsql-14/bin:${PATH}"

## Setup slurm-config for biomero
COPY biomeroworker/slurm-config.ini /etc/slurm-config.ini


### Install OMERO ADI library for import order creation ###
# Clone the specific branch of the repository
ADD "https://api.github.com/repos/Cellular-Imaging-Amsterdam-UMC/OMERO-Automated-Data-Import/commits?sha=mergebranch&per_page=1" /latest_commit
RUN git clone -b mergebranch https://github.com/Cellular-Imaging-Amsterdam-UMC/OMERO-Automated-Data-Import.git /auto-importer
RUN /opt/omero/web/venv3/bin/python3.9 -m pip install /auto-importer

### Comment out for development ###
# RUN /opt/omero/web/venv3/bin/pip install -e /opt/omero/web/omero-boost
### ###

# Implement the omero boost pages,
# RUN /opt/omero/web/venv3/bin/omero-boost-setup


# Set the working directory
WORKDIR /opt/omero/web/venv3/lib/python3.9/site-packages/omeroweb

# Run the script to update the login.html file from pretty_login
RUN python3.9 /script/get_images_for_login_page.py /images/ /script/login.html ./webclient/templates/webclient/login.html

# Login logos image and style page
ADD web/local_omeroweb_edits/pretty_login/login_page_images ./webclient/static/webclient/image/login_page_images/
ADD web/local_omeroweb_edits/pretty_login/ome.login.css ./webgateway/static/webgateway/css/ome.login.css

# Configuration file
ADD web/local_omeroweb_edits/01-default-webapps.omero /opt/omero/web/config

### Better Buttons ###

# # Improved top menu button clarity
ADD web/local_omeroweb_edits/script-text-play.svg ./webgateway/static/webgateway/img/script-text-play.svg

### ###

USER omero-web

