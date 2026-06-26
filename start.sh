#!/bin/bash
set -e

# Create MongoDB data directory if it doesn't exist
mkdir -p /home/runner/mongodb_data

# Start MongoDB in the background if not already running
if ! pgrep -x mongod > /dev/null; then
    echo "Starting MongoDB..."
    mongod --dbpath /home/runner/mongodb_data --bind_ip 127.0.0.1 --port 27017 --fork --logpath /home/runner/mongodb_data/mongod.log
    sleep 2
    echo "MongoDB started."
fi

echo "Starting bot..."
exec python3 bot/bot.py
