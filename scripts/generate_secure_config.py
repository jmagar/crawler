#!/usr/bin/env python3
"""
Generate secure configuration files with random passwords and optimal settings.
"""
import secrets
import string
import argparse
import sys
from pathlib import Path
from typing import Dict, Any

# Import our validation functions
sys.path.append(str(Path(__file__).parent.parent))
from src.core.validation import get_system_memory_info, calculate_optimal_memory_allocation

def generate_secure_password(length: int = 32) -> str:
    """Generate a cryptographically secure password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_neo4j_password() -> str:
    """Generate a Neo4j-compatible secure password."""
    # Neo4j has some character restrictions, use a safer subset
    alphabet = string.ascii_letters + string.digits + "_-"
    return ''.join(secrets.choice(alphabet) for _ in range(24))

def detect_hardware_config() -> Dict[str, Any]:
    """Detect hardware configuration for optimal settings."""
    memory_info = get_system_memory_info()
    total_memory_gb = memory_info['total_gb']
    
    # Detect CPU cores (fallback to conservative estimate)
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=True)
        physical_cores = psutil.cpu_count(logical=False)
    except:
        cpu_count = 8
        physical_cores = 4
    
    neo4j_memory = calculate_optimal_memory_allocation(total_memory_gb)
    
    # Calculate optimal worker settings
    max_workers = min(max(physical_cores, 4), 16)  # Between 4 and 16
    max_concurrent = max(4, int(cpu_count * 0.5))  # 50% of logical cores
    
    # Calculate batch sizes based on memory
    if total_memory_gb >= 32:
        batch_size = 500
        file_batch_size = 300
        max_file_size = 2 * 1024 * 1024  # 2MB
    elif total_memory_gb >= 16:
        batch_size = 300
        file_batch_size = 200
        max_file_size = 1024 * 1024  # 1MB
    elif total_memory_gb >= 8:
        batch_size = 150
        file_batch_size = 100
        max_file_size = 512 * 1024  # 512KB
    else:
        batch_size = 100
        file_batch_size = 50
        max_file_size = 256 * 1024  # 256KB
    
    return {
        'total_memory_gb': total_memory_gb,
        'cpu_count': cpu_count,
        'physical_cores': physical_cores,
        'max_workers': max_workers,
        'max_concurrent': max_concurrent,
        'batch_size': batch_size,
        'file_batch_size': file_batch_size,
        'max_file_size': max_file_size,
        'neo4j_memory': neo4j_memory
    }

def generate_env_content(hardware_config: Dict[str, Any], profile: str = "auto") -> str:
    """Generate .env file content with secure defaults."""
    
    # Generate secure passwords
    neo4j_password = generate_neo4j_password()
    
    # Get hardware-optimized settings
    memory = hardware_config['neo4j_memory']
    
    content = f"""# Secure Environment Configuration
# Generated automatically with hardware-optimized settings
# DO NOT COMMIT THIS FILE TO VERSION CONTROL

# ==========================================
# SECURITY NOTICE
# ==========================================
# This file contains sensitive credentials.
# Ensure it's listed in .gitignore and has proper file permissions (600).

# ==========================================
# NEO4J CONFIGURATION
# ==========================================
NEO4J_USER=neo4j
NEO4J_PASSWORD={neo4j_password}
NEO4J_URI=bolt://localhost:7687

# Neo4j Memory Settings (Auto-optimized for {hardware_config['total_memory_gb']:.1f}GB system)
NEO4J_HEAP_INITIAL={memory['heap_initial_gb']}G
NEO4J_HEAP_MAX={memory['heap_max_gb']}G
NEO4J_PAGECACHE={memory['pagecache_gb']}G

# ==========================================
# PERFORMANCE TUNING (Auto-detected)
# ==========================================

# CPU Configuration ({hardware_config['physical_cores']} physical cores, {hardware_config['cpu_count']} logical)
CRAWLER_MAX_WORKERS={hardware_config['max_workers']}
CRAWLER_MAX_CONCURRENT={hardware_config['max_concurrent']}
CRAWLER_MAX_CONCURRENT_QUERIES=6

# Memory Configuration ({hardware_config['total_memory_gb']:.1f}GB total)
CRAWLER_BATCH_SIZE={hardware_config['batch_size']}
CRAWLER_FILE_BATCH_SIZE={hardware_config['file_batch_size']}
CRAWLER_MAX_FILE_SIZE={hardware_config['max_file_size']}
CRAWLER_PAGE_SIZE=100
CRAWLER_METRICS_RETENTION=5000

# Resource Management
CRAWLER_MAX_MEMORY_USAGE_PERCENT=80
CRAWLER_CPU_USAGE_THRESHOLD=85
CRAWLER_MONITORING_INTERVAL=2.0

# ==========================================
# DOCKER AND CONTAINER SETTINGS
# ==========================================

# Container Resource Allocation
DOCKER_NEO4J_MEMORY={memory['docker_memory_gb']}G
DOCKER_NEO4J_CPUS={hardware_config['physical_cores']}.0
DOCKER_QDRANT_MEMORY=4G
DOCKER_QDRANT_CPUS=4.0

# ==========================================
# SECURITY SETTINGS
# ==========================================

# Database Security
NEO4J_BOLT_THREAD_POOL_MIN=10
NEO4J_BOLT_THREAD_POOL_MAX=200

# Transaction Limits
NEO4J_TRANSACTION_TOTAL_MAX=1G
NEO4J_TRANSACTION_MAX=64M
NEO4J_QUERY_GLOBAL_MAX=512M
NEO4J_QUERY_MAX=128M

# ==========================================
# OPERATIONAL SETTINGS
# ==========================================

# Data Paths
DATA_PATH=./data
NEO4J_DATA_PATH=${{DATA_PATH}}/neo4j
QDRANT_DATA_PATH=${{DATA_PATH}}/qdrant

# Logging Configuration
LOG_LEVEL=INFO
LOG_MAX_SIZE=10MB
LOG_MAX_FILES=5

# Performance Monitoring
ENABLE_PERFORMANCE_MONITORING=true
ENABLE_QUERY_OPTIMIZATION=true
ENABLE_BATCH_PROCESSING=true
PERFORMANCE_MONITORING_INTERVAL=5.0

# Safety Limits
MAX_REPOSITORY_SIZE_GB=10
MAX_CONCURRENT_REPOSITORIES=2
MAX_ANALYSIS_TIME_MINUTES=60

# ==========================================
# DEVELOPMENT SETTINGS
# ==========================================

# Development Mode (set to true for development)
DEVELOPMENT_MODE=false
ENABLE_DETAILED_LOGGING=false
ENABLE_DEBUG_METRICS=false

# Hardware Validation (for startup checks)
EXPECTED_CPU_CORES={hardware_config['physical_cores']}
EXPECTED_CPU_THREADS={hardware_config['cpu_count']}
EXPECTED_MEMORY_GB={int(hardware_config['total_memory_gb'])}

# ==========================================
# BACKUP AND MAINTENANCE
# ==========================================

# Backup Settings
ENABLE_AUTO_BACKUP=true
BACKUP_RETENTION_DAYS=7
BACKUP_COMPRESSION=true

# Maintenance
ENABLE_AUTO_OPTIMIZATION=true
MAINTENANCE_WINDOW_HOUR=3
"""

    return content

def generate_env_template() -> str:
    """Generate an .env.template file with placeholder values."""
    return """# Environment Configuration Template
# Copy this to .env and fill in the actual values
# DO NOT put real credentials in this template file

# ==========================================
# NEO4J CONFIGURATION
# ==========================================
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_ME_TO_SECURE_PASSWORD
NEO4J_URI=bolt://localhost:7687

# Neo4j Memory Settings (adjust based on your system)
NEO4J_HEAP_INITIAL=4G
NEO4J_HEAP_MAX=4G
NEO4J_PAGECACHE=8G

# ==========================================
# PERFORMANCE TUNING
# ==========================================

# CPU Configuration (adjust based on your system)
CRAWLER_MAX_WORKERS=8
CRAWLER_MAX_CONCURRENT=6
CRAWLER_MAX_CONCURRENT_QUERIES=4

# Memory Configuration (adjust based on your system)
CRAWLER_BATCH_SIZE=200
CRAWLER_FILE_BATCH_SIZE=150
CRAWLER_MAX_FILE_SIZE=1048576
CRAWLER_PAGE_SIZE=100
CRAWLER_METRICS_RETENTION=5000

# Resource Management
CRAWLER_MAX_MEMORY_USAGE_PERCENT=80
CRAWLER_CPU_USAGE_THRESHOLD=85
CRAWLER_MONITORING_INTERVAL=2.0

# ==========================================
# DOCKER AND CONTAINER SETTINGS
# ==========================================

# Container Resource Allocation
DOCKER_NEO4J_MEMORY=12G
DOCKER_NEO4J_CPUS=8.0
DOCKER_QDRANT_MEMORY=4G
DOCKER_QDRANT_CPUS=4.0

# ==========================================
# OPERATIONAL SETTINGS
# ==========================================

# Data Paths
DATA_PATH=./data
NEO4J_DATA_PATH=${DATA_PATH}/neo4j
QDRANT_DATA_PATH=${DATA_PATH}/qdrant

# Logging
LOG_LEVEL=INFO
LOG_MAX_SIZE=10MB
LOG_MAX_FILES=5

# Performance Monitoring
ENABLE_PERFORMANCE_MONITORING=true
ENABLE_QUERY_OPTIMIZATION=true
ENABLE_BATCH_PROCESSING=true
PERFORMANCE_MONITORING_INTERVAL=5.0

# Safety Limits
MAX_REPOSITORY_SIZE_GB=10
MAX_CONCURRENT_REPOSITORIES=2
MAX_ANALYSIS_TIME_MINUTES=60

# Development
DEVELOPMENT_MODE=false
ENABLE_DETAILED_LOGGING=false
ENABLE_DEBUG_METRICS=false
"""

def main():
    parser = argparse.ArgumentParser(description="Generate secure configuration files")
    parser.add_argument("--output", "-o", default=".env", help="Output file path")
    parser.add_argument("--template", action="store_true", help="Generate template instead of actual config")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--profile", choices=["auto", "development", "production"], default="auto",
                       help="Configuration profile")
    
    args = parser.parse_args()
    
    output_path = Path(args.output)
    
    # Check if file exists and warn user
    if output_path.exists() and not args.force:
        print(f"Error: {output_path} already exists. Use --force to overwrite.")
        return 1
    
    try:
        if args.template:
            content = generate_env_template()
            print(f"Generating template configuration: {output_path}")
        else:
            print("Detecting hardware configuration...")
            hardware_config = detect_hardware_config()
            print(f"Detected: {hardware_config['total_memory_gb']:.1f}GB RAM, "
                  f"{hardware_config['physical_cores']} cores, "
                  f"{hardware_config['cpu_count']} threads")
            
            content = generate_env_content(hardware_config, args.profile)
            print(f"Generating secure configuration: {output_path}")
        
        # Write the file with secure permissions
        output_path.write_text(content)
        
        if not args.template:
            # Set secure file permissions (owner read/write only)
            output_path.chmod(0o600)
            print(f"✓ Generated {output_path} with secure permissions (600)")
            print("✓ Secure Neo4j password generated")
            print("✓ Hardware-optimized settings applied")
            print("\nIMPORTANT: Keep this file secure and never commit it to version control!")
        else:
            print(f"✓ Generated template {output_path}")
            print("Fill in the actual values and rename to .env")
        
        return 0
        
    except Exception as e:
        print(f"Error generating configuration: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())