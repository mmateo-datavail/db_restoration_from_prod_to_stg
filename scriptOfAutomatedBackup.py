import subprocess
from tqdm import tqdm

import json
import sys
import time
import logging
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError


### ---------------------------------------------
##Try installing first tqdm...
# python3 -m pip install tqdm

## If it doens't work, try to create a virtual environment and install tqdm there:
# python3 -m venv path/to/venv
# source path/to/venv/bin/activate
# python3 -m pip install tqdm

## Run the Python script:
# python3 testttt.py
## Just in case, run it with:
# sudo python3 testttt.py
## Or...
# sudo python3 -m testttt.py
### ---------------------------------------------

## PUT LATER...
## a list of Integers that put the 'steps' to be performed of the whole script
## e.g.: [1,2,3,4] as a list parameter of execute_bash_commands

def execute_bash_commands(commands, number_of_steps):
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
  

# Execute one shell command and show progress

def execute_bash_conditional(command):
  try:
    result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()
  except subprocess.CalledProcessError as e:
    return f"Error: {e.stderr.strip()}"


# List of bash commands to execute

### commands1 | Check that the DAILY backup of LCAD_ATL has been already completed, before beginning the restore process, checking Helios environment
# or just telling the user to wait for the email.

commands1 = [
  "echo 'Command 1: Listing files' && ls"
]

### cmdGroup1: Run Helios Protection backup script
# This for... "LSATLCOHCLUSTER01"
# Then, within Protection, take group name "Inscope-LCAD-DBS90", that's a pyhisical file, NOT a log file
# and "Run Now" the replication.

# It will replicate from Primary "LSATLCOHCLUSTER01" to a "Remote Cluster": "LSDENCOHCLUSTER01",
# making a "Retain for": "31 days",
# performing a "Backup all Objects in the Protection Group",
# with a "Backup Type": "Incremental", 
 
cmdGroup1 = [
  "echo 'Starting the Protection backup process...'",
  "echo 'Gathering Protection Group...'",
  # It should be "Inscope-LCAD-DBS90" in the Helios environment
  # The previous command is NOT needed, just for the first time, to check the Protection Group name
  """
curl --request POST \
--url https://helios.cohesity.com/v2/mcm/data-protect/protection-group/activity \
--header 'accept: application/json' \
--header 'apiKey: asd123' \
--header 'content-type: application/json'
  """
  ]

### cmdGroup2: Run Helios Recovery script
cmdGroup2 = [
  """
  curl -X POST \
--url 'https://helios.cohesity.com/v2/data-protect/recoveries' \
-H 'apiKey: apiKey'\
-H 'Accept: application/json'\
-H 'Content-type: application/json' \
--data-raw '{
  "name": "name6",
  "snapshotEnvironment": "kView"}'
  """
  ]

### cmdGroup3 (a.k.a.: "restore_part1.sh")
cmdGroup3 = [
  "echo 'Command 1: Listing files' && ls",

  ". /home/db2insta/sqllib/db2profile",
  "rm -rf /data/overflow/*",
  "rm -rf /data/active_logs/*",
  
  "readonly timestamp=$(date +'%F')",
  
  "date=`date +%y_%m_%d_%H:%M:%S`",
  
  "db2set DB2_OVERRIDE_BPF=100000",
  "db2stop force",
  "db2start",
  """echo "date is: $date" >> /tmp/${timestamp}_restore.log""",
  "db2 -tvf /home/db2insta/scripts/restore.ddl >> /tmp/${timestamp}_restore.log",
  """echo "date is: $date" >> /tmp/${timestamp}_restore.log""",
  """db2 "rollforward  db lcad_tr1 to end of backup and complete overflow log path ('/data/overflow/')" >> /tmp/${timestamp}_restore.log""",
  """echo "date is: $date" >> /tmp/${timestamp}_restore.log""",
  "db2 activate db lcad_tr1",
  "db2 -v connect to lcad_tr1",
  
  """if [ "$?" -ne 0 ]
  then
          #/usr/local/bin/sendEmail -f "db2insta@logisticare.com" -u "TR1 Restore failed" -t "rob@allbluesolutions.com" -s "mail.logisticare.com" -m "Go check what happen\
# ed"
          /usr/local/bin/sendEmail -f "Database.Engineering@modivcare.com" -u "TR1 Restore failed" -t "santosh.jaini@modivcare.com,victor.francis@modivcare.com,db2tier2@d\
atavail.com,incident-management-database-operations@logisticare-operations.pagerduty.com" -s "mail.logisticare.com" -m "Go check what happened" -a /tmp/${timestamp}_res\
tore.log
          #/usr/local/bin/sendEmail -f "Database.Engineering@modivcare.com" -u "TR1 Restore failed" -t "" -s "mail.logisticare.com" -m "LCAD_TR1 Restore has failed. Pleas\
# e attempt to re-run $0 on $(hostname)."
          #/usr/local/bin/sendEmail -f "db2insta@logisticare.com" -u "TR1 Restore failed" -t "support@allbluesolutions.com" -s "mail.logisticare.com" -m "Go check what ha\
# ppened"
          #/usr/local/bin/sendEmail -f "db2insta@logisticare.com" -u "TR1 Restore failed" -t "incident-management-database-operations@logisticare-operations.pagerduty.com\
# "  -s "mail.logisticare.com" -m "Go check what happened"
  
  else
          /usr/local/bin/sendEmail -f "Database.Engineering@modivcare.com" -u "TR1 Restore successful" -t "santosh.jaini@modivcare.com,victor.francis@modivcare.com,db2tie\
r2@datavail.com" -s "mail.logisticare.com" -m "TR1 restore completed successfully, please proceed with next steps" -a /tmp/${timestamp}_restore.log
  fi
  """
]


### cmdGroup4 (a.k.a.: "restore_part2.sh")
cmdGroup4 = [
  ". /home/db2insta/sqllib/db2profile",
  
  "readonly timestamp=$(date +'%F')",
  
  "date=`date +%y_%m_%d_%H:%M:%S`",
  
  """echo "date is: $date" >> /tmp/${timestamp}_restore.log""",
  "#db2 activate db lcad_tr1",
  "db2 -v connect to lcad_tr1 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL ALTSYSTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL BIGBP IMMEDIATE SIZE 20 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL HUGEBP IMMEDIATE SIZE 800 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL IBMDEFAULTBP IMMEDIATE SIZE 6000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL LARGEBP IMMEDIATE SIZE 900 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL LEGAUDITBP IMMEDIATE SIZE 500 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL AUDITBP IMMEDIATE SIZE 750 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL BIGROLODEXBP IMMEDIATE SIZE 2650 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL DAILYBP IMMEDIATE SIZE 20000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL DATALOGSBP IMMEDIATE SIZE 1500 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL GEOBASEBP IMMEDIATE SIZE 800 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL ROLODEXBP IMMEDIATE SIZE 3000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL CATALOGBP IMMEDIATE SIZE 60000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL TOOLSBP IMMEDIATE SIZE 5000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL TOOLSTEMPBP IMMEDIATE SIZE 5000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL TEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL USERTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL LARGETEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL LARGEUSERTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL BIGSYSTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL BIGTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL HUGESYSTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL HUGETEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL RIDERLOGBP IMMEDIATE SIZE 10000 >> /tmp/${timestamp}_restore.log",
  "db2 -v ALTER BUFFERPOOL TRIPLEGBP IMMEDIATE SIZE 50000 >> /tmp/${timestamp}_restore.log",
  "db2 -v disconnect all >> /tmp/${timestamp}_restore.log",
  
  "db2stop force",
  "db2set DB2_OVERRIDE_BPF=",
  "db2start",
  
  "# Reset bufferpool override",
  "#db2 -v activate database lcad_trg",
  "db2 -v activate database lcad_tr1",
  "db2 -v connect to lcad_tr1",
  
  """
  db2 -v "update production.call_center_system_configuration set (normal_database_alias,updated_by,updated_on,fax_output_directory,report_database_alias) = ('LCAD_TR1'\
,-5,production.udf_gmt(),'','LCAD_TR1') where normal_database_alias = 'LCAD_ATL'"
  """,
  
  """
  db2 -v "update production.call_Center_system_configuration set (fax_output_directory,updated_by,updated_on) = ('',-5,production.udf_gmt()) where normal_database_alias\
  <> current server"
  """,

  """
  db2 -v "update production.user set (status,group_code,updated_by,updated_on) = (1,0,-5,production.udf_gmt()) where code between -100 and -1 or code in (92824,120966,2\
4102,78989,55282,33964,38824,82643,57508,84681,59261,84781,59381,85503,85456,85564,85560,75097,87955,87954,87580,87579,85124,87559,96873,98911,98913,99603,101525,1015\
27,90093,89578,90361,102160,94206,87951,109950,109038,110763,24176,93687,108225,112474,41757,125749,87179)"
  """,
  
  "#db2 -v disconnect all",
  "#",
  "db2rbind LCAD_TR1 -l /tmp/${timestamp}_db2rbind.log all -r any",
  
  "#Added on jan 12 2017 to fix bind issue for bind",
  "db2 -v grant BINDADD on database to user devuser",
  "db2 -v GRANT DBADM ON DATABASE TO USER svcdbadm",
  
  """
  db2 "import from /home/db2insta/scripts/Davidhp_-42.ixf of ixf insert_update into production.user"
  """,
  
  "#",
  "/home/db2insta/scripts/reader_rights",
  "#",
  "/home/db2insta/scripts/grant_packages",
  
  "db2 -v connect to lcad_tr1",
  
  """
  if [ "$?" -ne 0 ]
  then
    #/usr/local/bin/sendEmail -f "db2insta@logisticare.com" -u "TR1 Restore failed" -t "rob@allbluesolutions.com" -s "mail.logisticare.com" -m "Go check what happened"
    /usr/local/bin/sendEmail -f "Database.Engineering@modivcare.com" -u "TR1 post Restore steps failed" -t "santosh.jaini@modivcare.com,victor.francis@modivcare.com,db2t\
ier2@datavail.com,incident-management-database-operations@logisticare-operations.pagerduty.com" -s "mail.logisticare.com" -m "Go check what happened" -a /tmp/${timestamp}\
_restore.log /tmp/${timestamp}_db2rbind.log
    #/usr/local/bin/sendEmail -f "Database.Engineering@modivcare.com" -u "TR1 Restore failed" -t "" -s "mail.logisticare.com" -m "LCAD_TR1 Restore has failed. Please attempt to re-run $0 on $(hostname)."
    #/usr/local/bin/sendEmail -f "db2insta@logisticare.com" -u "TR1 Restore failed" -t "support@allbluesolutions.com" -s "mail.logisticare.com" -m "Go check what happened"
    #/usr/local/bin/sendEmail -f "db2insta@logisticare.com" -u "TR1 Restore failed" -t "incident-management-database-operations@logisticare-operations.pagerduty.com"  -s "mail.logisticare.com" -m "Go check what happened"
  
  else
    /usr/local/bin/sendEmail -f "Database.Engineering@modivcare.com" -u "TR1 Post restore steps completed successfully. " -t "santosh.jaini@modivcare.com,victor.francis@m\
odivcare.com,db2tier2@datavail.com" -s "mail.logisticare.com" -m "TR1 Post restore steps completed successfully. " -a /tmp/${timestamp}_restore.log /tmp/${timestamp}_db2rbind.log
  
  fi
  """,
  
  """
  db2 -v "alter bufferpool BIGBP immediate size 1000"
  """,
  
  "db2 -tvf /home/db2insta/scripts/abs_monitoring/P_FIX_IDENTITY_COLUMNS.sql",
  
  """
  db2 "call PRODUCTION.FIX_IDENTITY_COLUMNS ()" ;
  """,
  
  """
  db2 -v "grant dbadm on database to user cpe_repl_tr1"
  """,
  
  """
  db2 -v "grant connect on database to user cpe_repl_uat"
  """,
  
  """
  db2 -v "grant select on table PRODUCTION.RIDER TO user cpe_repl_uat"
  """
]


# cmdGroup8 = [
#   "ls",
#   "sleep 2",
#   "pwd"
# ]
cmdGroup9 = [
  "echo 'Command 1: AAAAAAAAAA' && pwd",
  "echo 'Command 2: BBBBBBBBBB' && pwd",
  
  """
  temp_var="start"

  if [ "$temp_var" = "start" ]; then
  echo 'Starting the process...'

  elif [ "$temp_var" = "stop" ]; then
  echo 'Stopping the process...'

  elif [ "$temp_var" = "status" ]; then
  echo 'Checking the status...'

  else
    echo 'Usage: $0 {start|stop|status}'
    exit 1
  fi

  """
  
  # "echo 'Command 4: DDDDDDDDDD' && pwd"
]
testWord = "testWord"
homeVar = "$HOME"
concatenatedString = "echo 'Command 3: '"+homeVar+""
print("concatenatedString is:", concatenatedString, sep="")
cmdGroup10 = [
  "echo 'Command 1: AAAAAAAAAA'",
  "echo 'Command 2: "+testWord+"'",
  concatenatedString,
  "./rds_metadata_extractor.sh agverdict-staging-rds > $PWD/02_metadata_extraction_report.txt",
  
  "echo 'Metadata extraction report is: ...'",
  "cat $PWD/02_metadata_extraction_report.txt; echo '\n\n'",
]

cmdGroup11 = [ "echo 'Command 3: CCCCCCCCCC'"]

groupOfCommands = [cmdGroup10,cmdGroup11]

for i in range (len(groupOfCommands)):
  # for groupofCommands in groupOfCommands:
    execute_bash_commands(groupOfCommands[i], (1+i))
    
    
path_of_db_metadata = execute_bash_conditional("""export temp_var=$(tail -n 1 $PWD/02_metadata_extraction_report.txt); echo $temp_var""")
print("2nd temp_var (& path_of_db_metadata) is:", path_of_db_metadata, sep="")

# execute_bash_commands(cmdGroup2, 2)

print("Script finished...")

