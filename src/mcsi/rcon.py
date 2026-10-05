"""A minimal Minecraft RCON client (https://minecraft.wiki/w/RCON).

Packets are: int32 length, int32 request id, int32 type, ASCII body, two NUL
bytes - all little-endian. Type 3 logs in, type 2 runs a command.
"""

import asyncio
import struct

LOGIN = 3
COMMAND = 2


class RconError(Exception):
    pass


async def _send(writer, request_id, kind, body):
    payload = struct.pack("<ii", request_id, kind) + body.encode() + b"\x00\x00"
    writer.write(struct.pack("<i", len(payload)) + payload)
    await writer.drain()


async def _receive(reader):
    (length,) = struct.unpack("<i", await reader.readexactly(4))
    data = await reader.readexactly(length)
    request_id, kind = struct.unpack("<ii", data[:8])
    return request_id, kind, data[8:-2].decode(errors="replace")


async def command(port, password, text, timeout=10):
    """Log in, run one command, return the server's reply text."""
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", port), timeout)
    try:
        await _send(writer, 1, LOGIN, password)
        request_id, _, _ = await asyncio.wait_for(_receive(reader), timeout)
        if request_id == -1:
            raise RconError("RCON login refused (wrong password)")
        await _send(writer, 2, COMMAND, text)
        _, _, reply = await asyncio.wait_for(_receive(reader), timeout)
        return reply
    finally:
        writer.close()
