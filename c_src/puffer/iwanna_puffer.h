/* PufferLib Ocean (4.0.0) adapter for the IWanna core.
 *
 * PufferLib 4.0.0's Ocean binding contract (src/vecenv.h) wires each
 * env slot's buffers as:
 *     float* observations;  float* actions;
 *     float* rewards;       float* terminals;   int num_agents;
 * and calls c_reset/c_step/c_render/c_close on the Env type, with a
 * Log struct of floats aggregated by static_vec + my_log. The IWanna
 * core instead uses int* actions and unsigned char* terminals, so this
 * thin adapter wraps an IWanna and translates the mismatched buffer
 * types every frame WITHOUT touching the core (the ctypes/CVecIWanna
 * path keeps its int/uint8 buffers). This is the real current-API
 * binding; the retired c_src/binding.c targeted PufferLib's old
 * env_binding.h API.
 *
 * The core's c_reset/c_step are renamed to iwcore_* here so the
 * adapter can own the c_reset/c_step(Env*) symbols vecenv.h calls.
 * That rename is local to THIS translation unit; libiwanna.so
 * (iwanna_capi.c) includes iwanna.h unrenamed and is unaffected.
 *
 * Build/run: docs/pufferlib_integration.md (pinned PufferLib
 * 42f70d69 == 4.0.0). Pack/level paths + discovery config arrive via
 * env vars / numeric kwargs; game bytes are never committed.
 */
#ifndef IWANNA_PUFFER_H
#define IWANNA_PUFFER_H

#include <math.h>
#include <stdlib.h>
#include <string.h>

#ifndef IW_NO_RAYLIB
#define IW_NO_RAYLIB 1
#endif

/* rename the core lifecycle fns so the adapter can define its own */
#define c_reset  iwcore_reset
#define c_step   iwcore_step
#define c_render iwcore_render
#define c_close  iwcore_close
#include "../iwanna.h"
#undef c_reset
#undef c_step
#undef c_render
#undef c_close

typedef struct PufferIWanna {
    Log log;                 /* MUST be first: static_vec aggregates it */
    float* observations;     /* puffer-owned (OBS_SIZE floats) */
    float* actions;          /* puffer-owned (NUM_ATNS floats) */
    float* rewards;          /* puffer-owned (1 float) */
    float* terminals;        /* puffer-owned (1 float) */
    int num_agents;

    int rng;                 /* per-env seed written by vecenv.h my_vec_init */

    IWanna inner;            /* the actual simulation */
    int inner_action;
    unsigned char inner_term;
    float inner_reward;

    /* construction config (from my_init) */
    int cfg_discovery, cfg_attempts_K, cfg_attempt_frames_H, cfg_obs_mode;
    int cfg_use_pack, cfg_difficulty;
    int cfg_task_start_set, cfg_task_start_room;
    double cfg_task_start_x, cfg_task_start_y;
    int cfg_task_goal_set, cfg_task_goal_room;
    double cfg_gx0, cfg_gy0, cfg_gx1, cfg_gy1;
    unsigned long long cfg_task_seed;
    int cfg_max_steps, cfg_reward_mode;
    float cfg_death_penalty;
    int built;
} PufferIWanna;

/* load the level/pack, wire buffers, apply discovery + task anchoring */
static void ipuf_build(PufferIWanna* e) {
    IWanna* iw = &e->inner;
    iw->observations = e->observations;      /* share the obs block */
    iw->actions = &e->inner_action;
    iw->rewards = &e->inner_reward;
    iw->terminals = &e->inner_term;
    iw->max_steps = e->cfg_max_steps > 0 ? e->cfg_max_steps : 1500;
    iw->reward_mode = e->cfg_reward_mode;
    iw->death_penalty = e->cfg_death_penalty;
    iw->hb_l = HB_L; iw->hb_t = HB_T; iw->hb_r = HB_R; iw->hb_b = HB_B;
    /* deterministic per-env seed: vecenv.h writes e->rng = env index */
    iw->rng = 0x9E3779B97F4A7C15ULL ^ ((uint64_t)(unsigned)e->rng * 2654435761u)
              ^ (uint64_t)(uintptr_t)e;

    char err[256];
    if (e->cfg_use_pack) {
        const char* p = getenv("IWG_PACK");
        if (!p || iw_load_pack_file(iw, p, err, sizeof err) != 0) {
            fprintf(stderr, "iwanna_puffer: pack load failed: %s\n",
                    p ? err : "IWG_PACK unset");
            exit(1);
        }
        iw->checkpoint_respawn = 1;
        if (e->cfg_difficulty >= 0 && e->cfg_difficulty <= 3)
            iw->difficulty = e->cfg_difficulty;
    } else {
        const char* lv = getenv("IWG_LEVEL_FILE");
        if (lv) {
            FILE* f = fopen(lv, "rb");
            if (!f) { fprintf(stderr, "iwanna_puffer: level open\n"); exit(1); }
            fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
            char* txt = (char*)malloc((size_t)n + 1);
            if (fread(txt, 1, (size_t)n, f) != (size_t)n) exit(1);
            fclose(f); txt[n] = 0;
            if (iw_load_level(iw, txt) != 0) exit(1);
            free(txt);
        } else if (iw_load_builtin(iw, 1) != 0) {   /* default builtin */
            exit(1);
        }
    }
    if (e->cfg_discovery) {
        iw->discovery = 1;
        iw->attempts_K = e->cfg_attempts_K;
        iw->attempt_frames_H = e->cfg_attempt_frames_H;
    }
    iw->obs_mode = e->cfg_obs_mode;
    if (e->cfg_task_start_set) {
        if (iw->pack && e->cfg_task_start_room >= 0)
            iw->start_room = e->cfg_task_start_room;
        iw->task_start_set = 1;
        iw->task_start_x = e->cfg_task_start_x;
        iw->task_start_y = e->cfg_task_start_y;
    }
    if (e->cfg_task_goal_set) {
        iw->task_goal_set = 1;
        iw->task_goal_room = e->cfg_task_goal_room;
        iw->task_gx0 = e->cfg_gx0; iw->task_gy0 = e->cfg_gy0;
        iw->task_gx1 = e->cfg_gx1; iw->task_gy1 = e->cfg_gy1;
    }
    if (e->cfg_task_seed) iw->task_seed_next = e->cfg_task_seed;
    e->built = 1;
}

static void c_reset(PufferIWanna* e) {
    if (!e->built) ipuf_build(e);
    iwcore_reset(&e->inner);
    e->rewards[0] = e->inner_reward;
    e->terminals[0] = (float)e->inner_term;
}

/* accumulate the core's per-step Log delta into the puffer Log, which
 * static_vec zeroes when it reads (so this must ADD, not overwrite) */
static void ipuf_accumulate_log(PufferIWanna* e) {
    int n = sizeof(Log) / sizeof(float);
    float* dst = (float*)&e->log;
    float* src = (float*)&e->inner.log;
    for (int i = 0; i < n; i++) dst[i] += src[i];
    memset(&e->inner.log, 0, sizeof(Log));  /* inner.log = per-step delta */
}

static void c_step(PufferIWanna* e) {
    e->inner_action = (int)lroundf(e->actions[0]);
    iwcore_step(&e->inner);
    e->rewards[0] = e->inner_reward;
    e->terminals[0] = (float)e->inner_term;
    ipuf_accumulate_log(e);
}

static void c_render(PufferIWanna* e) { (void)e; }   /* headless */
static void c_close(PufferIWanna* e) { iw_free(&e->inner); }

#endif /* IWANNA_PUFFER_H */
