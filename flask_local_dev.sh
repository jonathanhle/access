#!/usr/bin/env bash

start() {
    # Uninstall and reinstall Python packages
    pip uninstall "access-conditional-access @ file:///Users/jonathan.le/dev/jonathanhle/access/plugins/conditional_access" --yes
    pip install -r ./plugins/conditional_access/requirements.txt
    pip install ./plugins/conditional_access
    pip uninstall "access-notifications @ file:///Users/jonathan.le/dev/jonathanhle/access/plugins/notifications" --yes
    pip install -r ./plugins/notifications/requirements.txt
    pip install ./plugins/notifications

    # Check if Flask is already running
    if ! screen -list | grep -q "flask_session"; then
        # Start Flask application in a named screen session
        screen -dmS flask_session bash -c 'flask run'
        echo "Flask started in screen session 'flask_session'"
    else
        echo "Flask is already running in screen session 'flask_session'."
    fi

    # Check if npm is already running
    if ! screen -list | grep -q "npm_session"; then
        # Start npm in a named screen session
        screen -dmS npm_session bash -c 'npm start'
        echo "npm started in screen session 'npm_session'"
    else
        echo "npm is already running in screen session 'npm_session'."
    fi
}

stop() {
    # Gracefully stop Flask application screen session
    if screen -list | grep -q "flask_session"; then
        screen -S flask_session -p 0 -X stuff $'\003'
        sleep 3  # Wait for the process to handle the signal
        echo "Flask screen session 'flask_session' stopped."
    else
        echo "Flask screen session 'flask_session' is not running."
    fi

    # Gracefully stop npm screen session
    if screen -list | grep -q "npm_session"; then
        screen -S npm_session -p 0 -X stuff $'\003'
        sleep 3  # Wait for the process to handle the signal
        echo "npm screen session 'npm_session' stopped."
    else
        echo "npm screen session 'npm_session' is not running."
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    *)
        echo "Usage: $0 {start|stop}"
        exit 1
        ;;
esac
