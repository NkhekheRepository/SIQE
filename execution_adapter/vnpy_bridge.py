"""
VN.PY Bridge Module
Abstracts execution layer (VN.PY) to ensure business logic independence.
Deterministic: uses EventClock, seeded RNG, order lifecycle management.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from core.clock import EventClock
from models.trade import Decision, ExecutionResult, SignalType, OrderStatus

logger = logging.getLogger(__name__)


@dataclass
class OrderState:
    order_id: str
    symbol: str
    status: OrderStatus
    requested_qty: float
    filled_qty: float
    avg_fill_price: float
    created_at: int
    updated_at: int
    retry_count: int = 0
    error: str = ""


class ExecutionAdapter:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.bridge = None
        self.pending_orders: Dict[str, OrderState] = {}
        self.executed_trades: List[Dict[str, Any]] = []
        self.is_connected = False
        self.max_retries = settings.get("max_retries", 3)
        self.retry_base_delay = settings.get("retry_base_delay", 0.1)

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Execution Adapter...")
            use_mock = self.settings.get("use_mock_execution", True)

            if use_mock:
                logger.info("Using Mock VN.PY Bridge (development mode)")
                self.bridge = MockVNpyBridge(self.settings, self.clock)
            else:
                logger.info("Using Real VN.PY Bridge (production mode)")
                try:
                    self.bridge = VNpyBridge(self.settings, self.clock)
                except ImportError:
                    logger.warning("VN.PY not installed, falling back to Mock Bridge")
                    self.bridge = MockVNpyBridge(self.settings, self.clock)

            await self.bridge.initialize()
            self.is_initialized = True
            self.is_connected = True
            logger.info("Execution Adapter initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Execution Adapter: {e}")
            return False

    async def execute_trade(self, decision: Decision) -> ExecutionResult:
        if not self.is_initialized:
            return ExecutionResult(
                execution_id=f"exec_err_{self.clock.now}",
                trade_id="",
                symbol=decision.symbol,
                signal_type=decision.signal_type,
                filled_price=0.0,
                filled_quantity=0.0,
                status=OrderStatus.REJECTED,
                event_seq=decision.event_seq,
                error="Execution adapter not initialized",
            )

        if not self.is_connected:
            return ExecutionResult(
                execution_id=f"exec_err_{self.clock.now}",
                trade_id="",
                symbol=decision.symbol,
                signal_type=decision.signal_type,
                filled_price=0.0,
                filled_quantity=0.0,
                status=OrderStatus.REJECTED,
                event_seq=decision.event_seq,
                error="Not connected to execution layer",
            )

        try:
            execution_id = f"exec_{self.clock.tick()}"

            result = await self._execute_with_retry(
                symbol=decision.symbol,
                order_type=decision.signal_type.value,
                price=decision.price,
                strength=decision.strength,
                execution_id=execution_id,
            )

            if result.get("success"):
                trade_record = {
                    "execution_id": execution_id,
                    "symbol": decision.symbol,
                    "signal_type": decision.signal_type.value,
                    "price": result.get("filled_price", decision.price),
                    "quantity": result.get("filled_quantity", 0),
                    "timestamp": self.clock.now,
                    "strategy": decision.strategy,
                    "ev_score": decision.ev_score,
                    "status": result.get("status", "FILLED"),
                }

                self.executed_trades.append(trade_record)
                if len(self.executed_trades) > 1000:
                    self.executed_trades = self.executed_trades[-1000:]

                status = OrderStatus.PARTIALLY_FILLED if result.get("partial_fill", False) else OrderStatus.FILLED

                return ExecutionResult(
                    execution_id=execution_id,
                    trade_id="",
                    symbol=decision.symbol,
                    signal_type=decision.signal_type,
                    filled_price=result.get("filled_price", decision.price),
                    filled_quantity=result.get("filled_quantity", 0),
                    status=status,
                    event_seq=decision.event_seq,
                    strategy=decision.strategy,
                    slippage=result.get("slippage", 0.0),
                    partial_fill_qty=result.get("partial_fill_qty", 0.0),
                    partial_fill_price=result.get("partial_fill_price", 0.0),
                )
            else:
                return ExecutionResult(
                    execution_id=execution_id,
                    trade_id="",
                    symbol=decision.symbol,
                    signal_type=decision.signal_type,
                    filled_price=0.0,
                    filled_quantity=0.0,
                    status=OrderStatus.REJECTED,
                    event_seq=decision.event_seq,
                    error=result.get("error", "Unknown execution error"),
                )

        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return ExecutionResult(
                execution_id=f"exec_err_{self.clock.now}",
                trade_id="",
                symbol=decision.symbol,
                signal_type=decision.signal_type,
                filled_price=0.0,
                filled_quantity=0.0,
                status=OrderStatus.REJECTED,
                event_seq=decision.event_seq,
                error=f"Execution error: {str(e)}",
            )

    async def _execute_with_retry(self, symbol: str, order_type: str, price: float,
                                   strength: float, execution_id: str) -> Dict[str, Any]:
        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                result = await self.bridge.execute_order(
                    symbol=symbol,
                    order_type=order_type,
                    price=price,
                    strength=strength,
                    execution_id=execution_id,
                )
                if result.get("success"):
                    return result
                last_error = result.get("error", "Unknown")
                if attempt < self.max_retries:
                    adjusted_price = price * (1.001 if order_type == "long" else 0.999)
                    price = adjusted_price
                    delay = self.retry_base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    delay = self.retry_base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)

        return {"success": False, "error": f"Failed after {self.max_retries} retries: {last_error}"}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "Not initialized"}
        try:
            result = await self.bridge.cancel_order(order_id)
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]
            return result
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return {"success": False, "error": str(e)}

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "Not initialized"}
        try:
            return await self.bridge.get_order_status(order_id)
        except Exception as e:
            logger.error(f"Error getting order status for {order_id}: {e}")
            return {"success": False, "error": str(e)}

    async def get_position(self, symbol: str) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "Not initialized"}
        try:
            return await self.bridge.get_position(symbol)
        except Exception as e:
            logger.error(f"Error getting position for {symbol}: {e}")
            return {"success": False, "error": str(e)}

    async def get_account_info(self) -> Dict[str, Any]:
        if not self.is_initialized:
            return {"success": False, "error": "Not initialized"}
        try:
            return await self.bridge.get_account_info()
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return {"success": False, "error": str(e)}

    async def shutdown(self):
        logger.info("Shutting down Execution Adapter...")
        if self.bridge:
            await self.bridge.shutdown()
        self.is_initialized = False
        self.is_connected = False
        self.pending_orders.clear()
        logger.info("Execution Adapter shutdown complete")


class VNpyBridge:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.orders: Dict[str, OrderState] = {}
        self.positions: Dict[str, Any] = {}
        self.main_engine = None
        self.event_engine = None
        self.gateway_name = settings.get("vnpy_gateway", "BINANCE")

    async def initialize(self) -> bool:
        try:
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine

            self.event_engine = EventEngine()
            self.main_engine = MainEngine(self.event_engine)

            gateway_name = self.gateway_name.upper()
            if gateway_name == "BINANCE":
                from vnpy_binance import BinanceGateway
                self.main_engine.add_gateway(BinanceGateway, gateway_name)
            elif gateway_name == "CTP":
                from vnpy_ctp import CtpGateway
                self.main_engine.add_gateway(CtpGateway, gateway_name)
            else:
                logger.warning(f"Unknown gateway: {gateway_name}")
                return False

            gateway_setting = {
                "key": self.settings.get("exchange_api_key", ""),
                "secret": self.settings.get("exchange_api_secret", ""),
                "proxy_host": self.settings.get("proxy_host", ""),
                "proxy_port": self.settings.get("proxy_port", 0),
                "server": self.settings.get("exchange_server", "SIMULATOR"),
            }

            self.main_engine.connect(gateway_setting, gateway_name)
            self.event_engine.start()
            self.is_initialized = True
            logger.info(f"VN.PY Bridge initialized with gateway: {gateway_name}")
            return True
        except ImportError as e:
            logger.error(f"VN.PY not installed: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize VN.PY Bridge: {e}")
            return False

    async def execute_order(self, symbol: str, order_type: str, price: float,
                            strength: float, execution_id: str) -> Dict[str, Any]:
        try:
            from vnpy.trader.object import OrderRequest, SubscribeRequest
            from vnpy.trader.constant import Direction, Offset, OrderType

            req = SubscribeRequest(symbol=symbol, exchange="BINANCE")
            self.main_engine.subscribe(req, self.gateway_name)

            direction = Direction.LONG if order_type.upper() in ("long", "buy") else Direction.SHORT

            account_info = await self.get_account_info()
            balance = account_info.get("account_balance", 0)
            trade_value = balance * min(0.1, strength * 0.1)
            quantity = trade_value / price if price > 0 else 0

            order_req = OrderRequest(
                symbol=symbol,
                exchange="BINANCE",
                direction=direction,
                offset=Offset.OPEN,
                type=OrderType.LIMIT,
                price=price,
                volume=quantity,
            )

            vt_orderid = self.main_engine.send_order(order_req, self.gateway_name)

            order_state = OrderState(
                order_id=execution_id,
                symbol=symbol,
                status=OrderStatus.PENDING,
                requested_qty=quantity,
                filled_qty=0.0,
                avg_fill_price=0.0,
                created_at=self.clock.now,
                updated_at=self.clock.now,
            )
            self.orders[execution_id] = order_state

            await asyncio.sleep(0.5)

            order = self.main_engine.get_order(vt_orderid)
            if order and order.status.value == "alltraded":
                filled_price = order.price if order.price > 0 else price
                filled_qty = order.volume if order.volume > 0 else quantity

                order_state.status = OrderStatus.FILLED
                order_state.filled_qty = filled_qty
                order_state.avg_fill_price = filled_price
                order_state.updated_at = self.clock.now

                return {
                    "success": True,
                    "execution_id": execution_id,
                    "symbol": symbol,
                    "order_type": order_type,
                    "filled_price": filled_price,
                    "filled_quantity": filled_qty,
                    "timestamp": self.clock.now,
                    "status": "FILLED",
                }
            else:
                return {
                    "success": False,
                    "error": f"Order not filled: {order.status if order else 'unknown'}",
                    "execution_id": execution_id,
                }

        except Exception as e:
            logger.error(f"Error in VN.PY order execution: {e}")
            return {"success": False, "error": f"VN.PY execution error: {str(e)}", "execution_id": execution_id}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            order = self.orders[order_id]
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                order.updated_at = self.clock.now
                return {"success": True, "order_id": order_id, "status": "CANCELLED"}
            else:
                return {"success": False, "error": "Order cannot be cancelled"}
        return {"success": False, "error": "Order not found"}

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            order = self.orders[order_id]
            return {"success": True, "order_id": order_id, "status": order.status.value,
                    "filled_qty": order.filled_qty, "avg_fill_price": order.avg_fill_price}
        return {"success": False, "error": "Order not found"}

    async def get_position(self, symbol: str) -> Dict[str, Any]:
        if self.main_engine:
            positions = self.main_engine.get_all_positions()
            for pos in positions:
                if pos.symbol == symbol:
                    return {"success": True, "symbol": symbol, "position": pos.volume,
                            "direction": pos.direction.value, "price": pos.price, "pnl": pos.pnl,
                            "timestamp": self.clock.now}
        return {"success": True, "symbol": symbol, "position": 0.0}

    async def get_account_info(self) -> Dict[str, Any]:
        if self.main_engine:
            accounts = self.main_engine.get_all_accounts()
            if accounts:
                return {"success": True, "account_balance": accounts[0].balance,
                        "available": accounts[0].available, "frozen": accounts[0].frozen,
                        "currency": "USDT", "timestamp": self.clock.now}
        return {"success": True, "account_balance": self.settings.get("initial_equity", 10000.0),
                "currency": "USDT", "timestamp": self.clock.now}

    async def shutdown(self):
        logger.info("Shutting down VN.PY Bridge...")
        if self.event_engine:
            self.event_engine.stop()
        if self.main_engine:
            self.main_engine.close()
        self.is_initialized = False
        self.orders.clear()
        self.positions.clear()
        logger.info("VN.PY Bridge shutdown complete")


class MockVNpyBridge:
    def __init__(self, settings, clock: EventClock):
        self.settings = settings
        self.clock = clock
        self.is_initialized = False
        self.orders: Dict[str, OrderState] = {}
        self.positions: Dict[str, float] = {}
        self.account_balance = settings.get("initial_equity", 10000.0)
        self._fill_counter = 0

    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Mock VN.PY Bridge...")
            self.is_initialized = True
            self.positions = {"BTCUSDT": 0.0, "ETHUSDT": 0.0}
            logger.info("Mock VN.PY Bridge initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Mock VN.PY Bridge: {e}")
            return False

    async def execute_order(self, symbol: str, order_type: str, price: float,
                            strength: float, execution_id: str) -> Dict[str, Any]:
        try:
            await asyncio.sleep(0.01)

            self._fill_counter += 1
            if self._fill_counter % 100 == 0:
                return {"success": False, "error": "Simulated execution failure", "execution_id": execution_id}

            base_slippage = 0.0005
            strength_factor = 0.5 + (strength * 0.5)
            slippage = base_slippage * strength_factor

            if order_type.upper() in ("long", "buy"):
                filled_price = price * (1 + slippage)
            else:
                filled_price = price * (1 - slippage)

            trade_value_pct = min(0.1, strength * 0.1)
            trade_value = self.account_balance * trade_value_pct
            quantity = trade_value / filled_price if filled_price > 0 else 0
            quantity = round(quantity, 6)

            partial_fill = False
            partial_fill_qty = 0.0
            partial_fill_price = 0.0

            if self._fill_counter % 50 == 0:
                fill_ratio = 0.6
                partial_fill_qty = quantity * fill_ratio
                quantity = partial_fill_qty
                partial_fill = True
                partial_fill_price = filled_price

            if symbol not in self.positions:
                self.positions[symbol] = 0.0

            if order_type.upper() in ("long", "buy"):
                self.positions[symbol] += quantity
                self.account_balance -= (quantity * filled_price)
            else:
                self.positions[symbol] -= quantity
                self.account_balance += (quantity * filled_price)

            status = OrderStatus.PARTIALLY_FILLED if partial_fill else OrderStatus.FILLED
            order_state = OrderState(
                order_id=execution_id,
                symbol=symbol,
                status=status,
                requested_qty=quantity,
                filled_qty=quantity,
                avg_fill_price=filled_price,
                created_at=self.clock.now,
                updated_at=self.clock.now,
            )
            self.orders[execution_id] = order_state

            logger.debug(f"Mock execution: {order_type} {quantity:.6f} {symbol} @ {filled_price:.2f}")

            return {
                "success": True,
                "execution_id": execution_id,
                "symbol": symbol,
                "order_type": order_type,
                "filled_price": filled_price,
                "filled_quantity": quantity,
                "timestamp": self.clock.now,
                "status": status.value,
                "slippage": slippage,
                "partial_fill": partial_fill,
                "partial_fill_qty": partial_fill_qty,
                "partial_fill_price": partial_fill_price,
            }

        except Exception as e:
            logger.error(f"Error in mock order execution: {e}")
            return {"success": False, "error": f"Mock execution error: {str(e)}", "execution_id": execution_id}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            order = self.orders[order_id]
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CANCELLED
                order.updated_at = self.clock.now
                return {"success": True, "order_id": order_id, "status": "CANCELLED"}
            else:
                return {"success": False, "error": "Order cannot be cancelled"}
        return {"success": False, "error": "Order not found"}

    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        if order_id in self.orders:
            order = self.orders[order_id]
            return {"success": True, "order_id": order_id, "status": order.status.value,
                    "filled_qty": order.filled_qty, "avg_fill_price": order.avg_fill_price}
        return {"success": False, "error": "Order not found"}

    async def get_position(self, symbol: str) -> Dict[str, Any]:
        position = self.positions.get(symbol, 0.0)
        return {"success": True, "symbol": symbol, "position": position, "timestamp": self.clock.now}

    async def get_account_info(self) -> Dict[str, Any]:
        return {"success": True, "account_balance": self.account_balance, "currency": "USDT", "timestamp": self.clock.now}

    async def shutdown(self):
        logger.info("Shutting down Mock VN.PY Bridge...")
        self.is_initialized = False
        self.orders.clear()
        self.positions.clear()
        logger.info("Mock VN.PY Bridge shutdown complete")
