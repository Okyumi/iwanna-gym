/* boss_kraidgief.h — Kraidgief (rKraidgiefBoss), transliterated from
 * IWBTGR 1.5.3 source: objects/Kraidgief.gml (614 lines) + KGHitbox /
 * KGEyebox / KGHadouken / KGFireDown / KGFireSide / Blanka /
 * KraidgiefDebrisSpawner / KraidgiefDebris / KraidgiefFallingSpike /
 * KraidgiefCeiling / cameraKraid.gml.
 *
 * Spawned (not placed): the arena trigger's once-code
 * instance_create(128,896,Kraidgief) compiles to a SPAWN op.
 *
 * Body template p[]: p0 weak hitbox tmpl (sprKraidgiefHitbox), p1 weak
 * eyebox tmpl, p2 KGHadouken tmpl, p3 KGFireDown tmpl, p4 KGFireSide
 * tmpl, p5 Blanka tmpl, p6 debris-spawner tmpl, p7 key offset of the 12
 * body sprite mask ids (walk, chop, punch, lariet, chargeup, headbutt,
 * angrystand, fire, grab, spd, shit, dying — bs->sprite indexes this).
 *
 * Slot: bs->timer = the source master timer, bs->dmg = cumulative body
 * damage, p0 eye_damage, p1 eye_damage_max, p2 walk_counter, p3 rng,
 * p4 rng2, p5 blankas, p6 fire_down; flags: VULN, INTRO,
 * KG_WALK_RIGHT, KG_TRANSITION.  alarm[0] = the roar window (source
 * alarm[0]: vuln off + stance frame 1).
 *
 * Phases: intro rise -> 0 (walk left/right, chop/punch, vulnerable
 * during roars; 15 damage arms the lariat transition) -> lariat climb
 * destroying the ceiling -> 1 (top floor: eye-repel walk duel, charge /
 * headbutt / triple hadouken specials, random falling-spike drops;
 * reaching x<=-64 grabs the Kid: the source SPD piledriver cutscene is
 * an unavoidable kill, compressed here to the grab-close kill frame;
 * 25 total damage -> phase 2) -> 2 (charges to x=150 crushing the
 * destructible blocks, permanently vulnerable AngryStand, waves of five
 * Blankas then a giant fire aimed by player height; 120 total damage ->
 * dead) -> 4 (death fires, sinks, clears the floor spikes and Blankas,
 * unlocks the camera; the orb + exit warp complete the arena).
 */
#ifndef IWX_BOSS_KRAIDGIEF_H
#define IWX_BOSS_KRAIDGIEF_H

enum { KGS_WALK = 0, KGS_CHOP, KGS_PUNCH, KGS_LARIET, KGS_CHARGEUP,
       KGS_HEADBUTT, KGS_ANGRY, KGS_FIRE, KGS_GRAB, KGS_SPD, KGS_SHIT,
       KGS_DYING };

#define KG_WALK_RIGHT  (IWXB_F_USER << 0)
#define KG_TRANSITION  (IWXB_F_USER << 1)

static void iwxb_kg_sprite(IWanna* env, IWXBossState* bs, IWXEnt* e,
                           int sprite) {
    IWXState* xs = XS(env);
    bs->sprite = (int16_t)sprite;
    e->mask = (uint16_t)xs->keys[(int)e->p[7] + sprite];
}

static void iwxb_kg_debris(IWanna* env, IWXEnt* e) {
    iwxb_spawn(env, (int)e->p[6], 0, 0);          /* spawner (50 frames) */
}

/* with (KraidgiefFallingSpike) if (irandom(n)==0) active=true */
static void iwxb_kg_spike_rolls(IWanna* env, int n) {
    IWXState* xs = XS(env);
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* s = &xs->ents[i];
        if (s->alive && s->cls == XB_KGSPIKE && iwxb_irandom(env, n) == 0)
            s->armed = 1;
    }
}

static void iwxb_kg_destroy_class(IWanna* env, int cls) {
    IWXState* xs = XS(env);
    for (int i = 0; i < xs->n_ents; i++)
        if (xs->ents[i].alive && xs->ents[i].cls == cls)
            xs->ents[i].alive = 0;
}

static void iwxb_kraidgief_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_KRAIDGIEF, &fresh);
    if (!bs) return;
    if (fresh) {                                   /* Create event */
        bs->f |= IWXB_F_INTRO;
        bs->phase = 0;
        bs->p[3] = -1; bs->p[4] = -1;              /* rng, rng2 */
        iwxb_kg_sprite(env, bs, e, KGS_WALK);
        e->frame = 1;
        iwxb_wp_make(env, bs, 0, (int)e->p[0]);    /* KGHitbox */
        iwxb_wp_make(env, bs, 1, (int)e->p[1]);    /* KGEyebox */
    }

    /* alarm[0]: stop roaring (vuln off, stance frame) */
    if (iwxb_alarm(bs, 0)) {
        bs->f &= ~IWXB_F_VULN;
        e->frame = 1;
    }

    int T = bs->timer;

    /* ---------------- step event ---------------- */
    if (bs->f & IWXB_F_INTRO) {
        if (T == 50) e->vy = -1.0f;                /* mmf_speed(8) */
        if (T >= 50) {
            if (T % 10 == 0) {
                iwxb_cam_shake(env, 3);
                iwxb_kg_debris(env, e);
            } else iwxb_cam_shake(env, 15);
        }
        if (e->y <= 384.0f) {
            e->y = 384.0f; e->vy = 0;
            bs->timer = 2000; T = 2000;
            bs->f &= ~IWXB_F_INTRO;
        }
    } else if (bs->phase == 0) {
        if (T == 2020) {
            e->frame = 0;                          /* roar */
            bs->f |= IWXB_F_VULN;
            bs->alarm[0] = 80;
        } else if (T == 2150) {
            e->vx = 5.125f;                        /* mmf_speed(41) */
            if (!(bs->f & KG_WALK_RIGHT) && !(bs->f & KG_TRANSITION))
                e->vx = -e->vx;
            e->frame = 0;
            e->fspd = 0.30f;
            if ((bs->f & KG_WALK_RIGHT) && !(bs->f & KG_TRANSITION))
                bs->p[2] += 1;                     /* walk_counter */
        }
        if (!(bs->f & KG_TRANSITION)) {
            if ((int)e->frame == 2 &&
                e->frame - floorf(e->frame) < e->fspd &&
                (bs->sprite == KGS_CHOP || bs->sprite == KGS_PUNCH)) {
                iwxb_cam_shake(env, 15);
                iwxb_kg_debris(env, e);
            }
            if (T == 20050) {
                iwxb_kg_sprite(env, bs, e,
                               bs->p[3] == 0 ? KGS_CHOP : KGS_PUNCH);
                e->frame = 0; e->fspd = 0;
            } else if (T == 20100) {
                if (bs->p[3] == 0) e->frame = 1;
                e->fspd = 0.10f;
            } else if (T == 20200) {
                iwxb_kg_sprite(env, bs, e, KGS_WALK);
                e->frame = 1; e->fspd = 0;
                bs->f &= ~KG_WALK_RIGHT;
                bs->timer = 2019; T = 2019;
            }
        } else {
            if (e->x > 256.0f) {                   /* lariat rise */
                e->x = 256.0f; e->vx = 0;
                e->vy = -2.5f;                     /* mmf_speed(20) */
                iwxb_kg_sprite(env, bs, e, KGS_LARIET);
                e->frame = 0; e->fspd = 0.50f;
                bs->timer = 500000; T = 500000;
            }
            if (bs->sprite == KGS_LARIET) {
                if (T % 2 == 0) iwxb_cam_shake(env, 15);
                for (int i = 0; i < xs->n_ents; i++) {
                    IWXEnt* c = &xs->ents[i];
                    if (!c->alive || c->cls != XB_KGCEIL) continue;
                    double l, r, t2, b2;
                    iwx_ent_bbox(xs, c, &l, &r, &t2, &b2);
                    if (iwx_hit_rect(xs, e, (int)l, (int)r, (int)t2,
                                     (int)b2))
                        c->alive = 0;
                }
                int max_alarm = 0;                 /* keep debris raining */
                for (int i = 0; i < xs->n_ents; i++) {
                    IWXEnt* s = &xs->ents[i];
                    if (s->alive && s->cls == XB_KGDEBRISSPAWN &&
                        s->t0 > max_alarm) max_alarm = s->t0;
                }
                if (max_alarm < 40) iwxb_kg_debris(env, e);
            }
            if (e->y < 64.0f) {                    /* phase 1 entry */
                iwxb_kg_debris(env, e);
                iwxb_kg_destroy_class(env, XB_KGCEIL);
                e->y = 64.0f; e->vy = 0;
                bs->phase = 1;
                iwxb_kg_sprite(env, bs, e, KGS_WALK);
                e->frame = 0; e->fspd = 0;
                bs->alarm[0] = 60;
                bs->f |= IWXB_F_VULN;
                bs->timer = 600000; T = 600000;
                bs->f &= ~KG_TRANSITION;
                iwxb_cam_lock(env, 0);
                bs->p[2] = 0;                      /* walk_counter */
            }
        }
    } else if (bs->phase == 1) {
        if (T == 600100) {
            if (e->x - env->x < 150.0)
                bs->p[3] = (float)(iwxb_irandom(env, 3) + 1 + (int)bs->p[2]);
            else { bs->p[3] = -100; bs->p[1] = 100; }
        } else if (T == 600120 && bs->p[3] >= -10 && bs->p[3] < 6) {
            bs->p[1] = bs->p[2];                   /* eye_damage_max */
            bs->p[2] += 1;
        } else if (T == 600125 && bs->p[3] < 6) {
            e->fspd = 0.30f;
            e->vx = 5.125f;
            if (bs->p[0] > bs->p[1]) bs->p[0] = 0;     /* repelled right */
            else e->vx = -e->vx;                       /* advances left */
        } else if (T == 600120 && bs->p[3] > 5) {
            bs->p[4] = (float)(iwxb_irandom(env, 2) + 1);
            bs->p[2] = 0;
        } else if (T == 600125 && bs->p[4] == 1) {
            iwxb_kg_sprite(env, bs, e, KGS_CHARGEUP);
        } else if (T == 600150 && bs->p[4] == 1) {
            iwxb_kg_sprite(env, bs, e, KGS_WALK);
            e->frame = 0; e->fspd = 0.60f;
            e->vx = -3.75f;                        /* mmf_speed(30) */
        } else if (T == 600250 && bs->p[4] == 1) {
            e->vx = 3.75f;
        } else if (T == 600125 && bs->p[4] == 2) {
            iwxb_kg_sprite(env, bs, e, KGS_HEADBUTT);
            e->frame = 0; e->fspd = 0;
            e->vx = -1.25f;                        /* mmf_speed(10) */
        } else if (T == 600155 && bs->p[4] == 2) {
            e->x += 2; e->y -= 16;                 /* wonky origins */
        } else if (T == 600165 && bs->p[4] == 2) {
            e->x -= 10; e->y -= 85;
            e->fspd = 0.10f;
            e->frame += e->fspd;
        } else if (T == 600175 && bs->p[4] == 2) {
            e->x += 8; e->y += 101;
        } else if ((T == 600140 || T == 600240 || T == 600340) &&
                   bs->p[4] == 3) {
            e->frame = 0;
            bs->f |= IWXB_F_VULN;
            bs->alarm[0] = 60;
            IWXEnt* h = iwxb_spawn(env, (int)e->p[2], e->x + 311.0f,
                                   e->y + 150.0f);
            if (h) { h->vx = -9.375f; h->fspd = 0.50f; }
        } else if ((T == 600150 || T == 600250) && bs->p[4] == 3) {
            bs->f &= ~IWXB_F_VULN;
            e->frame = 1;
            bs->alarm[0] = -1;
        } else if (T == 600350 || T == 600420) {
            e->vx = 0;
            iwxb_kg_sprite(env, bs, e, KGS_WALK);
            e->frame = 0; e->fspd = 0;
            bs->f |= IWXB_F_VULN;
            bs->alarm[0] = 60;
        } else if (T == 600500) {
            bs->timer = 600000; T = 600000;
            bs->p[4] = -1;
        } else if (T == 600050 && e->x <= -64.0f) {
            /* the grab: source plays the SPD piledriver cutscene and
             * kills; compressed to the grab-close kill (deviation #2) */
            iwxb_kg_sprite(env, bs, e, KGS_GRAB);
            e->frame = 0; e->fspd = 0.01f;         /* mmf_animspeed(1) */
            bs->phase = 3;
            bs->timer = -5000; T = -5000;
        }
    } else if (bs->phase == 2) {
        if (T == 900050) {
            e->vx = -2.5f;                         /* mmf_speed(20) */
            iwxb_kg_sprite(env, bs, e, KGS_WALK);
            e->fspd = 0.60f;
        }
        if (e->vx < 0) {                           /* crush destructibles */
            int crushed = 0;
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* d = &xs->ents[i];
                if (!d->alive || d->cls != XB_DESTRUCTIBLE) continue;
                double l, r, t2, b2;
                iwx_ent_bbox(xs, d, &l, &r, &t2, &b2);
                if (iwx_hit_rect(xs, e, (int)l, (int)r, (int)t2, (int)b2)) {
                    iwx_kill_destructible(env, d, 0, 0);
                    crushed = 1;
                }
            }
            if (crushed) iwxb_kg_debris(env, e);
        }
        if (e->x < 150.0f) {
            iwxb_kg_debris(env, e);
            iwxb_kg_destroy_class(env, XB_DESTRUCTIBLE);
            e->x = 150.0f; e->vx = 0;
            iwxb_kg_sprite(env, bs, e, KGS_ANGRY);
            e->frame = 0; e->fspd = 0;
            bs->f |= IWXB_F_VULN;
            bs->timer = 900500; T = 900500;
        }
        if (T == 900600 && bs->p[5] < 5) {         /* Blanka waves */
            bs->p[5] += 1;
            bs->timer = 900300; T = 900300;
            int pb = gm_round(env->y) + env->hb_b;
            float bx = 0, by = 0;
            if (pb >= 560)      { bx = 226; by = 506; }
            else if (pb >= 462) { bx = 429; by = 410; }
            else if (pb >= 368) { bx = 355; by = 318; }
            else if (pb >= 272) { bx = 252; by = 231; }
            if (bx != 0) {
                IWXEnt* bl = iwxb_spawn(env, (int)e->p[5],
                                        e->x + bx, e->y + by);
                if (bl) bl->fspd = 0.50f;
            }
        }
        if (T == 900601) {
            bs->p[6] = (float)((gm_round(env->y) + env->hb_b) > 350);
        }
        if (T == 900700) {
            IWXEnt* fi = iwxb_spawn(env,
                                    (int)(bs->p[6] != 0 ? e->p[3]
                                                        : e->p[4]),
                                    e->x + 252.0f, e->y + 273.0f);
            if (fi) fi->fspd = 0.20f;         /* mmf_animspeed(20) */
            iwxb_kg_sprite(env, bs, e, KGS_FIRE);
            e->frame = 0; e->fspd = 0.50f;
        }
        if (T > 900700) {
            int fires = 0;
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_KGFIRE)
                    fires = 1;
            if (!fires) {
                bs->p[5] = 0;
                iwxb_kg_sprite(env, bs, e, KGS_ANGRY);
                e->frame = 0; e->fspd = 0;
                bs->timer = 900300; T = 900300;
            }
        }
    } else if (bs->phase == 3) {
        /* grabby hands: the close of the grab kills (cutscene compressed) */
        if (T > -6500 && e->frame + e->fspd >= 1.0f) {
            e->frame = 1; e->fspd = 0;
            iwxb_cam_piledriver(env, 1);
            iwxb_kill_player(env);
            bs->timer = -8000; T = -8000;
        }
    } else if (bs->phase == 4) {
        if (T == 1000050) {
            IWXEnt* f = iwxb_spawn(env, (int)e->p[4], e->x + 535.0f,
                                   e->y + 200.0f);
            if (f) f->fspd = 0.20f;
            iwxb_kg_debris(env, e);
        }
        if (T > 1000050) {
            e->vy = 2.5f;
            iwxb_kg_sprite(env, bs, e, KGS_DYING);
        }
        if (T == 1000200 || T == 1000205) {
            IWXEnt* f = iwxb_spawn(env, (int)e->p[4], e->x + 559.0f,
                                   e->y + (T == 1000200 ? 288.0f : 544.0f));
            if (f) f->fspd = 0.20f;
            iwxb_kg_debris(env, e);
        }
        if (T == 1000210) {
            IWXEnt* f = iwxb_spawn(env, (int)e->p[4], e->x + 551.0f,
                                   e->y + 154.0f);
            if (f) f->fspd = 0.20f;
            iwxb_kg_destroy_class(env, XB_BOLT);     /* the spike floor */
            iwxb_kg_destroy_class(env, XB_BLANKA);
            iwxb_kg_debris(env, e);
            /* Destroy event: release the camera */
            iwxb_cam_piledriver(env, 0);
            iwxb_cam_lock(env, 0);
            e->alive = 0;
            iwxb_release(xs, bs);
            return;
        }
    }

    /* left wall clamp (all phases) */
    if (e->x < -64.0f) {
        e->vx = 0; e->x = -64.0f;
        bs->f |= KG_WALK_RIGHT;
    }

    /* ---- weak-point placement (action points per sprite/frame) ---- */
    {
        float ax = 0, ay = 0;
        int ok = 1;
        if (bs->sprite == KGS_WALK) {
            static const float ap[5][2] = { {311, 179}, {310, 151},
                {310, 123}, {310, 151}, {310, 172} };
            int fi = (int)e->frame; if (fi > 4) fi = 4;
            ax = ap[fi][0]; ay = ap[fi][1];
        } else if (bs->sprite == KGS_ANGRY) { ax = 284; ay = 243; }
        else if (bs->sprite == KGS_FIRE) {
            if ((int)e->frame == 0) { ax = 282; ay = 244; }
            else                    { ax = 284; ay = 237; }
        } else ok = 0;
        if (ok) {
            iwxb_wp_place(xs, bs, 0, e->x + ax, e->y + ay);
            iwxb_wp_place(xs, bs, 1, e->x + ax, e->y + ay);
        } else {
            iwxb_wp_park(xs, bs, 0);
            iwxb_wp_park(xs, bs, 1);
        }
    }

    /* ---- damage pull (the source does instance_place in its Step) ---- */
    if (bs->f & IWXB_F_VULN) {
        float d = iwxb_pull_bullets(env, bs->wp_ent[0]);
        if (d > 0) bs->dmg += d;
        if (bs->phase < 1 && bs->dmg >= 15) bs->f |= KG_TRANSITION;
        if (bs->phase < 2 && bs->dmg >= 25) {
            bs->timer = 900000; T = 900000;
            bs->phase = 2;
            bs->alarm[0] = -1;
            iwxb_wp_off(xs, bs, 1);                /* eyebox destroyed */
        }
        if (bs->phase == 2 && bs->dmg >= 120) {
            bs->phase = 4;
            bs->timer = 1000000; T = 1000000;
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_BLANKA)
                    xs->ents[i].vx = 0;
        }
    }
    if (bs->phase == 1) {
        float d = iwxb_pull_bullets(env, bs->wp_ent[1]);
        bs->p[0] += d;                             /* eye_damage */
    }

    bs->timer++;

    /* ---- built-in motion, then Animation End (Other_7) ---- */
    e->x += e->vx; e->y += e->vy;

    int nf = iwxb_nframes(xs, e);
    if (iwxb_anim(e, nf)) {
        if (bs->sprite == KGS_WALK && e->fspd == 0.30f) {
            e->frame = 1; e->fspd = 0; e->vx = 0;
            iwxb_kg_debris(env, e);
            if (bs->phase == 0) {
                iwxb_cam_shake(env, 15);
                bs->timer = 2060;
                if (bs->p[2] >= 2) {
                    bs->timer = 20000;
                    bs->p[2] = 0;
                    bs->p[3] = (float)iwxb_irandom(env, 1);
                }
            } else if (bs->phase == 1) {
                bs->timer = 600000;
                iwxb_kg_spike_rolls(env, 11);
            }
        } else if (bs->sprite == KGS_CHOP) {
            iwxb_kg_sprite(env, bs, e, KGS_WALK);
            e->frame = 1; e->fspd = 0;
        } else if (bs->sprite == KGS_PUNCH) {
            e->frame = 2; e->fspd = 0;
        } else if (bs->sprite == KGS_HEADBUTT) {
            bs->timer = 600320;
            iwxb_kg_sprite(env, bs, e, KGS_WALK);
            e->frame = 1; e->fspd = 0;
            e->vx = 0;
        }
    }
}

/* ---- support entity steps ---- */

static void iwxb_kg_family_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    double l, r, t, b;
    switch (e->cls) {
    case XB_KGPROJ:                               /* KGHadouken */
        e->x += e->vx;
        e->frame += e->fspd;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < 0 || l > env->room_pw || b < 0 || t > env->room_ph)
            e->alive = 0;
        break;
    case XB_KGFIRE:                               /* one-shot flame */
        if (iwxb_anim(e, iwxb_nframes(xs, e))) e->alive = 0;
        break;
    case XB_BLANKA: {
        e->frame += 0.50f;
        int nf = iwxb_nframes(xs, e);
        if (e->frame >= (float)nf) e->frame = 15.0f;   /* Other_7 */
        if (e->frame == 13.0f) e->vx = -6.25f;    /* mmf_speed(50) */
        if ((int)e->frame >= 15 && e->p[0] > 0)
            e->mask = (uint16_t)e->p[0];          /* sprBlankaHitbox */
        if (e->x < 200.0f && e->vx == -6.25f) {
            iwxb_kg_spike_rolls(env, 23);
            iwxb_spawn(env, (int)e->p[1], 0, 0);  /* debris spawner */
            e->vx = -0.375f;                      /* mmf_speed(3) */
        }
        e->x += e->vx;
        int pl, pr, pt, pb;
        iwx_player_rect(env, &pl, &pr, &pt, &pb);
        if (iwx_hit_rect(xs, e, pl, pr, pt, pb)) xs->pending_kill = 1;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < 0) e->alive = 0;                  /* Outside Room */
        break;
    }
    case XB_KGDEBRISSPAWN:
        if (e->state == 0) { e->state = 1; e->t0 = 50; }
        {
            IWXEnt* d = iwxb_spawn_visual(
                env, (int)e->p[0],
                (float)iwxb_random(env, env->room_pw), 0.0f);
            if (d) {
                d->vx = (float)iwxb_irandom_range(env, -1, 4);
                d->vy = 2.0f;
                d->p[1] = (float)iwxb_random_range(env, 0.99, 1.01);
            }
        }
        if (--e->t0 <= 0) e->alive = 0;
        break;
    case XB_KGDEBRIS:
        e->vy += e->p[1];
        e->x += e->vx; e->y += e->vy;
        if (e->y > env->room_ph + 16 || e->x < -16 ||
            e->x > env->room_pw + 16) e->alive = 0;
        break;
    case XB_KGSPIKE:
        if (e->armed || e->t0 > 0) {
            if (e->t0 < 50) {
                if (e->t0 % 2 < 1) { e->x = e->x0 - 1; e->y = e->y0 - 1; }
                else               { e->x = e->x0 + 1; e->y = e->y0 + 1; }
            } else if (e->t0 == 50) {
                e->x = e->x0; e->y = e->y0;
                e->vy = 2.5f;                     /* mmf_speed(20) */
            }
            e->t0++;
        }
        e->y += e->vy;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (b > 798) {
            e->y = e->y0; e->vy = 0; e->t0 = 0; e->armed = 0;
            e->frame = 0; e->fspd = 0.50f;        /* respawn animation */
        }
        if (e->fspd > 0) {
            e->frame += e->fspd;
            int nf = iwxb_nframes(xs, e);
            if (e->frame >= (float)nf) {          /* Other_7 */
                e->frame = (float)(nf - 1);
                e->fspd = 0;
            }
        }
        break;
    default: break;
    }
}

#endif /* IWX_BOSS_KRAIDGIEF_H */
