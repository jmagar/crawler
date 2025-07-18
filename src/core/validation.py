"""
Comprehensive validation utilities for the Crawl4AI MCP server.
"""
import os
import re
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from urllib.parse import urlparse
import psutil

logger = logging.getLogger(__name__)

def validate_neo4j_connection() -> bool:
    """Check if Neo4j environment variables are configured."""
    return all([
        os.getenv("NEO4J_URI"),
        os.getenv("NEO4J_USER"),
        os.getenv("NEO4J_PASSWORD")
    ])

def format_neo4j_error(error: Exception) -> str:
    """
    Format Neo4j errors consistently for logging and user feedback.
    
    Args:
        error: The exception to format
        
    Returns:
        Formatted error message string
    """
    error_type = type(error).__name__
    error_msg = str(error)
    error_str = error_msg.lower()
    
    # Handle common Neo4j error patterns
    if "authentication" in error_str or "unauthorized" in error_str:
        return "Neo4j authentication failed. Check NEO4J_USER and NEO4J_PASSWORD."
    elif "connection" in error_str or "refused" in error_str or "timeout" in error_str:
        return "Cannot connect to Neo4j. Check NEO4J_URI and ensure Neo4j is running."
    elif "database" in error_str:
        return "Neo4j database error. Check if the database exists and is accessible."
    elif "memory" in error_str:
        return f"Neo4j memory error: {error_msg}"
    else:
        return f"Neo4j {error_type}: {error_msg}"

def validate_script_path(script_path: str) -> Dict[str, Any]:
    """Validate script path and return error info if invalid."""
    if not script_path or not isinstance(script_path, str):
        return {"valid": False, "error": "Script path is required"}
    
    if not os.path.exists(script_path):
        return {"valid": False, "error": f"Script not found: {script_path}"}
    
    if not script_path.endswith('.py'):
        return {"valid": False, "error": "Only Python (.py) files are supported"}
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            f.read(1)
        return {"valid": True}
    except Exception as e:
        return {"valid": False, "error": f"Cannot read script file: {str(e)}"}

def validate_github_url(repo_url: str) -> Dict[str, Any]:
    """Validate GitHub repository URL."""
    if not repo_url or not isinstance(repo_url, str):
        return {"valid": False, "error": "Repository URL is required"}
    
    repo_url = repo_url.strip()
    
    if not ("github.com" in repo_url.lower() or repo_url.endswith(".git")):
        return {"valid": False, "error": "Please provide a valid GitHub repository URL"}
    
    if not (repo_url.startswith("https://") or repo_url.startswith("git@")):
        return {"valid": False, "error": "Repository URL must start with https:// or git@"}
    
    return {"valid": True, "repo_name": repo_url.split('/')[-1].replace('.git', '')}

def validate_repository_url(repo_url: str) -> None:
    """
    Enhanced repository URL validation for security and correctness.
    
    Args:
        repo_url: Repository URL to validate
        
    Raises:
        ValueError: If URL is invalid or unsafe
    """
    if not repo_url or not isinstance(repo_url, str):
        raise ValueError("Repository URL must be a non-empty string")
    
    try:
        parsed = urlparse(repo_url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}")
    
    # Ensure HTTPS protocol only
    if parsed.scheme != 'https':
        raise ValueError(f"Only HTTPS repositories are allowed. Got: {parsed.scheme}")
    
    # Whitelist trusted hosts
    trusted_hosts = {
        'github.com',
        'gitlab.com', 
        'bitbucket.org',
        'gitlab.org',
        'codeberg.org',
        'git.sr.ht'  # SourceHut
    }
    
    if parsed.hostname not in trusted_hosts:
        raise ValueError(f"Repository host not in trusted list: {parsed.hostname}")
    
    # Basic path validation
    if not parsed.path or parsed.path == '/':
        raise ValueError("Invalid repository path")
    
    # Prevent path traversal attempts
    if '..' in parsed.path or parsed.path.startswith('/..'):
        raise ValueError("Invalid repository path: potential path traversal detected")
    
    # Validate path format for GitHub-style repositories
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) < 2:
        raise ValueError("Repository URL must include owner and repository name")
    
    # Check for suspicious characters
    suspicious_chars = ['<', '>', '"', "'", '&', '|', ';', '$', '`']
    for char in suspicious_chars:
        if char in repo_url:
            raise ValueError(f"URL contains suspicious character: {char}")

def validate_repository_size(repo_path: str, max_size_gb: int = 50) -> None:
    """
    Validate repository doesn't exceed size limits.
    
    Args:
        repo_path: Path to the repository
        max_size_gb: Maximum allowed size in gigabytes
        
    Raises:
        ValueError: If repository is too large
    """
    try:
        repo_path_obj = Path(repo_path)
        if not repo_path_obj.exists():
            return  # Path doesn't exist yet, can't validate
        
        total_size = 0
        file_count = 0
        
        for file_path in repo_path_obj.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
                file_count += 1
                
                # Early exit if size limit exceeded
                if total_size > max_size_gb * 1024**3:
                    size_gb = total_size / 1024**3
                    raise ValueError(
                        f"Repository too large: {size_gb:.1f}GB (limit: {max_size_gb}GB). "
                        f"Contains {file_count} files."
                    )
        
        size_gb = total_size / 1024**3
        logger.info(f"Repository size: {size_gb:.2f}GB with {file_count} files")
        
    except OSError as e:
        logger.warning(f"Could not validate repository size: {e}")

def validate_file_path(file_path: str, allowed_extensions: set = None) -> bool:
    """
    Validate if a file should be processed based on security and content rules.
    
    Args:
        file_path: Path to the file relative to repository root
        allowed_extensions: Set of allowed file extensions (optional)
        
    Returns:
        True if file should be processed, False otherwise
    """
    if not file_path or not isinstance(file_path, str):
        return False
    
    file_path_obj = Path(file_path)
    
    # Security exclusions - sensitive files that should never be processed
    sensitive_patterns = {
        # Credentials and secrets
        '.env', '.env.local', '.env.production', '.env.staging',
        '.secret', '.secrets', '.password', '.passwords',
        'id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519',
        '.pem', '.key', '.crt', '.p12', '.pfx',
        'credentials.json', 'service-account.json',
        '.netrc', '.htpasswd',
        
        # Database files
        '.db', '.sqlite', '.sqlite3', '.mdb',
        
        # Backup and temporary files
        '.bak', '.backup', '.tmp', '.temp',
        '.swp', '.swo', '~',
        
        # System files
        '.DS_Store', 'Thumbs.db', 'desktop.ini',
        
        # Package manager files that might contain tokens
        '.npmrc', '.pypirc', '.gem/credentials',
    }
    
    # Check file name and extension against sensitive patterns
    file_name = file_path_obj.name.lower()
    file_suffix = file_path_obj.suffix.lower()
    
    for pattern in sensitive_patterns:
        if pattern in file_name or file_suffix == pattern:
            logger.debug(f"Excluding sensitive file: {file_path}")
            return False
    
    # Check for hidden files (but allow some common ones)
    if file_name.startswith('.'):
        allowed_hidden = {
            '.gitignore', '.gitattributes', '.github', '.gitlab-ci.yml',
            '.dockerignore', '.editorconfig', '.eslintrc', '.prettierrc',
            '.babelrc', '.browserslistrc', '.nvmrc'
        }
        if file_name not in allowed_hidden and not file_path.startswith('.github/'):
            logger.debug(f"Excluding hidden file: {file_path}")
            return False
    
    # Check directory exclusions
    excluded_dirs = {
        'node_modules', '__pycache__', '.git', '.svn', '.hg',
        'build', 'dist', 'target', '.gradle', '.maven',
        'vendor', 'venv', '.venv', 'env', '.env',
        '.idea', '.vscode', '.vs', '*.egg-info',
        'coverage', '.coverage', '.nyc_output',
        'logs', 'tmp', 'temp', 'cache', '.cache'
    }
    
    for part in file_path_obj.parts:
        if part.lower() in excluded_dirs:
            logger.debug(f"Excluding file in excluded directory: {file_path}")
            return False
    
    # Check allowed extensions if specified
    if allowed_extensions and file_suffix:
        if file_suffix not in allowed_extensions:
            return False
    
    return True

def get_system_memory_info() -> Dict[str, Any]:
    """
    Get system memory information for dynamic configuration.
    
    Returns:
        Dictionary with memory information in GB
    """
    try:
        memory = psutil.virtual_memory()
        return {
            'total_gb': memory.total / 1024**3,
            'available_gb': memory.available / 1024**3,
            'used_gb': memory.used / 1024**3,
            'percentage': memory.percent
        }
    except Exception as e:
        logger.warning(f"Could not get memory info: {e}")
        return {
            'total_gb': 8.0,  # Fallback to conservative estimate
            'available_gb': 4.0,
            'used_gb': 4.0,
            'percentage': 50.0
        }

def calculate_optimal_memory_allocation(total_memory_gb: float) -> Dict[str, int]:
    """
    Calculate optimal memory allocation for Neo4j based on available system memory.
    
    Args:
        total_memory_gb: Total system memory in GB
        
    Returns:
        Dictionary with recommended memory settings
    """
    # Conservative allocation - never use more than 80% of system memory
    max_usable = total_memory_gb * 0.8
    
    if total_memory_gb >= 32:
        # High-end system
        heap_gb = min(16, max_usable * 0.4)
        pagecache_gb = min(20, max_usable * 0.6)
    elif total_memory_gb >= 16:
        # Mid-range system  
        heap_gb = min(8, max_usable * 0.4)
        pagecache_gb = min(12, max_usable * 0.6)
    elif total_memory_gb >= 8:
        # Entry-level system
        heap_gb = min(4, max_usable * 0.4)
        pagecache_gb = min(6, max_usable * 0.6)
    else:
        # Very limited system
        heap_gb = min(2, max_usable * 0.4)
        pagecache_gb = min(3, max_usable * 0.6)
    
    return {
        'heap_initial_gb': int(heap_gb),
        'heap_max_gb': int(heap_gb),
        'pagecache_gb': int(pagecache_gb),
        'docker_memory_gb': int(heap_gb + pagecache_gb + 2)  # +2GB for OS overhead
    }

def validate_batch_size(batch_size: int, max_memory_gb: float = None) -> int:
    """
    Validate and potentially adjust batch size based on available memory.
    
    Args:
        batch_size: Requested batch size
        max_memory_gb: Maximum memory available for processing
        
    Returns:
        Validated/adjusted batch size
    """
    if batch_size <= 0:
        return 100  # Default batch size
    
    # Hard limits for safety
    max_batch_size = 1000
    min_batch_size = 10
    
    if batch_size > max_batch_size:
        logger.warning(f"Batch size {batch_size} exceeds maximum {max_batch_size}, reducing")
        return max_batch_size
    
    if batch_size < min_batch_size:
        logger.warning(f"Batch size {batch_size} below minimum {min_batch_size}, increasing")
        return min_batch_size
    
    # Adjust based on available memory if provided
    if max_memory_gb:
        # Rough estimate: each batch item might use ~1MB
        estimated_memory_gb = (batch_size * 1024 * 1024) / 1024**3
        if estimated_memory_gb > max_memory_gb * 0.5:  # Don't use more than 50% for batching
            adjusted_size = int((max_memory_gb * 0.5 * 1024**3) / (1024 * 1024))
            logger.info(f"Reducing batch size from {batch_size} to {adjusted_size} due to memory constraints")
            return max(min_batch_size, adjusted_size)
    
    return batch_size

def sanitize_cypher_string(input_string: str) -> str:
    """
    Sanitize string input for safe use in Cypher queries.
    
    Args:
        input_string: String to sanitize
        
    Returns:
        Sanitized string safe for Cypher queries
    """
    if not isinstance(input_string, str):
        return str(input_string)
    
    # Remove null bytes and control characters
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', input_string)
    
    # Limit length to prevent memory issues
    max_length = 50000
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
        logger.warning(f"Truncated string to {max_length} characters")
    
    return sanitized

def validate_neo4j_query(query: str) -> bool:
    """
    Basic validation of Cypher queries for safety.
    
    Args:
        query: Cypher query to validate
        
    Returns:
        True if query appears safe, False otherwise
    """
    if not isinstance(query, str) or not query.strip():
        return False
    
    # Dangerous patterns to avoid
    dangerous_patterns = [
        r'(?i)\bDROP\b',
        r'(?i)\bDELETE\s+(?!.*WHERE)',  # DELETE without WHERE
        r'(?i)\bREMOVE\b',
        r'(?i)\bCREATE\s+(?:CONSTRAINT|INDEX)',
        r'(?i)\bALTER\b',
        r'(?i)\bCALL\s+dbms\.',
        r'(?i)\bCALL\s+db\.',
        r'(?i)\bLOAD\s+CSV',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, query):
            logger.warning(f"Potentially dangerous query pattern detected: {pattern}")
            return False
    
    return True

def validate_directory_path(directory_path: str) -> Dict[str, Any]:
    """
    Validate a directory path for crawling.
    
    Args:
        directory_path: Path to validate
        
    Returns:
        Dictionary with validation result and error message if any
    """
    try:
        if not directory_path or not isinstance(directory_path, str):
            return {"valid": False, "error": "Directory path must be a non-empty string"}
        
        # Normalize path
        normalized_path = os.path.abspath(os.path.expanduser(directory_path.strip()))
        
        # Security check - prevent access to sensitive system directories
        restricted_patterns = [
            '/proc', '/sys', '/dev', '/boot', '/etc/shadow', '/etc/passwd',
            '/root', '/var/log', '/var/run', '/var/lib', '/tmp/systemd',
            'C:\\Windows\\System32', 'C:\\Program Files', 'C:\\Users\\All Users'
        ]
        
        for restricted in restricted_patterns:
            if normalized_path.startswith(restricted) or restricted in normalized_path:
                return {"valid": False, "error": f"Access to {restricted} is restricted for security reasons"}
        
        # Check if path exists
        if not os.path.exists(normalized_path):
            return {"valid": False, "error": f"Directory does not exist: {normalized_path}"}
        
        # Check if it's actually a directory
        if not os.path.isdir(normalized_path):
            return {"valid": False, "error": f"Path is not a directory: {normalized_path}"}
        
        # Check read permissions
        if not os.access(normalized_path, os.R_OK):
            return {"valid": False, "error": f"No read permission for directory: {normalized_path}"}
        
        return {"valid": True, "normalized_path": normalized_path}
        
    except Exception as e:
        return {"valid": False, "error": f"Error validating directory path: {str(e)}"}

def validate_crawl_dir_params(
    directory_path: str,
    max_files: int = 500,
    max_file_size: int = 1048576,
    exclude_patterns: Optional[List[str]] = None,
    include_patterns: Optional[List[str]] = None,
    chunk_size: int = 5000
) -> Dict[str, Any]:
    """
    Validate all parameters for the crawl_dir tool.
    
    Args:
        directory_path: Path to the directory to crawl
        max_files: Maximum number of files to process
        max_file_size: Maximum file size in bytes
        exclude_patterns: List of patterns to exclude
        include_patterns: List of patterns to include
        chunk_size: Size of chunks for processing
        
    Returns:
        Dictionary with validation result and any errors
    """
    errors = []
    
    # Validate directory path
    dir_validation = validate_directory_path(directory_path)
    if not dir_validation["valid"]:
        errors.append(dir_validation["error"])
    
    # Validate max_files
    if not isinstance(max_files, int) or max_files <= 0 or max_files > 10000:
        errors.append("max_files must be a positive integer between 1 and 10000")
    
    # Validate max_file_size
    if not isinstance(max_file_size, int) or max_file_size <= 0 or max_file_size > 100 * 1024 * 1024:  # 100MB limit
        errors.append("max_file_size must be a positive integer between 1 byte and 100MB")
    
    # Validate chunk_size
    if not isinstance(chunk_size, int) or chunk_size < 100 or chunk_size > 50000:
        errors.append("chunk_size must be an integer between 100 and 50000")
    
    # Validate patterns
    if exclude_patterns is not None:
        if not isinstance(exclude_patterns, list):
            errors.append("exclude_patterns must be a list of strings")
        elif any(not isinstance(pattern, str) for pattern in exclude_patterns):
            errors.append("All exclude_patterns must be strings")
    
    if include_patterns is not None:
        if not isinstance(include_patterns, list):
            errors.append("include_patterns must be a list of strings")
        elif any(not isinstance(pattern, str) for pattern in include_patterns):
            errors.append("All include_patterns must be strings")
    
    if errors:
        return {"valid": False, "errors": errors}
    
    return {
        "valid": True,
        "normalized_directory_path": dir_validation.get("normalized_path", directory_path)
    }
