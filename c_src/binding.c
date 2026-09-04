/* PufferLib Ocean binding for IWanna.
 * Drop this env into pufferlib/ocean/iwanna/ as:
 *   iwanna.h  iwanna.c (demo)  binding.c
 * plus config/iwanna.ini, then:  puffer build iwanna && puffer train iwanna
 *
 * Action space: declare Discrete(12) on the Python side for the full space
 * (a = shoot_held*6 + 2*(h+1) + jump_held; docs/action_and_reset_semantics.md).
 * Actions 0..5 are the legacy no-shoot space — declare Discrete(6) to
 * reproduce pre-shooting experiments; the core accepts both.
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
    /* discovery task/attempt protocol (config/iwanna.ini [env]):
     *   discovery=1 makes one episode == one TASK of up to attempts_K
     *   death/timeout-bounded attempts (terminals fire only at task
     *   end, so recurrent state naturally persists across attempts and
     *   is cut by the trainer at the episode boundary = task reset);
     *   obs_mode 0 = privileged legacy vector (forbidden for headline
     *   discovery runs), 1 = observable vector (contract section 7).
     *   task_seed (optional, nonzero) pins the first task's seed for
     *   deterministic replay; later tasks derive from the env stream. */
    env->discovery = (int)unpack(kwargs, "discovery");
    env->attempts_K = (int)unpack(kwargs, "attempts_K");
    env->attempt_frames_H = (int)unpack(kwargs, "attempt_frames_H");
    env->obs_mode = (int)unpack(kwargs, "obs_mode");
    env->task_seed_next = (uint64_t)unpack(kwargs, "task_seed");
    if (env->obs_mode != IW_OBS_PRIVILEGED &&
        env->obs_mode != IW_OBS_OBSERVABLE) return 1;
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
    /* discovery task metrics (zero when discovery=0): attempts used per
     * ended task and task-success indicator — the per-task inputs for
     * Success@K and the success-versus-attempt curve. Diagnostics flow
     * ONLY through this log path, never into policy observations. */
    assign_to_dict(dict, "attempts", log->attempts);
    assign_to_dict(dict, "task_success", log->task_success);
    return 0;
}
