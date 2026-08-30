/* boss_guy.h — The Guy (rGuyBoss): the human duel (objects/GuyFirst.gml)
 * and the giant-head finale (GuyHead / Geye / GuyMouth / GuyTooth /
 * GuyToothShooter / GuyGlassShot / Guybrow / TheGun), ending with
 * orb_guy and room_goto(rEnding) — the completion state.
 *
 * GuyFirst slot (DEF_GUYFIRST): damage counts UP (any valid bullet, no
 * windows) — 30 ends the pillar stage, 45 makes him bullet-proof
 * (ricochets, invalid) in phase 2 where only his own bounced
 * GuyBouncingBullet hurts him (49 total = defeat); body kills on touch.
 * p[]: p0 aimed-bullet tmpl, p1 spread tmpl, p2 grenade tmpl, p3
 * pillar tmpl, p4 bounce tmpl, p5 TheGun tmpl, p6 pGuyJump keys.
 *
 * GuyHead slot (DEF_GUYHEAD): woken by TheGun pickup; drops the player
 * one screen down (+608, the floor bursts), then three eye phases —
 * both Geye dead advances the phase (timers 1501/3500/4500, verbatim);
 * the FINAL eye death sets orb_guy (the source fires its split there),
 * and phase 3 locks input and warps to rEnding at +150 frames.
 * p[]: p0 shot tmpl, p1 tooth tmpl, p2 toothshooter tmpl, p3
 * glass-shot tmpl, p4 pillar tmpl.
 */
#ifndef IWX_BOSS_GUY_H
#define IWX_BOSS_GUY_H

#define GF_PILLARS (IWXB_F_USER << 0)

static void iwxb_thegun_step(IWanna* env, IWXEnt* e);

static void iwxb_guyproj_aimed(IWanna* env, int tmpl, float x, float y,
                               float speed) {
    IWXEnt* b = iwxb_spawn(env, tmpl, x, y);
    if (b) {
        double dx = env->x - x, dy = env->y - y;
        double L = sqrt(dx * dx + dy * dy);
        if (L > 0) { b->vx = (float)(speed * dx / L);
                     b->vy = (float)(speed * dy / L); }
    }
}

static void iwxb_guyfirst_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_GUYFIRST, &fresh);
    if (!bs) return;
    if (fresh) {
        bs->f |= IWXB_F_INTRO;
        bs->p[8] = -1;                          /* facing */
    }
    int T = bs->timer;
    float ax;

    if (bs->f & IWXB_F_INTRO) {
        if (T == 0) {
            xs->cutscene = 1;
            if (env->x < 61) { xs->force_h = 1; return; }
            xs->force_h = 0;
        }
        if (T == 50)                            /* seal the entrance */
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_BOLT &&
                    (int)xs->ents[i].p[7] == 77)      /* the spikeRight wall */
                    xs->ents[i].vx = 2.5f;
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* s = &xs->ents[i];
            if (s->alive && s->cls == XB_BOLT && (int)s->p[7] == 77 &&
                s->x + s->vx > 0) { s->x = 0; s->vx = 0; }
        }
        if (T == 2800) {
            xs->cutscene = 0;
            bs->f &= ~IWXB_F_INTRO;
            bs->timer = 5000;
        } else bs->timer++;
        return;
    }

    T = bs->timer;
    if (bs->phase == 0) {
        if (T == 5050) iwxb_guyproj_aimed(env, (int)e->p[0], e->x - 37,
                                          e->y - 43, 12.5f);
        if (T == 5100) {                        /* pGuyJump (relative) */
            bs->p[0] = 1; bs->p[1] = 0; bs->p[2] = 12.5f;
            float px2, py2;
            iwxb_path_xy(xs, (int)e->p[6], 0, &px2, &py2);
            bs->p[3] = e->x - px2; bs->p[4] = e->y - py2;
        }
        if (T == 5120) {
            IWXEnt* g = iwxb_spawn(env, (int)e->p[2], e->x - 47,
                                   e->y - 41);
            if (g) g->vy = 7.5f;
        }
        if (T == 5200) { bs->p[0] = 0; e->vx = 6.25f; e->vy = 0; }
        if (T == 5210) { e->vx = 0; e->vy = 12.5f; }
        if (bs->dmg < 30 && e->y >= 576 && e->vy > 0) {
            e->vy = 0; e->y = 576;
            if (!(bs->f & GF_PILLARS)) {
                bs->f |= GF_PILLARS;
                static const float px3[4] = {48, 80, 720, 752};
                for (int k = 0; k < 4; k++) {
                    IWXEnt* p2 = iwxb_spawn(env, (int)e->p[3], px3[k],
                                            452);
                    if (p2) p2->p[2] = 1;       /* persistent */
                }
                iwxb_cam_shake(env, -4);
            }
        }
        if (T == 5350) {
            if (gm_round(env->y) + env->hb_b < 566) {
                iwxb_guyproj_aimed(env, (int)e->p[0], e->x + 34,
                                   e->y - 43, 12.5f);
                bs->timer = 5325;
            }
        }
        if (T == 5360) { e->vx = 12.5f; e->vy = 0; }
        if (bs->dmg < 30 && e->y == 576) {
            if (e->vx > 0 && e->x + 20 >= 708) {
                e->vx = -12.5f; iwxb_cam_shake(env, -4);
            }
            if (e->vx < 0 && e->x - 20 <= 91) {
                e->vx = 12.5f; iwxb_cam_shake(env, -4);
            }
        }
        if (T == 5500) {
            e->vx = 0; e->vy = -12.5f;
            bs->f &= ~GF_PILLARS;
            iwxb_kg_destroy_class(env, XB_WILYPILLAR);
        }
        if (T == 5520) {
            double dx = 734 - e->x, dy = 450 - e->y;
            double L = sqrt(dx * dx + dy * dy);
            if (L > 0) { e->vx = (float)(12.5 * dx / L);
                         e->vy = (float)(12.5 * dy / L); }
        }
        if (T > 5520 && T < 6000 && e->x >= 734) {
            e->x = 734; e->y = 448;
            e->vx = 0; e->vy = 0;
            iwxb_cam_shake(env, -4);
            if (bs->dmg < 30) bs->timer = 5001;
            else { bs->timer = 8000; bs->phase = 1; }
        }
    } else if (bs->phase == 1) {
        if (T == 8100) { e->vx = 0; e->vy = -6.25f; }
        if (T > 8000 && e->y - 60 < 63 && e->vy < 0) {
            e->vy = 7.5f;
            bs->timer = 8500;
        }
        if (T == 8501)
            for (int i2 = 19; i2 <= 24; i2++) {
                IWXEnt* b = iwxb_spawn(env, (int)e->p[1], e->x - 47,
                                       e->y - 41);
                if (b) {
                    float d = i2 * 90.0f / 8.0f *
                              3.14159265358979323846f / 180.0f;
                    b->vx = 12.5f * cosf(d); b->vy = -12.5f * sinf(d);
                }
            }
        if (e->x >= 720 && e->y + 9 >= 457 && e->vy == 7.5f) {
            e->x = 726; e->y = 448;
            e->vx = 0; e->vy = 0;
            iwxb_cam_shake(env, -4);
        }
        if (T == 8550)
            for (int i2 = 15; i2 <= 20; i2++) {
                IWXEnt* b = iwxb_spawn(env, (int)e->p[1], e->x - 37,
                                       e->y - 43);
                if (b) {
                    float d = i2 * 90.0f / 8.0f *
                              3.14159265358979323846f / 180.0f;
                    b->vx = 12.5f * cosf(d); b->vy = -12.5f * sinf(d);
                }
            }
        if (T == 8560) { e->vx = -6.25f; e->vy = 0; }
        if (T == 8570) { e->vx = 0; e->vy = 6.25f; }
        if (e->y >= 576 && e->vy > 0) { e->y = 576; e->vy = 0;
                                        iwxb_cam_shake(env, -4); }
        if (T == 8620) e->vx = -12.5f;
        if (T == 8660) {
            double dx = 63 - e->x, dy = 448 - e->y;
            double L = sqrt(dx * dx + dy * dy);
            if (L > 0) { e->vx = (float)(12.5 * dx / L);
                         e->vy = (float)(12.5 * dy / L); }
        }
        if (e->y <= 448 && T > 8650 && T < 8700 && e->vy < 0) {
            iwxb_cam_shake(env, -4);
            e->vx = 0; e->vy = 0;
            e->x = 76; e->y = 449;
        }
        if (T == 8800 || T == 8900 || T == 9000 || T == 9100 ||
            T == 9200)
            iwxb_guyproj_aimed(env, (int)e->p[1], e->x + 34, e->y - 43,
                               11.25f);
        if (T == 9300) { e->vx = 8.75f; e->vy = 0; }
        if (T == 9380) {
            e->x = 726; e->y = 448;
            e->vx = 0; e->vy = 0;
            bs->timer = 8001;
        }
    } else if (bs->phase == 2) {
        if (T <= 10010) {
            float f = (T - 10000) / 10.0f;
            if (f < 0) f = 0;
            e->x = bs->p[5] + (401 - bs->p[5]) * f;
            e->y = bs->p[6] + (577 - bs->p[6]) * f;
        }
        ax = env->x < 396 ? e->x - 37 : e->x + 34;
        if (T == 10100) {
            IWXEnt* b = iwxb_spawn(env, (int)e->p[4], ax, e->y - 43);
            if (b) {
                double dx = (env->x - 3) - ax,
                       dy = (env->y - 42) - (e->y - 43);
                double L = sqrt(dx * dx + dy * dy);
                if (L > 0) { b->vx = (float)(5 * dx / L);
                             b->vy = (float)(5 * dy / L); }
            }
        }
        if (T == 10200 && bs->p[9] < 3) {
            bs->p[9] += 1;
            bs->timer = 10020;
        }
        if (T == 10230) {
            IWXEnt* g = iwxb_spawn(env, (int)e->p[2], ax, e->y - 43);
            if (g) {
                float d = 135 * 3.14159265358979323846f / 180.0f;
                g->vx = 6.25f * cosf(d); g->vy = -6.25f * sinf(d);
            }
        }
        if (T == 10280) {
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_GRENADE) {
                    float d = 21 * 90.0f / 8.0f *
                              3.14159265358979323846f / 180.0f;
                    float sp = sqrtf(xs->ents[i].vx * xs->ents[i].vx +
                                     xs->ents[i].vy * xs->ents[i].vy);
                    if (sp == 0) sp = 6.25f;
                    xs->ents[i].vx = sp * cosf(d);
                    xs->ents[i].vy = -sp * sinf(d);
                }
            bs->p[9] = 0;
            bs->timer = 10011;
        }
    } else {                                    /* phase 3: defeated */
        if (T <= 20020) {
            float f = (T - 20000) / 20.0f;
            if (f < 0) f = 0;
            e->x = bs->p[5] + (416 - bs->p[5]) * f;
            e->y = bs->p[6] + (312 - bs->p[6]) * f;
        }
        if (T == 20020) {
            IWXEnt* g = iwxb_spawn(env, (int)e->p[5], 407, 301);
            if (g) g->vy = 7.5f;                /* TheGun falls */
            e->alive = 0;
            iwxb_release(xs, bs);
            return;
        }
    }
    bs->timer++;

    /* the jump path (phase 0) */
    if ((int)bs->p[0] == 1) {
        float total = iwxb_path_len(xs, (int)e->p[6]);
        bs->p[1] += bs->p[2] * iwxb_path_sp(xs, (int)e->p[6], bs->p[1]) /
                    (total > 0 ? total : 1);
        if (bs->p[1] >= 1) {
            bs->p[1] = 1;
            bs->p[0] = 0;                       /* Other_8: land, stand */
            e->vx = 0; e->vy = 0;
        }
        float px2, py2;
        iwxb_path_xy(xs, (int)e->p[6], bs->p[1], &px2, &py2);
        e->x = px2 + bs->p[3];
        e->y = py2 + bs->p[4];
    } else {
        e->x += e->vx; e->y += e->vy;
    }

    /* his own bouncing bullet hurts him (counter >= 1) */
    if (bs->phase == 2) {
        double l, r, t2, b2;
        iwx_ent_bbox(xs, e, &l, &r, &t2, &b2);
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* bb = &xs->ents[i];
            if (!bb->alive || bb->cls != XB_GUYBOUNCE || bb->t1 < 1)
                continue;
            double bl, br2, bt, bbot;
            iwx_ent_bbox(xs, bb, &bl, &br2, &bt, &bbot);
            if (br2 >= l && bl <= r && bbot >= t2 && bt <= b2) {
                bb->alive = 0;
                bs->dmg += 1;
                if (bs->dmg >= 49) {
                    bs->phase = 3;
                    bs->p[5] = e->x; bs->p[6] = e->y;
                    bs->timer = 20000;
                    iwxb_kg_destroy_class(env, XB_WILYPILLAR);
                    iwxb_kg_destroy_class(env, XB_GRENADE);
                    iwxb_kg_destroy_class(env, XB_GUYBOUNCE);
                }
            }
        }
    }
}

static void iwxb_guyhead_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_GUYHEAD, &fresh);
    if (!bs) return;
    if (fresh) {
        bs->phase = 0;
        iwxb_spawn(env, (int)e->p[5], e->x0 + 20, e->y0 + 146); /* mouth */
    }
    if (!e->on) return;                         /* waits for TheGun */
    int T = bs->timer;

    /* eye lists */
    int eyes[2] = {-1, -1}, ne = 0;
    for (int i = 0; i < xs->n_ents && ne < 2; i++)
        if (xs->ents[i].alive && xs->ents[i].cls == XB_GEYE)
            eyes[ne++] = i;

    if (bs->phase == 0) {
        if (T == 280) {                         /* the floor bursts */
            xs->cutscene = 0; xs->force_h = 0;
            iwxb_kg_destroy_class(env, XB_THEGUN);
            env->y += 608;
            env->prev_y = env->y;
            for (int i = 0; i < ne; i++) {
                xs->ents[eyes[i]].state = 0;
                xs->ents[eyes[i]].armed = 0;
            }
        }
        if (T == 390)
            for (int i = 0; i < ne; i++) xs->ents[eyes[i]].armed = 1;
        if (T == 600 || T == 800 || T == 1000)
            for (int i = 0; i < ne; i++)
                if (xs->ents[eyes[i]].armed)
                    iwxb_guyproj_aimed(env, (int)e->p[0],
                                       xs->ents[eyes[i]].x,
                                       xs->ents[eyes[i]].y, 6.25f);
        if (T == 1300) {
            IWXEnt* s2 = iwxb_spawn(env, (int)e->p[2], 105, 1129);
            if (s2) s2->vx = 5.0f;
            iwxb_kg_destroy_class(env, XB_GUYTOOTH);
            for (int i3 = 306; i3 <= 498; i3 += 32)
                iwxb_spawn(env, (int)e->p[1], (float)i3, 1141);
        }
        if (T == 1500) bs->timer = 590;
    } else if (bs->phase == 1) {
        if (T == 1550)
            for (int i = 0; i < ne; i++) xs->ents[eyes[i]].armed = 0;
        if (T == 1850)
            for (int i = 0; i < ne; i++) {      /* the radial spin */
                IWXEnt* ey = &xs->ents[eyes[i]];
                double d = atan2(-(env->y + (env->x >= 3584 ? 59 : -51)
                                   - ey->y0),
                                 env->x - ey->x0);
                ey->angle = (float)(d * 180.0 / 3.14159265358979323846);
                ey->angle = roundf(ey->angle * 8 / 90.0f) * 90.0f / 8.0f;
                ey->t0 = 25 * 8;                /* spin bursts window */
                ey->state = 2;                  /* spinning fire mode */
            }
        if (T == 2500)
            for (int i = 0; i < ne; i++) {
                xs->ents[eyes[i]].armed = 1;
                xs->ents[eyes[i]].state = 0;
                xs->ents[eyes[i]].t0 = 0;
            }
        if (T == 2520)
            for (int i = 0; i < ne; i++) {
                IWXEnt* ey = &xs->ents[eyes[i]];
                iwxb_guyproj_aimed(env, (int)e->p[0], ey->x, ey->y,
                                   12.5f);
            }
        if (T == 2540) {
            static const float px4[6] = {16, 48, 80, 720, 752, 784};
            for (int k = 0; k < 6; k++) {
                IWXEnt* p2 = iwxb_spawn(env, (int)e->p[4], px4[k], 1064);
                if (p2) p2->p[2] = 1;
            }
        }
        if (T == 2599)
            for (int i = 0; i < ne; i++) {
                IWXEnt* g = iwxb_spawn(env, (int)e->p[3],
                                       xs->ents[eyes[i]].x,
                                       xs->ents[eyes[i]].y);
                if (g) { g->link = eyes[i]; g->t0 = 60; }
            }
        if (T == 2800 || T == 2900 || T == 3000)
            for (int i = 0; i < ne; i++)
                if (xs->ents[eyes[i]].armed)
                    iwxb_guyproj_aimed(env, (int)e->p[0],
                                       xs->ents[eyes[i]].x,
                                       xs->ents[eyes[i]].y, 6.25f);
        if (T == 3200) bs->p[9] = (float)iwxb_irandom(env, 1);
        if (T == 3201 && bs->p[9] == 0) {
            double d = atan2(-(env->y - (e->y0 + 146)),
                             env->x - (e->x0 + 20));
            bs->p[8] = (float)(d * 180.0 / 3.14159265358979323846);
        }
        if (T >= 3201 && bs->p[9] == 0 && T % 3 == 0 && T < 3400) {
            IWXEnt* s3 = iwxb_spawn(env, (int)e->p[0], e->x0 + 20,
                                    e->y0 + 146);
            if (s3) {
                float d = bs->p[8] * 3.14159265358979323846f / 180.0f;
                s3->vx = 2.5f * cosf(d); s3->vy = -2.5f * sinf(d);
            }
        }
        if (T == 3202 && bs->p[9] == 1) {
            IWXEnt* s2 = iwxb_spawn(env, (int)e->p[2], -321, 1135);
            if (s2) s2->vx = 10.0f;
            iwxb_kg_destroy_class(env, XB_GUYTOOTH);
            for (int i3 = 306; i3 <= 498; i3 += 32)
                iwxb_spawn(env, (int)e->p[1], (float)i3, 1141);
        }
        if (T == 3400) bs->timer = 2600;
    } else if (bs->phase == 2) {
        if (T == 3550) {
            for (int i = 0; i < ne; i++) xs->ents[eyes[i]].armed = 0;
            static const int md[3] = {24, 22, 26};
            for (int k = 0; k < 3; k++) {
                IWXEnt* s3 = iwxb_spawn(env, (int)e->p[0], e->x0 + 20,
                                        e->y0 + 146);
                if (s3) {
                    float d = md[k] * 90.0f / 8.0f *
                              3.14159265358979323846f / 180.0f;
                    s3->vx = 12.5f * cosf(d); s3->vy = -12.5f * sinf(d);
                }
            }
            for (int i3 = 112; i3 <= 688; i3 += 32) {
                IWXEnt* p2 = iwxb_spawn(env, (int)e->p[4], (float)i3,
                                        1185);
                if (p2) p2->p[2] = 1;
            }
        }
        if (T == 3700) {
            for (int i = 0; i < ne; i++) xs->ents[eyes[i]].armed = 1;
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_GUYBROW)
                    iwx_ent_event(env, &xs->ents[i]);
        }
        if (T == 3800 || T == 4000)
            for (int i = 0; i < ne; i++)
                if (xs->ents[eyes[i]].armed)
                    iwxb_guyproj_aimed(env, (int)e->p[0],
                                       xs->ents[eyes[i]].x,
                                       xs->ents[eyes[i]].y, 3.75f);
        if (T == 3900) {
            IWXEnt* s2 = iwxb_spawn(env, (int)e->p[2], -321, 1129);
            if (s2) s2->vx = 12.5f;
            iwxb_spawn(env, (int)e->p[1], 370, 1141);
            iwxb_spawn(env, (int)e->p[1], 466, 1141);
        }
        if (T == 4001) bs->timer = 3700;
    } else {                                    /* phase 3: the end */
        if (T == 4550) {
            iwxb_kg_destroy_class(env, XB_GEYE);
            iwxb_kg_destroy_class(env, XB_GUYBROW);
            iwxb_kg_destroy_class(env, XB_GUYMOUTH);
            xs->cutscene = 1; xs->force_h = 0;
        }
        if (T == 4650) {
            xs->cutscene = 0;
            iwxb_goto_room(env, (int)e->p[9], 0, 0, 1);   /* rEnding */
            e->alive = 0;
            iwxb_release(xs, bs);
            return;
        }
    }
    bs->timer++;
}

/* eye death -> both dead advances the head (Geye Collision_bullet) */
static void iwxb_geye_bullet(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    if (!e->armed || e->state == 3) return;     /* not vuln / splat */
    if (e->state != 1) {                        /* enter pain */
        e->state = 1;
        e->frame = 5;
        e->hp = 0;
    }
    if (e->frame >= 1) e->frame -= 1;
    e->hp += 1;
    if (e->hp > 10 && e->frame < 1) {
        e->state = 3;                           /* splat: dead this phase */
        e->armed = 0;
        e->hp = 0;
        int both_dead = 1;
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* o = &xs->ents[i];
            if (o->alive && o->cls == XB_GEYE && o != e && o->armed)
                both_dead = 0;
        }
        if (!both_dead) return;
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* h = &xs->ents[i];
            if (!h->alive || h->cls != XB_BOSS_GUYHEAD) continue;
            IWXBossState* bs = iwxb_slot_of(xs, h);
            if (!bs) continue;
            if (bs->phase == 0) { bs->phase = 1; bs->timer = 1501; }
            else if (bs->phase == 1) { bs->phase = 2; bs->timer = 3500; }
            else if (bs->phase == 2) {
                bs->phase = 3; bs->timer = 4500;
                iwxb_set_flag(env, (int)h->p[8]);   /* orb_guy: source
                                                     * fires it here */
                iwxb_kg_destroy_class(env, XB_GUYGLASSSHOT);
                iwxb_kg_destroy_class(env, XB_GUYPROJ);
                iwxb_kg_destroy_class(env, XB_GUYTOOTH);
                iwxb_kg_destroy_class(env, XB_WILYPILLAR);
            }
            /* eyes revive for the next phase */
            if (bs->phase < 3)
                for (int k = 0; k < xs->n_ents; k++)
                    if (xs->ents[k].alive && xs->ents[k].cls == XB_GEYE) {
                        xs->ents[k].state = 0;
                        xs->ents[k].frame = 0;
                    }
        }
    }
}

static void iwxb_guy_family_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    double l, r, t, b;
    switch (e->cls) {
    case XB_GUYPROJ:
        e->x += e->vx; e->y += e->vy;
        if ((int)e->p[5] == 1) {                /* GuyFirstBullet: solids */
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (!iwx_rect_free(env, (int)l, (int)r, (int)t, (int)b)) {
                e->alive = 0; break;
            }
        }
        if (e->x < -200 || e->x > env->room_pw + 200 || e->y < -200 ||
            e->y > env->room_ph + 200) e->alive = 0;
        break;
    case XB_GRENADE:
        e->x += e->vx; e->y += e->vy;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (!iwx_rect_free(env, (int)l, (int)r, (int)t, (int)b)) {
            for (int i3 = 112; i3 <= 688; i3 += 64) {
                IWXEnt* p2 = iwxb_spawn(env, (int)e->p[0], (float)i3,
                                        578);
                if (p2) { p2->p[0] = 20; p2->p[1] = 75; }
            }
            e->alive = 0;
        }
        break;
    case XB_GUYBOUNCE:
        e->x += e->vx; e->y += e->vy;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (!iwx_rect_free(env, (int)l, (int)r, (int)t, (int)b)) {
            double dx = env->x - e->x, dy = env->y - e->y;
            double L = sqrt(dx * dx + dy * dy);
            float sp = sqrtf(e->vx * e->vx + e->vy * e->vy);
            if (L > 0) { e->vx = (float)(sp * dx / L);
                         e->vy = (float)(sp * dy / L); }
            e->t1 += 1;                         /* counter */
            if (e->t1 >= 10) e->alive = 0;
        }
        break;
    case XB_GEYE:
        if (e->state == 1) {                    /* pain heals slowly */
            e->frame += 0.01f;
            if (e->frame > 5) e->frame = 5;
        }
        if (e->state == 2 && e->t0 > 0) {       /* radial spin bursts */
            e->t0--;
            if (e->t0 % 25 == 0) e->angle += 90.0f / 8.0f;
            if (e->t0 % 3 == 0) {
                IWXEnt* h = NULL;
                for (int i = 0; i < xs->n_ents; i++)
                    if (xs->ents[i].alive &&
                        xs->ents[i].cls == XB_BOSS_GUYHEAD)
                        h = &xs->ents[i];
                if (h) {
                    IWXEnt* s2 = iwxb_spawn(env, (int)h->p[0], e->x,
                                            e->y - 4);
                    if (s2) {
                        float d = e->angle *
                                  3.14159265358979323846f / 180.0f;
                        s2->vx = 12.5f * cosf(d);
                        s2->vy = -12.5f * sinf(d);
                    }
                }
            }
            if (e->t0 == 0) e->state = 0;
        }
        break;
    case XB_GUYMOUTH:                           /* chomping killer bar */
        e->frame += 0.10f;
        if (e->frame >= 10) e->frame = 0;
        break;
    case XB_GUYTOOTH:
        e->x += e->vx; e->y += e->vy;
        if (e->x < -100 || e->x > env->room_pw + 100 ||
            e->y > env->room_ph + 100) e->alive = 0;
        break;
    case XB_TOOTHSHOOTER: {
        e->x += e->vx;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* th = &xs->ents[i];
            if (!th->alive || th->cls != XB_GUYTOOTH ||
                (th->vx != 0 || th->vy != 0)) continue;
            double tl, tr, tt, tb;
            iwx_ent_bbox(xs, th, &tl, &tr, &tt, &tb);
            if (tr >= l && tl <= r) {
                double dx = env->x - th->x, dy = env->y - th->y;
                double L = sqrt(dx * dx + dy * dy);
                if (L > 0) { th->vx = (float)(10.0 * dx / L);
                             th->vy = (float)(10.0 * dy / L); }
            }
        }
        if (e->x > env->room_pw + 400) e->alive = 0;
        break;
    }
    case XB_GUYGLASSSHOT:
        /* alarm0 (t0): go visible + burst 3.75 at the player for 40f
         * (t1), then park and re-arm; a bullet sends it back to its eye
         * (router) with a 160-frame cooldown */
        if (e->t0 > 0 && --e->t0 == 0) {
            e->on = 1;
            double dx = env->x - e->x, dy = env->y - e->y;
            double L = sqrt(dx * dx + dy * dy);
            if (L > 0) { e->vx = (float)(3.75 * dx / L);
                         e->vy = (float)(3.75 * dy / L); }
            e->t1 = 40;
        }
        if (e->t1 > 0 && --e->t1 == 0) { e->vx = 0; e->vy = 0;
                                         e->t0 = 60; }
        if (!e->on && e->link >= 0 && xs->ents[e->link].alive) {
            e->x = xs->ents[e->link].x;
            e->y = xs->ents[e->link].y;
        }
        e->x += e->vx; e->y += e->vy;
        break;
    case XB_THEGUN:
        iwxb_thegun_step(env, e);
        break;
    case XB_GUYBROW:
        /* jiggle skipped (visual); blocking set by event */
        break;
    default: break;
    }
}

static void iwxb_guybrow_event(IWanna* env, IWXEnt* e) {
    (void)env;
    e->on = 1;                                  /* blocking */
    e->y = e->y0 + 10;
    e->x = e->x0 + 51 * (e->xs > 0 ? 1 : -1);
}

/* TheGun: falls, then the pickup wakes the head */
static void iwxb_thegun_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    if (e->state == 1) {                        /* attached */
        e->x = (float)env->x + 10;
        e->y = (float)env->y - 20;
        return;
    }
    double l, r, t, b;
    iwx_ent_bbox(xs, e, &l, &r, &t, &b);
    if (e->vy != 0 &&
        !iwx_rect_free(env, (int)l, (int)r, (int)(b + 1), (int)(b + 2)))
        e->vy = 0;
    e->y += e->vy;
    int pl, pr, pt, pb;
    iwx_player_rect(env, &pl, &pr, &pt, &pb);
    if (pr >= l && pl <= r && pb >= t && pt <= b) {
        e->state = 1;
        xs->cutscene = 1; xs->force_h = 0;
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_BOSS_GUYHEAD)
                xs->ents[i].on = 1;
    }
}

#endif /* IWX_BOSS_GUY_H */
