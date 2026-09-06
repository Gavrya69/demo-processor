import os
import json

from core.demos import DemoParser

DEMOPATH = r".\files\palmslane[mdf.cpm]00.06.312(Arcaon.Sweden).dm_68"
DEMOPATH = r".\files\sodomia[mdf.cpm]00.39.232(AWNachos.Russia).dm_68"
DEMOPATH = r"C:\MY\Games\DEFRAG\Q3 DeFRaG\defrag\demos\123.dm_68"
# DEMOPATH = r".\files\sodomia[mdf.cpm]00.39.232(AWNachos.Russia).dm_68"
DEMOPATH = r"C:\MY\Games\DEFRAG\Q3 DeFRaG\defrag\demos\st1[df.vq3]00.07.776(Nachos.Russia).dm_68"
# DEMOPATH = r"C:\MY\Games\DEFRAG\Q3 DeFRaG\defrag\demos\Collection\DEFRAG WORLD CUP\DFWC 2017\Round 7\cpm\dfwc2017-7[df.cpm]00.39.040(kin3.Belarus)_8408.dm_68"
# DEMOPATH =r"C:\MY\Games\DEFRAG\Q3 DeFRaG\defrag\demos\MY\t\thetower[mdf.cpm]00.02.672(EBACHOS.Russia).dm_68"

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
        # print(sp.servertime, sp.is_jump(), sp.get_ps_all().get("pm_time"))
        # print(sp.servertime, sp.get_df_time())
    
    file_name = os.path.splitext(os.path.basename(demo_path))[0]
    with open(f"{file_name}.json", "w") as f:
        json.dump(data, f, indent=4)
    
    return


if __name__ == "__main__":
    parse_demo(DEMOPATH)