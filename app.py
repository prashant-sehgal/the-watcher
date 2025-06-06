import atexit
import json
import signal
import sys
import threading
from collections import OrderedDict

import netifaces
from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory, Response
from flask_socketio import SocketIO
from scapy.all import sniff
from flask_cors import CORS


from ids import run_suricata_live, stop_suricata_live, tail_alerts
from databse import  DATABASE

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_folder='public')
app.config['JSON_SORT_KEYS'] = False
CORS(app)  # This enables CORS for all routes and origins
# app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
socketio = SocketIO(app, cors_allowed_origins='*')



def get_default_interface():
    # Get default network interface
    gateways = netifaces.gateways()
    default_gateway = gateways.get('default')
    if default_gateway and netifaces.AF_INET in default_gateway:
        return default_gateway[netifaces.AF_INET][1]
    return None


def handle_received_packet(packet):
    socketio.emit('packet:received', packet.summary())


def start_sniffing(interface=None):
    # Start packet sniffing
    if interface is None:
        interface = get_default_interface()
    if not interface:
        print("[ERROR] No default network interface found!")
        return
    print(f"[INFO] Capturing packets on: {interface}")
    sniff(iface=interface, prn=handle_received_packet, store=False)


@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route("/api/dashboard", methods=["GET"])
def get_dash():
    db = DATABASE()
    logs = db.get_dashboard_data()
    # Assuming logs['timestamp'] is a dictionary, convert it to an OrderedDict
    # if you want to ensure the insertion order is kept.
    ordered_timestamp = OrderedDict(logs['timestamp'])

    # Directly assign the OrderedDict to the logs so it remains as an object when serialized.
    logs['timestamp'] = ordered_timestamp

    # Use json.dumps with sort_keys=False to prevent any reordering,
    # then return a Response with application/json mimetype.
    response_json = json.dumps({"status": "success", "Data": logs}, sort_keys=False)
    return Response(response=response_json, status=200, mimetype='application/json')

@app.route("/api/analytics", methods=["GET"])
def ana_data():
    db = DATABASE()
    logs = db.get_logs_data()
    return jsonify({'status': "success", "data": logs}), 200

def on_start():
    sniff_thread = threading.Thread(target=start_sniffing, daemon=True)
    sniff_thread.start()
    run_ids = threading.Thread(target=run_suricata_live, daemon=True)
    run_ids.start()
    tail_alert = threading.Thread(target=tail_alerts, daemon=True)
    tail_alert.start()



def on_exit():
    print("Flask app is closing...")
    stop_suricata_live()



# Register the exit function using at exit.
atexit.register(on_exit)


# Alternatively, handle termination signals:
def signal_handler(sig, frame):
    print("Signal received, closing Flask app...")
    stop_suricata_live()

    sys.exit(0)  # Exiting will trigger the at exit functions


# Register the signal handlers for SIGINT and SIGTERM.
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    # Run Flask app
    on_start()
    app.run(host="0.0.0.0", port=5000,debug=True)