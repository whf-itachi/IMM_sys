import json
import time
import hashlib
import ssl
from paho.mqtt import client as mqtt_client
from paho.mqtt.client import MQTTv311

# ======================== 【平台参数】 ========================
MQTT_BROKER = "haitch.tech"
MQTT_PORT = 8808  # 平台截图正确端口
PRODUCT_ID = "2062433954344341504"
DEVICE_ID = "202606049"
SECURE_ID = "admin"
SECURE_KEY = "JetLinks.C0mmVn1ty"
REPORT_INTERVAL = 5
# ============================================================================

REPORT_TOPIC = f"/{PRODUCT_ID}/{DEVICE_ID}/properties/report"

# 新版回调消除警告
def on_connect(client, userdata, flags, rc, props):
    if rc == 0:
        print("✅ 设备连接成功，平台显示在线！")
    else:
        print(f"❌ MQTT连接失败，错误码rc={rc}")
        # rc=4：时间戳偏差过大；rc=5：密钥不匹配

def on_message(client, userdata, msg):
    print(f"📩 平台下发指令 topic:{msg.topic} payload:{msg.payload.decode()}")

# 严格遵循平台MD5签名规则
def get_mqtt_auth():
    timestamp_ms = int(time.time() * 1000)
    username = f"{SECURE_ID}|{timestamp_ms}"
    raw_sign_str = f"{SECURE_ID}|{timestamp_ms}|{SECURE_KEY}"
    md5_pwd = hashlib.md5(raw_sign_str.encode("utf-8")).hexdigest()
    return username, md5_pwd

# 模拟传感器数据
def get_device_sensor_data():
    import random
    return {
        "temperature": round(random.uniform(20, 35), 1),
        "humidity": round(random.uniform(30, 70), 1),
        "cpu_load": random.randint(0, 100)
    }

if __name__ == "__main__":
    # 初始化MQTT客户端
    client = mqtt_client.Client(
        client_id=DEVICE_ID,
        protocol=MQTTv311,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2
    )
    client.on_connect = on_connect
    client.on_message = on_message

    # TLS配置：关闭证书校验，解决证书验证失败报错
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    print(f"🔒 已开启TLS加密，关闭证书校验，目标地址：{MQTT_BROKER}:{MQTT_PORT}")

    # 永久重连循环
    while True:
        try:
            uname, pwd = get_mqtt_auth()
            client.username_pw_set(uname, pwd)
            print(f"\n正在发起连接，当前时间戳毫秒：{int(time.time()*1000)}")
            client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            client.loop_start()

            # 定时上报数据
            while True:
                sensor_data = get_device_sensor_data()
                payload = json.dumps({
                    "deviceId": DEVICE_ID,
                    "properties": sensor_data
                })
                pub_result = client.publish(REPORT_TOPIC, payload)
                pub_result.wait_for_publish()
                if pub_result.rc != 0:
                    print(f"⚠️ 消息发送失败，错误码：{pub_result.rc}")
                else:
                    print(f"📤 上报数据: {sensor_data}")
                time.sleep(REPORT_INTERVAL)

        except Exception as e:
            print(f"\n⚠️ 连接异常，等待5秒后重连：{str(e)}")
            client.loop_stop()
            time.sleep(5)