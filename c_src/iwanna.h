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
    E_NUM_TYPES
};

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
    uint32_t collision_mask;
    float x, y;             /* center, room pixels */
    float vx, vy;
    int32_t state;
    int32_t timer;
    float params[IW_ENT_PARAMS];
    /* params by type:
     *  PLATFORM/SPIKEBALL/ENEMY: [0]=oscillation range px, [4],[5]=origin
     *  TRIGGER:    [0]=half w px, [1]=half h px
     *  TRAP:       [2],[3]=launch vx,vy, [4]=orientation 0=^ 1=v 2=< 3=>
     *  PROJECTILE: [0]=gravity per frame
     *  SHOOTER:    [0]=period, [1]=speed, [2]=aimed(1)/fixed(0), [3],[4]=fixed dir
     *  WARP:       [0],[1]=destination px
     *  BOSS:       [0]=period, [1]=volleys (0 = endless), state=volleys left
     */
} IWEntity;

/* contact half-extents per type (rect hitboxes; traps use spike triangles) */
static const float ENT_HW[E_NUM_TYPES] = {0, 16, 10, 0, 16, 4, 12, 11, 14, 14, 16};
static const float ENT_HH[E_NUM_TYPES] = {0,  8, 10, 0, 16, 4, 12, 14, 14, 14, 16};

/* Physics constants (from Renex engine Player.gml Create_0) */
#define IW_MAXSPEED 3.0
#define IW_JUMP 8.5
#define IW_JUMP2 7.0
#define IW_GRAV 0.4
#define IW_MAXVSPEED 9.0
#define IW_RELEASE_MULT 0.45
#define IW_MAXJUMPS 2

/* Player hitbox offsets from origin (sprMaskPlayer: origin 17,23; bbox 12..22 x 12..31) */
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
#define IW_NUM_ACTIONS 6 /* {left,none,right} x {jump released, jump held} */

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

    /* dynamic state */
    double x, y, hspeed, vspeed;
    int djump;                /* jumps used; can air-jump while djump < IW_MAXJUMPS */
    int face;
    int prev_jump_held;
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

static inline uint8_t iw_tile_at(IWanna* env, int tx, int ty) {
    if (tx < 0 || ty < 0 || tx >= env->tw || ty >= env->th) return T_EMPTY;
    return env->tiles[ty * env->tw + tx];
}

/* Solid check for player bbox at real position (px, py).
 * GM8 instance_place/place_free round the instance position. */
static int place_free(IWanna* env, double px, double py) {
    int ix = gm_round(px), iy = gm_round(py);
    int l = ix + HB_L, r = ix + HB_R, t = iy + HB_T, b = iy + HB_B;
    int tx0 = l >= 0 ? l / IW_TILE : (l - IW_TILE + 1) / IW_TILE;
    int tx1 = r >= 0 ? r / IW_TILE : (r - IW_TILE + 1) / IW_TILE;
    int ty0 = t >= 0 ? t / IW_TILE : (t - IW_TILE + 1) / IW_TILE;
    int ty1 = b >= 0 ? b / IW_TILE : (b - IW_TILE + 1) / IW_TILE;
    for (int ty = ty0; ty <= ty1; ty++)
        for (int tx = tx0; tx <= tx1; tx++)
            if (iw_tile_at(env, tx, ty) == T_BLOCK) return 0;
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

/* 1 = dead, checked at integer (rounded) position like instance_place */
static int killer_hit(IWanna* env) {
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + HB_L, r = ix + HB_R, t = iy + HB_T, b = iy + HB_B;
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
    /* falling out of the room is death */
    if (iy + HB_T > env->th * IW_TILE + IW_TILE) return 1;
    if (iy + HB_B < -IW_TILE) return 1;
    if (ix < -IW_TILE || ix > env->tw * IW_TILE + IW_TILE) return 1;
    return 0;
}

static int goal_reached(IWanna* env) {
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + HB_L, r = ix + HB_R, t = iy + HB_T, b = iy + HB_B;
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
            e->params[0] = grav;
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
                e->x += e->vx; e->y += e->vy;
                float range = e->params[0];
                if (range > 0) {
                    if (e->vx != 0 && fabsf(e->x - e->params[4]) >= range) e->vx = -e->vx;
                    if (e->vy != 0 && fabsf(e->y - e->params[5]) >= range) e->vy = -e->vy;
                }
                break;
            }
            case E_TRAP:
                if (!(e->flags & EF_DORMANT)) { e->x += e->vx; e->y += e->vy; }
                break;
            case E_PROJECTILE:
                e->vy += e->params[0];
                e->x += e->vx; e->y += e->vy;
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
        /* free-flying objects despawn well outside the room */
        if ((e->type == E_PROJECTILE || e->type == E_TRAP) &&
            (e->x < -64 || e->x > W + 64 || e->y < -64 || e->y > H + 64))
            e->flags &= ~EF_ACTIVE;
    }
}

/* Jump-through platforms: land on top, get carried, keep the double jump. */
static void resolve_platforms(IWanna* env) {
    env->on_platform = 0;
    int ix = gm_round(env->x), iy = gm_round(env->y);
    int l = ix + HB_L, r = ix + HB_R, b = iy + HB_B;
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* e = &env->entities[i];
        if (e->type != E_PLATFORM || !(e->flags & EF_ACTIVE)) continue;
        float ptop = e->y - ENT_HH[E_PLATFORM];
        float pl = e->x - ENT_HW[E_PLATFORM], pr = e->x + ENT_HW[E_PLATFORM] - 1;
        if (r < pl || l > pr) continue;
        if (env->vspeed >= e->vy - 0.001 &&
            b >= ptop - 1 && b <= ptop + 8 + env->vspeed) {
            env->y = ptop - 1 - HB_B;
            env->vspeed = e->vy > 0 ? e->vy : 0;
            env->djump = 1;           /* landing restores the air jump */
            env->x += e->vx;          /* carried horizontally */
            env->on_platform = 1;
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
    int l = ix + HB_L, r = ix + HB_R, t = iy + HB_T, b = iy + HB_B;
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
    int l = ix + HB_L, r = ix + HB_R, t = iy + HB_T, b = iy + HB_B;
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
            case E_SAVE:
                if (ent_rect_hit(e, l, r, t, b, ENT_HW[E_SAVE], ENT_HH[E_SAVE])) {
                    env->respawn_x = e->x;
                    env->respawn_y = e->y + IW_TILE / 2.0 - 1 - HB_B;
                    e->state = 1;
                }
                break;
            case E_WARP:
                if (ent_rect_hit(e, l, r, t, b, ENT_HW[E_WARP], ENT_HH[E_WARP])) {
                    env->x = e->params[0];
                    env->y = e->params[1];
                    env->hspeed = 0; env->vspeed = 0;
                    double wdx = env->goal_x - env->x, wdy = env->goal_y - env->y;
                    env->prev_goal_dist = sqrt(wdx * wdx + wdy * wdy);
                }
                break;
            default: break;
        }
    }
}

static void reset_entities(IWanna* env) {
    if (!env->entities) return;
    memset(env->entities, 0, sizeof(IWEntity) * (size_t)env->ent_cap);
    for (int i = 0; i < env->spawn_count; i++) env->entities[i] = env->spawns[i];
    env->free_hint = env->spawn_count;
    env->ent_top = env->spawn_count;
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
     * (negative = deadly). Zero-padded when fewer than K entities exist. */
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
    for (int s = 0; s < IW_OBS_K; s++) {
        if (s < nbest) {
            IWEntity* e = &env->entities[best[s]];
            float f0 = (float)((e->x - env->x) / W);
            float f1 = (float)((e->y - env->y) / H);
            float f2 = e->vx / 10.0f, f3 = e->vy / 10.0f;
            float f4 = (float)e->type / (float)E_NUM_TYPES;
            if (e->flags & EF_DEADLY) f4 = -f4;
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
    env->x = env->start_x;
    env->y = env->start_y;
    env->hspeed = 0; env->vspeed = 0;
    env->djump = 1;               /* engine Create_0: djump=1 (one air jump available) */
    env->face = 1;
    env->prev_jump_held = 0;
    env->tick = 0;
    env->ep_return = 0;
    env->on_platform = 0;
    env->deaths = 0;
    env->respawn_x = env->start_x;
    env->respawn_y = env->start_y;
    reset_entities(env);
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

    int action = env->actions[0];
    if (action < 0) action = 0;
    if (action >= IW_NUM_ACTIONS) action = IW_NUM_ACTIONS - 1;
    int jump_held = action % 2;
    int h = (action / 2) - 1;   /* -1, 0, 1 */
    int pressed = jump_held && !env->prev_jump_held;
    int released = !jump_held && env->prev_jump_held;
    env->prev_jump_held = jump_held;

    /* --- ///movement --- */
    if (h != 0) env->face = h;
    env->hspeed = IW_MAXSPEED * h;
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

    env->tick += 1;

    /* --- dynamic objects (pure C, no callbacks) --- */
    update_entities(env);
    resolve_platforms(env);

    /* --- killer detection: spike tiles + deadly entities --- */
    if (killer_hit(env) || entity_killer_hit(env)) {
        env->rewards[0] = -env->death_penalty;
        env->deaths += 1;
        if (env->checkpoint_respawn) {
            /* fangame semantics: respawn at last save, episode continues */
            env->ep_return += env->rewards[0];
            env->x = env->respawn_x;
            env->y = env->respawn_y;
            env->hspeed = 0; env->vspeed = 0;
            env->djump = 1;
            env->prev_jump_held = 0;
            env->on_platform = 0;
            env->last_event = 1;
            double rdx = env->goal_x - env->x, rdy = env->goal_y - env->y;
            env->prev_goal_dist = sqrt(rdx * rdx + rdy * rdy);
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

    /* --- goal / reward --- */
    double dx = env->goal_x - env->x, dy = env->goal_y - env->y;
    double dist = sqrt(dx * dx + dy * dy);
    if (env->reward_mode == 1) {
        env->rewards[0] += (float)((env->prev_goal_dist - dist) * 0.01);
    }
    env->prev_goal_dist = dist;

    if (goal_reached(env)) {
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
 *        grav        projectile gravity per frame
 *        volleys     boss volley count (0 = endless)
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
    int id = 0, aimed = 0, dir = 0;
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
        p += off;
    }

    if (!strcmp(type, "platform")) {
        e->type = E_PLATFORM;
        e->flags |= EF_SOLID_TOP;
        e->vx = vx; e->vy = vy;
        e->params[0] = range;
        e->params[4] = e->x; e->params[5] = e->y;
    } else if (!strcmp(type, "spikeball") || !strcmp(type, "enemy")) {
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
        e->params[0] = grav;
    } else {
        e->type = E_NONE;
        e->flags = 0;
    }
}

static int iw_load_level(IWanna* env, const char* text) {
    /* pass 1: tile-grid dimensions and entity count ('@' lines are spawns) */
    int tw = 0, th = 0, w = 0, nspawn = 0, line_start = 1, ent_line = 0;
    for (const char* p = text; *p; p++) {
        if (line_start && *p == '@') { ent_line = 1; nspawn++; }
        line_start = 0;
        if (*p == '\n') {
            if (!ent_line && w > 0) { if (w > tw) tw = w; th++; }
            w = 0; ent_line = 0; line_start = 1;
        } else if (!ent_line) w++;
    }
    if (!ent_line && w > 0) { if (w > tw) tw = w; th++; }
    if (tw <= 0 || th <= 0) return -1;

    free(env->tiles);
    env->tiles = (uint8_t*)calloc((size_t)(tw * th), 1);
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

    /* pass 2: fill tiles and parse '@' entity lines */
    int tx = 0, ty = 0, si = 0;
    line_start = 1; ent_line = 0;
    for (const char* p = text; *p; p++) {
        if (line_start && *p == '@') {
            iw_parse_entity(env, p, si++);
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
    reset_entities(env);
    return 0;
}

static void iw_free(IWanna* env) {
    free(env->tiles);
    env->tiles = NULL;
    free(env->spawns);
    env->spawns = NULL;
    free(env->entities);
    env->entities = NULL;
    env->spawn_count = 0;
    env->ent_cap = 0;
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
