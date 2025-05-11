This is python bot for meshtastic. Used to measure signal strength.

## Install


Start this on your home node.

```
git clone https://github.com/OH1KK/Meshtastic-mesh-replier.git
cd Meshtastic-mesh-replier
chmod +x mesh-replier.py
```

## Starting

```
./mesh-replier.py
```

You should see messages

```
Connected to radio. My node ID: 1129887680 (0x4358b7c0)
Waiting for messages
```

## Usage

Then send 'ping' message from another node to your node.

If your node hears it, it replies

```
pong 2025-05-11 15:06:46. rxSNR 6.25 dB RSSI -63 dBm (direct)
```

and if packet is relayed through another node then you see reply like

```
pong 2025-05-11 15:07:53. rxSNR 6.5 dB RSSI -30 dBm (relayed via 24)

```
