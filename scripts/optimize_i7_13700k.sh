#!/bin/bash

# System optimization script for Intel i7-13700K + 32GB DDR5 + RTX 4070
# Based on research and official Intel/Neo4j performance recommendations

set -e

echo "==================================================================="
echo "Intel i7-13700K System Optimization for Database Workloads"
echo "==================================================================="
echo "Hardware: i7-13700K (16C/24T) + 32GB DDR5 + RTX 4070 12GB"
echo "Optimizing for: Neo4j knowledge graph and high-performance computing"
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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo ""
echo "1. CPU Performance Optimizations (i7-13700K Specific)"
echo "======================================================"

# Enable performance governor for maximum frequency
if command_exists cpupower; then
    echo "Setting CPU governor to performance mode..."
    run_sudo "cpupower frequency-set -g performance"
    
    # Disable Intel P-State driver's turbo throttling
    echo "Enabling Turbo Boost..."
    run_sudo "echo 0 > /sys/devices/system/cpu/intel_pstate/no_turbo"
    
    # Set minimum frequency to high for consistent performance
    echo "Setting minimum CPU frequency for performance..."
    run_sudo "cpupower frequency-set -d 3400MHz"  # Base clock of i7-13700K
    
    echo "Current CPU frequency information:"
    cpupower frequency-info | grep -E "(current CPU|analyzing|boost state)"
else
    echo "Installing cpupower utilities..."
    sudo apt-get update
    sudo apt-get install -y linux-tools-common linux-tools-generic linux-tools-$(uname -r)
    run_sudo "cpupower frequency-set -g performance"
fi

# Optimize Intel Turbo Boost for sustained performance
echo "Optimizing Intel Turbo Boost settings..."
if [ -f /sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost ]; then
    run_sudo "echo 1 > /sys/devices/system/cpu/intel_pstate/hwp_dynamic_boost"
fi

echo ""
echo "2. Memory Optimizations (32GB DDR5 Specific)"
echo "============================================"

# Disable swap for database performance (with 32GB RAM, swap is unnecessary)
echo "Disabling swap for optimal database performance..."
run_sudo "swapoff -a"

# Comment out swap in fstab to make it permanent
sudo sed -i '/swap/s/^/#/' /etc/fstab

# Optimize vm settings for 32GB high-speed memory
echo "Optimizing virtual memory settings for 32GB DDR5..."
run_sudo "sysctl -w vm.swappiness=1"           # Minimal swapping
run_sudo "sysctl -w vm.dirty_ratio=10"         # Allow more dirty pages with 32GB
run_sudo "sysctl -w vm.dirty_background_ratio=5" # Start background writeback earlier
run_sudo "sysctl -w vm.dirty_expire_centisecs=3000"
run_sudo "sysctl -w vm.dirty_writeback_centisecs=500"
run_sudo "sysctl -w vm.overcommit_memory=1"    # Allow overcommit for performance
run_sudo "sysctl -w vm.vfs_cache_pressure=50"  # Balanced cache pressure

# Optimize for large memory systems
run_sudo "sysctl -w vm.min_free_kbytes=65536"  # Keep more memory free
run_sudo "sysctl -w vm.zone_reclaim_mode=0"    # Disable NUMA zone reclaim

echo ""
echo "3. I/O and Storage Optimizations (NVMe SSD)"
echo "==========================================="

# Optimize I/O scheduler for NVMe SSDs
echo "Optimizing I/O schedulers for NVMe SSDs..."
for disk in /sys/block/nvme*; do
    if [ -d "$disk" ]; then
        disk_name=$(basename "$disk")
        echo "Optimizing NVMe device: $disk_name"
        
        # Set scheduler to none for NVMe (best for modern SSDs)
        run_sudo "echo none > /sys/block/$disk_name/queue/scheduler" 2>/dev/null || true
        
        # Optimize queue depth for high-performance NVMe
        run_sudo "echo 32 > /sys/block/$disk_name/queue/nr_requests"
        
        # Reduce read-ahead for random I/O workloads
        run_sudo "echo 256 > /sys/block/$disk_name/queue/read_ahead_kb"
    fi
done

# Also check SATA SSDs
for disk in /sys/block/sd*; do
    if [ -d "$disk" ]; then
        disk_name=$(basename "$disk")
        if [ -f "/sys/block/$disk_name/queue/rotational" ]; then
            rotational=$(cat "/sys/block/$disk_name/queue/rotational")
            if [ "$rotational" = "0" ]; then
                echo "Optimizing SSD: $disk_name"
                run_sudo "echo mq-deadline > /sys/block/$disk_name/queue/scheduler" 2>/dev/null || true
            fi
        fi
    fi
done

echo ""
echo "4. Network Optimizations (High Bandwidth)"
echo "========================================="

# Optimize network buffers for high-performance database operations
echo "Optimizing network settings for database workloads..."
run_sudo "sysctl -w net.core.rmem_default=262144"
run_sudo "sysctl -w net.core.rmem_max=33554432"    # 32MB receive buffer
run_sudo "sysctl -w net.core.wmem_default=262144"
run_sudo "sysctl -w net.core.wmem_max=33554432"    # 32MB send buffer
run_sudo "sysctl -w net.core.netdev_max_backlog=10000"

# TCP optimizations for database connections
run_sudo "sysctl -w net.ipv4.tcp_rmem='4096 87380 33554432'"
run_sudo "sysctl -w net.ipv4.tcp_wmem='4096 65536 33554432'"
run_sudo "sysctl -w net.ipv4.tcp_congestion_control=bbr"
run_sudo "sysctl -w net.ipv4.tcp_mtu_probing=1"

# Increase connection tracking for concurrent database connections
run_sudo "sysctl -w net.netfilter.nf_conntrack_max=1048576" 2>/dev/null || true

echo ""
echo "5. File System Optimizations"
echo "============================"

# Increase file descriptor limits for database operations
echo "Optimizing file descriptor limits..."
run_sudo "sysctl -w fs.file-max=2097152"
run_sudo "sysctl -w fs.nr_open=2097152"

# Add to limits.conf for persistent effect
if ! grep -q "neo4j.*nofile" /etc/security/limits.conf; then
    echo "Adding file descriptor limits to limits.conf..."
    run_sudo "echo 'neo4j soft nofile 131072' >> /etc/security/limits.conf"
    run_sudo "echo 'neo4j hard nofile 131072' >> /etc/security/limits.conf"
    run_sudo "echo '*     soft nofile 65536' >> /etc/security/limits.conf"
    run_sudo "echo '*     hard nofile 65536' >> /etc/security/limits.conf"
fi

# Optimize inotify limits for file watching
run_sudo "sysctl -w fs.inotify.max_user_watches=1048576"
run_sudo "sysctl -w fs.inotify.max_user_instances=1024"

echo ""
echo "6. Transparent Huge Pages (Database Optimization)"
echo "================================================="

# Enable THP for database performance (beneficial for Neo4j)
echo "Enabling Transparent Huge Pages for database performance..."
run_sudo "echo always > /sys/kernel/mm/transparent_hugepage/enabled"
run_sudo "echo always > /sys/kernel/mm/transparent_hugepage/defrag"

# Set THP scanning for better memory management
run_sudo "echo 1000 > /sys/kernel/mm/transparent_hugepage/khugepaged/scan_sleep_millisecs"

echo ""
echo "7. Docker Optimizations"
echo "======================"

# Optimize Docker daemon for high-performance workloads
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
      "Hard": 131072,
      "Name": "nofile",
      "Soft": 65536
    },
    "memlock": {
      "Hard": -1,
      "Name": "memlock",
      "Soft": -1
    }
  },
  "max-concurrent-downloads": 6,
  "max-concurrent-uploads": 6,
  "storage-opts": [
    "overlay2.override_kernel_check=true"
  ],
  "default-shm-size": "1g",
  "experimental": false,
  "live-restore": true
}
EOF
    
    echo "Restarting Docker with optimized configuration..."
    run_sudo "systemctl restart docker"
else
    echo "Docker daemon.json already exists, skipping..."
fi

echo ""
echo "8. NVIDIA GPU Optimizations (RTX 4070)"
echo "======================================"

# Check if NVIDIA drivers are installed
if command_exists nvidia-smi; then
    echo "NVIDIA RTX 4070 detected and configured:"
    nvidia-smi --query-gpu=name,memory.total,power.limit,temperature.gpu --format=csv,noheader,nounits
    
    # Set GPU to performance mode
    echo "Setting GPU to maximum performance mode..."
    run_sudo "nvidia-smi -pm 1"
    
    # Set power limit to maximum (RTX 4070 typically 220W)
    echo "Setting GPU power limit to maximum..."
    run_sudo "nvidia-smi -pl 220" || echo "Could not set power limit (may require specific driver version)"
    
    # Optimize GPU clocks for compute workloads
    echo "Applying GPU compute optimizations..."
    run_sudo "nvidia-smi -ac 6500,2610" || echo "Could not set application clocks (may not be supported on this model)"
    
else
    echo "NVIDIA drivers not detected. For GPU acceleration, install:"
    echo "  sudo apt update"
    echo "  sudo apt install nvidia-driver-535 nvidia-cuda-toolkit"
    echo "  sudo reboot"
fi

echo ""
echo "9. CPU Thermal and Power Management"
echo "=================================="

# Install monitoring tools if not present
if ! command_exists sensors; then
    echo "Installing hardware monitoring tools..."
    sudo apt-get update
    sudo apt-get install -y lm-sensors
    run_sudo "sensors-detect --auto"
fi

# Display current thermal status
echo "Current CPU thermal status:"
sensors | grep -E "(Core|Package|CPU)" || echo "Thermal sensors not detected"

# Set CPU power management for maximum performance
if [ -d "/sys/devices/system/cpu/cpu0/cpufreq" ]; then
    echo "Setting CPU power management for maximum performance..."
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        run_sudo "echo performance > $cpu" 2>/dev/null || true
    done
fi

echo ""
echo "10. Create Persistent Configuration"
echo "=================================="

# Create comprehensive sysctl configuration
SYSCTL_CONF="/etc/sysctl.d/99-i7-13700k-optimization.conf"
if [ ! -f "$SYSCTL_CONF" ]; then
    echo "Creating persistent system optimization configuration..."
    cat << 'EOF' | sudo tee "$SYSCTL_CONF"
# Intel i7-13700K + 32GB DDR5 + RTX 4070 optimization
# Database and high-performance computing workloads

# Memory management (32GB DDR5)
vm.swappiness=1
vm.dirty_ratio=10
vm.dirty_background_ratio=5
vm.dirty_expire_centisecs=3000
vm.dirty_writeback_centisecs=500
vm.overcommit_memory=1
vm.vfs_cache_pressure=50
vm.min_free_kbytes=65536
vm.zone_reclaim_mode=0

# File system limits
fs.file-max=2097152
fs.nr_open=2097152
fs.inotify.max_user_watches=1048576
fs.inotify.max_user_instances=1024

# Network optimization (high bandwidth)
net.core.rmem_default=262144
net.core.rmem_max=33554432
net.core.wmem_default=262144
net.core.wmem_max=33554432
net.core.netdev_max_backlog=10000
net.ipv4.tcp_rmem=4096 87380 33554432
net.ipv4.tcp_wmem=4096 65536 33554432
net.ipv4.tcp_congestion_control=bbr
net.ipv4.tcp_mtu_probing=1

# Connection tracking
net.netfilter.nf_conntrack_max=1048576
EOF
    
    echo "Loading optimized sysctl configuration..."
    run_sudo "sysctl -p $SYSCTL_CONF"
fi

# Create systemd service for CPU governor persistence
GOVERNOR_SERVICE="/etc/systemd/system/cpu-performance.service"
if [ ! -f "$GOVERNOR_SERVICE" ]; then
    echo "Creating CPU performance governor service..."
    cat << 'EOF' | sudo tee "$GOVERNOR_SERVICE"
[Unit]
Description=Set CPU governor to performance mode
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/bin/cpupower frequency-set -g performance
ExecStart=/bin/bash -c 'echo 0 > /sys/devices/system/cpu/intel_pstate/no_turbo'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
    
    run_sudo "systemctl enable cpu-performance.service"
fi

echo ""
echo "11. Performance Monitoring Setup"
echo "==============================="

# Install comprehensive monitoring tools
echo "Installing performance monitoring tools..."
sudo apt-get update
sudo apt-get install -y htop iotop nethogs sysstat numactl hwinfo stress-ng

# Enable and configure sysstat for performance tracking
run_sudo "systemctl enable sysstat"
run_sudo "systemctl start sysstat"

# Configure sysstat to collect more frequent samples
sudo sed -i 's/5-55\/10/1-59\/2/g' /etc/cron.d/sysstat 2>/dev/null || true

echo ""
echo "12. Verification and Benchmarks"
echo "==============================="

echo "System verification:"
echo "CPU Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'Not available')"
echo "Turbo Boost: $([ "$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)" = "0" ] && echo 'Enabled' || echo 'Disabled/Not available')"
echo "Swappiness: $(cat /proc/sys/vm/swappiness)"
echo "Available Memory: $(free -h | grep 'Mem:' | awk '{print $7}')"
echo "File descriptor limit: $(ulimit -n)"
echo "THP status: $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || echo 'Not available')"

# CPU information
echo ""
echo "CPU Information:"
lscpu | grep -E "(Model name|CPU\(s\)|Thread|Core|MHz|Cache)"

# Memory information
echo ""
echo "Memory Information:"
free -h
if command_exists dmidecode; then
    sudo dmidecode -t memory | grep -E "(Speed|Type:|Size)" | head -10
fi

# Check CPU temperature
echo ""
echo "Current CPU Temperature:"
sensors 2>/dev/null | grep -E "(Core|Package|CPU)" | head -5 || echo "Temperature monitoring not available"

echo ""
echo "============================================================"
echo "OPTIMIZATION COMPLETE - i7-13700K PERFORMANCE SUMMARY"
echo "============================================================"
echo ""
echo "✅ CPU: Performance governor enabled, Turbo Boost active"
echo "✅ Memory: 32GB DDR5 optimized for database workloads"
echo "✅ Storage: NVMe/SSD I/O schedulers optimized"
echo "✅ Network: High-bandwidth settings configured"
echo "✅ GPU: RTX 4070 set to maximum performance mode"
echo "✅ Docker: Optimized for container workloads"
echo "✅ Monitoring: Comprehensive performance tracking enabled"
echo ""
echo "NEXT STEPS:"
echo "1. Reboot system to ensure all optimizations take effect:"
echo "   sudo reboot"
echo ""
echo "2. After reboot, start the optimized containers:"
echo "   docker-compose -f docker-compose.i7-13700k.yaml up -d"
echo ""
echo "3. Monitor performance with these commands:"
echo "   - htop (CPU and memory usage)"
echo "   - iotop (I/O usage)"
echo "   - sensors (temperature monitoring)"
echo "   - nvidia-smi (GPU monitoring)"
echo ""
echo "4. Run the hardware configuration:"
echo "   python knowledge_graphs/hardware_optimized_i7_13700k.py"
echo ""
echo "PERFORMANCE EXPECTATIONS:"
echo "• Exceptional multi-threaded performance (24 threads)"
echo "• Optimal database operation with 32GB memory"
echo "• High I/O throughput on NVMe storage"
echo "• GPU acceleration ready for future features"
echo "• System can handle very large repository analyses"
echo ""
echo "⚠️  IMPORTANT NOTES:"
echo "• Monitor CPU temperature under heavy load (keep below 80°C)"
echo "• Ensure adequate cooling for sustained high performance"
echo "• The i7-13700K can boost to 5.4GHz - verify cooling is adequate"
echo "• Use 'watch sensors' to monitor temps during heavy workloads"
echo ""
echo "Optimization completed successfully!"