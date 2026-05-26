#!/bin/bash
set -e

echo "hcc-framework-agent-dev" > /home/botuser/app/.instance-id

# Instance-specific packages and tools go here:
# dnf install -y --nodocs <package>
# pip3.12 install <package>
# npm install -g <package>

echo "Instance setup complete: hcc-framework-agent-dev"
