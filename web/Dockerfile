FROM openmicroscopy/omero-web-standalone:5.27.2

USER root

# Create L-Drive directory and set permissions
RUN mkdir -p /L-Drive && \
    chown omero-web:omero-web /L-Drive && \
    chmod 755 /L-Drive

# Add volume mount point for L-Drive
VOLUME ["/L-Drive"]

### Pretty Login ###
COPY local_omeroweb_edits/pretty_login/get_images_for_login_page.py /script/
COPY local_omeroweb_edits/pretty_login/login.html /script/
COPY local_omeroweb_edits/pretty_login/institution_banner /images/
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

### Comment out for development ###
# RUN /opt/omero/web/venv3/bin/pip install -e /opt/omero/web/omero-boost
### ###

# Implement the omero boost pages,
# RUN /opt/omero/web/venv3/bin/omero-boost-setup


# Set the working directory
WORKDIR /opt/omero/web/venv3/lib/python3.9/site-packages/omeroweb

# Run the script to update the login.html file
RUN python3.9 /script/get_images_for_login_page.py /images/ /script/login.html ./webclient/templates/webclient/login.html

# Login logos image and style page
ADD local_omeroweb_edits/pretty_login/login_page_images ./webclient/static/webclient/image/login_page_images/
ADD local_omeroweb_edits/pretty_login/ome.login.css ./webgateway/static/webgateway/css/ome.login.css

# Configuration file
ADD local_omeroweb_edits/01-default-webapps.omero /opt/omero/web/config

# # Improved top menu button clarity
ADD local_omeroweb_edits/script-text-play.svg ./webgateway/static/webgateway/img/script-text-play.svg


USER omero-web

