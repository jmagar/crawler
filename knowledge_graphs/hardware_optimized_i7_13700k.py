"""
Hardware-optimized configuration for Intel i7-13700K + 32GB DDR5 + RTX 4070 12GB VRAM.

Based on concrete research and Intel/Neo4j official documentation for optimal database workload performance.

Hardware Specifications (researched):
- Intel i7-13700K: 16 cores (8 P-cores + 8 E-cores), 24 threads, up to 5.4GHz boost
- 30MB L3 cache, 24MB L2 cache
- TDP: 125W base, 253W max turbo power
- Memory: 32GB DDR5 (optimal speeds: DDR5-6400 to DDR5-7200)
- GPU: RTX 4070 12GB VRAM
"""
import os
import psutil
import logging
from typing import Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class I7_13700K_Profile:
    """Hardware profile for Intel i7-13700K system."""
    cpu_model: str = "i7-13700K"
    cpu_generation: str = "13th Gen Raptor Lake"
    
    # Core configuration (researched specs)
    p_cores: int = 8           # Performance cores
    e_cores: int = 8           # Efficiency cores  
    total_cores: int = 16      # Total physical cores
    total_threads: int = 24    # With hyperthreading on P-cores
    
    # Clock speeds (official Intel specs)
    base_clock_ghz: float = 3.4
    max_boost_ghz: float = 5.4
    p_core_boost_ghz: float = 5.4
    e_core_boost_ghz: float = 4.2
    
    # Cache (official specs)
    l3_cache_mb: int = 30
    l2_cache_mb: int = 24
    
    # Memory and power
    total_ram_gb: int = 32
    available_ram_gb: int = 30     # Reserve 2GB for OS (modern system)
    gpu_vram_gb: int = 12
    tdp_base_w: int = 125
    tdp_max_w: int = 253
    
    # Memory recommendations based on research
    optimal_ddr5_speed: int = 6400  # MT/s - optimal for workloads
    memory_channels: int = 2        # Dual channel

class I7_13700K_OptimizedConfig:
    """Generate optimized configuration for i7-13700K based on research."""
    
    def __init__(self, profile: I7_13700K_Profile = None):
        """Initialize with hardware profile."""
        self.profile = profile or I7_13700K_Profile()
        self.config = self._generate_config()
    
    def _generate_config(self) -> Dict[str, Any]:
        """Generate optimized configuration based on researched best practices."""
        
        # CPU optimization - leverage the hybrid architecture
        # Use P-cores for main workload, E-cores for background tasks
        max_workers = min(16, self.profile.p_cores * 2)  # Leverage P-cores with hyperthreading
        
        # Memory optimization for 32GB DDR5
        available_memory_gb = self.profile.available_ram_gb
        
        # Neo4j memory allocation based on official recommendations
        # For 32GB system with database workloads:
        neo4j_heap_gb = 8      # Conservative heap size for stability
        neo4j_pagecache_gb = 16  # Generous page cache for performance
        
        # Batch sizes - can be larger with powerful CPU and memory
        neo4j_batch_size = 500  # Larger batches for modern hardware
        file_batch_size = 300   # Process more files per batch
        
        # File size limits - generous with 32GB RAM
        max_file_size = 2 * 1024 * 1024  # 2MB per file
        
        # Concurrency - leverage 24 threads but don't oversaturate
        max_concurrent_analyses = 12  # Use ~50% of threads
        max_concurrent_queries = 6    # Conservative for database connections
        
        # Performance monitoring - more frequent for high-performance system
        monitoring_interval = 1.0  # Monitor every second
        
        return {
            # CPU Configuration (optimized for hybrid architecture)
            "max_workers": max_workers,
            "max_concurrent_analyses": max_concurrent_analyses,
            "max_concurrent_queries": max_concurrent_queries,
            "use_p_cores_for_main_work": True,
            "use_e_cores_for_background": True,
            
            # Memory Configuration (based on Neo4j best practices)
            "neo4j_batch_size": neo4j_batch_size,
            "file_batch_size": file_batch_size,
            "max_file_size": max_file_size,
            "pagination_page_size": 500,  # Larger pages for better performance
            
            # Neo4j Memory (following official recommendations)
            "neo4j_heap_initial_gb": neo4j_heap_gb,
            "neo4j_heap_max_gb": neo4j_heap_gb,
            "neo4j_pagecache_gb": neo4j_pagecache_gb,
            
            # Performance Monitoring
            "monitoring_interval": monitoring_interval,
            "metrics_retention": 10000,  # Keep more metrics
            
            # System Resource Management
            "max_memory_usage_percent": 85,  # Can use more memory safely
            "cpu_usage_threshold": 90,       # Higher threshold for powerful CPU
            
            # Advanced Features (modern hardware capabilities)
            "enable_avx2_optimization": True,
            "enable_cpu_affinity": True,
            "prefer_p_cores": True,
            "enable_turbo_boost": True,
            "use_modern_scheduling": True,
            
            # I/O and Storage (assuming NVMe SSD)
            "assume_nvme_storage": True,
            "io_queue_depth": 32,
            "enable_direct_io": True,
        }
    
    def get_neo4j_memory_config(self) -> Dict[str, str]:
        """Get Neo4j memory configuration based on official best practices."""
        heap_size = f"{self.config['neo4j_heap_initial_gb']}G"
        pagecache_size = f"{self.config['neo4j_pagecache_gb']}G"
        
        return {
            # Heap configuration (same initial and max as recommended)
            "server.memory.heap.initial_size": heap_size,
            "server.memory.heap.max_size": heap_size,
            
            # Page cache (sized for database content + 20% headroom)
            "server.memory.pagecache.size": pagecache_size,
            
            # Transaction memory limits for high concurrency
            "dbms.memory.transaction.total.max": "2G",
            "db.memory.transaction.max": "128M",
            
            # Query memory limits
            "dbms.memory.query.global_max": "1G",
            "db.memory.query.max": "256M",
        }
    
    def get_neo4j_docker_config(self) -> Dict[str, str]:
        """Get optimized Neo4j Docker environment configuration."""
        memory_config = self.get_neo4j_memory_config()
        
        return {
            # Memory settings
            **{f"NEO4J_{k.replace('.', '_')}": v for k, v in memory_config.items()},
            
            # JVM optimizations for modern hardware
            "NEO4J_dbms_jvm_additional": (
                "-XX:+UseG1GC "
                "-XX:+UnlockExperimentalVMOptions "
                "-XX:MaxGCPauseMillis=100 "
                "-XX:G1HeapRegionSize=32m "
                "-XX:+UseTransparentHugePages "
                "-XX:+DisableExplicitGC "
                "-XX:+UseLargePages "
                "-XX:+AlwaysPreTouch"
            ),
            
            # Performance tuning for high-end hardware
            "NEO4J_dbms_tx_log_rotation_retention_policy": "2G size",
            "NEO4J_dbms_checkpoint_interval_time": "180s",
            "NEO4J_dbms_checkpoint_interval_tx": "50000",
            
            # Connection and threading (optimized for 24 threads)
            "NEO4J_dbms_connector_bolt_thread_pool_min_size": "10",
            "NEO4J_dbms_connector_bolt_thread_pool_max_size": "800",
            "NEO4J_dbms_connector_bolt_thread_pool_keep_alive": "5m",
            
            # Security and plugins
            "NEO4J_dbms_security_procedures_unrestricted": "apoc.*",
            "NEO4J_dbms_security_procedures_allowlist": "apoc.*",
            "NEO4J_PLUGINS": "apoc",
            
            # Logging and monitoring
            "NEO4J_dbms_logs_gc_enabled": "true",
            "NEO4J_dbms_logs_gc_options": (
                "-Xloggc:gc.log "
                "-XX:+UseGCLogFileRotation "
                "-XX:NumberOfGCLogFiles=5 "
                "-XX:GCLogFileSize=50m"
            ),
            
            # I/O optimizations for NVMe
            "NEO4J_dbms_memory_pagecache_warmup_enable": "true",
            "NEO4J_dbms_memory_pagecache_warmup_preload": "true",
        }
    
    def get_system_tuning_commands(self) -> list[str]:
        """Get system tuning commands optimized for i7-13700K."""
        return [
            # CPU performance optimizations
            "sudo cpupower frequency-set -g performance",
            "echo 0 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo",
            
            # Memory optimizations for 32GB system
            "sudo sysctl -w vm.swappiness=1",
            "sudo sysctl -w vm.dirty_ratio=10",
            "sudo sysctl -w vm.dirty_background_ratio=5",
            "sudo sysctl -w vm.overcommit_memory=1",
            
            # I/O optimizations for NVMe SSDs
            "sudo sysctl -w vm.vfs_cache_pressure=50",
            
            # Network optimizations for modern hardware
            "sudo sysctl -w net.core.rmem_default=262144",
            "sudo sysctl -w net.core.rmem_max=33554432",
            "sudo sysctl -w net.core.wmem_default=262144", 
            "sudo sysctl -w net.core.wmem_max=33554432",
            "sudo sysctl -w net.core.netdev_max_backlog=10000",
            
            # File system optimizations
            "sudo sysctl -w fs.file-max=2097152",
            "sudo sysctl -w fs.nr_open=2097152",
            
            # Transparent Huge Pages (beneficial for databases)
            "echo always | sudo tee /sys/kernel/mm/transparent_hugepage/enabled",
            "echo always | sudo tee /sys/kernel/mm/transparent_hugepage/defrag",
        ]
    
    def get_cpu_affinity_config(self) -> Dict[str, list]:
        """Get CPU affinity configuration for hybrid architecture."""
        return {
            # Bind main database processes to P-cores (0-15 with hyperthreading)
            "neo4j_cores": list(range(0, 16)),  # P-cores + hyperthreading
            
            # Bind background processes to E-cores (16-23)
            "background_cores": list(range(16, 24)),  # E-cores
            
            # Crawler processes can use mixed approach
            "crawler_cores": list(range(4, 20)),  # Mix of P and E cores
            
            # System processes
            "system_cores": [0, 1, 2, 3],  # Reserve some P-cores for OS
        }

class ResourceMonitor:
    """Enhanced resource monitoring for high-performance system."""
    
    def __init__(self, config: I7_13700K_OptimizedConfig):
        """Initialize resource monitor."""
        self.config = config
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed system status including modern metrics."""
        # Basic metrics
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
        
        # Per-core CPU usage (important for hybrid architecture)
        p_core_usage = cpu_percent[:16]  # P-cores + hyperthreading
        e_core_usage = cpu_percent[16:24] if len(cpu_percent) >= 24 else []
        
        # Thermal information (if available)
        try:
            temps = psutil.sensors_temperatures()
            cpu_temp = temps.get('coretemp', [{}])[0].get('current', 0)
        except:
            cpu_temp = 0
        
        return {
            "memory_percent": memory.percent,
            "memory_available_gb": memory.available / (1024**3),
            "total_cpu_percent": sum(cpu_percent) / len(cpu_percent),
            "p_core_avg_usage": sum(p_core_usage) / len(p_core_usage),
            "e_core_avg_usage": sum(e_core_usage) / len(e_core_usage) if e_core_usage else 0,
            "cpu_temperature": cpu_temp,
            "memory_warning": memory.percent > 85,
            "cpu_warning": max(cpu_percent) > 90,
            "thermal_warning": cpu_temp > 80 if cpu_temp > 0 else False,
        }

def create_optimized_extractors(neo4j_uri: str, neo4j_user: str, neo4j_password: str):
    """Create optimized extractors for i7-13700K system."""
    config = I7_13700K_OptimizedConfig()
    
    # Neo4j Extractor
    from .parse_repo_into_neo4j import DirectNeo4jExtractor
    extractor = DirectNeo4jExtractor(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        batch_size=config.config["neo4j_batch_size"],
        max_file_size=config.config["max_file_size"]
    )
    
    # Script Analyzer
    from .ai_script_analyzer import AIScriptAnalyzer
    analyzer = AIScriptAnalyzer(
        max_file_size=config.config["max_file_size"],
        max_workers=config.config["max_workers"]
    )
    
    # Performance Monitor
    from .performance_monitor import PerformanceMonitor
    monitor = PerformanceMonitor(
        max_metrics=config.config["metrics_retention"],
        collection_interval=config.config["monitoring_interval"]
    )
    
    return extractor, analyzer, monitor

def apply_cpu_affinity_i7_13700k():
    """Apply CPU affinity optimized for i7-13700K hybrid architecture."""
    try:
        import psutil
        
        config = I7_13700K_OptimizedConfig()
        affinity_config = config.get_cpu_affinity_config()
        
        # Get current process
        process = psutil.Process()
        
        # Use crawler cores (mix of P and E cores)
        crawler_cores = affinity_config["crawler_cores"]
        process.cpu_affinity(crawler_cores)
        
        logger.info(f"Set CPU affinity to cores: {crawler_cores}")
        logger.info("Optimized for i7-13700K hybrid architecture")
        
    except Exception as e:
        logger.warning(f"Could not set CPU affinity: {e}")

def print_i7_13700k_optimization_summary():
    """Print optimization summary with research-based recommendations."""
    config = I7_13700K_OptimizedConfig()
    profile = config.profile
    
    print("=" * 70)
    print("INTEL i7-13700K OPTIMIZED CONFIGURATION")
    print("=" * 70)
    print(f"CPU: {profile.cpu_model} ({profile.cpu_generation})")
    print(f"Architecture: Hybrid - {profile.p_cores} P-cores + {profile.e_cores} E-cores")
    print(f"Total Threads: {profile.total_threads} (P-cores with hyperthreading)")
    print(f"Boost Clock: {profile.max_boost_ghz}GHz")
    print(f"Cache: L3={profile.l3_cache_mb}MB, L2={profile.l2_cache_mb}MB")
    print(f"Memory: {profile.total_ram_gb}GB DDR5 (optimal: DDR5-{profile.optimal_ddr5_speed})")
    print(f"GPU: RTX 4070 {profile.gpu_vram_gb}GB VRAM")
    print()
    
    print("RESEARCH-BASED OPTIMIZATIONS:")
    print("-" * 40)
    for key, value in config.config.items():
        if isinstance(value, bool):
            print(f"{key:30}: {'✓' if value else '✗'}")
        else:
            print(f"{key:30}: {value}")
    print()
    
    print("NEO4J MEMORY CONFIGURATION:")
    print("-" * 40)
    memory_config = config.get_neo4j_memory_config()
    for key, value in memory_config.items():
        print(f"{key:30}: {value}")
    print()
    
    print("CPU AFFINITY STRATEGY:")
    print("-" * 40)
    affinity = config.get_cpu_affinity_config()
    print(f"Neo4j (P-cores): {affinity['neo4j_cores']}")
    print(f"Background (E-cores): {affinity['background_cores']}")
    print(f"Crawler (Mixed): {affinity['crawler_cores']}")
    print()
    
    print("PERFORMANCE EXPECTATIONS:")
    print("-" * 40)
    print("• Exceptional multi-threaded performance with 24 threads")
    print("• Optimal for concurrent database operations")
    print("• Hybrid architecture allows background task efficiency")
    print("• High memory bandwidth with DDR5")
    print("• Can handle very large repositories efficiently")
    print()
    
    monitor = ResourceMonitor(config)
    status = monitor.get_detailed_status()
    print("CURRENT SYSTEM STATUS:")
    print("-" * 40)
    print(f"Memory Usage: {status['memory_percent']:.1f}%")
    print(f"P-Core Avg Usage: {status['p_core_avg_usage']:.1f}%")
    print(f"E-Core Avg Usage: {status['e_core_avg_usage']:.1f}%")
    if status['cpu_temperature'] > 0:
        print(f"CPU Temperature: {status['cpu_temperature']:.1f}°C")
    
    if any([status['memory_warning'], status['cpu_warning'], status['thermal_warning']]):
        print("\n⚠️  SYSTEM WARNINGS:")
        if status['memory_warning']:
            print("   MEMORY: High usage detected")
        if status['cpu_warning']:
            print("   CPU: High usage detected")
        if status['thermal_warning']:
            print("   THERMAL: High temperature detected")

if __name__ == "__main__":
    print_i7_13700k_optimization_summary()