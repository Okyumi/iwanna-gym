/* ctypes shared-library API for the IWanna core.
 * Build:
 *   gcc -O2 -fPIC -shared -DIW_NO_RAYLIB -o libiwanna.so iwanna_capi.c -lm
 *
 * Python allocates the numpy buffers (observations, actions, rewards,
 * terminals) and passes their pointers in; the env writes into them
 * following the PufferLib Ocean convention (auto-reset inside step).
 */
#include <stdlib.h>
#include <time.h>
#include "iwanna.h"

typedef struct {
    IWanna env;
} Handle;

/* returns NULL on level-parse failure */
void* iw_new(const char* level_text,
             float* observations, int* actions, float* rewards,
             unsigned char* terminals,
             int max_steps, int reward_mode, float death_penalty,
             int random_goal, unsigned long long seed,
             int checkpoint_respawn) {
    Handle* h = (Handle*)calloc(1, sizeof(Handle));
    if (!h) return NULL;
    IWanna* e = &h->env;
    e->observations = observations;
    e->actions = actions;
    e->rewards = rewards;
    e->terminals = terminals;
    e->max_steps = max_steps > 0 ? max_steps : 1500;
    e->reward_mode = reward_mode;
    e->death_penalty = death_penalty;
    e->random_goal = random_goal;
    e->checkpoint_respawn = checkpoint_respawn;
    e->rng = seed ? seed : 0x9E3779B97F4A7C15ULL;
    e->hb_l = HB_L; e->hb_t = HB_T; e->hb_r = HB_R; e->hb_b = HB_B;
    if (iw_load_level(e, level_text) != 0) {
        free(h);
        return NULL;
    }
    return (void*)h;
}

void* iw_new_builtin(int level_idx,
                     float* observations, int* actions, float* rewards,
                     unsigned char* terminals,
                     int max_steps, int reward_mode, float death_penalty,
                     int random_goal, unsigned long long seed,
                     int checkpoint_respawn) {
    if (level_idx < 0 || level_idx >= IW_NUM_LEVELS) return NULL;
    return iw_new(IW_LEVELS[level_idx], observations, actions, rewards,
                  terminals, max_steps, reward_mode, death_penalty,
                  random_goal, seed, checkpoint_respawn);
}

/* ---- game-pack construction (compiled .iwpack blobs) ---- */

static char iw_err_buf[256];

const char* iw_last_error(void) { return iw_err_buf; }

/* returns NULL on pack-load failure; iw_last_error() has the reason */
void* iw_new_pack(const unsigned char* pack_data, long pack_len,
                  float* observations, int* actions, float* rewards,
                  unsigned char* terminals,
                  int max_steps, int reward_mode, float death_penalty,
                  int random_goal, unsigned long long seed,
                  int checkpoint_respawn) {
    iw_err_buf[0] = 0;
    Handle* h = (Handle*)calloc(1, sizeof(Handle));
    if (!h) { snprintf(iw_err_buf, sizeof iw_err_buf, "out of memory"); return NULL; }
    IWanna* e = &h->env;
    e->observations = observations;
    e->actions = actions;
    e->rewards = rewards;
    e->terminals = terminals;
    e->max_steps = max_steps > 0 ? max_steps : 1500;
    e->reward_mode = reward_mode;
    e->death_penalty = death_penalty;
    e->random_goal = random_goal;
    e->checkpoint_respawn = checkpoint_respawn;
    e->rng = seed ? seed : 0x9E3779B97F4A7C15ULL;
    e->hb_l = HB_L; e->hb_t = HB_T; e->hb_r = HB_R; e->hb_b = HB_B;
    if (iw_load_pack_mem(e, pack_data, (size_t)pack_len,
                         iw_err_buf, sizeof iw_err_buf) != 0) {
        free(h);
        return NULL;
    }
    return (void*)h;
}

/* pack-mode configuration; call BEFORE iw_reset. */
int iw_set_start_room(void* h, int room) {
    IWanna* e = &((Handle*)h)->env;
    if (!e->pack || room < 0 || room >= (int)e->pack->hdr.n_rooms) return -1;
    e->start_room = room;
    return 0;
}
int iw_set_difficulty(void* h, int difficulty) {
    IWanna* e = &((Handle*)h)->env;
    if (difficulty < 0 || difficulty > 3) return -1;
    e->difficulty = difficulty;
    return 0;
}
/* debug/research helper: force a global progression flag (e.g. to open a
 * source-conditional route whose setter is not imported yet). NOT source
 * behavior — inspection and experimentation only. */
void iw_set_gflag(void* h, int flag, int on) {
    IWanna* e = &((Handle*)h)->env;
    if (flag > 0 && flag < 64) {
        if (on) e->gflags |= 1ULL << flag;
        else    e->gflags &= ~(1ULL << flag);
    }
}
int iw_n_solids(void* h)          { return ((Handle*)h)->env.n_solids; }
int iw_n_killers(void* h)         { return ((Handle*)h)->env.n_killers; }
int iw_room_pw(void* h)           { IWanna* e = &((Handle*)h)->env; return e->room_pw > 0 ? e->room_pw : e->tw * IW_TILE; }
int iw_room_ph(void* h)           { IWanna* e = &((Handle*)h)->env; return e->room_ph > 0 ? e->room_ph : e->th * IW_TILE; }
/* copy static colliders (for inspection/rendering): solids rows of 4
 * floats, killers rows of 5 floats [shape,x0,y0,x1,y1] */
int iw_solids(void* h, float* out, int max_rows) {
    IWanna* e = &((Handle*)h)->env;
    int n = e->n_solids < max_rows ? e->n_solids : max_rows;
    for (int i = 0; i < n; i++) {
        out[i*4+0] = e->solids[i].x0; out[i*4+1] = e->solids[i].y0;
        out[i*4+2] = e->solids[i].x1; out[i*4+3] = e->solids[i].y1;
    }
    return n;
}
int iw_killers(void* h, float* out, int max_rows) {
    IWanna* e = &((Handle*)h)->env;
    int n = e->n_killers < max_rows ? e->n_killers : max_rows;
    for (int i = 0; i < n; i++) {
        out[i*5+0] = (float)e->killers[i].shape;
        out[i*5+1] = e->killers[i].x0; out[i*5+2] = e->killers[i].y0;
        out[i*5+3] = e->killers[i].x1; out[i*5+4] = e->killers[i].y1;
    }
    return n;
}

/* ---- attempt/task reset distinction (docs/action_and_reset_semantics.md) ----
 * iw_reset      = TASK reset: back to the start room, progression cleared.
 * iw_attempt_reset = ATTEMPT reset ("R" quick-retry): return to the active
 *   checkpoint with source retry semantics (pack mode: full room reset,
 *   exact saved position/facing, flags persist); no death is counted. */
void iw_attempt_reset(void* h) {
    IWanna* e = &((Handle*)h)->env;
    iw_respawn_to_checkpoint(e);
    e->rewards[0] = 0;
    e->terminals[0] = 0;
    e->last_event = 0;
    compute_observations(e);
}
int iw_attempt(void* h)           { return ((Handle*)h)->env.attempt; }
int iw_save_shoot_mode(void* h)   { return ((Handle*)h)->env.save_shoot_mode; }
void iw_set_save_mode(void* h, int shoot) {
    ((Handle*)h)->env.save_shoot_mode = shoot ? 1 : 0;
}
int iw_difficulty(void* h)        { return ((Handle*)h)->env.difficulty; }
double iw_respawn_face(void* h)   { return ((Handle*)h)->env.respawn_face; }
int iw_num_actions_legacy(void)   { return IW_NUM_ACTIONS_LEGACY; }

/* like iw_bench but sampling from the first n_actions actions */
double iw_bench_n(void* handle, long steps, unsigned long long seed,
                  int n_actions) {
    Handle* h = (Handle*)handle;
    if (n_actions <= 0 || n_actions > IW_NUM_ACTIONS) n_actions = IW_NUM_ACTIONS;
    uint64_t r = seed ? seed : 7;
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (long i = 0; i < steps; i++) {
        r ^= r >> 12; r ^= r << 25; r ^= r >> 27;
        h->env.actions[0] = (int)((r * 0x2545F4914F6CDD1DULL) % (uint64_t)n_actions);
        c_step(&h->env);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    return (t1.tv_sec - t0.tv_sec) + 1e-9 * (t1.tv_nsec - t0.tv_nsec);
}

int iw_room(void* h)              { return ((Handle*)h)->env.room_id; }
int iw_respawn_room(void* h)      { return ((Handle*)h)->env.respawn_room; }
int iw_room_transitions(void* h)  { return ((Handle*)h)->env.room_transitions; }
int iw_num_rooms(void* h) {
    IWanna* e = &((Handle*)h)->env;
    return e->pack ? (int)e->pack->hdr.n_rooms : 1;
}
unsigned long long iw_gflags(void* h) { return ((Handle*)h)->env.gflags; }

/* pure-C benchmark: run `steps` frames with xorshift-random actions, no
 * Python in the loop; returns elapsed seconds */
#include <time.h>
double iw_bench(void* handle, long steps, unsigned long long seed) {
    Handle* h = (Handle*)handle;
    uint64_t r = seed ? seed : 7;
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (long i = 0; i < steps; i++) {
        r ^= r >> 12; r ^= r << 25; r ^= r >> 27;
        h->env.actions[0] = (int)((r * 0x2545F4914F6CDD1DULL) % IW_NUM_ACTIONS);
        c_step(&h->env);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    return (t1.tv_sec - t0.tv_sec) + 1e-9 * (t1.tv_nsec - t0.tv_nsec);
}

void iw_delete(void* handle) {
    if (!handle) return;
    Handle* h = (Handle*)handle;
    iw_free(&h->env);
    free(h);
}

void iw_reset(void* handle) { c_reset(&((Handle*)handle)->env); }
void iw_step(void* handle)  { c_step(&((Handle*)handle)->env); }

/* ---- state getters for rendering / debugging / goal relabeling ---- */
double iw_x(void* h)        { return ((Handle*)h)->env.x; }
double iw_y(void* h)        { return ((Handle*)h)->env.y; }
double iw_vspeed(void* h)   { return ((Handle*)h)->env.vspeed; }
double iw_hspeed(void* h)   { return ((Handle*)h)->env.hspeed; }
int    iw_djump(void* h)    { return ((Handle*)h)->env.djump; }
int    iw_on_ground(void* h){ IWanna* e = &((Handle*)h)->env; return on_ground(e); }
int    iw_tick(void* h)     { return ((Handle*)h)->env.tick; }
double iw_goal_x(void* h)   { return ((Handle*)h)->env.goal_x; }
double iw_goal_y(void* h)   { return ((Handle*)h)->env.goal_y; }
int    iw_tw(void* h)       { return ((Handle*)h)->env.tw; }
int    iw_th(void* h)       { return ((Handle*)h)->env.th; }
int    iw_last_event(void* h){ return ((Handle*)h)->env.last_event; }

void iw_set_goal(void* h, double gx, double gy) {
    IWanna* e = &((Handle*)h)->env;
    e->goal_x = gx;
    e->goal_y = gy;
}

/* copy tile grid into caller buffer of size tw*th */
void iw_tiles(void* h, unsigned char* out) {
    IWanna* e = &((Handle*)h)->env;
    for (int i = 0; i < e->tw * e->th; i++) out[i] = e->tiles[i];
}

/* teleport for unit tests */
void iw_set_state(void* h, double x, double y, double hs, double vs, int djump) {
    IWanna* e = &((Handle*)h)->env;
    e->x = x; e->y = y; e->hspeed = hs; e->vspeed = vs; e->djump = djump;
    compute_observations(e);
}

/* ---- entity introspection for rendering / analysis ----
 * Writes up to max_rows rows of 8 floats:
 *   [type, x, y, vx, vy, state, dormant, p4]
 * Returns the number of rows written (active entities only; triggers
 * included so debuggers can see them; render layer may skip them). */
int iw_entities(void* h, float* out, int max_rows) {
    IWanna* e = &((Handle*)h)->env;
    int n = 0;
    for (int i = 0; i < e->ent_cap && n < max_rows; i++) {
        IWEntity* en = &e->entities[i];
        if (en->type == E_NONE || !(en->flags & EF_ACTIVE)) continue;
        float* r = out + n * 8;
        r[0] = (float)en->type;
        r[1] = en->x; r[2] = en->y;
        r[3] = en->vx; r[4] = en->vy;
        r[5] = (float)en->state;
        r[6] = (en->flags & EF_DORMANT) ? 1.0f : 0.0f;
        r[7] = en->params[4];
        n++;
    }
    return n;
}

int iw_ent_count(void* h) {
    IWanna* e = &((Handle*)h)->env;
    int n = 0;
    for (int i = 0; i < e->ent_cap; i++)
        if (e->entities[i].type != E_NONE && (e->entities[i].flags & EF_ACTIVE)) n++;
    return n;
}

int iw_deaths(void* h)      { return ((Handle*)h)->env.deaths; }
double iw_respawn_x(void* h){ return ((Handle*)h)->env.respawn_x; }
double iw_respawn_y(void* h){ return ((Handle*)h)->env.respawn_y; }

int iw_obs_size(void)    { return IW_OBS_SIZE; }
int iw_num_actions(void) { return IW_NUM_ACTIONS; }
int iw_num_levels(void)  { return IW_NUM_LEVELS; }
const char* iw_level_text(int idx) {
    if (idx < 0 || idx >= IW_NUM_LEVELS) return "";
    return IW_LEVELS[idx];
}

/* ---- exact-layer introspection (tests / rendering) ---- */
int iw_exact(void* h) { return ((Handle*)h)->env.xs != NULL; }
int iw_xent_count(void* h) {
    IWanna* e = &((Handle*)h)->env;
    return e->xs ? e->xs->n_ents : 0;
}
/* rows of 12 floats: cls, x, y, vx, vy, state, alive, active, frame, tag,
 * on/armed composite (on + 2*armed), xscale */
int iw_xents(void* h, float* out, int max_rows) {
    IWanna* e = &((Handle*)h)->env;
    if (!e->xs) return 0;
    int n = 0;
    for (int i = 0; i < e->xs->n_ents && n < max_rows; i++) {
        IWXEnt* x = &e->xs->ents[i];
        out[n * 12 + 0] = (float)x->cls;
        out[n * 12 + 1] = x->x;
        out[n * 12 + 2] = x->y;
        out[n * 12 + 3] = x->vx;
        out[n * 12 + 4] = x->vy;
        out[n * 12 + 5] = (float)x->state;
        out[n * 12 + 6] = (float)x->alive;
        out[n * 12 + 7] = (float)x->active;
        out[n * 12 + 8] = x->frame;
        out[n * 12 + 9] = (float)x->tag;
        out[n * 12 + 10] = (float)(x->on + 2 * x->armed);
        out[n * 12 + 11] = x->xs;
        n++;
    }
    return n;
}
void iw_view(void* h, float* out2) {
    IWanna* e = &((Handle*)h)->env;
    out2[0] = e->xs ? (float)e->xs->view_x : 0.0f;
    out2[1] = e->xs ? (float)e->xs->view_y : 0.0f;
}
/* 8 floats: frozen, stoned, birded, fished, carted, walljumpboost, hang, fire */
void iw_player_ext(void* h, float* out8) {
    IWanna* e = &((Handle*)h)->env;
    IWXState* xs = e->xs;
    out8[0] = xs ? (float)xs->frozen : 0.0f;
    out8[1] = xs ? (float)xs->stoned : 0.0f;
    out8[2] = xs ? (float)xs->birded : 0.0f;
    out8[3] = xs ? (float)xs->fished : 0.0f;
    out8[4] = xs ? (float)xs->carted : 0.0f;
    out8[5] = xs ? (float)xs->walljumpboost : 0.0f;
    out8[6] = xs ? (float)xs->hang : 0.0f;
    out8[7] = xs ? (float)xs->fire : 0.0f;
}
int iw_hb(void* h, int* out4) {
    IWanna* e = &((Handle*)h)->env;
    out4[0] = e->hb_l; out4[1] = e->hb_t; out4[2] = e->hb_r; out4[3] = e->hb_b;
    return 0;
}
