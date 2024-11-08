# filename: Dockerfile
# author: Christian Blank (https://github.com/Cyneric)
# created date: 2024-11-08
# description: Dockerfile for Addarr Refresh Telegram Bot.

FROM python:3.11.5-alpine3.18

WORKDIR /app

# Install requirements
RUN apk add --no-cache \
    transmission-cli

# Copy files to container
COPY . /app

# Install ans build Addarr Refresh requirements, make symlink to redirect logs to stdout
RUN	pip install --no-cache-dir -r requirements.txt --upgrade

ENTRYPOINT ["python", "/run.py"]
