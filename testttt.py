import subprocess
from tqdm import tqdm
import time
import boto3
import paramiko
import sys
import os
from datetime import datetime

def execute_bash_conditional(command):
  try:
    result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()
  except subprocess.CalledProcessError as e:
    return f"Error: {e.stderr.strip()}"

def execute_multiple_bash_commands(commands, number_of_steps):
  return_code = ""
  # Execute each command and show progress
  for i, command in enumerate(tqdm(commands, desc="Executing Commands", unit="cmd")):
    print(f"\n\n    * Executing: {command}", end="\n\n")
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Stream output in real-time
    for line in process.stdout:
      print(line, end="")
    
    # Wait for the command to complete
    return_code = process.wait()
    if process.returncode != 0:
      print(f"Error: {process.stderr.read()}")
    
    # Simulate progress bar delay for better visualization
    time.sleep(3.5)
  
  
  # return_code = process.wait()

  if return_code == 0:
      print(f"\n\n *** The process #{number_of_steps} was executed SUCCESSFULLY.\n\n\n ")
  else:
      print(f"\n\n *** The process #{number_of_steps} FAILED with return code: {return_code}\n\n\n ")
  

# Example usage
# bash_command = """
# [ -d /home/mateo ] && echo 'Directory exists' || echo 'Directory does not exist'
# """
# output = execute_bash_conditional(bash_command)

bash_command = """
dir_path="/home/mateo"
expected_path="/home/mateo"
if [ "$dir_path" = "$expected_path" ]; then
  echo 'Paths match'
  echo "jeje\
jeje"
else
  echo 'Paths do not match'
fi

"""



### cmdGroup1: Run Helios Protection backup script
# This for... "LSATLCOHCLUSTER01"
# Then, within Protection, take group name "Inscope-LCAD-DBS90", that's a pyhisical file, NOT a log file
# and "Run Now" the replication.

# It will replicate from "LSATLCOHCLUSTER01" to a "Remote Cluster": "LSDENCOHCLUSTER01",
# making a "Retain for": "31 days",
# performing a "Backup all Objects in the Protection Group",
# with a "Backup Type": "Incremental", 
# Check if it's mandatory "physicalParams" parameter
 
cmdGroup1 = [
  "echo 'Starting the Protection Group backup process...'",
  "echo 'Gathering Protection Group Inscope-LCAD-DBS90 info...'"
  # It should be "Inscope-LCAD-DBS90" in the Helios environment
  # The previous command is NOT needed, just for the first time, to check the Protection Group name

  ]

cmdGroup2 = [
  """
  curl --request GET \
--url 'https://helios.cohesity.com/v2/mcm/data-protect/protection-groups/Inscope-LCAD-DBS90?includeLastRunInfo=true' \
--header 'accept: application/json' \
--header 'apiKey: <APIKEY>'
  """
]

  ### Send signal to create the Replication of the Protection Group
cmdGroup3 =[
  # EXTRACT PARAMETERS SIGNING IN HELIOS, by gathering the actual created "Policy" (with a GET answer or by the ID) and attach it to the Creation of Protection Group...
  """
  curl -X POST \
--url 'https://helios.cohesity.com/v2/data-protect/protection-groups' \
-H 'apiKey: <APIKEY>'\
-H 'Accept: application/json'\
-H 'Content-type: application/json'\
-H 'accessClusterId: "<IS IT NECESSARY?>"' \
--data-raw '{
  "name": "Inscope-LCAD-DBS90",
  "policyId": "<EXTRACT_THIS>",
  "environment": "kPhysicalFiles | <EXTRACT_THIS>",
  "<SPECIFY THE DR/SECONDARY REPLICA remote cluster:LSDENCOHCLUSTER01>"
  "alertPolicy": {
    "backupRunStatus": [
      "kFailure"
    ],
    "alertTargets": [
      {
        "emailAddress": "mateo.matta@datavail.com",
        "language": "en-us",
        "recipientType": "kTo"
      }
    ]
  }
}'
  """
]

cmdGroup4 = [
  "echo 'Starting the Recovery backup process...'",
]


# print(execute_multiple_bash_commands(cmdGroup1,1))

# # output = execute_multiple_bash_commands(cmdGroup2,1)

# failedOutput = ""

# while (execute_multiple_bash_commands(cmdGroup2,1)).__contains__("Running"):
#   print("Replication is currently running. Waiting for completion...")
#   print(execute_multiple_bash_commands(cmdGroup2,1))
  
#   time.sleep(10) # Wait for 10 seconds before checking again
# else:
#   output = execute_multiple_bash_commands(cmdGroup2,1)
#   if output.__contains__("Succeeded"):
#     print("Replication completed successfully.")
    
#   elif output.__contains__("SucceededWithWarning"):
#     print("Replication completed with warnings.")
    
#   else:    
#     failedOutput = output
#     print(f"Error: {failedOutput}")

#############################################

### MAKES SILENT THIS EXECUTION, JUST SHOW THE OUTPUTS !!!
db2insta_password = input("Please type the password for the db2insta user on LXATL00LCDDBS36.logisticare.com:\n")
# print("This one: ", db2insta_password)

cmdGroup5 = [
  "Beginning the Delete of Backup files in TR1 (Training-NON PROD server) of the previous week",
  # Execute a "rm *" bash command remotely, on the machine "LXATL00LCDDBS36.logisticare.com" (TR1), on the specific paths: "/backup_coh/backup1" and "/backup_coh/backup2",
  # all of this as "db2insta" user.
  # "#",
  # "sudo su - db2insta; rm -rf /backup_coh/backup1/**",
  # Similar to:ssh -t mateo@172.17.0.1 -p 2222 'sudo rm -rf /home/mateo/cmon/**'
  # "ssh -t db2insta@LXATL00LCDDBS36.logisticare.com -p 22 'sudo rm -rf /home/mateo/cmon/**'",
  # "rm -rf /backup_coh/backup2/**",
  
  
  # Execute a sudo command on a remote machine using SSH and SSH_ASKPASS helper

  'REMOTE_USER="mateo"',
  'REMOTE_HOST="172.17.0.1"',
  
  # 'REMOTE_USER="db2insta"',
  # 'REMOTE_HOST="LXATL00LCDDBS36.logisticare.com"',
  'MYPASSWORD="{db2insta_password}"',
  
  """
  # Creation of the file password.txt on the home folder of the remote system
  sshpass -p $MYPASSWORD ssh ${REMOTE_USER}@${REMOTE_HOST} "echo $MYPASSWORD > /home/password.txt; touch /backup_coh/backup1/deleteThisFile.txt"
  sshpass -p $MYPASSWORD ssh ${REMOTE_USER}@${REMOTE_HOST} "echo $MYPASSWORD > /home/password.txt; touch /backup_coh/backup2/deleteThisFile.txt"
  """,
  
  # """
  # # # Execution of the command which needs the sudo privileges (on remote system) using sshpass
  # # sshpass -p $MYPASSWORD ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo -S < /home/password.txt sudo rm -rf /backup_coh/backup1/**"
  # # sshpass -p $MYPASSWORD ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo -S < /home/password.txt sudo rm -rf /backup_coh/backup2/**"
  # # # The '<' directs file password.txt as input to sudo
  # # """,
  """
  # Execution of the command which needs the sudo privileges (on remote system) using sshpass
  sshpass -p $MYPASSWORD ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo -S < /home/password.txt sudo ls /"
  # The '<' directs file password.txt as input to sudo
  """,
  
  """
  # Deletion of the file password.txt
  sshpass -p $MYPASSWORD ssh ${REMOTE_USER}@${REMOTE_HOST} "rm /home/password.txt"
  """    
]
#

execute_multiple_bash_commands(cmdGroup5, 5)

### ___________ Recovery backup process ___________

# From Cohesity "Recover"/"Recoveries", choose the physical server (and NOT the archive one) called "Protection Group Inscope-LCAD-DBS90"
# ( from lsatl00lcddbs90 ->  (Server OS Linux))
# Then, take the files from the paths:  
# "/lcad_temp_table_1/db2_backup/LCAD_ATL.0.db2insta"
# "/lcad_temp_table_1/db2_backup2/LCAD_ATL.0.db2insta"

# Then, choose the target server as "lxatl00lcddbs36"
# and select the "Recover to" path as: "/backup_coh/backup1"

# Unselect "Overwrite Existing File/Folder" as: false

# Additional Options:
# - "Preserve file/folder attributes" as: true
# - "Continue recovery even if one of the Objects encounters an error" as: false

# "Cohesity network interface" as: "Auto Select"

# Finally, execute "Recover Files".

### Perform this with a WHILE loop (part 001 && part 002 should be as "................Done?"), until the process is finished, and then show the output of the process.
# Maybe, the status of the while should be taken from "Recovery task" (The API call to perform recovery should output the ID of the task, which can be used to check
# the status of the recovery task until it is completed), this one has the groups of PARTS that are being Recovered.
# _____________ Then

# From Cohesity "Recover"/"Recoveries", choose the physical server (and NOT the archive one) called "Protection Group Inscope-LCAD-DBS90"
# ( from lsatl00lcddbs90 ->  (Server OS Linux))
# Then, take the files from the paths:  
# "/lcad_temp_table_2/db2_backup3/LCAD_ATL.0.db2insta"
# "/lcad_temp_table_2/db2_backup4/LCAD_ATL.0.db2insta"

# Then, choose the target server as "lxatl00lcddbs36"
# and select the "Recover to" path as: "/backup_coh/backup2"

# Unselect "Overwrite Existing File/Folder" as: false

# Additional Options:
# - "Preserve file/folder attributes" as: true
# - "Continue recovery even if one of the Objects encounters an error" as: false

# "Cohesity network interface" as: "Auto Select"

# Finally, execute "Recover Files".

### Perform this with a WHILE loop (part 003 && part 004 should be as "................Done?"), until the process is finished, and then show the output of the process.
# Maybe, the status of the while should be taken from "Recovery task" (The API call to perform recovery should output the ID of the task, which can be used to check
# the status of the recovery task until it is completed), this one has the groups of PARTS that are being Recovered.

cmdGroup6 = [

  # # # ... files whose names contain the given pattern
  # # """find /home/mateo/cmon -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'"""
   
  # """find /lcad_temp_table_1/db2_backup -type f | awk -v pat="LCAD_ATL.0.db2insta" 'index($0, pat) > 0 {print}'""",
  # """find /lcad_temp_table_1/db2_backup2 -type f | awk -v pat="LCAD_ATL.0.db2insta" 'index($0, pat) > 0 {print}'"""
  
  ""
]


# while execute_bash_conditional("""find /home/mateo/cmon -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'""").__eq__("") \
# or execute_bash_conditional("""find /home/mateo/cmon2 -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'""").__eq__(""):
    
#   print("Recovery process has not begun yet.")
#   time.sleep(5)  # Wait for 5 seconds before checking again
      
# else:
#   while (execute_bash_conditional("""find /home/mateo/cmon -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'""").__contains__("__ch__") \
#   and execute_bash_conditional("""find /home/mateo/cmon -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'""").__contains__(".001") \
#   and execute_bash_conditional("""find /home/mateo/cmon -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'""").__contains__(".002")) \
#   or (execute_bash_conditional("""find /home/mateo/cmon2 -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'""").__contains__("__ch__") \
#   and execute_bash_conditional("""find /home/mateo/cmon2 -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'""").__contains__(".003") \
#   and execute_bash_conditional("""find /home/mateo/cmon2 -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}'""").__contains__(".004")):
    
#     print("There are __ch__ files, so the Recovery process is not finished yet.")
#     time.sleep(5)  # Wait for 5 seconds before checking again

#   else:
#     print("Recovery process...")
    

# print("                ... is finished!")








# Pre check of correct password before executing the commands


# if __name__ == "__main__":
#   # Generate log file name with date and hour
#   log_file = f"execution_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
#   # log_file = "execution_log.txt"
#   # # Remove old log if exists
#   # if os.path.exists(log_file):
#   #   os.remove(log_file)

#   # Open log file and redirect stdout and stderr
#   with open(log_file, "w") as f:
#     # Save original stdout/stderr
#     orig_stdout = sys.stdout
#     orig_stderr = sys.stderr
#     sys.stdout = f
#     sys.stderr = f
#     try:
#       # Example: execute all command groups in order
#       execute_multiple_bash_commands(cmdGroup1, 1)
#       execute_multiple_bash_commands(cmdGroup2, 2)
#       execute_multiple_bash_commands(cmdGroup3, 3)
#       execute_multiple_bash_commands(cmdGroup4, 4)
#       execute_multiple_bash_commands(cmdGroup5, 5)
#       execute_multiple_bash_commands(cmdGroup6, 6)
#     finally:
#       # Restore stdout/stderr
#       sys.stdout = orig_stdout
#       sys.stderr = orig_stderr
#   print(f"Execution finished. Logs saved to {log_file}")