"""
API Layer Module
Provides RESTful interface for system control and observability.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SIQE V3 API",
    description="Self-Improving Quant Engine API for control and observability",
    version="3.0.0",
)

engine_instance = None


def set_engine_instance(engine):
    global engine_instance
    engine_instance = engine


@app.get("/health")
async def health_check():
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        status = engine_instance.get_status()
        return JSONResponse(
            content={
                "status": "healthy" if status["running"] else "starting",
                "timestamp": engine_instance.clock.now,
                "engine_status": status,
            }
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/detailed")
async def health_detailed():
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        status = engine_instance.get_status()
        metrics = engine_instance.get_metrics()
        settings = engine_instance.settings

        execution_status = "mock" if settings.use_mock_execution else "live"
        connection_status = "connected" if engine_instance.execution_adapter.is_connected else "disconnected"

        return JSONResponse(
            content={
                "status": "healthy" if status["running"] else "degraded",
                "timestamp": engine_instance.clock.now,
                "engine": {
                    "state": status["system_state"],
                    "running": status["running"],
                    "uptime_ticks": status["uptime_ticks"],
                    "total_trades": status["total_trades"],
                    "events_processed": status["total_events_processed"],
                    "events_rejected": status["total_events_rejected"],
                },
                "execution": {
                    "mode": execution_status,
                    "connection": connection_status,
                    "initialized": engine_instance.execution_adapter.is_initialized,
                    "gateway": settings.vnpy_gateway,
                    "exchange_server": settings.exchange_server,
                },
                "queue": {
                    "depth": metrics["queue_depth"],
                    "capacity": metrics["queue_capacity"],
                    "utilization_pct": round(metrics["queue_depth"] / metrics["queue_capacity"] * 100, 2) if metrics["queue_capacity"] > 0 else 0,
                },
                "resources": {
                    "memory_mb": round(metrics["memory_mb"], 2),
                    "peak_memory_mb": round(metrics["peak_memory_mb"], 2),
                    "active_concurrent": metrics["active_concurrent"],
                    "max_concurrent": metrics["max_concurrent"],
                },
                "latencies": metrics["stage_latencies_avg_ticks"],
            }
        )
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health/execution")
async def health_execution():
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        adapter = engine_instance.execution_adapter
        settings = engine_instance.settings

        execution_info = {
            "initialized": adapter.is_initialized,
            "connected": adapter.is_connected,
            "mode": "mock" if settings.use_mock_execution else "live",
            "gateway": settings.vnpy_gateway,
            "exchange_server": settings.exchange_server,
            "pending_orders": len(adapter.pending_orders),
            "executed_trades_count": len(adapter.executed_trades),
        }

        if adapter.is_connected:
            try:
                account_info = await adapter.get_account_info()
                execution_info["account"] = account_info
            except Exception as e:
                execution_info["account_error"] = str(e)

        return JSONResponse(content=execution_info)
    except Exception as e:
        logger.error(f"Execution health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_metrics():
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        engine_status = engine_instance.get_status()
        engine_metrics = engine_instance.get_metrics()

        metrics = {
            "timestamp": engine_instance.clock.now,
            "engine": engine_status,
            "queue_depth": engine_metrics["queue_depth"],
            "queue_capacity": engine_metrics["queue_capacity"],
            "active_concurrent": engine_metrics["active_concurrent"],
            "max_concurrent": engine_metrics["max_concurrent"],
            "stage_latencies_avg_ticks": engine_metrics["stage_latencies_avg_ticks"],
            "throughput_events": engine_metrics["throughput_events"],
            "rejected_events": engine_metrics["rejected_events"],
            "memory_mb": engine_metrics["memory_mb"],
            "peak_memory_mb": engine_metrics["peak_memory_mb"],
        }

        if hasattr(engine_instance, 'meta_harness') and engine_instance.meta_harness:
            try:
                meta_status = await engine_instance.meta_harness.get_status()
                metrics["meta_harness"] = meta_status
            except Exception as e:
                metrics["meta_harness"] = {"error": str(e)}

        if hasattr(engine_instance, 'risk_engine') and engine_instance.risk_engine:
            try:
                risk_status = await engine_instance.risk_engine.get_risk_status()
                metrics["risk_engine"] = risk_status
            except Exception as e:
                metrics["risk_engine"] = {"error": str(e)}

        return JSONResponse(content=metrics)

    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/meta/status")
async def get_meta_status():
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        if hasattr(engine_instance, 'meta_harness') and engine_instance.meta_harness:
            status = await engine_instance.meta_harness.get_status()
            return JSONResponse(content=status)
        else:
            raise HTTPException(status_code=503, detail="Meta harness not available")
    except Exception as e:
        logger.error(f"Error getting meta status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/halt")
async def halt_system(background_tasks: BackgroundTasks, reason: str = "Manual halt requested"):
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        if hasattr(engine_instance, 'meta_harness') and engine_instance.meta_harness:
            result = await engine_instance.meta_harness.halt_system(reason)
            if result["success"]:
                return JSONResponse(content=result)
            else:
                raise HTTPException(status_code=400, detail=result.get("message", "Halt failed"))
        else:
            raise HTTPException(status_code=503, detail="Meta harness not available")
    except Exception as e:
        logger.error(f"Error halting system: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/resume")
async def resume_system(background_tasks: BackgroundTasks):
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        if hasattr(engine_instance, 'meta_harness') and engine_instance.meta_harness:
            result = await engine_instance.meta_harness.resume_system()
            if result["success"]:
                return JSONResponse(content=result)
            else:
                raise HTTPException(status_code=400, detail=result.get("message", "Resume failed"))
        else:
            raise HTTPException(status_code=503, detail="Meta harness not available")
    except Exception as e:
        logger.error(f"Error resuming system: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/risk_adjust")
async def adjust_risk(adjustments: Dict[str, Any]):
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        if hasattr(engine_instance, 'meta_harness') and engine_instance.meta_harness:
            result = await engine_instance.meta_harness.adjust_risk_parameters(adjustments)
            if result["success"]:
                return JSONResponse(content=result)
            else:
                raise HTTPException(status_code=400, detail=result.get("message", "Risk adjustment failed"))
        else:
            raise HTTPException(status_code=503, detail="Meta harness not available")
    except Exception as e:
        logger.error(f"Error adjusting risk: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/disable_strategy")
async def disable_strategy(strategy_name: str):
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        if hasattr(engine_instance, 'meta_harness') and engine_instance.meta_harness:
            result = await engine_instance.meta_harness.disable_strategy(strategy_name)
            if result["success"]:
                return JSONResponse(content=result)
            else:
                raise HTTPException(status_code=400, detail=result.get("message", "Strategy disable failed"))
        else:
            raise HTTPException(status_code=503, detail="Meta harness not available")
    except Exception as e:
        logger.error(f"Error disabling strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/strategies")
async def get_strategy_status():
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        strategy_info = {
            "timestamp": engine_instance.clock.now,
            "strategies": {},
        }

        if hasattr(engine_instance, 'strategy_engine') and engine_instance.strategy_engine:
            try:
                perf = await engine_instance.strategy_engine.get_strategy_performance()
                strategy_info["strategies"]["performance"] = perf
            except Exception as e:
                strategy_info["strategies"]["performance_error"] = str(e)

        if hasattr(engine_instance, 'regime_engine') and engine_instance.regime_engine:
            try:
                regime = await engine_instance.regime_engine.get_current_regime()
                strategy_info["regime"] = regime
            except Exception as e:
                strategy_info["regime_error"] = str(e)

        return JSONResponse(content=strategy_info)

    except Exception as e:
        logger.error(f"Error getting strategy status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/regime")
async def get_regime_info():
    if engine_instance is None:
        raise HTTPException(status_code=503, detail="Engine not initialized")

    try:
        if hasattr(engine_instance, 'regime_engine') and engine_instance.regime_engine:
            regime_info = await engine_instance.regime_engine.get_current_regime()
            return JSONResponse(content=regime_info)
        else:
            raise HTTPException(status_code=503, detail="Regime engine not available")
    except Exception as e:
        logger.error(f"Error getting regime info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": "Endpoint not found"})


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
