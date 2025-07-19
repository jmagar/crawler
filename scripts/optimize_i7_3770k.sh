#!/bin/bash

# System optimization script for i7-3770K + 32GB RAM + RTX 4070
# This script optimizes the system for the crawler's Neo4j knowledge graph workload

set -e

echo "==================================================================="
echo "System Optimization for i7-3770K + 32GB RAM + RTX 4070"
echo "==================================================================="

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "This script should NOT be run as root for safety. Run with sudo privileges when needed."
   exit 1
fi

# Function to run with sudo and log
run_sudo() {
    echo "Running: $1"
    sudo bash -c "$1"
}

echo "1. CPU Performance Optimizations"
echo "---------------------------------"

# Set CPU governor to performance mode (important for older CPU)
if command -v cpupower >/dev/null 2>&1; then
    echo "Setting CPU governor to performance mode..."
    run_sudo "cpupower frequency-set -g performance"
    
    # Check current CPU frequency
    echo "Current CPU frequencies:"
    cpupower frequency-info
else
    echo "cpupower not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y linux-tools-common linux-tools-generic
    run_sudo "cpupower frequency-set -g performance"
fi

# Disable CPU power saving features for maximum performance
echo "Disabling CPU power saving features..."
run_sudo "echo 0 > /sys/devices/system/cpu/cpufreq/boost"
run_sudo "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"

echo ""
echo "2. Memory and Swap Optimizations"
echo "--------------------------------"

# Disable swap completely for database performance
echo "Disabling swap for optimal database performance..."
run_sudo "swapoff -a"

# Backup and modify swappiness
echo "Setting vm.swappiness to 1 (minimal swapping)..."
run_sudo "sysctl -w vm.swappiness=1"

# Optimize dirty page handling for 32GB RAM
echo "Optimizing memory management for 32GB RAM..."
run_sudo "sysctl -w vm.dirty_ratio=5"
run_sudo "sysctl -w vm.dirty_background_ratio=2"
run_sudo "sysctl -w vm.dirty_expire_centisecs=3000"
run_sudo "sysctl -w vm.dirty_writeback_centisecs=500"

# Optimize for database workloads
run_sudo "sysctl -w vm.overcommit_memory=2"
run_sudo "sysctl -w vm.overcommit_ratio=80"

echo ""
echo "3. File System Optimizations"
echo "----------------------------"

# Increase file limits for Neo4j
echo "Increasing file descriptor limits..."
run_sudo "sysctl -w fs.file-max=1000000"

# Add to limits.conf for permanent effect
if ! grep -q "neo4j.*nofile" /etc/security/limits.conf; then
    echo "Adding file descriptor limits to limits.conf..."
    run_sudo "echo 'neo4j soft nofile 65536' >> /etc/security/limits.conf"
    run_sudo "echo 'neo4j hard nofile 65536' >> /etc/security/limits.conf"
    run_sudo "echo '*     soft nofile 32768' >> /etc/security/limits.conf"
    run_sudo "echo '*     hard nofile 32768' >> /etc/security/limits.conf"
fi

echo ""
echo "4. Network Optimizations"
echo "------------------------"

# Optimize network buffers for Neo4j
echo "Optimizing network buffers..."
run_sudo "sysctl -w net.core.rmem_default=262144"
run_sudo "sysctl -w net.core.rmem_max=16777216"
run_sudo "sysctl -w net.core.wmem_default=262144"
run_sudo "sysctl -w net.core.wmem_max=16777216"
run_sudo "sysctl -w net.core.netdev_max_backlog=5000"

# TCP optimizations
run_sudo "sysctl -w net.ipv4.tcp_rmem='4096 87380 16777216'"
run_sudo "sysctl -w net.ipv4.tcp_wmem='4096 65536 16777216'"
run_sudo "sysctl -w net.ipv4.tcp_congestion_control=bbr"

echo ""
echo "5. Storage Optimizations"
echo "-----------------------"

# I/O scheduler optimization (if using SSD)
echo "Checking for SSD and optimizing I/O scheduler..."
for disk in /sys/block/sd*; do
    if [ -d "$disk" ]; then
        disk_name=$(basename "$disk")
        # Check if it's an SSD (simplified check)
        if [ -f "/sys/block/$disk_name/queue/rotational" ]; then
            rotational=$(cat "/sys/block/$disk_name/queue/rotational")
            if [ "$rotational" = "0" ]; then
                echo "SSD detected: $disk_name, setting noop/none scheduler"
                run_sudo "echo none > /sys/block/$disk_name/queue/scheduler" 2>/dev/null || \
                run_sudo "echo noop > /sys/block/$disk_name/queue/scheduler" 2>/dev/null || true
            else
                echo "HDD detected: $disk_name, setting deadline scheduler"
                run_sudo "echo deadline > /sys/block/$disk_name/queue/scheduler" 2>/dev/null || true
            fi
        fi
    fi
done

echo ""
echo "6. Docker Optimizations"
echo "----------------------"

# Create optimized Docker daemon configuration
DOCKER_DAEMON_CONFIG="/etc/docker/daemon.json"
if [ ! -f "$DOCKER_DAEMON_CONFIG" ]; then
    echo "Creating optimized Docker daemon configuration..."
    run_sudo "mkdir -p /etc/docker"
    
    cat << 'EOF' | sudo tee "$DOCKER_DAEMON_CONFIG"
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-ulimits": {
    "nofile": {
      "Hard": 65536,
      "Name": "nofile",
      "Soft": 32768
    }
  },
  "max-concurrent-downloads": 3,
  "max-concurrent-uploads": 3,
  "storage-opts": [
    "overlay2.override_kernel_check=true"
  ]
}
EOF
    
    echo "Restarting Docker with new configuration..."
    run_sudo "systemctl restart docker"
else
    echo "Docker daemon.json already exists, skipping..."
fi

echo ""
echo "7. GPU Optimizations (RTX 4070)"
echo "-------------------------------"

# Check if NVIDIA drivers are installed
if command -v nvidia-smi >/dev/null 2>&1; then
    echo "NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,memory.total,power.limit --format=csv,noheader,nounits
    
    # Set GPU to performance mode
    echo "Setting GPU to performance mode..."
    run_sudo "nvidia-smi -pm 1"
    
    # Optional: Set power limit to maximum (adjust as needed)
    echo "Setting GPU power limit to maximum..."
    run_sudo "nvidia-smi -pl 220" || echo "Could not set power limit (may not be supported)"
    
else
    echo "NVIDIA drivers not found. Install NVIDIA drivers for GPU acceleration."
    echo "Run: sudo apt-get install nvidia-driver-535 nvidia-cuda-toolkit"
fi

echo ""
echo "8. Create Persistent Configuration"
echo "---------------------------------"

# Create sysctl configuration file for persistent settings
SYSCTL_CONF="/etc/sysctl.d/99-crawler-optimization.conf"
if [ ! -f "$SYSCTL_CONF" ]; then
    echo "Creating persistent sysctl configuration..."
    cat << 'EOF' | sudo tee "$SYSCTL_CONF"
# Crawler optimization for i7-3770K + 32GB RAM
# Memory management
vm.swappiness=1
vm.dirty_ratio=5
vm.dirty_background_ratio=2
vm.dirty_expire_centisecs=3000
vm.dirty_writeback_centisecs=500
vm.overcommit_memory=2
vm.overcommit_ratio=80

# File system
fs.file-max=1000000

# Network optimization
net.core.rmem_default=262144
net.core.rmem_max=16777216
net.core.wmem_default=262144
net.core.wmem_max=16777216
net.core.netdev_max_backlog=5000
net.ipv4.tcp_rmem=4096 87380 16777216
net.ipv4.tcp_wmem=4096 65536 16777216
EOF
    
    echo "Loading new sysctl configuration..."
    run_sudo "sysctl -p $SYSCTL_CONF"
fi

echo ""
echo "9. Performance Monitoring Setup"
echo "------------------------------"

# Install performance monitoring tools
echo "Installing performance monitoring tools..."
sudo apt-get update
sudo apt-get install -y htop iotop nethogs sysstat

# Enable sysstat
run_sudo "systemctl enable sysstat"
run_sudo "systemctl start sysstat"

echo ""
echo "10. Hardware-Specific Recommendations"
echo "------------------------------------"

echo "Additional recommendations for your i7-3770K system:"
echo ""
echo "Temperature Monitoring:"
echo "- Install lm-sensors: sudo apt-get install lm-sensors"
echo "- Run sensors-detect and monitor CPU temperature under load"
echo "- Keep CPU temperature below 70°C for sustained performance"
echo ""
echo "Storage:"
echo "- Use SSD for Neo4j data directory for best performance"
echo "- Mount Neo4j data with noatime option: mount -o noatime"
echo ""
echo "Memory:"
echo "- Your 32GB RAM is excellent for this workload"
echo "- Consider upgrading to faster memory if using older DDR3"
echo ""
echo "CPU:"
echo "- The i7-3770K may become a bottleneck for very large repositories"
echo "- Monitor CPU usage and consider reducing concurrent operations if needed"
echo ""

echo ""
echo "11. Verification and Status"
echo "-------------------------"

echo "Current system status:"
echo "CPU Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'Not available')"
echo "Swappiness: $(cat /proc/sys/vm/swappiness)"
echo "Available Memory: $(free -h | grep 'Mem:' | awk '{print $7}')"
echo "File descriptor limit: $(ulimit -n)"

# Check if changes require reboot
echo ""
echo "IMPORTANT NOTES:"
echo "==============="
echo "1. Some optimizations require a reboot to take full effect"
echo "2. Monitor system temperature during heavy workloads"
echo "3. Adjust batch sizes in the crawler if you encounter memory pressure"
echo "4. The i7-3770K is from 2012 - consider CPU upgrade for maximum performance"
echo ""
echo "To apply the optimized configuration:"
echo "1. Reboot the system: sudo reboot"
echo "2. Use the optimized Docker Compose: docker-compose -f docker-compose.i7-3770k.yaml up -d"
echo "3. Monitor performance with: htop, iotop, and the crawler's built-in metrics"
echo ""
echo "Optimization complete!"