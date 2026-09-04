"""Dynamic channel management and permission filtering."""

import json
import os
from config import PERMITTED_SERVER_IDS, PERMITTED_CHANNEL_IDS

CHANNELS_FILE: str = "channels.json"

def load_channels() -> dict[str, list[int]]:
    """Loads configured channels per guild from channels.json."""
    if os.path.exists(CHANNELS_FILE):
        try:
            with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[RengoBot] Error loading {CHANNELS_FILE}: {e}")
    return {}

def save_channels(data: dict[str, list[int]]) -> None:
    """Saves configured channels per guild to channels.json."""
    try:
        with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[RengoBot] Error saving {CHANNELS_FILE}: {e}")

def is_channel_enabled(guild_id: int, channel_id: int) -> bool:
    """Checks if a channel is enabled in channels.json or PERMITTED_CHANNEL_IDS."""
    if channel_id in PERMITTED_CHANNEL_IDS:
        return True
    data = load_channels()
    guild_channels = data.get(str(guild_id), [])
    return channel_id in guild_channels

def is_permitted(ctx) -> bool:
    """Determines if the bot is permitted to respond in the context's guild and channel."""
    if not ctx.guild:
        return False
    if PERMITTED_SERVER_IDS and ctx.guild.id not in PERMITTED_SERVER_IDS:
        return False
    return is_channel_enabled(ctx.guild.id, ctx.channel.id)

def enable_channel(guild_id: int, channel_id: int) -> bool:
    """Enables RengoBot for a channel in the specified guild. Returns False if already enabled."""
    if channel_id in PERMITTED_CHANNEL_IDS:
        return False
    data = load_channels()
    g_key = str(guild_id)
    ch_list = data.get(g_key, [])
    if channel_id in ch_list:
        return False
    ch_list.append(channel_id)
    data[g_key] = ch_list
    save_channels(data)
    return True

def disable_channel(guild_id: int, channel_id: int) -> bool:
    """Disables RengoBot for a channel in the specified guild. Returns True if removed."""
    data = load_channels()
    g_key = str(guild_id)
    ch_list = data.get(g_key, [])
    if channel_id in ch_list:
        ch_list.remove(channel_id)
        data[g_key] = ch_list
        save_channels(data)
        return True
    return False

def get_active_channels_for_guild(guild) -> list[int]:
    """Returns a sorted list of all active channel IDs for the given guild."""
    data = load_channels()
    g_key = str(guild.id)
    ch_set = set(data.get(g_key, []))

    for cid in PERMITTED_CHANNEL_IDS:
        if guild.get_channel(cid):
            ch_set.add(cid)

    return sorted(ch_set)
