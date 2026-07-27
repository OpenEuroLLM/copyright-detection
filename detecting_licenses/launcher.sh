#!/bin/bash
#SBATCH --job-name=launcher
#SBATCH --error=/gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/detecting_licenses/error_orchestrator/launcher%j.log
#SBATCH --output=/gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/detecting_licenses/output_orchestrator/launcher%j.log
#SBATCH --time=02-00:00:00
#SBATCH --exclusive
#SBATCH --nodes=1
#SBATCH --partition=gpp
#SBATCH --qos gp_bscls
#SBATCH --account bsc88

source /gpfs/projects/bsc88/text/environments/tokenization_20240711/bin/activate
srun python3 /gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/detecting_licenses/orchestrator_licenses.py /gpfs/projects/bsc88/data/01-raw-collections/finepdfs-edu_mx_20251121 /gpfs/projects/bsc88/data/01-raw-collections/fine_pdfs_copyright_licenses_20261702

#srun python3 script input_folder output_folder