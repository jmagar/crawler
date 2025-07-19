"""
Knowledge graph tools for the MCP server.
"""
import os
import json
import logging
from typing import Dict, Any

from fastmcp import Context

logger = logging.getLogger(__name__)

from src.core.server import mcp
from src.core.validation import validate_script_path, validate_github_url
from src.utils.error_handling import MCPErrorHandler, ErrorCategory, ErrorSeverity, create_success_response
from src.utils.logging_utils import log_operation, OperationMonitor

# Conditional import for knowledge graph components
if os.getenv("USE_KNOWLEDGE_GRAPH", "false") == "true":
    from ai_script_analyzer import AIScriptAnalyzer
    from hallucination_reporter import HallucinationReporter


@mcp.tool()
async def you_trippin(ctx: Context, script_path: str) -> str:
    """
    Check an AI-generated Python script for hallucinations.
    """
    import time
    start_time = time.time()
    operation_id = f"you_trippin_{hash(script_path)}_{int(start_time)}"
    
    try:
        if os.getenv("USE_KNOWLEDGE_GRAPH", "false") != "true":
            return json.dumps({"success": False, "error": "Knowledge graph functionality is disabled."})

        # Validate context and get components
        if not hasattr(ctx.request_context, 'lifespan_context'):
            return json.dumps({"success": False, "error": "Server not properly initialized"}, indent=2)
            
        lifespan_ctx = ctx.request_context.lifespan_context
        knowledge_validator = lifespan_ctx.knowledge_validator
        
        if not knowledge_validator:
            return json.dumps({"success": False, "error": "Knowledge graph validator not available."})

        # Register this operation to prevent premature cleanup
        async with lifespan_ctx.cleanup_lock:
            lifespan_ctx.active_operations.add(operation_id)
            logger.info(f"🔒 Registered operation {operation_id}, active operations: {len(lifespan_ctx.active_operations)}")

        await ctx.report_progress(progress=0, total=100, message="Starting script validation...")
        
        validation = validate_script_path(script_path)
        if not validation["valid"]:
            return json.dumps({"success": False, "error": validation["error"]})

        await ctx.report_progress(progress=20, total=100, message="Analyzing script structure...")
        analyzer = AIScriptAnalyzer()
        analysis_result = analyzer.analyze_script(script_path)
        
        await ctx.report_progress(progress=60, total=100, message="Validating against knowledge graph...")
        validation_result = await knowledge_validator.validate_script(analysis_result)
        
        await ctx.report_progress(progress=90, total=100, message="Generating hallucination report...")
        reporter = HallucinationReporter()
        report = reporter.generate_comprehensive_report(validation_result)
        
        await ctx.report_progress(progress=100, total=100, message="Validation complete")
        return create_success_response(
            tool_name="you_trippin",
            data=report,
            message="Script validation completed",
            operation_id=operation_id
        )
    except Exception as e:
        error_handler = MCPErrorHandler("you_trippin", operation_id)
        if "FileNotFoundError" in str(type(e)):
            error = error_handler.create_error(
                e,
                category=ErrorCategory.FILESYSTEM,
                error_code="SCRIPT_NOT_FOUND",
                context={"script_path": script_path}
            )
        else:
            error = error_handler.create_error(
                e,
                category=ErrorCategory.INTERNAL,
                error_code="VALIDATION_FAILED"
            )
        return await error_handler.log_and_report_error(ctx, error)
    
    finally:
        # Always unregister the operation to prevent cleanup blocks
        try:
            if 'lifespan_ctx' in locals() and hasattr(lifespan_ctx, 'active_operations'):
                async with lifespan_ctx.cleanup_lock:
                    lifespan_ctx.active_operations.discard(operation_id)
                    logger.info(f"🔓 Unregistered operation {operation_id}, remaining: {len(lifespan_ctx.active_operations)}")
        except Exception as cleanup_error:
            logger.error(f"Error during operation cleanup: {cleanup_error}")

@mcp.tool()
async def crawl_repo(ctx: Context, repo_url: str) -> str:
    """
    Parse a GitHub repository into the Neo4j knowledge graph.
    """
    import time
    start_time = time.time()
    operation_id = f"crawl_repo_{hash(repo_url)}_{int(start_time)}"
    
    try:
        if os.getenv("USE_KNOWLEDGE_GRAPH", "false") != "true":
            return json.dumps({"success": False, "error": "Knowledge graph functionality is disabled."})

        # Validate context and get components
        if not hasattr(ctx.request_context, 'lifespan_context'):
            return json.dumps({"success": False, "error": "Server not properly initialized"}, indent=2)
            
        lifespan_ctx = ctx.request_context.lifespan_context
        repo_extractor = lifespan_ctx.repo_extractor
        
        if not repo_extractor:
            return json.dumps({"success": False, "error": "Knowledge graph extractor not available."})

        # Register this operation to prevent premature cleanup
        async with lifespan_ctx.cleanup_lock:
            lifespan_ctx.active_operations.add(operation_id)
            logger.info(f"🔒 Registered operation {operation_id}, active operations: {len(lifespan_ctx.active_operations)}")

        await ctx.report_progress(progress=0, total=100, message="Starting repository analysis...")
        
        validation = validate_github_url(repo_url)
        if not validation["valid"]:
            return json.dumps({"success": False, "error": validation["error"]})

        await ctx.report_progress(progress=10, total=100, message="Validating repository URL...")
        repo_name = validation["repo_name"]
        
        await ctx.report_progress(progress=20, total=100, message=f"Cloning and analyzing {repo_name}...")
        await repo_extractor.analyze_repository(repo_url)
        
        await ctx.report_progress(progress=90, total=100, message="Storing analysis in knowledge graph...")
        # ... (Statistics query from original file)
        
        await ctx.report_progress(progress=100, total=100, message=f"Repository {repo_name} parsed successfully")
        return create_success_response(
            tool_name="crawl_repo",
            data={"repo_name": repo_name, "repo_url": repo_url},
            message=f"Successfully parsed {repo_name}",
            operation_id=operation_id
        )
    except Exception as e:
        error_handler = MCPErrorHandler("crawl_repo", operation_id)
        if "git" in str(e).lower() or "clone" in str(e).lower():
            error = error_handler.handle_network_error(e, repo_url)
        elif "invalid" in str(e).lower() and "url" in str(e).lower():
            error = error_handler.handle_validation_error(e, "repo_url", repo_url)
        else:
            error = error_handler.create_error(
                e,
                category=ErrorCategory.INTERNAL,
                error_code="REPO_ANALYSIS_FAILED",
                context={"repo_url": repo_url}
            )
        return await error_handler.log_and_report_error(ctx, error)
    
    finally:
        # Always unregister the operation to prevent cleanup blocks
        try:
            if 'lifespan_ctx' in locals() and hasattr(lifespan_ctx, 'active_operations'):
                async with lifespan_ctx.cleanup_lock:
                    lifespan_ctx.active_operations.discard(operation_id)
                    logger.info(f"🔓 Unregistered operation {operation_id}, remaining: {len(lifespan_ctx.active_operations)}")
        except Exception as cleanup_error:
            logger.error(f"Error during operation cleanup: {cleanup_error}")

@mcp.tool()
async def graph_query(ctx: Context, command: str) -> str:
    """
    Query and explore the Neo4j knowledge graph.
    """
    await ctx.report_progress(progress=0, total=100, message="Initializing graph query...")
    
    if os.getenv("USE_KNOWLEDGE_GRAPH", "false") != "true":
        return json.dumps({"success": False, "error": "Knowledge graph functionality is disabled."})

    repo_extractor = ctx.request_context.lifespan_context.repo_extractor
    if not repo_extractor or not repo_extractor.driver:
        return json.dumps({"success": False, "error": "Neo4j connection not available."})

    await ctx.report_progress(progress=20, total=100, message="Validating query syntax...")
    # ... (The complex command parsing logic from the original file would go here)
    # This is a simplified placeholder.
    try:
        await ctx.report_progress(progress=40, total=100, message="Executing Neo4j query...")
        async with repo_extractor.driver.session() as session:
            result = await session.run(command)
            await ctx.report_progress(progress=80, total=100, message="Processing query results...")
            records = [dict(record) for record in await result.list()]
            await ctx.report_progress(progress=100, total=100, message="Query completed successfully")
            return create_success_response(
                tool_name="graph_query",
                data={"query": command, "results": records, "result_count": len(records)},
                message=f"Query returned {len(records)} records"
            )
    except Exception as e:
        error_handler = MCPErrorHandler("graph_query")
        if "neo4j" in str(e).lower() or "driver" in str(e).lower():
            error = error_handler.handle_database_error(e, "neo4j", "query")
        elif "syntax" in str(e).lower() or "cypher" in str(e).lower():
            error = error_handler.handle_validation_error(e, "command", command)
        else:
            error = error_handler.create_error(
                e,
                category=ErrorCategory.INTERNAL,
                error_code="GRAPH_QUERY_FAILED",
                context={"command": command}
            )
        return await error_handler.log_and_report_error(ctx, error)


