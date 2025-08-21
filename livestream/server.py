from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import eventlet

eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, ping_interval=30, ping_timeout=120, cors_allowed_origins="*")
# Global dictionaries:
# devices: maps device names to their socket ids
devices = {}
# admin_sid: holds the admin's socket id (assume only one admin)
admin_sid = None

@app.route("/")
def admin():
    # Admin page where live device video (with two way audio) is viewed.
    return render_template("admin.html")

@app.route("/device")
def device():
    # Device page which streams its live video and audio.
    return render_template("device.html")

@app.route("/viewer")
def viewer():
    # Simple viewer page that connects to a specific device
    return render_template("viewer.html")


@socketio.on('check_device_status')
def handle_check_device_status(data):
    device_id = data.get('deviceId')
    if device_id:
        is_online = device_id in devices  # Check if the device exists in the registered list
        socketio.emit('device_status', {'deviceId': device_id, 'online': is_online}, room=request.sid)


@socketio.on('connect')
def handle_connect():
    print("Client connected:", request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    global admin_sid
    sid = request.sid
    if sid == admin_sid:
        print("Admin disconnected.")
        admin_sid = None
    else:
        disconnected_device = None
        for name, dsid in list(devices.items()):
            if dsid == sid:
                disconnected_device = name
                del devices[name]
                print(f"Device disconnected: {name}")
                break
        if disconnected_device and admin_sid:
            socketio.emit('update_device_list', list(devices.keys()), room=admin_sid)

@socketio.on('join_admin')
def handle_join_admin():
    global admin_sid
    admin_sid = request.sid
    join_room(admin_sid)
    print("Admin joined:", admin_sid)
    emit('update_device_list', list(devices.keys()))

@socketio.on('register_device')
def handle_register_device(data):
    device_name = data.get('device_name')
    if device_name:
        devices[device_name] = request.sid
        join_room(device_name)
        print(f"Device registered: {device_name} (sid: {request.sid})")
        if admin_sid:
            socketio.emit('update_device_list', list(devices.keys()), room=admin_sid)
    else:
        print("Device registration failed: no device name provided.")

# --- WebRTC Signaling Events ---
@socketio.on('webrtc_offer')
def handle_webrtc_offer(data):
    try:
        target = data.get('target')
        if target in devices:
            print(f"✅ Relaying offer from admin {data.get('from')} to device {target}")
            socketio.emit('webrtc_offer', data, room=devices[target])
        else:
            print(f"❌ Error: Device not found for offer: {target}")
    except Exception as e:
        print(f"❌ Exception in webrtc_offer: {e}")


@socketio.on('webrtc_answer')
def handle_webrtc_answer(data):
    try:
        target = data.get('target')
        print(f"✅ Relaying answer from device {data.get('from')} to admin {target}")
        socketio.emit('webrtc_answer', data, room=target)
    except Exception as e:
        print(f"❌ Exception in webrtc_answer: {e}")

@socketio.on('webrtc_candidate')
def handle_webrtc_candidate(data):
    try:
        target = data.get('target')
        print(f"✅ Relaying ICE candidate from {data.get('from')} to {target}")
        socketio.emit('webrtc_candidate', data, room=target)
    except Exception as e:
        print(f"❌ Exception in webrtc_candidate: {e}")



@socketio.on('switch_camera')
def handle_switch_camera(data):
    # data: { "target": "<device_name>", "from": "<admin_sid>" }
    target = data.get('target')
    if target in devices:
        print(f"Relaying switch_camera command to device {target}")
        socketio.emit('switch_camera', data, room=devices[target])
    else:
        print("Device not found for switch_camera:", target)
        
@socketio.on('request_device_list')
def handle_request_device_list():
    if request.sid == admin_sid:
        emit('update_device_list', list(devices.keys()), room=admin_sid)

@socketio.on('stop_streaming')
def handle_stop_streaming(data):
    target = data.get('target')
    admin_id = request.sid
    if target in devices:
        # Notify specific device to stop streaming to this admin
        socketio.emit('stop_streaming', {'from': admin_id}, room=devices[target])

@socketio.on('refresh_command')
def handle_refresh_command():
    if request.sid == admin_sid:
        print("🔄 Admin triggered refresh for all devices")
        for device_name, sid in devices.items():
            socketio.emit('refresh_device', {}, room=sid)
    else:
        print("❌ Non-admin tried to trigger refresh")

@app.route("/admin2")
def admin_new():
    return render_template("admin_new.html")

if __name__ == '__main__':
    # Listen on all interfaces so devices on your network (e.g. 192.168.2.151) can connect.
    socketio.run(app, host='0.0.0.0', port=8003, debug=True)
