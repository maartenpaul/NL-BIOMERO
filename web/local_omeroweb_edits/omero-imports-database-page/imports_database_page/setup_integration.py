import os
import sys
from shutil import copyfile

def main():
    # Get the current Python version
    python_version = f"python{sys.version_info.major}.{sys.version_info.minor}"

    # Step 1: Add the script-menu-widget configuration to OMERO.web
    config_src = os.path.join(os.path.dirname(__file__), '03-imports_database_page.omero')
    config_dst = '/opt/omero/web/config/03-imports_database_page.omero'

    try:
        copyfile(config_src, config_dst)
        print(f"Successfully added script-menu-widget configuration: {config_src} -> {config_dst}")
    except Exception as e:
        print(f"Error adding script-menu-widget configuration: {e}")