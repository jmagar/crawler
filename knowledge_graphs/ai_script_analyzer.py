"""
AIScriptAnalyzer for parsing and analyzing AI-generated Python scripts.
"""
import ast
import logging
import re
from typing import Dict, Any, List, Set
from pathlib import Path

logger = logging.getLogger(__name__)

class AIScriptAnalyzer:
    """Analyze AI-generated Python scripts for structural patterns and potential issues."""
    
    def __init__(self):
        """Initialize the script analyzer."""
        self.analysis_cache = {}
    
    def analyze_script(self, script_path: str) -> Dict[str, Any]:
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
    
    def _analyze_imports(self, tree: ast.AST, result: Dict[str, Any]):
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
    
    def _analyze_functions(self, tree: ast.AST, result: Dict[str, Any]):
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
    
    def _analyze_classes(self, tree: ast.AST, result: Dict[str, Any]):
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
    
    def _analyze_external_calls(self, content: str, result: Dict[str, Any]):
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
    
    def _analyze_file_operations(self, tree: ast.AST, result: Dict[str, Any]):
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
    
    def _analyze_assertions(self, tree: ast.AST, content: str, result: Dict[str, Any]):
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
    
    def _calculate_complexity(self, tree: ast.AST, result: Dict[str, Any]):
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
    
    def _detect_suspicious_patterns(self, tree: ast.AST, content: str, result: Dict[str, Any]):
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