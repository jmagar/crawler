"""
Hardware-optimized configuration for i7-3770K, 32GB RAM, RTX 4070 12GB VRAM.

This module provides optimized settings tailored for the specific hardware configuration
to maximize performance while staying within hardware limits.
"""
import os
import psutil
import logging
from typing import Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class HardwareProfile:
    """Hardware profile for optimization."""
    cpu_cores: int
    cpu_threads: int
    total_ram_gb: int
    available_ram_gb: int
    gpu_vram_gb: int
    cpu_model: str
    
    def __post_init__(self):
        """Validate hardware profile."""
        if self.cpu_threads < self.cpu_cores:
            self.cpu_threads = self.cpu_cores
        
        if self.available_ram_gb > self.total_ram_gb:
            self.available_ram_gb = self.total_ram_gb

# Hardware profile for i7-3770K system
I7_3770K_PROFILE = HardwareProfile(
    cpu_cores=4,           # 4 physical cores
    cpu_threads=8,         # 8 threads with hyperthreading
    total_ram_gb=32,       # 32GB total RAM
    available_ram_gb=28,   # Conservative estimate (leaving 4GB for OS)
    gpu_vram_gb=12,        # RTX 4070 12GB VRAM
    cpu_model="i7-3770K"
)

class HardwareOptimizedConfig:
    """Generate optimized configuration based on hardware profile."""
    
    def __init__(self, profile: HardwareProfile = I7_3770K_PROFILE):
        """Initialize with hardware profile."""
        self.profile = profile
        self.config = self._generate_config()
    
    def _generate_config(self) -> Dict[str, Any]:
        """Generate optimized configuration for the hardware."""
        # Calculate optimal settings based on hardware
        
        # CPU-bound task configuration
        # i7-3770K: 4 cores/8 threads, but older architecture (2012)
        # Conservative thread allocation to avoid overwhelming older CPU
        max_workers = max(2, min(self.profile.cpu_threads - 2, 6))  # Leave 2 threads for OS
        
        # Memory-based configuration
        # 32GB RAM allows for larger operations, but be conservative with older DDR3
        available_memory_mb = int(self.profile.available_ram_gb * 1024)
        
        # Batch sizes based on available memory
        # Conservative for older system to avoid swapping
        neo4j_batch_size = min(300, max(100, available_memory_mb // 100))
        file_batch_size = min(150, max(50, available_memory_mb // 200))
        
        # File size limits (more generous with 32GB RAM)
        max_file_size = min(1024 * 1024, available_memory_mb * 1024 // 1000)  # Up to 1MB per file
        
        # Concurrency limits
        max_concurrent_analyses = max(4, min(max_workers, 8))
        max_concurrent_queries = max(2, min(max_workers // 2, 4))
        
        # Performance monitoring configuration
        monitoring_interval = 2.0  # More frequent monitoring for older hardware
        
        return {
            # CPU Configuration
            "max_workers": max_workers,
            "max_concurrent_analyses": max_concurrent_analyses,
            "max_concurrent_queries": max_concurrent_queries,
            
            # Memory Configuration
            "neo4j_batch_size": neo4j_batch_size,
            "file_batch_size": file_batch_size,
            "max_file_size": max_file_size,
            "pagination_page_size": 200,  # Larger pages with more RAM
            
            # Performance Monitoring
            "monitoring_interval": monitoring_interval,
            "metrics_retention": 5000,  # Keep more metrics in memory
            
            # Neo4j Specific
            "neo4j_heap_initial": "2G",
            "neo4j_heap_max": "4G",
            "neo4j_pagecache": "8G",  # Generous pagecache for 32GB system
            
            # System Resource Limits
            "max_memory_usage_percent": 70,  # Conservative for system stability
            "cpu_usage_threshold": 80,       # Alert threshold for older CPU
            
            # Hardware-specific optimizations
            "use_cpu_affinity": True,        # Pin processes to specific cores
            "enable_numa_optimization": False,  # Single socket system
            "prefer_memory_over_cpu": True,  # Leverage high RAM amount
        }
    
    def get_neo4j_docker_config(self) -> Dict[str, str]:
        """Get Neo4j Docker environment configuration."""
        return {
            "NEO4J_dbms_memory_heap_initial_size": self.config["neo4j_heap_initial"],
            "NEO4J_dbms_memory_heap_max_size": self.config["neo4j_heap_max"],
            "NEO4J_dbms_memory_pagecache_size": self.config["neo4j_pagecache"],
            "NEO4J_dbms_jvm_additional": "-XX:+UseG1GC -XX:+UnlockExperimentalVMOptions -XX:+UseTransparentHugePages",
            "NEO4J_dbms_security_procedures_unrestricted": "apoc.*",
            "NEO4J_dbms_security_procedures_allowlist": "apoc.*",
            "NEO4J_PLUGINS": "apoc",
            "NEO4J_dbms_logs_gc_enabled": "true",
            "NEO4J_dbms_logs_gc_options": "-Xloggc:gc.log -XX:+UseGCLogFileRotation -XX:NumberOfGCLogFiles=3 -XX:GCLogFileSize=20m"
        }
    
    def get_system_tuning_commands(self) -> list[str]:
        """Get system tuning commands for optimal performance."""
        return [
            # Disable swap to prevent performance degradation
            "sudo swapoff -a",
            
            # Tune virtual memory for database workloads
            "sudo sysctl -w vm.swappiness=1",
            "sudo sysctl -w vm.dirty_ratio=5",
            "sudo sysctl -w vm.dirty_background_ratio=2",
            
            # Network optimizations for Neo4j
            "sudo sysctl -w net.core.rmem_default=262144",
            "sudo sysctl -w net.core.rmem_max=16777216",
            "sudo sysctl -w net.core.wmem_default=262144",
            "sudo sysctl -w net.core.wmem_max=16777216",
            
            # File system optimizations
            "sudo sysctl -w fs.file-max=1000000",
            
            # CPU governor for performance (older CPU benefits from performance mode)
            "sudo cpupower frequency-set -g performance",
        ]

class OptimizedExtractorFactory:
    """Factory for creating hardware-optimized extractors."""
    
    def __init__(self, config: HardwareOptimizedConfig):
        """Initialize with hardware configuration."""
        self.config = config
    
    def create_neo4j_extractor(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        """Create optimized Neo4j extractor."""
        from .parse_repo_into_neo4j import DirectNeo4jExtractor
        
        return DirectNeo4jExtractor(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            batch_size=self.config.config["neo4j_batch_size"],
            max_file_size=self.config.config["max_file_size"]
        )
    
    def create_script_analyzer(self):
        """Create optimized script analyzer."""
        from .ai_script_analyzer import AIScriptAnalyzer
        
        return AIScriptAnalyzer(
            max_file_size=self.config.config["max_file_size"],
            max_workers=self.config.config["max_workers"]
        )
    
    def create_performance_monitor(self):
        """Create optimized performance monitor."""
        from .performance_monitor import PerformanceMonitor
        
        return PerformanceMonitor(
            max_metrics=self.config.config["metrics_retention"],
            collection_interval=self.config.config["monitoring_interval"]
        )

class ResourceGuard:
    """Monitor and protect system resources during intensive operations."""
    
    def __init__(self, config: HardwareOptimizedConfig):
        """Initialize resource guard."""
        self.config = config
        self.max_memory_percent = config.config["max_memory_usage_percent"]
        self.max_cpu_percent = config.config["cpu_usage_threshold"]
        
    def check_resources(self) -> Dict[str, Any]:
        """Check current resource usage."""
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        
        return {
            "memory_percent": memory.percent,
            "memory_available_gb": memory.available / (1024**3),
            "cpu_percent": cpu_percent,
            "memory_warning": memory.percent > self.max_memory_percent,
            "cpu_warning": cpu_percent > self.max_cpu_percent
        }
    
    def should_throttle(self) -> bool:
        """Check if operations should be throttled."""
        resources = self.check_resources()
        return resources["memory_warning"] or resources["cpu_warning"]
    
    def get_throttling_suggestions(self) -> Dict[str, str]:
        """Get suggestions for throttling operations."""
        resources = self.check_resources()
        suggestions = {}
        
        if resources["memory_warning"]:
            suggestions["memory"] = "Reduce batch sizes or enable more aggressive garbage collection"
        
        if resources["cpu_warning"]:
            suggestions["cpu"] = "Reduce worker threads or add delays between operations"
        
        return suggestions

def get_optimized_docker_compose() -> str:
    """Generate optimized docker-compose.yaml for the hardware."""
    config = HardwareOptimizedConfig()
    neo4j_env = config.get_neo4j_docker_config()
    
    env_vars = "\n".join([f"      - {k}={v}" for k, v in neo4j_env.items()])
    
    return f"""version: '3.8'

services:
  neo4j:
    image: neo4j:5.15-community
    container_name: crawler-neo4j-optimized
    restart: unless-stopped
    ports:
      - "7474:7474"
      - "7687:7687"
    environment:
      - NEO4J_AUTH=${{NEO4J_USER:-neo4j}}/${{NEO4J_PASSWORD}}
{env_vars}
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_conf:/conf
      - neo4j_plugins:/plugins
    networks:
      - crawler-network
    # Resource limits for i7-3770K system
    deploy:
      resources:
        limits:
          memory: 12G  # Leave 20GB for other processes
        reservations:
          memory: 6G
    # CPU affinity - use cores 0,1 for Neo4j
    cpuset: "0,1"
    
  qdrant:
    image: qdrant/qdrant:latest
    container_name: crawler-qdrant-optimized
    restart: unless-stopped
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - crawler-network
    # Resource limits
    deploy:
      resources:
        limits:
          memory: 8G
        reservations:
          memory: 2G
    # CPU affinity - use cores 2,3 for Qdrant
    cpuset: "2,3"

volumes:
  neo4j_data:
  neo4j_logs:
  neo4j_conf:
  neo4j_plugins:
  qdrant_data:

networks:
  crawler-network:
    driver: bridge
"""

def apply_cpu_affinity():
    """Apply CPU affinity for optimal performance on i7-3770K."""
    try:
        import psutil
        
        # Get current process
        process = psutil.Process()
        
        # Set CPU affinity to cores 4-7 (threads 4-7 on i7-3770K)
        # Leave cores 0-3 for system and databases
        available_cores = list(range(psutil.cpu_count()))
        if len(available_cores) >= 8:
            # Use the second set of threads for the crawler
            crawler_cores = available_cores[4:8]
            process.cpu_affinity(crawler_cores)
            logger.info(f"Set CPU affinity to cores: {crawler_cores}")
        else:
            logger.warning("Not enough CPU cores for optimal affinity setting")
            
    except Exception as e:
        logger.warning(f"Could not set CPU affinity: {e}")

def print_optimization_summary():
    """Print optimization summary for the hardware."""
    config = HardwareOptimizedConfig()
    
    print("=" * 60)
    print("HARDWARE-OPTIMIZED CONFIGURATION")
    print("=" * 60)
    print(f"Target Hardware: {config.profile.cpu_model}")
    print(f"CPU Cores/Threads: {config.profile.cpu_cores}/{config.profile.cpu_threads}")
    print(f"Total RAM: {config.profile.total_ram_gb}GB")
    print(f"Available RAM: {config.profile.available_ram_gb}GB")
    print(f"GPU VRAM: {config.profile.gpu_vram_gb}GB")
    print()
    
    print("OPTIMIZED SETTINGS:")
    print("-" * 30)
    for key, value in config.config.items():
        print(f"{key:25}: {value}")
    print()
    
    print("PERFORMANCE RECOMMENDATIONS:")
    print("-" * 30)
    print("• Use performance CPU governor for older CPU")
    print("• Disable swap to prevent performance degradation")
    print("• Pin Neo4j and Qdrant to separate CPU cores")
    print("• Use generous page cache with 32GB RAM")
    print("• Monitor CPU temperature under load")
    print("• Consider SSD for Neo4j data directory")
    print()
    
    guard = ResourceGuard(config)
    resources = guard.check_resources()
    print("CURRENT SYSTEM STATUS:")
    print("-" * 30)
    print(f"Memory Usage: {resources['memory_percent']:.1f}%")
    print(f"Available Memory: {resources['memory_available_gb']:.1f}GB")
    print(f"CPU Usage: {resources['cpu_percent']:.1f}%")
    
    if guard.should_throttle():
        print("\n⚠️  RESOURCE WARNING:")
        suggestions = guard.get_throttling_suggestions()
        for resource, suggestion in suggestions.items():
            print(f"   {resource.upper()}: {suggestion}")

if __name__ == "__main__":
    print_optimization_summary()