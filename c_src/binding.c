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

    /* ---- registry-driven task loading (discovery suite loader) ----
     * The task registry (iwanna_gym/discovery) resolves a task id to
     * NUMERIC kwargs (this function) plus the pack file, which cannot
     * travel through numeric kwargs and therefore comes from the
     * IWG_PACK environment variable when use_pack=1. The same path
     * loads ANY compiled .iwpack — a future iwbtg_original_2007 pack
     * needs a new pack file, not a binding rewrite. Content overrides
     * touch only where the attempt starts and what counts as success;
     * source geometry/triggers/physics/timing are untouched. */
    int use_pack = (int)unpack(kwargs, "use_pack");
    int use_level_file = (int)unpack(kwargs, "use_level_file");
    if (use_pack) {
        const char* p = getenv("IWG_PACK");
        char err[256];
        if (!p || iw_load_pack_file(env, p, err, sizeof err) != 0)
            return 1;
        env->checkpoint_respawn = 1;
        int diff = (int)unpack(kwargs, "difficulty");
        if (diff >= 0 && diff <= 3) env->difficulty = diff;
    } else if (use_level_file) {
        /* controlled research rooms are text files; the path comes
         * from IWG_LEVEL_FILE (kwargs are numeric-only) */
        const char* p = getenv("IWG_LEVEL_FILE");
        if (!p) return 1;
        FILE* f = fopen(p, "rb");
        if (!f) return 1;
        fseek(f, 0, SEEK_END);
        long n = ftell(f);
        fseek(f, 0, SEEK_SET);
        char* txt = n > 0 ? (char*)malloc((size_t)n + 1) : NULL;
        if (!txt || fread(txt, 1, (size_t)n, f) != (size_t)n) {
            fclose(f); free(txt); return 1;
        }
        fclose(f);
        txt[n] = 0;
        int rc = iw_load_level(env, txt);
        free(txt);
        if (rc != 0) return 1;
    } else {
        if (iw_load_builtin(env, level) != 0) return 1;
    }
    int ts_room = (int)unpack(kwargs, "task_start_room");
    if (ts_room >= -1 && (int)unpack(kwargs, "task_start_set")) {
        if (env->pack && ts_room >= 0) {
            if (ts_room >= (int)env->pack->hdr.n_rooms) return 1;
            env->start_room = ts_room;
        }
        env->task_start_set = 1;
        env->task_start_x = unpack(kwargs, "task_start_x");
        env->task_start_y = unpack(kwargs, "task_start_y");
    }
    if ((int)unpack(kwargs, "task_goal_set")) {
        env->task_goal_set = 1;
        env->task_goal_room = (int)unpack(kwargs, "task_goal_room");
        env->task_gx0 = unpack(kwargs, "task_gx0");
        env->task_gy0 = unpack(kwargs, "task_gy0");
        env->task_gx1 = unpack(kwargs, "task_gx1");
        env->task_gy1 = unpack(kwargs, "task_gy1");
        if (env->task_gx1 < env->task_gx0 ||
            env->task_gy1 < env->task_gy0) return 1;
    }
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
