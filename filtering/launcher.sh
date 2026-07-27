#!/bin/bash
#SBATCH --job-name=launcher
#SBATCH --error=/gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/filtering/error_orchestrator_filtering/launcher%j.log
#SBATCH --output=/gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/filtering/output_orchestrator_filtering/launcher%j.log
#SBATCH --time=02-00:00:00
#SBATCH --exclusive
#SBATCH --nodes=1
#SBATCH --partition=gpp
#SBATCH --qos gp_bscls
#SBATCH --account bsc88

source /gpfs/projects/bsc88/text/environments/tokenization_20240711/bin/activate
srun python3 /gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/filtering/orchestrator_filtering.py /gpfs/projects/bsc88/data/01-raw-collections/fine_pdfs_copyright_licenses_20261702 /gpfs/projects/bsc88/data/01-raw-collections/finepdfs-edu-filtered_copyright_licenses_20262502

#srun python3 script input_folder output_folder