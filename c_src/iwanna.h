/* IWannaGym — a fast RL environment with authentic "I Wanna" fangame physics.
 *
 * Physics faithfully reproduces the GameMaker 8 Yuuutu/Renex engine player:
 *   room_speed = 50 (one step = 1/50 s)
 *   maxSpeed   = 3      (run speed, px/frame)
 *   jump       = 8.5    (single jump vspeed)
 *   jump2      = 7      (double jump vspeed)
 *   baseGrav   = 0.4    (gravity per frame)
 *   maxVspeed  = 9      (fall speed cap; effective applied max 9.4)
 *   release    -> vspeed *= 0.45 when jump released while rising
 *   player hitbox: 11x20 px  (x-5..x+5, y-11..y+8 inclusive)
 * Collision resolution is a line-by-line port of the Renex engine
 * "solid collision" step event, including GM8 banker's rounding.
 *
 * Ocean-style: external buffers for observations/actions/rewards/terminals.
 */
#ifndef IWANNA_H
#define IWANNA_H

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "gamepack/iwpack.h"
#include "exact.h"

#define IW_TILE 32
#define IW_FPS 50

/* Tile codes */
#define T_EMPTY 0
#define T_BLOCK 1
#define T_SPIKE_UP 2
#define T_SPIKE_DOWN 3
#define T_SPIKE_LEFT 4
#define T_SPIKE_RIGHT 5
#define T_GOAL 6

/* ---------- entity system ----------
 * Static tile geometry stays in env->tiles. Everything that moves, fires,
 * triggers, saves, or teleports is an IWEntity. New mechanics must be added
 * as entity types, not tile codes. All entity logic runs in C inside
 * c_step: no Python callback ever occurs during an ordinary step, and the
 * PufferLib C path gets identical behavior (same header).
 */
#define IW_ENT_PARAMS 6

enum {
    E_NONE = 0,
    E_PLATFORM,     /* jump-through moving platform (carries the player) */
    E_SPIKEBALL,    /* oscillating deadly ball */
    E_TRIGGER,      /* invisible region: fires trigger_id once on touch */
    E_TRAP,         /* dormant trap spike; launches when its trigger fires */
    E_PROJECTILE,   /* ballistic deadly bullet ("cherry") */
    E_SHOOTER,      /* emits projectiles every params[0] frames */
    E_ENEMY,        /* patrolling contact-deadly enemy */
    E_SAVE,         /* save point: updates the respawn position on touch */
    E_WARP,         /* teleport to params[0..1] (room pixels) on touch */
    E_BOSS,         /* contact-deadly radial-burst shooter (boss scaffold) */
    E_GATE,         /* door: stamps solid tiles while closed (state=1) */
    E_PBULLET,      /* the Kid's bullet (IWBTGR bullet object semantics) */
    E_NUM_TYPES
};

/* ---- player shooting (IWBTGR source values; see playerShoot.gml,
 * objects/bullet.gml, sprites/sprBulletMask) ----
 *   spawn at (player.x, player.y-2); hspeed = facing * 16; no gravity;
 *   lifetime alarm[0]=42 frames; at most 4 bullets alive; one shot per
 *   shoot-key PRESS (autofire is a non-legit setting, not imported);
 *   mask: origin (5,1), bbox 0..9 x 0..1 => rect [x-5..x+4] x [y-1..y]. */
#define IW_BULLET_SPEED 16.0f
#define IW_BULLET_LIFE 42
#define IW_BULLET_MAX 4
#define IW_BULLET_SPAWN_DY (-2.0f)
#define IW_BULLET_L (-5)
#define IW_BULLET_R (4)
#define IW_BULLET_T (-1)
#define IW_BULLET_B (0)
#define IW_SAVE_TIMER 50   /* per-save cooldown between activations */

/* entity flags */
#define EF_ACTIVE    1u
#define EF_DEADLY    2u
#define EF_SOLID_TOP 4u   /* jump-through solid from above (platforms) */
#define EF_DORMANT   8u   /* inert until its trigger_id fires */

/* collision_mask bits */
#define CM_PLAYER 1u
#define CM_TILES  2u

typedef struct {
    uint8_t type;
    uint32_t flags;
    int32_t trigger_id;
    int32_t tag;            /* event-system handle; actions target all entities with a tag */
    uint32_t collision_mask;
    float x, y;             /* center, room pixels */
    float vx, vy;
    float grav;             /* per-frame vy increment (falling platforms, arcing fruit) */
    int32_t state;
    int32_t timer;
    float params[IW_ENT_PARAMS];
    /* params by type:
     *  PLATFORM/SPIKEBALL/ENEMY: [0]=oscillation range px, [4],[5]=origin
     *  TRIGGER:    [0]=half w px, [1]=half h px
     *  TRAP:       [2],[3]=launch vx,vy, [4]=orientation 0=^ 1=v 2=< 3=>
     *  PROJECTILE: (grav field)
     *  SHOOTER:    [0]=period, [1]=speed, [2]=aimed(1)/fixed(0), [3],[4]=fixed dir
     *  WARP:       [0],[1]=destination px
     *  BOSS:       [0]=period, [1]=volleys (0 = endless), state=volleys left
     *  GATE:       [0],[1]=tile x,y of top-left, [2],[3]=w,h tiles, [4]=w*100+h (export)
     */
} IWEntity;

/* contact half-extents per type (rect hitboxes; traps use spike triangles;
 * gates collide through stamped tiles, extents used for obs/render only) */
static const float ENT_HW[E_NUM_TYPES] = {0, 16, 10, 0, 16, 4, 12, 11, 14, 14, 16, 16, 5};
static const float ENT_HH[E_NUM_TYPES] = {0,  8, 10, 0, 16, 4, 12, 14, 14, 14, 16, 16, 1};

/* observation type normalization is pinned to the pre-shooting type count
 * so legacy observations are bit-identical; bullets show up as 13/12 capped
 * to 1.0 */
#define IW_OBS_TYPE_NORM 12.0f

/* ---------- declarative trigger/event system ----------
 * Level text lines starting with '!' declare events:
 *   !when=<cond> [subject keys] [once=0/1] [delay=N] -> action [key=val ...] ; action ...
 * All conditions and actions run inside c_step (no callbacks, no allocation
 * after load). Coordinates are in tiles (floats allowed).
 */
enum {
    W_ROOM_ENTER = 0, /* fires on every episode reset */
    W_ENTER_REGION,   /* player origin enters [x0,y0]..[x1,y1] (edge) */
    W_LEAVE_REGION,   /* player origin leaves the region (edge) */
    W_TOUCH_OBJECT,   /* player rect overlaps any entity with tag=N */
    W_LAND_ON_OBJECT, /* player lands on a solid-top entity with tag=N */
    W_PASS_X,         /* player crosses vertical line x=N (dir=any/left/right) */
    W_PASS_Y,         /* player crosses horizontal line y=N (dir=any/up/down) */
    W_TIMER,          /* countdown armed at reset (auto=1) or by start_timer */
    W_OBJECT_DESTROYED, /* an entity with tag=N was destroyed or culled */
    W_SAVE_ACTIVATED, /* a save point with tag=N was touched (first time) */
    W_FLAG_SET,       /* global progression flag (subject=N) is set */
    W_NUM_WHEN
};

enum {
    ACT_ACTIVATE = 0, ACT_DEACTIVATE,
    ACT_LAUNCH,       /* set velocity + wake from dormant (alias set_velocity) */
    ACT_SET_GRAVITY,
    ACT_MOVE,         /* relative teleport of entities by dx,dy px */
    ACT_TELEPORT,     /* absolute: entity (tag) or player (no tag) to gx,gy tiles */
    ACT_SPAWN,        /* create a new entity at runtime */
    ACT_DESTROY,      /* deactivate + emit OBJECT_DESTROYED */
    ACT_MAKE_KILLER, ACT_MAKE_HARMLESS,
    ACT_MAKE_SOLID, ACT_MAKE_UNSOLID,   /* jump-through solidity (EF_SOLID_TOP) */
    ACT_OPEN_GATE, ACT_CLOSE_GATE,
    ACT_START_TIMER,  /* arm timer event with id=N */
    ACT_SET_DIR,      /* rotate a trap spike: dir=up/down/left/right */
    ACT_SET_FLAG,     /* set global progression flag id=N (persists across rooms) */
    ACT_CLEAR_FLAG,   /* clear global progression flag id=N */
    ACT_NUM
};

#define IW_ACT_PARAMS 6
typedef struct {
    uint8_t type;
    int32_t tag;              /* target entity tag (or event id for start_timer); -1 = player */
    float p[IW_ACT_PARAMS];   /* per-action params, see exec_action */
} IWAction;

typedef struct {
    uint8_t when;
    uint8_t once;             /* default 1: fire a single time per episode */
    uint8_t auto_arm;         /* timers: armed at reset (default 1) */
    int8_t  dir;              /* pass_x/pass_y direction: 0 any, -1 neg, +1 pos */
    int32_t id;               /* handle for start_timer */
    int32_t subject;          /* entity tag for touch/land/destroyed/save */
    float x0, y0, x1, y1;     /* region px (converted from tiles at parse) */
    int32_t delay;            /* frames between condition and actions */
    int32_t period;           /* timers: refire interval (0 = one-shot) */
    int32_t first_action, n_actions;  /* slice of the action pool */
    /* runtime state (reset each episode) */
    uint8_t fired;
    uint8_t inside;
    int32_t countdown;        /* -1 idle, >=0 frames until actions run */
} IWEvent;

/* Physics constants (from Renex engine Player.gml Create_0) */
#define IW_MAXSPEED 3.0
#define IW_JUMP 8.5
#define IW_JUMP2 7.0
#define IW_GRAV 0.4
#define IW_MAXVSPEED 9.0
#define IW_RELEASE_MULT 0.45
#define IW_MAXJUMPS 2

/* Player hitbox offsets from origin. Legacy engine value (research levels):
 * 11x20 box with top at -11. Exact-game packs override via env->hb_* from
 * the pack header (IWBTGR sprMask: rectangle, origin (17,23), bbox
 * 12..22 x 11..31 => -5..+5 x -12..+8, 11x21). */
#define HB_L (-5)
#define HB_R (5)
#define HB_T (-11)
#define HB_B (8)

/* Observation layout: base features + local tile window + K nearest entities */
#define IW_LOCAL_W 9   /* tiles, centered on player */
#define IW_LOCAL_H 7
#define IW_OBS_BASE 8
#define IW_OBS_K 6         /* nearest visible entities in the observation */
#define IW_OBS_ENT_F 5     /* features per entity: dx, dy, vx, vy, signed type */
#define IW_OBS_SIZE (IW_OBS_BASE + IW_LOCAL_W * IW_LOCAL_H + IW_OBS_K * IW_OBS_ENT_F)
/* Action encoding: a = shoot_held*6 + 2*(h+1) + jump_held.
 * Actions 0..5 are EXACTLY the legacy 6-action space (shoot released), so
 * legacy research environments keep their action semantics unchanged; the
 * full space adds shoot_held for the exact-game loop. Shoot fires on the
 * held->pressed EDGE, like the GM key-press event (source default: one
 * bullet per press; autofire is a non-legit setting, not imported). */
#define IW_NUM_ACTIONS 12
#define IW_NUM_ACTIONS_LEGACY 6

/* PufferLib-required log struct: floats only, n last */
typedef struct {
    float perf;             /* 0-1: goal reached */
    float score;            /* same as perf here */
    float episode_return;
    float episode_length;
    float death;            /* 1.0 if episode ended by dying */
    float n;
} Log;

typedef struct {
    Log log;                /* required first field for env_binding.h */
    /* external buffers (Ocean convention) */
    float* observations;
    int* actions;
    float* rewards;
    unsigned char* terminals;

    /* level (owned) */
    uint8_t* tiles;
    int tw, th;               /* tile grid dims */
    double start_x, start_y;
    double goal_x, goal_y;    /* center of goal region */

    /* config */
    int max_steps;
    int reward_mode;          /* 0 = sparse, 1 = dense (distance-delta shaping) */
    float death_penalty;      /* subtracted on death */
    int random_goal;          /* 1 = resample goal uniformly from empty tiles each reset */
    int checkpoint_respawn;   /* 1 = death respawns at last save point instead of terminating */
    uint64_t rng;

    /* entities: `spawns` is the immutable level definition, `entities` is the
     * live array restored from spawns on every episode reset (deterministic
     * replay from seed + action sequence). */
    IWEntity* entities;
    IWEntity* spawns;
    int ent_cap;
    int spawn_count;
    int free_hint;            /* next-slot hint for projectile spawning */
    int ent_top;              /* high-water mark: loops scan [0, ent_top) */
    double respawn_x, respawn_y;
    int on_platform;          /* standing on a moving platform last frame */
    int deaths;               /* deaths this episode (checkpoint mode) */

    /* trigger/event system (immutable after load except runtime fields) */
    IWEvent* events;
    int event_count;
    IWAction* ev_actions;     /* flat pool; events own slices */
    int ev_action_count;
    uint8_t* tiles0;          /* pristine tile copy for gate stamping */
    int prev_on_platform;     /* for land_on_object edge detection */
    int landed_tag;           /* tag of platform landed on this frame (-1 none) */
    uint64_t destroyed_tags;  /* bitmask of destroyed entity tags (1..63) */
    uint64_t save_tags;       /* bitmask of activated save tags */
    double prev_x, prev_y;    /* player position at frame start (pass_x/pass_y) */

    /* ---- game-pack mode (docs/gamepack_format.md) ----
     * All zero/NULL when loading classic single-room levels; the classic
     * paths are untouched. A loaded pack keeps every room's compiled data
     * in one decoded blob; room switches memcpy into the live buffers
     * below (sized once, at load, from the pack maxima): no allocation
     * and no parsing after construction. */
    IWPackRT* pack;           /* owned decoded pack; NULL = classic mode */
    int room_id;              /* current room index */
    int start_room;
    int respawn_room;         /* room of the active save point */
    int room_has_goal;        /* pack rooms may have no terminal goal */
    int pending_room;         /* -1 none; >=0 = switch rooms after this phase */
    float pending_x, pending_y;
    int pending_keep_speed;
    int pending_use_start;    /* 1 = enter at the target room's start point */
    int pending_xop0, pending_xnops;  /* warp side-effect ops (exact layer) */
    uint64_t gflags;          /* global progression flags (bits 1..63) */
    int room_transitions;     /* count this episode (introspection) */
    int difficulty;           /* 0=medium 1=hard 2=very hard 3=impossible */
    int room_pw, room_ph;     /* exact room pixel dims (tw*32/th*32 classic) */
    /* static source colliders not representable on the tile grid; these
     * point INTO the decoded pack blob (immutable, no copy, no alloc) */
    const IWPackSolid* solids;   int n_solids;
    const IWPackKiller* killers; int n_killers;

    /* ---- exact-behavior layer (pack v3; NULL otherwise) ---- */
    IWXState* xs;
    int hb_l, hb_t, hb_r, hb_b;  /* player hitbox (legacy default; packs
                                    with an exact section override) */

    /* dynamic state */
    double x, y, hspeed, vspeed;
    int djump;                /* jumps used; can air-jump while djump < IW_MAXJUMPS */
    int face;
    int prev_jump_held;
    int prev_h;               /* previous h input (walljump press edges) */
    int prev_shoot_held;      /* for shoot press-edge detection */
    int save_shoot_mode;      /* 1 = source-faithful shot-activated saves;
                                 0 = legacy touch saves (research/debug) */
    double respawn_face;      /* facing stored by saveGame (savew) */
    int attempt;              /* attempt counter: respawns + manual retries */
    int tick;
    double prev_goal_dist;
    float ep_return;
    int last_event;           /* 0 none, 1 death, 2 goal, 3 timeout (survives auto-reset) */
} IWanna;

/* ---------- utilities ---------- */

static inline uint64_t iw_rand(IWanna* env) {
    /* xorshift64* */
    uint64_t x = env->rng;
    x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
    env->rng = x;
    return x * 0x2545F4914F6CDD1DULL;
}

/* GM8 round(): round half to even (banker's rounding) */
static inline int gm_round(double v) {
    double f = floor(v);
    double d = v - f;
    if (d < 0.5) return (int)f;
    if (d > 0.5) return (int)f + 1;
    int fi = (int)f;
    return (fi % 2 == 0) ? fi : fi + 1;
}

static inline int iw_sign(double v) { return (v > 0) - (v < 0); }

/* forward declarations (bullet update runs before these are defined) */
static int rect_hits_solid(IWanna* env, int l, int r, int t, int b);
static void iw_activate_save_shot(IWanna* env, IWEntity* e);
static inline int ent_rect_hit(const IWEntity* e, int l, int r, int t, int b,
                               float hw, float hh);
/* exact-layer hooks (exact_impl.h); all no-ops when env->xs == NULL */
static int iwx_solid_hit(IWanna* env, int l, int r, int t, int b);
static int iwx_killer_hit(IWanna* env);
static int iwx_bullet_hit(IWanna* env, float bx, float by,
                          int bl, int br, int bt, int bb);
static void iwx_frame_begin(IWanna* env);
static void iwx_frame_end(IWanna* env);
static void iwx_load_room(IWanna* env, int room);
static void iwx_after_spawn(IWanna* env);
static void iwx_free(IWanna* env);
static int iwx_load_section(IWanna* env, char* err, size_t errlen);
static void iwx_run_ops(IWanna* env, int op0, int nops, int self);
static int iwx_touch_water(IWanna* env, double px, double py, int kind);
static int iwx_touch_platform(IWanna* env, double px, double py);
static void iwx_walljump(IWanna* env, int h, int jump_held, int h_pressed_r,
                         int h_pressed_l, int jump_pressed);

static inline uint8_t iw_tile_at(IWanna* env, int tx, int ty) {
    if (tx < 0 || ty < 0 || tx >= env->tw || ty >= env->th) return T_EMPTY;
    return env->tiles[ty * env->tw + tx];
}

/* Solid check for player bbox at real position (px, py).
 * GM8 instance_place/place_free round the instance position. */
static int place_free(IWanna* env, double px, double py) {
    int ix = gm_round(px), iy = gm_round(py);
    int l = ix + env->hb_l, r = ix + env->hb_r, t = iy + env->hb_t, b = iy + env->hb_b;
    int tx0 = l >= 0 ? l / IW_TILE : (l - IW_TILE + 1) / IW_TILE;
    int tx1 = r >= 0 ? r / IW_TILE : (r - IW_TILE + 1) / IW_TILE;
    int ty0 = t >= 0 ? t / IW_TILE : (t - IW_TILE + 1) / IW_TILE;
    int ty1 = b >= 0 ? b / IW_TILE : (b - IW_TILE + 1) / IW_TILE;
    for (int ty = ty0; ty <= ty1; ty++)
        for (int tx = tx0; tx <= tx1; tx++)
            if (iw_tile_at(env, tx, ty) == T_BLOCK) return 0;
    /* static solid rects imported from source (empty in classic mode) */
    for (int i = 0; i < env->n_solids; i++) {
        const IWPackSolid* s = &env->solids[i];
        if (l <= s->x1 && r >= s->x0 && t <= s->y1 && b >= s->y0) return 0;
    }
    if (env->xs && iwx_solid_hit(env, l, r, t, b)) return 0;
    return 1;
}

/* Rect vs spike-triangle overlap. Triangle occupies a full 32px cell with
 * origin (x0, y0), apex at the center of one edge, base on the opposite
 * edge (standard fangame spike mask). Player rect is [l..r] x [t..b]
 * inclusive. Used for both spike tiles and trap-spike entities. */
static int spike_hit_px(int l, int r, int t, int b, int x0, int y0, uint8_t kind) {
    int x1 = x0 + IW_TILE - 1, y1 = y0 + IW_TILE - 1;
    /* clip rect to tile */
    int cl = l > x0 ? l : x0, cr = r < x1 ? r : x1;
    int ct = t > y0 ? t : y0, cb = b < y1 ? b : y1;
    if (cl > cr || ct > cb) return 0;
    double cx = x0 + (IW_TILE - 1) / 2.0; /* 15.5 */
    double cy = y0 + (IW_TILE - 1) / 2.0;
    /* Triangle widens away from apex at slope 0.5 (16 half-width over 32) */
    switch (kind) {
        case T_SPIKE_UP: {   /* apex at top edge center, base at bottom */
            double d = cb - y0;              /* depth of deepest overlap row */
            double w = 0.5 * (d + 1);        /* half width at that row */
            return (cl <= cx + w - 0.5) && (cr >= cx - w + 0.5);
        }
        case T_SPIKE_DOWN: {
            double d = y1 - ct;
            double w = 0.5 * (d + 1);
            return (cl <= cx + w - 0.5) && (cr >= cx - w + 0.5);
        }
        case T_SPIKE_LEFT: { /* apex at left edge center, base at right */
            double d = cr - x0;
            double w = 0.5 * (d + 1);
            return (ct <= cy + w - 0.5) && (cb >= cy - w + 0.5);
        }
        case T_SPIKE_RIGHT: {
            double d = x1 - cl;
            double w = 0.5 * (d + 1);
            return (ct <= cy + w - 0.5) && (cb >= cy - w + 0.5);
        }
    }
    return 0;
}

/* Rect vs generalized spike triangle over an arbitrary inclusive bbox
 * [x0..x1]x[y0..y1]: apex at one edge center, base on the opposite edge,
 * linear widening — reduces exactly to spike_hit_px for a 32x32 bbox. */
static int spike_hit_rect(int l, int r, int t, int b, uint32_t shape,
                          float x0, float y0, float x1, float y1) {
    int cl = l > (int)x0 ? l : (int)x0, cr = r < (int)x1 ? r : (int)x1;
    int ct = t > (int)y0 ? t : (int)y0, cb = b < (int)y1 ? b : (int)y1;
    if (cl > cr || ct > cb) return 0;
    double w = x1 - x0 + 1, h = y1 - y0 + 1;
    double cx = x0 + (w - 1) / 2.0, cy = y0 + (h - 1) / 2.0;
    switch (shape) {
        case IWPACK_KILL_SPIKE_UP: {
            double d = cb - y0, hw = (w / (2.0 * h)) * (d + 1);
            return (cl <= cx + hw - 0.5) && (cr >= cx - hw + 0.5);
        }
        case IWPACK_KILL_SPIKE_DOWN: {
            double d = y1 - ct, hw = (w / (2.0 * h)) * (d + 1);
            return (cl <= cx + hw - 0.5) && (cr >= cx - hw + 0.5);
        }
        case IWPACK_KILL_SPIKE_LEFT: {
            double d = cr - x0, hh = (h / (2.0 * w)) * (d + 1);
            return (ct <= cy + hh - 0.5) && (cb >= cy - hh + 0.5);
        }
        case IWPACK_KILL_SPIKE_RIGHT: {
            double d = x1 - cl, hh = (h / (2.0 * w)) * (d + 1);
            return (ct <= cy + hh - 0.5) && (cb >= cy - hh + 0.5);
        }
    }
    return 1; /* IWPACK_KILL_RECT: bbox overlap already established */
}

/* 1 = dead, checked at integer (rounded) position like instance_place */
static int killer_hit(IWanna* env) {
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + env->hb_l, r = ix + env->hb_r, t = iy + env->hb_t, b = iy + env->hb_b;
    int tx0 = l >= 0 ? l / IW_TILE : (l - IW_TILE + 1) / IW_TILE;
    int tx1 = r >= 0 ? r / IW_TILE : (r - IW_TILE + 1) / IW_TILE;
    int ty0 = t >= 0 ? t / IW_TILE : (t - IW_TILE + 1) / IW_TILE;
    int ty1 = b >= 0 ? b / IW_TILE : (b - IW_TILE + 1) / IW_TILE;
    for (int ty = ty0; ty <= ty1; ty++)
        for (int tx = tx0; tx <= tx1; tx++) {
            uint8_t k = iw_tile_at(env, tx, ty);
            if (k >= T_SPIKE_UP && k <= T_SPIKE_RIGHT)
                if (spike_hit_px(l, r, t, b, tx * IW_TILE, ty * IW_TILE, k)) return 1;
        }
    /* static killer colliders imported from source (empty in classic mode) */
    for (int i = 0; i < env->n_killers; i++) {
        const IWPackKiller* k = &env->killers[i];
        if (l <= k->x1 && r >= k->x0 && t <= k->y1 && b >= k->y0)
            if (spike_hit_rect(l, r, t, b, k->shape, k->x0, k->y0, k->x1, k->y1))
                return 1;
    }
    /* falling out of the room is death (exact source pixel dims in pack mode) */
    int W = env->room_pw > 0 ? env->room_pw : env->tw * IW_TILE;
    int H = env->room_ph > 0 ? env->room_ph : env->th * IW_TILE;
    if (iy + env->hb_t > H + IW_TILE) return 1;
    if (iy + env->hb_b < -IW_TILE) return 1;
    if (ix < -IW_TILE || ix > W + IW_TILE) return 1;
    return 0;
}

static int goal_reached(IWanna* env) {
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + env->hb_l, r = ix + env->hb_r, t = iy + env->hb_t, b = iy + env->hb_b;
    int gl = (int)(env->goal_x - IW_TILE / 2), gr = (int)(env->goal_x + IW_TILE / 2 - 1);
    int gt = (int)(env->goal_y - IW_TILE / 2), gb = (int)(env->goal_y + IW_TILE / 2 - 1);
    return (l <= gr && r >= gl && t <= gb && b >= gt);
}

static inline int on_ground(IWanna* env) {
    return !place_free(env, env->x, env->y + 1);
}

/* ---------- entity behavior (all in C; no callbacks) ---------- */

static void ent_spawn_projectile(IWanna* env, float x, float y,
                                 float vx, float vy, float grav) {
    for (int k = 0; k < env->ent_cap; k++) {
        int i = (env->free_hint + k) % env->ent_cap;
        IWEntity* e = &env->entities[i];
        if (e->type == E_NONE || !(e->flags & EF_ACTIVE)) {
            memset(e, 0, sizeof *e);
            e->type = E_PROJECTILE;
            e->flags = EF_ACTIVE | EF_DEADLY;
            e->collision_mask = CM_PLAYER;
            e->x = x; e->y = y; e->vx = vx; e->vy = vy;
            e->grav = grav;
            env->free_hint = (i + 1) % env->ent_cap;
            if (i + 1 > env->ent_top) env->ent_top = i + 1;
            return;
        }
    }
    /* array full: drop the projectile (bounded memory, never reallocates) */
}

static void update_entities(IWanna* env) {
    float W = (float)(env->tw * IW_TILE), H = (float)(env->th * IW_TILE);
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* e = &env->entities[i];
        if (e->type == E_NONE || !(e->flags & EF_ACTIVE)) continue;
        switch (e->type) {
            case E_PLATFORM:
            case E_SPIKEBALL:
            case E_ENEMY: {
                e->vy += e->grav;
                e->x += e->vx; e->y += e->vy;
                float range = e->params[0];
                if (range > 0 && e->grav == 0) {
                    if (e->vx != 0 && fabsf(e->x - e->params[4]) >= range) e->vx = -e->vx;
                    if (e->vy != 0 && fabsf(e->y - e->params[5]) >= range) e->vy = -e->vy;
                }
                break;
            }
            case E_TRAP:
                if (!(e->flags & EF_DORMANT)) {
                    e->vy += e->grav;
                    e->x += e->vx; e->y += e->vy;
                }
                break;
            case E_PROJECTILE:
                e->vy += e->grav;
                e->x += e->vx; e->y += e->vy;
                break;
            case E_PBULLET: {
                /* GM event order: the lifetime alarm fires BEFORE movement
                 * (bullet moves on 41 frames), solid collision is evaluated
                 * after movement */
                if (--e->timer <= 0) {
                    e->flags &= ~EF_ACTIVE;
                    break;
                }
                e->x += e->vx;
                int bx = gm_round(e->x), by = gm_round(e->y);
                int bl = bx + IW_BULLET_L, br = bx + IW_BULLET_R;
                int bt = by + IW_BULLET_T, bb = by + IW_BULLET_B;
                /* shootable exact entities first: GM fires both the
                 * bullet's Collision_block and the target's
                 * Collision_bullet in the same frame */
                if (env->xs &&
                    iwx_bullet_hit(env, e->x, e->y, bl, br, bt, bb)) {
                    e->flags &= ~EF_ACTIVE;
                    break;
                }
                if (rect_hits_solid(env, bl, br, bt, bb)) {
                    e->flags &= ~EF_ACTIVE;
                    break;
                }
                if (env->save_shoot_mode) {
                    for (int k = 0; k < env->ent_top; k++) {
                        IWEntity* s = &env->entities[k];
                        if (s->type != E_SAVE || !(s->flags & EF_ACTIVE))
                            continue;
                        float shw = s->params[3] > 0 ? s->params[3] : ENT_HW[E_SAVE];
                        float shh = s->params[4] > 0 ? s->params[4] : ENT_HH[E_SAVE];
                        if (ent_rect_hit(s, bl, br, bt, bb, shw, shh))
                            iw_activate_save_shot(env, s);
                        /* the bullet is not consumed by saves (source) */
                    }
                }
                break;
            }
            case E_SAVE:
                if (e->timer > 0) e->timer--;   /* saveTimer cooldown */
                break;
            case E_SHOOTER:
                if (--e->timer <= 0) {
                    e->timer = e->params[0] > 0 ? (int)e->params[0] : 60;
                    float sp = e->params[1] > 0 ? e->params[1] : 4.0f;
                    if (e->params[2] > 0) { /* aimed at the player */
                        float dx = (float)env->x - e->x, dy = (float)env->y - e->y;
                        float d = sqrtf(dx * dx + dy * dy);
                        if (d < 1.0f) d = 1.0f;
                        ent_spawn_projectile(env, e->x, e->y, sp * dx / d, sp * dy / d, 0);
                    } else {
                        ent_spawn_projectile(env, e->x, e->y, e->params[3], e->params[4], 0);
                    }
                }
                break;
            case E_BOSS:
                if (--e->timer <= 0) {
                    e->timer = e->params[0] > 0 ? (int)e->params[0] : 100;
                    for (int k = 0; k < 8; k++) {
                        float a = (float)(k * (3.14159265358979 / 4.0));
                        ent_spawn_projectile(env, e->x, e->y,
                                             3.0f * cosf(a), 3.0f * sinf(a), 0);
                    }
                    if (e->params[1] > 0 && --e->state <= 0) e->flags &= ~EF_ACTIVE;
                }
                break;
            default: break;
        }
        /* moving objects despawn well outside the room */
        if ((e->type == E_PROJECTILE || e->type == E_TRAP ||
             e->type == E_PBULLET ||
             ((e->type == E_SPIKEBALL || e->type == E_ENEMY || e->type == E_PLATFORM) &&
              e->grav != 0)) &&
            (e->x < -64 || e->x > W + 64 || e->y < -64 || e->y > H + 64)) {
            e->flags &= ~EF_ACTIVE;
            if (e->tag > 0 && e->tag < 64)
                env->destroyed_tags |= 1ULL << e->tag;
        }
    }
}

/* Jump-through platforms: land on top, get carried, keep the double jump. */
static void resolve_platforms(IWanna* env) {
    env->on_platform = 0;
    env->landed_tag = -1;
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + env->hb_l, r = ix + env->hb_r, b = iy + env->hb_b;
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* e = &env->entities[i];
        if (!(e->flags & EF_SOLID_TOP) || !(e->flags & EF_ACTIVE)) continue;
        float ptop = e->y - ENT_HH[e->type];
        float pl = e->x - ENT_HW[e->type], pr = e->x + ENT_HW[e->type] - 1;
        if (r < pl || l > pr) continue;
        if (env->vspeed >= e->vy - 0.001 &&
            b >= ptop - 1 && b <= ptop + 8 + env->vspeed) {
            env->y = ptop - 1 - env->hb_b;
            env->vspeed = e->vy > 0 ? e->vy : 0;
            env->djump = 1;           /* landing restores the air jump */
            env->x += e->vx;          /* carried horizontally */
            env->on_platform = 1;
            if (e->tag > 0) env->landed_tag = e->tag;
        }
    }
}

static inline int ent_rect_hit(const IWEntity* e, int l, int r, int t, int b,
                               float hw, float hh) {
    return l <= e->x + hw - 1 && r >= e->x - hw &&
           t <= e->y + hh - 1 && b >= e->y - hh;
}

static int entity_killer_hit(IWanna* env) {
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + env->hb_l, r = ix + env->hb_r, t = iy + env->hb_t, b = iy + env->hb_b;
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* e = &env->entities[i];
        if (!(e->flags & EF_ACTIVE) || !(e->flags & EF_DEADLY)) continue;
        if (!(e->collision_mask & CM_PLAYER)) continue;
        if (e->type == E_TRAP) {
            uint8_t kind = (uint8_t)(T_SPIKE_UP + (int)e->params[4]);
            if (spike_hit_px(l, r, t, b, (int)(e->x - 16), (int)(e->y - 16), kind))
                return 1;
        } else if (ent_rect_hit(e, l, r, t, b, ENT_HW[e->type], ENT_HH[e->type])) {
            return 1;
        }
    }
    return 0;
}

/* solid test for an arbitrary rect (tiles + static solid rects) — used by
 * player bullets; the player's own path keeps the specialized place_free */
static int rect_hits_solid(IWanna* env, int l, int r, int t, int b) {
    int tx0 = l >= 0 ? l / IW_TILE : (l - IW_TILE + 1) / IW_TILE;
    int tx1 = r >= 0 ? r / IW_TILE : (r - IW_TILE + 1) / IW_TILE;
    int ty0 = t >= 0 ? t / IW_TILE : (t - IW_TILE + 1) / IW_TILE;
    int ty1 = b >= 0 ? b / IW_TILE : (b - IW_TILE + 1) / IW_TILE;
    for (int ty = ty0; ty <= ty1; ty++)
        for (int tx = tx0; tx <= tx1; tx++)
            if (iw_tile_at(env, tx, ty) == T_BLOCK) return 1;
    for (int i = 0; i < env->n_solids; i++) {
        const IWPackSolid* s = &env->solids[i];
        if (l <= s->x1 && r >= s->x0 && t <= s->y1 && b >= s->y0) return 1;
    }
    if (env->xs && iwx_solid_hit(env, l, r, t, b)) return 1;
    return 0;
}

/* Source-faithful save activation (saveVeryHard Other_10 + saveGame):
 * per-save 50-frame cooldown, then store the PLAYER's exact position and
 * facing (savex/savey/savew) and the current room as the checkpoint. */
static void iw_activate_save_shot(IWanna* env, IWEntity* e) {
    if (e->timer > 0) return;             /* saveTimer */
    e->timer = IW_SAVE_TIMER;
    env->respawn_x = env->x;
    env->respawn_y = env->y;
    env->respawn_face = env->face;
    env->respawn_room = env->room_id;
    if (e->state == 0 && e->tag > 0 && e->tag < 64)
        env->save_tags |= 1ULL << e->tag;
    e->state = 1;
}

/* playerShoot(): at most 4 bullets alive; bullet at (x, y-2) with
 * hspeed = facing*16, lifetime 42 frames; shooting while overlapping a
 * save activates it directly (the source's contact-save path). */
static void iw_player_shoot(IWanna* env) {
    int alive = 0;
    for (int i = 0; i < env->ent_top; i++)
        if (env->entities[i].type == E_PBULLET &&
            (env->entities[i].flags & EF_ACTIVE)) alive++;
    if (alive < IW_BULLET_MAX) {
        for (int k = 0; k < env->ent_cap; k++) {
            int i = (env->free_hint + k) % env->ent_cap;
            IWEntity* e = &env->entities[i];
            if (e->type == E_NONE || !(e->flags & EF_ACTIVE)) {
                memset(e, 0, sizeof *e);
                e->type = E_PBULLET;
                e->flags = EF_ACTIVE;
                e->collision_mask = CM_TILES;
                e->x = (float)env->x;
                e->y = (float)env->y + IW_BULLET_SPAWN_DY;
                e->vx = env->face >= 0 ? IW_BULLET_SPEED : -IW_BULLET_SPEED;
                e->timer = IW_BULLET_LIFE;
                env->free_hint = (i + 1) % env->ent_cap;
                if (i + 1 > env->ent_top) env->ent_top = i + 1;
                break;
            }
        }
    }
    if (env->save_shoot_mode) {
        int ix = gm_round(env->x), iy = gm_round(env->y);
        int l = ix + env->hb_l, r = ix + env->hb_r, t = iy + env->hb_t, b = iy + env->hb_b;
        for (int i = 0; i < env->ent_top; i++) {
            IWEntity* e = &env->entities[i];
            if (e->type != E_SAVE || !(e->flags & EF_ACTIVE)) continue;
            float shw = e->params[3] > 0 ? e->params[3] : ENT_HW[E_SAVE];
            float shh = e->params[4] > 0 ? e->params[4] : ENT_HH[E_SAVE];
            if (ent_rect_hit(e, l, r, t, b, shw, shh))
                iw_activate_save_shot(env, e);
        }
    }
}

static void fire_trigger(IWanna* env, int id) {
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* f = &env->entities[i];
        if ((f->flags & (EF_ACTIVE | EF_DORMANT)) == (EF_ACTIVE | EF_DORMANT) &&
            f->trigger_id == id) {
            f->flags &= ~EF_DORMANT;
            f->vx = f->params[2];
            f->vy = f->params[3];
        }
    }
}

/* Non-deadly touch interactions: triggers, save points, warps. */
static void player_interactions(IWanna* env) {
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + env->hb_l, r = ix + env->hb_r, t = iy + env->hb_t, b = iy + env->hb_b;
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* e = &env->entities[i];
        if (!(e->flags & EF_ACTIVE)) continue;
        switch (e->type) {
            case E_TRIGGER:
                if (e->state == 0 &&
                    ent_rect_hit(e, l, r, t, b, e->params[0], e->params[1])) {
                    e->state = 1;
                    fire_trigger(env, e->trigger_id);
                }
                break;
            case E_SAVE: {
                /* touch activation is the LEGACY research mode; the
                 * source-faithful mode (save_shoot_mode, default in exact-
                 * game packs) activates saves by shooting them instead */
                if (env->save_shoot_mode) break;
                /* per-instance extents (params[3],[4]) override defaults
                 * (source save bbox); params[0] = difficulty mask */
                float shw = e->params[3] > 0 ? e->params[3] : ENT_HW[E_SAVE];
                float shh = e->params[4] > 0 ? e->params[4] : ENT_HH[E_SAVE];
                if (ent_rect_hit(e, l, r, t, b, shw, shh)) {
                    env->respawn_x = e->x;
                    env->respawn_y = e->y +
                        (e->params[4] > 0 ? shh : IW_TILE / 2.0f) - 1 - env->hb_b;
                    env->respawn_room = env->room_id;
                    if (e->state == 0 && e->tag > 0 && e->tag < 64)
                        env->save_tags |= 1ULL << e->tag;
                    e->state = 1;
                }
                break;
            }
            case E_WARP: {
                /* per-instance extents (params[3],[4]) override the default
                 * warp hitbox — source warps are stretched region strips */
                float hw = e->params[3] > 0 ? e->params[3] : ENT_HW[E_WARP];
                float hh = e->params[4] > 0 ? e->params[4] : ENT_HH[E_WARP];
                if (ent_rect_hit(e, l, r, t, b, hw, hh)) {
                    /* params[2] = destination room + 1 in pack mode
                     * (0 = same room, the classic single-room behavior).
                     * params[5] = mode: 0 absolute+stop, 1 offset+keep,
                     * 2 target room start point, 3 absolute+keep,
                     * 4 x-absolute/y-offset+keep, 5 x-offset/y-absolute+keep
                     * (source warps set position per axis). */
                    int mode = (int)e->params[5];
                    if (env->pack && e->params[2] > 0.5f) {
                        env->pending_room = (int)e->params[2] - 1;
                        env->pending_use_start = 0;
                        env->pending_xop0 = e->trigger_id;
                        env->pending_xnops = e->state;
                        if (mode == 1) {
                            env->pending_x = (float)(env->x + e->params[0]);
                            env->pending_y = (float)(env->y + e->params[1]);
                            env->pending_keep_speed = 1;
                        } else if (mode == 2) {
                            env->pending_keep_speed = 0;
                            env->pending_use_start = 1;
                        } else if (mode == 4) {
                            env->pending_x = e->params[0];
                            env->pending_y = (float)(env->y + e->params[1]);
                            env->pending_keep_speed = 1;
                        } else if (mode == 5) {
                            env->pending_x = (float)(env->x + e->params[0]);
                            env->pending_y = e->params[1];
                            env->pending_keep_speed = 1;
                        } else {
                            env->pending_x = e->params[0];
                            env->pending_y = e->params[1];
                            env->pending_keep_speed = (mode == 3);
                        }
                        break;
                    }
                    env->x = mode == 5 ? env->x + e->params[0] : e->params[0];
                    env->y = mode == 4 ? env->y + e->params[1] : e->params[1];
                    if (!(env->pack && mode >= 3)) {
                        env->hspeed = 0; env->vspeed = 0;
                    }
                    if (env->xs && e->state > 0)
                        iwx_run_ops(env, e->trigger_id, e->state, -1);
                    double wdx = env->goal_x - env->x, wdy = env->goal_y - env->y;
                    env->prev_goal_dist = sqrt(wdx * wdx + wdy * wdy);
                }
                break;
            }
            default: break;
        }
    }
}

#include "exact_impl.h"

static void reset_entities(IWanna* env) {
    if (!env->entities) return;
    memset(env->entities, 0, sizeof(IWEntity) * (size_t)env->ent_cap);
    for (int i = 0; i < env->spawn_count; i++) env->entities[i] = env->spawns[i];
    env->free_hint = env->spawn_count;
    env->ent_top = env->spawn_count;
}

/* ---------- trigger/event system (all in C; no callbacks) ---------- */

/* Gates block movement by stamping solid tiles into the live tile grid.
 * Opening restores the pristine tiles copied at reset. */
static void gate_stamp(IWanna* env, IWEntity* e, int closed) {
    int tx = (int)e->params[0], ty = (int)e->params[1];
    int w = (int)e->params[2], h = (int)e->params[3];
    for (int dy = 0; dy < h; dy++)
        for (int dx = 0; dx < w; dx++) {
            int x = tx + dx, y = ty + dy;
            if (x < 0 || y < 0 || x >= env->tw || y >= env->th) continue;
            env->tiles[y * env->tw + x] =
                closed ? T_BLOCK : (env->tiles0 ? env->tiles0[y * env->tw + x]
                                                : T_EMPTY);
        }
    e->state = closed;
}

static void ent_spawn_generic(IWanna* env, int type, float x, float y,
                              float vx, float vy, float grav, int deadly) {
    for (int k = 0; k < env->ent_cap; k++) {
        int i = (env->free_hint + k) % env->ent_cap;
        IWEntity* e = &env->entities[i];
        if (e->type == E_NONE || !(e->flags & EF_ACTIVE)) {
            memset(e, 0, sizeof *e);
            e->type = (uint8_t)type;
            e->flags = EF_ACTIVE | (deadly ? EF_DEADLY : 0) |
                       (type == E_PLATFORM ? EF_SOLID_TOP : 0);
            e->collision_mask = CM_PLAYER;
            e->x = x; e->y = y; e->vx = vx; e->vy = vy; e->grav = grav;
            e->timer = 1;
            env->free_hint = (i + 1) % env->ent_cap;
            if (i + 1 > env->ent_top) env->ent_top = i + 1;
            return;
        }
    }
}

static void exec_action(IWanna* env, const IWAction* a) {
    if (a->type == ACT_SPAWN) {
        /* p[0]=type p[1]=x px p[2]=y px p[3]=vx p[4]=vy p[5]=grav;
         * tag>=0 means deadly (parser encodes deadly=0 as tag=-1) */
        ent_spawn_generic(env, (int)a->p[0], a->p[1], a->p[2],
                          a->p[3], a->p[4], a->p[5], a->tag >= 0 ? 1 : 0);
        return;
    }
    if (a->type == ACT_START_TIMER) {
        for (int i = 0; i < env->event_count; i++) {
            IWEvent* ev = &env->events[i];
            if (ev->when == W_TIMER && ev->id == a->tag) {
                ev->fired = 0;
                ev->countdown = ev->delay;
            }
        }
        return;
    }
    if (a->type == ACT_SET_FLAG || a->type == ACT_CLEAR_FLAG) {
        if (a->tag > 0 && a->tag < 64) {
            if (a->type == ACT_SET_FLAG) env->gflags |= 1ULL << a->tag;
            else                         env->gflags &= ~(1ULL << a->tag);
        }
        return;
    }
    if (a->type == ACT_TELEPORT && a->tag < 0) {   /* player teleport */
        env->x = a->p[0]; env->y = a->p[1];
        env->hspeed = 0; env->vspeed = 0;
        double dx = env->goal_x - env->x, dy = env->goal_y - env->y;
        env->prev_goal_dist = sqrt(dx * dx + dy * dy);
        return;
    }
    /* entity-targeted actions apply to every entity with the tag */
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* e = &env->entities[i];
        if (e->type == E_NONE || e->tag != a->tag) continue;
        switch (a->type) {
            case ACT_ACTIVATE:
                e->flags |= EF_ACTIVE;
                if (e->type == E_GATE) gate_stamp(env, e, e->state);
                break;
            case ACT_DEACTIVATE: e->flags &= ~EF_ACTIVE; break;
            case ACT_LAUNCH:
                e->vx = a->p[0]; e->vy = a->p[1];
                e->flags &= ~EF_DORMANT;
                e->flags |= EF_ACTIVE;
                if (a->p[2] != 0) e->grav = a->p[2];
                break;
            case ACT_SET_GRAVITY: e->grav = a->p[0]; break;
            case ACT_MOVE: e->x += a->p[0]; e->y += a->p[1]; break;
            case ACT_TELEPORT: e->x = a->p[0]; e->y = a->p[1]; break;
            case ACT_DESTROY:
                e->flags &= ~EF_ACTIVE;
                if (e->type == E_GATE && e->state) gate_stamp(env, e, 0);
                if (e->tag > 0 && e->tag < 64)
                    env->destroyed_tags |= 1ULL << e->tag;
                break;
            case ACT_MAKE_KILLER:
                e->flags |= EF_DEADLY;
                e->flags &= ~EF_DORMANT;
                break;
            case ACT_MAKE_HARMLESS: e->flags &= ~EF_DEADLY; break;
            case ACT_MAKE_SOLID: e->flags |= EF_SOLID_TOP; break;
            case ACT_MAKE_UNSOLID: e->flags &= ~EF_SOLID_TOP; break;
            case ACT_OPEN_GATE:
                if (e->type == E_GATE && e->state) gate_stamp(env, e, 0);
                break;
            case ACT_CLOSE_GATE:
                if (e->type == E_GATE && !e->state) gate_stamp(env, e, 1);
                break;
            case ACT_SET_DIR:
                if (e->type == E_TRAP) e->params[4] = a->p[0];
                break;
            default: break;
        }
    }
}

static void run_event_actions(IWanna* env, IWEvent* ev) {
    for (int k = 0; k < ev->n_actions; k++)
        exec_action(env, &env->ev_actions[ev->first_action + k]);
}

/* Player "origin" for region tests: the GM8 sprite origin (x, y). */
static int point_in_region(const IWEvent* ev, double x, double y) {
    return x >= ev->x0 && x <= ev->x1 && y >= ev->y0 && y <= ev->y1;
}

static void update_events(IWanna* env) {
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + env->hb_l, r = ix + env->hb_r, t = iy + env->hb_t, b = iy + env->hb_b;
    for (int i = 0; i < env->event_count; i++) {
        IWEvent* ev = &env->events[i];

        /* 1. pending delayed actions */
        if (ev->countdown >= 0) {
            if (ev->countdown == 0) {
                run_event_actions(env, ev);
                if (ev->when == W_TIMER && ev->period > 0 && !ev->once)
                    ev->countdown = ev->period;
                else
                    ev->countdown = -1;
            } else {
                ev->countdown--;
            }
            if (ev->when == W_TIMER) continue;
        }

        /* 2. condition check (edge-triggered where it matters) */
        if (ev->once && ev->fired) continue;
        int hit = 0;
        switch (ev->when) {
            case W_ENTER_REGION: {
                int in = point_in_region(ev, env->x, env->y);
                hit = in && !ev->inside;
                ev->inside = (uint8_t)in;
                break;
            }
            case W_LEAVE_REGION: {
                int in = point_in_region(ev, env->x, env->y);
                hit = !in && ev->inside;
                ev->inside = (uint8_t)in;
                break;
            }
            case W_TOUCH_OBJECT:
                for (int k = 0; k < env->ent_top && !hit; k++) {
                    IWEntity* e = &env->entities[k];
                    if (e->tag != ev->subject || !(e->flags & EF_ACTIVE)) continue;
                    float hw = ENT_HW[e->type] > 0 ? ENT_HW[e->type] : 16;
                    float hh = ENT_HH[e->type] > 0 ? ENT_HH[e->type] : 16;
                    if (e->type == E_TRIGGER) { hw = e->params[0]; hh = e->params[1]; }
                    hit = ent_rect_hit(e, l, r, t, b, hw, hh);
                }
                break;
            case W_LAND_ON_OBJECT:
                hit = env->on_platform && !env->prev_on_platform &&
                      env->landed_tag == ev->subject;
                break;
            case W_PASS_X:
                hit = (env->prev_x < ev->x0) != (env->x < ev->x0);
                if (hit && ev->dir > 0) hit = env->x > env->prev_x;
                if (hit && ev->dir < 0) hit = env->x < env->prev_x;
                break;
            case W_PASS_Y:
                hit = (env->prev_y < ev->y0) != (env->y < ev->y0);
                if (hit && ev->dir > 0) hit = env->y > env->prev_y;
                if (hit && ev->dir < 0) hit = env->y < env->prev_y;
                break;
            case W_OBJECT_DESTROYED:
                hit = ev->subject > 0 && ev->subject < 64 &&
                      (env->destroyed_tags >> ev->subject) & 1ULL;
                break;
            case W_SAVE_ACTIVATED:
                hit = ev->subject > 0 && ev->subject < 64 &&
                      (env->save_tags >> ev->subject) & 1ULL;
                break;
            case W_FLAG_SET:
                hit = ev->subject > 0 && ev->subject < 64 &&
                      (env->gflags >> ev->subject) & 1ULL;
                break;
            default: break;  /* ROOM_ENTER and TIMER armed at reset */
        }
        if (hit && ev->countdown < 0) {
            ev->fired = 1;
            ev->countdown = ev->delay;
        }
    }
}

/* Arm events at episode start: restore pristine tiles, stamp closed gates,
 * schedule room_enter and auto timers. */
static void reset_events(IWanna* env) {
    env->destroyed_tags = 0;
    env->save_tags = 0;
    env->landed_tag = -1;
    env->prev_on_platform = 0;
    if (env->tiles0)
        memcpy(env->tiles, env->tiles0, (size_t)(env->tw * env->th));
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* e = &env->entities[i];
        if (e->type == E_GATE && (e->flags & EF_ACTIVE) && e->state)
            gate_stamp(env, e, 1);
    }
    for (int i = 0; i < env->event_count; i++) {
        IWEvent* ev = &env->events[i];
        ev->fired = 0;
        ev->inside = 0;
        ev->countdown = -1;
        if (ev->when == W_ROOM_ENTER ||
            (ev->when == W_TIMER && ev->auto_arm))
            ev->countdown = ev->delay;
    }
}

/* ---------- game-pack mode: room loading & transitions ----------
 * A pack keeps every room compiled in one decoded blob (IWPackRT). The env
 * owns live buffers sized ONCE at load from the pack-wide maxima; entering
 * a room is a bounded memcpy of that room's tiles/spawns/events/actions —
 * no allocation, no parsing. Rooms reset on entry (fangame semantics);
 * global flags (env->gflags), the active save (respawn_*), and the episode
 * clock persist across transitions.
 */

static void iw_pack_copy_room(IWanna* env, int room) {
    const IWPackRoom* r = &env->pack->rooms[room];
    env->room_id = room;
    env->tw = (int)r->tw;
    env->th = (int)r->th;
    env->room_pw = (int)r->pw;
    env->room_ph = (int)r->ph;
    memcpy(env->tiles0, r->tiles, (size_t)r->tw * r->th);
    memcpy(env->tiles, env->tiles0, (size_t)r->tw * r->th);
    env->start_x = r->start_x;
    env->start_y = r->start_y;
    env->goal_x = r->goal_x;
    env->goal_y = r->goal_y;
    env->room_has_goal = (int)r->has_goal;
    /* static colliders: immutable, referenced in place (no copy) */
    env->solids = r->solids;
    env->n_solids = (int)r->n_solids;
    env->killers = r->killers;
    env->n_killers = (int)r->n_killers;

    env->spawn_count = (int)r->n_spawns;
    for (uint32_t i = 0; i < r->n_spawns; i++) {
        const IWPackEnt* s = &r->spawns[i];
        IWEntity* e = &env->spawns[i];
        memset(e, 0, sizeof *e);
        e->type = (uint8_t)s->type;
        e->flags = s->flags;
        /* difficulty-gated saves: params[0] = mask of difficulties where
         * this save exists in the source (bit d set = present on diff d) */
        if (e->type == E_SAVE && s->params[0] > 0 &&
            !(((int)s->params[0] >> env->difficulty) & 1))
            e->flags &= ~EF_ACTIVE;
        e->trigger_id = s->trigger_id;
        e->tag = s->tag;
        e->collision_mask = s->collision_mask;
        e->x = s->x; e->y = s->y; e->vx = s->vx; e->vy = s->vy;
        e->grav = s->grav;
        e->state = s->state;
        e->timer = s->timer;
        memcpy(e->params, s->params, sizeof e->params);
    }
    env->event_count = (int)r->n_events;
    for (uint32_t i = 0; i < r->n_events; i++) {
        const IWPackEvt* s = &r->events[i];
        IWEvent* ev = &env->events[i];
        memset(ev, 0, sizeof *ev);
        ev->when = (uint8_t)s->when;
        ev->once = (uint8_t)s->once;
        ev->auto_arm = (uint8_t)s->auto_arm;
        ev->dir = (int8_t)s->dir;
        ev->id = s->id;
        ev->subject = s->subject;
        ev->x0 = s->x0; ev->y0 = s->y0; ev->x1 = s->x1; ev->y1 = s->y1;
        ev->delay = s->delay;
        ev->period = s->period;
        ev->first_action = s->first_action;
        ev->n_actions = s->n_actions;
        ev->countdown = -1;
    }
    env->ev_action_count = (int)r->n_actions;
    for (uint32_t i = 0; i < r->n_actions; i++) {
        const IWPackAct* s = &r->actions[i];
        IWAction* a = &env->ev_actions[i];
        a->type = (uint8_t)s->type;
        a->tag = s->tag;
        memcpy(a->p, s->p, sizeof a->p);
    }
    reset_entities(env);
    reset_events(env);
    if (env->xs) iwx_load_room(env, room);
}

/* Mid-episode transition (warp touch, edge exit). The previous room's
 * transient state is discarded — rooms reset on re-entry, as in the GM8
 * fangame engines — while gflags, the save point, and tick persist. */
static void iw_pack_room_switch(IWanna* env, int room, double px, double py,
                                int keep_speed) {
    iw_pack_copy_room(env, room);
    env->x = px;
    env->y = py;
    if (!keep_speed) { env->hspeed = 0; env->vspeed = 0; }
    env->on_platform = 0;
    env->prev_on_platform = 0;
    env->prev_x = env->x;
    env->prev_y = env->y;
    env->room_transitions += 1;
    double dx = env->goal_x - env->x, dy = env->goal_y - env->y;
    env->prev_goal_dist = sqrt(dx * dx + dy * dy);
    if (env->xs) iwx_after_spawn(env);
}

/* Edge transitions: leaving through a linked room edge enters the adjacent
 * room at the opposite edge, preserving velocity and the off-axis
 * coordinate (clamped inside the destination). Unlinked edges keep the
 * classic behavior (out-of-room death in killer_hit). */
static void iw_pack_check_edge(IWanna* env) {
    const IWPackRoom* cur = &env->pack->rooms[env->room_id];
    double W = env->room_pw > 0 ? env->room_pw : env->tw * IW_TILE;
    double H = env->room_ph > 0 ? env->room_ph : env->th * IW_TILE;
    int target = -1;
    int edge = -1;
    if (env->x < 0 && cur->edge[IWPACK_EDGE_L] >= 0) {
        target = cur->edge[IWPACK_EDGE_L]; edge = IWPACK_EDGE_L;
    } else if (env->x > W && cur->edge[IWPACK_EDGE_R] >= 0) {
        target = cur->edge[IWPACK_EDGE_R]; edge = IWPACK_EDGE_R;
    } else if (env->y < 0 && cur->edge[IWPACK_EDGE_U] >= 0) {
        target = cur->edge[IWPACK_EDGE_U]; edge = IWPACK_EDGE_U;
    } else if (env->y > H && cur->edge[IWPACK_EDGE_D] >= 0) {
        target = cur->edge[IWPACK_EDGE_D]; edge = IWPACK_EDGE_D;
    }
    if (target < 0) return;
    const IWPackRoom* dst = &env->pack->rooms[target];
    double DW = dst->pw, DH = dst->ph;
    double nx = env->x, ny = env->y;
    if (edge == IWPACK_EDGE_L)      nx = DW - 1 + env->hb_l;   /* enter at right edge */
    else if (edge == IWPACK_EDGE_R) nx = 1 - env->hb_l;        /* enter at left edge */
    else if (edge == IWPACK_EDGE_U) ny = DH - 1 + env->hb_t;   /* enter at bottom */
    else                            ny = 1 - env->hb_t;        /* enter at top */
    if (nx < -env->hb_l) nx = -env->hb_l;
    if (nx > DW - 1 - env->hb_r) nx = DW - 1 - env->hb_r;
    if (ny < -env->hb_t) ny = -env->hb_t;
    if (ny > DH - 1 - env->hb_b) ny = DH - 1 - env->hb_b;
    env->pending_room = target;
    env->pending_x = (float)nx;
    env->pending_y = (float)ny;
    env->pending_keep_speed = 1;
    env->pending_use_start = 0;
}

static int iw_pack_do_pending(IWanna* env) {
    if (env->pending_room < 0) return 0;
    int room = env->pending_room;
    env->pending_room = -1;
    if (env->pending_use_start) {
        /* source semantics: player is destroyed and respawns fresh at the
         * destination room's start point (warp with no warpX/warpY) */
        env->pending_use_start = 0;
        const IWPackRoom* dst = &env->pack->rooms[room];
        iw_pack_room_switch(env, room, dst->start_x, dst->start_y, 0);
        env->djump = 1;
        env->prev_jump_held = 0;
        if (env->xs && env->pending_xnops > 0) {
            iwx_run_ops(env, env->pending_xop0, env->pending_xnops, -1);
            env->pending_xnops = 0;
            if (env->xs->spawn_boost != 0) {
                env->vspeed = env->xs->spawn_boost;
                env->xs->spawn_boost = 0;
            }
        }
        return 1;
    }
    iw_pack_room_switch(env, room, env->pending_x, env->pending_y,
                        env->pending_keep_speed);
    if (env->xs && env->pending_xnops > 0) {
        iwx_run_ops(env, env->pending_xop0, env->pending_xnops, -1);
        env->pending_xnops = 0;
        if (env->xs->spawn_boost != 0) {
            env->vspeed = env->xs->spawn_boost;
            env->xs->spawn_boost = 0;
        }
    }
    return 1;
}

/* Load a compiled .iwpack blob: decode once, size the live buffers from the
 * pack maxima, and enter the start room. Returns 0 on success; on failure
 * the env is untouched apart from freed classic-level buffers. */
static int iw_load_pack_mem(IWanna* env, const uint8_t* data, size_t len,
                            char* err, size_t errlen) {
    IWPackRT* rt = iwpack_load(data, len, err, errlen);
    if (!rt) return -1;

    free(env->tiles);   env->tiles = NULL;
    free(env->tiles0);  env->tiles0 = NULL;
    free(env->spawns);  env->spawns = NULL;
    free(env->entities); env->entities = NULL;
    free(env->events);  env->events = NULL;
    free(env->ev_actions); env->ev_actions = NULL;

    uint32_t mt = rt->hdr.max_tiles;
    uint32_t ms = rt->hdr.max_spawns ? rt->hdr.max_spawns : 1;
    uint32_t me = rt->hdr.max_events ? rt->hdr.max_events : 1;
    uint32_t ma = rt->hdr.max_actions ? rt->hdr.max_actions : 1;
    env->ent_cap = (int)(ms * 2 > 2048 ? ms * 2 : 2048);
    env->tiles = (uint8_t*)calloc(mt, 1);
    env->tiles0 = (uint8_t*)calloc(mt, 1);
    env->spawns = (IWEntity*)calloc(ms, sizeof(IWEntity));
    env->entities = (IWEntity*)calloc((size_t)env->ent_cap, sizeof(IWEntity));
    env->events = (IWEvent*)calloc(me, sizeof(IWEvent));
    env->ev_actions = (IWAction*)calloc(ma, sizeof(IWAction));
    if (!env->tiles || !env->tiles0 || !env->spawns || !env->entities ||
        !env->events || !env->ev_actions) {
        iwpack_free_rt(rt);
        iwpack_err(err, errlen, "out of memory");
        return -1;
    }
    env->pack = rt;
    if (iwx_load_section(env, err, errlen) < 0) {
        env->pack = NULL;
        iwpack_free_rt(rt);
        return -1;
    }
    env->save_shoot_mode = 1;  /* exact-game default: shot-activated saves */
    env->start_room = (int)rt->hdr.start_room;
    env->respawn_room = env->start_room;
    env->pending_room = -1;
    env->gflags = 0;
    env->room_transitions = 0;
    env->free_hint = 0;
    iw_pack_copy_room(env, env->start_room);
    return 0;
}

/* Restore the source checkpoint state (death retry / "R" quick-retry):
 * in pack mode the room is FULLY reset (source reset_game does
 * room_goto(saveroom), recreating all room objects; bullets and dynamic
 * state are cleared) and the player returns to the exact saved position
 * and facing (load_game_execute: savex/savey/savew) with fresh movement
 * state (player Create: djump=true, speeds 0). Progression flags
 * (savedata) and the active save persist. Classic single-room mode keeps
 * its historical semantics: respawn position only, no room reset. */
static void iw_respawn_to_checkpoint(IWanna* env) {
    if (env->pack) {
        iw_pack_copy_room(env, env->respawn_room);
        env->face = env->respawn_face >= 0 ? 1 : -1;
    }
    env->x = env->respawn_x;
    env->y = env->respawn_y;
    env->hspeed = 0; env->vspeed = 0;
    env->djump = 1;
    env->prev_jump_held = 0;
    env->prev_shoot_held = 0;
    env->on_platform = 0;
    env->prev_on_platform = 0;
    env->pending_room = -1;
    env->pending_use_start = 0;
    env->attempt += 1;
    env->prev_x = env->x;
    env->prev_y = env->y;
    double rdx = env->goal_x - env->x, rdy = env->goal_y - env->y;
    env->prev_goal_dist = sqrt(rdx * rdx + rdy * rdy);
    if (env->xs) iwx_after_spawn(env);
}

/* ---------- observations ---------- */

static void compute_observations(IWanna* env) {
    float* o = env->observations;
    double W = env->tw * IW_TILE, H = env->th * IW_TILE;
    o[0] = (float)(2.0 * env->x / W - 1.0);
    o[1] = (float)(2.0 * env->y / H - 1.0);
    o[2] = (float)(env->hspeed / IW_MAXSPEED);
    o[3] = (float)(env->vspeed / (IW_MAXVSPEED + IW_GRAV));
    o[4] = (env->djump < IW_MAXJUMPS) ? 1.0f : 0.0f;
    o[5] = (on_ground(env) || env->on_platform) ? 1.0f : 0.0f;
    o[6] = (float)((env->goal_x - env->x) / W);
    o[7] = (float)((env->goal_y - env->y) / H);
    int ptx = gm_round(env->x) / IW_TILE, pty = gm_round(env->y) / IW_TILE;
    int i = IW_OBS_BASE;
    for (int dy = -(IW_LOCAL_H / 2); dy <= IW_LOCAL_H / 2; dy++)
        for (int dx = -(IW_LOCAL_W / 2); dx <= IW_LOCAL_W / 2; dx++) {
            int tx = ptx + dx, ty = pty + dy;
            uint8_t v;
            if (tx < 0 || ty < 0 || tx >= env->tw || ty >= env->th) v = T_BLOCK;
            else v = env->tiles[ty * env->tw + tx];
            o[i++] = (float)v / 6.0f;
        }

    /* K nearest active, visible entities (triggers are invisible), sorted by
     * squared distance. Features per slot: dx, dy, vx, vy, signed type
     * (negative = deadly). Zero-padded when fewer than K entities exist.
     * Exact-layer entities (xents) join the scan with index offset 1<<20. */
    int   best[IW_OBS_K];
    float bestd[IW_OBS_K];
    int nbest = 0;
    for (int k = 0; k < env->ent_top; k++) {
        IWEntity* e = &env->entities[k];
        if (!(e->flags & EF_ACTIVE) || e->type == E_TRIGGER || e->type == E_NONE)
            continue;
        float dx = e->x - (float)env->x, dy = e->y - (float)env->y;
        float d2 = dx * dx + dy * dy;
        if (nbest < IW_OBS_K) {
            int j = nbest++;
            while (j > 0 && bestd[j - 1] > d2) {
                bestd[j] = bestd[j - 1]; best[j] = best[j - 1]; j--;
            }
            bestd[j] = d2; best[j] = k;
        } else if (d2 < bestd[IW_OBS_K - 1]) {
            int j = IW_OBS_K - 1;
            while (j > 0 && bestd[j - 1] > d2) {
                bestd[j] = bestd[j - 1]; best[j] = best[j - 1]; j--;
            }
            bestd[j] = d2; best[j] = k;
        }
    }
    if (env->xs) {
        IWXState* xs = env->xs;
        for (int k = 0; k < xs->n_ents; k++) {
            IWXEnt* e = &xs->ents[k];
            if (!e->alive || !e->active) continue;
            if (e->cls == XB_TRIGGER || e->cls == XB_MARKER ||
                e->cls == XB_WALLSTRIP || e->cls == XB_WATER) continue;
            float dx = e->x - (float)env->x, dy = e->y - (float)env->y;
            float d2 = dx * dx + dy * dy;
            int key = k + (1 << 20);
            if (nbest < IW_OBS_K) {
                int j = nbest++;
                while (j > 0 && bestd[j - 1] > d2) {
                    bestd[j] = bestd[j - 1]; best[j] = best[j - 1]; j--;
                }
                bestd[j] = d2; best[j] = key;
            } else if (d2 < bestd[IW_OBS_K - 1]) {
                int j = IW_OBS_K - 1;
                while (j > 0 && bestd[j - 1] > d2) {
                    bestd[j] = bestd[j - 1]; best[j] = best[j - 1]; j--;
                }
                bestd[j] = d2; best[j] = key;
            }
        }
    }
    for (int s = 0; s < IW_OBS_K; s++) {
        if (s < nbest) {
            float f0, f1, f2, f3, f4;
            if (best[s] >= (1 << 20)) {
                IWXEnt* e = &env->xs->ents[best[s] - (1 << 20)];
                f0 = (float)((e->x - env->x) / W);
                f1 = (float)((e->y - env->y) / H);
                f2 = e->vx / 10.0f; f3 = e->vy / 10.0f;
                f4 = 13.0f / IW_OBS_TYPE_NORM;   /* capped to 1.0 below */
                if (e->flags & XEF_KILLER) f4 = -f4;
            } else {
                IWEntity* e = &env->entities[best[s]];
                f0 = (float)((e->x - env->x) / W);
                f1 = (float)((e->y - env->y) / H);
                f2 = e->vx / 10.0f; f3 = e->vy / 10.0f;
                f4 = (float)e->type / IW_OBS_TYPE_NORM;
                if (e->flags & EF_DEADLY) f4 = -f4;
            }
            float f[5] = { f0, f1, f2, f3, f4 };
            for (int q = 0; q < IW_OBS_ENT_F; q++) {
                float v = f[q];
                if (v > 1.0f) v = 1.0f;
                if (v < -1.0f) v = -1.0f;
                o[i++] = v;
            }
        } else {
            for (int q = 0; q < IW_OBS_ENT_F; q++) o[i++] = 0.0f;
        }
    }
}

/* ---------- lifecycle ---------- */

static void add_log(IWanna* env, float score, float death) {
    env->log.perf += score;
    env->log.score += score;
    env->log.episode_return += env->ep_return;
    env->log.episode_length += env->tick;
    env->log.death += death;
    env->log.n += 1;
}

static void sample_goal(IWanna* env) {
    if (!env->random_goal) return;
    /* uniform over empty tiles that have a block directly below (standable)
       or any empty tile as fallback */
    int tries = 200;
    while (tries--) {
        int tx = (int)(iw_rand(env) % (uint64_t)env->tw);
        int ty = (int)(iw_rand(env) % (uint64_t)env->th);
        if (iw_tile_at(env, tx, ty) == T_EMPTY &&
            (ty + 1 >= env->th || iw_tile_at(env, tx, ty + 1) == T_BLOCK)) {
            env->goal_x = tx * IW_TILE + IW_TILE / 2.0;
            env->goal_y = ty * IW_TILE + IW_TILE / 2.0;
            return;
        }
    }
}

static void c_reset(IWanna* env) {
    if (env->pack) {
        /* pack mode: every episode starts in the start room with a clean
         * progression state (flags, save, transition count). The room is
         * re-copied unconditionally so start-room/difficulty changes made
         * before reset always take effect. */
        env->gflags = 0;
        iw_pack_copy_room(env, env->start_room);
        env->respawn_room = env->start_room;
        env->pending_room = -1;
        env->pending_use_start = 0;
        env->room_transitions = 0;
    }
    env->x = env->start_x;
    env->y = env->start_y;
    env->hspeed = 0; env->vspeed = 0;
    env->djump = 1;               /* engine Create_0: djump=1 (one air jump available) */
    env->face = 1;
    env->prev_jump_held = 0;
    env->prev_shoot_held = 0;
    env->respawn_face = 1;
    env->attempt = 1;             /* task reset starts attempt #1 */
    env->tick = 0;
    env->ep_return = 0;
    env->on_platform = 0;
    env->deaths = 0;
    env->respawn_x = env->start_x;
    env->respawn_y = env->start_y;
    env->prev_x = env->x;
    env->prev_y = env->y;
    reset_entities(env);
    reset_events(env);
    if (env->xs) iwx_after_spawn(env);
    sample_goal(env);
    double dx = env->goal_x - env->x, dy = env->goal_y - env->y;
    env->prev_goal_dist = sqrt(dx * dx + dy * dy);
    compute_observations(env);
}

/* One 50Hz frame. Port of the Renex Player step event + GM8 built-in update. */
static void c_step(IWanna* env) {
    env->rewards[0] = 0;
    env->terminals[0] = 0;
    env->last_event = 0;

    env->prev_x = env->x;            /* for pass_x / pass_y events */
    env->prev_y = env->y;
    env->prev_on_platform = env->on_platform;  /* for land_on_object */

    int action = env->actions[0];
    if (action < 0) action = 0;
    if (action >= IW_NUM_ACTIONS) action = IW_NUM_ACTIONS - 1;
    /* a = shoot_held*6 + 2*(h+1) + jump_held; 0..5 == legacy space */
    int shoot_held = action / IW_NUM_ACTIONS_LEGACY;
    int a6 = action % IW_NUM_ACTIONS_LEGACY;
    int jump_held = a6 % 2;
    int h = (a6 / 2) - 1;       /* -1, 0, 1 */
    int pressed = jump_held && !env->prev_jump_held;
    int released = !jump_held && env->prev_jump_held;
    int shoot_pressed = shoot_held && !env->prev_shoot_held;
    env->prev_jump_held = jump_held;
    env->prev_shoot_held = shoot_held;

    int xmode = env->xs && (env->xs->hdr.flags & IWXF_PHYSICS);
    int hpl = (h == -1 && env->prev_h != -1);
    int hpr = (h == 1 && env->prev_h != 1);
    env->prev_h = h;

    /* exact layer: room entities step BEFORE the player (GM object order) */
    if (env->xs) iwx_frame_begin(env);

    if (xmode) {
        iwx_player_step(env, h, jump_held, pressed, released, shoot_pressed,
                        hpl, hpr);
    } else {
    /* --- ///movement --- */
    if (h != 0) env->face = h;
    env->hspeed = IW_MAXSPEED * h;
    /* shoot on the press edge, after facing updates (player Step order) */
    if (shoot_pressed) iw_player_shoot(env);
    if (env->hspeed == 0) env->x = gm_round(env->x); /* engine: if (hspeed=0) x=round(x) */
    if (env->vspeed > IW_MAXVSPEED) env->vspeed = IW_MAXVSPEED;

    if (pressed) { /* player_jump() */
        if (on_ground(env) || env->on_platform) {
            env->vspeed = -IW_JUMP;
            env->djump = 1;
        } else if (env->djump < IW_MAXJUMPS) {
            env->vspeed = -IW_JUMP2;
            env->djump += 1;
        }
    }
    if (released && env->vspeed < 0) env->vspeed *= IW_RELEASE_MULT;

    /* --- ///solid collision (verbatim port) --- */
    double rx, rxnext, oldvsp;
    if (env->hspeed >= 0) { rx = floor(env->x); rxnext = floor(env->x + env->hspeed); }
    else { rx = ceil(env->x); rxnext = ceil(env->x + env->hspeed); }
    oldvsp = env->vspeed;
    env->vspeed += IW_GRAV;

    if (!place_free(env, rxnext, env->y + env->vspeed)) {
        if (!place_free(env, rxnext, env->y)) {
            env->x = rx;
            int a = (int)ceil(fabs(env->hspeed));
            int s = iw_sign(env->hspeed);
            for (int i = 0; i <= a; i++) {
                env->x += s;
                if (!place_free(env, env->x, env->y)) { env->x -= s; env->hspeed = 0; break; }
            }
            env->x -= env->hspeed;
        }
        if (!place_free(env, rx, env->y + env->vspeed)) {
            int a = (int)ceil(fabs(env->vspeed));
            int s = iw_sign(env->vspeed);
            for (int i = 0; i <= a; i++) {
                env->y += s;
                if (!place_free(env, rx, env->y)) {
                    env->y -= s;
                    env->vspeed = 0;
                    if (s == 1) env->djump = 1; /* player_land() */
                    break;
                }
            }
        }
        if (env->hspeed >= 0) rxnext = floor(env->x + env->hspeed);
        else rxnext = ceil(env->x + env->hspeed);
        if (!place_free(env, rxnext, env->y + env->vspeed)) env->hspeed = 0;
        (void)oldvsp;
    }
    env->vspeed -= IW_GRAV;

    /* --- GM8 built-in update: gravity then motion --- */
    env->vspeed += IW_GRAV;
    env->x += env->hspeed;
    env->y += env->vspeed;
    }

    env->tick += 1;

    /* --- dynamic objects (pure C, no callbacks) --- */
    update_entities(env);
    resolve_platforms(env);

    /* --- pack mode: room-edge transitions (before out-of-room death) --- */
    if (env->pack) {
        iw_pack_check_edge(env);
        if (iw_pack_do_pending(env)) {
            env->ep_return += env->rewards[0];
            compute_observations(env);
            return;
        }
    }

    /* --- exact layer: collision events, triggers, camera (post-motion) --- */
    if (env->xs) iwx_frame_end(env);

    /* --- killer detection: spike tiles + deadly entities --- */
    if (killer_hit(env) || entity_killer_hit(env) ||
        (env->xs && iwx_killer_hit(env))) {
        env->rewards[0] = -env->death_penalty;
        env->deaths += 1;
        if (env->checkpoint_respawn) {
            /* fangame semantics: respawn at last save, episode continues */
            env->ep_return += env->rewards[0];
            iw_respawn_to_checkpoint(env);
            env->last_event = 1;
            compute_observations(env);
            return;
        }
        env->ep_return += env->rewards[0];
        env->terminals[0] = 1;
        add_log(env, 0.0f, 1.0f);
        c_reset(env);
        env->last_event = 1;
        return;
    }

    /* --- touch interactions: triggers, saves, warps --- */
    player_interactions(env);

    /* --- declarative trigger/event system --- */
    update_events(env);

    /* --- pack mode: warp-requested room transition --- */
    if (env->pack && iw_pack_do_pending(env)) {
        env->ep_return += env->rewards[0];
        compute_observations(env);
        return;
    }

    /* --- goal / reward --- */
    double dx = env->goal_x - env->x, dy = env->goal_y - env->y;
    double dist = sqrt(dx * dx + dy * dy);
    if (env->reward_mode == 1) {
        env->rewards[0] += (float)((env->prev_goal_dist - dist) * 0.01);
    }
    env->prev_goal_dist = dist;

    if ((!env->pack || env->room_has_goal) && goal_reached(env)) {
        env->rewards[0] += 1.0f;
        env->ep_return += env->rewards[0];
        env->terminals[0] = 1;
        add_log(env, 1.0f, 0.0f);
        c_reset(env);
        env->last_event = 2;
        return;
    }

    env->ep_return += env->rewards[0];

    if (env->tick >= env->max_steps) {
        env->terminals[0] = 1;
        add_log(env, 0.0f, 0.0f);
        c_reset(env);
        env->last_event = 3;
        return;
    }

    compute_observations(env);
}

/* ---------- level parsing ----------
 * Text format, one char per 32px tile:
 *   '#' block   '^' 'v' '<' '>' spikes   'S' start   'G' goal   '.' or ' ' empty
 *
 * Entity spawn lines start with '@' (skipped for the tile grid):
 *   @<type> <tx> <ty> [key=value ...]
 * Types: platform spikeball trap trigger shooter enemy save warp boss
 * Keys:  vx vy       initial velocity (px/frame)
 *        range       oscillation half-range in px (platform/spikeball/enemy)
 *        id          trigger link id (trigger fires all dormant ents with id)
 *        w h         trigger zone size in tiles (default 1x1)
 *        dir         up/down/left/right (trap spike orientation, shooter aim)
 *        speed       projectile speed for shooter/boss (px/frame)
 *        period      frames between shots / volleys
 *        aimed       1 = shooter aims at the player
 *        gx gy       warp destination in tiles
 *        grav        per-frame vy increment (any moving type)
 *        volleys     boss volley count (0 = endless)
 *        tag         event-system handle (actions target all ents with tag)
 *        active      0 = start deactivated (enable with an activate action)
 *        open        gates: 1 = start open (default closed)
 *
 * Event lines start with '!' (also skipped for the tile grid):
 *   !when=<cond> [keys] -> <action> [key=val ...] [; <action> ...]
 * See the IWEvent comment block for conditions and actions.
 */
static int iw_parse_dir(const char* v) {
    if (v[0] == 'd') return 1;      /* down  */
    if (v[0] == 'l') return 2;      /* left  */
    if (v[0] == 'r') return 3;      /* right */
    return 0;                       /* up    */
}

static void iw_parse_entity(IWanna* env, const char* line, int idx) {
    char type[32] = {0};
    float tx = 0, ty = 0;
    int off = 0;
    if (sscanf(line, "@%31s %f %f%n", type, &tx, &ty, &off) < 3) return;

    IWEntity* e = &env->spawns[idx];
    memset(e, 0, sizeof *e);
    e->x = tx * IW_TILE + IW_TILE / 2.0f;
    e->y = ty * IW_TILE + IW_TILE / 2.0f;
    e->flags = EF_ACTIVE;
    e->collision_mask = CM_PLAYER;

    /* defaults collected from key=value pairs */
    float vx = 0, vy = 0, range = 0, speed = 4, period = 60, grav = 0;
    float w = 1, h = 1, gx = 1, gy = 1, volleys = 0;
    int id = 0, aimed = 0, dir = 0, tag = 0, active = 1, open = 0;
    const char* p = line + off;
    char key[32], val[32];
    while (sscanf(p, " %31[a-z]=%31s%n", key, val, &off) >= 2) {
        float f = (float)atof(val);
        if      (!strcmp(key, "vx"))      vx = f;
        else if (!strcmp(key, "vy"))      vy = f;
        else if (!strcmp(key, "range"))   range = f;
        else if (!strcmp(key, "id"))      id = atoi(val);
        else if (!strcmp(key, "w"))       w = f;
        else if (!strcmp(key, "h"))       h = f;
        else if (!strcmp(key, "dir"))     dir = iw_parse_dir(val);
        else if (!strcmp(key, "speed"))   speed = f;
        else if (!strcmp(key, "period"))  period = f;
        else if (!strcmp(key, "aimed"))   aimed = atoi(val);
        else if (!strcmp(key, "gx"))      gx = f;
        else if (!strcmp(key, "gy"))      gy = f;
        else if (!strcmp(key, "grav"))    grav = f;
        else if (!strcmp(key, "volleys")) volleys = f;
        else if (!strcmp(key, "tag"))     tag = atoi(val);
        else if (!strcmp(key, "active"))  active = atoi(val);
        else if (!strcmp(key, "open"))    open = atoi(val);
        p += off;
    }

    if (!strcmp(type, "platform")) {
        e->type = E_PLATFORM;
        e->flags |= EF_SOLID_TOP;
        e->vx = vx; e->vy = vy;
        e->params[0] = range;
        e->params[4] = e->x; e->params[5] = e->y;
    } else if (!strcmp(type, "spikeball") || !strcmp(type, "fruit") ||
               !strcmp(type, "enemy")) {
        e->type = strcmp(type, "enemy") ? E_SPIKEBALL : E_ENEMY;
        e->flags |= EF_DEADLY;
        e->vx = vx; e->vy = vy;
        e->params[0] = range;
        e->params[4] = e->x; e->params[5] = e->y;
    } else if (!strcmp(type, "trap")) {
        e->type = E_TRAP;
        e->flags |= EF_DEADLY | EF_DORMANT;   /* deadly even before triggered */
        e->trigger_id = id;
        e->params[2] = vx; e->params[3] = vy; /* velocity applied on trigger */
        e->params[4] = (float)dir;            /* spike orientation */
    } else if (!strcmp(type, "trigger")) {
        e->type = E_TRIGGER;
        e->trigger_id = id;
        e->params[0] = w * IW_TILE / 2.0f;    /* zone half-extents in px */
        e->params[1] = h * IW_TILE / 2.0f;
    } else if (!strcmp(type, "shooter")) {
        e->type = E_SHOOTER;
        e->params[0] = period;
        e->params[1] = speed;
        e->params[2] = (float)aimed;
        /* fixed-direction muzzle velocity */
        float dvx = 0, dvy = 0;
        if (dir == 0) dvy = -speed;
        else if (dir == 1) dvy = speed;
        else if (dir == 2) dvx = -speed;
        else dvx = speed;
        e->params[3] = dvx; e->params[4] = dvy;
        e->timer = (int)period;
    } else if (!strcmp(type, "save")) {
        e->type = E_SAVE;
    } else if (!strcmp(type, "warp")) {
        e->type = E_WARP;
        e->params[0] = gx * IW_TILE + IW_TILE / 2.0f;
        e->params[1] = gy * IW_TILE + IW_TILE / 2.0f;
    } else if (!strcmp(type, "boss")) {
        e->type = E_BOSS;
        e->flags |= EF_DEADLY;
        e->params[0] = period;
        e->params[1] = volleys;
        e->state = (int)volleys;
        e->timer = (int)period;
    } else if (!strcmp(type, "projectile")) {
        e->type = E_PROJECTILE;
        e->flags |= EF_DEADLY;
        e->vx = vx; e->vy = vy;
    } else if (!strcmp(type, "gate")) {
        e->type = E_GATE;
        e->params[0] = tx; e->params[1] = ty;   /* tile top-left */
        e->params[2] = w;  e->params[3] = h;    /* size in tiles */
        e->params[4] = w * 100 + h;             /* packed for the 8-float export */
        e->x = (tx + w / 2.0f) * IW_TILE;       /* center for obs/render */
        e->y = (ty + h / 2.0f) * IW_TILE;
        e->state = open ? 0 : 1;                /* default: closed */
    } else {
        e->type = E_NONE;
        e->flags = 0;
    }
    e->tag = tag;
    e->grav = grav;
    if (!active) e->flags &= ~EF_ACTIVE;
}

/* ---------- event-line parsing ---------- */

static int iw_when_from_name(const char* s) {
    if (!strcmp(s, "room_enter"))       return W_ROOM_ENTER;
    if (!strcmp(s, "enter_region") || !strcmp(s, "player_enter"))
                                        return W_ENTER_REGION;
    if (!strcmp(s, "leave_region") || !strcmp(s, "player_leave"))
                                        return W_LEAVE_REGION;
    if (!strcmp(s, "touch_object") || !strcmp(s, "touch"))
                                        return W_TOUCH_OBJECT;
    if (!strcmp(s, "land_on_object") || !strcmp(s, "land"))
                                        return W_LAND_ON_OBJECT;
    if (!strcmp(s, "pass_x"))           return W_PASS_X;
    if (!strcmp(s, "pass_y"))           return W_PASS_Y;
    if (!strcmp(s, "timer"))            return W_TIMER;
    if (!strcmp(s, "object_destroyed") || !strcmp(s, "destroyed"))
                                        return W_OBJECT_DESTROYED;
    if (!strcmp(s, "save_activated") || !strcmp(s, "save"))
                                        return W_SAVE_ACTIVATED;
    if (!strcmp(s, "flag_set") || !strcmp(s, "flag"))
                                        return W_FLAG_SET;
    return -1;
}

static int iw_act_from_name(const char* s) {
    if (!strcmp(s, "activate"))       return ACT_ACTIVATE;
    if (!strcmp(s, "deactivate"))     return ACT_DEACTIVATE;
    if (!strcmp(s, "launch") || !strcmp(s, "set_velocity"))
                                      return ACT_LAUNCH;
    if (!strcmp(s, "set_gravity"))    return ACT_SET_GRAVITY;
    if (!strcmp(s, "move"))           return ACT_MOVE;
    if (!strcmp(s, "teleport"))       return ACT_TELEPORT;
    if (!strcmp(s, "spawn"))          return ACT_SPAWN;
    if (!strcmp(s, "destroy"))        return ACT_DESTROY;
    if (!strcmp(s, "make_killer"))    return ACT_MAKE_KILLER;
    if (!strcmp(s, "make_harmless"))  return ACT_MAKE_HARMLESS;
    if (!strcmp(s, "make_solid"))     return ACT_MAKE_SOLID;
    if (!strcmp(s, "make_unsolid"))   return ACT_MAKE_UNSOLID;
    if (!strcmp(s, "open_gate"))      return ACT_OPEN_GATE;
    if (!strcmp(s, "close_gate"))     return ACT_CLOSE_GATE;
    if (!strcmp(s, "start_timer"))    return ACT_START_TIMER;
    if (!strcmp(s, "set_dir"))        return ACT_SET_DIR;
    if (!strcmp(s, "set_flag"))       return ACT_SET_FLAG;
    if (!strcmp(s, "clear_flag"))     return ACT_CLEAR_FLAG;
    return -1;
}

static int iw_type_from_name(const char* s) {
    if (!strcmp(s, "platform"))   return E_PLATFORM;
    if (!strcmp(s, "spikeball") || !strcmp(s, "fruit")) return E_SPIKEBALL;
    if (!strcmp(s, "trap"))       return E_TRAP;
    if (!strcmp(s, "projectile") || !strcmp(s, "bullet")) return E_PROJECTILE;
    if (!strcmp(s, "enemy"))      return E_ENEMY;
    return E_PROJECTILE;
}

/* dir for pass_x / pass_y: right/down = +1, left/up = -1, any = 0 */
static int iw_pass_dir(const char* v) {
    if (v[0] == 'r' || v[0] == 'd') return 1;
    if (v[0] == 'l' || v[0] == 'u') return -1;
    return 0;
}

static void iw_parse_one_action(const char* seg, IWAction* a) {
    char name[32] = {0};
    int off = 0;
    memset(a, 0, sizeof *a);
    a->tag = -1;                       /* -1 = player (teleport) / no target */
    if (sscanf(seg, " %31[a-z_]%n", name, &off) < 1) { a->type = 255; return; }
    int t = iw_act_from_name(name);
    if (t < 0) { a->type = 255; return; }
    a->type = (uint8_t)t;
    float deadly = 1;
    const char* p = seg + off;
    char key[32], val[32];
    while (sscanf(p, " %31[a-z_0-9]=%31s%n", key, val, &off) >= 2) {
        float f = (float)atof(val);
        if      (!strcmp(key, "tag") || !strcmp(key, "id")) a->tag = atoi(val);
        else if (!strcmp(key, "vx"))   a->p[t == ACT_SPAWN ? 3 : 0] = f;
        else if (!strcmp(key, "vy"))   a->p[t == ACT_SPAWN ? 4 : 1] = f;
        else if (!strcmp(key, "grav")) {
            if      (t == ACT_SPAWN)  a->p[5] = f;
            else if (t == ACT_LAUNCH) a->p[2] = f;
            else                      a->p[0] = f;
        }
        else if (!strcmp(key, "dx"))   a->p[0] = f;   /* move: px */
        else if (!strcmp(key, "dy"))   a->p[1] = f;
        else if (!strcmp(key, "gx"))   a->p[0] = f * IW_TILE + IW_TILE / 2.0f;
        else if (!strcmp(key, "gy"))   a->p[1] = f * IW_TILE + IW_TILE / 2.0f;
        else if (!strcmp(key, "x"))    a->p[1] = f * IW_TILE + IW_TILE / 2.0f;
        else if (!strcmp(key, "y"))    a->p[2] = f * IW_TILE + IW_TILE / 2.0f;
        else if (!strcmp(key, "type")) a->p[0] = (float)iw_type_from_name(val);
        else if (!strcmp(key, "deadly")) deadly = f;
        else if (!strcmp(key, "dir"))  a->p[0] = (float)iw_parse_dir(val);
        p += off;
    }
    if (t == ACT_SPAWN) a->tag = deadly > 0 ? 1 : -1;
}

/* Parse one '!' event line; appends its actions to the flat pool. */
static void iw_parse_event(IWanna* env, const char* line, int idx) {
    char buf[512];
    int n = 0;
    for (const char* p = line + 1; *p && *p != '\n' && n < 511; p++) buf[n++] = *p;
    buf[n] = 0;

    IWEvent* ev = &env->events[idx];
    memset(ev, 0, sizeof *ev);
    ev->once = 1;
    ev->auto_arm = 1;
    ev->countdown = -1;
    ev->subject = -1;

    char* arrow = strstr(buf, "->");
    char* acts = NULL;
    if (arrow) { *arrow = 0; acts = arrow + 2; }

    int once_set = 0;
    const char* p = buf;
    char key[32], val[32];
    int off = 0;
    while (sscanf(p, " %31[a-z_0-9]=%31s%n", key, val, &off) >= 2) {
        float f = (float)atof(val);
        if      (!strcmp(key, "when")) {
            int w = iw_when_from_name(val);
            ev->when = (uint8_t)(w < 0 ? 255 : w);
        }
        else if (!strcmp(key, "once"))   { ev->once = (uint8_t)atoi(val); once_set = 1; }
        else if (!strcmp(key, "delay"))  ev->delay = atoi(val);
        else if (!strcmp(key, "period")) ev->period = atoi(val);
        else if (!strcmp(key, "auto"))   ev->auto_arm = (uint8_t)atoi(val);
        else if (!strcmp(key, "id"))     ev->id = atoi(val);
        else if (!strcmp(key, "tag"))    ev->subject = atoi(val);
        else if (!strcmp(key, "x0"))     ev->x0 = f * IW_TILE;
        else if (!strcmp(key, "y0"))     ev->y0 = f * IW_TILE;
        else if (!strcmp(key, "x1"))     ev->x1 = f * IW_TILE;
        else if (!strcmp(key, "y1"))     ev->y1 = f * IW_TILE;
        else if (!strcmp(key, "x"))      ev->x0 = f * IW_TILE;   /* pass_x */
        else if (!strcmp(key, "y"))      ev->y0 = f * IW_TILE;   /* pass_y */
        else if (!strcmp(key, "dir"))    ev->dir = (int8_t)iw_pass_dir(val);
        p += off;
    }
    /* a periodic timer refires by default */
    if (ev->period > 0 && !once_set) ev->once = 0;

    ev->first_action = env->ev_action_count;
    if (acts) {
        char* seg = acts;
        while (seg) {
            char* semi = strchr(seg, ';');
            if (semi) *semi = 0;
            IWAction* a = &env->ev_actions[env->ev_action_count];
            iw_parse_one_action(seg, a);
            if (a->type != 255) env->ev_action_count++;
            seg = semi ? semi + 1 : NULL;
        }
    }
    ev->n_actions = env->ev_action_count - ev->first_action;
}

static int iw_load_level(IWanna* env, const char* text) {
    /* classic single-room mode: no pack */
    if (env->pack) { iwpack_free_rt(env->pack); env->pack = NULL; }
    env->room_id = 0;
    env->start_room = 0;
    env->respawn_room = 0;
    env->room_has_goal = 1;
    env->pending_room = -1;
    env->pending_use_start = 0;
    env->gflags = 0;
    env->room_transitions = 0;
    env->room_pw = 0;             /* classic: derived from tw/th */
    env->room_ph = 0;
    env->solids = NULL;  env->n_solids = 0;
    env->killers = NULL; env->n_killers = 0;
    env->save_shoot_mode = 0;     /* classic: legacy touch saves */
    /* pass 1: tile-grid dimensions, entity count ('@' lines) and
     * event/action counts ('!' lines; actions = 1 + number of ';') */
    int tw = 0, th = 0, w = 0, nspawn = 0, line_start = 1, ent_line = 0;
    int nevent = 0, naction = 0;
    for (const char* p = text; *p; p++) {
        if (line_start && *p == '@') { ent_line = 1; nspawn++; }
        if (line_start && *p == '!') { ent_line = 1; nevent++; naction++; }
        line_start = 0;
        if (*p == ';' && ent_line) naction++;
        if (*p == '\n') {
            if (!ent_line && w > 0) { if (w > tw) tw = w; th++; }
            w = 0; ent_line = 0; line_start = 1;
        } else if (!ent_line) w++;
    }
    if (!ent_line && w > 0) { if (w > tw) tw = w; th++; }
    if (tw <= 0 || th <= 0) return -1;

    free(env->tiles); free(env->tiles0);
    env->tiles = (uint8_t*)calloc((size_t)(tw * th), 1);
    env->tiles0 = (uint8_t*)calloc((size_t)(tw * th), 1);
    env->tw = tw; env->th = th;
    env->start_x = IW_TILE * 1.5; env->start_y = IW_TILE * 1.5;
    env->goal_x = IW_TILE * (tw - 1.5); env->goal_y = IW_TILE * 1.5;

    /* entity storage: spawns (immutable template) + live array with headroom
     * for runtime projectiles. Fixed capacity => no realloc during step(). */
    free(env->spawns); free(env->entities);
    env->spawn_count = nspawn;
    env->ent_cap = nspawn * 2 > 2048 ? nspawn * 2 : 2048;
    env->spawns = (IWEntity*)calloc((size_t)(nspawn > 0 ? nspawn : 1), sizeof(IWEntity));
    env->entities = (IWEntity*)calloc((size_t)env->ent_cap, sizeof(IWEntity));
    env->free_hint = 0;

    /* event storage (fixed at load; no allocation during step) */
    free(env->events); free(env->ev_actions);
    env->events = (IWEvent*)calloc((size_t)(nevent > 0 ? nevent : 1), sizeof(IWEvent));
    env->ev_actions = (IWAction*)calloc((size_t)(naction > 0 ? naction : 1), sizeof(IWAction));
    env->event_count = nevent;
    env->ev_action_count = 0;   /* cursor advanced by iw_parse_event */

    /* pass 2: fill tiles, parse '@' entity and '!' event lines */
    int tx = 0, ty = 0, si = 0, ei = 0;
    line_start = 1; ent_line = 0;
    for (const char* p = text; *p; p++) {
        if (line_start && *p == '@') {
            iw_parse_entity(env, p, si++);
            ent_line = 1;
        }
        if (line_start && *p == '!') {
            iw_parse_event(env, p, ei++);
            ent_line = 1;
        }
        line_start = 0;
        if (*p == '\n') {
            if (!ent_line) { ty++; }
            tx = 0; ent_line = 0; line_start = 1;
            continue;
        }
        if (ent_line) continue;
        uint8_t t = T_EMPTY;
        switch (*p) {
            case '#': t = T_BLOCK; break;
            case '^': t = T_SPIKE_UP; break;
            case 'v': t = T_SPIKE_DOWN; break;
            case '<': t = T_SPIKE_LEFT; break;
            case '>': t = T_SPIKE_RIGHT; break;
            case 'G': t = T_GOAL;
                env->goal_x = tx * IW_TILE + IW_TILE / 2.0;
                env->goal_y = ty * IW_TILE + IW_TILE / 2.0;
                t = T_GOAL; break;
            case 'S':
                /* player origin: feet 9px above tile bottom (origin y=23 of 32) */
                env->start_x = tx * IW_TILE + IW_TILE / 2.0;
                env->start_y = ty * IW_TILE + (IW_TILE - 1) - HB_B;
                t = T_EMPTY; break;
            default: t = T_EMPTY; break;
        }
        if (ty < th && tx < tw) env->tiles[ty * tw + tx] = t;
        tx++;
    }
    memcpy(env->tiles0, env->tiles, (size_t)(tw * th));
    reset_entities(env);
    reset_events(env);
    return 0;
}

static void iw_free(IWanna* env) {
    iwx_free(env);
    if (env->pack) { iwpack_free_rt(env->pack); env->pack = NULL; }
    env->solids = NULL;  env->n_solids = 0;
    env->killers = NULL; env->n_killers = 0;
    free(env->tiles);
    env->tiles = NULL;
    free(env->tiles0);
    env->tiles0 = NULL;
    free(env->spawns);
    env->spawns = NULL;
    free(env->entities);
    env->entities = NULL;
    free(env->events);
    env->events = NULL;
    free(env->ev_actions);
    env->ev_actions = NULL;
    env->spawn_count = 0;
    env->ent_cap = 0;
    env->event_count = 0;
    env->ev_action_count = 0;
}

/* ---------- built-in levels (25x19 tiles = 800x608 rooms) ---------- */

static const char* IW_LEVELS[] = {
/* 0: flat walk */
"#########################\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.S..................G..#\n"
"#########################\n",
/* 1: gaps — requires jumps */
"#########################\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.S.......#....#.....G..#\n"
"####..#####....#..#######\n"
"#########################\n",
/* 2: spike corridor — first needle */
"#########################\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.......................#\n"
"#.S..^.....^^....^...G..#\n"
"#########################\n",
/* 3: platforming up — double jumps + ceiling spikes */
"#########################\n"
"#.......................#\n"
"#..................G....#\n"
"#................########\n"
"#.......................#\n"
"#...........####........#\n"
"#.......................#\n"
"#......####.............#\n"
"#.......................#\n"
"#.vv....................#\n"
"#####...................#\n"
"#.......................#\n"
"#....^^..........vv.....#\n"
"#..#####................#\n"
"#.......................#\n"
"#.......^....^..........#\n"
"#.S.....#####..#####..^.#\n"
"#########################\n",
};
#define IW_NUM_LEVELS 4

static int iw_load_builtin(IWanna* env, int idx) {
    if (idx < 0 || idx >= IW_NUM_LEVELS) idx = 0;
    return iw_load_level(env, IW_LEVELS[idx]);
}

/* ---------- rendering (raylib; excluded from the ctypes build) ---------- */
#ifndef IW_NO_RAYLIB
#include "raylib.h"

void c_render(IWanna* env) {
    if (!IsWindowReady()) {
        InitWindow(env->tw * IW_TILE, env->th * IW_TILE, "IWannaGym");
        SetTargetFPS(IW_FPS);
    }
    if (IsKeyDown(KEY_ESCAPE)) exit(0);
    BeginDrawing();
    ClearBackground((Color){12, 12, 20, 255});
    for (int ty = 0; ty < env->th; ty++) {
        for (int tx = 0; tx < env->tw; tx++) {
            uint8_t t = env->tiles[ty * env->tw + tx];
            int px = tx * IW_TILE, py = ty * IW_TILE;
            Color spike = (Color){200, 200, 210, 255};
            switch (t) {
                case T_BLOCK:
                    DrawRectangle(px, py, IW_TILE, IW_TILE, (Color){60, 60, 80, 255});
                    DrawRectangleLines(px, py, IW_TILE, IW_TILE, (Color){90, 90, 120, 255});
                    break;
                case T_SPIKE_UP:
                    DrawTriangle((Vector2){px + 16, py}, (Vector2){px, py + 32}, (Vector2){px + 32, py + 32}, spike);
                    break;
                case T_SPIKE_DOWN:
                    DrawTriangle((Vector2){px + 16, py + 32}, (Vector2){px + 32, py}, (Vector2){px, py}, spike);
                    break;
                case T_SPIKE_LEFT:
                    DrawTriangle((Vector2){px, py + 16}, (Vector2){px + 32, py + 32}, (Vector2){px + 32, py}, spike);
                    break;
                case T_SPIKE_RIGHT:
                    DrawTriangle((Vector2){px + 32, py + 16}, (Vector2){px, py}, (Vector2){px, py + 32}, spike);
                    break;
                case T_GOAL:
                    DrawRectangle(px + 4, py + 4, IW_TILE - 8, IW_TILE - 8, (Color){80, 220, 120, 255});
                    break;
            }
        }
    }
    /* dynamic entities (triggers are invisible by design) */
    for (int i = 0; i < env->ent_cap; i++) {
        IWEntity* e = &env->entities[i];
        if (e->type == E_NONE || !(e->flags & EF_ACTIVE) || e->type == E_TRIGGER)
            continue;
        float hw = ENT_HW[e->type], hh = ENT_HH[e->type];
        int ex = (int)e->x, ey = (int)e->y;
        switch (e->type) {
            case E_PLATFORM:
                DrawRectangle(ex - (int)hw, ey - (int)hh, (int)(2 * hw), (int)(2 * hh),
                              (Color){150, 110, 60, 255});
                break;
            case E_TRAP: {
                int d = (int)e->params[4];
                Color c = (e->flags & EF_DORMANT) ? (Color){170, 170, 185, 255}
                                                  : (Color){235, 200, 90, 255};
                int px = ex - 16, py = ey - 16;
                if (d == 0) DrawTriangle((Vector2){px + 16, py}, (Vector2){px, py + 32}, (Vector2){px + 32, py + 32}, c);
                else if (d == 1) DrawTriangle((Vector2){px + 16, py + 32}, (Vector2){px + 32, py}, (Vector2){px, py}, c);
                else if (d == 2) DrawTriangle((Vector2){px, py + 16}, (Vector2){px + 32, py + 32}, (Vector2){px + 32, py}, c);
                else DrawTriangle((Vector2){px + 32, py + 16}, (Vector2){px, py}, (Vector2){px, py + 32}, c);
                break;
            }
            case E_SPIKEBALL:
            case E_PROJECTILE:
                DrawCircle(ex, ey, hw, (Color){230, 120, 120, 255});
                break;
            case E_PBULLET:
                DrawRectangle(ex + IW_BULLET_L, ey + IW_BULLET_T,
                              IW_BULLET_R - IW_BULLET_L + 1,
                              IW_BULLET_B - IW_BULLET_T + 1,
                              (Color){250, 240, 120, 255});
                break;
            case E_ENEMY:
            case E_BOSS:
                DrawRectangle(ex - (int)hw, ey - (int)hh, (int)(2 * hw), (int)(2 * hh),
                              (Color){190, 80, 190, 255});
                break;
            case E_SAVE:
                DrawRectangle(ex - (int)hw, ey - (int)hh, (int)(2 * hw), (int)(2 * hh),
                              e->state ? (Color){120, 220, 120, 255} : (Color){90, 160, 220, 255});
                break;
            case E_WARP:
                DrawRectangleLines(ex - (int)hw, ey - (int)hh, (int)(2 * hw), (int)(2 * hh),
                                   (Color){170, 120, 240, 255});
                break;
            default: break;
        }
    }
    /* goal marker (may be random) */
    DrawRectangleLines((int)env->goal_x - 16, (int)env->goal_y - 16, 32, 32, (Color){80, 220, 120, 255});
    /* the kid */
    int ix = gm_round(env->x), iy = gm_round(env->y);
    DrawRectangle(ix + HB_L, iy + HB_T, HB_R - HB_L + 1, HB_B - HB_T + 1, (Color){235, 80, 80, 255});
    DrawRectangle(ix + HB_L, iy + HB_T, HB_R - HB_L + 1, 6, (Color){40, 40, 45, 255});
    EndDrawing();
}

void c_close(IWanna* env) {
    iw_free(env);
    if (IsWindowReady()) CloseWindow();
}
#else
void c_render(IWanna* env) { (void)env; }
void c_close(IWanna* env) { iw_free(env); }
#endif

#endif /* IWANNA_H */
