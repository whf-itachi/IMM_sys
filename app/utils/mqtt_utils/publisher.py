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
from collections import deque
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
        self._lock = threading.RLock()
        self._connect_attempts = 0
        self._reconnecting = False
        self._connecting = False  # 单次飞行：标记是否已有 connect 生命周期在运行中
        self._tls_insecure = True  # 是否关闭域名校验（自签证书开启True）
        self._shutting_down = False
        # 离线消息缓冲队列：断连期间的事件暂存于此，连接恢复后自动发送
        self._pending_queue: deque = deque(maxlen=500)
        self._pending_lock = threading.Lock()

    def _cleanup_client(self):
        """清理旧客户端：停止网络循环、断开socket"""
        if self._client is None:
            return
        old = self._client
        self._client = None
        try:
            old.loop_stop()
        except Exception:
            pass
        try:
            old.disconnect()
        except Exception:
            pass

    def connect(self):
        """Initialize and connect the MQTT client.

        注意：connect() 可能被多个线程并发进入（启动连接 main.py、后台重连线程
        reconnect_task、以及 paho 网络线程触发的回调）。self._client 是共享可变字段，
        必须在同一把锁内完成“清理旧连接 -> 创建新 client -> TLS 配置 -> connect -> loop_start”，
        否则会出现一个线程把 self._client 置 None、另一个线程正要对其做 tls_set 的竞态
        （AttributeError: 'NoneType' object has no attribute 'tls_set'）。
        """
        logger.info("Initializing MQTT connection to JetLinks...")
        if self._connected:
            logger.info("MQTT client is already connected.")
            return

        with self._lock:
            if self._connected:
                logger.info("MQTT client is already connected.")
                return
            # 单次飞行：已有 connect 生命周期在跑则直接跳过，避免并发竞态
            if self._connecting:
                logger.info("MQTT connect already in progress, skip concurrent call.")
                return
            self._connecting = True

            # 清理旧连接，防止 loop_start 线程泄漏。
            # 必须在锁内，与下方的“创建 client + TLS 配置 + connect + loop_start”构成原子段，
            # 其它线程无法在中间插入 _cleanup_client 把 self._client 置 None。
            self._cleanup_client()

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

                # TLS 配置（此时 self._client 一定非空：整个构建段在锁内，其它线程无法插入 _cleanup_client）
                if MQTT_USE_TLS:
                    logger.info("Enabling TLS for MQTT connection.")
                    if self._setup_tls():
                        logger.info(f"Certificate imported: {MQTT_CA_CERT_FILE}, hostname verification: {self._tls_insecure}")

                # 由自定义 _auto_reconnect() 统一管理重连，避免 paho 内部重连与自定义重连冲突
                # 不设置 reconnect_delay_set，以防产生双重重连链

                # 连接服务器（阻塞调用，仍在锁内；此时不会有其它线程同时操作 self._client）
                self._client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=MQTT_KEEP_ALIVE)
                logger.info(f"Connecting to MQTT broker at {MQTT_BROKER_HOST}:{MQTT_BROKER_PORT}...")

                # 启动网络循环
                self._client.loop_start()

            except Exception as e:
                self._connecting = False
                self._connected = False
                self._reconnecting = False
                self._cleanup_client()
                # 首次连接失败也自动重试（如开机时网络未就绪）
                self._auto_reconnect()
                logger.error(f"Error connecting to MQTT broker: {e}", exc_info=True)
                raise e

        # 等待连接结果：放在锁外，允许 paho 网络线程的 on_connect/on_disconnect 回调
        # （它们会获取同一把锁）正常执行，避免死锁。
        try:
            if not self._wait_for_connection():
                self._handle_connection_timeout()
        except Exception as e:
            self._connected = False
            self._reconnecting = False
            self._cleanup_client()
            self._auto_reconnect()
            logger.error(f"Error connecting to MQTT broker: {e}", exc_info=True)
            raise e
        finally:
            self._connecting = False

        logger.info("Successfully connected to JetLinks MQTT broker.")
        self._connect_attempts = 0

    def _setup_tls(self):
        """设置TLS连接参数"""
        # 防御性兜底：极端竞态下 self._client 可能为 None，避免抛 AttributeError 刷屏
        if self._client is None:
            logger.error("TLS setup skipped: MQTT client is None (possible concurrent reconnect race)")
            return False
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
        """连接超时处理

        connect() 第136行已发起一次阻塞式 CONNECT。若 15s 内未收到 CONNACK，
        说明本次握手未成功，直接抛异常交由外层 connect() 走后台指数退避重连即可，
        **不要**在此再同步调一次 self._client.reconnect()——否则每个重连周期会向 broker
        发两次 CONNECT（一次来自 connect()、一次来自这里的 reconnect()）：既翻倍请求量，
        又会制造“先 rc=4 被拒、同周期又 rc=0”的混乱日志（设备被后台禁用/鉴权被拒时尤明显）。
        """
        if self._shutting_down:
            logger.info("Shutting down, skip connection timeout handling.")
            return
        logger.warning(
            "Initial connection attempt timed out, delegating to background reconnect "
            "(no redundant manual reconnect)."
        )
        raise ConnectionError("Failed to connect to MQTT broker within timeout period.")

    def _auto_reconnect(self):
        """断线后台指数退避重连，独立线程执行"""
        if self._shutting_down or self._reconnecting or self._connected:
            return

        with self._lock:
            if self._shutting_down or self._reconnecting or self._connected:
                return
            self._reconnecting = True

        self._connect_attempts += 1

        # 指数退避封顶60秒，无限重连（MQTT本就应该持久连接）
        delay = min(2 * self._connect_attempts, 60)
        logger.info(f"Schedule background reconnect after {delay}s, attempt count={self._connect_attempts}")

        def reconnect_task():
            try:
                time.sleep(delay)
                if not self._connected and not self._shutting_down:
                    logger.info("Attempting to reconnect to MQTT broker...")
                    self.connect()
            except Exception as e:
                logger.error(f"Background reconnect task failed: {e}")
                self._cleanup_client()
            finally:
                need_retry = False
                with self._lock:
                    self._reconnecting = False
                    # connect() 内部调 _auto_reconnect 因 _reconnecting=True 被跳过，
                    # 所以在这里重置后补调度，保证重连链不断
                    if not self._connected and not self._shutting_down:
                        need_retry = True
                if need_retry:
                    self._auto_reconnect()

        threading.Thread(target=reconnect_task, daemon=True).start()

    def _on_log(self, level, buf):
        """MQTT底层日志回调"""
        logger.debug(f"MQTT internal log | lvl={level} msg={buf}")

    def disconnect(self):
        """安全断开连接，释放资源"""
        self._shutting_down = True
        self._connecting = False
        # 清空离线缓冲队列
        with self._pending_lock:
            count = len(self._pending_queue)
            self._pending_queue.clear()
            if count > 0:
                logger.info(f"关闭连接时清除 {count} 条缓冲消息")
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
            # 连接恢复后立即发送积压的离线消息
            self._flush_pending()
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

    def publish_event(self, event_name: str, event_data: dict) -> bool:
        """上报通用事件消息（非阻塞，断连时自动缓冲）"""
        try:
            standard_payload = {
                "messageId": str(uuid.uuid4()),
                "timestamp": int(datetime.now().timestamp() * 1000),
                "data": event_data
            }
            payload_json = json.dumps(standard_payload, ensure_ascii=False)
            topic = MQTT_EVENT_TOPIC_FORMAT.format(event_id=event_name)

            if not self._is_connected():
                # 断连时缓冲到队列，连接恢复后自动发送
                self._enqueue_pending(topic, payload_json, event_name)
                return False

            logger.info(f"Event topic: {topic}, payload: {payload_json}")
            pub_result = self._client.publish(topic, payload_json, qos=1)
            # 不调用 wait_for_publish，避免阻塞采集线程；
            # QoS 1 保证至少一次送达，paho 内部异步处理
            if pub_result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.debug(f"{event_name} event queued, mid={pub_result.mid}")
                return True
            else:
                logger.error(f"{event_name} event publish failed, rc={pub_result.rc}")
                self._enqueue_pending(topic, payload_json, event_name)
                return False
        except (TypeError, ValueError) as e:
            logger.error(f"Serialize {event_name} event json error: {e}, data={event_data}")
            return False
        except Exception as e:
            logger.error(f"Publish {event_name} event unknown error: {e}", exc_info=True)
            return False

    def _enqueue_pending(self, topic: str, payload: str, event_name: str):
        """将消息放入离线缓冲队列"""
        with self._pending_lock:
            if len(self._pending_queue) >= self._pending_queue.maxlen:
                # 队列满时丢弃最旧的消息
                self._pending_queue.popleft()
                logger.warning(f"离线缓冲队列已满，丢弃最旧的消息")
            self._pending_queue.append((topic, payload))
            logger.info(f"事件 {event_name} 已缓冲到离线队列 (队列长度: {len(self._pending_queue)})")

    def _flush_pending(self):
        """连接恢复后发送所有缓冲的消息"""
        with self._pending_lock:
            if not self._pending_queue:
                return
            count = len(self._pending_queue)
            logger.info(f"开始发送 {count} 条缓冲消息...")
            while self._pending_queue:
                topic, payload = self._pending_queue.popleft()
                try:
                    self._client.publish(topic, payload, qos=1)
                except Exception as e:
                    logger.error(f"发送缓冲消息失败: {e}")
                    # 发送失败放回队列头部，下次重试
                    self._pending_queue.appendleft((topic, payload))
                    break
            remaining = len(self._pending_queue)
            logger.info(f"缓冲消息发送完成，已发送 {count - remaining} 条，剩余 {remaining} 条")

    @property
    def pending_count(self) -> int:
        """获取待发送的缓冲消息数"""
        with self._pending_lock:
            return len(self._pending_queue)

    def _is_connected(self) -> bool:
        """检查连接状态（同时校验本地标志和 paho 内部状态）"""
        if self._client is None or not self._connected:
            return False
        # 双重校验：paho 内部可能状态已变但回调未及时触发
        try:
            if not self._client.is_connected():
                logger.debug("paho 内部状态显示已断开，本地 _connected 可能过期")
                self._connected = False
                return False
        except Exception:
            return False
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_status(self):
        """获取 MQTT 发布器完整状态"""
        return {
            "connected": self._connected,
            "is_really_connected": self._is_connected(),
            "reconnecting": self._reconnecting,
            "connect_attempts": self._connect_attempts,
            "pending_messages": self.pending_count,
            "shutting_down": self._shutting_down,
        }