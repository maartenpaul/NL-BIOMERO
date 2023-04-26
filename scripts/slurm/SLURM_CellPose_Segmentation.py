#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Original work Copyright (C) 2014 University of Dundee
#                                   & Open Microscopy Environment.
#                    All Rights Reserved.
# Modified work Copyright 2022 Torec Luik, Amsterdam UMC
# Use is subject to license terms supplied in LICENSE.txt
#

from __future__ import print_function
import omero
from omero.grid import JobParams
from omero.rtypes import rstring, unwrap
import omero.scripts as omscripts
from typing import List
import re
from fabric import Connection, Result
from paramiko import SSHException
import configparser

IMAGE_EXPORT_SCRIPT = "_SLURM_Image_transfer.py"
SCRIPTNAMES = [IMAGE_EXPORT_SCRIPT]
_DEFAULT_DATA_TYPE = "Image"
_DEFAULT_MODEL = "nuclei"
_VALUES_MODELS = [rstring(_DEFAULT_MODEL), rstring("cyto")]
_PARAM_MODEL = "Model"
_PARAM_NUCCHANNEL = "Nuclear Channel"
_PARAM_PROBTHRESH = "Cell probability threshold"
_PARAM_DIAMETER = "Cell diameter"
DEFAULT_MAIL = "No"
DEFAULT_TIME = "00:15:00"


class SlurmClient(Connection):
    """A client for connecting to and interacting with a Slurm cluster over SSH.

    This class extends the Fabric Connection class, adding methods and attributes specific to working with Slurm.

    SlurmClient accepts the same arguments as Connection. So below only mentions the added ones:

    Attributes:
        slurm_data_path (str): The path to the directory containing the data files for Slurm jobs.
        slurm_images_path (str): The path to the directory containing the Singularity images for Slurm jobs.
        slurm_model_paths (dict): A dictionary containing the paths to the Singularity images for specific Slurm job models.


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
    _DEFAULT_SLURM_DATA_PATH = "my-scratch/data/"
    _DEFAULT_SLURM_IMAGES_PATH = "my-scratch/singularity_images/workflows/"
    _GIT_DIR_SCRIPT = "slurm-scripts/"
    _OUT_SEP = "--split--"
    _VERSION_CMD = "ls -h {slurm_images_path}{image_path} | grep -oP '(?<=-)v.+(?=.simg)'"
    _DATA_CMD = "ls -h {slurm_data_path} | grep -oP '.+(?=.zip)'"

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
                 slurm_model_paths: dict = None
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
        # Create the SlurmClient object with the parameters read from the config file
        return cls(host=host,
                   inline_ssh_env=inline_ssh_env,
                   slurm_data_path=slurm_data_path,
                   slurm_images_path=slurm_images_path,
                   slurm_model_paths=slurm_model_paths)

    def validate(self):
        """Validate the connection to the Slurm cluster by running a simple command.

        Returns:
            bool: True if the command is executed successfully, False otherwise.
        """
        return self.run('echo " "').ok

    def run_commands(self, cmdlist: List[str], sep=' && ') -> Result:
        """Runs a list of shell commands consecutively, ensuring success of each before calling the next.

        These commands retain the same session (env vars etc.), unlike running them separately.

        Args:
            cmdlist (List[str]): A list of shell commands to run on SLURM

        Returns:
            Result: The result of the last command in the list.
        """
        cmd = sep.join(cmdlist)
        print(f"Running commands, with sep {sep}: {cmd}")
        return self.run(cmd)

    def run_commands_split_out(self, cmdlist: List[str]) -> List[str]:
        """Runs a list of shell commands consecutively and splits the output of each command.

        Each command in the list is executed with a separator in between that is unique and can be used to split
        the output of each command later. The separator used is specified by the `_OUT_SEP` attribute of the
        SlurmClient instance.

        Args:
            cmdlist (List[str]): A list of shell commands to run.

        Returns:
            List[str]: A list of strings, where each string corresponds to the output of a single command
                    in `cmdlist` split by the separator `_OUT_SEP`.
        Raises:
            SSHException: If any of the commands fail to execute successfully.
        """
        result = self.run_commands(cmdlist=cmdlist,
                                   sep=f" && echo {self._OUT_SEP} && ")
        if result.ok:
            response = result.stdout
            split_responses = response.split(self._OUT_SEP)
            return split_responses
        else:
            error = f"Result is not ok: {result}"
            print(error)
            raise SSHException(error)

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


def runScript():
    """
    The main entry point of the script
    """

    with SlurmClient.from_config() as slurmClient:

        params = JobParams()
        params.authors = ["Torec Luik"]
        params.version = "0.0.3"
        params.description = f'''Script to run CellPose on slurm cluster.
        First run the {IMAGE_EXPORT_SCRIPT} script to export your data to the cluster.
        
        Specifically will run: 
        https://hub.docker.com/r/torecluik/t_nucleisegmentation-cellpose
        

        This runs a script remotely on the SLURM cluster.
        Connection ready? {slurmClient.validate()}
        '''
        params.name = 'Slurm Cellpose Segmentation'
        params.contact = 't.t.luik@amsterdamumc.nl'
        params.institutions = ["Amsterdam UMC"]
        params.authorsInstitutions = [[1]]

        _versions, _datafiles = slurmClient.get_image_versions_and_data_files(
            'cellpose')
        input_list = [
            omscripts.Bool("CellPose", grouping="04", default=True),
            omscripts.String(_PARAM_MODEL, optional=False, grouping="04.3",
                             values=_VALUES_MODELS, default=_DEFAULT_MODEL),
            omscripts.Int(_PARAM_NUCCHANNEL, optional=True, grouping="04.4",
                          description="Channel with the nuclei (to segment)",
                          default=0),
            omscripts.Float(_PARAM_PROBTHRESH, optional=True, grouping="04.5",
                            description="threshold when to segment (0 = everything, 1 = nothing)",
                            default=0.5),
            omscripts.Float(_PARAM_DIAMETER, optional=True, grouping="04.6",
                            description="Diameter of a cell. Leave at 0 to let the computer guess.",
                            default=0),
            omscripts.String("Folder_Name", grouping="05",
                             description=f"Name of folder where images are stored, as provided with {IMAGE_EXPORT_SCRIPT}",
                             values=_datafiles),
            omscripts.Bool("SLURM Job Parameters",
                           grouping="06", default=True),
            omscripts.String("Version", grouping="06.1",
                             description="Version of the Singularity Image of Cellpose",
                             values=_versions),
            omscripts.String("Duration", grouping="06.2",
                             description="Maximum time the script should run for. Max is 8 hours. Notation is hh:mm:ss",
                             default=DEFAULT_TIME),
            omscripts.String("E-mail", grouping="06.3",
                             description="Provide an e-mail if you want a mail when your job is done or cancelled.",
                             default=DEFAULT_MAIL)
        ]
        inputs = {
            p._name: p for p in input_list
        }
        params.inputs = inputs
        params.namespaces = [omero.constants.namespaces.NSDYNAMIC]
        client = omscripts.client(params)

        cellpose_version = unwrap(client.getInput("Version"))
        try:
            # 1. Get image(s) from OMERO
            # 2. Send image(s) to SLURM
            # Use _SLURM_Image_Transfer script from Omero

            # 3. Call SLURM (segmentation)
            zipfile = unwrap(client.getInput("Folder_Name"))
            cp_model = unwrap(client.getInput(_PARAM_MODEL))
            nuc_channel = unwrap(client.getInput(_PARAM_NUCCHANNEL))
            prob_threshold = unwrap(client.getInput(_PARAM_PROBTHRESH))
            cell_diameter = unwrap(client.getInput(_PARAM_DIAMETER))
            email = unwrap(client.getInput("E-mail"))
            time = unwrap(client.getInput("Duration"))
            cmdlist = []
            # TODO move unzip command to SlurmClient
            unzip_cmd = f"mkdir {BASE_DATA_PATH}/{zipfile} \
                {BASE_DATA_PATH}/{zipfile}/data \
                {BASE_DATA_PATH}/{zipfile}/data/in \
                {BASE_DATA_PATH}/{zipfile}/data/out \
                {BASE_DATA_PATH}/{zipfile}/data/gt; \
                7z e -y -o{BASE_DATA_PATH}/{zipfile}/data/in \
                {BASE_DATA_PATH}/{zipfile}.zip *.tiff *.tif"
            cmdlist.append(unzip_cmd)
            # TODO move update command to SlurmClient
            update_cmd = f"git -C {GIT_DIR_SCRIPT} pull"
            cmdlist.append(update_cmd)
            # TODO move sbatch command to SlurmClient
            sbatch_cmd = f"export DATA_PATH={BASE_DATA_PATH}/{zipfile} ; \
            export IMAGE_PATH={IMAGE_PATH} ; \
            export IMAGE_VERSION={cellpose_version} ; \
            export DIAMETER={cell_diameter} ; \
            export PROB_THRESHOLD={prob_threshold} ; \
            export NUC_CHANNEL={nuc_channel} ; \
            export CP_MODEL={cp_model} ; \
            export USE_GPU=true ;"
            if email != DEFAULT_MAIL:
                sbatch_cmd += f" sbatch --mail-user={email} --time={time} {GIT_DIR_SCRIPT}/jobs/cellpose.sh"
            else:
                sbatch_cmd += f" sbatch --time={time} {GIT_DIR_SCRIPT}/jobs/cellpose.sh"
            cmdlist.append(sbatch_cmd)
            # ... Submitted batch job 73547
            print_result = slurmClient.run_commands(cmdlist)
            print_result = "".join(print_result.stdout)
            print(print_result)
            SLURM_JOB_ID = next((int(s.strip()) for s in print_result.split(
                "Submitted batch job") if s.strip().isdigit()), -1)
            print_result = f"Submitted to SLURM as batch job {SLURM_JOB_ID}."
            # 4. Poll SLURM results
            try:
                cmdlist = []
                cmdlist.append(f"scontrol show job {SLURM_JOB_ID}")
                print_job = slurmClient.run_commands(cmdlist)
                print(print_job.stdout)
                job_state = re.search(
                    'JobState=(\w+) Reason=(\w+)', print_job.stdout).group()
                print_result += f"\n{job_state}"
            except Exception as e:
                print_result += f" ERROR WITH JOB: {e}"

            # 5. Retrieve SLURM images

            # 6. Store results in OMERO

            # 7. Script output
            client.setOutput("Message", rstring(print_result))
        finally:
            client.closeSession()


if __name__ == '__main__':
    runScript()
