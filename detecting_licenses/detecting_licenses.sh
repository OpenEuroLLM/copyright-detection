#!/bin/bash
#SBATCH --job-name=licenses
#SBATCH --error=/gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/detecting_licenses/error_orchestrator/error%j.log
#SBATCH --output=/gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/detecting_licenses/output_orchestrator/output%j.log
#SBATCH --time=02-00:00:00
#SBATCH --exclusive
#SBATCH --nodes=1
#SBATCH --partition=gpp
#SBATCH --qos gp_bscls
#SBATCH --account bsc88
#SBATCH --cpus-per-task=4

INPUT_JSONL="$1"
OUTPUT_JSONL="$2"

source /gpfs/projects/bsc88/text/environments/tokenization_20240711/bin/activate
srun python3 /gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/detecting_licenses/detecting_licenses.py $INPUT_JSONL $OUTPUT_JSONL --workers $SLURM_CPUS_PER_TASK

