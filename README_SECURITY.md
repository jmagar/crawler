# Security Improvements Guide

This document outlines the security improvements made to the Crawl4AI MCP server and how to use them.

## 🔒 Security Enhancements

### 1. Secure Configuration Generator

**Problem**: Hardcoded credentials and static configuration files pose security risks.

**Solution**: Automated secure configuration generator with hardware detection.

```bash
# Generate secure .env with auto-detected settings
python scripts/generate_secure_config.py

# Generate template for manual configuration
python scripts/generate_secure_config.py --template --output .env.template

# Force overwrite existing files
python scripts/generate_secure_config.py --force

# Generate development profile
python scripts/generate_secure_config.py --profile development
```

**Features**:
- ✅ Cryptographically secure password generation
- ✅ Hardware-optimized settings (auto-detects RAM, CPU cores)
- ✅ Secure file permissions (600)
- ✅ No hardcoded credentials

### 2. Enhanced File Security

**Problem**: Repository processing could expose sensitive files.

**Solution**: Comprehensive file validation and exclusion.

**Protected file types**:
- Credentials: `.env`, `.secret`, SSH keys, certificates
- Database files: `.db`, `.sqlite`, etc.
- Backup files: `.bak`, `.backup`, etc.
- Package manager tokens: `.npmrc`, `.pypirc`, etc.

**Example usage**:
```python
from src.core.validation import validate_file_path

# Check if a file should be processed
if validate_file_path("src/config.py"):
    # Safe to process
    pass
else:
    # Skip sensitive file
    pass
```

### 3. Repository URL Validation

**Problem**: Arbitrary repository URLs could be security risks.

**Solution**: Strict URL validation with trusted host whitelist.

**Trusted hosts**:
- `github.com`
- `gitlab.com`
- `bitbucket.org`
- `gitlab.org`
- `codeberg.org`
- `git.sr.ht`

**Features**:
- ✅ HTTPS-only enforcement
- ✅ Path traversal protection
- ✅ Suspicious character detection

### 4. Input Sanitization

**Problem**: User input could lead to injection attacks.

**Solution**: Comprehensive input sanitization for Cypher queries.

```python
from src.core.validation import sanitize_cypher_string

# Sanitize before database operations
safe_content = sanitize_cypher_string(user_input)
```

### 5. Memory Management

**Problem**: Static memory allocation could cause system instability.

**Solution**: Dynamic memory detection and scaling.

**Features**:
- ✅ Auto-detects available system memory
- ✅ Calculates optimal Neo4j heap/pagecache settings
- ✅ Adjusts batch sizes based on available resources
- ✅ Prevents memory exhaustion

### 6. Transaction Safety

**Problem**: Database operations could leave inconsistent state on failure.

**Solution**: Atomic transactions with automatic rollback.

**Features**:
- ✅ Explicit transaction management
- ✅ Automatic rollback on errors
- ✅ Consistent error reporting
- ✅ Safe batch operations

## 📋 .gitignore Improvements

Enhanced `.gitignore` to prevent accidental credential commits:

```gitignore
# Sensitive files (automatically ignored)
*.pem
*.key
*.crt
id_rsa*
credentials.json
.env*

# Database files
data/
*.db
*.sqlite*
neostore*

# Package manager tokens
.npmrc
.pypirc
.gem/credentials
```

## 🚀 Quick Start (Secure Setup)

1. **Generate secure configuration**:
   ```bash
   python scripts/generate_secure_config.py
   ```

2. **Verify security settings**:
   ```bash
   # Check file permissions
   ls -la .env
   # Should show: -rw------- (600)
   
   # Verify no credentials in git
   git status --porcelain | grep -E "\.(env|key|pem)"
   # Should be empty
   ```

3. **Start services with secure config**:
   ```bash
   # Load the generated configuration
   source .env
   
   # Start with secure settings
   docker-compose up -d
   ```

## 🔍 Validation Functions

### Repository Size Limits
```python
validate_repository_size("/path/to/repo", max_size_gb=10)
# Raises ValueError if repository exceeds size limit
```

### Batch Size Optimization
```python
optimal_batch = validate_batch_size(
    requested_size=500, 
    max_memory_gb=available_memory
)
# Returns memory-safe batch size
```

### Memory Information
```python
memory_info = get_system_memory_info()
# Returns: {'total_gb': 32.0, 'available_gb': 24.5, 'percentage': 23.4}

optimal_settings = calculate_optimal_memory_allocation(32.0)
# Returns: {'heap_initial_gb': 8, 'heap_max_gb': 8, 'pagecache_gb': 16}
```

## ⚠️ Migration Guide

### From Old Configuration

1. **Backup existing configuration**:
   ```bash
   cp .env .env.backup
   ```

2. **Generate new secure configuration**:
   ```bash
   python scripts/generate_secure_config.py --force
   ```

3. **Update any custom settings**:
   ```bash
   # Edit .env to restore any custom values
   nano .env
   ```

4. **Restart services**:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

### From Hardcoded Passwords

Templates like `.env.i7-13700k.template` now use placeholders:
- `NEO4J_PASSWORD=GENERATE_SECURE_PASSWORD_HERE`

Use the generator instead of manual passwords:
```bash
python scripts/generate_secure_config.py --output .env
```

## 🛡️ Security Checklist

- [ ] Generated secure passwords with the configuration script
- [ ] Verified `.env` has 600 permissions
- [ ] Confirmed no credentials are in version control
- [ ] Tested repository URL validation
- [ ] Verified memory settings are appropriate for your system
- [ ] Enabled transaction rollback in Neo4j operations
- [ ] Checked that sensitive files are excluded from processing

## 🚨 Security Incidents

If you suspect a security issue:

1. **Immediate actions**:
   - Regenerate all passwords: `python scripts/generate_secure_config.py --force`
   - Check git history: `git log --grep="password\|secret\|key"`
   - Rotate any exposed credentials

2. **Prevention**:
   - Use the secure configuration generator
   - Never commit `.env` files
   - Regular security audits

## 📚 Additional Resources

- [Neo4j Security Guide](https://neo4j.com/docs/operations-manual/current/security/)
- [Docker Security Best Practices](https://docs.docker.com/engine/security/)
- [Python Security Guidelines](https://python.org/dev/security/)