import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class KeyManager:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._keys = {}
        self._usage = {}
        self._previous_keys = {}
        self._initialized = False
        self._init_lock = threading.Lock()

    def _ensure_initialized(self):
        if not self._initialized:
            with self._init_lock:
                if not self._initialized:
                    self._load_from_env()
                    self._initialized = True

    def _load_from_env(self):
        exchanges = ["binance", "bybit", "okx"]
        for exchange in exchanges:
            upper = exchange.upper()
            key = os.environ.get(f"{upper}_API_KEY")
            secret = os.environ.get(f"{upper}_API_SECRET")
            testnet_key = os.environ.get(f"{upper}_TESTNET_API_KEY")
            testnet_secret = os.environ.get(f"{upper}_TESTNET_API_SECRET")

            self._keys[exchange] = {
                "live": {"key": key, "secret": secret},
                "testnet": {"key": testnet_key, "secret": testnet_secret},
            }
            self._usage[exchange] = {
                "live": {"count": 0, "last_used": None},
                "testnet": {"count": 0, "last_used": None},
            }
            self._previous_keys[exchange] = {
                "live": {"key": None, "secret": None},
                "testnet": {"key": None, "secret": None},
            }

        legacy_mappings = [
            ("FUTURES_API_KEY", "FUTURES_API_SECRET", "binance"),
            ("EXCHANGE_API_KEY", "EXCHANGE_API_SECRET", "binance"),
        ]
        for key_env, secret_env, exchange in legacy_mappings:
            key = os.environ.get(key_env)
            secret = os.environ.get(secret_env)
            if key or secret:
                # Always ensure the exchange exists in our keys dict
                if exchange not in self._keys:
                    self._keys[exchange] = {
                        "live": {"key": None, "secret": None},
                        "testnet": {"key": None, "secret": None},
                    }
                    self._usage[exchange] = {
                        "live": {"count": 0, "last_used": None},
                        "testnet": {"count": 0, "last_used": None},
                    }
                    self._previous_keys[exchange] = {
                        "live": {"key": None, "secret": None},
                        "testnet": {"key": None, "secret": None},
                    }
                
                # Update the live credentials for this exchange
                self._keys[exchange]["live"] = {
                    "key": key,
                    "secret": secret,
                }
                # Reset usage when keys are updated (optional)
                self._usage[exchange]["live"] = {
                    "count": 0,
                    "last_used": None,
                }
            self._usage[exchange] = {
                "live": {"count": 0, "last_used": None},
                "testnet": {"count": 0, "last_used": None},
            }
            self._previous_keys[exchange] = {
                "live": {"key": None, "secret": None},
                "testnet": {"key": None, "secret": None},
            }

        legacy_mappings = [
            ("FUTURES_API_KEY", "FUTURES_API_SECRET", "binance"),
            ("EXCHANGE_API_KEY", "EXCHANGE_API_SECRET", "binance"),
        ]
        for key_env, secret_env, exchange in legacy_mappings:
            key = os.environ.get(key_env)
            secret = os.environ.get(secret_env)
            if key or secret:
                # Always ensure the exchange exists in our keys dict
                if exchange not in self._keys:
                    self._keys[exchange] = {
                        "live": {"key": None, "secret": None},
                        "testnet": {"key": None, "secret": None},
                    }
                    self._usage[exchange] = {
                        "live": {"count": 0, "last_used": None},
                        "testnet": {"count": 0, "last_used": None},
                    }
                    self._previous_keys[exchange] = {
                        "live": {"key": None, "secret": None},
                        "testnet": {"key": None, "secret": None},
                    }
                
                # Update the live credentials for this exchange
                self._keys[exchange]["live"] = {
                    "key": key,
                    "secret": secret,
                }
                # Reset usage when keys are updated (optional)
                self._usage[exchange]["live"] = {
                    "count": 0,
                    "last_used": None,
                }
            self._usage[exchange] = {
                "live": {"count": 0, "last_used": None},
                "testnet": {"count": 0, "last_used": None},
            }
            self._previous_keys[exchange] = {
                "live": {"key": None, "secret": None},
                "testnet": {"key": None, "secret": None},
            }

        legacy_mappings = [
            ("FUTURES_API_KEY", "FUTURES_API_SECRET", "binance"),
            ("EXCHANGE_API_KEY", "EXCHANGE_API_SECRET", "binance"),
        ]
        for key_env, secret_env, exchange in legacy_mappings:
            key = os.environ.get(key_env)
            secret = os.environ.get(secret_env)
            print(f"KEY_MANAGER_DEBUG: Legacy {key_env} -> {exchange} - key: {bool(key)}, secret: {bool(secret)}")
            if key or secret:
                # Always ensure the exchange exists in our keys dict
                if exchange not in self._keys:
                    self._keys[exchange] = {
                        "live": {"key": None, "secret": None},
                        "testnet": {"key": None, "secret": None},
                    }
                    self._usage[exchange] = {
                        "live": {"count": 0, "last_used": None},
                        "testnet": {"count": 0, "last_used": None},
                    }
                    self._previous_keys[exchange] = {
                        "live": {"key": None, "secret": None},
                        "testnet": {"key": None, "secret": None},
                    }
                
                # Update the live credentials for this exchange
                self._keys[exchange]["live"] = {
                    "key": key,
                    "secret": secret,
                }
                # Reset usage when keys are updated (optional)
                self._usage[exchange]["live"] = {
                    "count": 0,
                    "last_used": None,
                }

    @classmethod
    def get_key_manager(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def mask_key(self, key: str) -> str:
        if not key:
            return ""
        if len(key) <= 8:
            return key[:2] + "***" + key[-2:]
        return key[:4] + "***" + key[-4:]

    def validate_keys(self, exchange: str) -> dict:
        self._ensure_initialized()
        exchange = exchange.lower()
        result = {"live": {}, "testnet": {}}

        for mode in ["live", "testnet"]:
            key = self._keys.get(exchange, {}).get(mode, {}).get("key")
            secret = self._keys.get(exchange, {}).get(mode, {}).get("secret")
            result[mode] = {
                "key_valid": self._validate_key_format(key),
                "secret_valid": self._validate_key_format(secret),
                "key_length": len(key) if key else 0,
                "secret_length": len(secret) if secret else 0,
                "has_key": key is not None and len(key) > 0,
                "has_secret": secret is not None and len(secret) > 0,
            }

        return result

    def _validate_key_format(self, key: Optional[str]) -> bool:
        if not key or len(key) == 0:
            return False
        if len(key) < 8:
            return False
        if not all(c.isprintable() for c in key):
            return False
        return True

    def get_api_key(self, exchange: str, testnet: bool = False) -> Optional[str]:
        self._ensure_initialized()
        exchange = exchange.lower()
        mode = "testnet" if testnet else "live"

        key_data = self._keys.get(exchange, {}).get(mode, {})
        key = key_data.get("key")

        if key:
            usage = self._usage.setdefault(exchange, {}).setdefault(mode, {"count": 0, "last_used": None})
            usage["count"] += 1
            usage["last_used"] = datetime.now(timezone.utc).isoformat()

        return key

    def get_api_secret(self, exchange: str, testnet: bool = False) -> Optional[str]:
        self._ensure_initialized()
        exchange = exchange.lower()
        mode = "testnet" if testnet else "live"

        key_data = self._keys.get(exchange, {}).get(mode, {})
        return key_data.get("secret")

    def rotate_keys(self, exchange: str, new_key: str, new_secret: str, testnet: bool = False) -> bool:
        self._ensure_initialized()
        exchange = exchange.lower()
        mode = "testnet" if testnet else "live"

        if exchange not in self._keys:
            self._keys[exchange] = {
                "live": {"key": None, "secret": None},
                "testnet": {"key": None, "secret": None},
            }
            self._usage[exchange] = {
                "live": {"count": 0, "last_used": None},
                "testnet": {"count": 0, "last_used": None},
            }
            self._previous_keys[exchange] = {
                "live": {"key": None, "secret": None},
                "testnet": {"key": None, "secret": None},
            }

        current = self._keys[exchange][mode]
        self._previous_keys[exchange][mode] = {
            "key": current["key"],
            "secret": current["secret"],
        }

        self._keys[exchange][mode] = {
            "key": new_key,
            "secret": new_secret,
        }

        return True

    def get_key_status(self, exchange: str, testnet: bool = False) -> dict:
        self._ensure_initialized()
        exchange = exchange.lower()
        mode = "testnet" if testnet else "live"

        key_data = self._keys.get(exchange, {}).get(mode, {})
        usage_data = self._usage.get(exchange, {}).get(mode, {"count": 0, "last_used": None})
        key = key_data.get("key")
        secret = key_data.get("secret")

        return {
            "has_key": key is not None and len(key) > 0,
            "has_secret": secret is not None and len(secret) > 0,
            "last_used": usage_data.get("last_used"),
            "usage_count": usage_data.get("count", 0),
            "is_valid": self._validate_key_format(key) and self._validate_key_format(secret),
            "is_testnet": testnet,
            "masked_key": self.mask_key(key) if key else "",
        }