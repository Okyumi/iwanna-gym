/* PufferLib Ocean binding for IWanna.
 * Drop this env into pufferlib/ocean/iwanna/ as:
 *   iwanna.h  iwanna.c (demo)  binding.c
 * plus config/iwanna.ini, then:  puffer build iwanna && puffer train iwanna
 */
#include "iwanna.h"

#define Env IWanna
#include "../env_binding.h"

static int my_init(Env* env, PyObject* args, PyObject* kwargs) {
    int level = (int)unpack(kwargs, "level");
    env->max_steps = (int)unpack(kwargs, "max_steps");
    env->reward_mode = (int)unpack(kwargs, "reward_mode");
    env->death_penalty = (float)unpack(kwargs, "death_penalty");
    env->random_goal = (int)unpack(kwargs, "random_goal");
    if (env->rng == 0) env->rng = 0x9E3779B97F4A7C15ULL ^ (uint64_t)(uintptr_t)env;
    if (iw_load_builtin(env, level) != 0) return 1;
    return 0;
}

static int my_log(PyObject* dict, Log* log) {
    assign_to_dict(dict, "perf", log->perf);
    assign_to_dict(dict, "score", log->score);
    assign_to_dict(dict, "episode_return", log->episode_return);
    assign_to_dict(dict, "episode_length", log->episode_length);
    assign_to_dict(dict, "death", log->death);
    return 0;
}
