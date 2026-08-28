/* boss_birdo.h — MechaBirdo (rMechaBirdoBoss), transliterated from
 * IWBTGR 1.5.3 source: objects/MechaBirdo.gml + MechaHitbox{,2,3}.gml +
 * MechaEgg / EggPlatform / EggHitbox / BirdoLaza / FlyGuy.gml.
 *
 * Body template p[]: p0..p2 weak-point templates (antenna x10,
 * 2x2 x32, 2x2 x45/44), p3 MechaEgg tmpl, p4 EggPlatform tmpl,
 * p5 EggHitbox tmpl, p6 BirdoLaza tmpl, p7 FlyGuy tmpl,
 * p8 dest room (rFactoryOutskirts), p9 progression flag (orb_birdo).
 *
 * Slot: phase 1/2/3, bs->hp = current stage HP (30/15/5),
 * p0 = dir, p1 = eggspeed.  Alarms (initial/reload, source values):
 * a0 240/350 phase-1 attack, a1 2/150 phase-2 attack, a2 2/100 phase-3
 * attack, a3 2/200 phase-2 laser pair, a4 2/550 phase-1 FlyGuys (only
 * once x has walked in to 620), a5 2/400 phase-3 FlyGuys.
 * An attack = image_speed 0.15 on the 4-frame body sprite; Animation End
 * spits a MechaEgg at (x-235, y-447).  The weak point follows the body
 * while idle (frame < 1) in phases 1-2 and sits at the open mouth while
 * attacking in phase 3 — invulnerability outside those windows is
 * positional, exactly like the source's parked hitboxes.
 * Death: eggs freeze, the body sinks 2 px/f; below y 1507 the fight ends
 * with room_goto(rFactoryOutskirts) (the flag itself is set by the
 * OrbBirdo pickup there, and a set flag skips the fight on room entry).
 */
#ifndef IWX_BOSS_BIRDO_H
#define IWX_BOSS_BIRDO_H

#define IWXB_BIRDO_HP1 30.0f
#define IWXB_BIRDO_HP2 15.0f
#define IWXB_BIRDO_HP3 5.0f

static void iwxb_birdo_egg(IWanna* env, IWXEnt* body, IWXBossState* bs,
                           float ex, float ey) {
    /* MechaEgg Create: three rideable strips, phase 3 adds the killer */
    IWXEnt* egg = iwxb_spawn(env, (int)body->p[3], ex, ey);
    if (!egg) return;
    egg->vx = -bs->p[1];
    static const float dy[3] = { -63.0f, 13.0f, 62.0f };
    for (int i = 0; i < 3; i++) {
        IWXEnt* pl = iwxb_spawn(env, (int)body->p[4], ex + 68.0f,
                                ey + dy[i]);
        if (pl) pl->vx = egg->vx;
    }
    if (bs->phase == 3) {
        IWXEnt* hb = iwxb_spawn(env, (int)body->p[5], ex, ey);
        if (hb) { hb->vx = egg->vx; hb->fspd = 0.30f; }
    }
}

static void iwxb_birdo_flyguys(IWanna* env, IWXEnt* body, int four) {
    static const float fy[4] = { 362.0f, 422.0f, 486.0f, 537.0f };
    for (int i = 0; i < (four ? 4 : 3); i++) {
        IWXEnt* f = iwxb_spawn(env, (int)body->p[7], 784.0f, fy[i]);
        if (f) { f->vy = -5.625f; f->state = 0; }   /* mmf_speed(45) */
    }
}

static void iwxb_birdo_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_BIRDO, &fresh);
    if (!bs) return;
    if (fresh) {                                   /* Create event */
        bs->phase = 1;
        bs->hp = IWXB_BIRDO_HP1;
        bs->p[0] = 1.0f;                           /* dir */
        bs->p[1] = 1.0f;                           /* eggspeed */
        bs->sprite = 1;                            /* sprBirdo */
        bs->alarm[0] = 240; bs->alarm[1] = 2; bs->alarm[2] = 2;
        bs->alarm[3] = 2;   bs->alarm[4] = 2; bs->alarm[5] = 2;
        iwxb_wp_make(env, bs, 0, (int)e->p[0]);
        iwxb_wp_make(env, bs, 1, (int)e->p[1]);
        iwxb_wp_make(env, bs, 2, (int)e->p[2]);
        iwxb_birdo_egg(env, e, bs, 635.0f, 465.0f);
        e->x = 1068.0f; e->y = 931.0f;
        /* source: pre-advance 128 frames of walk-in ("the moon already
         * hit the floor" fudge, verbatim from MechaBirdo Create) */
        for (int i = 0; i < 128; i++) {
            e->y += bs->p[0] * (float)bs->phase;
            if (e->y < 739.0f) bs->p[0] = 1.0f;
            if (e->y > 963.0f) bs->p[0] = -1.0f;
            e->x = e->x - 0.4f > 620.0f ? e->x - 0.4f : 620.0f;
        }
    }
    bs->timer++;

    /* ---- alarms (GM: alarm events before the step event) ---- */
    if (iwxb_alarm(bs, 0)) {
        bs->alarm[0] = 7 * 50;
        if (bs->phase == 1) e->fspd = 0.15f;
    }
    if (iwxb_alarm(bs, 1)) {
        bs->alarm[1] = 3 * 50;
        if (bs->phase == 2) e->fspd = 0.15f;
    }
    if (iwxb_alarm(bs, 2)) {
        bs->alarm[2] = 2 * 50;
        if (bs->phase == 3 && !(bs->f & IWXB_F_DEAD)) e->fspd = 0.15f;
    }
    if (iwxb_alarm(bs, 3)) {
        bs->alarm[3] = 4 * 50;
        if (bs->phase == 2 && e->fspd == 0) {
            IWXEnt* a = iwxb_spawn(env, (int)e->p[6], e->x - 50.0f,
                                   e->y - 570.0f);
            IWXEnt* b = iwxb_spawn(env, (int)e->p[6], e->x + 10.0f,
                                   e->y - 546.0f);
            if (a) { a->vx = -9.375f; a->fspd = 0.50f; }
            if (b) { b->vx = -9.375f; b->fspd = 0.50f; }
        }
    }
    if (iwxb_alarm(bs, 4)) {
        bs->alarm[4] = 11 * 50;
        if (bs->phase == 1 && e->x == 620.0f)
            iwxb_birdo_flyguys(env, e, 0);
    }
    if (iwxb_alarm(bs, 5)) {
        bs->alarm[5] = 8 * 50;
        if (bs->phase == 3 && !(bs->f & IWXB_F_DEAD))
            iwxb_birdo_flyguys(env, e, 1);
    }

    /* ---- step event ---- */
    e->x = e->x - 0.4f > 620.0f ? e->x - 0.4f : 620.0f;

    if (bs->f & IWXB_F_DEAD) {
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* o = &xs->ents[i];
            if (o->alive && (o->cls == XB_MECHAEGG || o->cls == XB_EGGPLAT ||
                             o->cls == XB_EGGHITBOX))
                o->vx = 0;
        }
        e->frame = 0; e->fspd = 0;
        e->y += 2.0f;
        if (e->y > 1507.0f) {                     /* room_goto(outskirts) */
            iwxb_goto_room(env, (int)e->p[8], 0, 0, 1);
            e->alive = 0;
            iwxb_release(xs, bs);
        }
        return;
    }

    for (int i = 0; i < xs->n_ents; i++) {        /* with (egg family) */
        IWXEnt* o = &xs->ents[i];
        if (o->alive && (o->cls == XB_MECHAEGG || o->cls == XB_EGGPLAT ||
                         o->cls == XB_EGGHITBOX))
            o->vx = -bs->p[1];
    }
    if (bs->phase == 2) { bs->sprite = 2; bs->p[1] = 3.0f; }
    if (bs->phase == 3) bs->sprite = 3;

    if (e->fspd == 0) {                           /* idle bobbing */
        e->y += bs->p[0] * (float)bs->phase;
        if (e->y < 739.0f) bs->p[0] = 1.0f;
        if (e->y > 963.0f) bs->p[0] = -1.0f;
    }

    /* weak-point followers (the source hitbox with() blocks) */
    if (e->frame < 1.0f) {
        iwxb_wp_place(xs, bs, 0, e->x, e->y);
        iwxb_wp_place(xs, bs, 1, e->x + 19.0f, e->y - 575.0f);
        iwxb_wp_park(xs, bs, 2);
    } else {
        iwxb_wp_park(xs, bs, 0);
        iwxb_wp_park(xs, bs, 1);
        iwxb_wp_place(xs, bs, 2, e->x, e->y - 570.0f);
    }

    /* ---- animation end: spit an egg (Other_7) ---- */
    if (iwxb_anim(e, 4)) {
        e->fspd = 0;
        iwxb_birdo_egg(env, e, bs,
                       (float)gm_round(e->x - 235.0),
                       (float)gm_round(e->y - 447.0));
    }

    /* ---- routed damage (MechaHitbox* Step, one frame after impact) --- */
    int stage = bs->phase - 1;                    /* wp index 0/1/2 */
    float d = iwxb_take(bs, stage, NULL);
    if (d > 0) {
        bs->hp -= d;
        bs->dmg += d;
        if (bs->hp <= 0) {
            if (bs->phase == 1) {                 /* MechaHitbox dies */
                bs->phase = 2;
                bs->hp = IWXB_BIRDO_HP2;
                e->fspd = 0.15f;
                bs->alarm[1] = 3 * 50;
                iwxb_wp_off(xs, bs, 0);
            } else if (bs->phase == 2) {          /* MechaHitbox2 dies */
                bs->phase = 3;
                bs->hp = IWXB_BIRDO_HP3;
                e->fspd = 0.15f;
                bs->alarm[2] = 2 * 50;
                iwxb_wp_off(xs, bs, 1);
            } else {                              /* MechaHitbox3 dies */
                bs->f |= IWXB_F_DEAD;
                iwxb_wp_off(xs, bs, 2);
            }
        }
    }
}

/* ---- support entity steps (dispatched from iwx_update_ent) ---- */

static void iwxb_birdo_family_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    double l, r, t, b;
    switch (e->cls) {
    case XB_MECHAEGG:
    case XB_EGGPLAT:
        e->x += e->vx;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < 0) e->alive = 0;
        break;
    case XB_EGGHITBOX:
        e->x += e->vx;
        e->frame += e->fspd;                      /* mmf_animspeed(30) */
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < 0) e->alive = 0;
        break;
    case XB_LAZA:
        e->x += e->vx;
        e->frame += e->fspd;                      /* mmf_animspeed(50) */
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < 0) e->alive = 0;
        break;
    case XB_FLYGUY:
        if (e->state == 0) {
            if (e->y < 154.0f) { e->state = 1; e->t0 = 50; }
        } else if (--e->t0 <= 0) {                /* Alarm_0 re-aim */
            e->t0 = 50;
            double dx = env->x - e->x, dy = env->y - e->y;
            double L = sqrt(dx * dx + dy * dy);
            double spd = sqrt((double)e->vx * e->vx +
                              (double)e->vy * e->vy);
            if (L > 0) {
                e->vx = (float)(spd * dx / L);
                e->vy = (float)(spd * dy / L);
                e->xs = e->vx != 0 ? (e->vx > 0 ? 2.0f : -2.0f) : e->xs;
            }
        }
        e->x += e->vx; e->y += e->vy;
        break;
    default: break;
    }
}

#endif /* IWX_BOSS_BIRDO_H */
