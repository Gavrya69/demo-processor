import re
import math


def get_map_name_checksum(map_name):
    return sum(map_name.lower().encode("ascii", errors="ignore")) & 0xFF


def get_defrag_time(
    playerstate,
    snap_server_time,
    df_version,
    map_name_checksum,
    is_online=False,
    is_cheats_on=False,
):
    MASK32 = 0xFFFFFFFF
    
    def u32(value):
        return value & MASK32
    
    def shl32(value, bits):
        return (value << bits) & MASK32
    
    def shr32(value, bits):
        return (value & MASK32) >> bits
    
    stats = playerstate.get("stats", {})
    
    # C#:
    # int time = shl32(ps.stats[7], 0x10) | (ps.stats[8] & 0xffff);
    time = (
        shl32(stats.get("7", 0), 16)
        | (stats.get("8", 0) & 0xFFFF)
    )
    
    if time == 0:
        return 0, False
    
    # C#:
    # if ((client.isOnline && df_ver != 190) ||
    #     (df_ver >= 19112 && client.isCheatsOn))
    if (
        (is_online and df_version != 190)
        or
        (df_version >= 19112 and is_cheats_on)
    ):
        return time, False
    
    # time ^= abs(floor(origin[0])) & 0xffff
    origin_x = playerstate.get("origin[0]", 0.0)
    time ^= abs(math.floor(origin_x)) & 0xFFFF
    
    # time ^= abs(floor(velocity[0])) << 16
    velocity_x = playerstate.get("velocity[0]", 0.0)
    time ^= shl32(abs(math.floor(velocity_x)), 16)
    
    # time ^= stats[0] > 0 ? stats[0] & 0xff : 150
    stat0 = stats.get("0", 0)
    time ^= (stat0 & 0xFF) if stat0 > 0 else 150
    
    # time ^= (movementDir & 0xf) << 28
    movement_dir = playerstate.get("movementDir", 0)
    time ^= shl32(movement_dir & 0xF, 28)
    
    time = u32(time)
    
    # Equivalent to:
    # time[3] ^= time[2]
    # time[2] ^= time[1]
    # time[1] ^= time[0]
    for i in range(0x18, 0, -8):
        temp = (shr32(time, i) ^ shr32(time, i - 8)) & 0xFF
        
        time = (
            time
            & u32(~shl32(0xFF, i))
        ) | shl32(temp, i)
        
        time = u32(time)
    
    # local1c = (snap_serverTime << 2)
    local1c = shl32(snap_server_time, 2)
    
    # local1c += (df_ver + mapNameChecksum) << 8
    local1c = u32(
        local1c
        + shl32(df_version + map_name_checksum, 8)
    )
    
    # local1c ^= snap_serverTime << 24
    local1c ^= shl32(snap_server_time, 24)
    local1c = u32(local1c)
    
    # time ^= local1c
    time ^= local1c
    time = u32(time)
    
    # local1c = time[28:32]
    local1c = shr32(time, 28)
    
    # local1c |= (~local1c << 4) & 0xff
    local1c |= shl32(~local1c, 4) & 0xFF
    local1c = u32(local1c)
    
    # local1c |= local1c << 8
    local1c |= shl32(local1c, 8)
    local1c = u32(local1c)
    
    # local1c |= local1c << 16
    local1c |= shl32(local1c, 16)
    local1c = u32(local1c)
    
    # time ^= local1c
    time ^= local1c
    time = u32(time)
    
    # checksum stored in bits 22..27
    checksum = shr32(time, 0x16) & 0x3F
    
    # actual time is lower 22 bits
    time &= 0x3FFFFF
    
    # calculate checksum
    calculated = 0
    
    for l in range(3):
        calculated += (time >> (6 * l)) & 0x3F
    
    # upper 4 bits
    calculated += (time >> 0x12) & 0xF
    
    has_error = checksum != (calculated & 0x3F)
    
    return time, has_error


def get_uncolored_text(text):
    return re.sub(r"\^.", "", text)