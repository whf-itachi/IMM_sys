"""
MQTT Publisher Module for JetLinks IoT Platform
Handles MQTT connection, authentication, and data publishing.
"""

import hashlib
import json
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from app.utils.logging_config import setup_logger

import paho.mqtt.client as mqtt

import ssl

from app.config.app_config import (
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_USE_TLS,
    MQTT_CUSTOM_SECURE_ID,
    MQTT_CUSTOM_SECURE_KEY,
    MQTT_CUSTOM_DEVICE_ID,
    MQTT_TELEMETRY_TOPIC_FORMAT,
    MQTT_EVENT_TOPIC_FORMAT,
    MQTT_KEEP_ALIVE,
    MQTT_CA_CERT_FILE,
    PROPERTY_MAPPING,
)

logger = setup_logger()

class JetLinksMQTTPublisher:
    def __init__(self):
        self._client = None
        self._connected = False
        self._lock = threading.Lock() # 确保线程安全
        self._connect_attempts = 0
        # Use a flag to prevent multiple concurrent reconnection attempts
        self._reconnecting = False

    def connect(self):
        """Initialize and connect the MQTT client."""
        logger.info("Initializing MQTT connection to JetLinks...")
        if self._connected:
            logger.info("MQTT client is already connected.")
            return

        # Use lock to prevent multiple connect attempts simultaneously
        with self._lock:
            if self._connected: # Double-check inside lock
                logger.info("MQTT client is already connected.")
                return

            try:
                # --- Generate credentials according to test_1.py logic ---
                # 1. Client ID: Use the full Device ID
                client_id = MQTT_CUSTOM_DEVICE_ID

                # 2. Username: secureId + "|" + current_timestamp_ms
                current_timestamp_ms = str(int(time.time() * 1000)) # Convert to milliseconds
                username = f"{MQTT_CUSTOM_SECURE_ID}|{current_timestamp_ms}"

                # 3. Password: md5(secureId + "|" + timestamp_ms + "|" + secureKey)
                # This matches the logic in test_1.py
                password_input = f"{MQTT_CUSTOM_SECURE_ID}|{current_timestamp_ms}|{MQTT_CUSTOM_SECURE_KEY}"
                password = hashlib.md5(password_input.encode()).hexdigest()

                logger.debug(f"Using Custom Signature Auth - ClientID: {client_id}, Username: {username}")
                # ---

                self._client = mqtt.Client(client_id=client_id, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)

                # 设置生成的用户名密码
                self._client.username_pw_set(username, password)

                # 设置回调函数
                self._client.on_connect = self._on_connect
                self._client.on_disconnect = self._on_disconnect
                self._client.on_publish = self._on_publish

                # Configure TLS if enabled
                if MQTT_USE_TLS:
                    logger.info("Enabling TLS for MQTT connection.")
                    try:
                        import os
                        # 检查证书文件是否存在
                        if os.path.exists(MQTT_CA_CERT_FILE):
                            self._client.tls_set(
                                ca_certs=MQTT_CA_CERT_FILE,
                                cert_reqs=ssl.CERT_REQUIRED,
                                tls_version=ssl.PROTOCOL_TLS_CLIENT
                            )
                            # 禁用主机名检查（在某些情况下可能需要）
                            self._client.tls_insecure_set(True)
                            logger.info(f"TLS certificate loaded successfully: {MQTT_CA_CERT_FILE}")
                        else:
                            logger.warning(f"Certificate file not found: {MQTT_CA_CERT_FILE}. Using insecure TLS connection.")
                            # 如果证书文件不存在，仍然使用不验证证书的连接
                            self._client.tls_set(cert_reqs=ssl.CERT_NONE)
                    except ImportError:
                        logger.warning("Certificate file configuration not found. Using insecure TLS connection.")
                        # 如果配置不可用，回退到不验证证书的连接
                        self._client.tls_set(cert_reqs=ssl.CERT_NONE)

                # Configure automatic reconnection with exponential backoff
                # This handles disconnections due to network issues
                self._client.reconnect_delay_set(min_delay=1, max_delay=120) # 1s to 120s delay

                # 连接
                self._client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=MQTT_KEEP_ALIVE)
                logger.info(f"Connecting to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}...")

                # 启动网络循环（使用线程）
                self._client.loop_start()

                # 等待连接建立
                timeout = 10 # 等待连接成功的超时时间（秒）
                start_time = time.time()
                while not self._connected and time.time() - start_time < timeout:
                    time.sleep(0.1)

                if not self._connected:
                    # If still not connected after timeout, attempt manual reconnect once
                    # This can sometimes help if the initial connect handshake was delayed
                    logger.warning("Initial connection attempt timed out, trying manual reconnect...")
                    try:
                        self._client.reconnect()
                    except Exception as reconnect_e:
                        logger.error(f"Manual reconnect failed: {reconnect_e}")

                    # Wait a bit more after manual reconnect
                    time.sleep(1)
                    if not self._connected:
                        raise ConnectionError(f"Failed to connect to MQTT broker within {timeout} seconds.")

                logger.info("Successfully connected to JetLinks MQTT broker.")
                self._connect_attempts = 0 # 连接成功后重置尝试次数

            except Exception as e:
                logger.error(f"Error connecting to MQTT broker: {e}")
                # Ensure connected flag is False if connect fails critically
                self._connected = False
                self._reconnecting = False
                raise e # 或者根据策略决定是否抛出异常

    def _on_log(self, client, userdata, level, buf):
        """Optional: Log MQTT client internal logs for debugging."""
        logger.debug(f"MQTT Log: {level} - {buf}")

    def disconnect(self):
        """Disconnect the MQTT client."""
        if self._client:
            logger.info("Disconnecting from MQTT broker...")
            self._client.loop_stop() # 偞止网络循环
            self._client.disconnect()
            self._connected = False
            logger.info("Disconnected from MQTT broker.")

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            logger.info("Connected to MQTT broker with result code 0 (Success)")
            self._connected = True
            self._reconnecting = False # Reset reconnecting flag on successful connect
            self._connect_attempts = 0 # 连接成功后重置尝试次数
        else:
            logger.error(f"Connection to MQTT broker failed with result code {rc}")
            self._connected = False
            # paho-mqtt's built-in reconnection will handle retries based on reconnect_delay_set

    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the server."""
        logger.warning(f"Disconnected from MQTT broker with result code {rc}")
        self._connected = False
        self._reconnecting = True # Set flag indicating reconnection attempt is happening
        # paho-mqtt's built-in reconnection (via reconnect_delay_set) will trigger automatically

    def _on_publish(self, client, userdata, mid):
        """Callback for when a message is published."""
        logger.debug(f"Message with MID {mid} published successfully.")

    def _map_properties(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply property mapping if defined."""
        if PROPERTY_MAPPING:
            mapped_data = {}
            for local_key, value in data.items():
                jetlinks_key = PROPERTY_MAPPING.get(local_key, local_key) # 默认使用原名
                mapped_data[jetlinks_key] = value
            return mapped_data
        return data

    def publish_telemetry(self, data: Dict[str, Any], timestamp: Optional[int] = None):
        """
        Publish telemetry data to JetLinks. Uses the configured TELEMETRY_TOPIC_FORMAT.
        :param data: Dictionary containing telemetry data (e.g., {"temperature": 25.5, "status": "running"})
        :param timestamp: Optional timestamp in milliseconds since epoch.
        """
        if not self._connected:
             logger.warning("MQTT client is not connected. Attempting to publish anyway (paho-mqtt will queue if auto-reconnect is working).")
             # We rely on paho-mqtt's internal queuing and auto-reconnect for publish calls
             # It will attempt to send the message once reconnected.

        if not self._connected and not self._reconnecting:
             # If explicitly not connected and not in a reconnection attempt initiated by on_disconnect,
             # we might want to log or handle this differently if needed.
             logger.info("Not connected, but paho-mqtt auto-reconnect is enabled, publish will be queued.")

        try:
            # Apply property mapping if configured
            mapped_data = self._map_properties(data.copy()) # Copy to avoid modifying original

            # Add timestamp if provided by JetLinks standard or convention
            if timestamp is not None:
                pass # Placeholder for timestamp handling if required by specific setup

            payload_json = json.dumps(mapped_data)
            topic = MQTT_TELEMETRY_TOPIC_FORMAT # Use the configured telemetry topic

            logger.debug(f"Publishing telemetry to topic '{topic}': {payload_json}")

            result = self._client.publish(topic, payload_json, qos=1) # Use QoS 1 for at least once delivery

            # result.rc indicates the status of the publish call itself (not the delivery)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Telemetry queued for publishing to '{topic}'. Message ID: {result.mid}")
                # Note: Success here means it was queued, not necessarily delivered yet.
                # Delivery confirmation depends on QoS and broker/client state.
                return True
            else:
                logger.error(f"Failed to queue telemetry for '{topic}'. Error code: {result.rc}")
                return False

        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize telemetry data to JSON: {e}. Data: {data}")
            return False
        except Exception as e:
            logger.error(f"An error occurred while publishing telemetry: {e}")
            return False

    def publish_flatness_data_event(self, event_data: dict):
        """
        Publish flatness measurement data event to JetLinks. Uses the configured EVENT_TOPIC_FORMAT.
        :param event_data: Dictionary containing the flatness measurement data according to the thing model
        """
        logger.info("进入publisher事件处理函数")
        try:
            # 构造符合JetLinks标准的事件上报格式
            standard_payload = {
                "messageId": str(uuid.uuid4()),  # 生成唯一ID作为messageId
                "timestamp": int(datetime.now().timestamp() * 1000),  # 毫秒时间戳
                "data": event_data  # 实际的平面度测量数据
            }
            payload_json = json.dumps(standard_payload)
            # Format the event topic using the event ID 'flatness_data'
            topic = MQTT_EVENT_TOPIC_FORMAT.format(event_id='flatness_data')

            logger.info(f"话题为: {topic}， 数据为：{payload_json}")

            pub_result = self._client.publish(topic, payload_json, qos=1)
            if hasattr(pub_result, 'wait_for_publish'):
                pub_result.wait_for_publish(timeout=3)
            logger.info(f"Publish result: {pub_result.rc}, Message ID: {pub_result.mid}")

            if pub_result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Flatness data event queued for publishing to '{topic}'. Message ID: {pub_result.mid}")
                return True
            else:
                logger.error(f"Failed to queue flatness data event for '{topic}'. Error code: {pub_result.rc}")
                return False

        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize flatness data event to JSON: {e}. Event data: {event_data}")
            return False
        except Exception as e:
            logger.error(f"An error occurred while publishing flatness data event: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    @property
    def is_connected(self):
        return self._connected