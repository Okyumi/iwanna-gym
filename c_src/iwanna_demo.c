/* Pure C demo: play IWanna with the keyboard (requires raylib), or run a
 * headless random-agent throughput benchmark.
 *
 * Interactive:  gcc -O2 -o iwanna_demo iwanna_demo.c -lraylib -lm && ./iwanna_demo [level]
 * Benchmark:    gcc -O2 -DIW_NO_RAYLIB -o iwanna_bench iwanna_demo.c -lm && ./iwanna_bench [level]
 *
 * Controls: left/right arrows move, shift (or Z) jump, X shoot, ESC quit.
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "iwanna.h"

int main(int argc, char** argv) {
    int level = argc > 1 ? atoi(argv[1]) : 1;
    IWanna env = {0};
    env.observations = (float*)calloc(IW_OBS_SIZE, sizeof(float));
    env.actions = (int*)calloc(1, sizeof(int));
    env.rewards = (float*)calloc(1, sizeof(float));
    env.terminals = (unsigned char*)calloc(1, sizeof(unsigned char));
    env.max_steps = 1500;
    env.reward_mode = 1;
    env.death_penalty = 1.0f;
    env.rng = (uint64_t)time(NULL) | 1;
    if (iw_load_builtin(&env, level) != 0) {
        fprintf(stderr, "bad level\n");
        return 1;
    }
    c_reset(&env);

#ifdef IW_NO_RAYLIB
    /* headless throughput benchmark: random actions */
    const long N = 50 * 1000 * 1000;
    clock_t t0 = clock();
    for (long i = 0; i < N; i++) {
        env.actions[0] = (int)(iw_rand(&env) % IW_NUM_ACTIONS);
        c_step(&env);
    }
    double dt = (double)(clock() - t0) / CLOCKS_PER_SEC;
    printf("%ld steps in %.2fs = %.2fM steps/sec (single core)\n", N, dt, N / dt / 1e6);
    printf("episodes: %.0f  goals: %.0f  deaths: %.0f\n",
           env.log.n, env.log.score, env.log.death);
#else
    c_render(&env);
    while (!WindowShouldClose()) {
        int h = 1;
        if (IsKeyDown(KEY_LEFT))  h = 0;
        if (IsKeyDown(KEY_RIGHT)) h = 2;
        int j = (IsKeyDown(KEY_LEFT_SHIFT) || IsKeyDown(KEY_Z)) ? 1 : 0;
        int s = IsKeyDown(KEY_X) ? 1 : 0;
        env.actions[0] = 6 * s + 2 * h + j;
        c_step(&env);
        c_render(&env);
        if (env.terminals[0]) {
            const char* what[] = {"?", "died", "goal", "timeout"};
            printf("episode end: %s\n", what[env.last_event]);
        }
    }
#endif
    free(env.observations); free(env.actions); free(env.rewards); free(env.terminals);
    c_close(&env);
    return 0;
}
