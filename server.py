from flask import Flask, render_template, request, Response, jsonify
import cv2
import base64
import numpy as np
from flask_socketio import SocketIO
import time

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")  # Force WebSockets

# Store active streams {device_name: {"frame": frame_data, "last_update": timestamp}}
active_streams = {}

@app.route('/')
def admin_page():
    """Admin panel to view all streaming devices."""
    return render_template('admin.html', devices=active_streams.keys())

@app.route('/device')
def device_page():
    """Page for devices to start streaming."""
    return render_template('device.html')

@socketio.on('register')
def register_device(data):
    """Register a device for streaming."""
    device_name = data['name']
    active_streams[device_name] = {"frame": None, "last_update": time.time()}
    print(f"✅ Device registered: {device_name}")

@socketio.on('frame')
def receive_frame(data):
    """Receive frames from mobile devices."""
    device_name = data['name']
    frame_data = data['frame'].split(',')[1]  # Remove 'data:image/jpeg;base64,'

    try:
        frame = np.frombuffer(base64.b64decode(frame_data), np.uint8)
        frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)

        _, buffer = cv2.imencode('.jpg', frame)
        active_streams[device_name]["frame"] = buffer.tobytes()
        active_streams[device_name]["last_update"] = time.time()  # Update the timestamp

        print(f"✅ Received frame from {device_name} - Size: {len(frame_data)} bytes")  # Debug log
    except Exception as e:
        print(f"❌ Error decoding frame from {device_name}: {e}")

@app.route('/video_feed/<device_name>')
def video_feed(device_name):
    """Send video stream to admin panel."""
    def generate():
        while True:
            if device_name in active_streams and active_streams[device_name]["frame"]:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + active_streams[device_name]["frame"] + b'\r\n')

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/refresh_devices')
def refresh_devices():
    """Remove devices that have not sent data in the last 10 seconds."""
    global active_streams
    current_time = time.time()
    inactive_devices = [name for name, data in active_streams.items() if current_time - data["last_update"] > 10]
    
    for device in inactive_devices:
        del active_streams[device]
        print(f"❌ Removed inactive device: {device}")

    return jsonify({"devices": list(active_streams.keys())})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Use Railway's port
    socketio.run(app, host="0.0.0.0", port=port, debug=False)