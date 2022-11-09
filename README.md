# Specialized Processors - OMERO.server grid and OMERO.web (docker-compose)


This is an adaptation of [OMERO.server grid and OMERO.web (docker-compose)](https://github.com/ome/docker-example-omero-grid)

This is an example of running [OMERO.server components on multiple nodes using OMERO.grid](http://www.openmicroscopy.org/site/support/omero5/sysadmins/grid.html#nodes-on-multiple-hosts) in Docker, but with multiple and/or specialized processor nodes.

OMERO.server is listening on the standard OMERO ports `4063` and `4064`.
OMERO.web is listening on port `4080` (http://localhost:4080/).

Log in as user `root` password `omero`.
The initial password can be changed in [`docker-compose.yml`](docker-compose.yml).


## Run

First pull the latest major versions of the containers:

    docker-compose pull

Then start the containers:

    docker-compose up -d
    docker-compose logs -f

To rebuild a container:

    docker-compose up -d --build <name>

To attach to a container:

    docker-compose exec <name> /bin/bash

For more configuration options see:
- https://github.com/ome/omero-server-docker/blob/master/README.md
- https://github.com/ome/omero-web-docker/blob/master/README.md

## Processors

We have adjusted the [dockerfiles](./worker-gpu/Dockerfile) of workers/processors to work with multiple Python environments, possibly unique to that processor. 

The modified [processor-py](./processor.py) will check if a script job it receives matches any python environments it has and accept or reject the job based on that.

Specifically:
- The `worker-gpu` [image](./worker-gpu/Dockerfile) currently creates the 2 environments from the [.env](.env) file. This works with the example [cellpose](./scripts/Example_EnvCellpose_Segmentation.py) and [stardist](./scripts/Example_EnvStardist_Segmentation.py) scripts.
- The `worker-no-gpu` [image](./worker-no-gpu/Dockerfile) currently has no special environment, but does use the modified [processor](./processor.py). This only works with the [basic](./scripts/Example_Dynamic_Script.py) scripts. 
- The `worker` [image](./worker/Dockerfile) is still the default from [OME](https://github.com/ome/docker-example-omero-grid), not using the modified [processor](./processor.py). This only works with the [basic](./scripts/Example_Dynamic_Script.py) scripts.
- The [unknown environment](./scripts/Example_EnvUnknown_Dynamic_Script.py) script works with none of the processors.

### Configuration for GPU
You can also set the `CONFIG_omero_server_gpu: False` or `True` for the workers in the [compose](docker-compose.yml) file. There is a second check in the modified [processor-py](./processor.py) to see if this setting matches the script. 

Currently there is a non-strict implementation where a 'GPU server' is allowed to handle _both_ normal and GPU scripts, but a normal server is not allowed to handle GPU scripts. 

However, this is likely to be implemented differently or removed, as specifying python environments seems to handle most of this use-case already.

## Multiple processors

You can adjust the [compose](./docker-compose.yml) file to add a second worker with a different environment, or to reduce it to 1 processor.

Currently the behaviour of multiple processors is not working as intended.
