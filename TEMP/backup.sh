#!/bin/bash

# Backup script for RoleAgentBot databases and logs
# Creates a timestamped zip file with all databases and logs
# Run this script from the RoleAgentBot directory

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="roleagentbot_backup_${TIMESTAMP}.zip"

echo "Creating backup: ${BACKUP_FILE}"

# Create zip with databases and logs (relative paths)
zip -r "${BACKUP_FILE}" \
    databases/ \
    logs/ \
    -x "*.pyc" \
    -x "__pycache__/*" \
    -x ".git/*"

echo "Backup created: ${BACKUP_FILE}"
echo "Size: $(du -h "${BACKUP_FILE}" | cut -f1)"
