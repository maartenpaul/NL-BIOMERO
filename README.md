# OMERO server with Omero-Slurm-Client


This is an adaptation of [OMERO.server grid and OMERO.web (docker-compose)](https://github.com/ome/docker-example-omero-grid)

This is an example of running [OMERO.server components on multiple nodes using OMERO.grid](http://www.openmicroscopy.org/site/support/omero5/sysadmins/grid.html#nodes-on-multiple-hosts) in Docker, but with a connection to Omero Slurm Client.

OMERO.server is listening on the standard OMERO ports `4063` and `4064`.
OMERO.web is listening on port `4080` (http://localhost:4080/).


## Quickstart
Clone this repository locally (from the commandline)

    git clone https://github.com/TorecLuik/docker-example-omero-grid-amc.git

Change into the new directory

    cd docker-example-omero-grid-amc

Setup the connection with Slurm:

First, setup a configuration file, e.g. take the local slurm:

    cp worker-processor/slurm-config.localslurm.ini worker-processor/slurm-config.ini

Next, actually setup a local Slurm that matches this config.

Follow the README on https://github.com/TorecLuik/slurm-docker-cluster

Or in short: 

    cd ..
    git clone https://github.com/TorecLuik/slurm-docker-cluster
    cd slurm-docker-cluster
    docker-compose up -d --build

Then let's go back to our omero setup:

    cd docker-example-omero-grid-amc



Build and start the containers:

    docker-compose up -d --build

If you want, follow along with the logs on your commandline:

    docker-compose logs -f
    
You can exit the logs with CTRL+C (your Omero will keep running, because we ran them with `-d` = `detached`)

Log in on web (`localhost:4080`) as user `root` password `omero`. This might take a bit to get ready as the servers start up.

Enjoy!


## Docker specifics 

To stop the cluster:

    docker-compose down

N.B. Data is stored on Docker volumes, which are not automatically deleted when you down the setup. Convenient.

To remove volumes as well:

    docker-compose down --volumes

To rebuild a single container (while running your cluster):

    docker-compose up -d --build <name>

To attach to a running container:

    docker-compose exec <name> /bin/bash

Where `<name>` is e.g. `omeroworker-processor`

Exit back to your commandline by typing `exit`.



## Slurm specifics

Checkout the [Omero Slurm Client documentation](https://nl-bioimaging.github.io/omero-slurm-client/) for more details on how to setup your Slurm connection with Omero. 

In short, you always need:
- (headless) SSH setup to Slurm server from your host computer. See for example `ssh.config.example`.
    - Slurm IP
    - Slurm SSH port (probably `22`)
    - Slurm username
    - SSH keys (public key exchanged with Slurm server)
    - SSH alias config file stored as `~/.ssh/config`
- Configuration of `slurm-config.ini`. 
    - Alias used in your config, e.g. `localslurm` 
    - Setup storage paths on Slurm server, e.g. `slurm_data_path`, `slurm_images_path` and `slurm_script_path`.
