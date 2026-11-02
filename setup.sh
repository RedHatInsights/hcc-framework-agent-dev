#!/bin/bash
set -e

echo "hcc-framework-agent-dev" > /home/botuser/app/.instance-id

# Install the UI-test login helper dependencies in the shared runner image.
LOGIN_HELPER=/home/botuser/app/instance/ui-test-agent/agent/login-helper
npm ci --prefix "$LOGIN_HELPER"

# Instance-specific packages and tools go here:
# dnf install -y --nodocs <package>
# pip3.12 install <package>
# npm install -g <package>

echo "Instance setup complete: hcc-framework-agent-dev"
