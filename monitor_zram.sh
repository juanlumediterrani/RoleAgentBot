#!/bin/bash
# Monitor zram compression ratio during workload
# Usage: ./monitor_zram.sh [interval_seconds]

INTERVAL=${1:-5}  # Default 5 seconds
LOG_FILE="zram_monitor_$(date +%Y%m%d_%H%M%S).log"

echo "Starting zram compression monitoring (interval: ${INTERVAL}s)" | tee "$LOG_FILE"
echo "Log file: $LOG_FILE" | tee -a "$LOG_FILE"
echo "Press Ctrl+C to stop" | tee -a "$LOG_FILE"
echo "----------------------------------------" | tee -a "$LOG_FILE"

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Get zram stats
    ZRAM_STATS=$(zramctl)
    ZRAM_DISKSIZE=$(echo "$ZRAM_STATS" | awk 'NR==2 {print $3}')
    ZRAM_DATA=$(echo "$ZRAM_STATS" | awk 'NR==2 {print $4}')
    ZRAM_COMPR=$(echo "$ZRAM_STATS" | awk 'NR==2 {print $5}')
    ZRAM_TOTAL=$(echo "$ZRAM_STATS" | awk 'NR==2 {print $6}')
    
    # Calculate compression ratio
    if [ "$ZRAM_DATA" != "0B" ] && [ "$ZRAM_DATA" != "" ]; then
        # Convert to bytes for calculation
        DATA_BYTES=$(echo "$ZRAM_DATA" | sed 's/G/*1024^3/g; s/M/*1024^2/g; s/K/*1024/g; s/B//g' | bc)
        COMPR_BYTES=$(echo "$ZRAM_COMPR" | sed 's/G/*1024^3/g; s/M/*1024^2/g; s/K/*1024/g; s/B//g' | bc)
        
        if [ "$COMPR_BYTES" -gt 0 ]; then
            RATIO=$(echo "scale=2; $DATA_BYTES / $COMPR_BYTES" | bc)
        else
            RATIO="N/A"
        fi
    else
        RATIO="N/A"
    fi
    
    # Get memory stats
    MEM_STATS=$(free -h | grep Mem)
    MEM_TOTAL=$(echo "$MEM_STATS" | awk '{print $2}')
    MEM_USED=$(echo "$MEM_STATS" | awk '{print $3}')
    MEM_FREE=$(echo "$MEM_STATS" | awk '{print $4}')
    MEM_BUFF=$(echo "$MEM_STATS" | awk '{print $6}')
    
    # Get swap usage
    SWAP_STATS=$(free -h | grep Swap)
    SWAP_USED=$(echo "$SWAP_STATS" | awk '{print $3}')
    
    echo "[$TIMESTAMP]" | tee -a "$LOG_FILE"
    echo "  ZRAM: $ZRAM_DATA → $ZRAM_COMPR (ratio: ${RATIO}:1)" | tee -a "$LOG_FILE"
    echo "  ZRAM Total: $ZRAM_TOTAL / $ZRAM_DISKSIZE" | tee -a "$LOG_FILE"
    echo "  RAM: $MEM_USED / $MEM_TOTAL (free: $MEM_FREE, buffers: $MEM_BUFF)" | tee -a "$LOG_FILE"
    echo "  Swap used: $SWAP_USED" | tee -a "$LOG_FILE"
    echo "----------------------------------------" | tee -a "$LOG_FILE"
    
    sleep $INTERVAL
done
