#!/bin/bash
while true; do
    # Run the notifier script
    uv run notifier.py
    
    # Pause for 30 seconds before checking again
    sleep 30
done