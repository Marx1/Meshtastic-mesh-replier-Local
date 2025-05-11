#!/usr/bin/python3
import time
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import datetime
import binascii

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
    #print(f"{timestamp} received: {packet}")
   
    pFrom = packet['from']
    pTo = packet['to']
    
    # Get node names
    from_long_name, from_short_name = get_node_names(interface, pFrom)
    
    # Check if packet was received directly or relayed
    hop_start = packet.get('hopStart', 0)
    hop_limit = packet.get('hopLimit', 0)
    relay_node = packet.get('relayNode', 0)
    
    # Prepare SNR and RSSI if both exist
    signal_info = ""
    if 'rxSnr' in packet and 'rxRssi' in packet:
        signal_info = f", SNR: {packet['rxSnr']} dB, RSSI: {packet['rxRssi']} dBm"
    
    if hop_start == hop_limit and pFrom != interface.myInfo.my_node_num:
        print(f"{timestamp} Direct packet received. From {pFrom:x} ({from_long_name}/{from_short_name}) to {pTo:x}, relayNode: {relay_node} (0x{relay_node:x}){signal_info}")
        relay_info = "direct"
    else:
        print(f"{timestamp} Relayed packet received. From {pFrom:x} ({from_long_name}/{from_short_name}) to {pTo:x}, relayNode: {relay_node} (0x{relay_node:x}){signal_info}")
        relay_info = f"relayed via {relay_node:x}"

    # Handle telemetry packets
    portnum = packet['decoded'].get('portnum', 'UNKNOWN')
    if portnum == 'TELEMETRY_APP':
        telemetry = packet['decoded'].get('telemetry', {})
        
        # Handle deviceMetrics (battery, voltage, etc.)
        device_metrics = telemetry.get('deviceMetrics', {})
        if device_metrics:
            print(f"Telemetry (Device Metrics) from {pFrom:x} ({from_long_name}/{from_short_name}):")
            print(f"  Battery Level: {device_metrics.get('batteryLevel', 'N/A')} %")
            print(f"  Voltage: {device_metrics.get('voltage', 'N/A')} V")
            channel_util = device_metrics.get('channelUtilization', 'N/A')
            air_util = device_metrics.get('airUtilTx', 'N/A')
            print(f"  Channel Utilization: {channel_util:.2f} %" if isinstance(channel_util, (int, float)) else f"  Channel Utilization: {channel_util} %")
            print(f"  Air Utilization TX: {air_util:.2f} %" if isinstance(air_util, (int, float)) else f"  Air Utilization TX: {air_util} %")
            uptime_seconds = device_metrics.get('uptimeSeconds', 'N/A')
            uptime_hours = uptime_seconds / 3600 if isinstance(uptime_seconds, (int, float)) else 'N/A'
            print(f"  Uptime: {uptime_seconds} seconds ({uptime_hours:.2f} hours)" if isinstance(uptime_seconds, (int, float)) else f"  Uptime: {uptime_seconds}")
        
        # Handle localStats (network statistics)
        local_stats = telemetry.get('localStats', {})
        if local_stats:
            print(f"Telemetry (Local Stats) from {pFrom:x} ({from_long_name}/{from_short_name}):")
            uptime_seconds = local_stats.get('uptimeSeconds', 'N/A')
            uptime_hours = uptime_seconds / 3600 if isinstance(uptime_seconds, (int, float)) else 'N/A'
            print(f"  Uptime: {uptime_seconds} seconds ({uptime_hours:.2f} hours)" if isinstance(uptime_seconds, (int, float)) else f"  Uptime: {uptime_seconds}")
            channel_util = local_stats.get('channelUtilization', 'N/A')
            air_util = local_stats.get('airUtilTx', 'N/A')
            print(f"  Channel Utilization: {channel_util:.2f} %" if isinstance(channel_util, (int, float)) else f"  Channel Utilization: {channel_util} %")
            print(f"  Air Utilization TX: {air_util:.2f} %" if isinstance(air_util, (int, float)) else f"  Air Utilization TX: {air_util} %")
            print(f"  Packets TX: {local_stats.get('numPacketsTx', 'N/A')}")
            print(f"  Packets RX: {local_stats.get('numPacketsRx', 'N/A')}")
            print(f"  Packets RX Bad: {local_stats.get('numPacketsRxBad', 'N/A')}")
            print(f"  Online Nodes: {local_stats.get('numOnlineNodes', 'N/A')}")
            print(f"  Total Nodes: {local_stats.get('numTotalNodes', 'N/A')}")
            print(f"  RX Duplicates: {local_stats.get('numRxDupe', 'N/A')}")
            print(f"  TX Relay: {local_stats.get('numTxRelay', 'N/A')}")
            print(f"  TX Relay Canceled: {local_stats.get('numTxRelayCanceled', 'N/A')}")
        
        if not device_metrics and not local_stats:
            print(f"Telemetry from {pFrom:x} ({from_long_name}/{from_short_name}): No device metrics or local stats available")
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
        
        print(f"Position report from {pFrom:x} ({from_long_name}/{from_short_name}):")
        print(f"  Latitude: {latitude} degrees" if isinstance(latitude, (int, float)) else f"  Latitude: {latitude}")
        print(f"  Longitude: {longitude} degrees" if isinstance(longitude, (int, float)) else f"  Longitude: {longitude}")
        print(f"  Altitude: {altitude} meters" if isinstance(altitude, (int, float)) else f"  Altitude: {altitude}")
        print(f"  Time: {time_formatted}")
        print(f"  Ground Speed: {ground_speed} m/s" if isinstance(ground_speed, (int, float)) else f"  Ground Speed: {ground_speed}")
        print(f"  Ground Track: {ground_track:.2f} degrees" if isinstance(ground_track, (int, float)) else f"  Ground Track: {ground_track}")
        print(f"  Satellites in View: {sats_in_view}")
        print(f"  PDOP: {pdop:.2f}" if isinstance(pdop, (int, float)) else f"  PDOP: {pdop}")
        print(f"  Precision: {precision_text}")
        print(f"  Location Source: {location_source}")
        return  # Skip further processing for position packets

    # Handle all text message packets
    if portnum == 'TEXT_MESSAGE_APP':
        text = packet['decoded'].get('text', '')
        channel = packet.get('channel', 'N/A')
        print(f"Text message from {pFrom:x} ({from_long_name}/{from_short_name}) to {pTo:x} on channel {channel}: {text}")

    # Handle text message packets addressed to this node
    if pTo == interface.myInfo.my_node_num:
        print(f"Packet is for me! It's from {pFrom:x} ({from_long_name}/{from_short_name})")
        # Decode payload and check portnum
        payload = packet['decoded'].get('payload', b'')
        print(f"Portnum: {portnum}, Payload (hex): {binascii.hexlify(payload).decode()}")
        
        # Check for ping (case-sensitive by default)
        if portnum == 'TEXT_MESSAGE_APP' and payload == b'ping':  # Use b'ping' for byte string comparison
            # Format timestamp to show only seconds
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            msg = f"pong {timestamp}. rxSNR {packet['rxSnr']} dB RSSI {packet['rxRssi']} dBm ({relay_info})"
            print(f"It's a ping packet. Replying with {msg}")
            interface.sendText(msg, destinationId=pFrom, wantAck=True, wantResponse=False)
        else:
            print(f"Packet is not ping packet, payload: {packet['decoded']['text'] if portnum == 'TEXT_MESSAGE_APP' else payload}, ignoring")

def onConnection(interface, topic=pub.AUTO_TOPIC):  # called when connection is established
    print(f"Connected to radio. My node ID: {interface.myInfo.my_node_num} (0x{interface.myInfo.my_node_num:x})")
    print("Waiting for messages")

# Subscribe to connection and receive events
pub.subscribe(onReceive, "meshtastic.receive")
pub.subscribe(onConnection, "meshtastic.connection.established")

# Initialize serial interface
try:
    interface = meshtastic.serial_interface.SerialInterface(devPath='/dev/ttyUSB0')
except Exception as e:
    print(f"Failed to connect to radio: {e}")
    exit(1)

try:
    while True:
        time.sleep(1)  # Keep the script running with a shorter sleep
except KeyboardInterrupt:
    print("Shutting down...")
    interface.close()  # Close the interface only on exit
