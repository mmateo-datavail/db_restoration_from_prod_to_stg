#!/bin/bash

# RDS PostgreSQL Metadata Extraction Script with Enhanced AWS Authentication

# 1. Allow execution permissions for this DB metadata extraction script:
# chmod +x rds_metadata_extractor.sh

# 2. AWS Authentication Options:
#    Option A: Export AWS credentials (will override aws configure if set)
#    export AWS_ACCESS_KEY_ID="your-access-key"
#    export AWS_SECRET_ACCESS_KEY="your-secret-key"
#    export AWS_DEFAULT_REGION="your-region"  # optional, can also be provided as a command line argument"
#    
#    Option B: Use AWS configure (if credentials not exported)
#    aws configure set aws_access_key_id your-access-key
#    aws configure set aws_secret_access_key your-secret-key
#    aws configure set default.region your-region

# 3. Authenticate with AWS STS get-caller-identity
# aws sts get-caller-identity

# 4. Execute the script with: <DB identifier> and <region> as arguments.

# Usage:   ./rds_metadata_extractor.sh <db-identifier> [region]
# Or...
# Usage:   sh rds_metadata_extractor.sh <db-identifier> [region]

# Example: ./rds_metadata_extractor.sh agverdict-staging-rds us-west-2
# Or...
# Example: sh rds_metadata_extractor.sh agverdict-staging-rds us-west-2

set -e

# =============================================================================
# AWS AUTHENTICATION SETUP
# =============================================================================

setup_aws_credentials() {
    echo "Setting up AWS credentials..."
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        echo "❌ ERROR: AWS CLI is not installed or not in PATH"
        echo "Please install AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        exit 1
    fi
    
    # Check for exported environment variables first
    if [[ -n "$AWS_ACCESS_KEY_ID" && -n "$AWS_SECRET_ACCESS_KEY" ]]; then
        echo "✓ Using exported AWS credentials (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY)"
        
        # Optionally set session token if provided
        if [[ -n "$AWS_SESSION_TOKEN" ]]; then
            echo "✓ AWS_SESSION_TOKEN also detected"
        fi
        
        # Set default region from environment if available
        if [[ -n "$AWS_DEFAULT_REGION" ]]; then
            echo "✓ Using AWS_DEFAULT_REGION: $AWS_DEFAULT_REGION"
        fi
        
        return 0
    fi
    
    # Check if AWS configure has been set up
    if aws configure list &> /dev/null; then
        local access_key=$(aws configure get aws_access_key_id 2>/dev/null || echo "")
        local secret_key=$(aws configure get aws_secret_access_key 2>/dev/null || echo "")
        
        if [[ -n "$access_key" && -n "$secret_key" ]]; then
            echo "✓ Using AWS configure credentials"
            
            # Get configured region
            local configured_region=$(aws configure get region 2>/dev/null || echo "")
            if [[ -n "$configured_region" ]]; then
                echo "✓ Using configured region: $configured_region"
            fi
            
            return 0
        fi
    fi
    
    # No credentials found
    echo "❌ ERROR: No AWS credentials found!"
    echo ""
    echo "Please set up AWS credentials using one of these methods:"
    echo ""
    echo "Method 1 - Export environment variables:"
    echo "  export AWS_ACCESS_KEY_ID='your-access-key'"
    echo "  export AWS_SECRET_ACCESS_KEY='your-secret-key'"
    echo "  export AWS_DEFAULT_REGION='your-region'  # optional"
    echo ""
    echo "Method 2 - Use AWS configure:"
    echo "  aws configure set aws_access_key_id your-access-key"
    echo "  aws configure set aws_secret_access_key your-secret-key"
    echo "  aws configure set default.region your-region"
    echo ""
    echo "Method 3 - Use AWS configure interactively:"
    echo "  aws configure"
    echo ""
    exit 1
}

# =============================================================================
# REGION SETUP
# =============================================================================

setup_region() {
    local provided_region="$1"
    
    # Priority order for region selection:
    # 1. Command line argument
    # 2. AWS_DEFAULT_REGION environment variable
    # 3. AWS configure default region
    # 4. Prompt user for region
    
    if [[ -n "$provided_region" ]]; then
        REGION="$provided_region"
        echo "✓ Using region from command line: $REGION"
    elif [[ -n "$AWS_DEFAULT_REGION" ]]; then
        REGION="$AWS_DEFAULT_REGION"
        echo "✓ Using region from AWS_DEFAULT_REGION: $REGION"
    else
        local configured_region=$(aws configure get region 2>/dev/null || echo "")
        if [[ -n "$configured_region" ]]; then
            REGION="$configured_region"
            echo "✓ Using region from AWS configure: $REGION"
        else
            echo "⚠️  No region specified. Please provide a region:"
            echo "Common regions: us-east-1, us-west-2, eu-west-1, ap-southeast-1"
            read -p "Enter AWS region: " REGION
            
            if [[ -z "$REGION" ]]; then
                echo "❌ ERROR: Region is required"
                exit 1
            fi
        fi
    fi
    
    # Validate region format (basic check)
    if [[ ! "$REGION" =~ ^[a-z]{2}-[a-z]+-[0-9]+$ ]]; then
        echo "⚠️  Warning: Region format '$REGION' may be invalid"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# =============================================================================
# AWS CONNECTION TEST
# =============================================================================

test_aws_connection() {
    echo "Testing AWS connection..."
    
    # Test basic AWS connectivity
    if ! aws sts get-caller-identity --region "$REGION" &> /dev/null; then
        echo "❌ ERROR: Failed to connect to AWS"
        echo "Please check your credentials and region settings"
        echo ""
        echo "Debug information:"
        echo "Region: $REGION"
        echo "AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:+***set***}"
        echo "AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:+***set***}"
        echo ""
        echo "Try running: aws sts get-caller-identity --region $REGION"
        exit 1
    fi
    
    # Get caller identity for confirmation
    local caller_info=$(aws sts get-caller-identity --region "$REGION" 2>/dev/null)
    local account_id=$(echo "$caller_info" | jq -r '.Account' 2>/dev/null || echo "unknown")
    local user_arn=$(echo "$caller_info" | jq -r '.Arn' 2>/dev/null || echo "unknown")
    
    echo "✓ AWS connection successful"
    echo "  Account ID: $account_id"
    echo "  User/Role: $user_arn"
    echo "  Region: $REGION"
}

# =============================================================================
# PARAMETER VALIDATION
# =============================================================================

validate_parameters() {
    # Check if DB identifier is provided
    if [ $# -lt 1 ]; then
        echo "❌ ERROR: DB identifier is required"
        echo ""
        echo "Usage: $0 <db-identifier> [region]"
        echo "Example: $0 my-postgres-db us-east-1"
        echo ""
        echo "Available options:"
        echo "  db-identifier  : RDS database instance identifier (required)"
        echo "  region        : AWS region (optional, will use default if not specified)"
        exit 1
    fi
    
    DB_IDENTIFIER="$1"
    
    # Validate DB identifier format (basic check)
    if [[ ! "$DB_IDENTIFIER" =~ ^[a-zA-Z][a-zA-Z0-9-]*$ ]]; then
        echo "⚠️  Warning: DB identifier '$DB_IDENTIFIER' may have invalid format"
        echo "Valid format: starts with letter, contains only letters, numbers, and hyphens"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# =============================================================================
# MAIN SCRIPT LOGIC
# =============================================================================

# Validate command line parameters
validate_parameters "$@"

# Setup AWS credentials
setup_aws_credentials

# Setup region
setup_region "$2"

# Test AWS connection
test_aws_connection

echo ""
echo "=========================================="
echo "RDS PostgreSQL Metadata Extraction"
echo "=========================================="
echo "Database Identifier: $DB_IDENTIFIER"
echo "Region: $REGION"
echo "Timestamp: $(date)"
echo "=========================================="

# Set region parameter for AWS CLI commands
REGION_PARAM="--region $REGION"

# Create output directory
OUTPUT_DIR="rds_metadata_${DB_IDENTIFIER}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

echo "Output directory: $OUTPUT_DIR"
echo ""

# Function to run AWS CLI command and save output
run_aws_command() {
    local command="$1"
    local output_file="$2"
    local description="$3"
    
    echo "Extracting: $description"
    if eval "$command" > "$OUTPUT_DIR/$output_file" 2>/dev/null; then
        echo "✓ Saved to: $output_file"
    else
        echo "✗ Failed to extract: $description"
        echo "Error details saved to: ${output_file}.error"
        eval "$command" > "$OUTPUT_DIR/${output_file}.error" 2>&1 || true
    fi
    echo ""
}

# Verify DB instance exists before proceeding
echo "Verifying DB instance exists..."
if ! aws rds describe-db-instances --db-instance-identifier "$DB_IDENTIFIER" $REGION_PARAM &> /dev/null; then
    echo "❌ ERROR: DB instance '$DB_IDENTIFIER' not found in region '$REGION'"
    echo ""
    echo "Available DB instances in this region:"
    aws rds describe-db-instances $REGION_PARAM --query 'DBInstances[].DBInstanceIdentifier' --output table 2>/dev/null || echo "Failed to list DB instances"
    exit 1
fi
echo "✓ DB instance found"
echo ""

# 1. Basic DB Instance Information
run_aws_command \
    "aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --output json" \
    "01_db_instance_details.json" \
    "DB Instance Details"

# # 2. DB Parameter Group Information
# run_aws_command \
#     "aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DBParameterGroups[0].DBParameterGroupName' --output text | xargs -I {} aws rds describe-db-parameter-groups --db-parameter-group-name {} $REGION_PARAM --output json" \
#     "02_db_parameter_group.json" \
#     "DB Parameter Group Details"

# # 3. All DB Parameters
# run_aws_command \
#     "aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DBParameterGroups[0].DBParameterGroupName' --output text | xargs -I {} aws rds describe-db-parameters --db-parameter-group-name {} $REGION_PARAM --output json" \
#     "03_db_parameters.json" \
#     "All Database Parameters"

# # 4. User Modified Parameters Only
# run_aws_command \
#     "aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DBParameterGroups[0].DBParameterGroupName' --output text | xargs -I {} aws rds describe-db-parameters --db-parameter-group-name {} $REGION_PARAM --source user --output json" \
#     "04_user_modified_parameters.json" \
#     "User Modified Parameters"

# # 5. DB Subnet Group Information
# run_aws_command \
#     "aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DBSubnetGroup.DBSubnetGroupName' --output text | xargs -I {} aws rds describe-db-subnet-groups --db-subnet-group-name {} $REGION_PARAM --output json" \
#     "05_db_subnet_group.json" \
#     "DB Subnet Group Details"

# # 6. VPC Security Groups
# run_aws_command \
#     "aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].VpcSecurityGroups[].VpcSecurityGroupId' --output text | tr '\t' '\n' | xargs -I {} aws ec2 describe-security-groups --group-ids {} $REGION_PARAM --output json" \
#     "06_vpc_security_groups.json" \
#     "VPC Security Groups"

# # 7. Option Group Information (if applicable)
# run_aws_command \
#     "aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].OptionGroupMemberships[0].OptionGroupName' --output text | xargs -I {} aws rds describe-option-groups --option-group-name {} $REGION_PARAM --output json" \
#     "07_option_group.json" \
#     "Option Group Details"

# # 8. DB Snapshots
# run_aws_command \
#     "aws rds describe-db-snapshots --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --output json" \
#     "08_db_snapshots.json" \
#     "Database Snapshots"

# # 9. Automated Backups
# run_aws_command \
#     "aws rds describe-db-instance-automated-backups --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --output json" \
#     "09_automated_backups.json" \
#     "Automated Backup Information"

# # 10. Log Files
# run_aws_command \
#     "aws rds describe-db-log-files --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --output json" \
#     "10_log_files.json" \
#     "Available Log Files"

# # 11. Recent Events (last 7 days)
# run_aws_command \
#     "aws rds describe-events --source-identifier '$DB_IDENTIFIER' --source-type db-instance --start-time $(date -d '7 days ago' -u +%Y-%m-%dT%H:%M:%S) $REGION_PARAM --output json" \
#     "11_recent_events.json" \
#     "Recent Events (Last 7 Days)"

# # 12. Performance Insights Metadata (if enabled)
# run_aws_command \
#     "aws pi describe-dimension-keys --service-type RDS --identifier \$(aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DbiResourceId' --output text) --metric-type 'db.SQL.Innodb.rows_read.avg' --start-time $(date -d '1 hour ago' -u +%Y-%m-%dT%H:%M:%S) --end-time $(date -u +%Y-%m-%dT%H:%M:%S) $REGION_PARAM --output json" \
#     "12_performance_insights_metadata.json" \
#     "Performance Insights Metadata"

# # 13. Performance Insights Available Metrics
# run_aws_command \
#     "aws pi list-available-resource-metrics --service-type RDS --identifier \$(aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DbiResourceId' --output text) $REGION_PARAM --output json" \
#     "13_performance_insights_metrics.json" \
#     "Performance Insights Available Metrics"

# # 14. Performance Insights Available Dimensions
# run_aws_command \
#     "aws pi list-available-resource-dimensions --service-type RDS --identifier \$(aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DbiResourceId' --output text) $REGION_PARAM --output json" \
#     "14_performance_insights_dimensions.json" \
#     "Performance Insights Available Dimensions"

# # 15. PostgreSQL Engine Versions
# run_aws_command \
#     "aws rds describe-db-engine-versions --engine postgres $REGION_PARAM --output json" \
#     "15_postgres_engine_versions.json" \
#     "PostgreSQL Engine Versions"

# # 16. Orderable DB Instance Options for PostgreSQL
# run_aws_command \
#     "aws rds describe-orderable-db-instance-options --engine postgres $REGION_PARAM --output json" \
#     "16_orderable_instance_options.json" \
#     "PostgreSQL Orderable Instance Options"

# # 17. Reserved Instances
# run_aws_command \
#     "aws rds describe-reserved-db-instances $REGION_PARAM --output json" \
#     "17_reserved_instances.json" \
#     "Reserved DB Instances"

# # 18. Pending Maintenance Actions
# run_aws_command \
#     "aws rds describe-pending-maintenance-actions --filters Name=db-instance-id,Values='$DB_IDENTIFIER' $REGION_PARAM --output json" \
#     "18_pending_maintenance.json" \
#     "Pending Maintenance Actions"

# # 19. DB Cluster Details (if Aurora)
# run_aws_command \
#     "aws rds describe-db-clusters --db-cluster-identifier \$(aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DBClusterIdentifier' --output text 2>/dev/null) $REGION_PARAM --output json" \
#     "19_db_cluster_details.json" \
#     "DB Cluster Details (Aurora)"

# # 20. Resource Tags
# run_aws_command \
#     "aws rds list-tags-for-resource --resource-name \$(aws rds describe-db-instances --db-instance-identifier '$DB_IDENTIFIER' $REGION_PARAM --query 'DBInstances[0].DBInstanceArn' --output text) $REGION_PARAM --output json" \
#     "20_tags.json" \
#     "Resource Tags"

# # 21. SSL/TLS Certificates
# run_aws_command \
#     "aws rds describe-certificates $REGION_PARAM --output json" \
#     "21_certificates.json" \
#     "SSL/TLS Certificates"

# # 22. Event Subscriptions
# run_aws_command \
#     "aws rds describe-event-subscriptions $REGION_PARAM --output json" \
#     "22_event_subscriptions.json" \
#     "Event Subscriptions"

# # 23. Export Tasks
# run_aws_command \
#     "aws rds describe-export-tasks $REGION_PARAM --output json" \
#     "23_export_tasks.json" \
#     "Export Tasks"

# # 24. PostgreSQL Default Parameters
# run_aws_command \
#     "aws rds describe-engine-default-parameters --db-parameter-group-family postgres14 $REGION_PARAM --output json" \
#     "24_postgres_default_parameters.json" \
#     "PostgreSQL Default Parameters"

# Create a comprehensive summary file
echo "Creating metadata summary..."
cat > "$OUTPUT_DIR/00_metadata_summary.txt" << EOF
RDS PostgreSQL Database Metadata Extraction Summary
==================================================

Database Identifier: $DB_IDENTIFIER
Region: $REGION
Extraction Date: $(date)
Output Directory: $OUTPUT_DIR
AWS Account: $(aws sts get-caller-identity --region "$REGION" --query 'Account' --output text 2>/dev/null || echo "unknown")
AWS User/Role: $(aws sts get-caller-identity --region "$REGION" --query 'Arn' --output text 2>/dev/null || echo "unknown")

Authentication Method: $(if [[ -n "$AWS_ACCESS_KEY_ID" ]]; then echo "Environment Variables"; else echo "AWS Configure"; fi)

Files Generated:
================
00_metadata_summary.txt               - This summary file
01_db_instance_details.json          - Complete DB instance configuration
02_db_parameter_group.json           - Parameter group details
03_db_parameters.json                - All database parameters
04_user_modified_parameters.json     - User-modified parameters only
05_db_subnet_group.json              - Subnet group configuration
06_vpc_security_groups.json          - VPC security groups
07_option_group.json                 - Option group details (if applicable)
08_db_snapshots.json                 - All snapshots for this DB
09_automated_backups.json            - Automated backup information
10_log_files.json                    - Available log files
11_recent_events.json                - Recent events (last 7 days)
12_performance_insights_metadata.json - Performance Insights metadata
13_performance_insights_metrics.json  - Available PI metrics
14_performance_insights_dimensions.json - Available PI dimensions
15_postgres_engine_versions.json     - PostgreSQL engine versions
16_orderable_instance_options.json   - Available instance options
17_reserved_instances.json           - Reserved instances information
18_pending_maintenance.json          - Pending maintenance actions
19_db_cluster_details.json           - Cluster details (if Aurora)
20_tags.json                         - Resource tags
21_certificates.json                 - SSL/TLS certificates
22_event_subscriptions.json          - Event subscriptions
23_export_tasks.json                 - Export tasks
24_postgres_default_parameters.json  - PostgreSQL default parameters

PostgreSQL-Specific Metadata Included:
=====================================
- All PostgreSQL parameters and their current values
- PostgreSQL engine versions and compatibility
- PostgreSQL-specific log files (postgresql.log, upgrade.log)
- PostgreSQL parameter group family defaults
- PostgreSQL orderable instance options
- Performance Insights metrics specific to PostgreSQL workloads

Notes:
======
- Files with .error extension indicate extraction failures
- Some metadata may not be available depending on DB configuration
- Performance Insights data requires PI to be enabled on the database
- Aurora-specific metadata only included if DB is part of Aurora cluster

Quick Commands:
==============
View main DB details:
  cat $OUTPUT_DIR/01_db_instance_details.json | jq .

View PostgreSQL parameters:
  cat $OUTPUT_DIR/03_db_parameters.json | jq '.Parameters[] | select(.ParameterName | contains("postgres"))'

View user-modified parameters:
  cat $OUTPUT_DIR/04_user_modified_parameters.json | jq .

View security groups:
  cat $OUTPUT_DIR/06_vpc_security_groups.json | jq .

View recent events:
  cat $OUTPUT_DIR/11_recent_events.json | jq .

EOF

# Save AWS configuration info for reference
cat > "$OUTPUT_DIR/aws_config_info.txt" << EOF
AWS Configuration Information
============================
Extraction Time: $(date)
Region Used: $REGION
Authentication Method: $(if [[ -n "$AWS_ACCESS_KEY_ID" ]]; then echo "Environment Variables (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)"; else echo "AWS Configure Profile"; fi)

Environment Variables Status:
AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:+***SET***}
AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:+***SET***}
AWS_SESSION_TOKEN: ${AWS_SESSION_TOKEN:+***SET***}
AWS_DEFAULT_REGION: ${AWS_DEFAULT_REGION:-not set}

AWS CLI Configuration:
$(aws configure list 2>/dev/null || echo "AWS configure not set up")

Caller Identity:
$(aws sts get-caller-identity --region "$REGION" 2>/dev/null || echo "Failed to get caller identity")
EOF

echo "=========================================="
echo "✅ Metadata extraction completed successfully!"
echo "=========================================="
echo "All files saved in directory: $OUTPUT_DIR"
echo ""
echo "📋 Summary file: $OUTPUT_DIR/00_metadata_summary.txt"
echo "⚙️  AWS config info: $OUTPUT_DIR/aws_config_info.txt"
echo ""
echo "🔍 Quick view commands:"
echo "  Main DB details: cat $OUTPUT_DIR/01_db_instance_details.json | jq ."
echo "  User parameters: cat $OUTPUT_DIR/04_user_modified_parameters.json | jq ."
echo "  Security groups: cat $OUTPUT_DIR/06_vpc_security_groups.json | jq ."
echo ""
echo "📁 Browse all files: ls -la $OUTPUT_DIR/"
