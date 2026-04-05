#!/bin/bash
# SIQE Watchdog Script
# Auto-restarts paper trading if process dies

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="logs/watchdog.log"
MAX_RESTARTS=10
RESTART_DELAY=30
CHECK_INTERVAL=30

restart_count=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

while true; do
    if pgrep -f "paper_trade_futures.py" > /dev/null; then
        restart_count=0
    else
        log "SIQE process not found, attempting restart..."
        restart_count=$((restart_count + 1))
        
        if [ $restart_count -gt $MAX_RESTARTS ]; then
            log "ERROR: Max restarts ($MAX_RESTARTS) reached, giving up"
            exit 1
        fi
        
        # Try to restart
        nohup python3 scripts/paper_trade_futures.py --name siqe_autonomous_$(date +%s) > /tmp/siqe_trading.log 2>&1 &
        
        log "Restart attempt $restart_count/$MAX_RESTARTS in $RESTART_DELAY seconds..."
        sleep $RESTART_DELAY
    fi
    
    sleep $CHECK_INTERVAL
done
