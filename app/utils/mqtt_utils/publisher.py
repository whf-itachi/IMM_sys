"""
MQTT Publisher Module for JetLinks IoT Platform
Handles MQTT connection, authentication, and data publishing.
"""
import hashlib
import json
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

import paho.mqtt.client as mqtt
import ssl

from app.utils.logging_config import setup_logger
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
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._lock = threading.Lock()
        self._connect_attempts = 0
        self._reconnecting = False
        self._tls_insecure = True  # 是否关闭域名校验（自签证书开启True）

    def connect(self):
        """Initialize and connect the MQTT client."""
        logger.info("Initializing MQTT connection to JetLinks...")
        if self._connected:
            logger.info("MQTT client is already connected.")
            return

        with self._lock:
            if self._connected:
                logger.info("MQTT client is already connected.")
                return

            try:
                # 动态生成认证凭据
                client_id = MQTT_CUSTOM_DEVICE_ID
                current_timestamp_ms = str(int(time.time() * 1000))
                username = f"{MQTT_CUSTOM_SECURE_ID}|{current_timestamp_ms}"
                password_input = f"{MQTT_CUSTOM_SECURE_ID}|{current_timestamp_ms}|{MQTT_CUSTOM_SECURE_KEY}"
                password = hashlib.md5(password_input.encode()).hexdigest()

                logger.debug(f"Using Dynamic Auth - ClientID: {client_id}, Username: {username}")

                # 创建客户端实例
                self._client = mqtt.Client(
                    client_id=client_id,
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                    clean_session=False
                )
                self._client.username_pw_set(username, password)

                # 设置遗嘱消息
                self._client.will_set(
                    topic=f"device/{MQTT_CUSTOM_DEVICE_ID}/status",
                    payload=json.dumps({"status": "offline", "timestamp": time.time()}),
                    qos=1,
                    retain=True
                )

                # 注册回调
                self._client.on_connect = self._on_connect
                self._client.on_disconnect = self._on_disconnect
                self._client.on_publish = self._on_publish
                self._client.on_log = self._on_log

                # TLS配置
                if MQTT_USE_TLS:
                    logger.info("Enabling TLS for MQTT connection.")
                    if self._setup_tls():
                        logger.info(f"Certificate imported: {MQTT_CA_CERT_FILE}, hostname verification: {self._tls_insecure}")

                # 设置重连参数
                self._client.reconnect_delay_set(min_delay=2, max_delay=60)

                # 连接服务器
                self._client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=MQTT_KEEP_ALIVE)
                logger.info(f"Connecting to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}...")

                # 启动网络循环
                self._client.loop_start()

                # 等待连接完成
                if not self._wait_for_connection():
                    self._handle_connection_timeout()

                logger.info("Successfully connected to JetLinks MQTT broker.")
                self._connect_attempts = 0

            except Exception as e:
                logger.error(f"Error connecting to MQTT broker: {e}", exc_info=True)
                self._connected = False
                self._reconnecting = False
                raise e

    def _setup_tls(self):
        """设置TLS连接参数"""
        # 检查证书文件
        if not os.path.exists(MQTT_CA_CERT_FILE):
            logger.warning(f"No certificate file found: {MQTT_CA_CERT_FILE}, disabling verification.")
            self._client.tls_set(cert_reqs=ssl.CERT_NONE)
            self._client.tls_insecure_set(True)
            return True

        # 检查TLS版本支持
        if not hasattr(ssl, 'PROTOCOL_TLSv1_2'):
            logger.warning("TLS v1.2 not available, using insecure TLS.")
            self._client.tls_set(cert_reqs=ssl.CERT_NONE)
            self._client.tls_insecure_set(True)
            return True

        # 配置TLS
        self._client.tls_set(
            ca_certs=MQTT_CA_CERT_FILE,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLSv1_2
        )
        self._client.tls_insecure_set(self._tls_insecure)
        return True

    def _wait_for_connection(self, timeout=15):
        """等待连接完成"""
        start_time = time.time()
        while not self._connected and (time.time() - start_time) < timeout:
            time.sleep(0.1)
        return self._connected

    def _handle_connection_timeout(self):
        """处理连接超时"""
        logger.warning("Initial connection attempt timed out, trying manual reconnect...")
        try:
            self._client.reconnect()
        except Exception as e:
            logger.error(f"Manual reconnect failed: {e}")
        
        time.sleep(2)
        if not self._connected:
            raise ConnectionError("Failed to connect to MQTT broker within timeout period.")

    def _auto_reconnect(self):
        """断线后台指数退避重连，独立线程执行"""
        if self._reconnecting or self._connected:
            return

        with self._lock:
            if self._reconnecting or self._connected:
                return
            self._reconnecting = True

        self._connect_attempts += 1
        # 指数退避，最大延迟30秒
        delay = min(2 * self._connect_attempts, 30)
        logger.info(f"Schedule background reconnect after {delay}s, attempt count={self._connect_attempts}")

        def reconnect_task():
            try:
                time.sleep(delay)
                if not self._connected and not self._reconnecting:
                    logger.info("Attempting to reconnect to MQTT broker...")
                    self.connect()
            except Exception as e:
                logger.error(f"Background reconnect task failed: {e}")
            finally:
                with self._lock:
                    self._reconnecting = False

        threading.Thread(target=reconnect_task, daemon=True).start()

    def _on_log(self, level, buf):
        """MQTT底层日志回调"""
        logger.debug(f"MQTT internal log | lvl={level} msg={buf}")

    def disconnect(self):
        """安全断开连接，释放资源"""
        if self._client:
            logger.info("Disconnecting from MQTT broker...")
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            logger.info("Disconnected from MQTT broker.")

    def _on_connect(self, client, userdata, flags, rc):
        """连接结果回调"""
        if rc == 0:
            logger.info("Connected to MQTT broker with result code 0 (Success)")
            self._connected = True
            self._reconnecting = False
            self._connect_attempts = 0
        else:
            logger.error(f"Connection to MQTT broker failed with result code {rc}")
            self._connected = False
            self._auto_reconnect()

    def _on_disconnect(self, client, userdata, rc):
        """断线回调"""
        if rc == 0:
            logger.info("MQTT client disconnected cleanly")
            self._connected = False
        else:
            logger.warning(f"Disconnected from MQTT broker with result code {rc}")
            self._connected = False
            self._auto_reconnect()

    def _on_publish(self, client, userdata, mid):
        """消息发送完成回调"""
        logger.debug(f"Message with MID {mid} published successfully.")

    def _map_properties(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """字段映射转换"""
        if not PROPERTY_MAPPING:
            return data
        return {PROPERTY_MAPPING.get(k, k): v for k, v in data.items()}

    def publish_telemetry(self, data: Dict[str, Any]) -> bool:
        """上报时序遥测数据"""
        if not self._is_connected():
            logger.error("MQTT client not connected, skip publish")
            return False
        
        try:
            mapped_data = self._map_properties(data.copy())
            payload_json = json.dumps(mapped_data, ensure_ascii=False)
            topic = MQTT_TELEMETRY_TOPIC_FORMAT

            logger.debug(f"Publishing telemetry to topic '{topic}': {payload_json}")
            result = self._client.publish(topic, payload_json, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Telemetry queued, mid={result.mid}")
                return True
            else:
                logger.error(f"Telemetry publish failed, rc={result.rc}")
                return False
        except (TypeError, ValueError) as e:
            logger.error(f"Serialize telemetry json failed: {e}, raw data={data}")
            return False
        except Exception as e:
            logger.error(f"Publish telemetry unknown error: {e}", exc_info=True)
            return False

    def publish_flatness_data_event(self, event_data: dict) -> bool:
        """上报平面度事件消息"""
        if not self._is_connected():
            logger.error("MQTT client not connected, skip event publish")
            return False
            
        try:
            standard_payload = {
                "messageId": str(uuid.uuid4()),
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": event_data
            }
            payload_json = json.dumps(standard_payload, ensure_ascii=False)
            topic = MQTT_EVENT_TOPIC_FORMAT.format(event_id='flatness_data')

            logger.info(f"Event topic: {topic}, payload: {payload_json}")
            pub_result = self._client.publish(topic, payload_json, qos=1)
            pub_result.wait_for_publish(timeout=3)

            logger.info(f"Publish result rc={pub_result.rc}, mid={pub_result.mid}")
            if pub_result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Flatness event queued success, mid={pub_result.mid}")
                return True
            else:
                logger.error(f"Flatness event publish failed, rc={pub_result.rc}")
                return False
        except (TypeError, ValueError) as e:
            logger.error(f"Serialize event json error: {e}, data={event_data}")
            return False
        except Exception as e:
            logger.error(f"Publish flatness event unknown error: {e}", exc_info=True)
            return False

    def _is_connected(self) -> bool:
        """检查连接状态"""
        return self._client is not None and self._connected

    @property
    def is_connected(self) -> bool:
        return self._connected