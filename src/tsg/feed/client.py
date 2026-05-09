"""cTrader Open API client.

Bridges the Twisted-based `ctrader-open-api` library to a synchronous API
that mirrors the old `OandaClient`. Reactor runs in a daemon worker thread;
request/response pairs use threading.Event for sync handoff.

Public methods (compatibility with prior OandaClient surface):
    fetch_candles(instrument, granularity, count) -> pandas.DataFrame
    fetch_price(instrument)                       -> dict {bid, ask, mid, time}
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

try:
    from ctrader_open_api import Client, Protobuf, TcpProtocol  # type: ignore
    from ctrader_open_api.messages.OpenApiMessages_pb2 import (  # type: ignore
        ProtoOAApplicationAuthReq,
        ProtoOAApplicationAuthRes,
        ProtoOAAccountAuthReq,
        ProtoOAAccountAuthRes,
        ProtoOASymbolsListReq,
        ProtoOASymbolsListRes,
        ProtoOAGetTrendbarsReq,
        ProtoOAGetTrendbarsRes,
        ProtoOASubscribeSpotsReq,
        ProtoOASubscribeSpotsRes,
        ProtoOASpotEvent,
        ProtoOATraderReq,
        ProtoOATraderRes,
        ProtoOANewOrderReq,
        ProtoOAExecutionEvent,
        ProtoOAErrorRes,
    )
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import (  # type: ignore
        ProtoOATrendbarPeriod,
        ProtoOAPayloadType,
        ProtoOAOrderType,
        ProtoOATradeSide,
    )
    _CTRADER_AVAILABLE = True
except ImportError:
    _CTRADER_AVAILABLE = False


log = logging.getLogger(__name__)


def _instrument_to_ctrader(name: str) -> str:
    """EUR_USD -> EURUSD"""
    return name.replace("_", "")


def _now_ms() -> int:
    return int(time.time() * 1000)


class _Pending:
    __slots__ = ("event", "result", "error")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: Optional[Exception] = None


class CTraderClient:
    """Synchronous facade over the Twisted-based cTrader Open API client."""

    _msg_id_counter = 0
    _msg_id_lock = threading.Lock()

    def __init__(self, host: str, port: int,
                 client_id: str, client_secret: str,
                 access_token: str, account_id: int) -> None:
        if not _CTRADER_AVAILABLE:
            raise RuntimeError(
                "ctrader-open-api not installed. `pip install ctrader-open-api`."
            )
        self.host = host
        self.port = port
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.account_id = int(account_id)

        self._symbol_ids: dict[str, int] = {}
        self._spot: dict[int, dict] = {}
        self._subscribed: set[int] = set()
        self._pending: dict[str, _Pending] = {}

        self._client: Optional[Client] = None
        self._reactor_thread: Optional[threading.Thread] = None
        self._connected = threading.Event()
        self._authed = threading.Event()

    # ---------------- lifecycle ----------------
    def start(self, timeout: float = 30.0) -> None:
        from twisted.internet import reactor

        self._client = Client(self.host, self.port, TcpProtocol)
        self._client.setConnectedCallback(self._on_connected)
        self._client.setDisconnectedCallback(self._on_disconnected)
        self._client.setMessageReceivedCallback(self._on_message)
        self._client.startService()

        if not reactor.running:
            self._reactor_thread = threading.Thread(
                target=reactor.run,
                kwargs={"installSignalHandlers": False},
                daemon=True,
                name="twisted-reactor",
            )
            self._reactor_thread.start()

        if not self._connected.wait(timeout=timeout):
            raise RuntimeError("cTrader: connect timeout")
        self._app_auth(timeout)
        self._account_auth(timeout)
        self._refresh_symbols(timeout)

    def stop(self) -> None:
        from twisted.internet import reactor
        if self._client is not None:
            try:
                self._client.stopService()
            except Exception:
                pass
        try:
            if reactor.running:
                reactor.callFromThread(reactor.stop)
        except Exception:
            pass

    # ---------------- public sync API ----------------
    def fetch_candles(
        self,
        instrument: str,
        granularity: str = "H1",
        count: int = 200,
    ) -> pd.DataFrame:
        period = self._period_enum(granularity)
        symbol_id = self._symbol_id(instrument)

        period_ms = self._period_ms(granularity)
        to_ms = _now_ms()
        from_ms = to_ms - count * period_ms

        req = ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = symbol_id
        req.period = period
        req.fromTimestamp = from_ms
        req.toTimestamp = to_ms
        res = self._send(req, ProtoOAGetTrendbarsRes, timeout=15.0)

        rows = []
        for tb in res.trendbar:
            o = (tb.low + tb.deltaOpen) / 1e5
            h = (tb.low + tb.deltaHigh) / 1e5
            c = (tb.low + tb.deltaClose) / 1e5
            l = tb.low / 1e5
            t = pd.to_datetime(tb.utcTimestampInMinutes * 60, unit="s", utc=True)
            rows.append({
                "time": t, "open": float(o), "high": float(h),
                "low": float(l), "close": float(c),
                "volume": int(tb.volume),
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        return df.set_index("time").sort_index()

    def fetch_balance_usd(self) -> float:
        """Fetch account balance via ProtoOATraderReq.

        Returns balance in account currency (assumed USD for v1) as a float.
        cTrader sends `balance` as an integer in 1/10^moneyDigits units; for
        most demo accounts moneyDigits=2 (cents). We divide accordingly.
        """
        req = ProtoOATraderReq()
        req.ctidTraderAccountId = self.account_id
        res = self._send(req, ProtoOATraderRes, timeout=10.0)
        trader = res.trader
        money_digits = getattr(trader, "moneyDigits", 2) or 2
        return float(trader.balance) / (10 ** money_digits)

    def place_market_order(
        self,
        instrument: str,
        direction: str,           # "long" | "short"
        volume_units: int,        # cTrader volume (1 unit = 0.01 lot)
        sl_price: float,
        tp_price: float,
        label: str = "",
        comment: str = "tsg",
        timeout: float = 15.0,
    ) -> int:
        """Place a market order with attached SL/TP. Returns positionId.

        Blocks until ProtoOAExecutionEvent for the order returns with
        executionType ORDER_FILLED or raises if rejected.
        """
        symbol_id = self._symbol_id(instrument)
        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = symbol_id
        req.orderType = ProtoOAOrderType.MARKET
        req.tradeSide = (
            ProtoOATradeSide.BUY if direction == "long" else ProtoOATradeSide.SELL
        )
        req.volume = int(volume_units)
        req.stopLoss = float(sl_price)
        req.takeProfit = float(tp_price)
        if label:
            req.label = label
        if comment:
            req.comment = comment

        evt = self._send(req, ProtoOAExecutionEvent, timeout=timeout)
        # ExecutionEvent comes with various executionType values; we look for
        # ORDER_FILLED (3 in the proto enum) or accept ACCEPTED (1) as
        # provisional success. ORDER_REJECTED -> raise.
        et = getattr(evt, "executionType", None)
        if et == 6:  # ORDER_REJECTED
            raise RuntimeError(
                f"cTrader rejected order for {instrument}: "
                f"{getattr(evt, 'errorCode', '?')} {getattr(evt, 'description', '')}"
            )
        position = getattr(evt, "position", None)
        if position is None or not getattr(position, "positionId", 0):
            raise RuntimeError(
                f"cTrader order placed but no positionId returned (executionType={et})"
            )
        log.info(
            "cTrader order filled: %s %s vol=%d positionId=%s",
            instrument, direction, volume_units, position.positionId,
        )
        return int(position.positionId)

    def fetch_price(self, instrument: str, wait_seconds: float = 3.0) -> dict:
        symbol_id = self._symbol_id(instrument)
        if symbol_id not in self._subscribed:
            req = ProtoOASubscribeSpotsReq()
            req.ctidTraderAccountId = self.account_id
            req.symbolId.append(symbol_id)
            self._send(req, ProtoOASubscribeSpotsRes, timeout=10.0)
            self._subscribed.add(symbol_id)

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            spot = self._spot.get(symbol_id)
            if spot is not None and "bid" in spot and "ask" in spot:
                return {
                    "bid": spot["bid"],
                    "ask": spot["ask"],
                    "mid": (spot["bid"] + spot["ask"]) / 2.0,
                    "time": spot.get("time", datetime.now(timezone.utc)),
                }
            time.sleep(0.05)
        raise RuntimeError(f"cTrader: no spot tick yet for {instrument}")

    # ---------------- Twisted callbacks ----------------
    def _on_connected(self, client) -> None:
        log.info("cTrader connected")
        self._connected.set()

    def _on_disconnected(self, client, reason) -> None:
        log.warning("cTrader disconnected: %s", reason)
        self._connected.clear()
        self._authed.clear()

    def _on_message(self, client, message) -> None:
        try:
            payload_type = message.payloadType
            if payload_type == ProtoOAPayloadType.PROTO_OA_SPOT_EVENT:
                evt = Protobuf.extract(message)
                self._handle_spot(evt)
                return
            cm = message.clientMsgId or ""
            pending = self._pending.pop(cm, None)
            if pending is None:
                return
            try:
                pending.result = Protobuf.extract(message)
            except Exception as e:
                pending.error = e
            pending.event.set()
        except Exception:
            log.exception("cTrader: error handling message")

    def _handle_spot(self, evt) -> None:
        sid = evt.symbolId
        cur = self._spot.setdefault(sid, {})
        if evt.HasField("bid"):
            cur["bid"] = evt.bid / 1e5
        if evt.HasField("ask"):
            cur["ask"] = evt.ask / 1e5
        cur["time"] = datetime.now(timezone.utc)

    # ---------------- request/response plumbing ----------------
    def _next_msg_id(self) -> str:
        with CTraderClient._msg_id_lock:
            CTraderClient._msg_id_counter += 1
            return f"tsg-{CTraderClient._msg_id_counter}"

    def _send(self, req, res_type, timeout: float = 10.0):
        from twisted.internet import reactor
        if self._client is None:
            raise RuntimeError("cTrader client not started")
        cm = self._next_msg_id()
        pending = _Pending()
        self._pending[cm] = pending

        def _do_send():
            d = self._client.send(req, clientMsgId=cm)
            d.addErrback(lambda f: (
                setattr(pending, "error", f.value),
                pending.event.set(),
            ))
        reactor.callFromThread(_do_send)

        if not pending.event.wait(timeout=timeout):
            self._pending.pop(cm, None)
            raise TimeoutError(f"cTrader: {res_type.__name__} timeout")
        if pending.error is not None:
            raise pending.error
        return pending.result

    def _app_auth(self, timeout: float) -> None:
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.client_id
        req.clientSecret = self.client_secret
        self._send(req, ProtoOAApplicationAuthRes, timeout=timeout)
        log.info("cTrader application authenticated")

    def _account_auth(self, timeout: float) -> None:
        req = ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = self.account_id
        req.accessToken = self.access_token
        self._send(req, ProtoOAAccountAuthRes, timeout=timeout)
        self._authed.set()
        log.info("cTrader account %s authenticated", self.account_id)

    def _refresh_symbols(self, timeout: float) -> None:
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = self.account_id
        req.includeArchivedSymbols = False
        res = self._send(req, ProtoOASymbolsListRes, timeout=timeout)
        for s in res.symbol:
            self._symbol_ids[s.symbolName.upper()] = int(s.symbolId)
        log.info("cTrader: %d symbols loaded", len(self._symbol_ids))

    def _symbol_id(self, instrument: str) -> int:
        name = _instrument_to_ctrader(instrument).upper()
        sid = self._symbol_ids.get(name)
        if sid is None:
            raise KeyError(
                f"cTrader: unknown symbol {name!r}; broker may not list it"
            )
        return sid

    @staticmethod
    def _period_enum(granularity: str):
        return {
            "M1":  ProtoOATrendbarPeriod.M1,
            "M15": ProtoOATrendbarPeriod.M15,
            "H1":  ProtoOATrendbarPeriod.H1,
            "H4":  ProtoOATrendbarPeriod.H4,
            "D1":  ProtoOATrendbarPeriod.D1,
        }[granularity]

    @staticmethod
    def _period_ms(granularity: str) -> int:
        return {
            "M1":   60_000,
            "M15":  15 * 60_000,
            "H1":   60 * 60_000,
            "H4":   4 * 60 * 60_000,
            "D1":   24 * 60 * 60_000,
        }[granularity]
