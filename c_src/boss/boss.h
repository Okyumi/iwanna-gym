/* boss.h — the reusable boss framework (services shared by every boss).
 *
 * Included by exact_impl.h after the exact-layer primitives (iwx_spawn,
 * iwx_hit_rect, iw_rand, ...) and before iwx_update_ent, so boss step
 * functions are ordinary exact-layer behaviors that additionally own an
 * IWXBossState slot (see boss_types.h).
 *
 * What the framework provides (per the boss architecture doc):
 *   - slot allocation keyed to the body xent (works for placed bodies and
 *     for bodies spawned mid-room by trigger ops alike; room reload zeroes
 *     the slots, so death/retry resets a fight exactly like the source's
 *     room restart);
 *   - hit points / cumulative damage with threshold phase transitions
 *     (iwxb_take applies routed damage honoring invulnerability windows);
 *   - GM-style alarms (iwxb_alarm) and the master step timer;
 *   - weak points: hidden XB_WEAKBOX xents whose masks are the source
 *     hitbox sprites; bosses place or park them per animation frame
 *     (moving hitboxes), the bullet router accumulates damage into the
 *     slot (push mode), or the boss pulls overlapping bullets itself in
 *     its step (pull mode) — the two idioms the source games use;
 *   - projectile/minion spawning from pack templates, with a reserved-
 *     capacity guard for purely visual spawns;
 *   - arena transitions (pending room goto), progression flags, player
 *     kill, camera modes (lock / follow / piledriver / shake);
 *   - seeded randomness helpers matching GM's irandom/irandom_range/
 *     random call sites (distributions match; the stream is the
 *     environment's own seeded RNG — documented deviation).
 *
 * Overhead when no boss is live: n_boss == 0 short-circuits the bullet
 * router (one integer compare per bullet per frame); nothing else runs.
 */
#ifndef IWX_BOSS_H
#define IWX_BOSS_H

/* ---------------- slots ---------------- */

static IWXBossState* iwxb_slot_of(IWXState* xs, const IWXEnt* e) {
    for (int i = 0; i < IWXB_MAX; i++)
        if (xs->boss[i].used && xs->ents[xs->boss[i].ent].cls == e->cls &&
            &xs->ents[xs->boss[i].ent] == e)
            return &xs->boss[i];
    return NULL;
}

/* find-or-create the slot for a live boss body (lazy: first step calls
 * the per-boss init exactly once, mirroring the source Create event) */
static IWXBossState* iwxb_slot(IWanna* env, IWXEnt* e, int def, int* fresh) {
    IWXState* xs = XS(env);
    int idx = (int)(e - xs->ents);
    for (int i = 0; i < IWXB_MAX; i++)
        if (xs->boss[i].used && xs->boss[i].ent == idx) {
            *fresh = 0; return &xs->boss[i];
        }
    for (int i = 0; i < IWXB_MAX; i++) {
        IWXBossState* bs = &xs->boss[i];
        if (bs->used) continue;
        memset(bs, 0, sizeof *bs);
        bs->used = 1; bs->def = (uint8_t)def; bs->ent = idx;
        for (int a = 0; a < IWXB_ALARMS; a++) bs->alarm[a] = -1;
        for (int w = 0; w < IWXB_WEAK; w++) bs->wp_ent[w] = -1;
        xs->n_boss++;
        *fresh = 1;
        return bs;
    }
    *fresh = 0;
    return NULL;                       /* full: boss stands inert */
}

static void iwxb_release(IWXState* xs, IWXBossState* bs) {
    for (int w = 0; w < IWXB_WEAK; w++)
        if (bs->wp_ent[w] >= 0) xs->ents[bs->wp_ent[w]].alive = 0;
    bs->used = 0;
    if (xs->n_boss > 0) xs->n_boss--;
}

static inline IWXEnt* iwxb_body(IWXState* xs, IWXBossState* bs) {
    return &xs->ents[bs->ent];
}

/* ---------------- alarms (GM semantics: set to N, fires N steps later) */

static inline int iwxb_alarm(IWXBossState* bs, int i) {
    if (bs->alarm[i] > 0 && --bs->alarm[i] == 0) {
        bs->alarm[i] = -1;
        return 1;
    }
    return 0;
}

/* ---------------- seeded randomness (call-site compatible) ---------- */

static inline int iwxb_irandom(IWanna* env, int n) {        /* 0..n */
    return n <= 0 ? 0 : (int)(iw_rand(env) % (uint64_t)(n + 1));
}
static inline int iwxb_irandom_range(IWanna* env, int a, int b) {
    return a + iwxb_irandom(env, b - a);
}
static inline double iwxb_random(IWanna* env, double n) {   /* [0,n) */
    return (double)(iw_rand(env) >> 11) / 9007199254740992.0 * n;
}
static inline double iwxb_random_range(IWanna* env, double a, double b) {
    return a + iwxb_random(env, b - a);
}

/* ---------------- spawning ---------------- */

static inline IWXEnt* iwxb_spawn(IWanna* env, int tmpl, float x, float y) {
    return iwx_spawn(env, tmpl, x, y);
}

/* visual-only spawns must never crowd out gameplay entities */
static inline IWXEnt* iwxb_spawn_visual(IWanna* env, int tmpl,
                                        float x, float y) {
    IWXState* xs = XS(env);
    int free_slots = 0;
    for (int i = 0; i < xs->cap && free_slots <= IWXB_SPAWN_KEEP; i++)
        if (!xs->ents[i].alive) free_slots++;
    if (xs->n_ents < xs->cap) free_slots += xs->cap - xs->n_ents;
    if (free_slots <= IWXB_SPAWN_KEEP) return NULL;
    return iwx_spawn(env, tmpl, x, y);
}

/* ---------------- weak points (moving hitboxes) ---------------- */

static void iwxb_wp_make(IWanna* env, IWXBossState* bs, int i, int tmpl) {
    IWXEnt* w = iwx_spawn(env, tmpl, -400.0f, -9999.0f);
    if (w) {
        w->cls = XB_WEAKBOX;
        bs->wp_ent[i] = (int)(w - XS(env)->ents);
    }
}

static inline void iwxb_wp_place(IWXState* xs, IWXBossState* bs, int i,
                                 float x, float y) {
    if (bs->wp_ent[i] >= 0) {
        xs->ents[bs->wp_ent[i]].x = x;
        xs->ents[bs->wp_ent[i]].y = y;
    }
}
static inline void iwxb_wp_park(IWXState* xs, IWXBossState* bs, int i) {
    iwxb_wp_place(xs, bs, i, -400.0f, -9999.0f);
}
static inline void iwxb_wp_off(IWXState* xs, IWXBossState* bs, int i) {
    if (bs->wp_ent[i] >= 0) {
        xs->ents[bs->wp_ent[i]].alive = 0;
        bs->wp_ent[i] = -1;
    }
}

/* consume damage the bullet router accumulated on weak point i since the
 * last call (GM: Collision_bullet latches `damage`, the next Step applies
 * it).  Returns the damage taken; honors an invulnerability window whose
 * countdown the caller keeps in *iframes (damage arriving while it is
 * nonzero is discarded, as the source hitboxes do while parked). */
static inline float iwxb_take(IWXBossState* bs, int i, int* iframes) {
    float d = bs->wp_dmg[i];
    bs->wp_dmg[i] = 0;
    if (iframes) {
        if (*iframes > 0) { (*iframes)--; return 0.0f; }
        if (d > 0) *iframes = 0;
    }
    return d;
}

/* pull mode: destroy every active player bullet overlapping weak xent wp
 * (positions as of before this frame's bullet motion — the GM order when
 * the boss's own Step does instance_place(bullet)); returns damage sum */
static float iwxb_pull_bullets(IWanna* env, int wp_ent) {
    IWXState* xs = XS(env);
    if (wp_ent < 0) return 0;
    IWXEnt* w = &xs->ents[wp_ent];
    if (!w->alive) return 0;
    float dmg = 0;
    for (int i = 0; i < env->ent_top; i++) {
        IWEntity* b = &env->entities[i];
        if (b->type != E_PBULLET || !(b->flags & EF_ACTIVE)) continue;
        int bx = gm_round(b->x), by = gm_round(b->y);
        if (iwx_hit_rect(xs, w, bx + IW_BULLET_L, bx + IW_BULLET_R,
                         by + IW_BULLET_T, by + IW_BULLET_B)) {
            b->flags &= ~EF_ACTIVE;
            dmg += 1.0f;
        }
    }
    return dmg;
}

/* ---------------- bullet router (collision phase, push mode) --------- */
/* Called from the E_PBULLET step when n_boss > 0, after the bullet moved.
 * Weak-point overlap consumes the bullet and accumulates wp_dmg (applied
 * by the boss next step, matching GM collision->step latency).  A body
 * deflect (Kraidgief) redirects the bullet instead of consuming it.
 * Returns 1 when the bullet was consumed. */
static int iwxb_route_bullet(IWanna* env, IWEntity* b,
                             int bl, int br, int bt, int bb);

/* ---------------- arena / completion services ---------------- */

static inline void iwxb_goto_room(IWanna* env, int room, float x, float y,
                                  int use_start) {
    env->pending_room = room;
    env->pending_use_start = use_start;
    env->pending_keep_speed = 0;
    if (!use_start) { env->pending_x = x; env->pending_y = y; }
}

static inline void iwxb_set_flag(IWanna* env, int bit) {
    env->gflags |= 1ull << bit;
}

static inline void iwxb_kill_player(IWanna* env) {
    XS(env)->pending_kill = 1;
}

/* camera (XCAM_KRAID rooms) */
static inline void iwxb_cam_lock(IWanna* env, int on) {
    XS(env)->cam_locked = (uint8_t)on;
}
static inline void iwxb_cam_piledriver(IWanna* env, int on) {
    XS(env)->cam_piledriver = (uint8_t)on;
}
static inline void iwxb_cam_shake(IWanna* env, float voffset) {
    XS(env)->cam_voffset = voffset;
}

/* animation helper: advance frame by fspd, report GM Animation End */
static inline int iwxb_anim(IWXEnt* e, int nframes) {
    if (e->fspd == 0 || nframes <= 0) return 0;
    e->frame += e->fspd;
    if (e->frame >= (float)nframes) {
        e->frame -= (float)nframes;
        return 1;
    }
    return 0;
}

static inline int iwxb_nframes(IWXState* xs, const IWXEnt* e) {
    const IWXMaskRec* m = iwx_mask(xs, e->mask);
    return m ? m->nframes : 1;
}

/* ---------------- the synthetic framework-test boss ---------------- *
 * Exercises every framework feature without any game content; driven by
 * template params so tests can compile a tiny pack around it:
 *   p0 weak-point template     p5 progression flag bit on death
 *   p1 projectile template     p6 i-frames after each accepted hit
 *   p2 phase-1 hit points      p7 dest room on death (-1: stay)
 *   p3 phase-2 hit points      p8 projectile speed (px/f, fired left)
 *   p4 attack period (frames)  p9 unused
 * Slot p[]: p0 = i-frame countdown.                                    */
static void iwxb_test_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_TEST, &fresh);
    if (!bs) return;
    if (fresh) {
        bs->phase = 1;
        bs->hp = e->p[2];
        bs->alarm[0] = (int)e->p[4];
        iwxb_wp_make(env, bs, 0, (int)e->p[0]);
        bs->f |= IWXB_F_VULN;
    }
    if (bs->f & IWXB_F_DEAD) return;
    bs->timer++;

    if (iwxb_alarm(bs, 0)) {                    /* attack state machine */
        IWXEnt* s = iwxb_spawn(env, (int)e->p[1], e->x - 16.0f, e->y);
        if (s) s->vx = -e->p[8];
        bs->alarm[0] = bs->phase == 1 ? (int)e->p[4] : (int)e->p[4] / 2;
    }

    iwxb_wp_place(xs, bs, 0, e->x, e->y - 32.0f);   /* moving hitbox */

    int iframes = (int)bs->p[0];
    float d = iwxb_take(bs, 0, &iframes);
    if (d > 0) iframes = (int)e->p[6];
    bs->p[0] = (float)iframes;
    if (d > 0) {
        bs->hp -= d;
        bs->dmg += d;
        if (bs->hp <= 0) {
            if (bs->phase == 1) {
                bs->phase = 2;
                bs->hp = e->p[3];
            } else {
                bs->f |= IWXB_F_DEAD;
                bs->f &= ~IWXB_F_VULN;
                if ((int)e->p[5] >= 0) iwxb_set_flag(env, (int)e->p[5]);
                if ((int)e->p[7] >= 0)
                    iwxb_goto_room(env, (int)e->p[7], 0, 0, 1);
                e->alive = 0;
                iwxb_release(xs, bs);
            }
        }
    }
}

#endif /* IWX_BOSS_H */
