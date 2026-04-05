#!/bin/bash
# Install npudict on Linux
# Supports: Ubuntu, Pop!_OS, Debian, Fedora, Arch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.config/npudict"
SERVICE_DIR="$HOME/.config/systemd/user"

# Detect package manager
detect_package_manager() {
    if command -v apt &> /dev/null; then
        echo "apt"
    elif command -v dnf &> /dev/null; then
        echo "dnf"
    elif command -v pacman &> /dev/null; then
        echo "pacman"
    elif command -v zypper &> /dev/null; then
        echo "zypper"
    else
        echo "unknown"
    fi
}

# Install system dependencies
install_deps() {
    local pm=$(detect_package_manager)

    echo "Detected package manager: $pm"
    echo "Installing system dependencies..."

    case $pm in
        apt)
            sudo apt update
            sudo apt install -y alsa-utils xclip wl-clipboard xdotool libnotify-bin
            ;;
        dnf)
            sudo dnf install -y alsa-utils xclip wl-clipboard xdotool libnotify
            ;;
        pacman)
            sudo pacman -S --needed --noconfirm alsa-utils wl-clipboard xdotool libnotify
            ;;
        zypper)
            sudo zypper install -y alsa-utils xclip wl-clipboard xdotool libnotify-tools
            ;;
        *)
            echo "Unknown package manager. Please install manually:"
            echo "  alsa-utils xclip wl-clipboard xdotool libnotify"
            ;;
    esac
}

# Install Python dependencies
install_python() {
    echo ""
    echo "Installing Python dependencies..."

    if ! command -v uv &> /dev/null; then
        echo "uv not found. Please install uv first:"
        echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi

    uv sync
}

# Setup config file
setup_config() {
    echo ""
    echo "Setting up config..."
    mkdir -p "$CONFIG_DIR"

    if [ ! -f "$CONFIG_DIR/config.ini" ]; then
        cp "$SCRIPT_DIR/config.example.ini" "$CONFIG_DIR/config.ini"
        echo "Created config at $CONFIG_DIR/config.ini"
    else
        echo "Config already exists at $CONFIG_DIR/config.ini"
    fi
}

# Check whisper server availability
check_server() {
    echo ""
    echo "Checking server at http://localhost:8000..."

    if ! curl -sf http://localhost:8000 &> /dev/null; then
        echo "Warning: server at http://localhost:8000 is not reachable."
        echo "Make sure lemonade-server (or compatible) is running before using npudict."
    else
        echo "Server is reachable."
    fi
}

# Install systemd service
install_service() {
    echo ""
    echo "Installing systemd user service..."

    mkdir -p "$SERVICE_DIR"

    local display="${DISPLAY:-:0}"
    local xauthority="${XAUTHORITY:-$HOME/.Xauthority}"

    cat > "$SERVICE_DIR/npudict.service" << EOF
[Unit]
Description=npudict Voice Dictation
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/.venv/bin/python $SCRIPT_DIR/dictate.py
Restart=on-failure
RestartSec=5
Environment=DISPLAY=$display
Environment=XAUTHORITY=$xauthority

[Install]
WantedBy=default.target
EOF

    echo "Created service at $SERVICE_DIR/npudict.service"

    systemctl --user daemon-reload
    systemctl --user enable npudict

    echo ""
    echo "Service installed! Commands:"
    echo "  systemctl --user start npudict   # Start"
    echo "  systemctl --user stop npudict    # Stop"
    echo "  systemctl --user status npudict  # Status"
    echo "  journalctl --user -u npudict -f  # Logs"
}

# Main
main() {
    echo "==================================="
    echo "  npudict Installer"
    echo "==================================="
    echo ""

    install_deps
    install_python
    setup_config
    check_server

    echo ""
    read -p "Install as systemd service? [y/N] " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        install_service
    fi

    echo ""
    echo "==================================="
    echo "  Installation complete!"
    echo "==================================="
    echo ""
    echo "To run manually:"
    echo "  uv run npudict"
    echo "  uv run python dictate.py"
    echo ""
    echo "Config: $CONFIG_DIR/config.ini"
    echo "Hotkey: hold configured key to record"
    echo "Exit:   Ctrl+C"
}

main "$@"
