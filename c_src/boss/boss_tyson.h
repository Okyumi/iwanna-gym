/* boss_tyson.h — Mike Tyson (rGuy1), transliterated from
 * objects/Tyson.gml + TysonFist / TysonFireball / TysonDoor / OrbTyson.
 *
 * Body template/record p[]: p0 fist weak template (sprTysonFist x11/3,
 * KILLER — the fist both kills and receives bullets), p1 TysonFireball
 * tmpl, p2 OrbTyson tmpl, p9 progression flag (orb_tyson; loader skip).
 *
 * Slot: phase 0..2 (three knockdowns), bs->hp stage HP (5), timer = the
 * source master timer; p0 = base_speed, p1 = ystart (96), p2 = facing
 * (sign of image_xscale), p3 = hitted flag, p4 = running.
 * The ~2050-frame intro (walk-in cutscene, door close, rise, dance) runs
 * at source timing; skipButton is out of the action space (deviation).
 * Fight: the 515-frame punch schedule — uppercuts at [100,120)/[200,220)
 * /[300,320) (floor punch instead in phase 2), floor punches at
 * [350,380) knocking one random overlapped TysonBrick out, fireball
 * vomit at [450,510) — the only vulnerable window (the fist sits at his
 * mouth; shooting it deals damage). 5 hits = knockdown; three knockdowns
 * = victory: referee (visual), then the orb spawns at (4064,288) and
 * the doors + Tyson leave the arena.
 */
#ifndef IWX_BOSS_TYSON_H
#define IWX_BOSS_TYSON_H

#define TY_HITTED   (IWXB_F_USER << 0)
#define TY_RUNNING  (IWXB_F_USER << 1)
#define TY_VULN     IWXB_F_VULN

static void iwxb_tyson_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_TYSON, &fresh);
    if (!bs) return;
    if (fresh) {                                   /* Create */
        bs->f |= IWXB_F_INTRO | IWXB_F_PUSH;
        bs->phase = 0;
        bs->hp = 5;
        bs->p[1] = e->y;                           /* ystart (96) */
        e->y = ceilf(e->y / 608.0f) * 608.0f - 10.0f;
        bs->p[2] = 1;                              /* facing */
        iwxb_wp_make(env, bs, 0, (int)e->p[0]);    /* the fist */
    }
    float ystart = bs->p[1];
    IWXEnt* fist = bs->wp_ent[0] >= 0 ? &xs->ents[bs->wp_ent[0]] : NULL;

    /* trigger pulse -> running (doors close visually; already solid) */
    if (e->on && !(bs->f & TY_RUNNING)) bs->f |= TY_RUNNING;

    if (bs->f & IWXB_F_INTRO) {
        if (bs->timer == 0) {
            if (bs->f & TY_RUNNING) {
                xs->cutscene = 1;
                if (env->x < e->x) xs->force_h = 1;
                else { xs->force_h = 0; bs->timer += 1; }
            }
        } else {
            if (bs->timer == 103 || bs->timer == 403 || bs->timer == 703)
                iwxb_cam_shake(env, -6);
            if (bs->timer == 750) e->vy = -1.0f;
            if (bs->timer == 2050) {
                xs->cutscene = 0; xs->force_h = 0;
                bs->f &= ~IWXB_F_INTRO;
                bs->timer = 0;
            }
            if (fmodf(e->y, 608.0f) <= ystart) e->vy = 0;
            if (bs->timer != 0) bs->timer += 1;
        }
        e->y += e->vy;
        if (fist) { fist->x = -1000; fist->y = -1000; }
        return;
    }

    if (bs->f & TY_HITTED) {
        if (bs->hp > 0) {                          /* damage flinch */
            if (bs->timer < 10) { }
            else if (bs->timer < 15) {
                if (fist) fist->y = -1000;
                bs->f &= ~TY_VULN;
                e->vy = -6;
            } else if (bs->timer < 20) e->vy = 6;
            else { bs->timer = 470; bs->f &= ~TY_HITTED; }
        } else {                                   /* knockdown */
            if (bs->timer < 100) {
                if (bs->timer == 16 || bs->timer == 32 || bs->timer == 48)
                    bs->p[2] = -bs->p[2];
                e->vx = bs->p[2] * 2;
                e->vy = 4 + bs->timer / 8.0f;
                if (bs->timer % 16 < 2) { e->vx = 0; e->vy = 0; }
            } else if (bs->timer < 300) {
                e->vx = 0; e->vy = 0;
            } else if (bs->timer < 320 && bs->phase < 2) {
                e->x = 3584;                       /* get up */
                e->y = bs->timer >= 310 ? ystart : ystart + 200;
                if (bs->timer < 310) e->x -= 200 * (bs->p[2] > 0 ? 1 : -1);
                e->vx = 0; e->vy = 0;
            } else if (bs->phase == 2) {
                e->vx = 0; e->vy = 0;
                if (bs->timer == 730) {            /* VICTOLY */
                    iwxb_spawn(env, (int)e->p[2], 4064, 288);
                    iwxb_kg_destroy_class(env, XB_TYSONDOOR);
                    iwxb_wp_off(xs, bs, 0);
                    e->alive = 0;
                    iwxb_release(xs, bs);
                    return;
                }
            } else {
                e->y = ystart;
                bs->f &= ~TY_HITTED;
                bs->hp = 5;
                bs->phase += 1;
                bs->timer = -10;
                e->vx = 0; e->vy = 0;
            }
        }
        bs->timer += 1;
        e->x += e->vx; e->y += e->vy;
        return;
    }

    /* ---- regular battle ai (the 515-frame schedule) ---- */
    int punch = 0, punchtimer = 0;
    float base_speed = (float)bs->phase;
    int T = bs->timer;
    if (T >= 320 && bs->phase == 2) base_speed -= 5;
    if (T < 100) { }
    else if (T < 120) { punch = 1; punchtimer = T - 100; }
    else if (T < 200) { }
    else if (T < 220) { punch = 1; punchtimer = T - 200; }
    else if (T < 300) { }
    else if (T < 320) { punch = bs->phase < 2 ? 1 : 2; punchtimer = T - 300; }
    else if (T < 350) { }
    else if (T < 380) { punch = 2; punchtimer = T - 350; }
    else if (T < 450) { }
    else if (T < 510) { punch = 3; punchtimer = T - 450; }
    else bs->timer = -5;
    bs->timer += 1;

    bs->f &= ~TY_VULN;
    float pdir = env->x > e->x ? 1.0f : (env->x < e->x ? -1.0f : 0.0f);
    if (punch == 0) {
        bs->sprite = 0;                            /* walk */
        e->vx = base_speed * pdir;
        e->vy = 0;
        if (fist) fist->y = -1000;
    } else if (punch == 1) {                       /* uppercut */
        bs->sprite = 1;
        e->vx = (base_speed + 5) * pdir;
        if (punchtimer < 10) e->vy = 7;
        else {
            e->vy = -7;
            if (fist) { fist->x = e->x; fist->y = e->y + 225; }
        }
    } else if (punch == 2) {                       /* floor punch */
        bs->sprite = 1;
        e->vy = 0;
        e->vx = base_speed * pdir;
        if (punchtimer >= 10 && punchtimer < 30) {
            if (punchtimer == 20) bs->p[2] = -bs->p[2];
            if (fist) { fist->x = e->x; fist->y = e->y + 320; }
        }
        if (punchtimer == 17 || punchtimer == 27) {
            /* destroy one random TysonBrick overlapping the fist */
            int list[64], c = 0;
            if (fist) for (int i = 0; i < xs->n_ents && c < 64; i++) {
                IWXEnt* b = &xs->ents[i];
                if (!b->alive || b->cls != XB_DESTRUCTIBLE) continue;
                double l, r, t2, b2;
                iwx_ent_bbox(xs, b, &l, &r, &t2, &b2);
                if (iwx_hit_rect(xs, fist, (int)l, (int)r, (int)t2,
                                 (int)b2)) list[c++] = i;
            }
            if (c) iwx_kill_destructible(
                env, &xs->ents[list[iwxb_irandom(env, c - 1)]], 0, -2);
        }
    } else {                                       /* fireball vomit */
        bs->sprite = 2;
        bs->f |= TY_VULN;
        e->vx = 0; e->vy = 0;
        if (fist) {
            fist->x = e->x - 18 * bs->p[2];
            fist->y = e->y + 120;
        }
        if (punchtimer == 10) {
            for (int k = 0; k < 3; k++) {
                IWXEnt* f = iwxb_spawn(env, (int)e->p[1],
                                       fist ? fist->x : e->x,
                                       fist ? fist->y : e->y);
                if (f) {
                    /* direction = mmf_direction(choose(22..26)) */
                    float d = (22 + iwxb_irandom(env, 4)) * 90.0f / 8.0f *
                              3.14159265358979323846f / 180.0f;
                    f->vx = 7.5f * cosf(d);
                    f->vy = -7.5f * sinf(d);
                    f->t0 = 200;
                }
            }
        }
    }
    if (pdir != 0 && punch != 2)
        bs->p[2] = pdir;

    /* routed fist damage (Other_10: only while vulnerable) */
    float d = iwxb_take(bs, 0, NULL);
    if (d > 0 && (bs->f & TY_VULN)) {
        bs->hp -= d;
        bs->dmg += d;
        bs->f |= TY_HITTED;
        bs->timer = 0;
        if (bs->hp <= 0) {
            if (fist) fist->y = -1000;
        }
    }

    e->x += e->vx; e->y += e->vy;
}

static void iwxb_tyson_family_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    switch (e->cls) {
    case XB_TYSONFIREBALL:
        /* linear until a solid, then stick; alarm 200 despawn */
        if (--e->t0 <= 0) { e->alive = 0; return; }
        if (e->vx != 0 || e->vy != 0) {
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (!iwx_rect_free(env, (int)(l + e->vx), (int)(r + e->vx),
                               (int)(t + e->vy), (int)(b + e->vy))) {
                e->vx = 0; e->vy = 0;
            }
            e->x += e->vx; e->y += e->vy;
        }
        break;
    default: break;
    }
}

#endif /* IWX_BOSS_TYSON_H */
