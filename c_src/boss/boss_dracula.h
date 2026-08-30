/* boss_dracula.h — Dracula (rDraculaBoss), transliterated from
 * objects/DraculaIntro / Dracula / DraculasFace / Deadcula / DracTele /
 * DracGlass / Drac*Apple / DracMoon / DracFireball / DracDeathSpiral /
 * DracOrbiter / DractoPlasm / WilyFirePillar + scripts/trajectorycalc.
 *
 * DracIntro (ent, no slot): p0 glass tmpl, p1 Dracula tmpl, p2 tele tmpl.
 *   t0 = timer: 0..50 cutscene walk left; input locked to 1645 (the
 *   monologue), glass thrown at 1645 (gravity arc aimed at the player,
 *   deadly until it shatters on the floor at y>=543), tele at 1950,
 *   Dracula spawned at (-200,543) at 2000.
 * Dracula slot (DEF_DRACULA): hp 39 down-counter; the face (weak point,
 *   x-follows him at y 308) takes bullets at ANY time. Cycle: tele to a
 *   random column of {112,208,304,400,496,592,688}, materialize (7-frame
 *   appear anim at 0.20; deadly while materialized after timer 150),
 *   attack on the frame-6 crossing by irandom(99): <30 six horizontal
 *   apples (3.75/5/6.25 px/f pairs), <50 the moon (2.5 toward the
 *   player), <70 a fireball rain (x=112..688 step 96) whose landings
 *   spawn five fire pillars each, <80 the death spiral (spiral apples
 *   every 5|5+2 frames at +22.5deg, 3.75 px/f, 300f), <90 a homing
 *   apple (2.5, 400f), else two sine orbiters (+-cos, 5 px/f).
 *   hp<=23: two ectoplasm chasers (1 px/f; 1.625 at hp<=9; bullets
 *   knock them back 40px). hp<=0: everything clears, Deadcula runs the
 *   death sequence — reappear at x=399, true form at +220 frames, one
 *   more bullet -> the waddle death -> OrbDracula at (384,512).
 * Body template p[]: p0 tele, p1 apple, p2 moon, p3 orbiter, p4
 *   fireball, p5 spiral emitter, p6 plasm, p7 Deadcula tmpl.
 */
#ifndef IWX_BOSS_DRACULA_H
#define IWX_BOSS_DRACULA_H

#define DRAC_ENTER (IWXB_F_USER << 0)

/* trajectorycalc(xto,yto) with gravity g: returns vx/vy */
static void iwxb_trajectory(float sx, float sy, float tx, float ty,
                            float g, float* vx, float* vy) {
    float dX = tx - sx, dY = ty - sy;
    float ang = (atan2f(-dY, dX) + 3.14159265358979323846f / 2) / 2;
    if (ang != 3.14159265358979323846f / 2) {
        float in = 2 * (dY + tanf(ang) * dX) / g;
        if (in > 0) {
            float spd = dX / (cosf(ang) * sqrtf(in));
            *vx = spd * cosf(ang);
            *vy = -spd * sinf(ang);
            return;
        }
    }
    *vx = 0; *vy = -4;                             /* degenerate aim */
}

static void iwxb_dracintro_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    if (e->state == 0) {                           /* Create */
        e->state = 1;
        xs->cutscene = 1;
        xs->force_h = -1;
    }
    int T = e->t0;
    if (T == 50) xs->force_h = 0;
    if (T == 1645) {
        xs->cutscene = 0;
        IWXEnt* g = iwxb_spawn(env, (int)e->p[0], 430, 360);
        if (g) {
            iwxb_trajectory(430, 360, (float)env->x, (float)env->y,
                            0.25f, &g->vx, &g->vy);
            g->p[1] = 0.25f;                       /* gravity */
        }
    }
    if (T == 1950) {
        IWXEnt* t2 = iwxb_spawn(env, (int)e->p[2], e->x, 543);
        if (t2) { t2->link = -1; t2->t0 = 23; t2->t1 = 45; }
    }
    if (T == 2000) {
        iwxb_spawn(env, (int)e->p[1], -200, 543);
        e->alive = 0;
        return;
    }
    e->t0++;
}

static void iwxb_drac_tele(IWanna* env, IWXEnt* boss, int tmpl,
                           float x, int holder) {
    IWXEnt* t2 = iwxb_spawn(env, tmpl, x, 543);
    if (t2) { t2->link = holder; t2->t0 = 23; t2->t1 = 45; }
    (void)boss;
}

static void iwxb_dracula_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_DRACULA, &fresh);
    if (!bs) return;
    int self = (int)(e - xs->ents);
    if (fresh) {
        bs->hp = 39;
        bs->f |= DRAC_ENTER | IWXB_F_PUSH;
        iwxb_wp_make(env, bs, 0, (int)e->p[8]);    /* the face */
        bs->sprite = 1;
    }
    int T = bs->timer;

    if (T == 100) {
        static const float cols[7] = {112, 208, 304, 400, 496, 592, 688};
        iwxb_drac_tele(env, e, (int)e->p[0],
                       cols[iwxb_irandom(env, 6)], self);
    }
    if (T == 206) e->fspd = 0.20f;

    /* attack on the frame-6 crossing */
    float prev = e->frame;
    if (e->fspd > 0 && T < 500) {
        e->frame += e->fspd;
        if ((int)e->frame == 6 && (int)prev < 6) {
            e->fspd = 0;                           /* hold; unwind later */
            int choice = iwxb_irandom(env, 99);
            float dir = bs->p[2] >= 0 ? 1.0f : -1.0f;
            float ax = e->x - 29 * dir, ay = e->y - 115;
            if (choice < 30) {
                static const float off[6][2] = {
                    {-10, 30}, {-42, 30}, {-110, 40},
                    {-142, 40}, {-200, 50}, {-232, 50}};
                for (int k = 0; k < 6; k++) {
                    IWXEnt* a = iwxb_spawn(env, (int)e->p[1], e->x,
                                           e->y + off[k][0]);
                    if (a) { a->p[0] = 0;
                             a->vx = off[k][1] / 8.0f * dir; }
                }
            } else if (choice < 50) {
                IWXEnt* m = iwxb_spawn(env, (int)e->p[2], e->x,
                                       e->y - 100);
                if (m) {
                    m->p[0] = 3;
                    m->vx = env->x < m->x ? -2.5f : 2.5f;
                }
            } else if (choice < 70) {
                for (float xx = 112; xx <= 688; xx += 96) {
                    IWXEnt* f = iwxb_spawn(env, (int)e->p[4], xx, -6);
                    if (f) { f->vy = 2.5f; f->p[1] = 544; }
                }
            } else if (choice < 80) {
                iwxb_spawn(env, (int)e->p[5], ax, ay);
            } else if (choice < 90) {
                IWXEnt* h = iwxb_spawn(env, (int)e->p[1], ax, ay);
                if (h) { h->p[0] = 2; h->t0 = 400; }
            } else {
                for (int v = -1; v <= 1; v += 2) {
                    IWXEnt* o = iwxb_spawn(env, (int)e->p[3], ax, ay);
                    if (o) { o->p[0] = 4; o->p[1] = 1.5708f;
                             o->p[2] = dir; o->p[3] = (float)v; }
                }
            }
        }
    }
    if (T == 300) {
        int spiral = 0;
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_DRACSPIRAL)
                spiral = 1;
        if (!spiral) { bs->timer = 500; T = 500; }
    }
    if (T >= 500 && e->frame > 0) {
        e->frame -= 0.30f;
        if (e->frame < 0) e->frame = 0;
    }
    if (T == 523) {
        bs->f &= ~DRAC_ENTER;
        bs->timer = -1;
        iwxb_drac_tele(env, e, (int)e->p[0], e->x, self);
    }
    bs->timer++;

    /* deadly on touch while materialized (timer>150 && enter) */
    if ((bs->f & DRAC_ENTER) && bs->timer > 150) e->flags |= XEF_KILLER;
    else e->flags &= ~XEF_KILLER;

    /* the face follows x (y fixed at spawn height - 235 = 308) */
    iwxb_wp_place(xs, bs, 0, e->x, 308);
    if (env->x < e->x) bs->p[2] = -1; else bs->p[2] = 1;

    /* face damage: any time */
    float d = iwxb_take(bs, 0, NULL);
    if (d > 0) {
        bs->hp -= d;
        bs->dmg += d;
        if (bs->hp <= 23) {
            int plasm = 0;
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_DRACPLASM)
                    plasm = 1;
            if (!plasm) {
                IWXEnt* p1 = iwxb_spawn(env, (int)e->p[6], 107, 398);
                IWXEnt* p2 = iwxb_spawn(env, (int)e->p[6], 687, 416);
                if (p1) p1->p[0] = 1.0f;
                if (p2) p2->p[0] = 1.0f;
            }
        }
        if (bs->hp <= 9)
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_DRACPLASM)
                    xs->ents[i].p[0] = 1.625f;
        if (bs->hp <= 0) {
            iwxb_wp_off(xs, bs, 0);
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* o = &xs->ents[i];
                if (o->alive && (o->cls == XB_DRACPROJ ||
                                 o->cls == XB_DRACFIREBALL ||
                                 o->cls == XB_DRACSPIRAL ||
                                 o->cls == XB_DRACPLASM ||
                                 o->cls == XB_WILYPILLAR))
                    o->alive = 0;
            }
            IWXEnt* dd = iwxb_spawn(env, (int)e->p[7], e->x, e->y);
            /* source copies image_xscale (facing flip) — visual only;
             * p[2] must stay the true-form mask id */
            if (dd) dd->p[4] = bs->p[2];
            e->alive = 0;
            iwxb_release(xs, bs);
            return;
        }
    }
}

/* Dracula event_user(0): the teleport signal */
static void iwxb_dracula_event(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    IWXBossState* bs = iwxb_slot_of(xs, e);
    if (!bs) return;
    if (bs->f & DRAC_ENTER) {
        /* to the newest tele position */
        for (int i = xs->n_ents - 1; i >= 0; i--)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_DRACTELE &&
                xs->ents[i].link == bs->ent) { e->x = xs->ents[i].x;
                                               break; }
        bs->p[2] = env->x < e->x ? -1 : 1;
    } else {
        e->x = -200;
        bs->f |= DRAC_ENTER;
    }
}

/* Deadcula (plain ent): t0 timer, state 0 away / 1 true form staged */
static void iwxb_deadcula_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int T = e->t0;
    if (T == 0 && e->state == 0) {                 /* Create */
        e->state = 1;
        IWXEnt* t2 = iwxb_spawn(env, (int)e->p[1], e->x, 543);
        if (t2) { t2->link = (int)(e - xs->ents); t2->t0 = 23;
                  t2->t1 = 45; }
        e->hp = 0;
    }
    if (T == 100) {                                /* alarm[0] */
        IWXEnt* t2 = iwxb_spawn(env, (int)e->p[1], 399, 543);
        if (t2) { t2->link = (int)(e - xs->ents); t2->t0 = 23;
                  t2->t1 = 45; }
    }
    if (T == 320) {                                /* alarm[1]: true form */
        e->state = 3;
        /* sprite_index=sprDraculasTrueForm at 4x (the shootable box) */
        if (e->p[2] > 0) e->mask = (uint16_t)e->p[2];
        e->xs = 4.0f; e->ys = 4.0f; e->frame = 0;
    }
    if (e->state == 4) {                           /* shot: waddle death */
        e->t1++;
        if (e->t1 >= 16) {                         /* anim end (8fr/0.5) */
            iwxb_spawn(env, (int)e->p[0], 384, 512);   /* OrbDracula */
            e->alive = 0;
            return;
        }
    }
    e->t0++;
}

static void iwxb_deadcula_event(IWanna* env, IWXEnt* e) {
    (void)env;
    if (e->state == 1) { e->state = 2; e->x = -200; }
    else if (e->state == 2) e->x = 399;            /* reappear center */
}

/* ---- family steps ---- */

static void iwxb_drac_family_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    double l, r, t, b;
    switch (e->cls) {
    case XB_DRACTELE:
        if (e->t0 > 0 && --e->t0 == 0) {
            if (e->link >= 0 && xs->ents[e->link].alive) {
                IWXEnt* h = &xs->ents[e->link];
                if (h->cls == XB_BOSS_DRACULA) iwxb_dracula_event(env, h);
                else if (h->cls == XB_BOSS_DEADCULA)
                    iwxb_deadcula_event(env, h);
                else if (h->cls == XB_DRACPLASM) {
                    h->x = h->x0; h->y = h->y0;    /* materialize */
                }
            }
        } else if (e->t0 == 0 && --e->t1 <= 0) e->alive = 0;
        break;
    case XB_DRACGLASS:
        if (e->state == 0) {
            e->vy += e->p[1];
            e->x += e->vx; e->y += e->vy;
            if (e->y >= 543) { e->state = 1; e->vx = 0; e->vy = 0;
                               e->flags &= ~XEF_KILLER; e->t0 = 10; }
        } else if (--e->t0 <= 0) e->alive = 0;
        break;
    case XB_DRACPROJ: {
        int kind = (int)e->p[0];
        if (kind == 2) {                           /* homing apple */
            double dx = env->x - e->x, dy = env->y - e->y;
            double L = sqrt(dx * dx + dy * dy);
            if (L > 0) { e->vx = (float)(2.5 * dx / L);
                         e->vy = (float)(2.5 * dy / L); }
            if (--e->t0 <= 0) { e->alive = 0; break; }
        } else if (kind == 4) {                    /* orbiter */
            e->x += 5.0f * e->p[2];
            e->p[1] += 0.07f;
            e->y = e->y0 + 100.0f * cosf(e->p[1]) * e->p[3];
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (r < 0 || l > env->room_pw) e->alive = 0;
            break;
        }
        e->x += e->vx; e->y += e->vy;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < 0 || l > env->room_pw || b < 0 || t > env->room_ph)
            e->alive = 0;
        break;
    }
    case XB_DRACFIREBALL: {
        e->x += e->vx; e->y += e->vy;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (t > 0 && !iwx_rect_free(env, (int)(l + e->vx),
                                    (int)(r + e->vx),
                                    (int)(t + e->vy), (int)(b + e->vy))) {
            float py2 = e->p[1] > 0 ? e->p[1] : (float)b;
            static const float po[5][3] = {
                {0, 20, 75}, {-64, 40, 80}, {-128, 60, 90},
                {64, 40, 80}, {128, 60, 90}};
            for (int k = 0; k < 5; k++) {
                IWXEnt* pl = iwxb_spawn(env, (int)e->p[0],
                                        e->x + po[k][0], py2);
                if (pl) { pl->p[0] = po[k][1]; pl->p[1] = po[k][2]; }
            }
            e->alive = 0;
        }
        break;
    }
    case XB_DRACSPIRAL:
        if (e->t0 >= 100 && (e->t0 % 5 == 0 || e->t0 % 5 == 2)) {
            e->angle += 22.5f;
            IWXEnt* a = iwxb_spawn(env, (int)e->p[1], e->x, e->y);
            if (a) {
                float d = e->angle * 3.14159265358979323846f / 180.0f;
                a->p[0] = 1;
                a->vx = 3.75f * cosf(d);
                a->vy = -3.75f * sinf(d);
            }
        }
        if (e->t0 == 300) {
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive &&
                    xs->ents[i].cls == XB_DRACPROJ &&
                    (int)xs->ents[i].p[0] == 1)
                    xs->ents[i].alive = 0;
            e->alive = 0;
        }
        e->t0++;
        break;
    case XB_DRACPLASM:
        if (e->state == 0) {                       /* Create: tele in */
            e->state = 1;
            e->y -= 1000;
            IWXEnt* t2 = iwxb_spawn(env, (int)e->p[1], e->x0, 543);
            if (t2) { t2->link = (int)(e - xs->ents); t2->t0 = 23;
                      t2->t1 = 45; }
            break;
        }
        if (e->y > -500) {                         /* materialized */
            double dx = env->x - e->x, dy = env->y - e->y;
            double L = sqrt(dx * dx + dy * dy);
            if (L > 0) { e->x += (float)(e->p[0] * dx / L);
                         e->y += (float)(e->p[0] * dy / L); }
        }
        break;
    case XB_WILYPILLAR: {
        e->t0++;
        if ((int)e->p[2] == 1) {                   /* persistent */
            if (e->t0 == 20) e->fspd = 0.20f;
            if (e->fspd > 0) {
                e->frame += e->fspd;
                int nf = iwxb_nframes(xs, e);
                if (e->frame >= (float)nf) { e->frame = (float)(nf - 1);
                                             e->fspd = 0; }
            }
            break;
        }
        if (e->t0 == (int)e->p[0]) e->fspd = 0.20f;
        if (e->t0 == (int)e->p[1]) e->fspd = -0.20f;
        e->frame += e->fspd;
        int nf = iwxb_nframes(xs, e);
        if (e->frame >= (float)nf) { e->frame = (float)(nf - 1);
                                     e->fspd = 0; }
        if (e->frame < 0) e->frame = 0;
        if (e->t0 > (int)e->p[1] && e->frame < 1) e->alive = 0;
        break;
    }
    default: break;
    }
}

#endif /* IWX_BOSS_DRACULA_H */
