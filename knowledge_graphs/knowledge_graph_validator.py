"""
KnowledgeGraphValidator for validating AI-generated scripts against knowledge graph.
"""
import logging
from typing import Any
from neo4j import AsyncGraphDatabase
try:
    from src.core.validation import format_neo4j_error
except ImportError:
    def format_neo4j_error(error: Exception) -> str:
        return f"Neo4j error: {str(error)}"
    logger = logging.getLogger(__name__)
    logger.warning("Failed to import 'format_neo4j_error' from 'src.core.validation'. Using fallback implementation.")

logger = logging.getLogger(__name__)

class KnowledgeGraphValidator:
    """Validate AI-generated scripts against knowledge stored in Neo4j."""
    
    def __init__(self, neo4j_uri: str, neo4j_user: str, neo4j_password: str):
        """Initialize the knowledge graph validator."""
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.driver = None
        
    async def initialize(self):
        """Initialize the Neo4j connection."""
        try:
            self.driver = AsyncGraphDatabase.driver(
                self.neo4j_uri, 
                auth=(self.neo4j_user, self.neo4j_password)
            )
            # Test the connection
            async with self.driver.session() as session:
                await session.run("RETURN 1")
            logger.info("KnowledgeGraphValidator initialized successfully")
        except Exception as e:
            error_msg = format_neo4j_error(e)
            logger.error(f"Failed to initialize KnowledgeGraphValidator: {error_msg}")
            raise RuntimeError(error_msg)
    
    async def close(self):
        """Close the Neo4j connection."""
        if self.driver:
            await self.driver.close()
            logger.info("KnowledgeGraphValidator connection closed")
    
    async def validate_script(self, analysis_result: dict[str, Any]) -> dict[str, Any]:
        """
        Validate AI script analysis against knowledge graph.
        
        Args:
            analysis_result: Results from AIScriptAnalyzer containing:
                - imports: List of imported modules
                - functions: List of function definitions
                - classes: List of class definitions
                - external_calls: List of external API/library calls
                - file_operations: List of file operations
                - assertions: List of assertions made in the script
        
        Returns:
            Dict containing validation results with hallucination detection
        """
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")
        
        validation_result = {
            "hallucinations_detected": False,
            "confidence_score": 1.0,
            "issues": [],
            "validated_components": [],
            "recommendations": []
        }
        
        try:
            # Validate imports against known libraries
            await self._validate_imports(analysis_result.get("imports", []), validation_result)
            
            # Validate function signatures and patterns
            await self._validate_functions(analysis_result.get("functions", []), validation_result)
            
            # Validate external API calls
            await self._validate_external_calls(analysis_result.get("external_calls", []), validation_result)
            
            # Validate file operations patterns
            await self._validate_file_operations(analysis_result.get("file_operations", []), validation_result)
            
            # Calculate final confidence score
            validation_result["confidence_score"] = self._calculate_confidence_score(validation_result)
            validation_result["hallucinations_detected"] = validation_result["confidence_score"] < 0.7
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Script validation failed: {str(e)}")
            return {
                "hallucinations_detected": True,
                "confidence_score": 0.0,
                "issues": [f"Validation error: {str(e)}"],
                "validated_components": [],
                "recommendations": ["Unable to validate script due to technical issues"]
            }
    
    async def _validate_imports(self, imports: list[str], validation_result: dict[str, Any]):
        """Validate imported modules against known libraries in the graph."""
        if not imports:
            return
        
        async with self.driver.session() as session:
            for import_name in imports:
                # Check if library exists in knowledge graph
                query = """
                MATCH (lib:Library {name: $name})
                RETURN lib.name as name, lib.version as version, lib.documentation_url as docs
                UNION
                MATCH (f:File {name: $file_name})
                WHERE f.extension = '.py' AND f.type = 'code'
                RETURN f.name as name, f.repository as version, f.path as docs
                """
                
                result = await session.run(query, {
                    "name": import_name,
                    "file_name": f"{import_name}.py"
                })
                
                records = await result.list()
                if records:
                    validation_result["validated_components"].append({
                        "type": "import",
                        "name": import_name,
                        "status": "validated",
                        "source": "knowledge_graph"
                    })
                else:
                    # Check against common Python standard library
                    if self._is_standard_library(import_name):
                        validation_result["validated_components"].append({
                            "type": "import",
                            "name": import_name,
                            "status": "validated",
                            "source": "standard_library"
                        })
                    else:
                        validation_result["issues"].append({
                            "type": "unknown_import",
                            "severity": "medium",
                            "message": f"Unknown or unverified import: {import_name}",
                            "component": import_name
                        })
    
    async def _validate_functions(self, functions: list[dict[str, Any]], validation_result: dict[str, Any]):
        """Validate function definitions against known patterns."""
        if not functions:
            return
        
        async with self.driver.session() as session:
            for func_info in functions:
                func_name = func_info.get("name", "")
                func_args = func_info.get("args", [])
                
                # Check for similar function patterns in the graph
                query = """
                MATCH (f:File)-[:CONTAINS]->(func:Function {name: $func_name})
                RETURN func.name as name, func.args as args, func.return_type as return_type, f.repository as source
                LIMIT 5
                """
                
                result = await session.run(query, {"func_name": func_name})
                records = await result.list()
                
                if records:
                    validation_result["validated_components"].append({
                        "type": "function",
                        "name": func_name,
                        "status": "pattern_found",
                        "matches": len(records)
                    })
                else:
                    # Check for suspicious function names or patterns
                    if self._is_suspicious_function(func_name, func_args):
                        validation_result["issues"].append({
                            "type": "suspicious_function",
                            "severity": "high",
                            "message": f"Potentially hallucinated function: {func_name}",
                            "component": func_name
                        })
    
    async def _validate_external_calls(self, external_calls: list[str], validation_result: dict[str, Any]):
        """Validate external API calls against known APIs."""
        if not external_calls:
            return
        
        async with self.driver.session() as session:
            for call in external_calls:
                # Look for API endpoints or external service calls
                query = """
                MATCH (api:API {endpoint: $endpoint})
                RETURN api.name as name, api.method as method, api.documentation as docs
                UNION
                MATCH (f:File)
                WHERE f.content CONTAINS $call
                RETURN f.repository as name, f.type as method, f.path as docs
                LIMIT 3
                """
                
                result = await session.run(query, {
                    "endpoint": call,
                    "call": call
                })
                
                records = await result.list()
                if records:
                    validation_result["validated_components"].append({
                        "type": "external_call",
                        "name": call,
                        "status": "validated",
                        "sources": len(records)
                    })
                else:
                    validation_result["issues"].append({
                        "type": "unverified_external_call",
                        "severity": "medium",
                        "message": f"Unverified external call: {call}",
                        "component": call
                    })
    
    async def _validate_file_operations(self, file_ops: list[str], validation_result: dict[str, Any]):
        """Validate file operations against common patterns."""
        if not file_ops:
            return
        
        # Simple validation for now - check for suspicious file operations
        suspicious_patterns = [
            "/etc/passwd", "/etc/shadow", "rm -rf", "del /f /s /q",
            "system(", "eval(", "exec(", "__import__"
        ]
        
        for op in file_ops:
            is_suspicious = any(pattern in op.lower() for pattern in suspicious_patterns)
            if is_suspicious:
                validation_result["issues"].append({
                    "type": "suspicious_file_operation",
                    "severity": "high",
                    "message": f"Potentially dangerous file operation: {op}",
                    "component": op
                })
            else:
                validation_result["validated_components"].append({
                    "type": "file_operation",
                    "name": op,
                    "status": "safe_pattern"
                })
    
    def _is_standard_library(self, module_name: str) -> bool:
        """Check if a module is part of Python standard library."""
        standard_libs = {
            'os', 'sys', 'json', 'time', 'datetime', 'collections', 'itertools',
            'functools', 'pathlib', 'urllib', 'http', 'logging', 'argparse',
            'subprocess', 'threading', 'asyncio', 'typing', 're', 'math',
            'random', 'sqlite3', 'csv', 'xml', 'html', 'email', 'base64',
            'hashlib', 'hmac', 'secrets', 'ssl', 'socket', 'tempfile'
        }
        return module_name.split('.')[0] in standard_libs
    
    def _is_suspicious_function(self, func_name: str, func_args: list[str]) -> bool:
        """Check if function name/signature appears suspicious or hallucinated."""
        # Check for overly complex or nonsensical names
        suspicious_patterns = [
            "magic_", "super_", "ultimate_", "perfect_", "instant_",
            "auto_fix", "solve_all", "do_everything", "hack_"
        ]
        
        if any(pattern in func_name.lower() for pattern in suspicious_patterns):
            return True
        
        # Check for unrealistic number of parameters
        if len(func_args) > 15:
            return True
        
        # Check for suspicious parameter names
        suspicious_params = ["secret_key", "password", "admin_access", "root_access"]
        if any(param in str(func_args).lower() for param in suspicious_params):
            return True
        
        return False
    
    def _calculate_confidence_score(self, validation_result: dict[str, Any]) -> float:
        """Calculate confidence score based on validation results."""
        total_components = len(validation_result["validated_components"])
        total_issues = len(validation_result["issues"])
        
        if total_components == 0 and total_issues == 0:
            return 0.5  # Neutral when no data
        
        # Weight different types of issues
        issue_weights = {
            "unknown_import": 0.1,
            "unverified_external_call": 0.15,
            "suspicious_function": 0.3,
            "suspicious_file_operation": 0.4
        }
        
        # Calculate penalty from issues
        penalty = 0.0
        for issue in validation_result["issues"]:
            weight = issue_weights.get(issue["type"], 0.2)
            penalty += weight
        
        # Calculate bonus from validated components
        bonus = min(total_components * 0.1, 0.5)
        
        # Base confidence starts at 0.8, adjusted by penalty and bonus
        confidence = max(0.0, min(1.0, 0.8 - penalty + bonus))
        return round(confidence, 2)