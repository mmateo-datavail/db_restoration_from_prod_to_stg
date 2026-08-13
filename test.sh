
  . /home/db2insta/sqllib/db2profile
  
  readonly timestamp=$(date +'%F')
  
  date=`date +%y_%m_%d_%H:%M:%S`
  
  echo "date is: $date" >> /tmp/${timestamp}_restore.log
  #db2 activate db lcad_tr1
  db2 -v connect to lcad_tr1 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL ALTSYSTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL BIGBP IMMEDIATE SIZE 20 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL HUGEBP IMMEDIATE SIZE 800 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL IBMDEFAULTBP IMMEDIATE SIZE 6000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL LARGEBP IMMEDIATE SIZE 900 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL LEGAUDITBP IMMEDIATE SIZE 500 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL AUDITBP IMMEDIATE SIZE 750 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL BIGROLODEXBP IMMEDIATE SIZE 2650 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL DAILYBP IMMEDIATE SIZE 20000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL DATALOGSBP IMMEDIATE SIZE 1500 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL GEOBASEBP IMMEDIATE SIZE 800 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL ROLODEXBP IMMEDIATE SIZE 3000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL CATALOGBP IMMEDIATE SIZE 60000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL TOOLSBP IMMEDIATE SIZE 5000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL TOOLSTEMPBP IMMEDIATE SIZE 5000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL TEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL USERTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL LARGETEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL LARGEUSERTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL BIGSYSTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL BIGTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL HUGESYSTEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL HUGETEMPBP IMMEDIATE SIZE 1000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL RIDERLOGBP IMMEDIATE SIZE 10000 >> /tmp/${timestamp}_restore.log
  db2 -v ALTER BUFFERPOOL TRIPLEGBP IMMEDIATE SIZE 50000 >> /tmp/${timestamp}_restore.log
  db2 -v disconnect all >> /tmp/${timestamp}_restore.log
  
  db2stop force
  db2set DB2_OVERRIDE_BPF=
  db2start
  
  # Reset bufferpool override
  #db2 -v activate database lcad_trg
  db2 -v activate database lcad_tr1
  db2 -v connect to lcad_tr1
  db2 -v "update production.call_center_system_configuration set (normal_database_alias,updated_by,updated_on,fax_output_directory,report_database_alias) = ('LCAD_TR1'\
  ,-5,production.udf_gmt(),'','LCAD_TR1') where normal_database_alias = 'LCAD_ATL'"
  db2 -v "update production.call_Center_system_configuration set (fax_output_directory,updated_by,updated_on) = ('',-5,production.udf_gmt()) where normal_database_alias\
  <> current server"
  db2 -v "update production.user set (status,group_code,updated_by,updated_on) = (1,0,-5,production.udf_gmt()) where code between -100 and -1 or code in (92824,120966,2\
  4102,78989,55282,33964,38824,82643,57508,84681,59261,84781,59381,85503,85456,85564,85560,75097,87955,87954,87580,87579,85124,87559,96873,98911,98913,99603,101525,1015\
  27,90093,89578,90361,102160,94206,87951,109950,109038,110763,24176,93687,108225,112474,41757,125749,87179)"
  
  #db2 -v disconnect all
  #
  db2rbind LCAD_TR1 -l /tmp/${timestamp}_db2rbind.log all -r any
  
  #Added on jan 12 2017 to fix bind issue for bind
  db2 -v grant BINDADD on database to user devuser
  db2 -v GRANT DBADM ON DATABASE TO USER svcdbadm
  db2 "import from /home/db2insta/scripts/Davidhp_-42.ixf of ixf insert_update into production.user"
  #
  /home/db2insta/scripts/reader_rights
  #
  /home/db2insta/scripts/grant_packages
  
  db2 -v connect to lcad_tr1
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
  
  db2 -v "alter bufferpool BIGBP immediate size 1000"
  db2 -tvf /home/db2insta/scripts/abs_monitoring/P_FIX_IDENTITY_COLUMNS.sql
  db2 "call PRODUCTION.FIX_IDENTITY_COLUMNS ()" ;
  
  db2 -v "grant dbadm on database to user cpe_repl_tr1"
  db2 -v "grant connect on database to user cpe_repl_uat"
  db2 -v "grant select on table PRODUCTION.RIDER TO user cpe_repl_uat"


  # --- SSH Secure Connection Setup ---

  ### SERVER Side: (Run as root or with sudo)
  # 1. Ensure SSH server is installed and running
  sudo apt-get update
  sudo apt-get install -y openssh-server
  sudo systemctl enable ssh
  sudo systemctl start ssh

  # 2. (Optional) Harden SSH configuration
  sudo sed -i 's/^#Port 22/Port 22/' /etc/ssh/sshd_config
  sudo sed -i 's/^#PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
  sudo sed -i 's/^#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  sudo systemctl reload ssh


  ### CLIENT Side:
    # 1. Generate SSH key pair (if not already present)

  # if [ ! -f ~/.ssh/id_rsa ]; then
  #   ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa
  # fi

    # 2. Copy public key to server (replace user@server with actual values)
  # ssh-copy-id user@server

    # 3. Ensure the SSH controlmasters directory exists to avoid unix_listener errors and install sshpass
  # apt-get install sshpass
  # mkdir -p ~/.ssh/controlmasters
  # chmod 700 ~/.ssh/controlmasters

    # 4. Test SSH connection on CLIENT's side:
  # ssh user@server


  ### If it doesn't work, you can manually copy the public key on CLIENT's side:
  ### CLIENT Side:
    # 2. a) Display the public key
  # cat ~/.ssh/id_rsa.pub
    # 2. b.a) Copy the output and paste it into the SERVER's authorized_keys file

    # 2. b.b) Install sshpass and ensure the SSH controlmasters directory exists to avoid unix_listener errors and 
  # apt-get install sshpass
  # mkdir -p ~/.ssh/controlmasters
  # chmod 700 ~/.ssh/controlmasters

  ### SERVER Side:
  # sudo nano ~/.ssh/authorized_keys
    # 2. c) Ensure the permissions are set correctly
  # sudo chmod 700 ~/.ssh
  # sudo chmod 600 ~/.ssh/authorized_keys
    # 2. d) Activate parameters in /etc/ssh/sshd_config to make sure SSH works as expected:
  # sudo nano /etc/ssh/sshd_config
  #   - Ensure the following lines are set (uncommented):
      # Port 22
      # AddressFamily any
      # ListenAddress 0.0.0.0

      # PermitRootLogin yes
      # PubkeyAuthentication yes

      # PasswordAuthentication yes
      # ChallengeResponseAuthentication no

      # X11Forwarding yes

    # 2. e) Restart the SSH service
  # sudo systemctl reload ssh

    # 3. Test SSH connection on CLIENT's side:
  # ssh user@server

  # Note: For automation, you can use the following (replace variables as needed):
  # SERVER_USER="user"
  # SERVER_IP="server_ip_or_hostname"
  # ssh-copy-id ${SERVER_USER}@${SERVER_IP}
  # ssh ${SERVER_USER}@${SERVER_IP}


# _____________



# Example conditional script in Bash

  # temp_var="start"

  # if [ "$temp_var" = "start" ]; then
  # echo 'Starting the process...'
  # # echo "jeje\
  # # jeje"

  # elif [ "$temp_var" = "stop" ]; then
  # echo 'Stopping the process...'

  # elif [ "$temp_var" = "status" ]; then
  # echo 'Checking the status...'

  # else
  #   echo 'Usage: $0 {start|stop|status}'
  #   exit 1
  # fi

  # Delete files whose names contain the given pattern
  find /home/mateo/cmon -type f | awk -v pat="LCAD_ATL" 'index($0, pat) > 0 {print}' | xargs -r rm -f

  # Example: Connect to a random IP as "mateo" using sshpass to provide the password as a parameter
  # Replace RANDOM_IP and PASSWORD with actual values

  RANDOM_IP="192.0.2.123"
  PASSWORD="your_password_here"

  sshpass -p "$PASSWORD" ssh mateo@$RANDOM_IP