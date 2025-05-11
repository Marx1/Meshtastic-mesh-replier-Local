This is python bot for meshtastic. Used to measure signal strength.

Start this on your home node.

Then send 'ping' message from another node to your node.

If your node hears it, it replies

```
pong 2025-05-11 15:06:46. rxSNR 6.25 dB RSSI -63 dBm (direct)
```

and if packet is relayed then you see reply like

```
pong 2025-05-11 15:07:53. rxSNR 6.5 dB RSSI -30 dBm (relayed via 24)

```
