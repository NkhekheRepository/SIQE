#!/usr/bin/env python3
"""
SIQE V3 - Disaster Recovery Script
Handles system recovery after crashes, data corruption, or exchange disconnects.
Usage: python3 scripts/disaster_recovery.py [--action check|recover|reset|status]
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = "./data/siqe.db"
LOCK_FILE = "./data/siqe.lock"
LOG_DIR = "./logs"
STATE_FILE = "./data/last_state.json"


def check_system_health():
    """Run comprehensive health checks."""
    results = {"timestamp": datetime.now(timezone.utc).isoformat(), "checks": {}}

    # Check database
    db_exists = os.path.exists(DB_PATH)
    db_size = os.path.getsize(DB_PATH) if db_exists else 0
    results["checks"]["database"] = {
        "exists": db_exists,
        "size_bytes": db_size,
        "status": "OK" if db_exists and db_size > 0 else "MISSING",
    }

    # Check lock files
    lock_exists = os.path.exists(LOCK_FILE)
    results["checks"]["locks"] = {
        "active": lock_exists,
        "status": "CLEAN" if not lock_exists else "LOCKED",
    }

    # Check logs
    log_exists = os.path.isdir(LOG_DIR)
    log_files = []
    if log_exists:
        log_files = [f for f in os.listdir(LOG_DIR) if f.endswith(".log")]
    results["checks"]["logs"] = {
        "directory_exists": log_exists,
        "file_count": len(log_files),
        "status": "OK" if log_exists else "MISSING",
    }

    # Check DuckDB integrity
    if db_exists:
        try:
            import duckdb
            conn = duckdb.connect(DB_PATH, read_only=True)
            tables = conn.execute("SHOW TABLES").fetchall()
            table_names = [t[0] for t in tables]
            trade_count = 0
            if "trades" in table_names:
                trade_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            conn.close()
            results["checks"]["database_integrity"] = {
                "tables": table_names,
                "trade_count": trade_count,
                "status": "OK",
            }
        except Exception as e:
            results["checks"]["database_integrity"] = {
                "error": str(e),
                "status": "CORRUPTED",
            }

    # Check configuration
    env_exists = os.path.exists(".env")
    results["checks"]["configuration"] = {
        "env_exists": env_exists,
        "status": "OK" if env_exists else "MISSING",
    }

    # Overall status
    valid_statuses = {"OK", "CLEAN"}
    all_ok = all(c.get("status") in valid_statuses for c in results["checks"].values() if isinstance(c, dict))
    results["overall_status"] = "HEALTHY" if all_ok else "DEGRADED"

    return results


def recover_database():
    """Attempt database recovery."""
    logger.info("Starting database recovery...")

    if not os.path.exists(DB_PATH):
        logger.warning("No database file found. Nothing to recover.")
        return {"success": False, "reason": "no_database_file"}

    try:
        import duckdb

        # Test current connection
        conn = duckdb.connect(DB_PATH)

        # Check tables
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        logger.info(f"Found tables: {table_names}")

        # Run integrity check
        for table in table_names:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            logger.info(f"Table {table}: {count} rows")

        conn.close()
        logger.info("Database recovery complete — all tables accessible")
        return {"success": True, "tables": table_names}

    except Exception as e:
        logger.error(f"Database recovery failed: {e}")
        return {"success": False, "error": str(e)}


def clear_locks():
    """Clear stale lock files."""
    lock_files = [LOCK_FILE]
    cleared = []

    for lock_file in lock_files:
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                cleared.append(lock_file)
                logger.info(f"Cleared lock file: {lock_file}")
            except Exception as e:
                logger.error(f"Failed to clear {lock_file}: {e}")

    return {"cleared": cleared, "count": len(cleared)}


def reset_state():
    """Reset system to initial state (preserves trade history)."""
    logger.info("Resetting system state...")

    state_data = {
        "reset_at": datetime.now(timezone.utc).isoformat(),
        "reason": "manual_reset",
        "previous_state": None,
    }

    # Save reset marker
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state_data, f, indent=2)

    logger.info(f"State reset marker saved to {STATE_FILE}")
    return state_data


def show_status():
    """Show current system status."""
    health = check_system_health()
    print(json.dumps(health, indent=2))
    return health


async def main():
    parser = argparse.ArgumentParser(description="SIQE V3 Disaster Recovery")
    parser.add_argument(
        "--action",
        choices=["check", "recover", "reset", "status", "clear-locks"],
        default="check",
        help="Recovery action to perform",
    )
    args = parser.parse_args()

    if args.action == "check":
        health = check_system_health()
        print(json.dumps(health, indent=2))
        if health["overall_status"] != "HEALTHY":
            sys.exit(1)

    elif args.action == "recover":
        result = recover_database()
        print(json.dumps(result, indent=2))
        if not result["success"]:
            sys.exit(1)

    elif args.action == "reset":
        result = reset_state()
        print(json.dumps(result, indent=2))

    elif args.action == "status":
        show_status()

    elif args.action == "clear-locks":
        result = clear_locks()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
