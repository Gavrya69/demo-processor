from core import defs
from core.q3classes import Snapshot, GameState, ServerCommand
from core.buffers import Buffer
from core.utils import get_defrag_time, get_uncolored_text


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
        
        for pid, pdata in players.items():
            pdata["name"] = get_uncolored_text(pdata["n"])
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
        
        return ServerCommand(
            sequence=command_sequence,
            server_time=self.current_server_time,
            command=command
        )
    
    
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
    
    
    def parse(self):
        self.file = open(self.filepath, 'rb')
        
        for sequence, buffer in self.get_messages():
            events = self.parse_message_stream(sequence, buffer)
            
            for event_type, event in events:
                if event_type == "snapshot":
                    self.snapshots[event.sequence] = event
                    
                elif event_type == "servercommand":
                    self.servercommands.append(event)
                    
                elif event_type == "gamestate":
                    self.gamestate = event
        
        self.file.close()
        
        return Demo(
            filepath=self.filepath,
            gamestate=self.gamestate,
            snapshots=self.snapshots,
            servercommands=self.servercommands,
        )



