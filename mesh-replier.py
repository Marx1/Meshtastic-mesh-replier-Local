#!/usr/bin/python3

#Hevily modified version https://github.com/OH1KK/Meshtastic-mesh-replier/
#Modified by KG6MDW https://github.com/Marx1/Meshtastic-mesh-replier-Local/

import time
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import datetime
import binascii
import logging
import sys
from logging.handlers import RotatingFileHandler
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingTCPServer
import threading
import urllib.parse
import socket
import os
import errno

# Precision bits to uncertainty mapping
PRECISION_BITS_MAP = {
    10: {"metric": "23.3 km", "imperial": "14.5 miles"},
    11: {"metric": "11.7 km", "imperial": "7.3 miles"},
    12: {"metric": "5.8 km", "imperial": "3.6 miles"},
    13: {"metric": "2.9 km", "imperial": "1.8 miles"},
    14: {"metric": "1.5 km", "imperial": "4787 feet"},
    15: {"metric": "729 m", "imperial": "2392 feet"},
    16: {"metric": "364 m", "imperial": "1194 feet"},
    17: {"metric": "182 m", "imperial": "597 feet"},
    18: {"metric": "91 m", "imperial": "299 feet"},
    19: {"metric": "45 m", "imperial": "148 feet"}
}

#Database (simple text file) of nodes we've messaged.
nodelist = []
open("messagednodes.txt", "a").close()
with open("messagednodes.txt", "r") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                nodelist.append(int(line))
            except ValueError:
                pass  # skip lines that aren't valid integers

# Configure logging
logger = logging.getLogger('MeshReplier')
logger.setLevel(logging.INFO)

# Remove existing handlers to prevent duplication
logger.handlers = []

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)

# File handler for /tmp/mesh-replier.log
file_handler = RotatingFileHandler('/tmp/mesh-replier.log', maxBytes=10*1024*1024, backupCount=5)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Disable propagation to prevent Meshtastic's logger from duplicating output
logger.propagate = False

# Configure Meshtastic's logger to avoid console output
meshtastic_logger = logging.getLogger('meshtastic')
meshtastic_logger.handlers = []  # Remove any existing handlers
meshtastic_logger.propagate = False  # Prevent propagation to root logger
meshtastic_logger.addHandler(logging.NullHandler())  # Suppress output

# Global Meshtastic interface (to be initialized later)
interface = None
'''
class CustomThreadingTCPServer(ThreadingTCPServer):
    """Custom ThreadingTCPServer for IPv6 binding."""
    def __init__(self, server_address, RequestHandlerClass):
        self.address_family = socket.AF_INET6
        try:
            # Initialize parent class first
            super().__init__(server_address, RequestHandlerClass)
            self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            logger.info(f"Binding to {server_address}")
            self.socket.bind(server_address)
            self.socket.listen(5)
            logger.info(f"Successfully bound to {server_address}")
        except socket.gaierror as e:
            logger.error(f"Socket binding failed (gaierror): {e}")
            self.socket.close()
            raise
        except socket.error as e:
            logger.error(f"Socket error during setup: {e}")
            self.socket.close()
            raise
        except Exception as e:
            logger.error(f"Unexpected error during socket setup: {e}")
            self.socket.close()
            raise

    def server_close(self):
        """Ensure socket is properly closed."""
        try:
            self.socket.close()
            logger.info("Server socket closed")
        except Exception as e:
            logger.error(f"Error closing server socket: {e}")

def run_http_server():
    """Run the HTTP server on port 8080 with IPv6 support."""
    port = 8080
    server_address = ('::', port)
    
    # Log network configuration for debugging
    try:
        logger.info("Network interfaces:")
        for line in os.popen("ip addr").readlines():
            logger.info(line.strip())
        logger.info("IPv6 status:")
        for line in os.popen("sysctl net.ipv6.conf.all.disable_ipv6 net.ipv6.bindv6only").readlines():
            logger.info(line.strip())
        logger.info("Port 8080 status:")
        for line in os.popen("netstat -tulnp | grep 8080").readlines():
            logger.info(line.strip())
    except Exception as e:
        logger.error(f"Failed to log network configuration: {e}")

    # Attempt to bind to :: on port 8080
    try:
        httpd = CustomThreadingTCPServer(server_address, MeshHTTPRequestHandler)
        logger.info(f"Starting HTTP server on {server_address[0]}:{port} (IPv6)")
        httpd.serve_forever()
    except socket.error as e:
        if e.errno == errno.EADDRINUSE:
            logger.error(f"Port {port} is already in use. Checking processes...")
            os.system("netstat -tulnp | grep 8080")
            logger.error("Please free port 8080 or choose a different port.")
        logger.error(f"Failed to bind to {server_address[0]}:{port}: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")
        sys.exit(1)

class MeshHTTPRequestHandler(BaseHTTPRequestHandler):
    """Handle HTTP GET requests to send Meshtastic messages."""
    def do_GET(self):
        global interface
        try:
            # Parse the URL and query parameters
            parsed_url = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_url.query)

            # Extract ch_index, dest, and sendtext
            ch_index = query_params.get('ch_index', [None])[0]
            dest = query_params.get('dest', [None])[0]
            sendtext = query_params.get('sendtext', [''])[0]

            logger.info(f"Received HTTP request: path={self.path}, ch_index={ch_index}, dest={dest}, sendtext={sendtext}")

            # Validate request
            if not interface:
                logger.error("Meshtastic interface not initialized")
                self.send_error(500, "Meshtastic interface not initialized")
                return
            if not sendtext:
                logger.error("No sendtext provided")
                self.send_error(400, "Missing sendtext parameter")
                return
            if not (ch_index or dest):
                logger.error("Neither ch_index nor dest provided")
                self.send_error(400, "Must provide ch_index or dest")
                return

            # Send Meshtastic message
            try:
                if ch_index:
                    ch_index = int(ch_index)  # Convert to integer
                    interface.sendText(sendtext, channelIndex=ch_index, wantAck=True)
                    logger.info(f"Sent message to channel {ch_index}: {sendtext}")
                else:
                    # Convert dest hex string to integer
                    dest_id = int(dest, 16)
                    interface.sendText(sendtext, destinationId=dest_id, wantAck=True)
                    logger.info(f"Sent message to node {dest}: {sendtext}")

                # Send HTTP response
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Message sent successfully")
            except ValueError as e:
                logger.error(f"Invalid ch_index or dest: {e}")
                self.send_error(400, f"Invalid ch_index or dest: {e}")
            except Exception as e:
                logger.error(f"Failed to send Meshtastic message: {e}")
                self.send_error(500, f"Failed to send message: {e}")

        except Exception as e:
            logger.error(f"Error processing HTTP request: {e}")
            self.send_error(500, f"Internal server error: {e}")
'''
def get_node_names(interface, node_id):
    """Retrieve longName and shortName from NodeDB for a given node ID (integer)."""
    node = interface.nodes.get(f"!{node_id:08x}", None)
    if node and 'user' in node:
        long_name = node['user'].get('longName', 'Unknown')
        short_name = node['user'].get('shortName', 'UNK')
        return long_name, short_name
    hex_id = f"{node_id:08x}"[-4:]
    return f"Meshtastic {hex_id}", hex_id

def onReceive(packet, interface):  # called when a packet arrives
    global nodelist
    now = datetime.datetime.now()
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    #logger.info(f"{timestamp} received: {packet}")
   
    pFrom = packet['from']
    pTo = packet['to']
    
    # Get node names
    try:
        from_long_name, from_short_name = get_node_names(interface, pFrom)
    except Exception as e:
        logger.error(f"Error getting node names for {pFrom:x}: {e}")
        from_long_name, from_short_name = f"Unknown_{pFrom:x}", f"UNK_{pFrom:x}"
    
    # Check if packet was received directly or relayed
    hop_start = packet.get('hopStart', 0)
    hop_limit = packet.get('hopLimit', 0)
    relay_node = packet.get('relayNode', 0)
    
    # Prepare SNR and RSSI if both exist
    signal_info = ""
    if 'rxSnr' in packet and 'rxRssi' in packet:
        signal_info = f", SNR: {packet['rxSnr']} dB, RSSI: {packet['rxRssi']} dBm"
    
    if hop_start == hop_limit and pFrom != interface.myInfo.my_node_num:
        logger.info(f"{timestamp} Direct packet received. From {pFrom:x} ({from_long_name}/{from_short_name}) to {pTo:x}, relayNode: {relay_node} (0x{relay_node:x}){signal_info}")
        relay_info = "direct"
    else:
        #logger.info(f"{timestamp} Relayed packet received. From {pFrom:x} ({from_long_name}/{from_short_name}) to {pTo:x}, relayNode: {relay_node} (0x{relay_node:x}){signal_info}")
        relay_info = f"relayed via {relay_node:x}"

    # Handle telemetry packets
    portnum = packet['decoded'].get('portnum', 'UNKNOWN')

    '''
    if portnum == 'TELEMETRY_APP':
        telemetry = packet['decoded'].get('telemetry', {})
        
        # Handle deviceMetrics (battery, voltage, etc.)
        device_metrics = telemetry.get('deviceMetrics', {})
        if device_metrics:
            logger.info(f"Telemetry (Device Metrics) from {pFrom:x} ({from_long_name}/{from_short_name}):")
            logger.info(f"  Battery Level: {device_metrics.get('batteryLevel', 'N/A')} %")
            logger.info(f"  Voltage: {device_metrics.get('voltage', 'N/A')} V")
            channel_util = device_metrics.get('channelUtilization', 'N/A')
            air_util = device_metrics.get('airUtilTx', 'N/A')
            logger.info(f"  Channel Utilization: {channel_util:.2f} %" if isinstance(channel_util, (int, float)) else f"  Channel Utilization: {channel_util} %")
            logger.info(f"  Air Utilization TX: {air_util:.2f} %" if isinstance(air_util, (int, float)) else f"  Air Utilization TX: {air_util} %")
            uptime_seconds = device_metrics.get('uptimeSeconds', 'N/A')
            uptime_hours = uptime_seconds / 3600 if isinstance(uptime_seconds, (int, float)) else 'N/A'
            logger.info(f"  Uptime: {uptime_seconds} seconds ({uptime_hours:.2f} hours)" if isinstance(uptime_seconds, (int, float)) else f"  Uptime: {uptime_seconds}")
        
        # Handle localStats (network statistics)
        local_stats = telemetry.get('localStats', {})
        if local_stats:
            logger.info(f"Telemetry (Local Stats) from {pFrom:x} ({from_long_name}/{from_short_name}):")
            uptime_seconds = local_stats.get('uptimeSeconds', 'N/A')
            uptime_hours = uptime_seconds / 3600 if isinstance(uptime_seconds, (int, float)) else 'N/A'
            logger.info(f"  Uptime: {uptime_seconds} seconds ({uptime_hours:.2f} hours)" if isinstance(uptime_seconds, (int, float)) else f"  Uptime: {uptime_seconds}")
            channel_util = local_stats.get('channelUtilization', 'N/A')
            air_util = local_stats.get('airUtilTx', 'N/A')
            logger.info(f"  Channel Utilization: {channel_util:.2f} %" if isinstance(channel_util, (int, float)) else f"  Channel Utilization: {channel_util} %")
            logger.info(f"  Air Utilization TX: {air_util:.2f} %" if isinstance(air_util, (int, float)) else f"  Air Utilization TX: {air_util} %")
            logger.info(f"  Packets TX: {local_stats.get('numPacketsTx', 'N/A')}")
            logger.info(f"  Packets RX: {local_stats.get('numPacketsRx', 'N/A')}")
            logger.info(f"  Packets RX Bad: {local_stats.get('numPacketsRxBad', 'N/A')}")
            logger.info(f"  Online Nodes: {local_stats.get('numOnlineNodes', 'N/A')}")
            logger.info(f"  Total Nodes: {local_stats.get('numTotalNodes', 'N/A')}")
            logger.info(f"  RX Duplicates: {local_stats.get('numRxDupe', 'N/A')}")
            logger.info(f"  TX Relay: {local_stats.get('numTxRelay', 'N/A')}")
            logger.info(f"  TX Relay Canceled: {local_stats.get('numTxRelayCanceled', 'N/A')}")
        
        if not device_metrics and not local_stats:
            logger.info(f"Telemetry from {pFrom:x} ({from_long_name}/{from_short_name}): No device metrics or local stats available")
        return  # Skip further processing for telemetry packets

    # Handle position packets
    if portnum == 'POSITION_APP':
        position = packet['decoded'].get('position', {})
        latitude = position.get('latitudeI', 0) * 1e-7 if position.get('latitudeI') else 'N/A'
        longitude = position.get('longitudeI', 0) * 1e-7 if position.get('longitudeI') else 'N/A'
        altitude = position.get('altitude', 'N/A')
        time_unix = position.get('time', 0)
        time_formatted = datetime.datetime.fromtimestamp(time_unix).strftime('%Y-%m-%d %H:%M:%S') if time_unix > 0 else 'N/A'
        ground_speed = position.get('groundSpeed', 'N/A')
        ground_track = position.get('groundTrack', 0) * 1e-5 if 'groundTrack' in position else 'N/A'
        sats_in_view = position.get('satsInView', 'N/A')
        pdop = position.get('PDOP', 0) * 0.01 if 'PDOP' in position else 'N/A'
        precision_bits = position.get('precisionBits', 'N/A')
        location_source = position.get('locationSource', 'N/A')
        # Get precision uncertainty
        precision_info = PRECISION_BITS_MAP.get(precision_bits, {"metric": "N/A", "imperial": "N/A"}) if isinstance(precision_bits, int) else {"metric": "N/A", "imperial": "N/A"}
        precision_text = f"±{precision_info['metric']} (±{precision_info['imperial']}) for {precision_bits} bits" if precision_info['metric'] != "N/A" else "N/A"
        
        logger.info(f"Position report from {pFrom:x} ({from_long_name}/{from_short_name}):")
        logger.info(f"  Latitude: {latitude} degrees" if isinstance(latitude, (int, float)) else f"  Latitude: {latitude}")
        logger.info(f"  Longitude: {longitude} degrees" if isinstance(longitude, (int, float)) else f"  Longitude: {longitude}")
        logger.info(f"  Altitude: {altitude} meters" if isinstance(altitude, (int, float)) else f"  Altitude: {altitude}")
        logger.info(f"  Time: {time_formatted}")
        logger.info(f"  Ground Speed: {ground_speed} m/s" if isinstance(ground_speed, (int, float)) else f"  Ground Speed: {ground_speed}")
        logger.info(f"  Ground Track: {ground_track:.2f} degrees" if isinstance(ground_track, (int, float)) else f"  Ground Track: {ground_track}")
        logger.info(f"  Satellites in View: {sats_in_view}")
        logger.info(f"  PDOP: {pdop:.2f}" if isinstance(pdop, (int, float)) else f"  PDOP: {pdop}")
        logger.info(f"  Precision: {precision_text}")
        logger.info(f"  Location Source: {location_source}")
        return  # Skip further processing for position packets
'''
    # Handle all text message packets
    if portnum == 'TEXT_MESSAGE_APP':
        text = packet['decoded'].get('text', '')
        channel = packet.get('channel', 'N/A')
        
        logger.info(f"Text message from {pFrom:x} ({from_long_name}/{from_short_name}) to {pTo:x} on channel {channel}: {text}")
        print(f"Relayinfo: {relay_info}")

        if pTo == interface.myInfo.my_node_num:
            print(text.strip().lower())
            if text.strip().lower() == "ping":  # Use b'ping' for byte string comparison
                # Format timestamp to show only seconds
                timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
                msg = f"pong {timestamp}. rxSNR {packet['rxSnr']} dB RSSI {packet['rxRssi']} dBm ({relay_info})"
                logger.info(f"It's a ping packet. Replying with {msg}")
                try:
                    interface.sendText(msg, destinationId=pFrom, wantAck=True, wantResponse=True, channelIndex=0)
                except Exception as e:
                    logger.error(f"Failed to send pong: {e}")
                
            else:
                # Format timestamp to show only seconds
                timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
                msg = "I'm just a bot. If you need assitance contact Trevor KG6MDW on the BAYME.sh discord."
                logger.info(f"It's a some other message. Replying with canned responce")
                try:
                    interface.sendText(msg, destinationId=pFrom, wantAck=True, wantResponse=True, channelIndex=0)

                except Exception as e:
                    logger.error(f"Failed to send automessage: {e}")

        else:    
        # Do a responce if the node is not in the local DB.
            if pFrom not in nodelist and relay_info == "direct" : 
                #add it to the list
                nodelist.append(pFrom)
                with open("messagednodes.txt", "w") as f:
                    for node_id in nodelist:
                        f.write(f"{node_id}\n")

                logger.info(f"We heard a packet from a node not in our database. Replying with with automated message")
                msg = f"Hello, It looks like your at Pacificon. I saw a packet from you directly. We are using a special event settings at Pacificon, You can get them here: https://www.pacificon.org/events/meshtastic"
                try:
                    interface.sendText(msg, destinationId=pFrom, wantAck=True, wantResponse=True, channelIndex=0)

                except Exception as e:
                    logger.info(f"Failed to send message: {e}")

                msg = f"The rest of the SF Bay area uses Medium Slow. IF you would like to join our mesh after Pacificon, check us out at https://bayme.sh "
                try:
                    interface.sendText(msg, destinationId=pFrom, wantAck=True, wantResponse=True, channelIndex=0)

                except Exception as e:
                    logger.error(f"Failed to send message: {e}")
            else:
                logger.info(f"Not a 0-hop message or node already in database. Ignoring")

       
'''
    # Handle text message packets addressed to this node
    if pTo == interface.myInfo.my_node_num:
        logger.info(f"Packet is for me! It's from {pFrom:x} ({from_long_name}/{from_short_name})")
        # Decode payload and check portnum
        payload = packet['decoded'].get('payload', b'')
        logger.info(f"Portnum: {portnum}, Payload (hex): {binascii.hexlify(payload).decode()}")
        
        # Check for ping (case-sensitive by default)
        if portnum == 'TEXT_MESSAGE_APP' and payload == b'ping':  # Use b'ping' for byte string comparison
            # Format timestamp to show only seconds
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            msg = f"pong {timestamp}. rxSNR {packet['rxSnr']} dB RSSI {packet['rxRssi']} dBm ({relay_info})"
            logger.info(f"It's a ping packet. Replying with {msg}")
            try:
                result = interface.sendText(msg, destinationId=pFrom, wantAck=True, wantResponse=True, channelIndex=0)
                logger.info (result)
            except Exception as e:
                logger.error(f"Failed to send pong: {e}")
        else:
            # Format timestamp to show only seconds
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Packet is not direct message, payload: {packet['decoded']['text'] if portnum == 'TEXT_MESSAGE_APP' else payload}, ignoring")
'''
def onConnection(interface, topic=pub.AUTO_TOPIC):  # called when connection is established
    logger.info(f"Connected to radio. My node ID: {interface.myInfo.my_node_num} (0x{interface.myInfo.my_node_num:x})")
    logger.info("Waiting for messages")

# Subscribe to connection and receive events
pub.subscribe(onReceive, "meshtastic.receive")
pub.subscribe(onConnection, "meshtastic.connection.established")

# Initialize serial interface
try:
    interface = meshtastic.serial_interface.SerialInterface(devPath='/dev/ttyUSB0')
except Exception as e:
    logger.error(f"Failed to connect to radio: {e}")
    sys.exit(1)

# Start HTTP server in a separate thread
#http_thread = threading.Thread(target=run_http_server, daemon=True)
#http_thread.start()

try:
    while True:
        time.sleep(1)  # Keep the main thread running for Meshtastic events
except KeyboardInterrupt:
    logger.info("Shutting down...")
    interface.close()  # Close the Meshtastic interface
    sys.exit(0)