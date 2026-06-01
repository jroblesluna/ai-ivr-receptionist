#!/bin/bash
set -euo pipefail

# Update system packages
yum update -y

# Ensure SSM agent is running
systemctl enable amazon-ssm-agent
systemctl restart amazon-ssm-agent

# Install Docker
amazon-linux-extras install docker -y || yum install -y docker
systemctl enable docker
systemctl start docker

# Add ec2-user to docker group
usermod -aG docker ec2-user

# Install Docker Compose v2
DOCKER_COMPOSE_VERSION="v2.29.1"
mkdir -p /usr/local/lib/docker/cli-plugins
curl -SL "https://github.com/docker/compose/releases/download/$${DOCKER_COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Install AWS CLI v2 (for S3 access from deploy script)
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install --update
rm -rf /tmp/aws /tmp/awscliv2.zip

# Verify installations
docker --version
docker compose version
aws --version

# Create application directory
mkdir -p /opt/pickup
chown ec2-user:ec2-user /opt/pickup

# Restart SSM agent one more time after all installs
systemctl restart amazon-ssm-agent

echo "User data script completed successfully"
