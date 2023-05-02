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
# SlurmClient dependencies
from typing import Dict, List, Optional, Tuple
from fabric import Connection, Result
from fabric.transfer import Result as TransferResult
from paramiko import SSHException
import configparser

_SLURM_JOB_ID = "SLURM Job Id"
_COMPLETED_JOB = "Completed Job"
_LOGFILE_PATH_PATTERN_GROUP = "DATA_PATH"
_LOGFILE_PATH_PATTERN = f"Running \w+ w/ (?P<IMAGE_PATH>.+) \| (?P<IMAGE_VERSION>.+) \| (?P<{_LOGFILE_PATH_PATTERN_GROUP}>.+) \|.*"


class SlurmClient(Connection):
    """A client for connecting to and interacting with a Slurm cluster over SSH.

    This class extends the Fabric Connection class, adding methods and attributes specific to working with Slurm.

    SlurmClient accepts the same arguments as Connection. So below only mentions the added ones:

    Attributes:
        slurm_data_path (str): The path to the directory containing the data files for Slurm jobs.
        slurm_images_path (str): The path to the directory containing the Singularity images for Slurm jobs.
        slurm_model_paths (dict): A dictionary containing the paths to the Singularity images for specific Slurm job models.
        slurm_script_path (str): The path to the directory containing the Slurm job submission scripts. This is expected to be a Git repository.

    Example:
        # Create a SlurmClient object as contextmanager

        with SlurmClient.from_config() as client:

            # Run a command on the remote host

            result = client.run('sbatch myjob.sh')

            # Check whether the command succeeded

            if result.ok:
                print('Job submitted successfully!')

            # Print the output of the command

            print(result.stdout)

    """
    _DEFAULT_CONFIG_PATH_1 = "/etc/slurm-config.ini"
    _DEFAULT_CONFIG_PATH_2 = "~/slurm-config.ini"
    _DEFAULT_HOST = "slurm"
    _DEFAULT_INLINE_SSH_ENV = True
    _DEFAULT_SLURM_DATA_PATH = "my-scratch/data"
    _DEFAULT_SLURM_IMAGES_PATH = "my-scratch/singularity_images/workflows"
    _DEFAULT_SLURM_GIT_SCRIPT_PATH = "slurm-scripts"
    _OUT_SEP = "--split--"
    _VERSION_CMD = "ls -h {slurm_images_path}/{image_path} | grep -oP '(?<=-)v.+(?=.simg)'"
    _DATA_CMD = "ls -h {slurm_data_path} | grep -oP '.+(?=.zip)'"
    _ACCT_CMD = "sacct --starttime {start_time} -o JobId -n -X"
    _ZIP_CMD = "7z a -y {filename} -tzip {data_location}/data/out"
    # TODO move all commands to a similar format. 
    # Then maybe allow overwrite from slurm-config.ini
    _LOGFILE = "omero-{slurm_job_id}.log"

    def __init__(self,
                 host=_DEFAULT_HOST,
                 user=None,
                 port=None,
                 config=None,
                 gateway=None,
                 forward_agent=None,
                 connect_timeout=None,
                 connect_kwargs=None,
                 inline_ssh_env=_DEFAULT_INLINE_SSH_ENV,
                 slurm_data_path: str = _DEFAULT_SLURM_DATA_PATH,
                 slurm_images_path: str = _DEFAULT_SLURM_IMAGES_PATH,
                 slurm_model_paths: dict = None,
                 slurm_script_path: str = _DEFAULT_SLURM_GIT_SCRIPT_PATH
                 ):
        super(SlurmClient, self).__init__(host,
                                          user,
                                          port,
                                          config,
                                          gateway,
                                          forward_agent,
                                          connect_timeout,
                                          connect_kwargs,
                                          inline_ssh_env)
        self.slurm_data_path = slurm_data_path
        self.slurm_images_path = slurm_images_path
        self.slurm_model_paths = slurm_model_paths
        self.slurm_script_path = slurm_script_path
        # TODO: setup the script path by downloading from GIT? setup all the directories?

    @classmethod
    def from_config(cls, configfile: str = '') -> 'SlurmClient':
        """Creates a new SlurmClient object using the parameters read from a configuration file (.ini).

        Defaults paths to look for config files are:
            - /etc/slurm-config.ini
            - ~/slurm-config.ini

        Note that this is only for the SLURM specific values that we added.
        Most configuration values are set via configuration mechanisms from Fabric library,
        like SSH settings being loaded from SSH config, /etc/fabric.yml or environment variables.
        See Fabric's documentation for more info on configuration if needed.

        Args:
            configfile (str): The path to your configuration file. Optional.

        Returns:
            SlurmClient: A new SlurmClient object.
        """
        # Load the configuration file
        configs = configparser.ConfigParser(allow_no_value=True)
        # Loads from default locations and given location, missing files are ok
        configs.read([cls._DEFAULT_CONFIG_PATH_1,
                     cls._DEFAULT_CONFIG_PATH_2, configfile])
        # Read the required parameters from the configuration file, fallback to defaults
        host = configs.get("SSH", "host", fallback=cls._DEFAULT_HOST)
        inline_ssh_env = configs.getboolean(
            "SSH", "inline_ssh_env", fallback=cls._DEFAULT_INLINE_SSH_ENV)
        slurm_data_path = configs.get(
            "SLURM", "slurm_data_path", fallback=cls._DEFAULT_SLURM_DATA_PATH)
        slurm_images_path = configs.get(
            "SLURM", "slurm_images_path", fallback=cls._DEFAULT_SLURM_IMAGES_PATH)
        slurm_model_paths = dict(configs.items("MODELS"))
        slurm_script_path = configs.get(
            "SLURM", "slurm_script_path", fallback=cls._DEFAULT_SLURM_GIT_SCRIPT_PATH)
        # Create the SlurmClient object with the parameters read from the config file
        return cls(host=host,
                   inline_ssh_env=inline_ssh_env,
                   slurm_data_path=slurm_data_path,
                   slurm_images_path=slurm_images_path,
                   slurm_model_paths=slurm_model_paths,
                   slurm_script_path=slurm_script_path)

    def validate(self):
        """Validate the connection to the Slurm cluster by running a simple command.

        Returns:
            bool: True if the command is executed successfully, False otherwise.
        """
        return self.run('echo " "').ok

    def run_commands(self, cmdlist: List[str], env: Optional[Dict[str, str]] = None, sep: str = ' && ') -> Result:
        """
        Runs a list of shell commands consecutively, ensuring success of each before calling the next.

        The environment variables can be set using the `env` argument. These commands retain the same session (environment variables
        etc.), unlike running them separately.

        Args:
            cmdlist (List[str]): A list of shell commands to run on SLURM.
            env (Optional[Dict[str, str]]): A dictionary of environment variables to be set for the commands (default: None).
            sep (str): The separator used to concatenate the commands (default: ' && ').

        Returns:
            Result: The result of the last command in the list.
        """
        if env is None:
            env = {}
        cmd = sep.join(cmdlist)
        print(f"Running commands, with env {env} and sep {sep}: {cmd}")
        return self.run(cmd, env=env)

    def run_commands_split_out(self, cmdlist: List[str], env: Optional[Dict[str, str]] = None) -> List[str]:
        """Runs a list of shell commands consecutively and splits the output of each command.

        Each command in the list is executed with a separator in between that is unique and can be used to split
        the output of each command later. The separator used is specified by the `_OUT_SEP` attribute of the
        SlurmClient instance.

        Args:
            cmdlist (List[str]): A list of shell commands to run.
            env (Optional[Dict[str, str]]): A dictionary of environment variables to set when running the commands.

        Returns:
            List[str]: A list of strings, where each string corresponds to the output of a single command
                    in `cmdlist` split by the separator `_OUT_SEP`.
        Raises:
            SSHException: If any of the commands fail to execute successfully.
        """
        result = self.run_commands(cmdlist=cmdlist,
                                   env=env,
                                   sep=f" && echo {self._OUT_SEP} && ")
        if result.ok:
            response = result.stdout
            split_responses = response.split(self._OUT_SEP)
            return split_responses
        else:
            error = f"Result is not ok: {result}"
            print(error)
            raise SSHException(error)

    def list_old_jobs(self, env: Optional[Dict[str, str]] = None) -> List[str]:
        """Get list of finished jobs from SLURM.

        Args:
            env (Optional[Dict[str, str]]): Optional environment variables to set when running the command.
                Defaults to None.

        Returns:
            List: List of Job Ids
        """

        cmd = self.get_old_job_command()
        print("Retrieving list of finished jobs from Slurm")
        result = self.run_commands([cmd], env=env)
        job_list = result.stdout.strip().split('\n')
        job_list.reverse()
        return job_list

    def get_old_job_command(self, start_time: str = "2023-01-01") -> str:
        """Return the Slurm command to retrieve information about old jobs.

        The command will be formatted with the specified start time, which is
        expected to be in the ISO format "YYYY-MM-DD".
        The command will use the "sacct" tool to query the
        Slurm accounting database for jobs that started on or after the
        specified start time, and will output only the job IDs (-o JobId)
        without header or trailer lines (-n -X).

        Args:
            start_time (str): The start time from which to retrieve job information.
                Defaults to "2023-01-01".

        Returns:
            str: A string representing the Slurm command to retrieve information
                about old jobs.
        """
        return self._ACCT_CMD.format(start_time=start_time)

    def transfer_data(self, local_path: str) -> Result:
        """Transfers a file or directory from the local machine to the remote Slurm cluster.

        Args:
            local_path (str): The local path to the file or directory to transfer.

        Returns:
            Result: The result of the file transfer operation.
        """
        print(
            f"Transfering file {local_path} to {self.slurm_data_path}")
        return self.put(local=local_path, remote=self.slurm_data_path)

    def unpack_data(self, zipfile: str, env: Optional[Dict[str, str]] = None) -> Result:
        """Unpacks a zipped file on the remote Slurm cluster.

        Args:
            zipfile (str): The name of the zipped file to be unpacked.
            env (Optional[Dict[str, str]]): Optional environment variables to set when running the command.
                Defaults to None.

        Returns:
            Result: The result of the command.

        """
        cmd = self.get_unzip_command(zipfile)
        print(f"Unpacking {zipfile} on Slurm")
        return self.run_commands([cmd], env=env)

    def update_slurm_scripts(self, env: Optional[Dict[str, str]] = None) -> Result:
        """Updates the local copy of the Slurm job submission scripts.

        This function pulls the latest version of the scripts from the Git repository,
        and copies them to the slurm_script_path directory.

        Args:
            env (Optional[Dict[str, str]]): Optional environment variables to set when running the command.
                Defaults to None.

        Returns:
            Result: The result of the command.
        """
        cmd = self.get_update_slurm_scripts_command()
        print("Updating Slurm job scripts on Slurm")
        return self.run_commands([cmd], env=env)

    def run_cellpose(self, cellpose_version, input_data, cp_model, nuc_channel, prob_threshold, cell_diameter, email, time) -> Result:
        """
        Runs CellPose on Slurm on the specified input data using the given parameters.

        Args:
            cellpose_version (str): The version of CellPose to use.
            input_data (str): The name of the input data folder containing the input image files.
            cp_model (str): The name of the CellPose model to use for segmentation.
            nuc_channel (int): The index of the nuclear channel in the image data.
            prob_threshold (float): The threshold probability value for object segmentation.
            cell_diameter (int): The approximate diameter of the cells in pixels.
            email (str): The email address to use for Slurm job notifications.
            time (str): The time limit for the Slurm job in the format HH:MM:SS.

        Returns:
            Result: An object containing the output from starting the CellPose job.

        """
        sbatch_cmd, sbatch_env = self.get_cellpose_command(
            cellpose_version, input_data, cp_model, nuc_channel, prob_threshold, cell_diameter, email, time)
        print("Running CellPose job on Slurm")
        return self.run_commands([sbatch_cmd], sbatch_env)

    def get_update_slurm_scripts_command(self) -> str:
        """Generates the command to update the Git repository containing the Slurm scripts, if necessary.

        Returns:
            str: A string containing the Git command to update the Slurm scripts.
        """
        update_cmd = f"git -C {self.slurm_script_path} pull"
        return update_cmd

    def check_job_status(self, slurm_job_id: str, env: Optional[Dict[str, str]] = None) -> Result:
        """
        Checks the status of a Slurm job with the given job ID.

        Args:
            slurm_job_id (str): The job ID of the Slurm job to check.
            env (Optional[Dict[str, str]]): A dictionary of environment variables to set before executing the command. Defaults to None.

        Returns:
            Result: The result of the command execution.
        """
        cmd = self.get_job_status_command(slurm_job_id)
        print(f"Getting status of {slurm_job_id} on Slurm")
        return self.run_commands([cmd], env=env)

    def get_job_status_command(self, slurm_job_id: str) -> str:
        """
        Returns the Slurm command to get the status of a job with the given job ID.

        Args:
            slurm_job_id (str): The job ID of the job to check.

        Returns:
            str: The Slurm command to get the status of the job.
        """

        return f"sacct -n -o JobId,State,End -X -j {slurm_job_id}"

    def get_cellpose_command(self, image_version, input_data, cp_model, nuc_channel, prob_threshold, cell_diameter, email=None, time=None, model="cellpose", job_script="cellpose.sh") -> Tuple[str, dict]:
        """
        Returns the command and environment dictionary to run a CellPose job on the Slurm workload manager.

        Args:
            image_version (str): The version of the Singularity image to use.
            input_data (str): The name of the input data folder on the shared file system.
            cp_model (str): The name of the CellPose model to use.
            nuc_channel (int): The index of the nuclear channel.
            prob_threshold (float): The probability threshold for nuclei detection.
            cell_diameter (float): The expected cell diameter in pixels.
            email (Optional[str]): The email address to send notifications to (default is None).
            time (Optional[str]): The maximum time for the job to run (default is None).
            model (str): The name of the folder of the Docker image to use (default is "cellpose").
            job_script (str): The name of the Slurm job script to use (default is "cellpose.sh").

        Returns:
            Tuple[str, dict]: A tuple containing the Slurm sbatch command and the environment dictionary.

        """
        sbatch_env = {
            "DATA_PATH": f"{self.slurm_data_path}/{input_data}",
            "IMAGE_PATH": f"{self.slurm_images_path}/{model}",
            "IMAGE_VERSION": f"{image_version}",
        }
        cellpose_env = {
            "DIAMETER": f"{cell_diameter}",
            "PROB_THRESHOLD": f"{prob_threshold}",
            "NUC_CHANNEL": f"{nuc_channel}",
            "CP_MODEL": f"{cp_model}",
            "USE_GPU": "true",
        }
        env = {**sbatch_env, **cellpose_env}

        email_param = "" if email is None else f" --mail-user={email}"
        time_param = "" if time is None else f" --time={time}"
        job_params = [time_param, email_param]
        job_param = "".join(job_params)
        sbatch_cmd = f"sbatch{job_param} --output=omero-%4j.log {self.slurm_script_path}/jobs/{job_script}"

        return sbatch_cmd, env

    def copy_zip_locally(self, local_tmp_storage: str, filename: str) -> TransferResult:
        """ Copy zip from SLURM to local server

        Note about (Transfer)Result:

        Unlike similar classes such as invoke.runners.Result or fabric.runners.Result 
        (which have a concept of “warn and return anyways on failure”) this class has no useful truthiness behavior. 
        If a file transfer fails, some exception will be raised, either an OSError or an error from within Paramiko.

        Args:
            local_tmp_storage (String): Path to store zip
            filename (String): Zip filename on Slurm
        """
        print(f"Copying zip {filename} from Slurm to {local_tmp_storage}")
        return self.get(
            remote=f"{filename}.zip",
            local=local_tmp_storage)

    def zip_data_on_slurm_server(self, data_location: str, filename: str, env: Optional[Dict[str, str]] = None) -> Result:
        """Zip the output folder of a job on SLURM

        Args:
            data_location (String): Folder on SLURM with the "data/out" subfolder
            filename (String): Name to give to the zipfile
        """
        # zip
        zip_cmd = self.get_zip_command(data_location, filename)
        print(f"Zipping {data_location} as {filename} on Slurm")
        return self.run_commands([zip_cmd], env=env)

    def get_zip_command(self, data_location: str, filename: str) -> str:
        return self._ZIP_CMD.format(filename=filename, data_location=data_location)

    def get_logfile_from_slurm(self, slurm_job_id: str, local_tmp_storage: str = "/tmp/", logfile: str = None) -> Tuple[str, str, TransferResult]:
        """Copy the logfile of given SLURM job to local server

        Note about (Transfer)Result:

        Unlike similar classes such as invoke.runners.Result or fabric.runners.Result 
        (which have a concept of “warn and return anyways on failure”) this class has no useful truthiness behavior. 
        If a file transfer fails, some exception will be raised, either an OSError or an error from within Paramiko.

        Args:
            slurm_job_id (String): ID of the SLURM job

        Returns:
            Tuple: directory, full path of the logfile, and TransferResult
        """
        if logfile is None:
            logfile = self._LOGFILE
        logfile = logfile.format(slurm_job_id=slurm_job_id)
        print(f"Copying logfile {logfile} from Slurm to {local_tmp_storage}")
        result = self.get(
            remote=logfile,
            local=local_tmp_storage)
        export_file = local_tmp_storage+logfile
        return local_tmp_storage, export_file, result

    def get_unzip_command(self, zipfile: str, filter_filetypes: str = "*.tiff *.tif") -> str:
        """
        Generate a command string for unzipping a data archive and creating 
        required directories for Slurm jobs.

        Args:
            zipfile (str): The name of the zip archive file to extract. Without extension.
            filter_filetypes (str, optional): A space-separated string containing the file extensions to extract
            from the zip file. The default value is "*.tiff *.tif".
            Setting this argument to `None` or '*' will omit the file filter and extract all files.

        Returns:
            str: The command to extract the specified filetypes from the zip file.

        """
        if filter_filetypes is None:
            filter_filetypes = '*'  # omit filter
        unzip_cmd = f"mkdir {self.slurm_data_path}/{zipfile} \
                    {self.slurm_data_path}/{zipfile}/data \
                    {self.slurm_data_path}/{zipfile}/data/in \
                    {self.slurm_data_path}/{zipfile}/data/out \
                    {self.slurm_data_path}/{zipfile}/data/gt; \
                    7z e -y -o{self.slurm_data_path}/{zipfile}/data/in \
                    {self.slurm_data_path}/{zipfile}.zip {filter_filetypes}"

        return unzip_cmd

    def get_image_versions_and_data_files(self, model: str) -> List[List[str]]:
        """
        Gets the available image versions and (input) data files for a given model.

        Args:
            model (str): The name of the model to query for.

        Returns:
            List[List[str]]: A list of 2 lists, the first containing the available image versions
            and the second containing the available data files.
        Raises:
            ValueError: If the provided model is not found in the SlurmClient's known model paths.
        """
        try:
            image_path = self.slurm_model_paths.get(model)
        except KeyError:
            raise ValueError(
                f"No path known for provided model {model}, in {self.slurm_model_paths}")
        cmdlist = [self._VERSION_CMD.format(slurm_images_path=self.slurm_images_path,
                                            image_path=image_path),
                   self._DATA_CMD.format(slurm_data_path=self.slurm_data_path)]
        # split responses per command
        response_list = self.run_commands_split_out(cmdlist)
        # split lines further into sublists
        response_list = [response.strip().split('\n')
                         for response in response_list]
        return response_list[0], response_list[1]

  
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
        # TODO this somehow gets also datasets? But we only allow projects. Filter?
        objparams = [rstring('%d: %s' % (d.id, d.getName()))
                     for d in conn.getObjects('Project') if type(d) == omero.gateway.ProjectWrapper]
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
            print(line)
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

        _oldjobs = slurmClient.list_old_jobs()
        _projects = getUserProjects()

        client = scripts.client(
            'Slurm Get Results',
            '''Retrieve the results from your SLURM job.
            
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
                result = slurmClient.check_job_status(slurm_job_id)
                print(result.stdout)
                message += f"\n{result.stdout}"

            # Pull project from Omero
            project_ids = unwrap(client.getInput("Project"))
            print(project_ids)
            projects = [conn.getObject("Project", p.split(":")[0])
                        for p in project_ids]

            # Job log
            if unwrap(client.getInput(_COMPLETED_JOB)):
                try:
                    # Copy file to server
                    local_tmp_storage, export_file, get_result = slurmClient.get_logfile_from_slurm(
                        slurm_job_id)
                    message += "\nSuccesfully copied logfile."
                    print(message, get_result)

                    # Read file for data location
                    data_location = extract_data_location_from_log(export_file)
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
                                client, conn, message, slurm_job_id, projects, folder)

                            message = unzip_zip_locally(message, folder)

                            message = upload_contents_to_omero(
                                client, conn, message, folder)

                            message = cleanup_tmp_files_locally(
                                message, folder)

                            # TODO cleanup_tmp_files_slurm ?

                except Exception as e:
                    message += f" Retrieving results failed: {e}\n"

            client.setOutput("Message", rstring(str(message)))

        finally:
            client.closeSession()


if __name__ == '__main__':
    runScript()
