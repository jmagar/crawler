"""
Progress reporting utilities for MCP tools.
"""
import asyncio
from typing import Optional
from fastmcp import Context


class ProgressReporter:
    """
    Enhanced progress reporting utility for long-running MCP operations.
    """
    
    def __init__(self, ctx: Context, tool_name: str, total_steps: int = 100):
        """
        Initialize progress reporter.
        
        Args:
            ctx: FastMCP context for progress reporting
            tool_name: Name of the tool for logging
            total_steps: Total progress steps (default: 100)
        """
        self.ctx = ctx
        self.tool_name = tool_name
        self.total_steps = total_steps
        self.current_progress = 0
        
    async def report(self, progress: int, message: str = None, force: bool = False):
        """
        Report progress with optional message.
        
        Args:
            progress: Progress value (0-total_steps)
            message: Optional progress message
            force: Force report even if progress hasn't changed
        """
        if force or progress != self.current_progress:
            self.current_progress = progress
            display_message = message or f"{self.tool_name} in progress..."
            await self.ctx.report_progress(
                progress=progress, 
                total=self.total_steps, 
                message=display_message
            )
    
    async def start(self, message: str = None):
        """Start progress reporting."""
        await self.report(0, message or f"Starting {self.tool_name}...")
    
    async def update(self, progress: int, message: str = None):
        """Update progress."""
        await self.report(progress, message)
    
    async def complete(self, message: str = None):
        """Complete progress reporting."""
        await self.report(self.total_steps, message or f"{self.tool_name} completed successfully")


class BatchProgressReporter(ProgressReporter):
    """
    Progress reporter for batch operations with automatic progress calculation.
    """
    
    def __init__(self, ctx: Context, tool_name: str, total_items: int, start_progress: int = 0, end_progress: int = 100):
        """
        Initialize batch progress reporter.
        
        Args:
            ctx: FastMCP context for progress reporting
            tool_name: Name of the tool for logging
            total_items: Total number of items to process
            start_progress: Starting progress value
            end_progress: Ending progress value
        """
        super().__init__(ctx, tool_name, 100)
        self.total_items = total_items
        self.start_progress = start_progress
        self.end_progress = end_progress
        self.progress_range = end_progress - start_progress
        self.processed_items = 0
    
    async def report_item_progress(self, item_name: str = None, increment: int = 1):
        """
        Report progress for processing a single item.
        
        Args:
            item_name: Optional name of the item being processed
            increment: Number of items processed (default: 1)
        """
        self.processed_items += increment
        
        # Calculate progress within the specified range
        if self.total_items > 0:
            item_progress = (self.processed_items / self.total_items) * self.progress_range
            current_progress = self.start_progress + int(item_progress)
        else:
            current_progress = self.end_progress
        
        message = f"Processed {self.processed_items}/{self.total_items}"
        if item_name:
            message += f" - {item_name}"
            
        await self.report(current_progress, message)


async def with_progress_reporting(ctx: Context, tool_name: str, operation_func, *args, **kwargs):
    """
    Wrapper function to add automatic progress reporting to any async operation.
    
    Args:
        ctx: FastMCP context
        tool_name: Name of the tool for progress reporting
        operation_func: Async function to execute
        *args, **kwargs: Arguments to pass to operation_func
    
    Returns:
        Result of operation_func
    """
    reporter = ProgressReporter(ctx, tool_name)
    
    try:
        await reporter.start()
        
        # Create a task for the operation
        operation_task = asyncio.create_task(operation_func(*args, **kwargs))
        
        # Simple progress simulation while operation runs
        progress_step = 10
        current_progress = 10
        
        while not operation_task.done() and current_progress < 90:
            await asyncio.sleep(0.5)  # Check every 500ms
            await reporter.update(current_progress, f"{tool_name} in progress...")
            current_progress = min(current_progress + progress_step, 90)
        
        # Wait for the operation to complete
        result = await operation_task
        
        await reporter.complete()
        return result
        
    except Exception as e:
        await reporter.report(0, f"{tool_name} failed: {str(e)}", force=True)
        raise


class MultiStageProgressReporter:
    """
    Progress reporter for operations with multiple distinct stages.
    """
    
    def __init__(self, ctx: Context, tool_name: str, stages: list):
        """
        Initialize multi-stage progress reporter.
        
        Args:
            ctx: FastMCP context for progress reporting
            tool_name: Name of the tool for logging
            stages: List of stage names/descriptions
        """
        self.ctx = ctx
        self.tool_name = tool_name
        self.stages = stages
        self.total_stages = len(stages)
        self.current_stage = 0
        
    async def start_stage(self, stage_index: int, message: str = None):
        """
        Start a specific stage.
        
        Args:
            stage_index: Index of the stage (0-based)
            message: Optional custom message
        """
        if stage_index < len(self.stages):
            self.current_stage = stage_index
            progress = int((stage_index / self.total_stages) * 100)
            stage_message = message or f"Starting {self.stages[stage_index]}..."
            
            await self.ctx.report_progress(
                progress=progress,
                total=100,
                message=f"[{stage_index + 1}/{self.total_stages}] {stage_message}"
            )
    
    async def complete_stage(self, stage_index: int, message: str = None):
        """
        Complete a specific stage.
        
        Args:
            stage_index: Index of the stage (0-based)
            message: Optional custom message
        """
        if stage_index < len(self.stages):
            progress = int(((stage_index + 1) / self.total_stages) * 100)
            stage_message = message or f"Completed {self.stages[stage_index]}"
            
            await self.ctx.report_progress(
                progress=progress,
                total=100,
                message=f"[{stage_index + 1}/{self.total_stages}] {stage_message}"
            )
    
    async def complete_all(self, message: str = None):
        """Complete all stages."""
        final_message = message or f"{self.tool_name} completed successfully"
        await self.ctx.report_progress(progress=100, total=100, message=final_message)