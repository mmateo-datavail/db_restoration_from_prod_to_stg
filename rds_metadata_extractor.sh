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
OUTPUT_DIR=$PWD
# OUTPUT_DIR="rds_metadata_${DB_IDENTIFIER}_$(date +%Y%m%d_%H%M%S)"
# mkdir -p "$OUTPUT_DIR"

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


echo "=========================================="
echo "✅ Metadata extraction completed successfully!"
echo "=========================================="
echo "File saved in actual directory: $OUTPUT_DIR with name: 01_db_instance_details.json"
echo ""
echo "🔍 Quick view commands:"
echo ""
echo " - DB details/metadata full path:"
echo "$OUTPUT_DIR/01_db_instance_details.json"
