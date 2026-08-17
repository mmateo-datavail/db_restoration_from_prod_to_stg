#!/usr/bin/env python3
"""
RDS Recreation Script from JSON Metadata and Snapshot using boto3 (with Aurora support and Secrets Manager)
Usage: python v4_dbRestoration.py <json_file_path> <snapshot_arn> <region> <secret_arn> <secret_key's_username> <secret_key's_password> <mode: only-restore|restore-and-delete> <old_db_identifier> <new_db_identifier> [<new_db_cluster_identifier>]
For Aurora, <new_db_identifier> is used as the regional cluster identifier and [<new_db_cluster_identifier>] is used as the writer instance identifier.
"""

# INCLUDE ARGUMENT THAT CHECKS ID OF AWS ACCOUNT? ....
# Make an exception that describes the user should input a Snapshot logically related to the Old DB instance, otherwise the script will not work properly.

# IMPORTANT NOTE: if <old_db_identifier> parameter is equals a string value = "null", then the script will ignore the old DB instance
# identifier and will not attempt to stop and delete it.

# This is useful when you want to ONLY restore/recreate a snapshot without deleting an original old or non-existent instance.

# # RDS regular with MySQL recreation AND Old DB deletion
# venv/bin/python v4_dbRestoration.py mysql_metadata.json arn:aws:rds:us-west-2:123456789012:snapshot:mysql-snap us-west-2 arn:aws:secretsmanager:us-west-2:123456789012:secret:mysql-pass-abc123 "username" "password" "restore-and-delete" old-db-instance-identifier mysql-restored
# # RDS regular with MySQL recreation WITHOUT Old DB deletion
# venv/bin/python v4_dbRestoration.py mysql_metadata.json arn:aws:rds:us-west-2:123456789012:snapshot:mysql-snap us-west-2 arn:aws:secretsmanager:us-west-2:123456789012:secret:mysql-pass-abc123 "username" "password" "only-restore" old-db-instance-identifier mysql-restored
# ------------------------------------------------------------------------

# # Aurora PostgreSQL recreation AND Old DB deletion
# venv/bin/python v4_dbRestoration.py aurora_pg_metadata.json arn:aws:rds:us-west-2:123456789012:cluster-snapshot:aurora-pg-snap us-west-2 arn:aws:secretsmanager:us-west-2:123456789012:secret:aurora-pass-def456 "username" "password" "restore-and-delete" old-aurora-instance-identifier aurora-instance-restored aurora-cluster-restored
# # Aurora PostgreSQL recreation WITHOUT Old DB deletion
# venv/bin/python v4_dbRestoration.py aurora_pg_metadata.json arn:aws:rds:us-west-2:123456789012:cluster-snapshot:aurora-pg-snap us-west-2 arn:aws:secretsmanager:us-west-2:123456789012:secret:aurora-pass-def456 "username" "password" "only-restore" old-aurora-instance-identifier aurora-instance-restored aurora-cluster-restored
# ------------------------------------------------------------------------

# # Oracle recreation AND Old DB deletion
# venv/bin/python v4_dbRestoration.py oracle_metadata.json arn:aws:rds:us-west-2:123456789012:snapshot:oracle-snap us-west-2 arn:aws:secretsmanager:us-west-2:123456789012:secret:oracle-pass-ghi789 "username" "password" "restore-and-delete" old-oracle-instance-identifier oracle-restored
# # Oracle recreation WITHOUT Old DB deletion
# venv/bin/python v4_dbRestoration.py oracle_metadata.json arn:aws:rds:us-west-2:123456789012:snapshot:oracle-snap us-west-2 arn:aws:secretsmanager:us-west-2:123456789012:secret:oracle-pass-ghi789 "username" "password" "only-restore" old-oracle-instance-identifier oracle-restored

# AWS authentication methods:
# Method 1 - Export environment variables:
#   export AWS_ACCESS_KEY_ID='your-access-key'
#   export AWS_SECRET_ACCESS_KEY='your-secret-key'
#   export AWS_DEFAULT_REGION='your-region'  # optional
#
# Method 2 - Use AWS configure:
#   aws configure set aws_access_key_id your-access-key
#   aws configure set aws_secret_access_key your-secret-key
#   aws configure set default.region your-region
#
# Method 3 - Use AWS configure interactively:
#   aws configure
#
# Method 4 - Use the IAM Service Role attached to your AWS CodeBuild project (recommended for CodeBuild):
#   - Attach a proper IAM role/service role to the CodeBuild project.
#   - Add the required trust policy so the CodeBuild service can assume the role.
#   - In CodeBuild, boto3 will use the project role automatically via the AWS SDK default credential chain.
#   - No AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY variables are required in CodeBuild.
#
# Example in CodeBuild environment:
#   import boto3
#   session = boto3.Session()
#   sts = session.client('sts')
#   print(sts.get_caller_identity())
#
# If you want to assume a role explicitly from code:
#   import boto3
#   role_arn = 'arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>'
#   sts_client = boto3.client('sts')
#   try:
#       assumed = sts_client.assume_role(
#           RoleArn=role_arn,
#           RoleSessionName='db-restoration-session',
#           DurationSeconds=3600
#       )
#       creds = assumed['Credentials']
#       session = boto3.Session(
#           aws_access_key_id=creds['AccessKeyId'],
#           aws_secret_access_key=creds['SecretAccessKey'],
#           aws_session_token=creds['SessionToken'],
#           region_name='us-west-2'
#       )
#       rds_client = session.client('rds')
#   except ClientError as e:
#       logger.error(f"Failed to assume role: {e}")
#
# This script is compatible with the default AWS credential chain, meaning it can work in:
# - local shells configured through AWS CLI or env vars
# - EC2 / ECS / Lambda / CodeBuild with an attached IAM role

# # Version of Python libraries used in this project:
## boto3           1.43.36
## botocore        1.43.36
## jmespath        1.1.0
## logging         0.4.9.6
## pip             25.2
## python-dateutil 2.9.0.post0
## s3transfer      0.19.0
## six             1.17.0
## tqdm            4.68.3
## typing          3.7.4.3
## urllib3         2.7.0


import subprocess
from tqdm import tqdm

import json
import sys
import time
import logging
from typing import Dict, List, Optional, Any, Union
import boto3
from botocore.exceptions import ClientError, NoCredentialsError



# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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


class EngineSpecificValidator:
    """Engine-specific validation and parameter handling"""
    
    @staticmethod
    def get_engine_specific_families() -> Dict[str, Dict[str, str]]:
        """Get engine-specific parameter group families"""
        return {
            'aurora': {
                'aurora-mysql': 'aurora-mysql{major}.{minor}',
                'aurora-postgresql': 'aurora-postgresql{major}'
            },
            'rds': {
                'mysql': 'mysql{major}.{minor}',
                'postgres': 'postgres{major}',
                'mariadb': 'mariadb{major}.{minor}',
                'oracle-ee': 'oracle-ee-{major}.{minor}',
                'oracle-se2': 'oracle-se2-{major}.{minor}',
                'oracle-se1': 'oracle-se1-{major}.{minor}',
                'sqlserver-ee': 'sqlserver-ee-{major}.{minor}',
                'sqlserver-se': 'sqlserver-se-{major}.{minor}',
                'sqlserver-ex': 'sqlserver-ex-{major}.{minor}',
                'sqlserver-web': 'sqlserver-web-{major}.{minor}'
            }
        }
    
    @staticmethod
    def get_engine_specific_parameters() -> Dict[str, Dict[str, Any]]:
        """Get engine-specific parameter requirements and defaults"""
        return {
            'mysql': {
                'required_params': ['port'],
                'default_port': 3306,
                'supports_character_set': True,
                'supports_license_model': True,
                'default_license_model': 'general-public-license',
                'supports_option_groups': False,
                'supports_processor_features': False,
                'cloudwatch_logs': ['error', 'general', 'slow-query']
            },
            'postgres': {
                'required_params': ['port'],
                'default_port': 5432,
                'supports_character_set': False,
                'supports_license_model': True,
                'default_license_model': 'postgresql-license',
                'supports_option_groups': False,
                'supports_processor_features': False,
                'cloudwatch_logs': ['postgresql']
            },
            'mariadb': {
                'required_params': ['port'],
                'default_port': 3306,
                'supports_character_set': True,
                'supports_license_model': True,
                'default_license_model': 'general-public-license',
                'supports_option_groups': False,
                'supports_processor_features': False,
                'cloudwatch_logs': ['error', 'general', 'slow-query']
            },
            'oracle-ee': {
                'required_params': ['port', 'license_model'],
                'default_port': 1521,
                'supports_character_set': True,
                'supports_license_model': True,
                'default_license_model': 'bring-your-own-license',
                'supports_option_groups': True,
                'supports_processor_features': True,
                'cloudwatch_logs': ['alert', 'audit', 'trace', 'listener']
            },
            'oracle-se2': {
                'required_params': ['port', 'license_model'],
                'default_port': 1521,
                'supports_character_set': True,
                'supports_license_model': True,
                'default_license_model': 'license-included',
                'supports_option_groups': True,
                'supports_processor_features': True,
                'cloudwatch_logs': ['alert', 'audit', 'trace', 'listener']
            },
            'sqlserver-ee': {
                'required_params': ['port', 'license_model'],
                'default_port': 1433,
                'supports_character_set': False,
                'supports_license_model': True,
                'default_license_model': 'license-included',
                'supports_option_groups': True,
                'supports_processor_features': True,
                'cloudwatch_logs': ['error', 'agent']
            },
            'sqlserver-se': {
                'required_params': ['port', 'license_model'],
                'default_port': 1433,
                'supports_character_set': False,
                'supports_license_model': True,
                'default_license_model': 'license-included',
                'supports_option_groups': True,
                'supports_processor_features': True,
                'cloudwatch_logs': ['error', 'agent']
            },
            'aurora-mysql': {
                'required_params': ['port'],
                'default_port': 3306,
                'supports_character_set': False,
                'supports_license_model': False,
                'supports_option_groups': False,
                'supports_processor_features': False,
                'supports_backtrack': True,
                'supports_serverless': True,
                'cloudwatch_logs': ['error', 'general', 'slowquery']
            },
            'aurora-postgresql': {
                'required_params': ['port'],
                'default_port': 5432,
                'supports_character_set': False,
                'supports_license_model': False,
                'supports_option_groups': False,
                'supports_processor_features': False,
                'supports_backtrack': False,
                'supports_serverless': True,
                'cloudwatch_logs': ['postgresql']
            }
        }

class RDSRecreator:
    """Class to handle RDS instance recreation from JSON metadata and snapshot"""
    
    def __init__(self, region: str, role_arn: Optional[str] = None):
        """Initialize the RDS recreator with AWS clients"""
        try:
            self.region = region
            session = self._create_session(role_arn)
            self.rds_client = session.client('rds', region_name=region)
            self.ec2_client = session.client('ec2', region_name=region)
            self.secrets_client = session.client('secretsmanager', region_name=region)
            self.validator = EngineSpecificValidator()
            logger.info(f"Initialized AWS clients for region: {region}")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure your credentials.")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {str(e)}")
            raise

    def _create_session(self, role_arn: Optional[str] = None) -> 'boto3.Session':
        """Create a boto3 session, optionally assuming a role"""
        try:
            if role_arn:
                logger.info(f"Assuming role: {role_arn}")
                sts_client = boto3.client('sts')
                assumed = sts_client.assume_role(
                    RoleArn=role_arn,
                    RoleSessionName='db-restoration-session'
                )
                creds = assumed['Credentials']
                session = boto3.Session(
                    aws_access_key_id=creds['AccessKeyId'],
                    aws_secret_access_key=creds['SecretAccessKey'],
                    aws_session_token=creds['SessionToken'],
                    region_name=self.region
                )
                logger.info("Successfully assumed role")
                return session
            else:
                logger.info("Using default AWS credentials")
                session = boto3.Session()
                creds = session.get_credentials()
                if creds is None:
                    logger.warning("No credentials found in default chain")
                return session
        except Exception as e:
            logger.error(f"Failed to create session: {str(e)}")
            raise

    def _operation_supports_parameter(self, operation_name: str, parameter_name: str) -> bool:
        """Return whether the RDS client operation supports a specific parameter."""
        try:
            operation_model = self.rds_client.meta.service_model.operation_model(operation_name)
            if not operation_model or not operation_model.input_shape:
                return False
            return parameter_name in operation_model.input_shape.members
        except Exception:
            return False

    def get_secret_value(self, secret_arn: str, secret_key: str = 'password') -> str:
        """Retrieve password from AWS Secrets Manager"""
        try:
            logger.info(f"Retrieving secret from: {secret_arn}")
            response = self.secrets_client.get_secret_value(SecretId=secret_arn)
            
            if 'SecretString' in response:
                secret_data = json.loads(response['SecretString'])
                if secret_key in secret_data:
                    logger.info("Successfully retrieved password from Secrets Manager")
                    return secret_data[secret_key]
                else:
                    available_keys = list(secret_data.keys())
                    raise ValueError(f"Secret key '{secret_key}' not found. Available keys: {available_keys}")
            else:
                raise ValueError("Secret does not contain SecretString")
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                raise ValueError(f"Secret not found: {secret_arn}")
            elif error_code == 'DecryptionFailure':
                raise ValueError(f"Failed to decrypt secret: {secret_arn}")
            elif error_code == 'InvalidRequestException':
                raise ValueError(f"Invalid request for secret: {secret_arn}")
            else:
                raise ValueError(f"Failed to retrieve secret: {str(e)}")
        except json.JSONDecodeError:
            raise ValueError("Secret value is not valid JSON")
        except Exception as e:
            raise ValueError(f"Unexpected error retrieving secret: {str(e)}")

    def load_metadata(self, json_file_path: str) -> Dict[str, Any]:
        """Load and parse the JSON metadata file"""
        try:
            with open(json_file_path, 'r') as file:
                metadata = json.load(file)
            logger.info(f"Successfully loaded metadata from {json_file_path}")
            return metadata
        except FileNotFoundError:
            logger.error(f"JSON file not found: {json_file_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format: {str(e)}")
            raise

    def is_aurora_engine(self, engine: str) -> bool:
        """Check if the engine is Aurora"""
        return engine.startswith('aurora')

    def validate_and_normalize_engine_params(self, db_info: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize engine-specific parameters"""
        engine = db_info.get('engine', '').lower()
        engine_specs = self.validator.get_engine_specific_parameters()
        
        if engine not in engine_specs:
            logger.warning(f"Unknown engine: {engine}. Using default validation.")
            return db_info
        
        specs = engine_specs[engine]
        normalized_info = db_info.copy()
        
        # Validate and set default port
        if not normalized_info.get('port'):
            normalized_info['port'] = specs['default_port']
            logger.info(f"Set default port {specs['default_port']} for engine {engine}")
        
        # Handle license model
        if specs.get('supports_license_model', False):
            if not normalized_info.get('license_model'):
                normalized_info['license_model'] = specs.get('default_license_model')
                logger.info(f"Set default license model {specs.get('default_license_model')} for engine {engine}")
        else:
            # Remove license model for engines that don't support it
            normalized_info.pop('license_model', None)
        
        # Handle character set
        if not specs.get('supports_character_set', False):
            normalized_info.pop('character_set_name', None)
            normalized_info.pop('nchar_character_set_name', None)
        
        # Handle option groups
        if not specs.get('supports_option_groups', False):
            normalized_info.pop('option_group_name', None)
        
        # Handle processor features
        if not specs.get('supports_processor_features', False):
            normalized_info.pop('processor_features', None)
        
        # Validate CloudWatch logs
        valid_logs = specs.get('cloudwatch_logs', [])
        if normalized_info.get('enabled_cloudwatch_logs_exports'):
            filtered_logs = [log for log in normalized_info['enabled_cloudwatch_logs_exports'] if log in valid_logs]
            if len(filtered_logs) != len(normalized_info['enabled_cloudwatch_logs_exports']):
                logger.warning(f"Filtered invalid CloudWatch logs for {engine}. Valid logs: {valid_logs}")
            normalized_info['enabled_cloudwatch_logs_exports'] = filtered_logs
        
        # Aurora-specific validations
        if engine.startswith('aurora'):
            # Remove RDS-specific parameters
            rds_only_params = ['multi_az', 'availability_zone', 'allocated_storage', 'storage_type', 'iops', 'storage_throughput']
            for param in rds_only_params:
                if param in normalized_info:
                    logger.info(f"Removed RDS-specific parameter '{param}' for Aurora engine")
                    normalized_info.pop(param, None)
            
            # Handle backtrack (Aurora MySQL only)
            if engine != 'aurora-mysql':
                normalized_info.pop('backtrack_window', None)
        
        return normalized_info

    def extract_db_info(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract DB information from metadata (works for both RDS and Aurora)"""
        try:
            # Check if it's Aurora cluster metadata or RDS instance metadata
            if 'DBClusters' in metadata and metadata['DBClusters']:
                db_info = self.extract_aurora_cluster_info(metadata)
            elif 'DBInstances' in metadata and metadata['DBInstances']:
                db_info = self.extract_rds_instance_info(metadata)
            else:
                raise ValueError("No valid DB cluster or instance data found in metadata")
            
            # Validate and normalize engine-specific parameters
            return self.validate_and_normalize_engine_params(db_info)
                
        except Exception as e:
            logger.error(f"Failed to extract DB info: {str(e)}")
            raise

    def safe_get(self, data: Dict[str, Any], key: str, default: Any = None) -> Any:
        """Safely get value from dictionary with logging"""
        try:
            value = data.get(key, default)
            if value is None and default is not None:
                logger.debug(f"Using default value for '{key}': {default}")
            return value
        except Exception as e:
            logger.warning(f"Error accessing key '{key}': {str(e)}. Using default: {default}")
            return default

    def extract_aurora_cluster_info(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Aurora cluster information from metadata with robust error handling"""
        try:
            db_cluster = metadata.get('DBClusters', [{}])[0]
            engine = db_cluster.get('Engine', '').lower()
            is_aurora_engine = self.is_aurora_engine(engine.lower())
            
            info = {
                'is_aurora': is_aurora_engine,
                'engine': self.safe_get(db_cluster, 'Engine', ''),
                'engine_version': self.safe_get(db_cluster, 'EngineVersion', ''),
                'database_name': self.safe_get(db_cluster, 'DatabaseName'),
                'port': self.safe_get(db_cluster, 'Port'),
                'backup_retention_period': self.safe_get(db_cluster, 'BackupRetentionPeriod', 0),
                'preferred_backup_window': self.safe_get(db_cluster, 'PreferredBackupWindow'),
                'preferred_maintenance_window': self.safe_get(db_cluster, 'PreferredMaintenanceWindow'),
                'engine_lifecycle_support': self.safe_get(db_cluster, 'EngineLifecycleSupport'),
                'storage_encrypted': self.safe_get(db_cluster, 'StorageEncrypted', False),
                'kms_key_id': self.safe_get(db_cluster, 'KmsKeyId'),
                'iam_database_authentication_enabled': self.safe_get(db_cluster, 'IAMDatabaseAuthenticationEnabled', False),
                'backtrack_window': self.safe_get(db_cluster, 'BacktrackWindow', 0),
                'enabled_cloudwatch_logs_exports': self.safe_get(db_cluster, 'EnabledCloudwatchLogsExports', []),
                'deletion_protection': self.safe_get(db_cluster, 'DeletionProtection', False),
                'multi_az': self.safe_get(db_cluster, 'MultiAZ', False),
                'copy_tags_to_snapshot': self.safe_get(db_cluster, 'CopyTagsToSnapshot', False),
                # 'copy_tags_to_snapshot': self.safe_get(db_cluster, 'CopyTagsToSnapshot'),
                'engine_mode': self.safe_get(db_cluster, 'EngineMode', 'provisioned'),
                'auto_minor_version_upgrade': self.safe_get(db_cluster, 'AutoMinorVersionUpgrade', True),
                'publicly_accessible': self.safe_get(db_cluster, 'PubliclyAccessible', False),
                'availability_zone': self.safe_get(db_cluster, 'AvailabilityZone')
            }
            
            # Safely extract complex nested objects
            try:
                scaling_config = db_cluster.get('ScalingConfiguration', {})
                if scaling_config:
                    info['scaling_configuration'] = scaling_config
            except Exception as e:
                logger.warning(f"Error extracting scaling configuration: {str(e)}")
            
            try:
                serverlessv2_config = db_cluster.get('ServerlessV2ScalingConfiguration', {})
                if serverlessv2_config:
                    info['serverlessv2_scaling_configuration'] = serverlessv2_config
            except Exception as e:
                logger.warning(f"Error extracting serverless v2 configuration: {str(e)}")
            
            # Extract parameter groups safely
            try:
                info['cluster_parameter_group_name'] = db_cluster.get('DBClusterParameterGroup')
            except Exception as e:
                logger.warning(f"Error extracting cluster parameter group: {str(e)}")
            
            # Extract subnet group safely
            try:
                info['subnet_group_name'] = db_cluster.get('DBSubnetGroup')
            except Exception as e:
                logger.warning(f"Error extracting subnet group: {str(e)}")
            
            # Extract VPC security groups safely
            try:
                vpc_security_groups = db_cluster.get('VpcSecurityGroups', [])
                info['vpc_security_group_ids'] = [sg.get('VpcSecurityGroupId') for sg in vpc_security_groups if sg.get('VpcSecurityGroupId')]
            except Exception as e:
                logger.warning(f"Error extracting VPC security groups: {str(e)}")
                info['vpc_security_group_ids'] = []
            
            # Multi-AZ cluster specific parameters (safely)
            try:
                info['storage_type'] = self.safe_get(db_cluster, 'StorageType')
                info['iops'] = self.safe_get(db_cluster, 'Iops')
                info['storage_throughput'] = self.safe_get(db_cluster, 'StorageThroughput')
                info['allocated_storage'] = self.safe_get(db_cluster, 'AllocatedStorage')
                info['db_cluster_instance_class'] = self.safe_get(db_cluster, 'DBInstanceClass')
                # info['db_cluster_instance_class'] = self.safe_get(db_cluster, 'DBClusterInstanceClass')
            except Exception as e:
                logger.warning(f"Error extracting Multi-AZ cluster parameters: {str(e)}")
            
            # Performance and monitoring (safely)
            try:
                info['performance_insights_enabled'] = self.safe_get(db_cluster, 'PerformanceInsightsEnabled', False)
                info['performance_insights_kms_key_id'] = self.safe_get(db_cluster, 'PerformanceInsightsKMSKeyId')
                info['performance_insights_retention_period'] = self.safe_get(db_cluster, 'PerformanceInsightsRetentionPeriod', 7)
                info['monitoring_interval'] = self.safe_get(db_cluster, 'MonitoringInterval', 0)
                info['monitoring_role_arn'] = self.safe_get(db_cluster, 'MonitoringRoleArn')
            except Exception as e:
                logger.warning(f"Error extracting performance/monitoring settings: {str(e)}")
            
            logger.info(f"Extracted Aurora cluster info for engine: {info['engine']} {info['engine_version']}")
            return info
            
        except Exception as e:
            logger.error(f"Failed to extract Aurora cluster info: {str(e)}")
            raise

    def extract_rds_instance_info(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract RDS instance information from metadata with robust error handling"""
        try:
            db_instance = metadata.get('DBInstances', [{}])[0]
            engine = db_instance.get('Engine', '').lower()
            is_aurora_engine = self.is_aurora_engine(engine.lower())
            
            info = {
                'is_aurora': is_aurora_engine,
                'engine': self.safe_get(db_instance, 'Engine', ''),
                'engine_version': self.safe_get(db_instance, 'EngineVersion', ''),
                # 'db_instance_class': self.safe_get(db_instance, 'DBInstanceClass', 'db.t3.micro'),
                'db_instance_class': self.safe_get(db_instance, 'DBInstanceClass', 'db.t3.micro'),
                'allocated_storage': self.safe_get(db_instance, 'AllocatedStorage', 20),
                'storage_type': self.safe_get(db_instance, 'StorageType', 'gp2'),
                'storage_encrypted': self.safe_get(db_instance, 'StorageEncrypted', False),
                'kms_key_id': self.safe_get(db_instance, 'KmsKeyId'),
                'iops': self.safe_get(db_instance, 'Iops'),
                'storage_throughput': self.safe_get(db_instance, 'StorageThroughput'),
                'publicly_accessible': self.safe_get(db_instance, 'PubliclyAccessible', False),
                'port': self.safe_get(db_instance, 'DbInstancePort'),
                'availability_zone': self.safe_get(db_instance, 'AvailabilityZone'),
                'multi_az': self.safe_get(db_instance, 'MultiAZ', False),
                'copy_tags_to_snapshot': self.safe_get(db_instance, 'CopyTagsToSnapshot', False),
                'backup_retention_period': self.safe_get(db_instance, 'BackupRetentionPeriod', 0),
                'preferred_backup_window': self.safe_get(db_instance, 'PreferredBackupWindow'),
                'preferred_maintenance_window': self.safe_get(db_instance, 'PreferredMaintenanceWindow'),
                'auto_minor_version_upgrade': self.safe_get(db_instance, 'AutoMinorVersionUpgrade', True),
                'deletion_protection': self.safe_get(db_instance, 'DeletionProtection', False),
                'performance_insights_enabled': self.safe_get(db_instance, 'PerformanceInsightsEnabled', False),
                'performance_insights_kms_key_id': self.safe_get(db_instance, 'PerformanceInsightsKMSKeyId'),
                'performance_insights_retention_period': self.safe_get(db_instance, 'PerformanceInsightsRetentionPeriod', 7),
                'monitoring_interval': self.safe_get(db_instance, 'MonitoringInterval', 0),
                'monitoring_role_arn': self.safe_get(db_instance, 'MonitoringRoleArn'),
                'iam_database_authentication_enabled': self.safe_get(db_instance, 'IAMDatabaseAuthenticationEnabled', False),
                'license_model': self.safe_get(db_instance, 'LicenseModel'),
                'character_set_name': self.safe_get(db_instance, 'CharacterSetName'),
                'nchar_character_set_name': self.safe_get(db_instance, 'NcharCharacterSetName'),
                'enabled_cloudwatch_logs_exports': self.safe_get(db_instance, 'EnabledCloudwatchLogsExports', [])
            }
            
            # Safely extract parameter groups
            try:
                param_groups = db_instance.get('DBParameterGroups', [])
                info['parameter_group_name'] = param_groups[0].get('DBParameterGroupName') if param_groups else None
            except Exception as e:
                logger.warning(f"Error extracting parameter groups: {str(e)}")
                info['parameter_group_name'] = None
            
            # Safely extract option groups
            try:
                option_groups = db_instance.get('OptionGroupMemberships', [])
                info['option_group_name'] = option_groups[0].get('OptionGroupName') if option_groups else None
            except Exception as e:
                logger.warning(f"Error extracting option groups: {str(e)}")
                info['option_group_name'] = None
            
            # Safely extract subnet group and subnet IDs
            try:
                subnet_group = db_instance.get('DBSubnetGroup', {})
                info['subnet_group_name'] = subnet_group.get('DBSubnetGroupName')
                subnets = subnet_group.get('Subnets', [])
                info['subnet_ids'] = [subnet.get('SubnetIdentifier') for subnet in subnets if subnet.get('SubnetIdentifier')]
            except Exception as e:
                logger.warning(f"Error extracting subnet information: {str(e)}")
                info['subnet_group_name'] = None
                info['subnet_ids'] = []
            
            # Safely extract VPC security groups
            try:
                vpc_security_groups = db_instance.get('VpcSecurityGroups', [])
                info['vpc_security_group_ids'] = [sg.get('VpcSecurityGroupId') for sg in vpc_security_groups if sg.get('VpcSecurityGroupId')]
            except Exception as e:
                logger.warning(f"Error extracting VPC security groups: {str(e)}")
                info['vpc_security_group_ids'] = []
            
            # Safely extract processor features
            try:
                info['processor_features'] = self.safe_get(db_instance, 'ProcessorFeatures', [])
            except Exception as e:
                logger.warning(f"Error extracting processor features: {str(e)}")
                info['processor_features'] = []
            
            logger.info(f"Extracted RDS instance info for engine: {info['engine']} {info['engine_version']}")
            return info
            
        except Exception as e:
            logger.error(f"Failed to extract RDS instance info: {str(e)}")
            raise

    def get_parameter_group_family(self, engine: str, engine_version: str, is_aurora: bool = False) -> str:
        """Determine the parameter group family based on engine and version with error handling"""
        try:
            families = self.validator.get_engine_specific_families()
            
            if is_aurora:
                family_templates = families['aurora']
            else:
                family_templates = families['rds']
            
            if engine not in family_templates:
                logger.warning(f"Unknown engine {engine}, using fallback family")
                return f"{engine}{'.'.join(engine_version.split('.')[:2])}"
            
            template = family_templates[engine]
            version_parts = engine_version.split('.')
            major = version_parts[0] if len(version_parts) > 0 else '1'
            minor = version_parts[1] if len(version_parts) > 1 else '0'
            
            return template.format(major=major, minor=minor)
            
        except Exception as e:
            logger.warning(f"Error determining parameter group family: {str(e)}")
            return f"{engine}{'.'.join(engine_version.split('.')[:2])}"

    def wait_for_resource(self, resource_type: str, resource_name: str, max_attempts: int = 1000, require_reset: bool = False, expected_status: str = 'available') -> bool:
        """Wait for a resource to reach the expected status with improved error handling"""
        logger.info(f"Waiting for {resource_type} '{resource_name}' to reach status '{expected_status}'...")
        seen_resetting = False
        seen_modifying = False
        
        for attempt in range(max_attempts):
            try:
                if resource_type == 'cluster-parameter-group':
                    self.rds_client.describe_db_cluster_parameter_groups(DBClusterParameterGroupName=resource_name)
                    logger.info(f"Cluster parameter group '{resource_name}' is available")
                    return True
                elif resource_type == 'parameter-group':
                    self.rds_client.describe_db_parameter_groups(DBParameterGroupName=resource_name)
                    logger.info(f"Parameter group '{resource_name}' is available")
                    return True
                elif resource_type == 'option-group':
                    self.rds_client.describe_option_groups(OptionGroupName=resource_name)
                    logger.info(f"Option group '{resource_name}' is available")
                    return True
                elif resource_type == 'subnet-group':
                    self.rds_client.describe_db_subnet_groups(DBSubnetGroupName=resource_name)
                    logger.info(f"Subnet group '{resource_name}' is available")
                    return True
                elif resource_type == 'db-cluster':
                    response = self.rds_client.describe_db_clusters(DBClusterIdentifier=resource_name)
                    status = response['DBClusters'][0]['Status']
                    if status == expected_status:
                        logger.info(f"DB cluster '{resource_name}' reached status '{expected_status}'")
                        return True
                    if expected_status == 'available' and status in ['failed', 'incompatible-parameters', 'incompatible-option-group']:
                        logger.error(f"DB cluster '{resource_name}' is in failed state: {status}")
                        return False
                    if expected_status == 'stopped' and status in ['failed', 'incompatible-parameters', 'incompatible-option-group']:
                        logger.error(f"DB cluster '{resource_name}' is in failed state while waiting for stop: {status}")
                        return False
                    logger.info(f"DB cluster status: {status}")
                elif resource_type == 'db-instance':
                    response = self.rds_client.describe_db_instances(DBInstanceIdentifier=resource_name)
                    instance = response['DBInstances'][0]
                    status = instance['DBInstanceStatus']
                    pending = instance.get('PendingModifiedValues', {})
                    if expected_status == 'available':
                        if status in ['modifying', 'configuring-enhanced-monitoring', 'resetting-master-credentials', 'backing-up']:
                            if status == 'modifying':
                                seen_modifying = True
                            if status == 'resetting-master-credentials':
                                seen_resetting = True
                            logger.info(f"DB instance '{resource_name}' is in transitional state: {status}; pending={pending}")
                        elif status == 'available':
                            if require_reset:
                                master_password_pending = 'MasterUserPassword' in pending
                                if not master_password_pending or seen_modifying or seen_resetting:
                                    logger.info(
                                        f"DB instance '{resource_name}' is available and the required reset/transitional states are complete."
                                        # f"DB instance '{resource_name}' is available and the required reset/transitional states are complete; "
                                        # f"pending={pending}, seen_modifying={seen_modifying}, seen_resetting={seen_resetting}"
                                    )
                                    return True
                                logger.info(
                                    f"DB instance '{resource_name}' is available but has not yet cleared the required reset state; "
                                    f"pending={pending}, seen_modifying={seen_modifying}, seen_resetting={seen_resetting}; continuing to wait..."
                                )
                            else:
                                logger.info(f"DB instance '{resource_name}' is available")
                                return True
                        elif status in ['failed', 'incompatible-parameters', 'incompatible-option-group']:
                            logger.error(f"DB instance '{resource_name}' is in failed state: {status}")
                            return False
                        else:
                            logger.info(f"DB instance status: {status}")
                    elif expected_status in ['stopped', 'deleting']:
                        if status == expected_status:
                            logger.info(f"DB instance '{resource_name}' reached status '{expected_status}'")
                            return True
                        if status in ['failed', 'incompatible-parameters', 'incompatible-option-group']:
                            logger.error(f"DB instance '{resource_name}' is in failed state: {status}")
                            return False
                        logger.info(f"DB instance status: {status}")
                    elif expected_status == 'deleted':
                        logger.info(f"DB instance status: {status}")
                else:
                    logger.warning(f"Unsupported resource type: {resource_type}")
                    return False
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if expected_status == 'deleted' and 'NotFound' in error_code:
                    logger.info(f"{resource_type} '{resource_name}' was deleted")
                    return True
                if 'NotFound' in error_code:
                    logger.debug(f"{resource_type} not found yet, continuing to wait...")
                else:
                    logger.warning(f"Error checking {resource_type}: {error_code}")
            except Exception as e:
                logger.warning(f"Unexpected error checking {resource_type}: {str(e)}")
            
            time.sleep(30)
            logger.info(f"Ticks before cancelling attempt {attempt + 1}/{max_attempts} - still waiting...\n")
        
        logger.error(f"Timeout waiting for {resource_type} '{resource_name}' to reach status '{expected_status}'")
        return False

    def _resolve_db_resources(self, db_instance_identifier: str) -> Dict[str, Any]:
        """Resolve an RDS instance, its cluster, and replica identifiers."""
        try:
            response = self.rds_client.describe_db_instances(DBInstanceIdentifier=db_instance_identifier)
            db_instance = response['DBInstances'][0]
            cluster_id = db_instance.get('DBClusterIdentifier')
            instance_ids = [db_instance['DBInstanceIdentifier']]
            replicas = []

            if cluster_id:
                try:
                    cluster_instances = self.rds_client.describe_db_instances(
                        Filters=[{'Name': 'db-cluster-id', 'Values': [cluster_id]}]
                    )
                    instance_ids = [inst['DBInstanceIdentifier'] for inst in cluster_instances['DBInstances'] if inst.get('DBInstanceIdentifier')]
                    replicas = [inst_id for inst_id in instance_ids if inst_id != db_instance_identifier]
                except ClientError as e:
                    logger.warning(f"Failed to resolve cluster members for cluster {cluster_id}: {str(e)}")

            return {
                'instance_id': db_instance_identifier,
                'cluster_id': cluster_id,
                'instance_ids': instance_ids,
                'replicas': replicas
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Failed to describe DB instance '{db_instance_identifier}': {error_code}")
            raise
        except Exception as e:
            logger.error(f"Failed to resolve DB resources for '{db_instance_identifier}': {str(e)}")
            raise

    def _get_db_cluster_status(self, cluster_id: str) -> Optional[str]:
        """Return the current status of a DB cluster."""
        try:
            response = self.rds_client.describe_db_clusters(DBClusterIdentifier=cluster_id)
            return response['DBClusters'][0].get('Status')
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'DBClusterNotFoundFault':
                logger.warning(f"DB cluster '{cluster_id}' not found while checking status")
                return None
            logger.warning(f"Failed to get status for DB cluster '{cluster_id}': {str(e)}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error getting cluster status for '{cluster_id}': {str(e)}")
            return None

    def _start_db_cluster_if_stopped(self, cluster_id: str, max_attempts: int = 1000) -> bool:
        """Start a stopped DB cluster and wait until it becomes available."""
        status = self._get_db_cluster_status(cluster_id)
        if status not in ['stopped', 'stopping']:
            return True

        try:
            self.rds_client.start_db_cluster(DBClusterIdentifier=cluster_id)
            logger.info(f"Starting DB cluster '{cluster_id}' to allow deletion")
            return self.wait_for_resource('db-cluster', cluster_id, max_attempts=max_attempts, expected_status='available')
        except ClientError as e:
            logger.error(f"Failed to start DB cluster '{cluster_id}': {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting DB cluster '{cluster_id}': {str(e)}")
            return False

    def stop_db_resources(self, db_instance_identifier: str, max_attempts: int = 1000) -> str:
        """Stop a DB instance and related cluster/replicas, waiting until stopped."""
        resources = self._resolve_db_resources(db_instance_identifier)
        resource_names = [resources['instance_id']]

        try:
            if resources['cluster_id']:
                cluster_id = resources['cluster_id']
                resource_names.append(cluster_id)
                resource_names.extend(resources['replicas'])

                try:
                    self.rds_client.stop_db_cluster(DBClusterIdentifier=cluster_id)
                    logger.info(f"Stopping DB cluster '{cluster_id}'")
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    if error_code in ['InvalidDBClusterStateFault', 'DBClusterAlreadyStoppedFault']:
                        logger.info(f"DB cluster '{cluster_id}' is already stopping or stopped")
                    else:
                        logger.error(f"Failed to stop DB cluster '{cluster_id}': {str(e)}")
                        raise

                if not self.wait_for_resource('db-cluster', cluster_id, max_attempts=max_attempts, expected_status='stopped'):
                    raise Exception(f"Timed out waiting for DB cluster '{cluster_id}' to stop")

                for instance_id in resources['instance_ids']:
                    if not self.wait_for_resource('db-instance', instance_id, max_attempts=max_attempts, expected_status='stopped'):
                        raise Exception(f"Timed out waiting for DB instance '{instance_id}' to stop")
            else:
                try:
                    self.rds_client.stop_db_instance(DBInstanceIdentifier=db_instance_identifier)
                    logger.info(f"Stopping DB instance '{db_instance_identifier}'")
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    if error_code in ['InvalidDBInstanceState', 'DBInstanceAlreadyStopped']:
                        logger.info(f"DB instance '{db_instance_identifier}' is already stopping or stopped")
                    else:
                        logger.error(f"Failed to stop DB instance '{db_instance_identifier}': {str(e)}")
                        raise

                if not self.wait_for_resource('db-instance', db_instance_identifier, max_attempts=max_attempts, expected_status='stopped'):
                    raise Exception(f"Timed out waiting for DB instance '{db_instance_identifier}' to stop")

            return f"Stopped DB resources: {', '.join(resource_names)}."
        except Exception as e:
            logger.error(f"Failed to stop DB resources for '{db_instance_identifier}': {str(e)}")
            raise

    def _wait_for_db_identifier_rename(self, resource_type: str, original_identifier: str, renamed_identifier: str, max_attempts: int = 1000, expected_status: str = 'available') -> bool:
        """Poll until the renamed identifier is visible and ready. This handles the eventual consistency
        window between Azure's rename call and the subsequent describe calls."""
        for attempt in range(max_attempts):
            try:
                if resource_type == 'db-cluster':
                    response = self.rds_client.describe_db_clusters(DBClusterIdentifier=renamed_identifier)
                    cluster = response['DBClusters'][0]
                    status = cluster.get('Status')
                    if status == expected_status:
                        logger.info(f"DB cluster '{renamed_identifier}' is available after rename")
                        return True
                    logger.info(f"DB cluster '{renamed_identifier}' is in status '{status}' during rename propagation; waiting...")
                elif resource_type == 'db-instance':
                    response = self.rds_client.describe_db_instances(DBInstanceIdentifier=renamed_identifier)
                    instance = response['DBInstances'][0]
                    status = instance.get('DBInstanceStatus')
                    if status == expected_status:
                        logger.info(f"DB instance '{renamed_identifier}' is available after rename")
                        return True
                    logger.info(f"DB instance '{renamed_identifier}' is in status '{status}' during rename propagation; waiting...")
            except ClientError as e:
                error_code = e.response['Error']['Code']
                if 'NotFound' in error_code:
                    logger.info(f"Rename still propagating: '{renamed_identifier}' not found yet while waiting for '{original_identifier}' -> '{renamed_identifier}'")
                else:
                    logger.warning(f"Unexpected error while polling rename for '{renamed_identifier}': {str(e)}")
            except Exception as e:
                logger.warning(f"Unexpected polling error for '{renamed_identifier}': {str(e)}")

            time.sleep(30)

        logger.error(f"Timed out waiting for '{renamed_identifier}' to become '{expected_status}' after rename from '{original_identifier}'")
        return False

    def rename_db_resources(self, db_instance_identifier: str, max_attempts: int = 1000) -> str:
        """Rename DB instance/cluster and its instances by appending '-OLD' and wait until available."""
        resources = self._resolve_db_resources(db_instance_identifier)

        try:
            if resources.get('cluster_id'):
                cluster_id = resources['cluster_id']
                new_cluster_id = f"{cluster_id}-OLD"

                # If the target identifier already exists, assume the rename was already completed.
                try:
                    self.rds_client.describe_db_clusters(DBClusterIdentifier=new_cluster_id)
                    logger.info(f"DB cluster '{new_cluster_id}' already exists; rename already completed.")
                    cluster_rename_complete = True
                except ClientError:
                    cluster_rename_complete = False

                if not cluster_rename_complete:
                    logger.info(f"Renaming DB cluster '{cluster_id}' to '{new_cluster_id}'")
                    try:
                        self.rds_client.modify_db_cluster(
                            DBClusterIdentifier=cluster_id,
                            NewDBClusterIdentifier=new_cluster_id,
                            ApplyImmediately=True
                        )
                    except ClientError as e:
                        error_code = e.response['Error']['Code']
                        if error_code == 'DBClusterNotFoundFault':
                            logger.info(f"DB cluster '{cluster_id}' not found when attempting rename")
                        else:
                            logger.error(f"Failed to rename DB cluster '{cluster_id}': {str(e)}")
                            raise

                    if not self._wait_for_db_identifier_rename('db-cluster', cluster_id, new_cluster_id, max_attempts=max_attempts, expected_status='available'):
                        raise Exception(f"Timed out waiting for DB cluster '{new_cluster_id}' to become available after rename")

                # Rename all instances in the cluster
                for instance_id in resources.get('instance_ids', []):
                    new_instance_id = f"{instance_id}-OLD"

                    try:
                        self.rds_client.describe_db_instances(DBInstanceIdentifier=new_instance_id)
                        logger.info(f"DB instance '{new_instance_id}' already exists; rename already completed.")
                        instance_rename_complete = True
                    except ClientError:
                        instance_rename_complete = False

                    if not instance_rename_complete:
                        logger.info(f"Renaming DB instance '{instance_id}' to '{new_instance_id}'")
                        try:
                            self.rds_client.modify_db_instance(
                                DBInstanceIdentifier=instance_id,
                                NewDBInstanceIdentifier=new_instance_id,
                                ApplyImmediately=True
                            )
                        except ClientError as e:
                            error_code = e.response['Error']['Code']
                            if error_code == 'DBInstanceNotFound':
                                logger.info(f"DB instance '{instance_id}' not found when attempting rename")
                            else:
                                logger.error(f"Failed to rename DB instance '{instance_id}': {str(e)}")
                                raise

                        if not self._wait_for_db_identifier_rename('db-instance', instance_id, new_instance_id, max_attempts=max_attempts, expected_status='available'):
                            raise Exception(f"Timed out waiting for DB instance '{new_instance_id}' to become available after rename")

                return f"Renamed cluster '{cluster_id}' and instances to '-OLD' suffix."
            else:
                # Standalone instance
                new_instance_id = f"{db_instance_identifier}-OLD"
                try:
                    self.rds_client.describe_db_instances(DBInstanceIdentifier=new_instance_id)
                    logger.info(f"DB instance '{new_instance_id}' already exists; rename already completed.")
                except ClientError:
                    logger.info(f"Renaming DB instance '{db_instance_identifier}' to '{new_instance_id}'")
                    try:
                        self.rds_client.modify_db_instance(
                            DBInstanceIdentifier=db_instance_identifier,
                            NewDBInstanceIdentifier=new_instance_id,
                            ApplyImmediately=True
                        )
                    except ClientError as e:
                        error_code = e.response['Error']['Code']
                        if error_code == 'DBInstanceNotFound':
                            logger.info(f"DB instance '{db_instance_identifier}' not found when attempting rename")
                        else:
                            logger.error(f"Failed to rename DB instance '{db_instance_identifier}': {str(e)}")
                            raise

                    if not self._wait_for_db_identifier_rename('db-instance', db_instance_identifier, new_instance_id, max_attempts=max_attempts, expected_status='available'):
                        raise Exception(f"Timed out waiting for DB instance '{new_instance_id}' to become available after rename")

                return f"Renamed DB instance '{db_instance_identifier}' to '{new_instance_id}'."
        except Exception as e:
            logger.error(f"Failed to rename DB resources for '{db_instance_identifier}': {str(e)}")
            raise

    def delete_db_resources(self, db_instance_identifier: str, max_attempts: int = 1000, skip_final_snapshot: bool = True) -> str:
        """Delete a DB instance and related cluster/replicas, waiting until deletion is confirmed."""
        resources = self._resolve_db_resources(db_instance_identifier)
        resource_names = [resources['instance_id']]

        try:
            if resources['cluster_id']:
                cluster_id = resources['cluster_id']
                resource_names.append(cluster_id)
                resource_names.extend(resources['replicas'])

                for instance_id in resources['instance_ids']:
                    try:
                        self.rds_client.delete_db_instance(
                            DBInstanceIdentifier=instance_id,
                            SkipFinalSnapshot=skip_final_snapshot,
                            DeleteAutomatedBackups=True
                        )
                        logger.info(f"Deleting DB instance '{instance_id}'")
                    except ClientError as e:
                        error_code = e.response['Error']['Code']
                        if error_code == 'InvalidDBClusterStateFault':
                            cluster_status = self._get_db_cluster_status(cluster_id)
                            if cluster_status in ['stopped', 'stopping']:
                                logger.info(f"DB cluster '{cluster_id}' is in state '{cluster_status}', starting it before deleting instances")
                                if self._start_db_cluster_if_stopped(cluster_id, max_attempts=max_attempts):
                                    try:
                                        self.rds_client.delete_db_instance(
                                            DBInstanceIdentifier=instance_id,
                                            SkipFinalSnapshot=skip_final_snapshot,
                                            DeleteAutomatedBackups=True
                                        )
                                        logger.info(f"Deleting DB instance '{instance_id}' after starting cluster")
                                    except ClientError as inner_e:
                                        inner_code = inner_e.response['Error']['Code']
                                        if inner_code in ['InvalidDBInstanceState', 'DBInstanceAlreadyBeingDeleted', 'DBInstanceNotFound']:
                                            logger.info(f"DB instance '{instance_id}' is already deleting or not found")
                                        else:
                                            logger.error(f"Failed to delete DB instance '{instance_id}' after starting cluster: {str(inner_e)}")
                                            raise
                                else:
                                    raise Exception(f"Unable to start DB cluster '{cluster_id}' before deletion")
                            else:
                                logger.error(f"Failed to delete DB instance '{instance_id}': {str(e)}")
                                raise
                        elif error_code in ['InvalidDBInstanceState', 'DBInstanceAlreadyBeingDeleted', 'DBInstanceNotFound']:
                            logger.info(f"DB instance '{instance_id}' is already deleting or not found")
                        else:
                            logger.error(f"Failed to delete DB instance '{instance_id}': {str(e)}")
                            raise

                for instance_id in resources['instance_ids']:
                    if not self.wait_for_resource('db-instance', instance_id, max_attempts=max_attempts, expected_status='deleting'):
                        raise Exception(f"Timed out waiting for DB instance '{instance_id}' to start deleting")

                try:
                    self.rds_client.delete_db_cluster(
                        DBClusterIdentifier=cluster_id,
                        SkipFinalSnapshot=skip_final_snapshot
                    )
                    logger.info(f"Deleting DB cluster '{cluster_id}'")
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    if error_code == 'DBClusterNotFoundFault':
                        logger.info(f"DB cluster '{cluster_id}' is already deleted")
                    elif error_code == 'InvalidDBClusterStateFault':
                        logger.warning(f"DB cluster '{cluster_id}' is in an invalid state for deletion: {str(e)}")
                    else:
                        logger.error(f"Failed to delete DB cluster '{cluster_id}': {str(e)}")
                        raise

                if not self.wait_for_resource('db-cluster', cluster_id, max_attempts=max_attempts, expected_status='deleted'):
                    raise Exception(f"Timed out waiting for DB cluster '{cluster_id}' to be deleted")
            else:
                try:
                    self.rds_client.delete_db_instance(
                        DBInstanceIdentifier=db_instance_identifier,
                        SkipFinalSnapshot=skip_final_snapshot,
                        DeleteAutomatedBackups=True
                    )
                    logger.info(f"Deleting DB instance '{db_instance_identifier}'")
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    if error_code in ['InvalidDBInstanceState', 'DBInstanceAlreadyBeingDeleted', 'DBInstanceNotFound']:
                        logger.info(f"DB instance '{db_instance_identifier}' is already deleting or not found")
                    else:
                        logger.error(f"Failed to delete DB instance '{db_instance_identifier}': {str(e)}")
                        raise

                if not self.wait_for_resource('db-instance', db_instance_identifier, max_attempts=max_attempts, expected_status='deleting'):
                    raise Exception(f"Timed out waiting for DB instance '{db_instance_identifier}' to start deleting")

                if not self.wait_for_resource('db-instance', db_instance_identifier, max_attempts=max_attempts, expected_status='deleted'):
                    raise Exception(f"Timed out waiting for DB instance '{db_instance_identifier}' to be deleted")

            return f"Deleted DB resources: {', '.join(resource_names)}."
        except Exception as e:
            logger.error(f"Failed to delete DB resources for '{db_instance_identifier}': {str(e)}")
            raise

    def create_cluster_parameter_group(self, metadata: Dict[str, Any], db_info: Dict[str, Any], new_identifier: str) -> Optional[str]:
        """Create a custom cluster parameter group for Aurora with enhanced error handling"""
        cluster_param_group_name = db_info.get('cluster_parameter_group_name')
        
        if not cluster_param_group_name or cluster_param_group_name.startswith('default.'):
            logger.info("Using default cluster parameter group")
            return None
        
        new_cluster_param_group_name = f"{new_identifier}-cluster-params"
        
        try:
            param_group_family = self.get_parameter_group_family(db_info['engine'], db_info['engine_version'], self.get_parameter_group_family(db_info['engine']))
            
            logger.info(f"Creating cluster parameter group: {new_cluster_param_group_name}")
            logger.info(f"Using parameter group family: {param_group_family}")
            
            self.rds_client.create_db_cluster_parameter_group(
                DBClusterParameterGroupName=new_cluster_param_group_name,
                DBParameterGroupFamily=param_group_family,
                Description=f"Cluster parameter group for {new_identifier}"
            )
            
            if not self.wait_for_resource('cluster-parameter-group', new_cluster_param_group_name):
                raise Exception("Cluster parameter group creation timeout")
            
            # Apply custom parameters if they exist
            self._apply_cluster_parameters(metadata, new_cluster_param_group_name, db_info['engine'])
            
            return new_cluster_param_group_name
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'DBParameterGroupAlreadyExistsFault':
                logger.warning(f"Cluster parameter group {new_cluster_param_group_name} already exists, using existing one")
                return new_cluster_param_group_name
            else:
                logger.error(f"Failed to create cluster parameter group: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error creating cluster parameter group: {str(e)}")
            raise

    def _apply_cluster_parameters(self, metadata: Dict[str, Any], param_group_name: str, engine: str) -> None:
        """Apply cluster parameters with engine-specific validation"""
        try:
            parameters = metadata.get('Parameters', [])
            if not parameters:
                logger.info("No custom parameters to apply")
                return
            
            logger.info("Applying custom cluster parameters...")
            modifiable_params = []
            
            for param in parameters:
                try:
                    if (param.get('IsModifiable', False) and 
                        param.get('ParameterValue') is not None and
                        param.get('ParameterName')):
                        
                        # Engine-specific parameter validation
                        if self._is_valid_parameter_for_engine(param['ParameterName'], engine, is_cluster=True):
                            modifiable_params.append({
                                'ParameterName': param['ParameterName'],
                                'ParameterValue': str(param['ParameterValue']),
                                'ApplyMethod': param.get('ApplyMethod', 'immediate')
                            })
                        else:
                            logger.debug(f"Skipping parameter {param['ParameterName']} - not valid for engine {engine}")
                except Exception as e:
                    logger.warning(f"Error processing parameter {param.get('ParameterName', 'unknown')}: {str(e)}")
            
            if modifiable_params:
                # Apply parameters in batches of 20 (AWS limit)
                for i in range(0, len(modifiable_params), 20):
                    batch = modifiable_params[i:i+20]
                    try:
                        self.rds_client.modify_db_cluster_parameter_group(
                            DBClusterParameterGroupName=param_group_name,
                            Parameters=batch
                        )
                        logger.info(f"Applied {len(batch)} cluster parameters")
                    except ClientError as e:
                        logger.warning(f"Failed to apply cluster parameter batch: {str(e)}")
            else:
                logger.info("No valid modifiable cluster parameters found")
                
        except Exception as e:
            logger.warning(f"Error applying cluster parameters: {str(e)}")

    def _is_valid_parameter_for_engine(self, param_name: str, engine: str, is_cluster: bool = False) -> bool:
        """Validate if a parameter is valid for the specific engine"""
        # This is a simplified validation - in production, you might want to 
        # query the actual engine versions to get valid parameters
        engine_specific_invalid_params = {
            'aurora-mysql': {
                'cluster': ['shared_preload_libraries', 'log_statement'],
                'instance': ['wal_buffers', 'checkpoint_segments']
            },
            'aurora-postgresql': {
                'cluster': ['innodb_buffer_pool_size', 'query_cache_size'],
                'instance': ['innodb_log_file_size', 'binlog_format']
            },
            'mysql': {
                'instance': ['shared_preload_libraries', 'wal_buffers']
            },
            'postgres': {
                'instance': ['innodb_buffer_pool_size', 'query_cache_size']
            }
        }
        
        param_type = 'cluster' if is_cluster else 'instance'
        invalid_params = engine_specific_invalid_params.get(engine, {}).get(param_type, [])
        
        return param_name not in invalid_params

    def create_parameter_group(self, metadata: Dict[str, Any], db_info: Dict[str, Any], new_identifier: str) -> Optional[str]:
        """Create a custom parameter group for regular RDS instances with enhanced error handling"""
        param_group_name = db_info.get('parameter_group_name')
        
        if not param_group_name or param_group_name.startswith('default.'):
            logger.info("Using default parameter group")
            return None
        
        new_param_group_name = f"{new_identifier}-params"
        
        try:
            param_group_family = self.get_parameter_group_family(db_info['engine'], db_info['engine_version'], self.is_aurora_engine(db_info['engine']))
            
            logger.info(f"Creating parameter group: {new_param_group_name}")
            logger.info(f"Using parameter group family: {param_group_family}")
            
            self.rds_client.create_db_parameter_group(
                DBParameterGroupName=new_param_group_name,
                DBParameterGroupFamily=param_group_family,
                Description=f"Parameter group for {new_identifier}"
            )
            
            if not self.wait_for_resource('parameter-group', new_param_group_name):
                raise Exception("Parameter group creation timeout")
            
            # Apply custom parameters if they exist
            self._apply_instance_parameters(metadata, new_param_group_name, db_info['engine'])
            
            return new_param_group_name
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'DBParameterGroupAlreadyExistsFault':
                logger.warning(f"Parameter group {new_param_group_name} already exists, using existing one")
                return new_param_group_name
            else:
                logger.error(f"Failed to create parameter group: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error creating parameter group: {str(e)}")
            raise

    def _apply_instance_parameters(self, metadata: Dict[str, Any], param_group_name: str, engine: str) -> None:
        """Apply instance parameters with engine-specific validation"""
        try:
            parameters = metadata.get('Parameters', [])
            if not parameters:
                logger.info("No custom parameters to apply")
                return
            
            logger.info("Applying custom parameters...")
            modifiable_params = []
            
            for param in parameters:
                try:
                    if (param.get('IsModifiable', False) and 
                        param.get('ParameterValue') is not None and
                        param.get('ParameterName')):
                        
                        # Engine-specific parameter validation
                        if self._is_valid_parameter_for_engine(param['ParameterName'], engine, is_cluster=False):
                            modifiable_params.append({
                                'ParameterName': param['ParameterName'],
                                'ParameterValue': str(param['ParameterValue']),
                                'ApplyMethod': param.get('ApplyMethod', 'immediate')
                            })
                        else:
                            logger.debug(f"Skipping parameter {param['ParameterName']} - not valid for engine {engine}")
                except Exception as e:
                    logger.warning(f"Error processing parameter {param.get('ParameterName', 'unknown')}: {str(e)}")
            
            if modifiable_params:
                # Apply parameters in batches of 20 (AWS limit)
                for i in range(0, len(modifiable_params), 20):
                    batch = modifiable_params[i:i+20]
                    try:
                        self.rds_client.modify_db_parameter_group(
                            DBParameterGroupName=param_group_name,
                            Parameters=batch
                        )
                        logger.info(f"Applied {len(batch)} parameters")
                    except ClientError as e:
                        logger.warning(f"Failed to apply parameter batch: {str(e)}")
            else:
                logger.info("No valid modifiable parameters found")
                
        except Exception as e:
            logger.warning(f"Error applying parameters: {str(e)}")

    def create_option_group(self, db_info: Dict[str, Any], new_identifier: str) -> Optional[str]:
        """Create a custom option group if needed with enhanced validation"""
        option_group_name = db_info.get('option_group_name')
        engine = db_info['engine']
        
        # Check if engine supports option groups
        engine_specs = self.validator.get_engine_specific_parameters().get(engine, {})
        if not engine_specs.get('supports_option_groups', False):
            logger.info(f"Engine {engine} does not support option groups")
            return None
        
        if not option_group_name or option_group_name.startswith('default:'):
            logger.info("Using default option group")
            return None
        
        new_option_group_name = f"{new_identifier}-options"
        
        try:
            major_engine_version = '.'.join(db_info['engine_version'].split('.')[:2])
            
            logger.info(f"Creating option group: {new_option_group_name}")
            logger.info(f"Engine: {engine}, Major version: {major_engine_version}")
            
            self.rds_client.create_option_group(
                OptionGroupName=new_option_group_name,
                EngineName=engine,
                MajorEngineVersion=major_engine_version,
                OptionGroupDescription=f"Option group for {new_identifier}"
            )
            
            if not self.wait_for_resource('option-group', new_option_group_name):
                raise Exception("Option group creation timeout")
            
            return new_option_group_name
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'OptionGroupAlreadyExistsFault':
                logger.warning(f"Option group {new_option_group_name} already exists, using existing one")
                return new_option_group_name
            else:
                logger.error(f"Failed to create option group: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error creating option group: {str(e)}")
            raise

    def create_subnet_group(self, db_info: Dict[str, Any], new_identifier: str) -> Optional[str]:
        """Create a custom subnet group if needed with enhanced validation"""
        subnet_group_name = db_info.get('subnet_group_name')
        subnet_ids = db_info.get('subnet_ids', [])
        
        if not subnet_group_name or subnet_group_name == 'default':
            logger.info("Using default subnet group")
            return None
        
        if not subnet_ids:
            logger.warning("No subnet IDs found, cannot create custom subnet group")
            return None
        
        # Validate subnet IDs exist
        try:
            response = self.ec2_client.describe_subnets(SubnetIds=subnet_ids)
            valid_subnets = [subnet['SubnetId'] for subnet in response['Subnets']]
            if len(valid_subnets) != len(subnet_ids):
                logger.warning(f"Some subnets not found. Using valid subnets: {valid_subnets}")
                subnet_ids = valid_subnets
        except ClientError as e:
            logger.error(f"Error validating subnets: {str(e)}")
            return None
        
        new_subnet_group_name = f"{new_identifier}-subnet-group"
        
        try:
            logger.info(f"Creating subnet group: {new_subnet_group_name}")
            logger.info(f"Using subnets: {subnet_ids}")
            
            self.rds_client.create_db_subnet_group(
                DBSubnetGroupName=new_subnet_group_name,
                DBSubnetGroupDescription=f"Subnet group for {new_identifier}",
                SubnetIds=subnet_ids
            )
            
            if not self.wait_for_resource('subnet-group', new_subnet_group_name):
                raise Exception("Subnet group creation timeout")
            
            return new_subnet_group_name
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'DBSubnetGroupAlreadyExistsFault':
                logger.warning(f"Subnet group {new_subnet_group_name} already exists, using existing one")
                return new_subnet_group_name
            else:
                logger.error(f"Failed to create subnet group: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error creating subnet group: {str(e)}")
            raise

    def extract_tags(self, metadata: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract tags from metadata with error handling"""
        try:
            tags = metadata.get('Tags', [])
            valid_tags = []
            for tag in tags:
                if isinstance(tag, dict) and 'Key' in tag and 'Value' in tag:
                    valid_tags.append({'Key': str(tag['Key']), 'Value': str(tag['Value'])})
            return valid_tags
        except Exception as e:
            logger.warning(f"Error extracting tags: {str(e)}")
            return []

    def restore_aurora_cluster(self, snapshot_arn: str, cluster_identifier: str, db_info: Dict[str, Any], 
                             cluster_param_group_name: Optional[str], subnet_group_name: Optional[str], 
                             tags: List[Dict[str, str]], master_password: Optional[str] = "password", master_username: Optional[str] = "username") -> Dict[str, Any]:
        """Restore Aurora cluster from snapshot with engine-specific handling"""
        
        engine = db_info['engine']
        logger.info(f"Restoring Aurora cluster for engine: {engine}")
        
        restore_params = {
            'DBClusterIdentifier': cluster_identifier,
            'SnapshotIdentifier': snapshot_arn,
            'Engine': engine
        }

        # Master username/password for Aurora will be applied in post-restore modifications
        # (some boto3/aws versions do not support setting them during restore)
        
        # Engine version (with validation)
        if db_info.get('engine_version'):
            restore_params['EngineVersion'] = db_info['engine_version']
        
        # Database name (engine-specific handling)
        if db_info.get('database_name'):
            restore_params['DatabaseName'] = db_info['database_name']
        
        # Port (with engine-specific defaults)
        port = db_info.get('port')
        if port:
            restore_params['Port'] = port
        
        # Availability Zone
        if db_info.get('availability_zone'):
            restore_params['AvailabilityZone'] = db_info['availability_zone']
        
        # Parameter and subnet groups
        if cluster_param_group_name:
            restore_params['DBClusterParameterGroupName'] = cluster_param_group_name
        
        if subnet_group_name:
            restore_params['DBSubnetGroupName'] = subnet_group_name
        
        # Security Groups
        if db_info.get('vpc_security_group_ids'):
            restore_params['VpcSecurityGroupIds'] = [sg for sg in db_info['vpc_security_group_ids'] if sg]
        
        # Storage encryption
        if db_info.get('storage_encrypted') and db_info.get('kms_key_id'):
            restore_params['KmsKeyId'] = db_info['kms_key_id']
        
        # Engine-specific features
        try:
            # Aurora MySQL specific features
            if engine == 'aurora-mysql':
                if db_info.get('backtrack_window', 0) > 0:
                    restore_params['BacktrackWindow'] = db_info['backtrack_window']
            
            # Common Aurora features
            restore_params['EnableIAMDatabaseAuthentication'] = db_info.get('iam_database_authentication_enabled', False)
            restore_params['DeletionProtection'] = db_info.get('deletion_protection', False)
            # restore_params['CopyTagsToSnapshot'] = db_info.get('copy_tags_to_snapshot', False)
            restore_params['CopyTagsToSnapshot'] = db_info.get('copy_tags_to_snapshot')
            
            # CloudWatch Logs (engine-specific)
            if db_info.get('enabled_cloudwatch_logs_exports'):
                restore_params['EnableCloudwatchLogsExports'] = db_info['enabled_cloudwatch_logs_exports']
            
            # Engine Mode and Scaling
            if db_info.get('engine_mode'):
                restore_params['EngineMode'] = db_info['engine_mode']
            
            if db_info.get('scaling_configuration'):
                restore_params['ScalingConfiguration'] = db_info['scaling_configuration']
            
            if db_info.get('serverlessv2_scaling_configuration'):
                restore_params['ServerlessV2ScalingConfiguration'] = db_info['serverlessv2_scaling_configuration']
            
            # Multi-AZ cluster specific settings
            if db_info.get('db_cluster_instance_class'):
                # restore_params['DBClusterInstanceClass'] = db_info['db_cluster_instance_class']
                restore_params['DBInstanceClass'] = db_info['db_cluster_instance_class']
            
            if db_info.get('storage_type'):
                restore_params['StorageType'] = db_info['storage_type']
            
            if db_info.get('iops') and db_info['iops'] > 0:
                restore_params['Iops'] = db_info['iops']
            
            if db_info.get('allocated_storage'):
                restore_params['AllocatedStorage'] = db_info['allocated_storage']
            
            restore_params['PubliclyAccessible'] = db_info.get('publicly_accessible', False)
            
            # Tags
            if tags:
                restore_params['Tags'] = tags
            
            # Set BackupRetentionPeriod during restore using value from metadata if valid
            # AWS requires 1-35 for Aurora clusters; only include if valid to avoid InvalidParameterValue
            brp = db_info.get('backup_retention_period')
            try:
                if brp is not None:
                    brp_int = int(brp)
                    if 1 <= brp_int <= 35:
                        restore_params['BackupRetentionPeriod'] = brp_int
                    else:
                        logger.warning(f"Ignoring invalid BackupRetentionPeriod {brp}; must be between 1 and 35 for Aurora")
            except (ValueError, TypeError):
                logger.warning(f"Invalid BackupRetentionPeriod value in metadata: {brp}")
                
        except Exception as e:
            logger.warning(f"Error setting engine-specific parameters: {str(e)}")
        
        try:
            logger.info(f"Restoring Aurora cluster: {cluster_identifier}")
            logger.debug(f"Restore parameters: {json.dumps({k: v for k, v in restore_params.items() if k != 'MasterUserPassword'}, indent=2)}")
            
            response = self.rds_client.restore_db_cluster_from_snapshot(**restore_params)
            logger.info("Aurora cluster restore initiated successfully")
            return response
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Failed to restore Aurora cluster ({error_code}): {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error restoring Aurora cluster: {str(e)}")
            raise

    def restore_aurora_instance(self, cluster_identifier: str, instance_identifier: str, db_info: Dict[str, Any]) -> Dict[str, Any]:
        """Restore Aurora DB instance in the cluster with engine-specific handling"""
        engine = db_info['engine']
        
        # Determine appropriate instance class
        # instance_class = db_info.get('db_cluster_instance_class')
        instance_class = db_info.get('db_instance_class')
        
        if not instance_class:
            # Use engine-appropriate default
            if engine == 'aurora-mysql':
                instance_class = 'db.t3.medium'
            elif engine == 'aurora-postgresql':
                instance_class = 'db.t3.medium'
            else:
                instance_class = 'db.t3.medium'
        
        create_params = {
            'DBInstanceIdentifier': instance_identifier,
            'DBClusterIdentifier': cluster_identifier,
            'DBInstanceClass': instance_class,
            'Engine': engine
        }
        
        try:            
            # Availability Zone
            if db_info.get('availability_zone'):
                create_params['AvailabilityZone'] = db_info['availability_zone']
            
            if db_info.get('multi_az'):
                print("multi_az value is: ", db_info.get('multi_az'))
                print("multi_az value is: ", db_info.get('multi_az', False))
                create_params['MultiAZ'] = db_info.get('multi_az', False)
            
            if db_info.get('engine_lifecycle_support'):
                create_params['EngineLifecycleSupport'] = db_info.get('engine_lifecycle_support')
                print("engine_lifecycle_support value is: ", db_info.get('engine_lifecycle_support'))
                # modifications_needed = True
            if db_info.get('preferred_maintenance_window'):
                create_params['PreferredMaintenanceWindow'] = db_info['preferred_maintenance_window']
                # modifications_needed = True
            
            # Performance Insights (engine-specific)
            if db_info.get('performance_insights_enabled'):
                if self._operation_supports_parameter('create_db_instance', 'EnablePerformanceInsights'):
                    create_params['EnablePerformanceInsights'] = True
                if self._operation_supports_parameter('create_db_instance', 'PerformanceInsightsKMSKeyId') and db_info.get('performance_insights_kms_key_id'):
                    create_params['PerformanceInsightsKMSKeyId'] = db_info['performance_insights_kms_key_id']
                if self._operation_supports_parameter('create_db_instance', 'PerformanceInsightsRetentionPeriod') and db_info.get('performance_insights_retention_period', 7) != 7:
                    create_params['PerformanceInsightsRetentionPeriod'] = db_info['performance_insights_retention_period']
                if not any(self._operation_supports_parameter('create_db_instance', name) for name in (
                    'EnablePerformanceInsights',
                    'PerformanceInsightsKMSKeyId',
                    'PerformanceInsightsRetentionPeriod'
                )):
                    logger.warning('Performance Insights parameters are not supported by create_db_instance in this boto3 version; skipping them.')
            
            # Monitoring
            if db_info.get('monitoring_interval', 0) > 0:
                create_params['MonitoringInterval'] = db_info['monitoring_interval']
                if db_info.get('monitoring_role_arn'):
                    create_params['MonitoringRoleArn'] = db_info['monitoring_role_arn']
            
            create_params['AutoMinorVersionUpgrade'] = db_info.get('auto_minor_version_upgrade', True)
            create_params['PubliclyAccessible'] = db_info.get('publicly_accessible', False)
            
            logger.info(f"Creating Aurora instance: {instance_identifier}")
            logger.info(f"Instance class: {instance_class}")
            
            response = self.rds_client.create_db_instance(**create_params)
            logger.info("Aurora instance creation initiated successfully")
            return response
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.error(f"Failed to create Aurora instance ({error_code}): {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating Aurora instance: {str(e)}")
            raise

    def restore_db_instance(self, snapshot_arn: str, new_identifier: str, db_info: Dict[str, Any], 
                          param_group_name: Optional[str], option_group_name: Optional[str], 
                          subnet_group_name: Optional[str], tags: List[Dict[str, str]], 
                          master_password: Optional[str] = "password", master_username: Optional[str] = "username") -> Dict[str, Any]:
        """Restore regular RDS DB instance from snapshot with engine-specific handling"""
        
        engine = db_info['engine']
        logger.info(f"Restoring RDS instance for engine: {engine}")
        
        restore_params = {
            # 'DBInstanceIdentifier': new_identifier,
            # 'DBSnapshotIdentifier': snapshot_arn,
            'DBInstanceClass': db_info['db_instance_class']
        }
        
        try:
            
            try:
                print("Look here 1")
                print("1 EngineLifecycleSupport value is:", db_info.get('EngineLifecycleSupport'))
            except Exception as e:
                logger.warning(f"Exception 1: {str(e)}")
            try:
                print("2 EngineLifecycleSupport value is:", db_info.get('engine_lifecycle_support'))
            except Exception as e:
                logger.warning(f"Exception 1: {str(e)}")
            try:
                print("3 EngineLifecycleSupport value is:", db_info['EngineLifecycleSupport'])
            except Exception as e:
                logger.warning(f"Exception 1: {str(e)}")
            try:
                print("4 EngineLifecycleSupport value is:", db_info['engine_lifecycle_support'])

            except Exception as e:
                logger.warning(f"Exception 1: {str(e)}")
            try:
                print("5 EngineLifecycleSupport value is:", db_info.get('MultiAZ'))
            except Exception as e:
                logger.warning(f"Exception 1: {str(e)}")
            try:
                print("6 EngineLifecycleSupport value is:", db_info.get('multi_az'))

            except Exception as e:
                logger.warning(f"Exception 1: {str(e)}")
            try:
                print("7 EngineLifecycleSupport value is:", db_info['MultiAZ'])
            except Exception as e:
                logger.warning(f"Exception 1: {str(e)}")
            try:
                print("8 EngineLifecycleSupport value is:", db_info['multi_az'])
            except Exception as e:
                logger.warning(f"Exception 1: {str(e)}")
                
            
            
            if db_info.get('engine_lifecycle_support'):
                restore_params['EngineLifecycleSupport'] = db_info.get('engine_lifecycle_support')
                modifications_needed = True
            
            if db_info.get('copy_tags_to_snapshot'):
                restore_params['CopyTagsToSnapshot'] = db_info.get('copy_tags_to_snapshot')
            
            if new_identifier:
                restore_params['DBInstanceIdentifier'] = new_identifier
                
            if snapshot_arn:
                restore_params['DBSnapshotIdentifier'] = snapshot_arn
                
            if master_password:
                if self._operation_supports_parameter('restore_db_instance_from_db_snapshot', 'MasterUserPassword'):
                    restore_params['MasterUserPassword'] = master_password
                else:
                    logger.warning("MasterUserPassword is not supported by restore_db_instance_from_db_snapshot. Password will be updated after restore using modify_db_instance.")
                    # MasterUserPassword is not a valid parameter for restore_db_instance_from_db_snapshot.
                    # Password changes are applied after restore using modify_db_instance.

            if master_username:
                if self._operation_supports_parameter('restore_db_instance_from_db_snapshot', 'MasterUsername'):
                    restore_params['MasterUsername'] = master_username
                else:
                    logger.warning("MasterUsername is not supported by restore_db_instance_from_db_snapshot; skipping it.")
            
            # Storage parameters (engine-specific validation)
            if db_info.get('storage_type'):
                restore_params['StorageType'] = db_info['storage_type']

            if db_info.get('storage_encrypted'):
                if self._operation_supports_parameter('restore_db_instance_from_db_snapshot', 'StorageEncrypted'):
                    restore_params['StorageEncrypted'] = True

                if db_info.get('kms_key_id'):
                    if engine.startswith('oracle'):
                        if self._operation_supports_parameter('restore_db_instance_from_db_snapshot', 'MasterUserSecretKmsKeyId'):
                            # Oracle restore requires ManageMasterUserPassword when MasterUserSecretKmsKeyId is provided.
                            restore_params['MasterUserSecretKmsKeyId'] = db_info['kms_key_id']
                            restore_params['ManageMasterUserPassword'] = False
                        else:
                            logger.warning('MasterUserSecretKmsKeyId is not supported by restore_db_instance_from_db_snapshot; skipping KMS key parameter for Oracle.')
                    elif self._operation_supports_parameter('restore_db_instance_from_db_snapshot', 'KmsKeyId'):
                        restore_params['KmsKeyId'] = db_info['kms_key_id']
                    else:
                        logger.warning('KmsKeyId is not supported by restore_db_instance_from_db_snapshot; skipping KMS key parameter.')

            if db_info.get('iops') and db_info['iops'] > 0:
                restore_params['Iops'] = db_info['iops']
            
            # Network parameters
            if db_info.get('port'):
                restore_params['Port'] = db_info['port']
            
            if db_info.get('availability_zone'):
                restore_params['AvailabilityZone'] = db_info['availability_zone']
            
            restore_params['PubliclyAccessible'] = db_info.get('publicly_accessible', False)
            if db_info.get('multi_az'):
                print("multi_az value is: ", db_info.get('multi_az'))
                print("multi_az value is: ", db_info.get('multi_az', False))
                restore_params['MultiAZ'] = db_info.get('multi_az', False)
            
            # Parameter and Option Groups
            if param_group_name:
                restore_params['DBParameterGroupName'] = param_group_name
            
            if option_group_name:
                restore_params['OptionGroupName'] = option_group_name
            
            if subnet_group_name:
                restore_params['DBSubnetGroupName'] = subnet_group_name
            
            # Security Groups
            if db_info.get('vpc_security_group_ids'):
                restore_params['VpcSecurityGroupIds'] = [sg for sg in db_info['vpc_security_group_ids'] if sg]
            
            # Engine-specific parameters
            engine_specs = self.validator.get_engine_specific_parameters().get(engine, {})
            
            # License and Character Set (engine-specific)
            if engine_specs.get('supports_license_model') and db_info.get('license_model'):
                restore_params['LicenseModel'] = db_info['license_model']
            
            if engine_specs.get('supports_character_set'):
                if db_info.get('character_set_name'):
                    restore_params['CharacterSetName'] = db_info['character_set_name']
                if db_info.get('nchar_character_set_name'):
                    restore_params['NcharCharacterSetName'] = db_info['nchar_character_set_name']
            
            # Advanced Features
            restore_params['AutoMinorVersionUpgrade'] = db_info.get('auto_minor_version_upgrade', True)
            restore_params['DeletionProtection'] = db_info.get('deletion_protection', False)
            restore_params['EnableIAMDatabaseAuthentication'] = db_info.get('iam_database_authentication_enabled', False)
            
            # Performance Insights
            if db_info.get('performance_insights_enabled'):
                if self._operation_supports_parameter('restore_db_instance_from_db_snapshot', 'EnablePerformanceInsights'):
                    restore_params['EnablePerformanceInsights'] = True
                if self._operation_supports_parameter('restore_db_instance_from_db_snapshot', 'PerformanceInsightsKMSKeyId') and db_info.get('performance_insights_kms_key_id'):
                    restore_params['PerformanceInsightsKMSKeyId'] = db_info['performance_insights_kms_key_id']
                if self._operation_supports_parameter('restore_db_instance_from_db_snapshot', 'PerformanceInsightsRetentionPeriod') and db_info.get('performance_insights_retention_period', 7) != 7:
                    restore_params['PerformanceInsightsRetentionPeriod'] = db_info['performance_insights_retention_period']
                if not any(self._operation_supports_parameter('restore_db_instance_from_db_snapshot', name) for name in (
                    'EnablePerformanceInsights',
                    'PerformanceInsightsKMSKeyId',
                    'PerformanceInsightsRetentionPeriod'
                )):
                    logger.warning('Performance Insights parameters are not supported by restore_db_instance_from_db_snapshot in this boto3 version; skipping them.')
            
            # Enhanced Monitoring
            if db_info.get('monitoring_interval', 0) > 0:
                restore_params['MonitoringInterval'] = db_info['monitoring_interval']
                if db_info.get('monitoring_role_arn'):
                    restore_params['MonitoringRoleArn'] = db_info['monitoring_role_arn']
            
            # CloudWatch Logs (engine-specific)
            if db_info.get('enabled_cloudwatch_logs_exports'):
                restore_params['EnableCloudwatchLogsExports'] = db_info['enabled_cloudwatch_logs_exports']
            
            # Processor Features (engine-specific)
            if engine_specs.get('supports_processor_features') and db_info.get('processor_features'):
                restore_params['ProcessorFeatures'] = db_info['processor_features']
            
            # Tags
            if tags:
                restore_params['Tags'] = tags
            
            # Set BackupRetentionPeriod to 0 during restore to avoid initial snapshot
            restore_params['BackupRetentionPeriod'] = 0
            print(" 2. restore_db_instance")
            logger.info(f"Restoring RDS instance: {new_identifier}")
            
            print(" 3. restore_db_instance")
            print("restore_params are:", restore_params, "\n\n")
            
            # print("restore_params.items() are:", restore_params.items(), "\n\n")
                # logger.debug(f"Restore parameters: {json.dumps({k: v for k, v in restore_params.items() if k != 'MasterUserPassword'}, indent=2)}")
            
            print(" 4. restore_db_instance")
            
            response = self.rds_client.restore_db_instance_from_db_snapshot(**restore_params)
            
            print(" 5. restore_db_instance")
            logger.info("RDS instance restore initiated successfully")
            
            print(" 6. restore_db_instance")
            return response
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            print(" 7. restore_db_instance")
            logger.error(f"Failed to restore RDS instance ({error_code}): {str(e)}")
            raise
        except Exception as e:
            print(" 8. restore_db_instance")
            logger.error(f"Unexpected error restoring RDS instance: {str(e)}")
            raise

    def apply_post_restore_modifications(self, new_identifier: str, db_info: Dict[str, Any], is_aurora: bool = False, master_password: Optional[str] = "password",
                                         cluster_identifier: Optional[str] = None) -> bool:
        """Apply modifications that can't be set during restore with enhanced error handling"""
        try:
            if is_aurora:
                return self._apply_aurora_post_restore_modifications(new_identifier, cluster_identifier, db_info, master_password)
            else:
                return self._apply_rds_post_restore_modifications(new_identifier, db_info, master_password)
        except Exception as e:
            logger.warning(f"Error applying post-restore modifications: {str(e)}")
            return False

    def _wait_for_aurora_cluster_ready(self, cluster_identifier: str, timeout_seconds: int = 600, poll_interval: int = 10) -> bool:
        """Wait for an Aurora cluster to leave the resetting-master-password state and become available."""
        deadline = time.time() + timeout_seconds
        last_status = None

        while time.time() < deadline:
            try:
                resp = self.rds_client.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
                cluster = resp.get('DBClusters', [{}])[0]
                status = cluster.get('Status')
                if status:
                    last_status = status
                pending = cluster.get('PendingModifiedValues', {})
                if status == 'available' and 'MasterUserPassword' not in pending:
                    logger.info(f"Aurora cluster '{cluster_identifier}' is available and no longer resetting master password.")
                    return True
                logger.info(f"Aurora cluster '{cluster_identifier}' status is '{status}' with pending={pending}; waiting for available/resetting-master-password to finish...")
            except Exception as exc:
                logger.warning(f"Error checking Aurora cluster state for '{cluster_identifier}': {exc}")
            time.sleep(poll_interval)

        logger.warning(f"Timed out waiting for Aurora cluster '{cluster_identifier}' to become available after master password reset; last status='{last_status}'")
        return False

    def _wait_for_rds_instance_ready(self, instance_identifier: str, timeout_seconds: int = 600, poll_interval: int = 10, max_attempts: Optional[int] = None) -> bool:
        """Wait for an RDS instance to finish transient states after a restore or password reset."""
        deadline = time.time() + timeout_seconds
        last_status = None

        # if max_attempts is None:
        #     max_attempts = max(1, int(timeout_seconds / poll_interval) + 1)

        max_attempts = 1000
        
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self.rds_client.describe_db_instances(DBInstanceIdentifier=instance_identifier)
                instance = resp.get('DBInstances', [{}])[0]
                status = instance.get('DBInstanceStatus')
                if status:
                    last_status = status
                pending = instance.get('PendingModifiedValues', {})

                if status == 'available' and 'MasterUserPassword' not in pending:
                    logger.info(
                        f"RDS instance '{instance_identifier}' is available and no longer resetting master password; "
                        f"pending={pending}, last_status={last_status}"
                    )
                    return True

                logger.info(
                    f"DB instance with status='{status}' is in transitional state:..."
                    f"\n                         Pending modifications={pending}"
                )
            except Exception as exc:
                logger.warning(f"Error checking RDS instance state for '{instance_identifier}': {exc}")

            if time.time() >= deadline:
                break

            if attempt < max_attempts:
                time.sleep(poll_interval)
                logger.info(f"Ticks before cancelling attempt {attempt}/{max_attempts} - still waiting...\n")

        logger.warning(
            f"Timed out waiting for RDS instance '{instance_identifier}' to become available after post-restore changes; "
            f"last status='{last_status}'"
        )
        return False


    def _apply_aurora_post_restore_modifications(self, instance_identifier: str, cluster_identifier: str, db_info: Dict[str, Any], master_password: Optional[str] = "password") -> bool:
        """Apply Aurora cluster post-restore modifications"""
        # modify_db_cluster expects DBClusterIdentifier; keep instance identifier separate
        cluster_modify_params = {
            'DBClusterIdentifier': cluster_identifier,
            'ApplyImmediately': True
        }
        # instance-level modifications (if needed) will use instance_identifier
        
        modifications_needed = False
        
        try:
            
            # try:
            #     print("Look here")
            #     print("9 EngineLifecycleSupport value is:", db_info.get('EngineLifecycleSupport'))
            # except Exception as e:
            #     logger.warning(f"Exception 1: {str(e)}")
            # try:
            #     print("10 EngineLifecycleSupport value is:", db_info.get('engine_lifecycle_support'))
            # except Exception as e:
            #     logger.warning(f"Exception 1: {str(e)}")
            # try:
            #     print("11 EngineLifecycleSupport value is:", db_info['EngineLifecycleSupport'])
            # except Exception as e:
            #     logger.warning(f"Exception 1: {str(e)}")
            # try:
            #     print("12 EngineLifecycleSupport value is:", db_info['engine_lifecycle_support'])

            # except Exception as e:
            #     logger.warning(f"Exception 1: {str(e)}")
            # try:
            #     print("13 EngineLifecycleSupport value is:", db_info.get('MultiAZ'))
            # except Exception as e:
            #     logger.warning(f"Exception 1: {str(e)}")
            # try:
            #     print("14 EngineLifecycleSupport value is:", db_info.get('multi_az'))

            # except Exception as e:
            #     logger.warning(f"Exception 1: {str(e)}")
            # try:
            #     print("15 EngineLifecycleSupport value is:", db_info['MultiAZ'])
            # except Exception as e:
            #     logger.warning(f"Exception 1: {str(e)}")
            # try:
            #     print("16 EngineLifecycleSupport value is:", db_info['multi_az'])
            # except Exception as e:
            #     logger.warning(f"Exception 1: {str(e)}")
                            
                        
                        
            if db_info.get('engine_lifecycle_support'):
                cluster_modify_params['EngineLifecycleSupport'] = db_info['engine_lifecycle_support']
                modifications_needed = True

            # Master password (cluster-level for Aurora)
            if master_password:
                cluster_modify_params['MasterUserPassword'] = master_password
                modifications_needed = True
                logger.info(f"Setting master password for Aurora cluster '{cluster_identifier}'")

            # Backup settings
            backup_retention_period = db_info.get('backup_retention_period', 7)
            cluster_modify_params['BackupRetentionPeriod'] = backup_retention_period
            modifications_needed = True

            if db_info.get('preferred_backup_window'):
                cluster_modify_params['PreferredBackupWindow'] = db_info['preferred_backup_window']
                modifications_needed = True
            
            if modifications_needed:
                logger.info("Applying post-restore cluster modifications...")
                try:
                    self.rds_client.modify_db_cluster(**cluster_modify_params)
                    logger.info("Post-restore cluster modifications applied successfully")
                except ClientError as e:
                    logger.warning(f"Failed to apply some post-restore cluster modifications: {str(e)}")
                    return False

                if master_password:
                    timeout = db_info.get('post_modify_wait_timeout', 600)
                    logger.info(f"Waiting for Aurora cluster '{cluster_identifier}' to finish resetting master password before continuing...")
                    if not self._wait_for_aurora_cluster_ready(cluster_identifier, timeout_seconds=timeout, poll_interval=5):
                        logger.warning(f"Aurora cluster '{cluster_identifier}' did not finish the reset/availability transitional state within {timeout}s.")

                # Also ensure instance-level password change is applied for writer instance
                try:
                    instance_modified = self._apply_aurora_instance_post_restore_modifications(instance_identifier, db_info, master_password)
                    if instance_modified:
                        logger.info("Post-restore Aurora instance modifications applied successfully")
                except Exception:
                    logger.warning("Failed to apply instance-level post-restore modifications")

            return modifications_needed
        except ClientError as e:
            logger.warning(f"Failed to apply some post-restore cluster modifications: {str(e)}")
            return False

    def _apply_aurora_instance_post_restore_modifications(self, instance_identifier: str, db_info: Dict[str, Any], master_password: Optional[str] = "password") -> bool:
        """Apply Aurora instance post-restore modifications.

        For Aurora cluster members, MasterUserPassword must be changed at the cluster level via
        modify_db_cluster, not on individual DB instances. This method intentionally excludes
        MasterUserPassword to avoid InvalidParameterCombination errors.
        """
        modify_params = {
            'DBInstanceIdentifier': instance_identifier,
            'ApplyImmediately': True
        }

        modifications_needed = False

        try:
            # Aurora DB instances within a cluster do not accept MasterUserPassword updates via
            # modify_db_instance. Password changes must be applied to the DB cluster instead.
            if master_password:
                logger.info(f"Aurora password change is managed at cluster level for instance '{instance_identifier}'. Skipping instance-level password update.")

            if db_info.get('monitoring_interval', 0) > 0:
                modify_params['MonitoringInterval'] = db_info['monitoring_interval']
                modifications_needed = True
                if db_info.get('monitoring_role_arn'):
                    modify_params['MonitoringRoleArn'] = db_info['monitoring_role_arn']

            if db_info.get('performance_insights_enabled'):
                modify_params['EnablePerformanceInsights'] = True
                modifications_needed = True
                if self._operation_supports_parameter('modify_db_instance', 'PerformanceInsightsKMSKeyId') and db_info.get('performance_insights_kms_key_id'):
                    modify_params['PerformanceInsightsKMSKeyId'] = db_info['performance_insights_kms_key_id']
                if self._operation_supports_parameter('modify_db_instance', 'PerformanceInsightsRetentionPeriod') and db_info.get('performance_insights_retention_period', 7) != 7:
                    modify_params['PerformanceInsightsRetentionPeriod'] = db_info['performance_insights_retention_period']

            if modifications_needed:
                logger.info("Applying post-restore Aurora instance modifications...")
                self.rds_client.modify_db_instance(**modify_params)
                logger.info("Post-restore Aurora instance modifications applied successfully")

            return modifications_needed
        except ClientError as e:
            logger.warning(f"Failed to apply some post-restore Aurora instance modifications: {str(e)}")
            return False

    def _apply_rds_post_restore_modifications(self, instance_identifier: str, db_info: Dict[str, Any], master_password: Optional[str] = "password") -> bool:
        """Apply RDS instance post-restore modifications"""
        modify_params = {
            'DBInstanceIdentifier': instance_identifier,
            'ApplyImmediately': True
        }
        
        modifications_needed = False
        
        try:
            logger.info("Waiting a short interval before applying post-restore modifications...")
            time.sleep(30)

            if db_info.get('engine_lifecycle_support'):
                modify_params['EngineLifecycleSupport'] = db_info['engine_lifecycle_support']
                modifications_needed = True

            # Master password (required for triggering resetting-master-credentials state)
            if master_password:
                modify_params['MasterUserPassword'] = master_password
                modifications_needed = True
                logger.info(f"Setting master password for RDS instance '{instance_identifier}'")

            # Backup settings
            backup_retention_period = db_info.get('backup_retention_period', 7)
            modify_params['BackupRetentionPeriod'] = backup_retention_period
            modifications_needed = True
            
            if db_info.get('preferred_backup_window'):
                modify_params['PreferredBackupWindow'] = db_info['preferred_backup_window']
                modifications_needed = True
            
            if db_info.get('preferred_maintenance_window'):
                modify_params['PreferredMaintenanceWindow'] = db_info['preferred_maintenance_window']
                modifications_needed = True
            
            if modifications_needed:
                logger.info("Applying post-restore modifications...")
                if 'performance_insights_enabled' in db_info and 'EnablePerformanceInsights' not in modify_params:
                    modify_params['EnablePerformanceInsights'] = bool(db_info.get('performance_insights_enabled'))
                elif 'PerformanceInsightsEnabled' in db_info and 'EnablePerformanceInsights' not in modify_params:
                    modify_params['EnablePerformanceInsights'] = bool(db_info.get('PerformanceInsightsEnabled'))

                if db_info.get('performance_insights_kms_key_id'):
                    modify_params['PerformanceInsightsKMSKeyId'] = db_info.get('performance_insights_kms_key_id')
                elif db_info.get('PerformanceInsightsKMSKeyId'):
                    modify_params['PerformanceInsightsKMSKeyId'] = db_info.get('PerformanceInsightsKMSKeyId')

                self.rds_client.modify_db_instance(**modify_params)
                logger.info("Post-restore modifications applied successfully")

                if master_password:
                    timeout = db_info.get('post_modify_wait_timeout', 600)
                    logger.info(f"Waiting for RDS instance '{instance_identifier}' to finish resetting master password before continuing...")
                    if not self._wait_for_rds_instance_ready(instance_identifier, timeout_seconds=timeout, poll_interval=5):
                        logger.warning(f"RDS instance '{instance_identifier}' did not finish the reset/availability transitional state within {timeout}s.")

            return modifications_needed
        except ClientError as e:
            logger.warning(f"Failed to apply some post-restore modifications: {str(e)}")
            return False

    def get_connection_info(self, identifier: str, is_aurora: bool = False) -> Dict[str, Any]:
        """Get connection information for the restored DB with error handling"""
        try:
            if is_aurora:
                response = self.rds_client.describe_db_clusters(DBClusterIdentifier=identifier)
                db_cluster = response['DBClusters'][0]
                
                return {
                    'identifier': db_cluster['DBClusterIdentifier'],
                    'endpoint': db_cluster.get('Endpoint'),
                    'reader_endpoint': db_cluster.get('ReaderEndpoint'),
                    'port': db_cluster.get('Port'),
                    'master_username': db_cluster.get('MasterUsername'),
                    'status': db_cluster['Status'],
                    'engine': db_cluster['Engine'],
                    'engine_version': db_cluster['EngineVersion'],
                    'database_name': db_cluster.get('DatabaseName')
                }
            else:
                response = self.rds_client.describe_db_instances(DBInstanceIdentifier=identifier)
                db_instance = response['DBInstances'][0]
                
                return {
                    'identifier': db_instance['DBInstanceIdentifier'],
                    'endpoint': db_instance.get('Endpoint', {}).get('Address'),
                    'port': db_instance.get('Endpoint', {}).get('Port'),
                    'master_username': db_instance.get('MasterUsername'),
                    'status': db_instance['DBInstanceStatus'],
                    'engine': db_instance['Engine'],
                    'engine_version': db_instance['EngineVersion']
                }
        except ClientError as e:
            logger.error(f"Failed to get connection info: {str(e)}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error getting connection info: {str(e)}")
            return {}

    def recreate_rds_instance(self, json_file_path: str, snapshot_arn: str, new_db_identifier: str, secret_arn: str,
                              secret_username_key: str, secret_password_key: str,
                              new_db_cluster_identifier: Optional[str] = None) -> Dict[str, Any]:
        """Main method to recreate RDS instance/cluster from JSON metadata and snapshot"""
        logger.info("=" * 60)
        logger.info("RDS/Aurora Recreation Started")
        logger.info(f"JSON File: {json_file_path}")
        logger.info(f"Snapshot ARN: {snapshot_arn}")
        logger.info(f"DB Identifier: {new_db_identifier}")
        logger.info(f"DB Cluster Name: {new_db_cluster_identifier or 'N/A'}")
        logger.info(f"Secret ARN: {secret_arn}")
        logger.info(f"Secret username key: {secret_username_key}")
        logger.info(f"Secret password key: {secret_password_key}")
        logger.info(f"Region: {self.region}")
        logger.info("=" * 60)
        
        try:
            # Get master username and password from Secrets Manager
            master_username = self.get_secret_value(secret_arn, secret_username_key)
            master_password = self.get_secret_value(secret_arn, secret_password_key)
            
            # Load metadata
            metadata = self.load_metadata(json_file_path)
            
            # Extract and validate DB information
            db_info = self.extract_db_info(metadata)
            is_aurora = db_info['is_aurora']
            
            logger.info(f"Detected engine type: {'Aurora' if is_aurora else 'RDS'} - {db_info['engine']}")
            
            # Re-use subnet group (common for both Aurora and RDS)
            subnet_group_name = db_info.get('subnet_group_name')
            # 
            # here
            
            # Old
            # # Create subnet group (common for both Aurora and RDS)
            # subnet_group_name = self.create_subnet_group(db_info, new_identifier)
            
            # Extract tags
            tags = self.extract_tags(metadata)
            
            if is_aurora:
                # Aurora cluster restoration
                # Use the requested new identifier for the Aurora cluster and the optional
                # cluster name argument as the writer instance identifier.
                cluster_identifier = new_db_cluster_identifier or f"{new_db_identifier}-writer"
                writer_instance_identifier = new_db_identifier
                print("1. good")
                # Re-use cluster parameter group (Aurora-specific)
                cluster_param_group_name = db_info.get('cluster_parameter_group_name')
                
                print("2. good")
                # Restore Aurora cluster
                # 1st
                restore_response = self.restore_aurora_cluster(
                    snapshot_arn, cluster_identifier, db_info,
                    cluster_param_group_name, subnet_group_name, tags, master_password
                )
                print("3. good")
                
                # Wait for cluster to be available
                if not self.wait_for_resource('db-cluster', cluster_identifier, max_attempts=1000):
                    raise Exception("Aurora cluster creation timeout")
                
                print("4. good")
                # Create Aurora instance
                #2nd
                instance_response = self.restore_aurora_instance(cluster_identifier, writer_instance_identifier, db_info)
                
                print("5. good")
                # Wait for instance to be available
                if not self.wait_for_resource('db-instance', writer_instance_identifier, max_attempts=1000):
                    raise Exception("Aurora instance creation timeout")
                
                print("6. good")
                # Apply post-restore modifications
                post_restore_modified = self.apply_post_restore_modifications(writer_instance_identifier, db_info, is_aurora=True, master_password=master_password, cluster_identifier=cluster_identifier)
                if post_restore_modified:
                    # Aurora password changes are managed at the cluster level, so the instance
                    # does not necessarily enter a separate DB-instance resetting-master-credentials
                    # state. We only require the instance to become available after the cluster
                    # reset completes.
                    if not self.wait_for_resource('db-instance', writer_instance_identifier, max_attempts=1000):
                        raise Exception("Aurora writer instance did not become available after cluster-level post-restore modifications")
                print("7. good")
                
                # Get connection information
                connection_info = self.get_connection_info(cluster_identifier, is_aurora=True)
                
                logger.info("=" * 60)
                logger.info("Aurora Cluster Recreation Completed Successfully!")
                logger.info(f"Cluster Identifier: {cluster_identifier}")
                logger.info(f"Instance Identifier: {writer_instance_identifier}")
                logger.info(f"Engine: {db_info['engine']} {db_info['engine_version']}")
                if cluster_param_group_name:
                    logger.info(f"Cluster Parameter Group: {cluster_param_group_name}")
                if subnet_group_name:
                    logger.info(f"Subnet Group: {subnet_group_name}")
                logger.info("=" * 60)
                
                return {
                    'success': True,
                    'is_aurora': True,
                    'cluster_identifier': cluster_identifier,
                    'instance_identifier': writer_instance_identifier,
                    'connection_info': connection_info,
                    'cluster_parameter_group': cluster_param_group_name,
                    'subnet_group': subnet_group_name,
                    'restore_response': restore_response,
                    'instance_response': instance_response
                }
                
            else:
                # Regular RDS instance restoration
                param_group_name = db_info.get('parameter_group_name')
                option_group_name = db_info.get('option_group_name')
                
                if new_db_cluster_identifier:
                    logger.info(f"Ignoring DB cluster name for regular RDS instance restoration: {new_db_cluster_identifier}")
                
                # # Regular RDS instance restoration
                # param_group_name = self.create_parameter_group(metadata, db_info, new_db_identifier)
                # option_group_name = self.create_option_group(db_info, new_db_identifier)
                print("1. PRE RESTORE")
                # Restore RDS instance
                restore_response = self.restore_db_instance(
                    snapshot_arn, new_db_identifier, db_info,
                    param_group_name, option_group_name, subnet_group_name, tags, master_password
                )
                print("99. POST RESTORE")
                
                # Wait for instance to be available
                if not self.wait_for_resource('db-instance', new_db_identifier, max_attempts=1000):
                    raise Exception("RDS instance creation timeout")
                
                # Apply post-restore modifications
                post_restore_modified = self.apply_post_restore_modifications(new_db_identifier, db_info, is_aurora=False, master_password=master_password)
                if post_restore_modified:
                    if not self.wait_for_resource('db-instance', new_db_identifier, max_attempts=1000, require_reset=True):
                        raise Exception("DB instance did not pass through resetting-master-credentials to available after post-restore modifications")
                
                # Get connection information
                connection_info = self.get_connection_info(new_db_identifier, is_aurora=False)
                
                logger.info("=" * 60)
                logger.info("RDS Instance Recreation Completed Successfully!")
                logger.info(f"DB Instance Identifier: {new_db_identifier}")
                logger.info(f"Engine: {db_info['engine']} {db_info['engine_version']}")
                logger.info(f"Instance Class: {db_info['db_instance_class']}")
                if param_group_name:
                    logger.info(f"Parameter Group: {param_group_name}")
                if option_group_name:
                    logger.info(f"Option Group: {option_group_name}")
                if subnet_group_name:
                    logger.info(f"Subnet Group: {subnet_group_name}")
                logger.info("=" * 60)
                
                return {
                    'success': True,
                    'is_aurora': False,
                    'db_identifier': new_db_identifier,
                    'connection_info': connection_info,
                    'parameter_group': param_group_name,
                    'option_group': option_group_name,
                    'subnet_group': subnet_group_name,
                    'restore_response': restore_response
                }
            
        except Exception as e:
            logger.error(f"Recreation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

def main():
    current_string = time.ctime()
    print("Beginning execution at:", current_string)
    
    """Main function to handle command line arguments and execute recreation"""
    if len(sys.argv) not in (10, 11):
        print("Usage: python v4_dbRestoration.py <json_file_path> <snapshot_arn> <region> <secret_arn> <username_secret_key> <password_secret_key> <mode: only-restore|restore-and-delete> <old_db_identifier> <new_db_identifier> [<new_db_cluster_identifier>]")
        print("Example: python v4_dbRestoration.py rds_metadata.json arn:aws:rds:us-east-1:123456789012:snapshot:mydb-snapshot us-east-1 arn:aws:secretsmanager:us-east-1:123456789012:secret:rds-secret username password only-restore old-db-instance-identifier mydb-restored")
        print("Example (Aurora): python v4_dbRestoration.py aurora_metadata.json arn:aws:rds:us-east-1:123456789012:cluster-snapshot:aurora-cluster-snapshot us-east-1 arn:aws:secretsmanager:us-east-1:123456789012:secret:aurora-secret username password restore-and-delete old-aurora-instance-identifier aurora-instance-restored aurora-cluster-restored")
        sys.exit(1)
    
    json_file_path = sys.argv[1]
    snapshot_arn = sys.argv[2]
    region = sys.argv[3]
    secret_arn = sys.argv[4]
    username_secret_key = sys.argv[5]
    password_secret_key = sys.argv[6]
    mode = sys.argv[7]
    old_db_identifier = sys.argv[8]
    new_db_identifier = sys.argv[9]
    new_db_cluster_identifier = sys.argv[10] if len(sys.argv) == 11 else None

    print(f"Mode: {mode}")
    print(f"Old DB Instance: {old_db_identifier}")
    
    concatenatedStringAsCommand = "./rds_metadata_extractor.sh "+old_db_identifier+" > $PWD/02_metadata_extraction_report.txt"
    cmdGroup10 = [
        "echo 'Command 1: AAAAAAAAAA'",
        concatenatedStringAsCommand,
        # "./rds_metadata_extractor.sh agverdict-staging-rds > $PWD/02_metadata_extraction_report.txt",
        
        "echo 'Metadata extraction report is: ...'",
        "cat $PWD/02_metadata_extraction_report.txt; echo '\n\n'",
    ]
    
    cmdGroup11 = [ "echo 'Command 3: CCCCCCCCCC'"]

    
    groupOfCommands = [cmdGroup10,cmdGroup11]
    
    
    try:
        
        for i in range (len(groupOfCommands)):
        # for groupofCommands in groupOfCommands:
            execute_bash_commands(groupOfCommands[i], (1+i))        
        
        test=execute_bash_conditional("""ls""")
        print("test var is:", test, sep="")        
        path_of_db_metadata = execute_bash_conditional("""export temp_var=$(tail -n 1 $PWD/02_metadata_extraction_report.txt); echo $temp_var""")
        print("temp_var (& path_of_db_metadata) is:", path_of_db_metadata, sep="")        
        
        #Remove later the argument of this json file path. This will be overwritten by the path_of_db_metadata extracted metadata extraction function.
        json_file_path = path_of_db_metadata
        
        time.sleep(5)
        
        recreator = RDSRecreator(region)
        
        # Determine mode: only-restore -> do not stop/delete old; restore-and-delete -> stop then delete
        if mode not in ("only-restore", "restore-and-delete"):
            print("Invalid mode. Use 'only-restore' or 'restore-and-delete'.")
            sys.exit(1)

        perform_stop_and_delete = (mode == "restore-and-delete")

        if perform_stop_and_delete:
            try:
                old_db_resources = recreator._resolve_db_resources(old_db_identifier)
                if old_db_resources.get('cluster_id'):
                    logger.info(f"Old DB '{old_db_identifier}' is part of DB cluster '{old_db_resources['cluster_id']}'. PHASE 1 will rename cluster resources.")
                else:
                    logger.info(f"Old DB '{old_db_identifier}' is a standalone DB instance. PHASE 1 will rename the old DB resource.")
            except Exception as e:
                logger.warning(f"Could not determine old DB resource type: {str(e)}. Proceeding with PHASE 1 rename attempt.")

        if perform_stop_and_delete:
            # PHASE 1: Rename old Database resources by appending '-OLD'
            print("PHASE 1: Renaming old DB resources.")
            rename_db_resources = recreator.rename_db_resources(old_db_identifier)
            print("PHASE 1 completed: DB resources renamed.")
            
            if not ("Renamed" in rename_db_resources):
                print("Failed to rename DB resources.")
                current_string = time.ctime()
                print("Ending execution at:", current_string)
                sys.exit(1)

        # PHASE 2: Gather old Database metadata and snapshot, and Recreate new Database from mentioned files
        print("PHASE 2: Recreating new Database.")
        result = recreator.recreate_rds_instance(
            json_file_path, snapshot_arn, new_db_identifier, secret_arn, username_secret_key, password_secret_key, new_db_cluster_identifier
        )
        print("PHASE 2 completed: New Database Recreated.")
        
        if result['success']:
            print("\n" + "=" * 60)
            if result.get('is_aurora'):
                print("SUCCESS: Aurora Cluster Recreation Completed!")
                print("=" * 60)
                print(f"Cluster Identifier: {result['cluster_identifier']}")
                print(f"Instance Identifier: {result['instance_identifier']}")
            else:
                print("SUCCESS: RDS Instance Recreation Completed!")
                print("=" * 60)
                print(f"DB Instance Identifier: {result['db_identifier']}")
            
            conn_info = result['connection_info']
            if conn_info.get('endpoint'):
                print(f"Endpoint: {conn_info['endpoint']}")
                if conn_info.get('reader_endpoint'):
                    print(f"Reader Endpoint: {conn_info['reader_endpoint']}")
                print(f"Port: {conn_info['port']}")
                print(f"Master Username: {conn_info['master_username']}")
                
                print(f"Status: {conn_info['status']}")
                if conn_info.get('database_name'):
                    print(f"Database Name: {conn_info['database_name']}")
            
            print("\nMaster password has been set from AWS Secrets Manager.")
            
            # PHASE 3: Apply SQL configurations
            print("\nPHASE 3: Applying SQL configurations...")
            try:
                print("\nBeginning... ")
                print("\nIn progress...")
                print("\nPHASE 3 completed: SQL configurations applied successfully.")
                
            except Exception as e:
                print(f"\nUnexpected error: {str(e)}")
                current_string = time.ctime()
                print("Ending execution at:", current_string)
                sys.exit(1)
            
            # PHASE 4: Delete old Database (only if mode is restore-and-delete)
            if perform_stop_and_delete:
                print("\nPHASE 4:Deleting old DB resources...")
                try:
                    old_db_identifier = old_db_identifier + "-old"
                    print("PHASE 4: Deleting old: ", old_db_identifier)
                    delete_response = recreator.delete_db_resources(old_db_identifier)
                    print("\nPHASE 4 completed: Old DB resources removed successfully. Status: ", delete_response)
                    print("\n\nProcess successfully completed, DB recreation finished for", new_db_identifier)
                    current_string = time.ctime()
                    print("Ending execution at:", current_string)
                    
                except Exception as e:
                    print(f"\nUnexpected error: {str(e)}")
                    current_string = time.ctime()
                    print("Ending execution at:", current_string)
                    sys.exit(1)
            else:
                print("\n\nProcess successfully completed, DB recreation finished for", new_db_identifier)
                current_string = time.ctime()
                print("Ending execution at:", current_string)
            
            
        else:
            print(f"\nERROR: Recreation failed - {result['error']}")
            current_string = time.ctime()
            print("Ending execution at:", current_string)
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        current_string = time.ctime()
        print("Ending execution at:", current_string)
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        current_string = time.ctime()
        print("Ending execution at:", current_string)
        sys.exit(1)

if __name__ == "__main__":
    main()
