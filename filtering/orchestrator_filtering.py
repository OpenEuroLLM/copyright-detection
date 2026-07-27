import os
import sys
import subprocess
import time
from typing import List, Tuple
from math import ceil

"""
==========================================================
BATCH FILTERING JSONL SLURM SUBMISSION SCRIPT
==========================================================
This script automates the submission of .jsonl files to a Slurm cluster for batch processing. It recursively searches for all .jsonl files in a given directory, preserves the folder structure when generating output files, and submits jobs in controlled batches to avoid exceeding the maximum number of active jobs allowed per user. Each job executes filtering_restrictions.sh, which filters out restrictive-license, copyrighted, and book-flagged instances from the corresponding JSONL file. The system is designed for large-scale corpus processing on HPC environments. 
The output files follow the same relative directory structure and filenames as the input (no prefix is added). 
 
===Steps===
    1. Recursively search for all .jsonl files in the input directory. 
    2. Build corresponding output file paths under the output directory, preserving relative folder structure and filenames. 
    3. Wait for available job slots if the number of active Slurm jobs exceeds the defined maximum (MAX_ACTIVE_JOBS). 
    4. Submit JSONL files in batches (default batch size: 100) to Slurm using filtering_restrictions.sh. 
    5. Monitor job submission and print a status per batch: fully sent, partially sent (with the exact files affected), or not sent at all. 
 
===Job Control===
To prevent overloading the slurm queue, the script: 
    - Monitors the number of active jobs for the current user using squeue. 
    - Waits 2 minutes if the number of active jobs exceeds MAX_ACTIVE_JOBS (default:100). 
    - Submits jobs in batches, ensuring that at most one batch of 100 jobs is submitted at a time. 
 
===Usage===
python orchestrator_filtering.py <input_directory> <output_directory>
 
===Arguments===
    input_directory         Path to the folder containing JSONL files already enriched by detecting_licenses.py (recursive search applied)
    output_directory        Path to store the filtered JSONL files. The directory is created automatically if it does not exist.
"""

#1.===SEARCH JSONL FILES RECURSIVELY=== 
def find_jsonl_file(base_dir: str)-> List[str]:
    """
    This function recursively searches for all .jsonl files in a folder. It returns a list with the full paths of the .jsonl files.
    """
    jsonl_files = []
    
    #Go through the initial folder
    for root, _, files in os.walk(base_dir):
        for f in files: #Iteration over each file found in the current directory
            if f.lower().endswith(".jsonl"): #If file ends in .jsonl
                jsonl_files.append(os.path.join(root, f)) #Save its path in jsonl_files
    
    return jsonl_files #Return list with all jsonl paths

#2. ===BUILD POUTPUT FILES BASED ON JSONL INPUT FILES===
def build_output_files(jsonl_paths, base_dir, output_folder):
    """
    This function creates output file paths while preserving the relative folde structure from base_dir. 
    """
    output_files = []

    for path in jsonl_paths:
        #Get relative path of JSONL file relative to the base directory 
        rel_path = os.path.relpath(path, base_dir)  # e.g., folder2/subfolder2.1/C.jsonl

        # Split the relative path into directory and filename
        dirname, filename = os.path.split(rel_path)
        #Remove the file extension (.jsonl) from the filename
        name_no_ext = os.path.splitext(filename)[0]
        #Create a filtered name prefixing "license": license_<name>.jsonl
        filtered_name = f"{name_no_ext}.jsonl"

        # Build the output file path
        output_subfolder = os.path.join(output_folder, dirname)
        os.makedirs(output_subfolder, exist_ok=True) #Create the folder if it doesn't exist

        #Complete output file path
        output_file = os.path.join(output_subfolder, filtered_name)
        output_files.append(output_file) #Add to output files list 

    return output_files #Return the list of output file paths

#Maximum allowed simultaneous active jobs
MAX_ACTIVE_JOBS=100
#Get the current system user from environment variables
USER= os.getenv("USER")

#3. ===WAIT FOR AN AVAILABLE SLOT IN SLURM===
def wait_for_available_slot(): 
    """
    Wait until the number of active jobs (running + pending) for the current user is below MAX_ACTIVE_JOBS.
    """
    while True: 
        #Run "squeue" to check the number of jobs in Slurm for the current user
        result=subprocess.run(
           ["squeue", "-u", USER, "-h"], #List jobs for this user, without headers
           capture_output=True, 
           text=True
        )

        #Count the number of active jobs by splitting lines of the output 
        active_jobs=len(result.stdout.strip().splitlines())

        if active_jobs<MAX_ACTIVE_JOBS: #If number of jobs is below the limit
            print(f"Waiting... {active_jobs} active jobs (limit {MAX_ACTIVE_JOBS})")
            break #Exit loop and proceed

        time.sleep(120) #Otherwise, wait 2 minutes and check again

#4. ===SUBMIT BATCH JOBS TO SLURM===
def submit_job(jsonl_paths: List[str], base_dir: str, output_folder: str) -> bool:
    try:
        #Build the corresponding output file paths for the given JSONLs
        output_files = build_output_files(jsonl_paths, base_dir, output_folder)

        #Iterate over input/output file pairs
        for input_path, output_path in zip(jsonl_paths, output_files):
            wait_for_available_slot() #Wait if too many active jobs 

            #Submit the job to Slurm using sbatch 
            subprocess.run(
                [
                    "sbatch", #Slurm batch submission command 
                    "/gpfs/scratch/bsc88/bsc934385/copyright_and_licenses/filtering/filtering_restrictions.sh", #Bash script to execute
                    input_path, #Input JSONL path
                    output_path, #Output file path
                ],
                check=True, #Raise exception if sbatch fails 
            )

        return True #Return True if all submissions succeed

    except Exception as e:
        print(f"Submission error: {e}") #Print error message if something goes wrong
        return False #Return False if there was an exception

#5. ===MAIN===
def main():
    #1. Arguments of main 
    if len(sys.argv)<3: #Check if list of arguments has less than 3 (arg0 its the script itself)
        sys.exit(1) #if there are less than 3, you stop
    base_dir=sys.argv[1] #arg1: input folder
    output_dir=sys.argv[2] #arg2: output folder
    os.makedirs(output_dir, exist_ok=True) #If folder doesn't exist, it is created

    print(f"Input dir to analyze: {base_dir}")
    print(f"Output dir to store filtered data: {output_dir}")
 
    
    #2. Check if input folder (arg1) exists
    if not os.path.isdir(base_dir):
        print(f"Error: folder '{base_dir}' does not exist :(")
        sys.exit(1)

    ##3. Find all JSONL files inside base_dir
    jsonl_files=find_jsonl_file(base_dir)
    if not jsonl_files: 
        print("There are no .jsonls lol")
        sys.exit(1) #If error, then we stop 
    

    ## 4. Submit jobs in batches of 100 JSONL files
    batch_size = 100
    num_batches = ceil(len(jsonl_files) / batch_size) #Number of batches

    for b in range(num_batches):
        #Get a batch of JSONL files
        batch = jsonl_files[b*batch_size : (b+1)*batch_size]
        #Submit the batch to Slurm
        ok=submit_job(batch, base_dir, output_dir)

        #If slurm is ok, we get confirmation 
        if ok: 
            print(f"Job sent correctly: {batch[0].strip()}:{batch[-1].strip()}")
        # If not, we get an error
        else:
            print(f"Error: job not sent: {batch[0].strip()}:{batch[-1].strip()}")

if __name__ == "__main__":
    main()