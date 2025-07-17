"""
AIScriptAnalyzer for parsing and analyzing AI-generated Python scripts.
"""
import ast
import asyncio
import logging
import re
import time
from typing import Any, Optional, Dict, List
import aiofiles
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

class AIScriptAnalyzer:
    """Analyze AI-generated Python scripts for structural patterns and potential issues with async optimizations."""
    
    def __init__(self, max_file_size: int = 1024 * 1024, max_workers: int = 4):
        """Initialize the script analyzer.
        
        Args:
            max_file_size: Maximum file size to analyze (bytes)
            max_workers: Maximum number of worker threads for CPU-bound tasks
        """
        self.analysis_cache = {}
        self.max_file_size = max_file_size
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.performance_metrics = {}
    
    def analyze_script(self, script_path: str) -> dict[str, Any]:
        """
        Analyze a Python script and extract structural information.
        
        Args:
            script_path: Path to the Python script file
            
        Returns:
            Dict containing analysis results with:
                - imports: List of imported modules
                - functions: List of function definitions with metadata
                - classes: List of class definitions with metadata
                - external_calls: List of detected external API/library calls
                - file_operations: List of file operation calls
                - assertions: List of assertions and assumptions made
                - complexity_score: Estimated complexity score
                - suspicious_patterns: List of potentially problematic patterns
        """
        try:
            # Read the script content
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the AST
            tree = ast.parse(content, filename=script_path)
            
            # Initialize analysis result
            analysis_result = {
                "script_path": script_path,
                "imports": [],
                "functions": [],
                "classes": [],
                "external_calls": [],
                "file_operations": [],
                "assertions": [],
                "complexity_score": 0,
                "suspicious_patterns": [],
                "line_count": len(content.splitlines()),
                "character_count": len(content)
            }
            
            # Analyze different aspects of the script
            self._analyze_imports(tree, analysis_result)
            self._analyze_functions(tree, analysis_result)
            self._analyze_classes(tree, analysis_result)
            self._analyze_external_calls(content, analysis_result)
            self._analyze_file_operations(tree, analysis_result)
            self._analyze_assertions(tree, content, analysis_result)
            self._calculate_complexity(tree, analysis_result)
            self._detect_suspicious_patterns(tree, content, analysis_result)
            
            return analysis_result
            
        except SyntaxError as e:
            logger.error(f"Syntax error in script {script_path}: {str(e)}")
            return {
                "script_path": script_path,
                "error": "syntax_error",
                "error_message": str(e),
                "imports": [],
                "functions": [],
                "classes": [],
                "external_calls": [],
                "file_operations": [],
                "assertions": [],
                "complexity_score": 0,
                "suspicious_patterns": ["syntax_error"]
            }
        except Exception as e:
            logger.error(f"Failed to analyze script {script_path}: {str(e)}")
            return {
                "script_path": script_path,
                "error": "analysis_error",
                "error_message": str(e),
                "imports": [],
                "functions": [],
                "classes": [],
                "external_calls": [],
                "file_operations": [],
                "assertions": [],
                "complexity_score": 0,
                "suspicious_patterns": ["analysis_failed"]
            }
    
    async def analyze_script_async(self, script_path: str) -> dict[str, Any]:
        """
        Analyze a Python script and extract structural information asynchronously.
        
        Args:
            script_path: Path to the Python script file
            
        Returns:
            Dict containing analysis results with enhanced performance metrics
        """
        start_time = time.time()
        
        # Validate file path and size
        if not await self._validate_file(script_path):
            return self._create_error_result(script_path, "invalid_file", "File validation failed")
        
        try:
            # Read the script content asynchronously
            content = await self._read_file_safe(script_path)
            if not content:
                return self._create_error_result(script_path, "read_error", "Could not read file content")
            
            # Parse the AST in a thread pool (CPU-bound operation)
            tree = await self._parse_ast_async(content, script_path)
            
            # Initialize analysis result
            analysis_result = {
                "script_path": script_path,
                "imports": [],
                "functions": [],
                "classes": [],
                "external_calls": [],
                "file_operations": [],
                "assertions": [],
                "complexity_score": 0,
                "suspicious_patterns": [],
                "line_count": len(content.splitlines()),
                "character_count": len(content),
                "analysis_time": 0
            }
            
            # Analyze different aspects of the script asynchronously
            await asyncio.gather(
                self._analyze_imports_async(tree, analysis_result),
                self._analyze_functions_async(tree, analysis_result),
                self._analyze_classes_async(tree, analysis_result),
                self._analyze_external_calls_async(content, analysis_result),
                self._analyze_file_operations_async(tree, analysis_result),
                self._analyze_assertions_async(tree, content, analysis_result),
                self._calculate_complexity_async(tree, analysis_result),
                self._detect_suspicious_patterns_async(tree, content, analysis_result)
            )
            
            analysis_result["analysis_time"] = time.time() - start_time
            self.performance_metrics[script_path] = analysis_result["analysis_time"]
            
            return analysis_result
            
        except SyntaxError as e:
            logger.error(f"Syntax error in script {script_path}: {str(e)}")
            return self._create_error_result(script_path, "syntax_error", str(e), ["syntax_error"])
        except Exception as e:
            logger.error(f"Failed to analyze script {script_path}: {str(e)}")
            return self._create_error_result(script_path, "analysis_error", str(e), ["analysis_failed"])
    
    async def analyze_multiple_scripts(self, script_paths: list[str], max_concurrent: int = 10) -> list[dict[str, Any]]:
        """
        Analyze multiple scripts concurrently.
        
        Args:
            script_paths: List of script file paths
            max_concurrent: Maximum number of concurrent analyses
            
        Returns:
            List of analysis results
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def analyze_with_semaphore(path: str) -> dict[str, Any]:
            async with semaphore:
                return await self.analyze_script_async(path)
        
        tasks = [analyze_with_semaphore(path) for path in script_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Analysis failed for {script_paths[i]}: {str(result)}")
                final_results.append(
                    self._create_error_result(script_paths[i], "analysis_exception", str(result))
                )
            else:
                final_results.append(result)
        
        return final_results
    
    async def _validate_file(self, file_path: str) -> bool:
        """Validate file path and size asynchronously."""
        try:
            if not os.path.exists(file_path):
                return False
            
            stat = await asyncio.get_event_loop().run_in_executor(
                None, os.stat, file_path
            )
            
            # Check file size
            if stat.st_size > self.max_file_size:
                logger.warning(f"File {file_path} too large: {stat.st_size} bytes")
                return False
            
            # Check if it's a regular file
            if not os.path.isfile(file_path):
                return False
            
            return True
        except Exception as e:
            logger.error(f"File validation failed for {file_path}: {str(e)}")
            return False
    
    async def _read_file_safe(self, file_path: str) -> Optional[str]:
        """Read file content safely with size limits."""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read(self.max_file_size)
                return content
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {str(e)}")
            return None
    
    async def _parse_ast_async(self, content: str, filename: str) -> ast.AST:
        """Parse AST in a thread pool to avoid blocking."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor, 
            lambda: ast.parse(content, filename=filename)
        )
    
    def _create_error_result(self, script_path: str, error_type: str, error_message: str, 
                           suspicious_patterns: list[str] | None = None) -> dict[str, Any]:
        """Create a standardized error result."""
        return {
            "script_path": script_path,
            "error": error_type,
            "error_message": error_message,
            "imports": [],
            "functions": [],
            "classes": [],
            "external_calls": [],
            "file_operations": [],
            "assertions": [],
            "complexity_score": 0,
            "suspicious_patterns": suspicious_patterns or [],
            "analysis_time": 0
        }
    
    # Async versions of analysis methods
    async def _analyze_imports_async(self, tree: ast.AST, result: dict[str, Any]):
        """Analyze imports asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._analyze_imports, tree, result)
    
    async def _analyze_functions_async(self, tree: ast.AST, result: dict[str, Any]):
        """Analyze functions asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._analyze_functions, tree, result)
    
    async def _analyze_classes_async(self, tree: ast.AST, result: dict[str, Any]):
        """Analyze classes asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._analyze_classes, tree, result)
    
    async def _analyze_external_calls_async(self, content: str, result: dict[str, Any]):
        """Analyze external calls asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._analyze_external_calls, content, result)
    
    async def _analyze_file_operations_async(self, tree: ast.AST, result: dict[str, Any]):
        """Analyze file operations asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._analyze_file_operations, tree, result)
    
    async def _analyze_assertions_async(self, tree: ast.AST, content: str, result: dict[str, Any]):
        """Analyze assertions asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._analyze_assertions, tree, content, result)
    
    async def _calculate_complexity_async(self, tree: ast.AST, result: dict[str, Any]):
        """Calculate complexity asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._calculate_complexity, tree, result)
    
    async def _detect_suspicious_patterns_async(self, tree: ast.AST, content: str, result: dict[str, Any]):
        """Detect suspicious patterns asynchronously."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self.executor, self._detect_suspicious_patterns, tree, content, result)
    
    def get_performance_metrics(self) -> Dict[str, float]:
        """Get performance metrics for analyzed scripts."""
        return dict(self.performance_metrics)
    
    async def cleanup(self):
        """Clean up resources."""
        if self.executor:
            self.executor.shutdown(wait=True)
    
    def _analyze_imports(self, tree: ast.AST, result: dict[str, Any]):
        """Extract import statements from the AST."""
        imports = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
                    # Also add specific imports
                    for alias in node.names:
                        imports.add(f"{node.module}.{alias.name}")
        
        result["imports"] = sorted(list(imports))
    
    def _analyze_functions(self, tree: ast.AST, result: dict[str, Any]):
        """Analyze function definitions in the script."""
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_info = {
                    "name": node.name,
                    "args": [arg.arg for arg in node.args.args],
                    "line_number": node.lineno,
                    "is_async": False,
                    "has_docstring": bool(ast.get_docstring(node)),
                    "decorators": [self._get_decorator_name(dec) for dec in node.decorator_list]
                }
                functions.append(func_info)
            elif isinstance(node, ast.AsyncFunctionDef):
                func_info = {
                    "name": node.name,
                    "args": [arg.arg for arg in node.args.args],
                    "line_number": node.lineno,
                    "is_async": True,
                    "has_docstring": bool(ast.get_docstring(node)),
                    "decorators": [self._get_decorator_name(dec) for dec in node.decorator_list]
                }
                functions.append(func_info)
        
        result["functions"] = functions
    
    def _analyze_classes(self, tree: ast.AST, result: dict[str, Any]):
        """Analyze class definitions in the script."""
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_info = {
                    "name": node.name,
                    "bases": [self._get_name_from_node(base) for base in node.bases],
                    "line_number": node.lineno,
                    "has_docstring": bool(ast.get_docstring(node)),
                    "methods": [],
                    "decorators": [self._get_decorator_name(dec) for dec in node.decorator_list]
                }
                
                # Extract methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        class_info["methods"].append({
                            "name": item.name,
                            "line_number": item.lineno,
                            "is_async": isinstance(item, ast.AsyncFunctionDef)
                        })
                
                classes.append(class_info)
        
        result["classes"] = classes
    
    def _analyze_external_calls(self, content: str, result: dict[str, Any]):
        """Detect potential external API calls and library usage."""
        external_calls = []
        
        # Common patterns for external calls
        patterns = [
            r'requests\.(get|post|put|delete|patch)\s*\(',
            r'urllib\.request\.',
            r'http\.client\.',
            r'subprocess\.(run|call|Popen)',
            r'os\.system\s*\(',
            r'eval\s*\(',
            r'exec\s*\(',
            r'\.api\.',
            r'\.client\.',
            r'https?://[^\s\'"]+',
            r'@\w+\.route\s*\(',
            r'\.connect\s*\(',
            r'\.cursor\s*\(',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                external_calls.append(match.group())
        
        result["external_calls"] = list(set(external_calls))
    
    def _analyze_file_operations(self, tree: ast.AST, result: dict[str, Any]):
        """Detect file operations in the script."""
        file_operations = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._get_name_from_node(node.func)
                
                # Common file operation functions
                file_ops = {
                    'open', 'read', 'write', 'close', 'remove', 'unlink',
                    'mkdir', 'rmdir', 'listdir', 'walk', 'glob',
                    'Path', 'pathlib.Path'
                }
                
                if any(op in func_name for op in file_ops):
                    file_operations.append(func_name)
        
        result["file_operations"] = list(set(file_operations))
    
    def _analyze_assertions(self, tree: ast.AST, content: str, result: dict[str, Any]):
        """Extract assertions and assumptions made in the script."""
        assertions = []
        
        # AST-based assertion detection
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                assertions.append({
                    "type": "assert_statement",
                    "line_number": node.lineno,
                    "test": ast.unparse(node.test) if hasattr(ast, 'unparse') else "assertion"
                })
        
        # Comment-based assumptions
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            line_lower = line.strip().lower()
            if any(keyword in line_lower for keyword in ['# assumes', '# assumption', '# todo', '# fixme', '# hack']):
                assertions.append({
                    "type": "comment_assumption",
                    "line_number": i,
                    "content": line.strip()
                })
        
        result["assertions"] = assertions
    
    def _calculate_complexity(self, tree: ast.AST, result: dict[str, Any]):
        """Calculate a complexity score for the script."""
        complexity = 0
        
        for node in ast.walk(tree):
            # Control flow adds complexity
            if isinstance(node, (ast.If, ast.While, ast.For, ast.Try, ast.With)):
                complexity += 1
            # Function/class definitions add complexity
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                complexity += 2
            # Nested structures add more complexity
            elif isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
                complexity += 1
        
        result["complexity_score"] = complexity
    
    def _detect_suspicious_patterns(self, tree: ast.AST, content: str, result: dict[str, Any]):
        """Detect potentially suspicious or problematic patterns."""
        suspicious = []
        
        # Check for suspicious imports
        suspicious_imports = {
            'os.system', 'subprocess', 'eval', 'exec', '__import__',
            'pickle', 'marshal', 'shelve'
        }
        
        for imp in result["imports"]:
            if any(sus in imp for sus in suspicious_imports):
                suspicious.append(f"suspicious_import:{imp}")
        
        # Check for hardcoded secrets patterns
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']'
        ]
        
        for pattern in secret_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                suspicious.append(f"hardcoded_secret_pattern")
        
        # Check for overly complex functions
        for func in result["functions"]:
            if len(func["args"]) > 10:
                suspicious.append(f"complex_function:{func['name']}")
        
        # Check for suspicious function names
        suspicious_names = [
            'hack', 'crack', 'exploit', 'bypass', 'steal', 'leak',
            'magic_solve', 'auto_fix_everything', 'instant_solution'
        ]
        
        for func in result["functions"]:
            if any(sus in func["name"].lower() for sus in suspicious_names):
                suspicious.append(f"suspicious_function_name:{func['name']}")
        
        result["suspicious_patterns"] = suspicious
    
    def _get_decorator_name(self, decorator):
        """Extract decorator name from AST node."""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return f"{self._get_name_from_node(decorator.value)}.{decorator.attr}"
        elif isinstance(decorator, ast.Call):
            return self._get_name_from_node(decorator.func)
        else:
            return "unknown_decorator"
    
    def _get_name_from_node(self, node):
        """Extract name from various AST node types."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name_from_node(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return self._get_name_from_node(node.func)
        else:
            return "unknown"