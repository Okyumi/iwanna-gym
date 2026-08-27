"""Generate the 20 event-system trap rooms (levels/traps/t*.txt).

Every room is plain level text: tiles + '@' entity spawns + '!' event lines.
No C code is specific to any room (milestone B acceptance criterion).

Rooms follow classic I Wanna Be The Guy / fangame trap archetypes:
sudden fruit launches, delayed collapses, doors slamming shut, fake saves,
and timing gauntlets that punish constant-speed running.
"""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "iwanna_gym", "levels", "traps")

W, H = 25, 19


def base_room():
    rows = ["#" * W]
    for _ in range(1, 17):
        rows.append("#" + "." * (W - 2) + "#")
    rows.append("#S" + "." * (W - 4) + "G#")
    rows.append("#" * W)
    return [list(r) for r in rows]


def put(rows, tx, ty, ch):
    rows[ty][tx] = ch


def text(rows, extra):
    return "\n".join("".join(r) for r in rows) + "\n" + extra


ROOMS = {}

# t01: the user-story room — apple launches upward as the player approaches.
r = base_room()
ROOMS["t01_apple"] = text(r, """\
@fruit 13 17 tag=17
!when=pass_x x=11 dir=right -> launch tag=17 vx=1.1 vy=-8 grav=0.4
""")

# t02: ceiling fruit volley dropped by a region trigger; running clears it.
r = base_room()
ROOMS["t02_volley"] = text(r, """\
@fruit 11 2 tag=21
@fruit 13 2 tag=21
@fruit 15 2 tag=21
!when=enter_region x0=7 y0=0 x1=9 y1=19 -> launch tag=21 vy=6
""")

# t03: spike rises out of the floor, a chained timer freezes it into a wall.
r = base_room()
ROOMS["t03_riser"] = text(r, """\
@trap 12 19 tag=3 dir=up
!when=enter_region x0=8 y0=0 x1=9 y1=19 -> launch tag=3 vy=-2 ; start_timer id=5
!when=timer id=5 auto=0 delay=48 -> set_velocity tag=3 vy=0
""")

# t04: two platforms over a spike pit collapse 15 frames after you land.
r = base_room()
for tx in range(9, 16):
    put(r, tx, 17, "^")
ROOMS["t04_fall"] = text(r, """\
@platform 10 16 tag=5
@platform 13 16 tag=6
!when=land tag=5 delay=15 -> set_gravity tag=5 grav=0.35
!when=land tag=6 delay=15 -> set_gravity tag=6 grav=0.35
""")

# t05: the door slams shut behind you; the save ahead opens the exit gate.
r = base_room()
ROOMS["t05_door"] = text(r, """\
@gate 5 14 w=1 h=4 tag=2 open=1
@gate 19 14 w=1 h=4 tag=3
@save 12 17 tag=7
!when=pass_x x=7 dir=right -> close_gate tag=2
!when=save tag=7 -> open_gate tag=3
""")

# t06: ceiling crusher drops on anyone standing under it too long.
r = base_room()
ROOMS["t06_crusher"] = text(r, """\
@platform 12 2 tag=6
!when=enter_region x0=8.5 y0=13 x1=13.5 y1=19 -> set_velocity tag=6 vy=10 ; make_killer tag=6
""")

# t07: periodic bullets stream along the floor at head height.
r = base_room()
ROOMS["t07_bullets"] = text(r, """\
!when=timer delay=20 period=80 -> spawn type=bullet x=23 y=17 vx=-4
""")

# t08: leaving the spawn area releases a same-speed chaser; never stop.
r = base_room()
ROOMS["t08_chase"] = text(r, """\
@fruit 0.5 17 tag=19
!when=leave_region x0=0 y0=0 x1=4 y1=19 -> launch tag=19 vx=3
!when=timer delay=180 -> launch tag=19 vx=3
""")

# t09: fake save — touching it drops a fruit on your head; touch and go.
r = base_room()
ROOMS["t09_fakesave"] = text(r, """\
@save 12 17 tag=8
!when=touch tag=8 delay=8 -> spawn type=fruit x=12 y=13 vy=5 ; spawn type=fruit x=15 y=13 vy=5
""")

# t10: the exit gate only opens after the launched fruit is destroyed
# (culled offscreen) — an object_destroyed chain.
r = base_room()
ROOMS["t10_chain"] = text(r, """\
@fruit 8 17 tag=17
@gate 18 14 w=1 h=4 tag=4
!when=pass_x x=6 dir=right -> launch tag=17 vx=1.4 vy=-9 grav=0.35
!when=destroyed tag=17 -> open_gate tag=4
""")

# t11: a ground-level teleport field bounces walkers back to the start;
# jump over it (region only covers low heights).
r = base_room()
ROOMS["t11_teleport"] = text(r, """\
!when=enter_region x0=11 y0=16 x1=12 y1=19 once=0 -> teleport gx=2 gy=16
""")

# t12: pass_x gauntlet — each line drops a fruit exactly where a
# constant-speed runner would be; pause after each trigger.
r = base_room()
ROOMS["t12_gauntlet"] = text(r, """\
@trap 21 1 tag=14 dir=up
!when=pass_x x=6 dir=right -> spawn type=fruit x=9 y=12 vy=4
!when=pass_x x=11 dir=right -> spawn type=fruit x=14 y=12 vy=4
!when=pass_x x=16 dir=right -> spawn type=fruit x=19 y=12 vy=4
!when=pass_x x=20 dir=right -> set_dir tag=14 dir=down ; launch tag=14 vy=6
""")

# t13: the floor bridge over spikes is a gate that opens mid-crossing;
# jump the pit instead of walking it.
r = base_room()
for tx in range(10, 13):
    put(r, tx, 17, "^")
ROOMS["t13_floorgate"] = text(r, """\
@gate 10 16 w=3 h=1 tag=6
!when=pass_x x=11.5 dir=right delay=3 -> open_gate tag=6
""")

# t14: race — fruits rise through the floor across the whole room on a
# room_enter fuse; reach the goal before the room floods.
r = base_room()
ROOMS["t14_race"] = text(r, """\
@fruit 1 20 tag=4
@fruit 6 20 tag=4
@fruit 11 20 tag=4
@fruit 16 20 tag=4
@fruit 21 20 tag=4
!when=room_enter delay=150 -> launch tag=4 vy=-0.9
""")

# t15: lobbed fruit rain arcs across the room on a repeating timer.
r = base_room()
ROOMS["t15_rain"] = text(r, """\
!when=timer delay=10 period=55 -> spawn type=fruit x=1 y=2 vx=3.2 vy=-2 grav=0.12
""")

# t16: invisible bridge — platforms over the pit only activate from a
# region on the near side, and deactivate once you are across.
r = base_room()
for tx in range(10, 15):
    put(r, tx, 17, "^")
ROOMS["t16_bridge"] = text(r, """\
@platform 10.5 15 tag=11 active=0
@platform 13.5 15 tag=11 active=0
!when=enter_region x0=6 y0=14 x1=9 y1=19 -> activate tag=11
!when=enter_region x0=16 y0=14 x1=19 y1=19 -> deactivate tag=11
""")

# t17: one trigger, many actions — a three-height bullet wall plus a fruit
# that pops out of the floor further on (move action).
r = base_room()
ROOMS["t17_wall"] = text(r, """\
@fruit 20 20 tag=13
!when=pass_x x=10 dir=right -> spawn type=bullet x=24 y=17 vx=-4 ; spawn type=bullet x=24 y=14 vx=-4 ; spawn type=bullet x=24 y=13 vx=-4
!when=pass_x x=16 dir=right -> move tag=13 dy=-96
""")

# t18: platform ladder to an elevated goal; each landing (and crossing the
# height line) calls in a horizontal shot at that height.
r = base_room()
put(r, 20, 12, "G")
r[17][23] = "."           # remove the default floor goal
ROOMS["t18_ladder"] = text(r, """\
@platform 10 15 tag=21
@platform 16 13 tag=22
!when=land tag=21 -> spawn type=bullet x=24 y=14 vx=-5
!when=land tag=22 -> spawn type=bullet x=24 y=12 vx=-5
!when=pass_y y=13.5 dir=up -> spawn type=bullet x=24 y=13 vx=-4
""")

# t19: speed gate — the save opens the exit but a chained timer slams it
# shut again; sprint.
r = base_room()
ROOMS["t19_speedgate"] = text(r, """\
@save 10 17 tag=9
@gate 15 14 w=1 h=4 tag=12
!when=save tag=9 -> open_gate tag=12 ; start_timer id=30
!when=timer id=30 auto=0 delay=110 -> close_gate tag=12
""")

# t20: finale — door closes behind, apple launch, collapsing platform over
# spikes, save-opened exit gate, periodic floor bullets.
r = base_room()
for tx in range(12, 15):
    put(r, tx, 17, "^")
ROOMS["t20_finale"] = text(r, """\
@gate 3 14 w=1 h=4 tag=2 open=1
@fruit 9 17 tag=17
@platform 13 15 tag=5
@save 16 17 tag=7
@gate 20 14 w=1 h=4 tag=3
!when=pass_x x=5 dir=right -> close_gate tag=2
!when=pass_x x=7 dir=right -> launch tag=17 vy=-11 grav=0.4
!when=land tag=5 delay=20 -> set_gravity tag=5 grav=0.4
!when=save tag=7 -> open_gate tag=3
!when=timer delay=40 period=90 -> spawn type=bullet x=24 y=17 vx=-3.5
""")


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, txt in sorted(ROOMS.items()):
        path = os.path.join(OUT, name + ".txt")
        with open(path, "w") as f:
            f.write(txt)
        print("wrote", path)
    print(len(ROOMS), "rooms")


if __name__ == "__main__":
    main()
