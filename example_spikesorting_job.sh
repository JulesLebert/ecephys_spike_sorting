#!/bin/bash -l

# Request 1 hour of wallclock time (format hours:minutes:seconds).
#$ -l h_rt=01:00:00

# Request 128 gigabyte of RAM (must be an integer followed by M, G, or T)
#$ -l mem=128

# Request 15 gigabyte of TMPDIR space (default is 10 GB)
#$ -l tmpfs=15G

# For 1 GPU
#$ -l gpu=1

# Set the name of the job.
#$ -N spikesort

# Set the working directory to somewhere in your scratch space.  
#  This is a necessary step as compute nodes cannot write to $HOME.
# Replace "<your_UCL_id>" with your UCL user ID :)
#$ -wd /home/skgtjml/Scratch/workspace

module load xorg-utils/X11R7.7
module load matlab/full/r2021a/9.10
module load cuda/10.1.243/gnu-4.9.2
module load python3/3.8

# Activate python environment
. /home/skgtjml/.local/share/virtualenvs/ecephys_spike_sorting-JEluCBiM/bin/activate

# Some code related to matlab engine
# matlab.engine can't be imported in python without these
# For for information, see:
# https://uk.mathworks.com/matlabcentral/answers/816045-modulenotfounderror-issue-using-matlab-engine-with-rhel-or-centos-linux 
# https://uk.mathworks.com/matlabcentral/answers/868193-segmentation-fault-when-using-matlab-engine-with-rhel-or-centos-linux
export PYTHONPATH=${PYTHONPATH}:/lustre/shared/ucl/apps/Matlab/R2021a/full/extern/engines/python/dist/matlab/engine/glnxa64
export LD_PRELOAD=/lustre/shared/ucl/apps/Matlab/R2021a/full/bin/glnxa64/glibc-2.17_shim.so

# Your work should be done in $TMPDIR 
cd $TMPDIR

python /home/skgtjml/code/ecephys_spike_sorting/ecephys_spike_sorting/scripts/jules_sglx_multi_run_pipeline.py