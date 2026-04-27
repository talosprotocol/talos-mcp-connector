import json
import logging
import base64
import os
import asyncio
from typing import Dict, Any, List, Optional
import requests
import websockets
from talos_mcp.transport.base import McpTransport
from talos.core.session import SessionManager, PrekeyBundle
from talos.core.crypto import generate_signing_keypair, KeyPair

logger = logging.getLogger(__name__)

class TalosTunnelTransport(McpTransport):
    def __init__(self, config):
        super().__init__(config)
        self.session_manager = None
        self.session = None
        self.ws = None
        self.loop = asyncio.get_event_loop()
        self.connected = False

    def connect(self):
        """Establish a secure Double Ratchet session with the Gateway."""
        if not self.config.endpoint:
            raise ValueError("No endpoint configured for Talos Tunnel")

        # 1. Fetch Gateway Prekey Bundle
        http_url = self.config.endpoint.replace("ws://", "http://").replace("wss://", "https://")
        prekey_url = f"{http_url.rstrip('/')}/v1/protocol/prekey"
        
        try:
            resp = requests.get(prekey_url, timeout=10)
            resp.raise_for_status()
            bundle_data = resp.json()
            
            bundle = PrekeyBundle(
                identity_key=base64.urlsafe_b64decode(bundle_data["identity_key"] + "==="),
                signed_prekey=base64.urlsafe_b64decode(bundle_data["signed_prekey"] + "==="),
                prekey_signature=base64.urlsafe_b64decode(bundle_data["prekey_signature"] + "===")
            )
        except Exception as e:
            raise RuntimeError(f"Failed to fetch Gateway prekey: {e}")

        # 2. Initialize Session Manager (Alice)
        # In a real app, we'd load our identity from a wallet file.
        kp = generate_signing_keypair()
        self.session_manager = SessionManager(kp)
        
        # 3. Perform Handshake via WebSocket
        ws_url = self.config.endpoint.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url.rstrip('/')}/v1/connect"
        
        # We need to run this in a thread or use sync-over-async because McpTransport is sync
        return self.loop.run_until_complete(self._async_connect(ws_url, bundle))

    async def _async_connect(self, ws_url: str, bundle: PrekeyBundle):
        self.ws = await websockets.connect(ws_url, subprotocols=["talos.1.0"])
        
        # Create session as initiator
        self.session = self.session_manager.create_session_as_initiator(
            peer_id="gateway",
            peer_bundle=bundle
        )
        
        # Send HANDSHAKE frame
        # Alice sends her identity and ephemeral public key (reusing first ratchet key)
        handshake_frame = {
            "version": 1,
            "type": "HANDSHAKE",
            "payload": base64.urlsafe_b64encode(self.session.state.dh_keypair.public_key).decode().rstrip("="),
            "nonce": base64.urlsafe_b64encode(self.session_manager.identity_keypair.public_key).decode().rstrip("="),
            "session_id": "mcp-connector-1"
        }
        await self.ws.send(json.dumps(handshake_frame))
        
        # Receive HANDSHAKE_ACK
        resp_data = await self.ws.recv()
        resp = json.loads(resp_data)
        if resp.get("type") != "HANDSHAKE_ACK":
             raise RuntimeError(f"Handshake failed: {resp}")
        
        self.connected = True
        logger.info(f"Secure tunnel established. Session: {resp.get('session_id')}")

    def close(self):
        if self.ws:
            self.loop.run_until_complete(self.ws.close())
        self.connected = False

    def list_tools(self) -> List[Dict[str, Any]]:
        # Encrypted tool listing over tunnel
        request = {"method": "list_tools", "params": {"server_id": self.config.id}}
        response = self._send_encrypted(request)
        return response.get("tools", [])

    def get_tool_schema(self, tool_name: str) -> Dict[str, Any]:
        request = {"method": "get_tool_schema", "params": {"server_id": self.config.id, "tool_name": tool_name}}
        response = self._send_encrypted(request)
        return response.get("json_schema", {})

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        request = {
            "method": "call_tool", 
            "params": {
                "server_id": self.config.id,
                "tool_name": tool_name,
                "arguments": arguments
            }
        }
        response = self._send_encrypted(request)
        return response.get("output", {})

    def _send_encrypted(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.connected:
            self.connect()

        plaintext = json.dumps(payload).encode()
        encrypted = self.session.encrypt(plaintext)
        
        data_frame = {
            "version": 1,
            "type": "DATA",
            "payload": base64.urlsafe_b64encode(encrypted).decode().rstrip("="),
            "sequence": self.session.messages_sent
        }
        
        return self.loop.run_until_complete(self._async_send_receive(data_frame))

    async def _async_send_receive(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        await self.ws.send(json.dumps(frame))
        
        resp_data = await self.ws.recv()
        resp_frame = json.loads(resp_data)
        
        if resp_frame.get("type") == "DATA":
            ciphertext = base64.urlsafe_b64decode(resp_frame["payload"] + "===")
            plaintext = self.session.decrypt(ciphertext)
            return json.loads(plaintext.decode())
        
        return {"error": f"Unexpected response type: {resp_frame.get('type')}"}
