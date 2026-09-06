/* PufferLib Ocean (4.0.0) binding for IWanna.
 *
 * Pinned PufferLib: github.com/PufferAI/PufferLib @ 42f70d69 (4.0.0).
 * Install/build/run: docs/pufferlib_integration.md. This file is the
 * env's static-library entry point; drop c_src/ into the pinned
 * PufferLib's ocean/iwanna/ (see the setup script) and build with the
 * standard puffer toolchain.
 *
 * Discrete action space: declare Discrete(12) on the Python side for
 * the full shoot-enabled space (a = shoot_held*6 + 2*(h+1) + jump_held;
 * docs/action_and_reset_semantics.md). Actions 0..5 are the legacy
 * no-shoot space. Actions arrive as float and are rounded to int.
 */
#include "iwanna_puffer.h"

#define OBS_SIZE IW_OBS_SIZE      /* 101 */
#define NUM_ATNS 1
#define ACT_SIZES {IW_NUM_ACTIONS}   /* 12 */
#define OBS_TENSOR_T FloatTensor

#define Env PufferIWanna
#include "vecenv.h"

void my_init(Env* env, Dict* kwargs) {
    env->num_agents = 1;
    /* numeric kwargs from config/iwanna.ini [env]; file paths (pack /
     * level) travel via the IWG_PACK / IWG_LEVEL_FILE env vars because
     * Dict values are doubles. */
    env->cfg_max_steps      = (int)dict_get(kwargs, "max_steps")->value;
    env->cfg_reward_mode    = (int)dict_get(kwargs, "reward_mode")->value;
    env->cfg_death_penalty  = (float)dict_get(kwargs, "death_penalty")->value;
    env->cfg_discovery      = (int)dict_get(kwargs, "discovery")->value;
    env->cfg_attempts_K     = (int)dict_get(kwargs, "attempts_K")->value;
    env->cfg_attempt_frames_H = (int)dict_get(kwargs, "attempt_frames_H")->value;
    env->cfg_obs_mode       = (int)dict_get(kwargs, "obs_mode")->value;
    env->cfg_use_pack       = (int)dict_get(kwargs, "use_pack")->value;
    env->cfg_difficulty     = (int)dict_get(kwargs, "difficulty")->value;
    env->cfg_task_start_set = (int)dict_get(kwargs, "task_start_set")->value;
    env->cfg_task_start_room = (int)dict_get(kwargs, "task_start_room")->value;
    env->cfg_task_start_x   = dict_get(kwargs, "task_start_x")->value;
    env->cfg_task_start_y   = dict_get(kwargs, "task_start_y")->value;
    env->cfg_task_goal_set  = (int)dict_get(kwargs, "task_goal_set")->value;
    env->cfg_task_goal_room = (int)dict_get(kwargs, "task_goal_room")->value;
    env->cfg_gx0 = dict_get(kwargs, "task_gx0")->value;
    env->cfg_gy0 = dict_get(kwargs, "task_gy0")->value;
    env->cfg_gx1 = dict_get(kwargs, "task_gx1")->value;
    env->cfg_gy1 = dict_get(kwargs, "task_gy1")->value;
    env->cfg_task_seed = (unsigned long long)dict_get(kwargs, "task_seed")->value;
    if (env->cfg_obs_mode != IW_OBS_PRIVILEGED &&
        env->cfg_obs_mode != IW_OBS_OBSERVABLE) {
        fprintf(stderr, "iwanna binding: bad obs_mode\n");
        exit(1);
    }
    /* the level/pack is loaded lazily on first c_reset (ipuf_build),
     * after vecenv.h has assigned env->observations/actions/... */
}

void my_log(Log* log, Dict* out) {
    dict_set(out, "perf", log->perf);
    dict_set(out, "score", log->score);
    dict_set(out, "episode_return", log->episode_return);
    dict_set(out, "episode_length", log->episode_length);
    dict_set(out, "death", log->death);
    dict_set(out, "attempts", log->attempts);        /* discovery */
    dict_set(out, "task_success", log->task_success); /* discovery */
}
