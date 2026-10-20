import asyncio
import json
from pathlib import Path

async def main():
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
    manager = await Manager.request_async()
    results = []
    for session in manager.get_sessions():
        info = session.get_playback_info()
        controls = info.controls
        props = await session.try_get_media_properties_async()
        timeline = session.get_timeline_properties()
        results.append(dict(app=session.source_app_user_model_id,
            title=props.title, artist=props.artist, status=int(info.playback_status),
            can_play=controls.is_play_enabled, can_pause=controls.is_pause_enabled,
            can_next=controls.is_next_enabled, can_previous=controls.is_previous_enabled,
            can_seek=controls.is_playback_position_enabled,
            duration=timeline.end_time.total_seconds()))
    print(json.dumps(results, ensure_ascii=False, indent=2))

asyncio.run(main())
