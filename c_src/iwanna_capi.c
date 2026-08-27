/* ctypes shared-library API for the IWanna core.
 * Build:
 *   gcc -O2 -fPIC -shared -DIW_NO_RAYLIB -o libiwanna.so iwanna_capi.c -lm
 *
 * Python allocates the numpy buffers (observations, actions, rewards,
 * terminals) and passes their pointers in; the env writes into them
 * following the PufferLib Ocean convention (auto-reset inside step).
 */
#include <stdlib.h>
#include "iwanna.h"

typedef struct {
    IWanna env;
} Handle;

/* returns NULL on level-parse failure */
void* iw_new(const char* level_text,
             float* observations, int* actions, float* rewards,
             unsigned char* terminals,
             int max_steps, int reward_mode, float death_penalty,
             int random_goal, unsigned long long seed) {
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
    e->rng = seed ? seed : 0x9E3779B97F4A7C15ULL;
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
                     int random_goal, unsigned long long seed) {
    if (level_idx < 0 || level_idx >= IW_NUM_LEVELS) return NULL;
    return iw_new(IW_LEVELS[level_idx], observations, actions, rewards,
                  terminals, max_steps, reward_mode, death_penalty,
                  random_goal, seed);
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

int iw_obs_size(void)    { return IW_OBS_SIZE; }
int iw_num_actions(void) { return IW_NUM_ACTIONS; }
int iw_num_levels(void)  { return IW_NUM_LEVELS; }
const char* iw_level_text(int idx) {
    if (idx < 0 || idx >= IW_NUM_LEVELS) return "";
    return IW_LEVELS[idx];
}
