import os
from shutil import copyfile


def main():
    # Step 1: Add the imports-database-page configuration to OMERO.web
    config_src = os.path.join(
        os.path.dirname(__file__), '03-imports_database_page.omero'
    )
    config_dst = '/opt/omero/web/config/03-imports_database_page.omero'

    try:
        copyfile(config_src, config_dst)
        print(
            f"Successfully added imports-database-page configuration: "
            f"{config_src} -> {config_dst}"
        )
    except Exception as e:
        print(f"Error adding imports-database-page configuration: {e}")
