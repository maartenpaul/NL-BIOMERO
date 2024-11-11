#!/bin/bash

# Check if correct number of arguments is provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <path_to_images> <dataset_id>"
    exit 1
fi

# Store arguments in named variables
IMAGE_PATH=$1
DATASET_ID=$2

# Check if directory exists
if [ ! -d "$IMAGE_PATH" ]; then
    echo "Error: Directory $IMAGE_PATH does not exist"
    exit 1
fi

# OMERO server connection details
SERVER="localhost"
PORT="4064"
USER="root"
PASS="omero"
GROUP="system"

# Login to OMERO
echo "Logging in to OMERO..."
omero login -s $SERVER -p $PORT -u $USER -w $PASS -g $GROUP

# Check if login was successful
if [ $? -ne 0 ]; then
    echo "Error: Failed to login to OMERO server"
    exit 1
fi

# Import images
echo "Importing images from $IMAGE_PATH to dataset $DATASET_ID..."
omero import -d $DATASET_ID "$IMAGE_PATH"/*

# Check if import was successful
if [ $? -ne 0 ]; then
    echo "Error: Failed to import images"
    exit 1
fi

echo "Import completed successfully"

# Logout
omero logout