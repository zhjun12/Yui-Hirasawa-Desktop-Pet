"""Validate WinRT artwork byte extraction with an isolated in-memory stream."""
import asyncio
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from winrt.runtime import init_apartment,uninit_apartment,ApartmentType
from winrt.windows.storage.streams import InMemoryRandomAccessStream,DataWriter
from media_bridge import read_artwork


async def check():
    payload=b'isolated artwork byte test'
    stream=InMemoryRandomAccessStream()
    writer=DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(payload)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream();writer.close()
    class Reference:
        async def open_read_async(self): return stream
    assert await read_artwork(Reference())==payload
    print('PASS: native artwork stream extraction')


init_apartment(ApartmentType.MULTI_THREADED)
try: asyncio.run(check())
finally: uninit_apartment()
