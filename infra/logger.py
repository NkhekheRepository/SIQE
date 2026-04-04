"""
Infrastructure Logging Module
Provides structured JSON logging for SIQE V3
"""
import logging
import json
import sys
from datetime import datetime, timezone
from typing import Dict, Any
from loguru import logger as loguru_logger


class InterceptHandler(logging.Handler):
    """Bridge standard logging to loguru."""
    
    def emit(self, record):
        # Get corresponding Loguru level
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        
        # Find caller from original stack frame
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        
        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


class StructuredLogger:
    """Structured JSON logger for SIQE V3."""
    
    def __init__(self, name: str = "siqe", log_file: str = "./logs/siqe.log", 
                 log_level: str = "INFO"):
        self.name = name
        self.log_file = log_file
        self.log_level = log_level.upper()
        self.logger = None
        self._setup_logger()
    
    def _setup_logger(self):
        """Setup loguru logger with JSON formatting."""
        # Remove default logger
        loguru_logger.remove()
        
        # Add stdout sink with JSON format
        loguru_logger.add(
            sys.stdout,
            format=self._json_formatter,
            level=self.log_level,
            serialize=True  # JSON serialization
        )
        
        # Add file sink with JSON format
        loguru_logger.add(
            self.log_file,
            format=self._json_formatter,
            level=self.log_level,
            serialize=True,
            rotation="10 MB",  # Rotate when file reaches 10MB
            retention="7 days",  # Keep logs for 7 days
            compression="zip"  # Compress old logs
        )
        
        self.logger = loguru_logger
    
    def _json_formatter(self, record):
        """Format log record as JSON."""
        # Extract relevant information from record
        log_entry = {
            "timestamp": datetime.fromtimestamp(record["time"].timestamp(), tz=timezone.utc).isoformat(),
            "level": record["level"].name,
            "logger": record["name"],
            "message": record["message"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"]
        }
        
        # Add extra fields if present
        if "extra" in record and record["extra"]:
            log_entry.update(record["extra"])
        
        # Add exception info if present
        if record["exception"]:
            log_entry["exception"] = {
                "type": record["exception"].type.__name__ if record["exception"].type else None,
                "value": str(record["exception"].value) if record["exception"].value else None,
                "traceback": record["exception"].traceback
            }
        
        return json.dumps(log_entry)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logger.error(message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self.logger.critical(message, **kwargs)
    
    def exception(self, message: str, **kwargs):
        """Log exception with traceback."""
        self.logger.exception(message, **kwargs)


# Global logger instance
def setup_logging(log_file: str = "./logs/siqe.log", log_level: str = "INFO"):
    """Setup global structured logging."""
    global structured_logger
    structured_logger = StructuredLogger(
        name="siqe",
        log_file=log_file,
        log_level=log_level
    )
    return structured_logger


def get_logger(name: str = None):
    """Get logger instance."""
    if 'structured_logger' not in globals():
        setup_logging()
    if name:
        return structured_logger.logger.bind(name=name)
    return structured_logger.logger
