/* boss_clowncar.h — the Bowser -> Wart -> Wily triple fight
 * (rBowserBoss), transliterated from objects/ClownCar.gml (the whole
 * fight lives in that one object) + BowserBomb / BowserExplosion /
 * WartBanzai / WartPoof / WilyBall / WilyFireball / BowserFloor /
 * FallingCeiling{,Spike,Switch,Wall} / OrbBowser.
 *
 * Slot (DEF_CLOWNCAR): phase 0 Bowser / 1 Wart / 2 Wily; timer = the
 * source master timer (one shared clock across all three); hp = Wily's
 * 18; alarms 0/1 drive the swoosh path cadence.
 * p[0] path kind (0 none, 1 swoosh, 2 dash, 3 hover), p[1] path pos,
 * p[2] path px/f (signed), p[3]/p[4] relative-path origin offset,
 * p[5]/p[6] lerp starts, p[7] wart velocity dir placeholder, p[8]
 * facing, p[9] big-bullet/meme scratch.
 * Body template p[]: p0 bomb, p1 banzai, p2 poof, p3 wilyball,
 * p4 wilyfireball, p5 orb, p6 floor, p7 swoosh keys, p8 dash keys,
 * p9 hover keys.  (Explosion tmpl rides on the bomb/banzai p0; the
 * pillar tmpl on the wilyfireball p0.)
 *
 * Kill zone: the source collision_rectangle (x-48,y-180)-(x+48,y-84)
 * every frame. Damage: phase 0/1 die to BowserExplosion contact (shoot
 * the pinball bomb into the car / destroy Wart's Banzai); phase 2 Wily
 * takes bullet hits (18) — bullets bounced up by the WilyBall are
 * validated, plain hits land in the driver rect, other body hits
 * ricochet at mmf_direction(irandom(31)) and become invalid.
 * Victory: OrbBowser at (678,486), the floors return, the walls open.
 */
#ifndef IWX_BOSS_CLOWNCAR_H
#define IWX_BOSS_CLOWNCAR_H

#define CC_DEAD (IWXB_F_USER << 0)
#define CC_MEME (IWXB_F_USER << 1)

static void iwxb_cc_path(IWXState* xs, IWXBossState* bs, IWXEnt* e,
                         int kind, float speed, int absolute) {
    bs->p[0] = (float)kind;
    bs->p[1] = 0;
    bs->p[2] = speed;
    if (absolute) { bs->p[3] = 0; bs->p[4] = 0; }
    else {
        int off = kind == 1 ? (int)e->p[7] :
                  kind == 2 ? (int)e->p[8] : (int)e->p[9];
        float px, py;
        iwxb_path_xy(xs, off, 0, &px, &py);
        bs->p[3] = e->x - px;
        bs->p[4] = e->y - py;
    }
}

/* returns 1 while a path drives the position */
static int iwxb_cc_path_step(IWanna* env, IWXBossState* bs, IWXEnt* e,
                             int* end_at_far, int* ended) {
    IWXState* xs = XS(env);
    *ended = 0; *end_at_far = 0;
    int kind = (int)bs->p[0];
    if (!kind) return 0;
    int off = kind == 1 ? (int)e->p[7] :
              kind == 2 ? (int)e->p[8] : (int)e->p[9];
    float total = iwxb_path_len(xs, off);
    if (bs->p[2] != 0 && total > 0) {
        bs->p[1] += bs->p[2] * iwxb_path_sp(xs, off, bs->p[1]) / total;
        if (bs->p[1] >= 1) { bs->p[1] = 1; *ended = 1; *end_at_far = 1; }
        if (bs->p[1] <= 0) { bs->p[1] = 0; if (bs->p[2] < 0) *ended = 1; }
    }
    float px, py;
    iwxb_path_xy(xs, off, bs->p[1], &px, &py);
    float ox = e->x, oy = e->y;
    e->x = px + bs->p[3];
    e->y = py + bs->p[4];
    e->vx = e->x - ox; e->vy = e->y - oy;   /* direction readout only */
    return 1;
}

static void iwxb_cc_die(IWanna* env, IWXBossState* bs, IWXEnt* e,
                        int next_timer) {
    (void)env; (void)e;
    bs->p[0] = 0;
    e->vy = -8.75f;                          /* mmf_speed(70) up */
    e->vx = 0;
    bs->f |= CC_DEAD;
    bs->timer = next_timer;
}

static void iwxb_clowncar_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_CLOWNCAR, &fresh);
    if (!bs) return;
    if (fresh) {
        bs->phase = 0;
        bs->f |= IWXB_F_INTRO;
        bs->hp = 18;
        e->vy = 0.75f;                       /* descend */
        bs->p[8] = -1;
    }
    int T = bs->timer;

    /* the kill rectangle above the car */
    {
        int pl, pr, pt, pb;
        iwx_player_rect(env, &pl, &pr, &pt, &pb);
        if (pr >= e->x - 48 && pl <= e->x + 48 &&
            pb >= e->y - 180 && pt <= e->y - 84)
            xs->pending_kill = 1;
    }

    /* explosion contact (phases 0/1): the source Collision_BowserExplosion
     * event — the car's own sprite mask vs the explosion's, both bboxes */
    if (bs->phase < 2 && !(bs->f & CC_DEAD)) {
        double cl, cr, ct, cb;
        iwx_ent_bbox(xs, e, &cl, &cr, &ct, &cb);
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* x2 = &xs->ents[i];
            if (!x2->alive || x2->cls != XB_BOWSEREXPL) continue;
            double l, r, t2, b2;
            iwx_ent_bbox(xs, x2, &l, &r, &t2, &b2);
            if (r >= cl && l <= cr && b2 >= ct && t2 <= cb) {
                iwxb_cc_die(env, bs, e, bs->phase == 0 ? 2000 : 5000);
                break;
            }
        }
    }

    /* Wily's driver rect takes non-invalid bullets (phase 2) */
    if (bs->phase == 2 && !(bs->f & CC_DEAD) && !(bs->f & IWXB_F_INTRO)) {
        for (int i = 0; i < env->ent_top; i++) {
            IWEntity* b = &env->entities[i];
            if (b->type != E_PBULLET || !(b->flags & EF_ACTIVE)) continue;
            if (b->grav == 1) continue;      /* invalid */
            int bx = gm_round(b->x), by = gm_round(b->y);
            if (bx + IW_BULLET_R >= e->x - 48 &&
                bx + IW_BULLET_L <= e->x + 48 &&
                by + IW_BULLET_B >= e->y - 180 &&
                by + IW_BULLET_T <= e->y - 84) {
                b->flags &= ~EF_ACTIVE;
                bs->hp -= 1;
                bs->dmg += 1;
                if (bs->hp <= 0) {
                    iwxb_cc_die(env, bs, e, 10000);
                    bs->f |= IWXB_F_DEAD;
                }
            }
        }
    }

    if (bs->phase == 0) {
        if (bs->f & IWXB_F_INTRO) {
            if (T == 550) e->vy = 0;
            if (T == 675) {
                bs->f &= ~IWXB_F_INTRO;
                iwxb_cc_path(xs, bs, e, 1, 0, 0);
                bs->alarm[1] = 25;
            }
        } else if (bs->f & CC_DEAD) {
            if (T == 2200) {
                e->x = 704; e->y = -204;
                e->vx = 0; e->vy = 0.75f;
                bs->phase = 1;
                bs->f &= ~CC_DEAD;
                bs->f |= IWXB_F_INTRO;
                bs->timer = 2200; T = 2200;
            }
        }
    } else if (bs->phase == 1) {
        if (bs->f & IWXB_F_INTRO) {
            if (T == 2300)
                for (int i = 0; i < xs->n_ents; i++)
                    if (xs->ents[i].alive &&
                        xs->ents[i].cls == XB_BOWSERFLOOR)
                        xs->ents[i].fspd = 0.50f;   /* open the floor */
            if (T == 2800) e->vy = 0;
            if (T == 2975) {
                bs->f &= ~IWXB_F_INTRO;
                float d = 20 * 90.0f / 8.0f *
                          3.14159265358979323846f / 180.0f;
                e->vx = 5.0f * cosf(d);
                e->vy = -5.0f * sinf(d);
            }
        } else if (!(bs->f & CC_DEAD)) {
            if (T < 3900) {                  /* the DVD bounce */
                if (e->y + 84 + 24 >= 512) {
                    IWXEnt* pf = iwxb_spawn(env, (int)e->p[2], e->x, 512);
                    IWXEnt* pg = iwxb_spawn(env, (int)e->p[2], e->x, 512);
                    if (pf) pf->vx = 11.2f;
                    if (pg) { pg->vx = -11.2f; pg->xs = -pg->xs; }
                    float dd = (e->vx < 0 ? 12 : 4) * 90.0f / 8.0f *
                               3.14159265358979323846f / 180.0f;
                    float sp = sqrtf(e->vx * e->vx + e->vy * e->vy);
                    e->vx = sp * cosf(dd); e->vy = -sp * sinf(dd);
                }
                if (e->x - 96 <= 0) {
                    float dd = 28 * 90.0f / 8.0f *
                               3.14159265358979323846f / 180.0f;
                    float sp = sqrtf(e->vx * e->vx + e->vy * e->vy);
                    e->vx = sp * cosf(dd); e->vy = -sp * sinf(dd);
                }
                if (e->x + 96 >= 800) {
                    float dd = 21 * 90.0f / 8.0f *
                               3.14159265358979323846f / 180.0f;
                    float sp = sqrtf(e->vx * e->vx + e->vy * e->vy);
                    e->vx = sp * cosf(dd); e->vy = -sp * sinf(dd);
                }
                if (e->y - 84 - 96 <= 32) {
                    float dd = (e->vx < 0 ? 21 : 28) * 90.0f / 8.0f *
                               3.14159265358979323846f / 180.0f;
                    float sp = sqrtf(e->vx * e->vx + e->vy * e->vy);
                    e->vx = sp * cosf(dd); e->vy = -sp * sinf(dd);
                }
            } else if (T == 3900) {
                bs->p[5] = e->x; bs->p[6] = e->y;
                e->vx = 0; e->vy = 0;
            } else if (T < 4000) {
                float f = (T - 3900) / 100.0f;
                e->x = bs->p[5] + (672 - bs->p[5]) * f;
                e->y = bs->p[6] + (92 + 84 - bs->p[6]) * f;
                if (T == 3999) { bs->p[6] = e->y; }
            } else if (T == 4000) {
                e->x = 672; e->y = 92 + 84;
                bs->p[6] = e->y;
            } else if (T <= 4030) {
                e->y = bs->p[6] + (332 + 84 - bs->p[6]) *
                       ((T - 4000) / 30.0f);
            } else if (T == 4050) {
                IWXEnt* bz = iwxb_spawn(env, (int)e->p[1], e->x - 35,
                                        e->y - 11 - 84);
                if (bz) { bz->hp = 50; bz->vx = -0.375f; }
            } else if (T > 4050) {
                int live = 0;
                for (int i = 0; i < xs->n_ents; i++)
                    if (xs->ents[i].alive &&
                        (xs->ents[i].cls == XB_WARTBANZAI ||
                         xs->ents[i].cls == XB_BOWSEREXPL)) live = 1;
                if (!live) {
                    if (!(bs->f & CC_MEME)) {
                        bs->timer = 4100; T = 4100;
                        bs->f |= CC_MEME;
                    } else if (T >= 4200) {
                        if (e->y >= 331 + 84) {
                            bs->timer = 4200; T = 4200;
                            e->vy = -4;
                        } else if (e->y <= 246) {
                            if (T < 4225) e->vy = 0;
                            if (T == 4425) e->vy = -8;
                            if (T == 4475) {
                                bs->f |= CC_DEAD;
                                bs->timer = 5175; T = 5175;
                            }
                        } else {
                            bs->timer = 4200; T = 4200;
                        }
                    }
                }
            }
        } else {                              /* dead: rise, then Wily */
            if (T == 5200) {
                e->x = 704; e->y = -204;
                e->vx = 0; e->vy = 0.75f;
                bs->phase = 2;
                bs->f &= ~CC_DEAD;
                bs->f |= IWXB_F_INTRO;
            }
        }
    } else {                                  /* phase 2: Wily */
        if (bs->f & IWXB_F_INTRO) {
            if (T == 5800) e->vy = 0;
            if (T == 6100) {
                bs->f &= ~IWXB_F_INTRO;
                iwxb_cc_path(xs, bs, e, 3, 12.5f, 1);
            }
        } else if (!(bs->f & CC_DEAD)) {
            if (T >= 6110 && T < 7000 && T % 75 == 0) {
                IWXEnt* f = iwxb_spawn(env, (int)e->p[4], e->x,
                                       e->y + 180 - 84);
                if (f) f->vy = 2.5f;
            }
            if (T == 7000) {
                bs->p[0] = 0;                 /* path stop */
                bs->p[5] = e->x; bs->p[6] = e->y;
            }
            if (T > 7000 && T <= 7040) {
                float f = (T - 7000) / 40.0f;
                e->x = bs->p[5] + (704 - bs->p[5]) * f;
                e->y = bs->p[6] + (246 - bs->p[6]) * f;
            }
            if (T == 7100)
                iwxb_spawn(env, (int)e->p[3], e->x, e->y - 22);
            if (T == 7150 + 100) {            /* loop the pattern */
                /* source loops via driver anim back at ~7150+: timer=6090 */
            }
            if (T >= 7150 && T < 10000 && T == 7250) {
                bs->timer = 6090; T = 6090;
                iwxb_cc_path(xs, bs, e, 3, 12.5f, 1);
            }
        } else {                              /* Wily beaten */
            if (T == 10600) {
                iwxb_spawn(env, (int)e->p[5], 678, 486);   /* OrbBowser */
                IWXEnt* f1 = iwxb_spawn(env, (int)e->p[6], 32, 512);
                IWXEnt* f2 = iwxb_spawn(env, (int)e->p[6], 768, 512);
                if (f1) f1->frame = 0;
                if (f2) f2->frame = 0;
                iwxb_kg_destroy_class(env, XB_CONDSOLID);  /* the walls */
                iwxb_kg_destroy_class(env, XB_WILYBALL);
                e->alive = 0;
                iwxb_release(xs, bs);
                return;
            }
        }
    }

    /* swoosh alarm chain (phase 0) */
    if (iwxb_alarm(bs, 0)) bs->alarm[1] = 25;
    if (iwxb_alarm(bs, 1)) {
        bs->p[2] = 12.5f;
        if (bs->p[1] > 0.5f) bs->p[2] = -12.5f;
    }

    int far2 = 0, ended = 0;
    if (iwxb_cc_path_step(env, bs, e, &far2, &ended)) {
        if (ended && bs->phase == 0 && !(bs->f & CC_DEAD)) {
            /* Other_8 */
            if (bs->p[1] < 0.5f || bs->timer < 1100) {
                bs->p[2] = 0;
                bs->alarm[0] = 25;
            } else if ((int)bs->p[0] == 1) {
                iwxb_cc_path(xs, bs, e, 2, 12.5f, 0);
            } else {
                e->x = e->x0; e->y = 208.5f;   /* source: x=xstart y=208.5 */
                iwxb_cc_path(xs, bs, e, 1, 0, 0);
                bs->alarm[1] = 25;
                bs->timer = 690;
                iwxb_spawn(env, (int)e->p[0], 711, 118);   /* the bomb */
            }
        } else if (ended && bs->phase == 2) {
            bs->p[2] = -bs->p[2];             /* endaction 3: reverse */
        }
    } else {
        e->x += e->vx; e->y += e->vy;
    }
    bs->timer++;
}

/* ---- family steps ---- */

static void iwxb_cc_family_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    double l, r, t, b;
    switch (e->cls) {
    case XB_BOWSERBOMB: {
        if (e->state == 0) {                  /* Create */
            e->state = 1;
            e->x -= 1;
            float d = 29 * 90.0f / 8.0f * 3.14159265358979323846f / 180.0f;
            e->vx = 2.0f * cosf(d);
            e->vy = -2.0f * sinf(d);
            e->p[1] = 0.25f;                  /* grav/100 */
        }
        if (e->t0 == 300) {
            iwxb_spawn(env, (int)e->p[0], e->x, e->y);
            e->alive = 0;
            return;
        }
        e->t0++;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (!iwx_rect_free(env, (int)l, (int)r, (int)t, (int)b)) {
            /* source Step_2: move_outside_solid(direction+180, speed)
             * BEFORE re-speeding — the bomb never rests inside a block */
            float sp0 = sqrtf(e->vx * e->vx + e->vy * e->vy);
            if (sp0 > 0.01f) {
                float ux = -e->vx / sp0, uy = -e->vy / sp0;
                for (int k2 = 0; k2 < 64; k2++) {
                    e->x += ux; e->y += uy;
                    iwx_ent_bbox(xs, e, &l, &r, &t, &b);
                    if (iwx_rect_free(env, (int)l, (int)r,
                                      (int)t, (int)b)) break;
                }
            }
            e->p[1] = 0.50f;
            float sp = sqrtf(e->vx * e->vx + e->vy * e->vy);
            if (sp > 0) { e->vx *= 5.0f / sp; e->vy *= 5.0f / sp; }
            if (!iwx_rect_free(env, (int)l, (int)r, (int)(t + e->vy),
                               (int)(b + e->vy)))
                e->vy = -e->vy;
            else {
                e->vx = -e->vx;
                e->x -= e->vx > 0 ? 1.0f : -1.0f;
            }
        }
        e->vy += e->p[1];
        float sp2 = sqrtf(e->vx * e->vx + e->vy * e->vy);
        if (sp2 > 12.5f) { e->vx *= 12.5f / sp2; e->vy *= 12.5f / sp2; }
        e->x += e->vx; e->y += e->vy;
        break;
    }
    case XB_BOWSEREXPL:
        if (++e->t0 >= 40) e->alive = 0;
        break;
    case XB_BOWSERFIRE:                       /* BowserFireClassic */
        if (e->vx == 0) e->vx = 4.375f;       /* Create: mmf_speed(35) */
        e->x += e->vx;
        e->frame += 0.50f;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < 0 || l > env->room_pw) e->alive = 0;
        /* the LuBooHoo torch absorbs it (Collision_BowserFireClassic:
         * with(other) instance_destroy) */
        else if (iwxb_marker_overlap(xs, e, XM_FIRESINK)) e->alive = 0;
        break;
    case XB_WARTBANZAI:
        e->t0++;
        if (e->t0 >= 10) {
            e->t0 -= 10;
            e->p[1] += 1;                     /* speedmod */
            e->vx = e->vx * 1.1f - (e->p[1] / 15.0f) / 8.0f;
        }
        e->x += e->vx;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < 0 || l > env->room_pw) e->alive = 0;
        break;
    case XB_WARTPOOF:
        e->p[1] += 0.7f;
        if (e->p[1] >= 13) { e->alive = 0; break; }
        e->x += e->vx;
        break;
    case XB_WILYBALL:
        if (e->vy != 0 && e->y > 410 - 16 + 72) {
            e->y = 410 - 16 + 72;
            iwxb_cam_shake(env, 4);
            e->vy = 0;
            e->t0 = 46;
        }
        if (e->t0 > 0 && --e->t0 == 0) e->vx = -1.875f;
        e->x += e->vx; e->y += e->vy;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < xs->view_x - 64 || l > xs->view_x + 864) e->alive = 0;
        break;
    case XB_WILYFIREBALL:
        e->x += e->vx; e->y += e->vy;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (!iwx_rect_free(env, (int)l, (int)r, (int)(b + 1),
                           (int)(b + 2))) {
            static const float po[5][3] = {
                {0, 20, 75}, {-64, 40, 80}, {-128, 60, 90},
                {64, 40, 80}, {128, 60, 90}};
            for (int k = 0; k < 5; k++) {
                IWXEnt* pl2 = iwxb_spawn(env, (int)e->p[0],
                                         e->x + po[k][0], (float)(b + 1));
                if (pl2) { pl2->p[0] = po[k][1]; pl2->p[1] = po[k][2]; }
            }
            e->alive = 0;
        }
        break;
    case XB_FCEIL:
        if (e->y + e->vy > 448 || e->y + e->vy < 160) {
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* o = &xs->ents[i];
                if (o->alive && (o->cls == XB_FCEIL ||
                                 o->cls == XB_FCSPIKE) && o->vy != 0)
                    o->vy = -o->vy;
            }
        }
        e->y += e->vy;
        break;
    case XB_FCSPIKE: {
        if (e->armed && e->p[5] < 31) {
            if (e->p[5] == 0) { e->p[5] = 1; e->y += 1; }
            e->p[5] += 2;
            e->y += 2;
        }
        if (e->link >= 0) {                   /* the stretch column */
            IWXEnt* c = &xs->ents[e->link];
            c->x = e->x;
            c->y = e->y - e->p[5];
            c->ys = (e->p[5] + 1) / 32.0f;
            c->alive = e->p[5] > 0 ? 1 : 0;
        }
        e->y += e->vy;                        /* group bounce motion */
        break;
    }
    case XB_FCSWITCH: {
        int pl, pr, pt, pb;
        iwx_player_rect(env, &pl, &pr, &pt, &pb);
        double l2, r2, t2, b2;
        iwx_ent_bbox(xs, e, &l2, &r2, &t2, &b2);
        if (!e->on && pr >= l2 && pl <= r2 && pb >= t2 - 1 && pt <= t2) {
            e->on = 1;
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_FCSPIKE)
                    xs->ents[i].armed = 1;
        }
        break;
    }
    case XB_BOWSERFLOOR:
        if (e->fspd > 0) {
            e->frame += e->fspd;
            if (e->frame >= (float)iwxb_nframes(xs, e)) e->alive = 0;
        }
        break;
    default: break;
    }
}

#endif /* IWX_BOSS_CLOWNCAR_H */
