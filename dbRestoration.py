#!/usr/bin/env
## !/usr/bin/env python3

# # 1. Make sure AWS credentials are configured
# aws configure
# # or set environment variables
# export AWS_ACCESS_KEY_ID=your_access_key
# export AWS_SECRET_ACCESS_KEY=your_secret_key

# # 2. Basic usage
# python recreate_rds_from_json.py rds_metadata.json arn:aws:rds:us-east-1:123456789012:snapshot:mydb-snapshot mydb-restored us-east-1




# RDS Recreation Script from JSON Metadata and Snapshot using boto3 (with Aurora support)
# Usage: python recreate_rds_from_json.py <json_file_path> <snapshot_arn> <new_db_identifier> <region>
# """

import subprocess
from tqdm import tqdm

import json
import sys
import time
import logging
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError, NoCredentialsError





# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RDSRecreator:
    """Class to handle RDS instance recreation from JSON metadata and snapshot"""
    
    def __init__(self, region: str):
        """Initialize the RDS recreator with AWS clients"""
        try:
            self.region = region
            self.rds_client = boto3.client('rds', region_name=region)
            self.ec2_client = boto3.client('ec2', region_name=region)
            logger.info(f"Initialized AWS clients for region: {region}")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure your credentials.")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {str(e)}")
            raise

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

    def extract_db_instance_info(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Extract DB instance information from metadata"""
        try:
            db_instance = metadata.get('DBInstances', [{}])[0]
            
            info = {
                'engine': db_instance.get('Engine', ''),
                'engine_version': db_instance.get('EngineVersion', ''),
                'db_instance_class': db_instance.get('DBInstanceClass', 'db.t3.micro'),
                'allocated_storage': db_instance.get('AllocatedStorage', 20),
                'storage_type': db_instance.get('StorageType', 'gp2'),
                'storage_encrypted': db_instance.get('StorageEncrypted', False),
                'kms_key_id': db_instance.get('KmsKeyId'),
                'iops': db_instance.get('Iops'),
                'storage_throughput': db_instance.get('StorageThroughput'),
                'publicly_accessible': db_instance.get('PubliclyAccessible', False),
                'port': db_instance.get('DbInstancePort'),
                'availability_zone': db_instance.get('AvailabilityZone'),
                'multi_az': db_instance.get('MultiAZ', False),
                'backup_retention_period': db_instance.get('BackupRetentionPeriod', 7),
                'preferred_backup_window': db_instance.get('PreferredBackupWindow'),
                'preferred_maintenance_window': db_instance.get('PreferredMaintenanceWindow'),
                'auto_minor_version_upgrade': db_instance.get('AutoMinorVersionUpgrade', True),
                'deletion_protection': db_instance.get('DeletionProtection', False),
                'performance_insights_enabled': db_instance.get('PerformanceInsightsEnabled', False),
                'performance_insights_kms_key_id': db_instance.get('PerformanceInsightsKMSKeyId'),
                'performance_insights_retention_period': db_instance.get('PerformanceInsightsRetentionPeriod', 7),
                'monitoring_interval': db_instance.get('MonitoringInterval', 0),
                'monitoring_role_arn': db_instance.get('MonitoringRoleArn'),
                'iam_database_authentication_enabled': db_instance.get('IAMDatabaseAuthenticationEnabled', False),
                'license_model': db_instance.get('LicenseModel'),
                'character_set_name': db_instance.get('CharacterSetName'),
                'nchar_character_set_name': db_instance.get('NcharCharacterSetName'),
                'enabled_cloudwatch_logs_exports': db_instance.get('EnabledCloudwatchLogsExports', []),
                'processor_features': db_instance.get('ProcessorFeatures', []),
                'associated_roles': db_instance.get('AssociatedRoles', []),
                'domain_memberships': db_instance.get('DomainMemberships', [])
            }
            
            # Extract parameter groups
            param_groups = db_instance.get('DBParameterGroups', [])
            info['parameter_group_name'] = param_groups[0].get('DBParameterGroupName') if param_groups else None
            
            # Extract option groups
            option_groups = db_instance.get('OptionGroupMemberships', [])
            info['option_group_name'] = option_groups[0].get('OptionGroupName') if option_groups else None
            
            # Extract subnet group
            subnet_group = db_instance.get('DBSubnetGroup', {})
            info['subnet_group_name'] = subnet_group.get('DBSubnetGroupName')
            info['subnet_ids'] = [subnet.get('SubnetIdentifier') for subnet in subnet_group.get('Subnets', [])]
            
            # Extract VPC security groups
            vpc_security_groups = db_instance.get('VpcSecurityGroups', [])
            info['vpc_security_group_ids'] = [sg.get('VpcSecurityGroupId') for sg in vpc_security_groups]
            
            logger.info(f"Extracted DB instance info for engine: {info['engine']} {info['engine_version']}")
            return info
            
        except Exception as e:
            logger.error(f"Failed to extract DB instance info: {str(e)}")
            raise

    def get_parameter_group_family(self, engine: str, engine_version: str) -> str:
        """Determine the parameter group family based on engine and version"""
        family_map = {
            'mysql': f"mysql{'.'.join(engine_version.split('.')[:2])}",
            'postgres': f"postgres{engine_version.split('.')[0]}",
            'oracle-ee': f"oracle-ee-{'.'.join(engine_version.split('.')[:2])}",
            'oracle-se2': f"oracle-se2-{'.'.join(engine_version.split('.')[:2])}",
            'oracle-se1': f"oracle-se1-{'.'.join(engine_version.split('.')[:2])}",
            'sqlserver-ee': f"sqlserver-ee-{'.'.join(engine_version.split('.')[:2])}",
            'sqlserver-se': f"sqlserver-se-{'.'.join(engine_version.split('.')[:2])}",
            'sqlserver-ex': f"sqlserver-ex-{'.'.join(engine_version.split('.')[:2])}",
            'sqlserver-web': f"sqlserver-web-{'.'.join(engine_version.split('.')[:2])}",
            'mariadb': f"mariadb{'.'.join(engine_version.split('.')[:2])}"
        }
        return family_map.get(engine, f"{engine}{'.'.join(engine_version.split('.')[:2])}")

    def wait_for_resource(self, resource_type: str, resource_name: str, max_attempts: int = 60) -> bool:
        """Wait for a resource to become available"""
        logger.info(f"Waiting for {resource_type} '{resource_name}' to be available...")
        
        for attempt in range(max_attempts):
            try:
                if resource_type == 'parameter-group':
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
                elif resource_type == 'db-instance':
                    response = self.rds_client.describe_db_instances(DBInstanceIdentifier=resource_name)
                    status = response['DBInstances'][0]['DBInstanceStatus']
                    if status == 'available':
                        logger.info(f"DB instance '{resource_name}' is available")
                        return True
                    logger.info(f"DB instance status: {status}")
                    
            except ClientError as e:
                if resource_type == 'db-instance' and e.response['Error']['Code'] != 'DBInstanceNotFound':
                    logger.warning(f"Error checking {resource_type}: {str(e)}")
            except Exception as e:
                logger.warning(f"Error checking {resource_type}: {str(e)}")
            
            time.sleep(30)
            logger.info(f"Attempt {attempt + 1}/{max_attempts} - still waiting...")
        
        logger.error(f"Timeout waiting for {resource_type} '{resource_name}'")
        return False

    def create_parameter_group(self, metadata: Dict[str, Any], db_info: Dict[str, Any], new_db_identifier: str) -> Optional[str]:
        """Create a custom parameter group if needed"""
        param_group_name = db_info.get('parameter_group_name')
        
        if not param_group_name or param_group_name.startswith('default.'):
            logger.info("Using default parameter group")
            return None
        
        new_param_group_name = f"{new_db_identifier}-params"
        param_group_family = self.get_parameter_group_family(db_info['engine'], db_info['engine_version'])
        
        try:
            logger.info(f"Creating parameter group: {new_param_group_name}")
            self.rds_client.create_db_parameter_group(
                DBParameterGroupName=new_param_group_name,
                DBParameterGroupFamily=param_group_family,
                Description=f"Parameter group for {new_db_identifier}"
            )
            
            if not self.wait_for_resource('parameter-group', new_param_group_name):
                raise Exception("Parameter group creation timeout")
            
            # Apply custom parameters if they exist
            parameters = metadata.get('Parameters', [])
            if parameters:
                logger.info("Applying custom parameters...")
                modifiable_params = []
                
                for param in parameters:
                    if param.get('IsModifiable', False) and param.get('ParameterValue') is not None:
                        modifiable_params.append({
                            'ParameterName': param['ParameterName'],
                            'ParameterValue': str(param['ParameterValue']),
                            'ApplyMethod': param.get('ApplyMethod', 'immediate')
                        })
                
                if modifiable_params:
                    # Apply parameters in batches of 20 (AWS limit)
                    for i in range(0, len(modifiable_params), 20):
                        batch = modifiable_params[i:i+20]
                        try:
                            self.rds_client.modify_db_parameter_group(
                                DBParameterGroupName=new_param_group_name,
                                Parameters=batch
                            )
                            logger.info(f"Applied {len(batch)} parameters")
                        except ClientError as e:
                            logger.warning(f"Failed to apply parameter batch: {str(e)}")
            
            return new_param_group_name
            
        except ClientError as e:
            logger.error(f"Failed to create parameter group: {str(e)}")
            raise

    def create_option_group(self, db_info: Dict[str, Any], new_db_identifier: str) -> Optional[str]:
        """Create a custom option group if needed (Oracle/SQL Server only)"""
        option_group_name = db_info.get('option_group_name')
        engine = db_info['engine']
        
        if not option_group_name or option_group_name.startswith('default:') or not engine.startswith(('oracle', 'sqlserver')):
            logger.info("No custom option group needed or using default")
            return None
        
        new_option_group_name = f"{new_db_identifier}-options"
        major_engine_version = '.'.join(db_info['engine_version'].split('.')[:2])
        
        try:
            logger.info(f"Creating option group: {new_option_group_name}")
            self.rds_client.create_option_group(
                OptionGroupName=new_option_group_name,
                EngineName=engine,
                MajorEngineVersion=major_engine_version,
                OptionGroupDescription=f"Option group for {new_db_identifier}"
            )
            
            if not self.wait_for_resource('option-group', new_option_group_name):
                raise Exception("Option group creation timeout")
            
            return new_option_group_name
            
        except ClientError as e:
            logger.error(f"Failed to create option group: {str(e)}")
            raise

    def create_subnet_group(self, db_info: Dict[str, Any], new_db_identifier: str) -> Optional[str]:
        """Create a custom subnet group if needed"""
        subnet_group_name = db_info.get('subnet_group_name')
        subnet_ids = db_info.get('subnet_ids', [])
        
        if not subnet_group_name or subnet_group_name == 'default' or not subnet_ids:
            logger.info("Using default subnet group or no subnets specified")
            return None
        
        new_subnet_group_name = f"{new_db_identifier}-subnet-group"
        
        try:
            logger.info(f"Creating subnet group: {new_subnet_group_name}")
            self.rds_client.create_db_subnet_group(
                DBSubnetGroupName=new_subnet_group_name,
                DBSubnetGroupDescription=f"Subnet group for {new_db_identifier}",
                SubnetIds=subnet_ids
            )
            
            if not self.wait_for_resource('subnet-group', new_subnet_group_name):
                raise Exception("Subnet group creation timeout")
            
            return new_subnet_group_name
            
        except ClientError as e:
            logger.error(f"Failed to create subnet group: {str(e)}")
            raise

    def extract_tags(self, metadata: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract tags from metadata"""
        tags = metadata.get('Tags', [])
        return [{'Key': tag['Key'], 'Value': tag['Value']} for tag in tags if 'Key' in tag and 'Value' in tag]

    def restore_db_instance(self, snapshot_arn: str, new_db_identifier: str, db_info: Dict[str, Any], 
                          param_group_name: Optional[str], option_group_name: Optional[str], 
                          subnet_group_name: Optional[str], tags: List[Dict[str, str]]) -> Dict[str, Any]:
        """Restore DB instance from snapshot with all configurations"""
        
        restore_params = {
            'DBInstanceIdentifier': new_db_identifier,
            'DBSnapshotIdentifier': snapshot_arn,
            'DBInstanceClass': db_info['db_instance_class']
        }
        
        # Storage parameters
        if db_info['storage_type']:
            restore_params['StorageType'] = db_info['storage_type']
        
        if db_info['storage_encrypted'] and db_info['kms_key_id']:
            restore_params['KmsKeyId'] = db_info['kms_key_id']
        
        if db_info['iops'] and db_info['iops'] > 0:
            restore_params['Iops'] = db_info['iops']
        
        if db_info['storage_throughput'] and db_info['storage_throughput'] > 0:
            restore_params['StorageThroughput'] = db_info['storage_throughput']
        
        # Network parameters
        if db_info['port']:
            restore_params['Port'] = db_info['port']
        
        if db_info['availability_zone']:
            restore_params['AvailabilityZone'] = db_info['availability_zone']
        
        restore_params['PubliclyAccessible'] = db_info['publicly_accessible']
        restore_params['MultiAZ'] = db_info['multi_az']
        
        # Parameter and Option Groups
        if param_group_name:
            restore_params['DBParameterGroupName'] = param_group_name
        
        if option_group_name:
            restore_params['OptionGroupName'] = option_group_name
        
        if subnet_group_name:
            restore_params['DBSubnetGroupName'] = subnet_group_name
        
        # Security Groups
        if db_info['vpc_security_group_ids']:
            restore_params['VpcSecurityGroupIds'] = [sg for sg in db_info['vpc_security_group_ids'] if sg]
        
        # License and Character Set
        if db_info['license_model']:
            restore_params['LicenseModel'] = db_info['license_model']
        
        if db_info['character_set_name']:
            restore_params['CharacterSetName'] = db_info['character_set_name']
        
        if db_info['nchar_character_set_name']:
            restore_params['NcharCharacterSetName'] = db_info['nchar_character_set_name']
        
        # Advanced Features
        restore_params['AutoMinorVersionUpgrade'] = db_info['auto_minor_version_upgrade']
        restore_params['DeletionProtection'] = db_info['deletion_protection']
        restore_params['EnableIAMDatabaseAuthentication'] = db_info['iam_database_authentication_enabled']
        
        # Performance Insights
        if db_info['performance_insights_enabled']:
            restore_params['EnablePerformanceInsights'] = True
            if db_info['performance_insights_kms_key_id']:
                restore_params['PerformanceInsightsKMSKeyId'] = db_info['performance_insights_kms_key_id']
            if db_info['performance_insights_retention_period'] != 7:
                restore_params['PerformanceInsightsRetentionPeriod'] = db_info['performance_insights_retention_period']
        
        # Enhanced Monitoring
        if db_info['monitoring_interval'] > 0:
            restore_params['MonitoringInterval'] = db_info['monitoring_interval']
            if db_info['monitoring_role_arn']:
                restore_params['MonitoringRoleArn'] = db_info['monitoring_role_arn']
        
        # CloudWatch Logs
        if db_info['enabled_cloudwatch_logs_exports']:
            restore_params['EnableCloudwatchLogsExports'] = db_info['enabled_cloudwatch_logs_exports']
        
        # Processor Features
        if db_info['processor_features']:
            restore_params['ProcessorFeatures'] = db_info['processor_features']
        
        # Tags
        if tags:
            restore_params['Tags'] = tags
        
        try:
            logger.info(f"Restoring DB instance: {new_db_identifier}")
            logger.info(f"Restore parameters: {json.dumps({k: v for k, v in restore_params.items() if k not in ['Tags']}, indent=2)}")
            
            response = self.rds_client.restore_db_instance_from_db_snapshot(**restore_params)
            logger.info("DB instance restore initiated successfully")
            return response
            
        except ClientError as e:
            logger.error(f"Failed to restore DB instance: {str(e)}")
            raise

    def apply_post_restore_modifications(self, new_db_identifier: str, db_info: Dict[str, Any]) -> None:
        """Apply modifications that can't be set during restore"""
        modify_params = {
            'DBInstanceIdentifier': new_db_identifier,
            'ApplyImmediately': True
        }
        
        modifications_needed = False
        
        # Backup settings
        if db_info['backup_retention_period'] != 7:
            modify_params['BackupRetentionPeriod'] = db_info['backup_retention_period']
            modifications_needed = True
        
        if db_info['preferred_backup_window']:
            modify_params['PreferredBackupWindow'] = db_info['preferred_backup_window']
            modifications_needed = True
        
        if db_info['preferred_maintenance_window']:
            modify_params['PreferredMaintenanceWindow'] = db_info['preferred_maintenance_window']
            modifications_needed = True
        
        if modifications_needed:
            try:
                logger.info("Applying post-restore modifications...")
                self.rds_client.modify_db_instance(**modify_params)
                logger.info("Post-restore modifications applied successfully")
            except ClientError as e:
                logger.warning(f"Failed to apply some post-restore modifications: {str(e)}")

    def get_connection_info(self, db_identifier: str) -> Dict[str, Any]:
        """Get connection information for the restored DB instance"""
        try:
            response = self.rds_client.describe_db_instances(DBInstanceIdentifier=db_identifier)
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

    def recreate_rds_instance(self, json_file_path: str, snapshot_arn: str, new_db_identifier: str) -> Dict[str, Any]:
        """Main method to recreate RDS instance from JSON metadata and snapshot"""
        logger.info("=" * 60)
        logger.info("RDS Instance Recreation Started")
        logger.info(f"JSON File: {json_file_path}")
        logger.info(f"Snapshot ARN: {snapshot_arn}")
        logger.info(f"New DB Identifier: {new_db_identifier}")
        logger.info(f"Region: {self.region}")
        logger.info("=" * 60)
        
        try:
            # Load metadata
            metadata = self.load_metadata(json_file_path)
            
            # Extract DB instance information
            db_info = self.extract_db_instance_info(metadata)
            
            # Create parameter group
            param_group_name = self.create_parameter_group(metadata, db_info, new_db_identifier)
            
            # Create option group
            option_group_name = self.create_option_group(db_info, new_db_identifier)
            
            # Create subnet group
            subnet_group_name = self.create_subnet_group(db_info, new_db_identifier)
            
            # Extract tags
            tags = self.extract_tags(metadata)
            
            # Restore DB instance
            restore_response = self.restore_db_instance(
                snapshot_arn, new_db_identifier, db_info,
                param_group_name, option_group_name, subnet_group_name, tags
            )
            
            # Wait for DB instance to be available
            if not self.wait_for_resource('db-instance', new_db_identifier, max_attempts=120):
                raise Exception("DB instance creation timeout")
            
            # Apply post-restore modifications
            self.apply_post_restore_modifications(new_db_identifier, db_info)
            
            # Get connection information
            connection_info = self.get_connection_info(new_db_identifier)
            
            logger.info("=" * 60)
            logger.info("RDS Instance Recreation Completed Successfully!")
            logger.info(f"New DB Instance Identifier: {new_db_identifier}")
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
                'db_identifier': new_db_identifier,
                'connection_info': connection_info,
                'parameter_group': param_group_name,
                'option_group': option_group_name,
                'subnet_group': subnet_group_name,
                'restore_response': restore_response
            }
            
        except Exception as e:
            logger.error(f"RDS recreation failed: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

def main():
    """Main function to handle command line arguments and execute recreation"""
    if len(sys.argv) != 5:
        print("Usage: python recreate_rds_from_json.py <json_file_path> <snapshot_arn> <new_db_identifier> <region>")
        print("Example: python recreate_rds_from_json.py rds_metadata.json arn:aws:rds:us-east-1:123456789012:snapshot:mydb-snapshot mydb-restored us-east-1")
        sys.exit(1)
    
    json_file_path = sys.argv[1]
    snapshot_arn = sys.argv[2]
    new_db_identifier = sys.argv[3]
    region = sys.argv[4]
    
    try:
        recreator = RDSRecreator(region)
        result = recreator.recreate_rds_instance(json_file_path, snapshot_arn, new_db_identifier)
        
        if result['success']:
            print("\n" + "=" * 60)
            print("SUCCESS: RDS Instance Recreation Completed!")
            print("=" * 60)
            print(f"DB Instance Identifier: {result['db_identifier']}")
            
            conn_info = result['connection_info']
            if conn_info.get('endpoint'):
                print(f"Endpoint: {conn_info['endpoint']}")
                print(f"Port: {conn_info['port']}")
                print(f"Master Username: {conn_info['master_username']}")
                print(f"Status: {conn_info['status']}")
            
            print("\nNote: The master password will need to be reset as it's not stored in the metadata.")
            print("You can reset it using the AWS Console or CLI modify-db-instance command.")
        else:
            print(f"\nERROR: RDS recreation failed - {result['error']}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
