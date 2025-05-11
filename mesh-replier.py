#!/usr/bin/python3
import time
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import datetime
import binascii
import logging
import sys
from logging.handlers import RotatingFileHandler

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
        logger.info(f"{timestamp} Relayed packet received. From {pFrom:x} ({from_long_name}/{from_short_name}) to {pTo:x}, relayNode: {relay_node} (0x{relay_node:x}){signal_info}")
        relay_info = f"relayed via {relay_node:x}"

    # Handle telemetry packets
    portnum = packet['decoded'].get('portnum', 'UNKNOWN')
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

    # Handle all text message packets
    if portnum == 'TEXT_MESSAGE_APP':
        text = packet['decoded'].get('text', '')
        channel = packet.get('channel', 'N/A')
        logger.info(f"Text message from {pFrom:x} ({from_long_name}/{from_short_name}) to {pTo:x} on channel {channel}: {text}")

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
                interface.sendText(msg, destinationId=pFrom, wantAck=True, wantResponse=False)
            except Exception as e:
                logger.error(f"Failed to send pong: {e}")
        else:
            logger.info(f"Packet is not ping packet, payload: {packet['decoded']['text'] if portnum == 'TEXT_MESSAGE_APP' else payload}, ignoring")

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
    exit(1)

try:
    while True:
        time.sleep(1)  # Keep the script running with a shorter sleep
except KeyboardInterrupt:
    logger.info("Shutting down...")
    interface.close()  # Close the interface only on exit
