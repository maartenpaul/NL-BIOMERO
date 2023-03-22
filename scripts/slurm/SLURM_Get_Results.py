#!/opt/omero/server/cellposeenv/bin/python
# -*- coding: utf-8 -*-
#
# Original work Copyright (C) 2014 University of Dundee
#                                   & Open Microscopy Environment.
#                    All Rights Reserved.
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt
#
# Example OMERO.script using Cellpose segmentation
# from a cellpose python environment

import shutil
import subprocess
import omero
import omero.gateway
from omero import scripts
import omero.util.script_utils as script_utils
from omero.constants.namespaces import NSCREATED
from omero.gateway import BlitzGateway
from omero.rtypes import rstring, rlong, robject, unwrap, rint
from cellpose import models, io
import os
import numpy as np
from pathlib import Path
from typing import Union, List
import itertools
import re
import zipfile
import glob

SLURM_HOME = "/home/sandbox/ttluik"
IMAGE_PATH = f"{SLURM_HOME}/my-scratch/singularity_images/workflows/cellpose"
BASE_DATA_PATH = f"{SLURM_HOME}/my-scratch/data"
_CHANNEL_VALUES = [rint(0), rint(1), rint(2), rint(3)]
_DEFAULT_CHANNEL_CYTOPLASM = 0
_DEFAULT_CHANNEL_NUCLEUS = 0
_DEFAULT_DATA_TYPE = "Image"
_DEFAULT_MODEL = "nuclei"
_MODELS_VALUES = [rstring(_DEFAULT_MODEL)]
_PARAM_CHANNEL_CYTOPLASM = "Channel_(cytoplasm)"
_PARAM_CHANNEL_NUCLEUS = "Channel_(nucleus)"
_PARAM_DATA_TYPE = "Data_Type"
_PARAM_IDS = "IDs"
_PARAM_MODEL = "Model"
_QUEUE_COMMAND = "squeue --nohead --format %F -u ttluik"
_ACCT_COMMAND = "sacct --starttime 2023-01-01 -o JobId -n -X"
SLURM_JOB_ID = "SLURM Job Id"
SLURM_JOB_ID_OLD = "SLURM Job Id (old)"
RUN_ON_GPU_NS = "GPU"
SSH_KEY = '~/.ssh/id_rsa'
SLURM_REMOTE = 'luna.amc.nl'
SLURM_USER = 'ttluik'
SSH_HOSTS = '~/.ssh/known_hosts'
RUNNING_JOB = "Running Job"
COMPLETED_JOB = "Completed Job"
_DATA_CMD = f"ls -h {BASE_DATA_PATH} | grep -oP '.+(?=.zip)'"
LOGFILE_PATH_PATTERN_GROUP = "DATA_PATH"
LOGFILE_PATH_PATTERN = f"Running CellPose w/ (?P<IMAGE_PATH>.+) \| (?P<IMAGE_VERSION>.+) \| (?P<{LOGFILE_PATH_PATTERN_GROUP}>.+) \|.*"


# TODO use Fabric library?
class SshClient():
    """ Perform commands and copy files on ssh using subprocess 
        and native ssh client (OpenSSH).
        Based on https://gist.github.com/TorecLuik/aae824e081895707f0a82585d273164f
    """

    def __init__(self,
                 user: str,
                 remote: str,
                 key_path: Union[str, Path],
                 known_hosts: str = "/dev/null") -> None:
        """

        Args:
            user (str): username for the remote
            remote (str): remote host IP/DNS
            key_path (str or pathlib.Path): path to .pem file
            known_hosts (str, optional): path to known_hosts file
        """
        self.user = user
        self.remote = remote
        self.key_path = str(key_path)
        self.known_hosts = known_hosts

    def cmd(self,
            cmds: List[str],
            check=True,
            strict_host_key_checking=True,
            **run_kwargs) -> subprocess.CompletedProcess:
        """runs commands consecutively, ensuring success of each
            after calling the next command.

        Args:
            cmds (list[str]): list of commands to run.
            strict_host_key_checking (bool, optional): Defaults to True.
        """

        # strict_host_key_checking = 'yes' if strict_host_key_checking else 'no'
        strict_host_key_checking = 'no'
        cmd = ' && '.join(cmds)
        print(f"CMD: {cmd} || extra args: {run_kwargs}")
        return subprocess.run(
            [
                'ssh',
                '-i', self.key_path,
                '-o', f'StrictHostKeyChecking={strict_host_key_checking}',
                '-o', f'UserKnownHostsFile={self.known_hosts}',
                # '-o', 'LogLevel=DEBUG',
                f'{self.user}@{self.remote}',
                cmd
            ],
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **run_kwargs
        )

    def scp(self,
            sources: List[Union[str, bytes, os.PathLike]],
            destination: Union[str, bytes, os.PathLike],
            check=True,
            strict_host_key_checking=False,
            recursive=False,
            **run_kwargs) -> subprocess.CompletedProcess:
        """Copies `srouce` file to remote `destination` using the 
            native `scp` command.

        Args:
            source (Union[str, bytes, os.PathLike]): List of source files path.
            destination (Union[str, bytes, os.PathLike]): Destination path on remote.
        """

        strict_host_key_checking = 'yes' if strict_host_key_checking else 'no'

        return subprocess.run(
            list(filter(bool, [
                'scp',
                '-i', self.key_path,
                '-o', f'StrictHostKeyChecking={strict_host_key_checking}',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'LogLevel=ERROR',
                '-r' if recursive else '',
                *map(str, sources),
                # sources,
                f'{self.user}@{self.remote}:{str(destination)}',
            ])),
            check=check,
            **run_kwargs
        )

    def scpull(self,
               destination: Union[str, bytes, os.PathLike],
               source: Union[str, bytes, os.PathLike],
               check=True,
               strict_host_key_checking=False,
               recursive=False,
               **run_kwargs) -> subprocess.CompletedProcess:
        """Copies remote `destination` file to local `source` using the 
            native `scp` command.

            Inverse of scp command.

        Args:
            source (Union[str, bytes, os.PathLike]): List of source files path.
            destination (Union[str, bytes, os.PathLike]): Destination path on remote.
        """

        strict_host_key_checking = 'yes' if strict_host_key_checking else 'no'

        return subprocess.run(
            list(filter(bool, [
                'scp',
                '-i', self.key_path,
                '-o', f'StrictHostKeyChecking={strict_host_key_checking}',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'LogLevel=ERROR',
                '-r' if recursive else '',
                # *map(str, sources),
                f'{self.user}@{self.remote}:{str(destination)}',
                str(source),
            ])),
            check=check,
            **run_kwargs
        )

    def validate(self):
        return self.cmd([f'echo " "'], check=False).returncode == 0

    def ssh_connect_cmd(self) -> str:
        return f'ssh -i {self.key_path} {self.user}@{self.remote}'


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
                      file_ann.getId(), ",", file_ann.getFile().getName(), "Size:",
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


def call_slurm(slurmClient, cmdlist):
    """Easier function to provide list of commandline orders to SLURM server.

    Args:
        slurmClient (SshClient): SLURM SshClient
        cmdlist (List): List of commands to execute on SLURM

    Returns:
        String: Message describing results
    """
    print_result = []
    try:
        # run a list of commands
        results = slurmClient.cmd(
            cmdlist,
            check=True,
            strict_host_key_checking=False)
        print(f"Ran slurm {results.__dict__}")
    except subprocess.CalledProcessError as e:
        results = f"Error {e.__dict__}"
        print(results)
    finally:
        try:
            print_result.append(f"{results.stdout.decode('utf-8')}")
        except Exception:
            print_result.append(f"{results.stderr.decode('utf-8')}")
    return print_result


def getOldJobs(slurmClient):
    """Get list of finished jobs from SLURM.

    Args:
        slurmClient (SshClient): SLURM SshClient

    Returns:
        List: List of Job Ids
    """
    if slurmClient.validate():
        cmdlist = [_ACCT_COMMAND]
        slurm_response = call_slurm(slurmClient, cmdlist)
        responselist = slurm_response[0].strip().split('\n')
        responselist.reverse()  # newest on top
        return responselist
    else:
        return ["Error connecting to SLURM"]


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
                     for d in conn.getObjects('Project')]
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
        mimetype = "application/zip"
        namespace = NSCREATED + "/SLURM/SLURM_GET_RESULTS"
        description = f"Results from SLURM job {slurm_job_id}"
        zip_annotation = conn.createFileAnnfromLocalFile(
            f"{folder}.zip", mimetype=mimetype,
            ns=namespace, desc=description)
        for project in projects:
            project.linkAnnotation(zip_annotation)  # link it to project.
        print(f"Uploaded {folder}.zip and attached to {projects}")
        client.setOutput("File_Annotation", robject(zip_annotation._obj))
    except Exception as e:
        message += f" Uploading zip failed: {e}"


def copy_zip_locally(slurmClient, message, local_tmp_storage, filename):
    """ Copy zip from SLURM to local server

    Args:
        slurmClient (SshClient): SLURM SshClient
        message (String): Script output
        local_tmp_storage (String): Path to store zip
        filename (String): Zip filename on SLURM
    """    
    try:
        # scp
        results = slurmClient.scpull(
            destination=f"{SLURM_HOME}/{filename}.zip",
            source=local_tmp_storage,
            check=True,
            strict_host_key_checking=False)
        print(f"Ran slurm {results.__dict__}")
    except Exception as e:
        message += f" SCP output zip failed: {e}"


def zip_data_on_slurm_server(slurmClient, message, cmdlist, data_location, filename):
    """Zip the output folder of a job on SLURM

    Args:
        slurmClient (SshClient): SLURM SshClient
        message (String): Script output
        cmdlist (List): List of other commands you want to run first
        data_location (String): Folder on SLURM with the "data/out" subfolder
        filename (String): Name to give to the zipfile
    """    
    try:
        # zip
        zip_cmd = f"7z a -y {filename} -tzip {data_location}/data/out"
        cmdlist.append(zip_cmd)
        print_job = call_slurm(slurmClient, cmdlist)
        print(print_job[0])
        message += f"\n{print_job[0]}"
    except Exception as e:
        message += f" Zipping output data failed: {e}"


def extract_data_location_from_log(export_file):
    """Read SLURM job logfile to find location of the data

    Args:
        export_file (String): Path to the logfile

    Returns:
        String: Data location according to the log
    """
    with open(export_file, 'r', encoding='utf-8') as log:
        data_location = None
        for line in log:
            print(line)
            match = re.match(pattern=LOGFILE_PATH_PATTERN, string=line)
            if match:
                data_location = match.group(LOGFILE_PATH_PATTERN_GROUP)
                break
    return data_location


def get_logfile_from_slurm(slurmClient, slurm_job_id):
    """Copy the logfile of given SLURM job to local server

    Args:
        slurmClient (SshClient): SLURM SshClient
        slurm_job_id (String): ID of the SLURM job

    Returns:
        _type_: _description_
    """
    local_tmp_storage = "/tmp/"
    logfile = f"cellpose-{slurm_job_id}.log"
    results = slurmClient.scpull(
        destination=f"{SLURM_HOME}/{logfile}",
        source=local_tmp_storage,
        check=True,
        strict_host_key_checking=False)
    print(f"Ran slurm {results.__dict__}")

    export_file = local_tmp_storage+logfile
    return local_tmp_storage, export_file


def check_slurm_job_state(slurmClient, client, message, slurm_job_id):
    """Check status for given SLURM job

    Args:
        slurmClient (SshClient): SLURM SshClient
        client (_type_): OMERO client
        message (String): Script output
        slurm_job_id (String): SLURM job id
    """
    if unwrap(client.getInput(COMPLETED_JOB)):
        try:
            cmdlist = []
            cmdlist.append(f"sacct -n -o JobId,State,End -X -j {slurm_job_id}")
            print_job = call_slurm(slurmClient, cmdlist)
            print(print_job[0])
            message += f"\n{print_job[0]}"
        except Exception as e:
            message += f" Show job failed: {e}"


def runScript():
    """
    The main entry point of the script
    """

    slurmClient = SshClient(user=SLURM_USER,
                            remote=SLURM_REMOTE,
                            key_path=SSH_KEY,
                            known_hosts=SSH_HOSTS)

    _oldjobs = getOldJobs(slurmClient)
    _projects = getUserProjects()

    client = scripts.client(
        'Slurm Get Results',
        '''Retrieve the results from your SLURM job.
        
        Attach files to provided project/dataset.
        ''',
        scripts.Bool(COMPLETED_JOB, optional=False, grouping="01",
                     default=True),
        scripts.String(SLURM_JOB_ID, optional=False, grouping="01.1",
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
        slurm_job_id = unwrap(client.getInput(SLURM_JOB_ID)).strip()

        # Ask job State
        check_slurm_job_state(slurmClient, client, message, slurm_job_id)

        # unwrap project id
        project_ids = unwrap(client.getInput("Project"))
        print(project_ids)
        projects = [conn.getObject("Project", p.split(":")[0])
                    for p in project_ids]

        # Job log
        if unwrap(client.getInput(COMPLETED_JOB)):
            try:
                cmdlist = []

                # Copy file to server
                local_tmp_storage, export_file = get_logfile_from_slurm(
                    slurmClient, slurm_job_id)

                # Read file for data location
                data_location = extract_data_location_from_log(export_file)

                # zip and scp data location
                if data_location:
                    filename = f"{slurm_job_id}_out"
                    cmdlist = []
                    zip_data_on_slurm_server(
                        slurmClient, message, cmdlist, data_location, filename)

                    copy_zip_locally(slurmClient, message,
                                     local_tmp_storage, filename)

                    folder = f"{local_tmp_storage}/{filename}"

                    upload_zip_to_omero(
                        client, conn, message, slurm_job_id, projects, folder)

                    unzip_zip_locally(message, folder)

                    upload_contents_to_omero(client, conn, message, folder)

                    cleanup_tmp_files_locally(message, folder)

            except Exception as e:
                message += f" Retrieving results failed: {e}\n"

        client.setOutput("Message", rstring(str(message)))

    finally:
        client.closeSession()


if __name__ == '__main__':
    runScript()
