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

/* Observation layout */
#define IW_LOCAL_W 9   /* tiles, centered on player */
#define IW_LOCAL_H 7
#define IW_OBS_BASE 8
#define IW_OBS_SIZE (IW_OBS_BASE + IW_LOCAL_W * IW_LOCAL_H)
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
    uint64_t rng;

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

/* Rect vs spike-triangle overlap. Triangle occupies a full 32px tile,
 * apex at the center of one edge, base on the opposite edge (standard
 * fangame spike mask). Player rect is [l..r] x [t..b] inclusive. */
static int spike_hit(int l, int r, int t, int b, int tx, int ty, uint8_t kind) {
    int x0 = tx * IW_TILE, y0 = ty * IW_TILE;
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
                if (spike_hit(l, r, t, b, tx, ty, k)) return 1;
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

/* ---------- observations ---------- */

static void compute_observations(IWanna* env) {
    float* o = env->observations;
    double W = env->tw * IW_TILE, H = env->th * IW_TILE;
    o[0] = (float)(2.0 * env->x / W - 1.0);
    o[1] = (float)(2.0 * env->y / H - 1.0);
    o[2] = (float)(env->hspeed / IW_MAXSPEED);
    o[3] = (float)(env->vspeed / (IW_MAXVSPEED + IW_GRAV));
    o[4] = (env->djump < IW_MAXJUMPS) ? 1.0f : 0.0f;
    o[5] = on_ground(env) ? 1.0f : 0.0f;
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
        if (on_ground(env)) {
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

    /* --- killer detection --- */
    if (killer_hit(env)) {
        env->rewards[0] = -env->death_penalty;
        env->ep_return += env->rewards[0];
        env->terminals[0] = 1;
        add_log(env, 0.0f, 1.0f);
        c_reset(env);
        env->last_event = 1;
        return;
    }

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
 */
static int iw_load_level(IWanna* env, const char* text) {
    int tw = 0, th = 0, w = 0;
    for (const char* p = text; *p; p++) {
        if (*p == '\n') { if (w > 0) { if (w > tw) tw = w; th++; w = 0; } }
        else w++;
    }
    if (w > 0) { if (w > tw) tw = w; th++; }
    if (tw <= 0 || th <= 0) return -1;

    free(env->tiles);
    env->tiles = (uint8_t*)calloc((size_t)(tw * th), 1);
    env->tw = tw; env->th = th;
    env->start_x = IW_TILE * 1.5; env->start_y = IW_TILE * 1.5;
    env->goal_x = IW_TILE * (tw - 1.5); env->goal_y = IW_TILE * 1.5;

    int tx = 0, ty = 0;
    for (const char* p = text; *p; p++) {
        if (*p == '\n') { if (tx > 0 || 1) { ty++; tx = 0; } continue; }
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
    return 0;
}

static void iw_free(IWanna* env) {
    free(env->tiles);
    env->tiles = NULL;
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
