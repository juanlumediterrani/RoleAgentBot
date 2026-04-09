#!/bin/bash
# System Dependencies Installation Script for RoleAgentBot
# This script installs all required system dependencies for running the bot outside Docker

set -e

echo "🔧 Installing system dependencies for RoleAgentBot..."

# Update package list
sudo apt-get update

# Install base dependencies (always required)
echo "📦 Installing base dependencies..."
sudo apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    python3-dev \
    make \
    libssl-dev \
    libsqlite3-dev \
    curl \
    wget \
    ca-certificates

# Ask if user wants to install MC (music) dependencies
read -p "🎵 Do you want to install MC (music) dependencies? (ffmpeg, nodejs, audio libraries) [y/N]: " install_mc
if [[ $install_mc =~ ^[Yy]$ ]]; then
    echo "🎵 Installing MC (music) dependencies..."
    sudo apt-get install -y --no-install-recommends \
        ffmpeg \
        nodejs \
        libavformat-dev \
        libavcodec-dev \
        libavdevice-dev \
        libavfilter-dev \
        libswscale-dev \
        libswresample-dev \
        libopus-dev \
        libsodium-dev
fi

echo "✅ System dependencies installation complete!"
echo ""
echo "📋 Next steps:"
echo "1. Install Python dependencies: pip install -r requirements.txt"
echo "2. Set up your .env file with required environment variables"
echo ""
echo "🔐 For Vertex AI (optional):"
echo "   - Install Google Cloud SDK: curl https://sdk.cloud.google.com | bash"
echo "   - Authenticate: gcloud auth application-default login"
echo "   - Or set GOOGLE_APPLICATION_CREDENTIALS to your service account JSON"
echo ""
echo "🚀 Run the bot: python run.py"
