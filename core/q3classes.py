import numpy as np
from core import defs
from core.utils import get_map_name_checksum


class Snapshot():
    def __init__(
        self, 
        sequence=None, 
        server_time=None, 
        delta_num=None, 
        playerstate=None
    ):
        self.sequence = sequence
        self.server_time = server_time
        self.delta_num = delta_num
        self.playerstate = playerstate
        
        self.previous_snapshot = None
        self.next_snapshot = None
        
        self.time = 0
        self.time_error = 0
    
    
    def get_ps_val(self, key: str): # WTF: А надо ли? Если есть поле playerstate
        return self.playerstate.get(key, None)
    
    
    def get_es_val(self, key: str):
        return self.entitystate.get(key, None)
    
    
    def get_ps_all(self):
        return self.playerstate
    
    
    def get_es_all(self):
        return self.entities
    
    
    def get_stat(self, num: int):
        return self.playerstate.get('stats', {}).get(num, None)
    
    
    def is_dj_time(self): # TODO: Написать
        return
    
    
    def is_jump(self): # TODO: Потестить
        try:
            return self.get_ps_val('pm_time') > self.previous_snapshot.get_ps_val('pm_time')
        except (AttributeError, TypeError):
            return False
    
    
    def get_pos(self):
        return [
            self.playerstate.get("origin[0]", 0),
            self.playerstate.get("origin[1]", 0),
            self.playerstate.get("origin[2]", 0)
        ]
    
    
    def get_view_angles(self, rad: bool=False):
        scalar = np.pi/180 if rad else 1
        
        pitch = self.playerstate.get('viewangles[0]', 0)
        yaw = self.playerstate.get('viewangles[1]', 0)
        roll = self.playerstate.get('viewangles[2]', 0)
        
        return list(map(lambda angle: angle * scalar, [pitch, yaw, roll]))
    
    
    def get_wish_dir(self): # TODO: Потестить
        pitch, yaw, roll = self.get_view_angles(rad=True)
        
        forward = [np.cos(pitch) * np.cos(yaw),
                   np.cos(pitch) * np.sin(yaw)]
        right = [-np.sin(roll)*np.sin(pitch)*np.cos(yaw) + np.cos(roll)*np.sin(yaw),
                -np.sin(roll)*np.sin(pitch)*np.sin(yaw) - np.cos(roll)*np.cos(yaw)]
        
        presses = self.get_presses()
        if 'F' in presses:
            fwd_press = 127.0
        elif 'B' in presses:
            fwd_press = -127.0
        else:
            fwd_press = 0.0
        
        if 'R' in presses:
            side_press = 127.0
        elif 'L' in presses:
            side_press = -127.0
        else:
            side_press = 0.0
        
        wish_vel = np.array([0.0, 0.0])
        for i in range(0, 2):
            wish_vel[i] = forward[i] * fwd_press + right[i] * side_press
        
        if np.linalg.norm(wish_vel):
            wish_dir = wish_vel / np.linalg.norm(wish_vel)
        else:
            wish_dir = np.array([0, 0])
        
        return wish_dir
    
    
    def get_vel(self):
        return [
            self.playerstate.get('velocity[0]', 0), 
            self.playerstate.get('velocity[1]', 0),
            self.playerstate.get('velocity[2]', 0)
        ]
    
    
    def in_cgaz_zone(self): # TODO: Потестить
        wish_dir = self.get_wish_dir()
        
        if not np.linalg.norm(wish_dir):
            return False
        
        vel = np.array(self.get_vel())
        dot_prod = np.dot(vel, wish_dir)
        
        return 0 < 320 - dot_prod <= 320
    
    
    def get_speed(self):
        [vel_x, vel_y, vel_z] = self.get_vel()
        return round((vel_x**2 + vel_y**2)**0.5)
    
    
    def get_df_time(self): # TODO: Потестить
        try:
            timer = self.playerstate['time']
        except KeyError:
            timer = 0
        return timer
    
    
    def get_presses(self):
        press = self.playerstate.get('stats', {}).get('13', 0)
        presses = ""
        
        for symbol, press_num in defs.PRESS_NUMS.items():
            if press >= press_num:
                presses += symbol
                press -= press_num
            if press == 0:
                break
        
        return presses
    
    
    def has_pm_flag(self, flag: int): # TODO: Написать
        return
    
    
    def get_pm_flags(self): # TODO: Написать
        # pm_flags = format(playerstate['pm_flags'], '013b')
        # print(f'stats at time {time}: presses: {PRESSES}, speed:{speed} pm_flags: {pm_flags}')
        return
    
    
    def get_health_armor(self):
        health = self.playerstate.get('stats', {}).get('0', 0)
        armor = self.playerstate.get('stats', {}).get('3', 0)
        
        return [health, armor]
    
    
    def get_ammo(self):
        return self.playerstate.get('ammo', {})
    
    
    def is_checkpoint(self): # TODO: Написать
        return



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


class ServerCommand:
    def __init__(self, sequence, server_time, command):
        self.sequence = sequence
        self.server_time = server_time
        self.command = command.decode("utf8", errors="ignore").rstrip("\0")