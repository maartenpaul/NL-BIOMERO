#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
-----------------------------------------------------------------------------
  Copyright (C) 2023 T T Luik
  Copyright (C) 2006-2014 University of Dundee. All rights reserved.


  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License along
  with this program; if not, write to the Free Software Foundation, Inc.,
  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

------------------------------------------------------------------------------

This script takes a number of images and saves individual image planes in a
zip file for download, then exports it to SLURM.

@author Torec Luik
@version 0.0.2
"""

import omero.scripts as scripts
from omero.gateway import BlitzGateway
import omero.util.script_utils as script_utils
import omero
from omero.rtypes import rstring, rlong, robject
from omero.constants.namespaces import NSCREATED, NSOMETIFF
import os
from pathlib import Path
from typing import List
import glob
import zipfile
from datetime import datetime
from fabric import Connection, Result
from fabric.transfer import Result as TransferResult
import configparser
from paramiko import SSHException
try:
    from PIL import Image  # see ticket:2597
except ImportError:
    import Image

_PYCMD = "Python_Command"
_DEFAULT_CMD = "import numpy as np; arr = np.array([1,2,3,4,5]); print(arr.mean())"
_RUNPY = "Run_Python"
_RUNSLRM = "Check_SLURM_Status"
_SQUEUE = "Check_Queue"
_SINFO = "Check_Cluster"
_SOTHER = "Run_Other_Command"
_SCMD = "Linux_Command"
_DEFAULT_SCMD = "ls -la"


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


# keep track of log strings.
log_strings = []


def log(text):
    """
    Adds the text to a list of logs. Compiled into text file at the end.
    """
    # Handle unicode
    try:
        text = text.encode('utf8')
    except UnicodeEncodeError:
        pass
    log_strings.append(str(text))


def compress(target, base):
    """
    Creates a ZIP recursively from a given base directory.

    @param target:      Name of the zip file we want to write E.g.
                        "folder.zip"
    @param base:        Name of folder that we want to zip up E.g. "folder"
    """
    zip_file = zipfile.ZipFile(target, 'w')
    try:
        files = os.path.join(base, "*")
        for name in glob.glob(files):
            zip_file.write(name, os.path.basename(name), zipfile.ZIP_DEFLATED)

    finally:
        zip_file.close()


def save_plane(image, format, c_name, z_range, project_z, t=0, channel=None,
               greyscale=False, zoom_percent=None, folder_name=None):
    """
    Renders and saves an image to disk.

    @param image:           The image to render
    @param format:          The format to save as
    @param c_name:          The name to use
    @param z_range:         Tuple of (zIndex,) OR (zStart, zStop) for
                            projection
    @param t:               T index
    @param channel:         Active channel index. If None, use current
                            rendering settings
    @param greyscale:       If true, all visible channels will be
                            greyscale
    @param zoom_percent:    Resize image by this percent if specified
    @param folder_name:     Indicate where to save the plane
    """

    original_name = image.getName()
    log("")
    log("save_plane..")
    log("channel: %s" % c_name)
    log("z: %s" % z_range)
    log("t: %s" % t)

    # if channel == None: use current rendering settings
    if channel is not None:
        image.setActiveChannels([channel+1])    # use 1-based Channel indices
        if greyscale:
            image.setGreyscaleRenderingModel()
        else:
            image.setColorRenderingModel()
    if project_z:
        # imageWrapper only supports projection of full Z range (can't
        # specify)
        image.setProjection('intmax')

    # All Z and T indices in this script are 1-based, but this method uses
    # 0-based.
    plane = image.renderImage(z_range[0]-1, t-1)
    if zoom_percent:
        w, h = plane.size
        fraction = (float(zoom_percent) / 100)
        plane = plane.resize((int(w * fraction), int(h * fraction)),
                             Image.ANTIALIAS)

    if format == "PNG":
        img_name = make_image_name(
            original_name, c_name, z_range, t, "png", folder_name)
        log("Saving image: %s" % img_name)
        plane.save(img_name, "PNG")
    elif format == 'TIFF':
        img_name = make_image_name(
            original_name, c_name, z_range, t, "tiff", folder_name)
        log("Saving image: %s" % img_name)
        plane.save(img_name, 'TIFF')
    else:
        img_name = make_image_name(
            original_name, c_name, z_range, t, "jpg", folder_name)
        log("Saving image: %s" % img_name)
        plane.save(img_name)


def make_image_name(original_name, c_name, z_range, t, extension, folder_name):
    """
    Produces the name for the saved image.
    E.g. imported/myImage.dv -> myImage_DAPI_z13_t01.png
    """
    name = os.path.basename(original_name)
    # name = name.rsplit(".",1)[0]  # remove extension
    if len(z_range) == 2:
        z = "%02d-%02d" % (z_range[0], z_range[1])
    else:
        z = "%02d" % z_range[0]
    img_name = "%s_%s_z%s_t%02d.%s" % (name, c_name, z, t, extension)
    if folder_name is not None:
        img_name = os.path.join(folder_name, img_name)
    # check we don't overwrite existing file
    i = 1
    name = img_name[:-(len(extension)+1)]
    while os.path.exists(img_name):
        img_name = "%s_(%d).%s" % (name, i, extension)
        i += 1
    return img_name


def save_as_ome_tiff(conn, image, folder_name=None):
    """
    Saves the image as an ome.tif in the specified folder
    """

    extension = "ome.tif"
    name = os.path.basename(image.getName())
    img_name = "%s.%s" % (name, extension)
    if folder_name is not None:
        img_name = os.path.join(folder_name, img_name)
    # check we don't overwrite existing file
    i = 1
    path_name = img_name[:-(len(extension)+1)]
    while os.path.exists(img_name):
        img_name = "%s_(%d).%s" % (path_name, i, extension)
        i += 1

    log("  Saving file as: %s" % img_name)
    file_size, block_gen = image.exportOmeTiff(bufsize=65536)
    with open(str(img_name), "wb") as f:
        for piece in block_gen:
            f.write(piece)


def save_planes_for_image(conn, image, size_c, split_cs, merged_cs,
                          channel_names=None, z_range=None, t_range=None,
                          greyscale=False, zoom_percent=None, project_z=False,
                          format="PNG", folder_name=None):
    """
    Saves all the required planes for a single image, either as individual
    planes or projection.

    @param renderingEngine:     Rendering Engine, NOT initialised.
    @param queryService:        OMERO query service
    @param imageId:             Image ID
    @param zRange:              Tuple: (zStart, zStop). If None, use default
                                Zindex
    @param tRange:              Tuple: (tStart, tStop). If None, use default
                                Tindex
    @param greyscale:           If true, all visible channels will be
                                greyscale
    @param zoomPercent:         Resize image by this percent if specified.
    @param projectZ:            If true, project over Z range.
    """

    channels = []
    if merged_cs:
        # render merged first with current rendering settings
        channels.append(None)
    if split_cs:
        for i in range(size_c):
            channels.append(i)

    # set up rendering engine with the pixels
    """
    renderingEngine.lookupPixels(pixelsId)
    if not renderingEngine.lookupRenderingDef(pixelsId):
        renderingEngine.resetDefaults()
    if not renderingEngine.lookupRenderingDef(pixelsId):
        raise "Failed to lookup Rendering Def"
    renderingEngine.load()
    """

    if t_range is None:
        # use 1-based indices throughout script
        t_indexes = [image.getDefaultT()+1]
    else:
        if len(t_range) > 1:
            t_indexes = range(t_range[0], t_range[1])
        else:
            t_indexes = [t_range[0]]

    c_name = 'merged'
    for c in channels:
        if c is not None:
            g_scale = greyscale
            if c < len(channel_names):
                c_name = channel_names[c].replace(" ", "_")
            else:
                c_name = "c%02d" % c
        else:
            # if we're rendering 'merged' image - don't want grey!
            g_scale = False
        for t in t_indexes:
            if z_range is None:
                default_z = image.getDefaultZ()+1
                save_plane(image, format, c_name, (default_z,), project_z, t,
                           c, g_scale, zoom_percent, folder_name)
            elif project_z:
                save_plane(image, format, c_name, z_range, project_z, t, c,
                           g_scale, zoom_percent, folder_name)
            else:
                if len(z_range) > 1:
                    for z in range(z_range[0], z_range[1]):
                        save_plane(image, format, c_name, (z,), project_z, t,
                                   c, g_scale, zoom_percent, folder_name)
                else:
                    save_plane(image, format, c_name, z_range, project_z, t,
                               c, g_scale, zoom_percent, folder_name)


def batch_image_export(conn, script_params, slurmClient: SlurmClient):

    # for params with default values, we can get the value directly
    split_cs = script_params["Export_Individual_Channels"]
    merged_cs = script_params["Export_Merged_Image"]
    greyscale = script_params["Individual_Channels_Grey"]
    data_type = script_params["Data_Type"]
    folder_name = script_params["Folder_Name"]
    folder_name = os.path.basename(folder_name)
    format = script_params["Format"]
    project_z = "Choose_Z_Section" in script_params and \
        script_params["Choose_Z_Section"] == 'Max projection'

    if (not split_cs) and (not merged_cs):
        log("Not chosen to save Individual Channels OR Merged Image")
        return

    # check if we have these params
    channel_names = []
    if "Channel_Names" in script_params:
        channel_names = script_params["Channel_Names"]
    zoom_percent = None
    if "Zoom" in script_params and script_params["Zoom"] != "100%":
        zoom_percent = int(script_params["Zoom"][:-1])

    # functions used below for each imaage.
    def get_z_range(size_z, script_params):
        z_range = None
        if "Choose_Z_Section" in script_params:
            z_choice = script_params["Choose_Z_Section"]
            # NB: all Z indices in this script are 1-based
            if z_choice == 'ALL Z planes':
                z_range = (1, size_z+1)
            elif "OR_specify_Z_index" in script_params:
                z_index = script_params["OR_specify_Z_index"]
                z_index = min(z_index, size_z)
                z_range = (z_index,)
            elif "OR_specify_Z_start_AND..." in script_params and \
                    "...specify_Z_end" in script_params:
                start = script_params["OR_specify_Z_start_AND..."]
                start = min(start, size_z)
                end = script_params["...specify_Z_end"]
                end = min(end, size_z)
                # in case user got z_start and z_end mixed up
                z_start = min(start, end)
                z_end = max(start, end)
                if z_start == z_end:
                    z_range = (z_start,)
                else:
                    z_range = (z_start, z_end+1)
        return z_range

    def get_t_range(size_t, script_params):
        t_range = None
        if "Choose_T_Section" in script_params:
            t_choice = script_params["Choose_T_Section"]
            # NB: all T indices in this script are 1-based
            if t_choice == 'ALL T planes':
                t_range = (1, size_t+1)
            elif "OR_specify_T_index" in script_params:
                t_index = script_params["OR_specify_T_index"]
                t_index = min(t_index, size_t)
                t_range = (t_index,)
            elif "OR_specify_T_start_AND..." in script_params and \
                    "...specify_T_end" in script_params:
                start = script_params["OR_specify_T_start_AND..."]
                start = min(start, size_t)
                end = script_params["...specify_T_end"]
                end = min(end, size_t)
                # in case user got t_start and t_end mixed up
                t_start = min(start, end)
                t_end = max(start, end)
                if t_start == t_end:
                    t_range = (t_start,)
                else:
                    t_range = (t_start, t_end+1)
        return t_range

    # Get the images or datasets
    message = ""
    objects, log_message = script_utils.get_objects(conn, script_params)
    message += log_message
    if not objects:
        return None, message

    # Attach figure to the first image
    parent = objects[0]

    if data_type == 'Dataset':
        images = []
        for ds in objects:
            images.extend(list(ds.listChildren()))
        if not images:
            message += "No image found in dataset(s)"
            return None, message
    else:
        images = objects

    log("Processing %s images" % len(images))

    # somewhere to put images
    curr_dir = os.getcwd()
    exp_dir = os.path.join(curr_dir, folder_name)
    try:
        os.mkdir(exp_dir)
    except OSError:
        pass
    # max size (default 12kx12k)
    size = conn.getDownloadAsMaxSizeSetting()
    size = int(size)

    ids = []
    # do the saving to disk

    for img in images:
        log("Processing image: ID %s: %s" % (img.id, img.getName()))
        pixels = img.getPrimaryPixels()
        if (pixels.getId() in ids):
            continue
        ids.append(pixels.getId())

        if format == 'OME-TIFF':
            if img._prepareRE().requiresPixelsPyramid():
                log("  ** Can't export a 'Big' image to OME-TIFF. **")
                if len(images) == 1:
                    return None, "Can't export a 'Big' image to %s." % format
                continue
            else:
                save_as_ome_tiff(conn, img, folder_name)
        else:
            size_x = pixels.getSizeX()
            size_y = pixels.getSizeY()
            if size_x*size_y > size:
                msg = "Can't export image over %s pixels. " \
                      "See 'omero.client.download_as.max_size'" % size
                log("  ** %s. **" % msg)
                if len(images) == 1:
                    return None, msg
                continue
            else:
                log("Exporting image as %s: %s" % (format, img.getName()))

            log("\n----------- Saving planes from image: '%s' ------------"
                % img.getName())
            size_c = img.getSizeC()
            size_z = img.getSizeZ()
            size_t = img.getSizeT()
            z_range = get_z_range(size_z, script_params)
            t_range = get_t_range(size_t, script_params)
            log("Using:")
            if z_range is None:
                log("  Z-index: Last-viewed")
            elif len(z_range) == 1:
                log("  Z-index: %d" % z_range[0])
            else:
                log("  Z-range: %s-%s" % (z_range[0], z_range[1]-1))
            if project_z:
                log("  Z-projection: ON")
            if t_range is None:
                log("  T-index: Last-viewed")
            elif len(t_range) == 1:
                log("  T-index: %d" % t_range[0])
            else:
                log("  T-range: %s-%s" % (t_range[0], t_range[1]-1))
            log("  Format: %s" % format)
            if zoom_percent is None:
                log("  Image Zoom: 100%")
            else:
                log("  Image Zoom: %s" % zoom_percent)
            log("  Greyscale: %s" % greyscale)
            log("Channel Rendering Settings:")
            for ch in img.getChannels():
                log("  %s: %d-%d"
                    % (ch.getLabel(), ch.getWindowStart(), ch.getWindowEnd()))

            try:
                save_planes_for_image(conn, img, size_c, split_cs, merged_cs,
                                      channel_names, z_range, t_range,
                                      greyscale, zoom_percent,
                                      project_z=project_z, format=format,
                                      folder_name=folder_name)
            finally:
                # Make sure we close Rendering Engine
                img._re.close()

        # write log for exported images (not needed for ome-tiff)
        name = 'Batch_Image_Export.txt'
        with open(os.path.join(exp_dir, name), 'w') as log_file:
            for s in log_strings:
                log_file.write(s)
                log_file.write("\n")

    if len(os.listdir(exp_dir)) == 0:
        return None, "No files exported. See 'info' for more details"
    # zip everything up (unless we've only got a single ome-tiff)
    if format == 'OME-TIFF' and len(os.listdir(exp_dir)) == 1:
        ometiff_ids = [t.id for t in parent.listAnnotations(ns=NSOMETIFF)]
        conn.deleteObjects("Annotation", ometiff_ids)
        export_file = os.path.join(folder_name, os.listdir(exp_dir)[0])
        namespace = NSOMETIFF
        output_display_name = "OME-TIFF"
        mimetype = 'image/tiff'
    else:
        export_file = "%s.zip" % folder_name
        compress(export_file, folder_name)
        mimetype = 'application/zip'
        output_display_name = f"Batch export zip '{folder_name}'"
        namespace = NSCREATED + "/omero/export_scripts/Batch_Image_Export"

    # Copy to SLURM
    try:
        r = slurmClient.transfer_data(Path(export_file))
        print(r)
        message += f"'{folder_name}' succesfully copied to SLURM!\n"
    except Exception as e:
        message += f"Copying to SLURM failed: {e}\n"

    file_annotation, ann_message = script_utils.create_link_file_annotation(
        conn, export_file, parent, output=output_display_name,
        namespace=namespace, mimetype=mimetype)
    message += ann_message
    return file_annotation, message


def run_script():
    """
    The main entry point of the script, as called by the client via the
    scripting service, passing the required parameters.
    """

    with SlurmClient.from_config() as slurmClient:

        data_types = [rstring('Dataset'), rstring('Image')]
        formats = [rstring('JPEG'), rstring('PNG'), rstring('TIFF'),
                   rstring('OME-TIFF')]
        default_z_option = 'Default-Z (last-viewed)'
        z_choices = [rstring(default_z_option),
                     rstring('ALL Z planes'),
                     # currently ImageWrapper only allows full Z-stack projection
                     rstring('Max projection'),
                     rstring('Other (see below)')]
        default_t_option = 'Default-T (last-viewed)'
        t_choices = [rstring(default_t_option),
                     rstring('ALL T planes'),
                     rstring('Other (see below)')]
        zoom_percents = omero.rtypes.wrap(["25%", "50%", "100%", "200%",
                                           "300%", "400%"])

        client = scripts.client(
            '_SLURM_Image_Transfer',
            f"""Save multiple images as TIFF
            in a zip file and export them to SLURM.
            Also attaches the zip as a downloadable file in OMERO.
            
            This runs a script remotely on your SLURM cluster.
            Connection ready? {slurmClient.validate()}""",

            scripts.String(
                "Data_Type", optional=False, grouping="1",
                description="The data you want to work with.", values=data_types,
                default="Image"),

            scripts.List(
                "IDs", optional=False, grouping="2",
                description="List of Dataset IDs or Image IDs").ofType(rlong(0)),

            scripts.Bool(
                "Image settings (Optional)", grouping="5",
                description="Settings for how to export your images",
                default=True
            ),

            scripts.Bool(
                "Export_Individual_Channels", grouping="5.6",
                description="Save individual channels as separate images",
                default=False),

            scripts.Bool(
                "Individual_Channels_Grey", grouping="5.6.1",
                description="If true, all individual channel images will be"
                " grayscale", default=False),

            scripts.List(
                "Channel_Names", grouping="5.6.2",
                description="Names for saving individual channel images"),

            scripts.Bool(
                "Export_Merged_Image", grouping="5.5",
                description="Save merged image, using current rendering settings",
                default=True),

            scripts.String(
                "Choose_Z_Section", grouping="5.7",
                description="Default Z is last viewed Z for each image, OR choose"
                " Z below.", values=z_choices, default=default_z_option),

            scripts.Int(
                "OR_specify_Z_index", grouping="5.7.1",
                description="Choose a specific Z-index to export", min=1),

            scripts.Int(
                "OR_specify_Z_start_AND...", grouping="5.7.2",
                description="Choose a specific Z-index to export", min=1),

            scripts.Int(
                "...specify_Z_end", grouping="5.7.3",
                description="Choose a specific Z-index to export", min=1),

            scripts.String(
                "Choose_T_Section", grouping="5.8",
                description="Default T is last viewed T for each image, OR choose"
                " T below.", values=t_choices, default=default_t_option),

            scripts.Int(
                "OR_specify_T_index", grouping="5.8.1",
                description="Choose a specific T-index to export", min=1),

            scripts.Int(
                "OR_specify_T_start_AND...", grouping="5.8.2",
                description="Choose a specific T-index to export", min=1),

            scripts.Int(
                "...specify_T_end", grouping="5.8.3",
                description="Choose a specific T-index to export", min=1),

            scripts.String(
                "Zoom", grouping="5.9", values=zoom_percents,
                description="Zoom (jpeg, png or tiff) before saving with"
                " ANTIALIAS interpolation", default="100%"),

            scripts.String(
                "Format", grouping="5.1",
                description="Format to save image", values=formats,
                default='TIFF'),

            scripts.String(
                "Folder_Name", grouping="3",
                description="Name of folder (and zip file) to store images",
                default='SLURM_IMAGES_'),

            version="0.0.3",
            authors=["Torec Luik", "William Moore", "OME Team"],
            institutions=["Amsterdam UMC", "University of Dundee"],
            contact="t.t.luik@amsterdamumc.nl",
            authorsInstitutions=[[1], [2]]
        )

        try:
            start_time = datetime.now()
            script_params = {}

            conn = BlitzGateway(client_obj=client)

            script_params = client.getInputs(unwrap=True)
            for key, value in script_params.items():
                log("%s:%s" % (key, value))

            # call the main script - returns a file annotation wrapper
            file_annotation, message = batch_image_export(
                conn, script_params, slurmClient)

            stop_time = datetime.now()
            log("Duration: %s" % str(stop_time-start_time))

            # return this fileAnnotation to the client.
            client.setOutput("Message", rstring(message))
            if file_annotation is not None:
                client.setOutput("File_Annotation",
                                 robject(file_annotation._obj))

        finally:
            client.closeSession()


if __name__ == "__main__":
    run_script()
