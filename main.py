import os
import json

from core.demos import DemoParser


DEMOPATH = r".\files\palmslane[mdf.cpm]00.06.312(Arcaon.Sweden).dm_68"


def parse_demo(demo_path: str):
    demoparser = DemoParser(demo_path)
    demo = demoparser.parse()
    
    data = []
    
    for sp in demo.snapshots.values():
        data.append({
            "ServerTime": sp.servertime,
            # "PlayerState": sp.get_ps_all(),
            "Position": sp.get_pos(), 
            # "Velocity": sp.get_vel(), 
            # "ViewAngles": sp.get_view_angles(),
            "Presses": sp.get_presses()
        })
    
    file_name = os.path.splitext(os.path.basename(demo_path))[0]
    with open(f"{file_name}.json", "w") as f:
        json.dump(data, f, indent=4)
    
    return


if __name__ == "__main__":
    parse_demo(DEMOPATH)