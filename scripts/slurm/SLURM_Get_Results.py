#!/opt/omero/server/cellposeenv/bin/python
# -*- coding: utf-8 -*-
#
# Original work Copyright (C) 2014 University of Dundee
#                                   & Open Microscopy Environment.
#                    All Rights Reserved.
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt
#
# Example OMERO.script to get results from a Slurm job.

import shutil
import omero
import omero.gateway
from omero import scripts
from omero.constants.namespaces import NSCREATED
from omero.gateway import BlitzGateway
from omero.rtypes import rstring, robject, unwrap
import os
import re
import zipfile
import glob
from omero_slurm_client import SlurmClient
import logging

logger = logging.getLogger(__name__)

_SLURM_JOB_ID = "SLURM Job Id"
_COMPLETED_JOB = "Completed Job"
_LOGFILE_PATH_PATTERN_GROUP = "DATA_PATH"
_LOGFILE_PATH_PATTERN = "Running [\w-]+? Job w\/ .+? \| .+? \| (?P<DATA_PATH>.+?) \|.*"


def load_image(conn, image_id):
    """Load the Image object.

    Args:
        conn (_type_): Open OMERO connection
        image_id (String): ID of the image

    Returns:
        _type_: OMERO Image object
    """
    return conn.getObject('Image', image_id)


def getOriginalFilename(name):
    """Attempt to retrieve original filename.

    Assuming /../../Cells Apoptotic.png_merged_z01_t01.tiff,
    we want 'Cells Apoptotic.png' to be returned.

    Args:
        name (String): name of processed file
    """
    match = re.match(pattern=".+\/(.+\.[A-Za-z]+).+\.tiff", string=name)
    if match:
        name = match.group(1)

    return name


def saveCPImagesToOmero(conn, folder, client):
    """Save image from a (unzipped) folder to OMERO as attachments

    Args:
        conn (_type_): Connection to OMERO
        folder (String): Unzipped folder
        client : OMERO client to attach output

    Returns:
        String: Message to add to script output
    """
    all_files = glob.iglob(folder+'**/**', recursive=True)
    files = [f for f in all_files if os.path.isfile(f)
             and f.endswith('.tiff')]
    # more_files = [f for f in os.listdir(f"{folder}/out") if os.path.isfile(f)
    #               and f.endswith('.tiff')]  # out folder
    # files += more_files
    print(f"Found the following files in {folder}: {all_files} && {files}")
    namespace = NSCREATED + "/SLURM/SLURM_GET_RESULTS"
    msg = ""
    for name in files:
        print(name)
        og_name = getOriginalFilename(name)
        print(og_name)
        images = conn.getObjects("Image", attributes={
                                 "name": f"{og_name}"})  # Can we get in 1 go?
        print(images)

        if images:
            try:
                # attach the masked image to the original image
                file_ann = conn.createFileAnnfromLocalFile(
                    name, mimetype="image/tiff",
                    ns=namespace, desc=f"Result from analysis {folder}")
                print(f"Attaching {name} to image {og_name}")
                # image = load_image(conn, image_id)
                for image in images:
                    image.linkAnnotation(file_ann)

                print("Attaching FileAnnotation to Image: ", "File ID:",
                      file_ann.getId(), ",",
                      file_ann.getFile().getName(), "Size:",
                      file_ann.getFile().getSize())

                os.remove(name)
                client.setOutput("File_Annotation", robject(file_ann._obj))
            except Exception as e:
                msg = f"Issue attaching file {name} to OMERO {og_name}: {e}"
                print(msg)
        else:
            msg = f"No images ({og_name}) found to attach {name} to: {images}"
            print(msg)

    message = f"Tried attaching {files} to OMERO original images. \n{msg}"

    return message


def getUserProjects():
    """ Get (OMERO) Projects that user has access to.

    Returns:
        List: List of project ids and names
    """
    try:
        client = omero.client()
        client.createSession()
        conn = omero.gateway.BlitzGateway(client_obj=client)
        conn.SERVICE_OPTS.setOmeroGroup(-1)
        objparams = [rstring('%d: %s' % (d.id, d.getName()))
                     for d in conn.getObjects('Project')
                     if type(d) == omero.gateway.ProjectWrapper]
        #  if type(d) == omero.model.ProjectI
        if not objparams:
            objparams = [rstring('<No objects found>')]
        return objparams
    except Exception as e:
        return ['Exception: %s' % e]
    finally:
        client.closeSession()


def cleanup_tmp_files_locally(message, folder):
    """ Cleanup zip and unzipped files/folders

    Args:
        message (String): Script output
        folder (String): Path of folder/zip to remove
    """
    try:
        # Cleanup
        os.remove(f"{folder}.zip")
        shutil.rmtree(folder)
    except Exception as e:
        message += f" Failed to cleanup tmp files: {e}"

    return message


def upload_contents_to_omero(client, conn, message, folder):
    """Upload contents of folder to OMERO

    Args:
        client (_type_): OMERO client
        conn (_type_): Open connection to OMERO
        message (String): Script output
        folder (String): Path to folder with content
    """
    try:
        # upload and link individual images
        msg = saveCPImagesToOmero(conn=conn, folder=folder, client=client)
        message += msg
    except Exception as e:
        message += f" Failed to upload images to OMERO: {e}"

    return message


def unzip_zip_locally(message, folder):
    """ Unzip a zipfile

    Args:
        message (String): Script output
        folder (String): zipfile name/path (w/out zip ext)
    """
    try:
        # unzip locally
        with zipfile.ZipFile(f"{folder}.zip", "r") as zip:
            zip.extractall(folder)
        print(f"Unzipped {folder} on the server")
    except Exception as e:
        message += f" Unzip failed: {e}"

    return message


def upload_zip_to_omero(client, conn, message, slurm_job_id, projects, folder):
    """ Upload a zip to omero (without unpacking)

    Args:
        client (_type_): OMERO client
        conn (_type_): Open connection to OMERO
        message (String): Script output
        slurm_job_id (String): ID of the SLURM job the zip came from
        projects (List): OMERO projects to attach zip to
        folder (String): path to / name of zip (w/o zip extension)
    """
    try:
        # upload zip and link to project(s)
        print(f"Uploading {folder}.zip and attaching to {projects}")
        mimetype = "application/zip"
        namespace = NSCREATED + "/SLURM/SLURM_GET_RESULTS"
        description = f"Results from SLURM job {slurm_job_id}"
        zip_annotation = conn.createFileAnnfromLocalFile(
            f"{folder}.zip", mimetype=mimetype,
            ns=namespace, desc=description)

        client.setOutput("File_Annotation", robject(zip_annotation._obj))

        for project in projects:
            project.linkAnnotation(zip_annotation)  # link it to project.
        message += f"Attached zip to {projects}"
    except Exception as e:
        message += f" Uploading zip failed: {e}"
        print(message)

    return message


def extract_data_location_from_log(export_file):
    """Read SLURM job logfile to find location of the data

    Args:
        export_file (String): Path to the logfile

    Returns:
        String: Data location according to the log
    """
    # TODO move to SlurmClient? makes more sense to read this remotely? Can we?
    with open(export_file, 'r', encoding='utf-8') as log:
        data_location = None
        for line in log:
            try:
                print(f"logline: {line}")
            except UnicodeEncodeError as e:
                logger.error(f"Unicode error: {e}")
                line = line.encode(
                    'ascii', 'ignore').decode('ascii')
                print(f"logline: {line}")
            match = re.match(pattern=_LOGFILE_PATH_PATTERN, string=line)
            if match:
                data_location = match.group(_LOGFILE_PATH_PATTERN_GROUP)
                break
    return data_location


def runScript():
    """
    The main entry point of the script
    """

    with SlurmClient.from_config() as slurmClient:

        _oldjobs = slurmClient.list_completed_jobs()
        _projects = getUserProjects()

        client = scripts.client(
            'Slurm Get Results',
            '''Retrieve the results from your completed SLURM job.

            Attach files to provided project.
            ''',
            scripts.Bool(_COMPLETED_JOB, optional=False, grouping="01",
                         default=True),
            scripts.String(_SLURM_JOB_ID, optional=False, grouping="01.1",
                           values=_oldjobs),
            scripts.List("Project", optional=False, grouping="02.5",
                         description="Project to attach workflow results to",
                         values=_projects),
            namespaces=[omero.constants.namespaces.NSDYNAMIC],
        )

        try:
            scriptParams = client.getInputs(unwrap=True)
            conn = BlitzGateway(client_obj=client)

            message = ""
            print(f"Request: {scriptParams}\n")

            # Job id
            slurm_job_id = unwrap(client.getInput(_SLURM_JOB_ID)).strip()

            # Ask job State
            if unwrap(client.getInput(_COMPLETED_JOB)):
                _, result = slurmClient.check_job_status([slurm_job_id])
                print(result.stdout)
                message += f"\n{result.stdout}"

            # Pull project from Omero
            project_ids = unwrap(client.getInput("Project"))
            print(project_ids)
            projects = [conn.getObject("Project", p.split(":")[0])
                        for p in project_ids]

            # Job log
            if unwrap(client.getInput(_COMPLETED_JOB)):
                # Copy file to server
                tup = slurmClient.get_logfile_from_slurm(
                    slurm_job_id)
                (local_tmp_storage, export_file, get_result) = tup
                message += "\nSuccesfully copied logfile."
                print(message)
                print(get_result.__dict__)

                # Read file for data location
                data_location = slurmClient.extract_data_location_from_log(
                    slurm_job_id)
                print(f"Extracted {data_location}")

                # zip and scp data location
                if data_location:
                    filename = f"{slurm_job_id}_out"

                    zip_result = slurmClient.zip_data_on_slurm_server(
                        data_location, filename)
                    if not zip_result.ok:
                        message += "\nFailed to zip data on Slurm."
                        print(message, zip_result.stderr)
                    else:
                        message += "\nSuccesfully zipped data on Slurm."
                        print(message, zip_result.stdout)

                        copy_result = slurmClient.copy_zip_locally(
                            local_tmp_storage, filename)

                        message += "\nSuccesfully copied zip."
                        print(message, copy_result)

                        folder = f"{local_tmp_storage}/{filename}"

                        message = upload_zip_to_omero(
                            client, conn, message,
                            slurm_job_id, projects, folder)

                        message = unzip_zip_locally(message, folder)

                        message = upload_contents_to_omero(
                            client, conn, message, folder)

                        message = cleanup_tmp_files_locally(
                            message, folder)

                        clean_result = slurmClient.cleanup_tmp_files(
                            slurm_job_id,
                            filename,
                            data_location)
                        message += "\nSuccesfully cleaned up tmp files"
                        print(message, clean_result)

            client.setOutput("Message", rstring(str(message)))

        finally:
            client.closeSession()


if __name__ == '__main__':
    runScript()
