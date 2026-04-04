#!/usr/bin/env python3
"""
Basic validation script for SIQE V3 setup
"""
import asyncio
import sys
import os

# Add the siqe directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

async def validate_imports():
    """Validate that all modules can be imported."""
    print("Validating module imports...")
    
    modules_to_test = [
        "config.settings",
        "infra.logger",
        "core.data_engine",
        "strategy_engine.strategy_base",
        "ev_engine.ev_calculator",
        "decision_engine.decision_maker",
        "risk_engine.risk_manager",
        "meta_harness.meta_governor",
        "execution_adapter.vnpy_bridge",
        "feedback.feedback_loop",
        "memory.state_manager",
        "learning.learning_engine",
        "regime.regime_engine",
        "api.main"
    ]
    
    failed_imports = []
    
    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"  ✓ {module_name}")
        except Exception as e:
            print(f"  ✗ {module_name}: {e}")
            failed_imports.append((module_name, str(e)))
    
    if failed_imports:
        print(f"\nFailed to import {len(failed_imports)} modules:")
        for module, error in failed_imports:
            print(f"  - {module}: {error}")
        return False
    else:
        print(f"\nAll {len(modules_to_test)} modules imported successfully!")
        return True

async def validate_settings():
    """Validate settings loading."""
    print("\nValidating settings...")
    
    try:
        from config.settings import get_settings
        settings = get_settings()
        is_valid, errors = settings.validate()
        
        if is_valid:
            print("  ✓ Settings validation passed")
            print(f"    Environment: {settings.environment}")
            print(f"    Initial equity: ${settings.initial_equity}")
            print(f"    Max drawdown: {settings.max_drawdown:.0%}")
            return True
        else:
            print("  ✗ Settings validation failed:")
            for error in errors:
                print(f"    - {error}")
            return False
    except Exception as e:
        print(f"  ✗ Error loading settings: {e}")
        return False

async def validate_dockerfile():
    """Validate Dockerfile exists and has correct base image."""
    print("\nValidating Dockerfile...")
    
    dockerfile_path = "Dockerfile"
    if not os.path.exists(dockerfile_path):
        print(f"  ✗ {dockerfile_path} not found")
        return False
    
    try:
        with open(dockerfile_path, 'r') as f:
            content = f.read()
            
        if "FROM python:3.11-slim" in content:
            print("  ✓ Dockerfile uses correct base image")
        else:
            print("  ✗ Dockerfile does not use python:3.11-slim")
            return False
            
        if "WORKDIR /app" in content:
            print("  ✓ Dockerfile sets WORKDIR correctly")
        else:
            print("  ✗ Dockerfile missing WORKDIR /app")
            return False
            
        return True
    except Exception as e:
        print(f"  ✗ Error reading Dockerfile: {e}")
        return False

async def validate_docker_compose():
    """Validate docker-compose.yml exists."""
    print("\nValidating docker-compose.yml...")
    
    compose_path = "docker-compose.yml"
    if not os.path.exists(compose_path):
        print(f"  ✗ {compose_path} not found")
        return False
    
    try:
        with open(compose_path, 'r') as f:
            content = f.read()
            
        required_services = ["engine:"]
        missing_services = []

        for service in required_services:
            if service not in content:
                missing_services.append(service)

        has_api_port = "8000:8000" in content
        has_engine = "engine:" in content

        if missing_services:
            print(f"  ✗ Missing services in docker-compose.yml: {missing_services}")
            return False
        elif has_engine and has_api_port:
            print("  ✓ Engine service present with API port (single-container architecture)")
            return True
        else:
            print("  ✓ Engine service present")
            return True
    except Exception as e:
        print(f"  ✗ Error reading docker-compose.yml: {e}")
        return False

async def main():
    """Main validation function."""
    print("=" * 60)
    print("SIQE V3 Setup Validation")
    print("=" * 60)
    
    # Change to siqe directory if we're not already there
    if not os.path.exists("Dockerfile"):
        if os.path.exists("siqe/Dockerfile"):
            os.chdir("siqe")
        else:
            print("Error: Could not find siqe directory")
            return False
    
    # Run validations
    validations = [
        validate_imports(),
        validate_settings(),
        validate_dockerfile(),
        validate_docker_compose()
    ]
    
    # Wait for all validations to complete
    results = await asyncio.gather(*validations, return_exceptions=True)
    
    # Check results
    passed = sum(1 for r in results if r is True)
    total = len(results)
    
    print("\n" + "=" * 60)
    print(f"Validation Results: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 All validations passed! SIQE V3 setup is ready.")
        print("\nNext steps:")
        print("  1. Build: docker-compose build")
        print("  2. Run:   docker-compose up")
        print("  3. Check: http://localhost:8000/health")
        return True
    else:
        print("❌ Some validations failed. Please fix the issues above.")
        return False

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nValidation failed with error: {e}")
        sys.exit(1)
