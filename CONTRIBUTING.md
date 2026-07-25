# Development

This fork targets FIIO Air Link only. Do not add generic FIIO PEQ commands or other device drivers.

Read `docs/FIIO_AIR_LINK_HANDOFF.md` before changing the HID protocol. In particular:

- probe only interfaces with vendor `0x2972` and product `0x0158` using the safe firmware GET;
- keep all Air Link commands serialized and match responses by feature and command;
- verify writes with a property-specific readback;
- keep unverified and destructive commands disabled until hardware-tested.

Run `python -m unittest discover -s tests -v` before submitting changes. The
application must remain independent of Node.js, Electron, and WebHID.

Project code lives directly in `fiiocontrol/`; do not recreate a `src/` wrapper.
Keep BDUI renderer assets in `fiiocontrol/web/` so editable installs and packaged
builds use the same files.
