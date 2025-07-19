"""
Performance monitoring and metrics collection for the knowledge graph system.
"""
import asyncio
import logging
import time
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
import statistics
import json
import psutil
import threading
from contextlib import asynccontextmanager, suppress

logger = logging.getLogger(__name__)

@dataclass
class PerformanceMetric:
    """Individual performance metric data."""
    name: str
    value: float
    timestamp: float
    category: str = "general"
    tags: dict[str, str] = field(default_factory=dict)

@dataclass
class SystemMetrics:
    """System resource metrics."""
    cpu_percent: float
    memory_percent: float
    memory_available: int
    disk_usage_percent: float
    timestamp: float

class PerformanceMonitor:
    """Monitor and collect performance metrics for the knowledge graph system."""
    
    def __init__(self, max_metrics: int = 10000, collection_interval: float = 5.0):
        """Initialize the performance monitor.
        
        Args:
            max_metrics: Maximum number of metrics to keep in memory
            collection_interval: Interval between system metric collections (seconds)
        """
        self.max_metrics = max_metrics
        self.collection_interval = collection_interval
        self.metrics = deque(maxlen=max_metrics)
        self.aggregated_metrics = defaultdict(list)
        self.system_metrics = deque(maxlen=1000)
        self.is_collecting = False
        self.collection_task = None
        self._lock = threading.Lock()
    
    def start_collection(self):
        """Start automated system metrics collection."""
        if self.is_collecting:
            return
        
        self.is_collecting = True
        self.collection_task = asyncio.create_task(self._collect_system_metrics())
        logger.info("Performance monitoring started")
    
    async def stop_collection(self):
        """Stop automated metrics collection."""
        if not self.is_collecting:
            return
        
        self.is_collecting = False
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            with suppress(asyncio.CancelledError):
                await self.collection_task
        logger.info("Performance monitoring stopped")
    
    def record_metric(self, name: str, value: float, category: str = "general", 
                     tags: dict[str, str] = None):
        """Record a performance metric.
        
        Args:
            name: Metric name
            value: Metric value
            category: Metric category
            tags: Additional tags for the metric
        """
        metric = PerformanceMetric(
            name=name,
            value=value,
            timestamp=time.time(),
            category=category,
            tags=tags or {}
        )
        
        with self._lock:
            self.metrics.append(metric)
            self.aggregated_metrics[name].append(value)
            
            # Keep aggregated metrics within limits
            if len(self.aggregated_metrics[name]) > 1000:
                self.aggregated_metrics[name] = self.aggregated_metrics[name][-1000:]
    
    @asynccontextmanager
    async def measure_operation(self, operation_name: str, category: str = "operation",
                              tags: Dict[str, str] = None):
        """Context manager to measure operation duration.
        
        Args:
            operation_name: Name of the operation being measured
            category: Category for the metric
            tags: Additional tags
        """
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss
        
        try:
            yield
        finally:
            duration = time.time() - start_time
            end_memory = psutil.Process().memory_info().rss
            memory_delta = end_memory - start_memory
            
            self.record_metric(
                f"{operation_name}_duration",
                duration,
                category,
                tags
            )
            
            self.record_metric(
                f"{operation_name}_memory_delta",
                memory_delta,
                category,
                tags
            )
    
    async def measure_async_function(self, func: Callable, *args, **kwargs) -> Any:
        """Measure an async function's performance.
        
        Args:
            func: Async function to measure
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        func_name = getattr(func, '__name__', 'unknown_function')
        
        async with self.measure_operation(func_name, "function_call"):
            return await func(*args, **kwargs)
    
    def get_metric_summary(self, metric_name: str) -> Dict[str, float]:
        """Get statistical summary of a metric.
        
        Args:
            metric_name: Name of the metric
            
        Returns:
            Dictionary with statistical summary
        """
        values = self.aggregated_metrics.get(metric_name, [])
        
        if not values:
            return {"count": 0}
        
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
            "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
            "p95": self._percentile(values, 95),
            "p99": self._percentile(values, 99)
        }
    
    def get_all_metrics_summary(self) -> Dict[str, Dict[str, float]]:
        """Get summary of all collected metrics.
        
        Returns:
            Dictionary mapping metric names to their summaries
        """
        summaries = {}
        
        with self._lock:
            for metric_name in self.aggregated_metrics:
                summaries[metric_name] = self.get_metric_summary(metric_name)
        
        return summaries
    
    def get_recent_metrics(self, minutes: int = 10) -> List[PerformanceMetric]:
        """Get metrics from the last N minutes.
        
        Args:
            minutes: Number of minutes to look back
            
        Returns:
            List of recent metrics
        """
        cutoff_time = time.time() - (minutes * 60)
        
        with self._lock:
            return [m for m in self.metrics if m.timestamp >= cutoff_time]
    
    def get_system_metrics_summary(self) -> Dict[str, float]:
        """Get summary of system metrics.
        
        Returns:
            Summary of system resource usage
        """
        if not self.system_metrics:
            return {}
        
        recent_metrics = list(self.system_metrics)[-100:]  # Last 100 readings
        
        cpu_values = [m.cpu_percent for m in recent_metrics]
        memory_values = [m.memory_percent for m in recent_metrics]
        
        return {
            "avg_cpu_percent": statistics.mean(cpu_values),
            "max_cpu_percent": max(cpu_values),
            "avg_memory_percent": statistics.mean(memory_values),
            "max_memory_percent": max(memory_values),
            "current_memory_available": recent_metrics[-1].memory_available if recent_metrics else 0,
            "sample_count": len(recent_metrics)
        }
    
    async def export_metrics(self, file_path: str, format: str = "json"):
        """Export collected metrics to a file.
        
        Args:
            file_path: Path to export file
            format: Export format ("json" or "csv")
        """
        if format == "json":
            await self._export_json(file_path)
        elif format == "csv":
            await self._export_csv(file_path)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    async def _export_json(self, file_path: str):
        """Export metrics to JSON format."""
        export_data = {
            "export_time": time.time(),
            "metrics_summary": self.get_all_metrics_summary(),
            "system_metrics_summary": self.get_system_metrics_summary(),
            "recent_metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "timestamp": m.timestamp,
                    "category": m.category,
                    "tags": m.tags
                }
                for m in self.get_recent_metrics(60)  # Last hour
            ]
        }
        
        async with asyncio.to_thread(open, file_path, 'w') as f:
            await asyncio.to_thread(json.dump, export_data, f, indent=2)
        
        logger.info(f"Metrics exported to {file_path}")
    
    async def _export_csv(self, file_path: str):
        """Export metrics to CSV format."""
        import csv
        
        recent_metrics = self.get_recent_metrics(60)
        
        async with asyncio.to_thread(open, file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            await asyncio.to_thread(
                writer.writerow,
                ['timestamp', 'name', 'value', 'category', 'tags']
            )
            
            for metric in recent_metrics:
                await asyncio.to_thread(
                    writer.writerow,
                    [
                        metric.timestamp,
                        metric.name,
                        metric.value,
                        metric.category,
                        json.dumps(metric.tags)
                    ]
                )
        
        logger.info(f"Metrics exported to {file_path}")
    
    async def _collect_system_metrics(self):
        """Continuously collect system metrics."""
        while self.is_collecting:
            try:
                # Get system metrics
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                system_metric = SystemMetrics(
                    cpu_percent=cpu_percent,
                    memory_percent=memory.percent,
                    memory_available=memory.available,
                    disk_usage_percent=disk.percent,
                    timestamp=time.time()
                )
                
                self.system_metrics.append(system_metric)
                
                # Record as individual metrics
                self.record_metric("system_cpu_percent", cpu_percent, "system")
                self.record_metric("system_memory_percent", memory.percent, "system")
                self.record_metric("system_memory_available", memory.available, "system")
                self.record_metric("system_disk_usage_percent", disk.percent, "system")
                
                await asyncio.sleep(self.collection_interval)
                
            except (OSError, psutil.Error, asyncio.TimeoutError) as e:
                logger.error(f"Error collecting system metrics: {str(e)}")
                await asyncio.sleep(self.collection_interval)
            except Exception as e:
                logger.critical(f"Unexpected error in system metrics collection: {str(e)}")
                await asyncio.sleep(self.collection_interval)
    
    def _percentile(self, values: list[float], percentile: float) -> float:
        """Calculate percentile of values.
        
        Args:
            values: List of values
            percentile: Percentile to calculate (0-100)
            
        Returns:
            Percentile value
        """
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * percentile / 100
        f = int(k)
        c = k - f
        
        if f == len(sorted_values) - 1:
            return sorted_values[f]
        
        return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c

class QueryPerformanceMonitor:
    """Specialized monitor for Neo4j query performance."""
    
    def __init__(self, performance_monitor: PerformanceMonitor):
        """Initialize query performance monitor.
        
        Args:
            performance_monitor: Main performance monitor instance
        """
        self.monitor = performance_monitor
        self.query_cache = {}
        self.slow_query_threshold = 1.0  # seconds
    
    @asynccontextmanager
    async def monitor_query(self, query_name: str, query: str, params: dict[str, Any] = None):
        """Monitor a Neo4j query execution.
        
        Args:
            query_name: Name/identifier for the query
            query: Cypher query string
            params: Query parameters
        """
        start_time = time.time()
        
        # Hash query for caching analysis (MD5 used for performance tracking only, not security)
        import hashlib
        query_hash = hashlib.md5(query.encode()).hexdigest()[:8]
        
        tags = {
            "query_name": query_name,
            "query_hash": query_hash,
            "param_count": str(len(params) if params else 0)
        }
        
        try:
            yield
            
            duration = time.time() - start_time
            
            # Record query metrics
            self.monitor.record_metric(
                "neo4j_query_duration",
                duration,
                "neo4j_query",
                tags
            )
            
            # Track slow queries
            if duration > self.slow_query_threshold:
                self.monitor.record_metric(
                    "neo4j_slow_query",
                    duration,
                    "neo4j_slow_query",
                    {**tags, "query_snippet": query[:100]}
                )
                
                logger.warning(f"Slow query detected: {query_name} took {duration:.2f}s")
            
            # Cache query performance data
            if query_name not in self.query_cache:
                self.query_cache[query_name] = []
            
            self.query_cache[query_name].append({
                "duration": duration,
                "timestamp": time.time(),
                "query_hash": query_hash
            })
            
            # Keep cache size manageable
            if len(self.query_cache[query_name]) > 1000:
                self.query_cache[query_name] = self.query_cache[query_name][-1000:]
        
        except Exception as e:
            duration = time.time() - start_time
            
            # Record failed query
            self.monitor.record_metric(
                "neo4j_query_error",
                duration,
                "neo4j_error",
                {**tags, "error_type": type(e).__name__}
            )
            
            raise
    
    def get_query_performance_report(self) -> Dict[str, Any]:
        """Generate a performance report for queries.
        
        Returns:
            Performance report with query statistics
        """
        report = {
            "total_queries": len(self.query_cache),
            "query_statistics": {},
            "slow_queries": [],
            "recommendations": []
        }
        
        for query_name, executions in self.query_cache.items():
            durations = [e["duration"] for e in executions]
            
            stats = {
                "execution_count": len(executions),
                "avg_duration": statistics.mean(durations),
                "max_duration": max(durations),
                "min_duration": min(durations),
                "p95_duration": self.monitor._percentile(durations, 95)
            }
            
            report["query_statistics"][query_name] = stats
            
            # Identify slow queries
            if stats["avg_duration"] > self.slow_query_threshold:
                report["slow_queries"].append({
                    "query_name": query_name,
                    "avg_duration": stats["avg_duration"],
                    "execution_count": stats["execution_count"]
                })
        
        # Generate recommendations
        if report["slow_queries"]:
            report["recommendations"].append(
                "Consider optimizing slow queries with indexes or query restructuring"
            )
        
        return report

# Global performance monitor instance
_global_monitor = None

def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor

def setup_performance_monitoring():
    """Set up and start performance monitoring."""
    monitor = get_performance_monitor()
    monitor.start_collection()
    return monitor

async def cleanup_performance_monitoring():
    """Clean up performance monitoring resources."""
    global _global_monitor
    if _global_monitor:
        await _global_monitor.stop_collection()
        _global_monitor = None