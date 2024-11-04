FROM openmicroscopy/omero-web-standalone:5.27.2

USER root

### Pretty Login ###
COPY local_omeroweb_edits/pretty_login/get_images_for_login_page.py /script/
COPY local_omeroweb_edits/pretty_login/login.html /script/
COPY local_omeroweb_edits/pretty_login/institution_banner /images/
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
        whitenoise \
        omero-script-menu-widget==1.1.2\
        omero-database-pages==0.1.1

# Implement the script menu widget, replacing the native functionality of the script button in the header
RUN /opt/omero/web/venv3/bin/omero-script-menu-widget-setup

# Implement the database pages: imports and workflows to allow browsing of database tables
RUN /opt/omero/web/venv3/bin/omero-database-pages-setup

# Set the working directory
WORKDIR /opt/omero/web/venv3/lib/python3.9/site-packages/omeroweb

# Run the script to update the login.html file from pretty_login
RUN python3.9 /script/get_images_for_login_page.py /images/ /script/login.html ./webclient/templates/webclient/login.html

# Login logos image and style page
ADD local_omeroweb_edits/pretty_login/login_page_images ./webclient/static/webclient/image/login_page_images/
ADD local_omeroweb_edits/pretty_login/ome.login.css ./webgateway/static/webgateway/css/ome.login.css

# Configuration file
ADD local_omeroweb_edits/01-default-webapps.omero /opt/omero/web/config

### Better Buttons ###

# Double-Click for better file browsing and improved groupsusersbutton
ADD local_omeroweb_edits/better_buttons/group_user_dropdown2.html ./webclient/templates/webclient/base/includes/group_user_dropdown2.html
ADD local_omeroweb_edits/better_buttons/layout.css ./webclient/static/webclient/css/layout.css

# Removing Shares tab and button in left-side menu
ADD local_omeroweb_edits/better_buttons/containers.html ./webclient/templates/webclient/data/containers.html
ADD local_omeroweb_edits/better_buttons/public.html ./webclient/templates/webclient/public/public.html

# Improved top menu button clarity
ADD local_omeroweb_edits/better_buttons/ome.header.css ./webgateway/static/webgateway/css/ome.header.css
ADD local_omeroweb_edits/script-text-play.svg ./webgateway/static/webgateway/img/script-text-play.svg

### ###

USER omero-web

