from core import defs
from core.q3classes import Snapshot
from core.buffers import Buffer


class Demo:
    def __init__(self, filepath, gamestate, snapshots, servercommands):
        self.filepath = filepath
        self.gamestate = gamestate
        self.snapshots = snapshots
        self.servercommands = servercommands
        
        self.client_number = gamestate.client_number
        self.players = self.get_players()
        
    
    def get_players(self):
        players = {}
        for key, val in self.gamestate.configs.items():
            s = val.decode("utf-8", errors="ignore").rstrip("\x00")
            if s.startswith("\\"):
                s = s[1:]
            parts = s.split("\\")
            
            if parts[0] == "n": # "name" value (only players have it)
                players[key] = dict(zip(parts[0::2], parts[1::2]))
        
        players = {(k-544): v for k, v in players.items()}
        
        import re
        for pid, pdata in players.items():
            pdata["name"] = re.sub(r"\^.", "", pdata["n"]) # uncolored nickname
            if pid == self.client_number:
                pdata["is_main"] = True
            else:
                pdata["is_main"] = False
        
        return players
    
    
    def get_weapons(self, client_id=None):
        weap_list = []
        
        if client_id is None or (client_id) == self.gamestate.client_number:
            for snapshot in self.snapshots.values():
                weap = snapshot.playerstate.get('weapon', None)
                if weap and (weap not in weap_list):
                    weap_list.append(weap)
        else:
            for snapshot in self.snapshots.values():
                entity_info = snapshot.entities.get(client_id, None)
                if entity_info:
                    weap = entity_info.get('weapon', None)
                    if weap and (weap not in weap_list):
                        weap_list.append(weap)
        
        return sorted(weap_list)
    
    
    def get_playermodel(self, client_id=None):
        model = self.players[client_id]["model"]
        head_model = self.players[client_id]["hmodel"]
        return model, head_model


class DemoParser:
    def __init__(self, filepath):
        self.filepath = filepath
        
        self.gamestate = None
        self.servercommands = []
        self.baselines = {}
        self.snapshots = {}
        
        self.last_snapshot = None
        self.current_server_time = 0
    
    
    def parse_snapshot(self, sequence, buffer):
        server_time = buffer.read_bits(32)
        delta_num = buffer.read_bits(8)
        
        snapshot = Snapshot(
            sequence=sequence,
            server_time=server_time,
            delta_num=delta_num
        )
        
        self.current_server_time = server_time
        
        snapshot_to_delta_from = None
        
        if delta_num != 0:
            key = (sequence - delta_num) & defs.PACKET_MASK
            snapshot_to_delta_from = self.snapshots.get(key)
            
            if snapshot_to_delta_from and snapshot_to_delta_from.sequence != sequence - delta_num:
                snapshot_to_delta_from = None
        
        snapshot.snap_flags = buffer.read_bits(8)
        
        areamask_length = buffer.read_bits(8)
        snapshot.areamask = buffer.read_bits(areamask_length * 8)
        
        snapshot.playerstate = self.parse_playerstate(buffer, snapshot_to_delta_from)
        snapshot.entities = self.parse_entities(buffer, snapshot_to_delta_from)
        
        snapshot.time, snapshot.time_error = get_defrag_time(
            playerstate=snapshot.playerstate,
            snap_server_time=snapshot.server_time,
            df_version=self.gamestate.df_version,
            map_name_checksum=self.gamestate.map_name_checksum,
            is_online=self.gamestate.is_online,
            is_cheats_on=self.gamestate.is_cheats_on,
        )
        
        self.snapshots[sequence & defs.PACKET_MASK] = snapshot
        
        snapshot.previous_snapshot = self.last_snapshot
        if self.last_snapshot:
            self.last_snapshot.next_snapshot = snapshot
        
        self.last_snapshot = snapshot
        
        return snapshot
    
    
    def parse_playerstate(self, buffer, snapshot_to_delta_from):
        if snapshot_to_delta_from is not None:
            playerstate = snapshot_to_delta_from.playerstate.copy()
        else:
            playerstate = {}
        
        field_count = buffer.read_bits(8, "field_count")
        
        for i in range(field_count):
            if buffer.read_bit("field_changed"):
                field = defs.PLAYERSTATE_FIELDS[i]
                
                if field.bits == 0:  # float
                    if buffer.read_bit("int_or_float") == 0:
                        playerstate[field.name] = buffer.read_int_float(field.name)
                    else:
                        playerstate[field.name] = buffer.read_float(field.name)
                else:
                    playerstate[field.name] = buffer.read_bits(field.bits, field.name)
        
        if buffer.read_bit("arrays_changed"):
            if buffer.read_bit("stats_changed"):
                bits = buffer.read_bits(16, "stats_bits")
                stats = playerstate.get('stats', {}).copy()
                for i in range(16):
                    if bits & (1 << i):
                        stats[str(i)] = buffer.read_bits(16, f"stats_bit_{i}")
                playerstate['stats'] = stats
            
            if buffer.read_bit("persistent_changed"):
                bits = buffer.read_bits(16, "persistent_bits")
                persistent_bits = {}
                for i in range(16):
                    if bits & (1 << i):
                        persistent_bits[str(i)] = buffer.read_bits(16, "persistent_bit_{}".format(i))
                playerstate['persistent_bits'] = persistent_bits
            
            if buffer.read_bit("ammo_changed"):
                ammo = {}
                bits = buffer.read_bits(16, "ammo_bits")
                for i in range(16):
                    if bits & (1 << i):
                        ammo[str(i)] = buffer.read_bits(16, "ammo_bit_{}".format(i))
                playerstate['ammo'] = ammo
                
            if buffer.read_bit("powerups_changed"):
                powerups = {}
                bits = buffer.read_bits(16, "powerups_bits")
                for i in range(16):
                    if bits & (1 << i):
                        powerups[str(i)] = buffer.read_bits(32, "powerups_bit_{}".format(i))
                playerstate['powerups'] = powerups
        
        return playerstate
    
    
    def parse_entities(self, buffer, snapshot_to_delta_from):
        if snapshot_to_delta_from is not None:
            entities = snapshot_to_delta_from.entities.copy()
        else:
            entities = {}
        
        while True:
            entity_number = buffer.read_bits(defs.GENTITYNUM_BITS, "entity_number")
            
            if entity_number == defs.MAX_GENTITIES - 1:
                break
            
            elif buffer.read_bit("update_or_delete") == 1:
                if entity_number in entities:
                    del entities[entity_number]
                continue
            
            if entity_number in entities:
                old = entities[entity_number]
            elif entity_number in self.baselines:
                old = self.baselines[entity_number]
            else:
                old = {}
            
            entities[entity_number] = self.read_delta_entity(buffer, old)
        
        return entities
    
    
    def parse_gamestate(self, buffer):
        server_command_sequence = buffer.read_bits(32)
        
        configs = {}
        self.baselines = {}
        
        while True:
            gamestate_op = buffer.read_bits(8)
            
            if gamestate_op == 8: # svc_EOF
                break
            
            elif gamestate_op == 3: # configstring
                i = buffer.read_bits(16, "configstring_index")
                config_string = buffer.read_string("configstring")
                configs[i] = config_string
                
            elif gamestate_op == 4:  # baseline
                entity_number = buffer.read_bits(defs.GENTITYNUM_BITS, "entity_number")
                if buffer.read_bit("update_or_delete") == 0:
                    self.baselines[entity_number] = self.read_delta_entity(buffer, {})
            else:
                raise Exception(f"Unknown gamestate op: {gamestate_op}")
        
        client_number = buffer.read_bits(32, "client_number")
        checksum_feed = buffer.read_bits(32, "checksum_feed")
        
        return GameState(
            configs=configs,
            client_number=client_number,
            checksum_feed=checksum_feed,
            baselines=self.baselines
        )
    
    
    def read_delta_entity(self, buffer, old):
        entity = old.copy()
        
        if buffer.read_bit("entity_changed") == 1:
            field_count = buffer.read_bits(8, "field_count")
            
            for i in range(field_count):
                if buffer.read_bit("field_changed") == 1:
                    field = defs.ENTITY_FIELDS[i]
                    
                    if field.bits == 0: # float
                        if buffer.read_bit("float_is_not_zero") == 1:
                            if buffer.read_bit("int_or_float") == 0:
                                entity[field.name] = buffer.read_int_float(field.name)
                            else:
                                entity[field.name] = buffer.read_float(field.name)
                        else:
                            entity[field.name] = 0
                    else:
                        if buffer.read_bit("int_is_not_zero") == 1:
                            entity[field.name] = buffer.read_bits(field.bits, field.name)
                        else:
                            entity[field.name] = 0
        
        return entity
    
    
    def parse_server_command(self, buffer):
        command_sequence = buffer.read_bits(32)
        command = buffer.read_string()
        
        return {
            "sequence": command_sequence,
            "server_time": self.current_server_time,
            "command": command
        }
    
    
    def parse_message_stream(self, sequence, buffer):
        events = []
        
        buffer.read_bits(32) # skip header
        
        while True:
            opcode = buffer.read_bits(8)
            
            if opcode == defs.SVC_EOF:
                break
            
            elif opcode == defs.SVC_SNAPSHOT:
                events.append(("snapshot", self.parse_snapshot(sequence, buffer)))
            
            elif opcode == defs.SVC_SERVERCOMMAND:
                events.append(("servercommand", self.parse_server_command(buffer)))
            
            elif opcode == defs.SVC_GAMESTATE:
                self.gamestate = self.parse_gamestate(buffer)
                events.append(("gamestate", self.gamestate))
            
            
            else:
                raise Exception(f"Unknown opcode {opcode}")
        
        return events
    
    
    def get_messages(self):
        while True:
            sequence = int.from_bytes(
                self.file.read(defs.MSG_SEQUENCE_LEN),
                'little'
            )
            msg_length = int.from_bytes(
                self.file.read(defs.MSG_LENGTH_LEN),
                'little'
            )
            
            if sequence in (0, 0xFFFFFFFF) and msg_length in (0, 0xFFFFFFFF):
                return
            
            buffer = Buffer(self.file.read(msg_length))
            
            yield sequence, buffer
    
    
    def parse(self): # IDEA: добавить логирование
        self.file = open(self.filepath, 'rb')
        
        gamestate = None
        snapshots = {}
        servercommands = []
        
        print("Start reading")
        for sequence, buffer in self.get_messages():
            events = self.parse_message_stream(sequence, buffer)
            
            for event_type, event in events:
                
                if event_type == "snapshot":
                    snapshots[event.sequence] = event
                    
                elif event_type == "servercommand":
                    servercommands.append(event)
                    
                elif event_type == "gamestate":
                    gamestate = event
        
        self.file.close()
        print("End reading")
        
        return Demo(
            filepath=self.filepath,
            gamestate=gamestate,
            snapshots=snapshots,
            servercommands=servercommands,
        )


def get_defrag_time(
    playerstate,
    snap_server_time,
    df_version,
    map_name_checksum,
    is_online=False,
    is_cheats_on=False,
):
    import math
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


def get_map_name_checksum(map_name):
    return sum(map_name.lower().encode("ascii", errors="ignore")) & 0xFF


class GameState:
    def __init__(self, configs, client_number, checksum_feed, baselines):
        self.configs = configs
        self.client_number = client_number
        self.checksum_feed = checksum_feed
        self.baselines = baselines
        
        self.client = {}
        self.game = {}
        self.raw = {}
        
        self.parse_configs()
        
        # Defrag Settings (for time parsing)
        self.map_name = self.client.get("mapname", "")
        self.map_name_checksum = get_map_name_checksum(self.map_name)
        self.df_version = int(self.client.get("defrag_vers", 0))
        self.is_online = int(self.client.get("defrag_gametype", 0)) > 4
        self.is_cheats_on = int(self.game.get("sv_cheats", 0)) > 0
        
        
    def parse_configs(self):
        data = {"game": {}, "client": {}, "raw": {}}
        for key, val in self.configs.items():
            s = val.decode("utf-8", errors="ignore").rstrip("\x00")
            if s.startswith("\\"):
                s = s[1:]
            parts = s.split("\\")
            
            if key == 0:
                self.client = dict(zip(parts[0::2], parts[1::2]))
            elif key == 1:
                self.game = dict(zip(parts[0::2], parts[1::2]))
            else:
                self.raw[key] = dict(zip(parts[0::2], parts[1::2]))
        
        return data