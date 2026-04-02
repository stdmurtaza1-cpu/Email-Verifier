#!/bin/bash
# Ubuntu VPS Setup Script for Email Verifier (PostgreSQL + Native Node)
# Run this file using: sudo bash setup.sh

echo "====================================="
echo "Updating and Upgrading Packages"
echo "====================================="
sudo apt update && sudo apt upgrade -y

echo "====================================="
echo "Installing System Dependencies"
echo "====================================="
# Installing Python, Nginx, Redis, PostgreSQL, Git, Firewall
sudo apt install python3-pip python3-venv python3-dev libpq-dev postgresql postgresql-contrib redis-server nginx git ufw curl -y

echo "====================================="
echo "Configuring PostgreSQL Database"
echo "====================================="
# PostgreSQL Setup (Database 'email_verifier', User 'verifier_user')
sudo -u postgres psql -c "CREATE DATABASE email_verifier;"
sudo -u postgres psql -c "CREATE USER verifier_user WITH PASSWORD 'your_secure_password_123';"
sudo -u postgres psql -c "ALTER ROLE verifier_user SET client_encoding TO 'utf8';"
sudo -u postgres psql -c "ALTER ROLE verifier_user SET default_transaction_isolation TO 'read committed';"
sudo -u postgres psql -c "ALTER ROLE verifier_user SET timezone TO 'UTC';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE email_verifier TO verifier_user;"

echo "====================================="
echo "Setting up Firewall (UFW)"
echo "====================================="
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
# Enabling UFW non-interactively
sudo ufw --force enable 

echo "====================================="
echo "Setup Complete!"
echo "====================================="
echo "PostgreSQL is ready with database: email_verifier"
echo "Your Database URL for .env file will be:"
echo "DATABASE_URL=postgresql://verifier_user:your_secure_password_123@localhost/email_verifier"
echo "-------------------------------------"
echo "Next Steps:"
echo "1. Clone your GitHub repository to /var/www/"
echo "2. Create Python virtual environment and run 'pip install -r requirements.txt'"
