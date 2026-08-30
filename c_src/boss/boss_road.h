/* boss_road.h — the rGuyRoad boss sequence + the fortress-2 Sinistar:
 * RoadMoon (cutscene) -> Devil Dragon (objects/Dragon.gml + DragonFire /
 * DragonFace / DragonDevilism / DragonBlock / DragonMarker{,2}), the
 * VicViper Gradius segment (VicViper / VicBullet / GradiusBoss / Bugz /
 * Drones / DroneBullet / Fruit / Marker), and Sinistar (wakes when the
 * Arkanoid bricks are gone).
 *
 * Dragon slot (DEF_DRAGON): bs->dmg = the source hp (counts UP via face
 * hits during the 200-frame `shooting` windows; deflected bullets don't
 * count); flags 20/21/78 = the source phase latches; hp milestones
 * 10/25/50 trigger the devilism teleport sets; DragonMarker turns him up
 * at mmf_direction(17), DragonMarker2 ends him: 1.25 px/f at 315deg,
 * then the player warps to rGuyFortress1 with orb_dragon set + saved
 * (global.orb_on_room_change, verbatim).
 * Body template p[]: p0 face weak tmpl, p1 fire tmpl, p2 devilism tmpl,
 * p3 destructible tmpl (DragonBlock rebuild), p9 flag (orb_dragon).
 *
 * VicViper: touching the parked viper mounts it (player hidden; input
 * remapped — see the deviation table: jump held = up 4, else down 4,
 * h unchanged; the source uses the up/down keys our 12-action space
 * does not carry). Enemies/walls kill; killing the GradiusBoss clears
 * the segment and flies the player back on an invisible platform.
 * Viper p[]: p0 bullet tmpl, p1 platform tmpl.
 */
#ifndef IWX_BOSS_ROAD_H
#define IWX_BOSS_ROAD_H

#define DR_F20   (IWXB_F_USER << 0)
#define DR_F21   (IWXB_F_USER << 1)
#define DR_F78   (IWXB_F_USER << 2)
#define DR_DEADX (IWXB_F_USER << 3)

static void iwxb_vicbullet_hits(IWanna* env, IWXEnt* b);

static void iwxb_dragon_devilism(IWanna* env, IWXEnt* e, float gx,
                                 const float off[6][2],
                                 const int when[6], int T) {
    for (int k = 0; k < 6; k++)
        if (T == when[k]) {
            IWXEnt* d = iwxb_spawn(env, (int)e->p[2], e->x + off[k][0],
                                   e->y + off[k][1]);
            if (d) { d->p[0] = gx; d->t0 = 100; }
        }
}

static void iwxb_dragon_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    int fresh = 0;
    IWXBossState* bs = iwxb_slot(env, e, IWXB_DEF_DRAGON, &fresh);
    if (!bs) return;
    if (fresh) {
        bs->f |= IWXB_F_PUSH;
        iwxb_wp_make(env, bs, 0, (int)e->p[0]);
        bs->p[2] = 1;                          /* facing (xscale sign) */
    }
    int T = bs->timer;

    if (bs->phase == 0) {                      /* intro (RoadMoon wakes) */
        if (e->on) bs->timer++;
        if (T == 100) e->vy = 12.5f;
        if (e->on && e->y > 128 && e->vy > 0 && bs->p[5] == 0) { }
        if (bs->p[5] == 0 && e->vy > 0 && e->y >= 128) {
            e->y = 128; e->vy = 0;
            bs->p[5] = 1;                      /* inplace */
            xs->cutscene = 0; xs->force_h = 0; /* the moon froze input */
        }
        if (T == 250) e->vx = 3.125f;          /* mmf_speed(25) */
        if (e->x >= 25984) {
            e->vx = 0; e->vy = 0;
            bs->phase = 1;
            bs->timer = 0; T = 0;
        }
        e->x += e->vx; e->y += e->vy;
        iwxb_wp_park(xs, bs, 0);
        return;
    }

    /* ---- in phase ---- */
    bs->timer++;
    T = bs->timer;

    /* action point / face follower (event_user(0) inline) */
    float ax = e->x + 28 * 3 * (bs->p[2] > 0 ? 1 : -1) / 3.0f * 3.0f;
    ax = e->x + 28 * bs->p[2] * 3.0f;
    float ay = e->y + 44 * 3.0f;
    iwxb_wp_place(xs, bs, 0, ax - 70, ay - 73);

    if (T == 10) {
        e->vx = -1.875f;                       /* mmf_speed(-15) */
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_DESTRUCTIBLE &&
                xs->ents[i].x == 25984)
                iwx_kill_destructible(env, &xs->ents[i], 0, 0);
    }
    if (T == 50) { e->vx = 0; e->vy = 0; }
    if (T == 100) e->vy = -1.875f;
    if (!iwxb_marker_overlap(xs, e, XM_DRAGONTURN)) { }
    {
        /* vertical bounce band right of DragonMarker.x (183/184) */
        double l, r, t2, b2;
        iwx_ent_bbox(xs, e, &l, &r, &t2, &b2);
        float mx = 1e9f;
        for (int k = 0; k < xs->n_idx_marker; k++) {
            IWXEnt* m = &xs->ents[xs->idx_marker[k]];
            if (m->alive && (int)m->p[0] == XM_DRAGONTURN && m->x < mx)
                mx = m->x;
        }
        if (e->x > mx) {
            /* GM bbox_top/bottom: the sprite's editor bbox, not the
             * pixel-trimmed collider (sprDragon: bbox 0..156, origin 0) */
            const IWXMaskRec* dm = iwx_mask(xs, e->mask);
            double gt = e->y, gb = e->y;
            if (dm) {
                gt = e->y + (dm->bt - dm->oy) * e->ys;
                gb = e->y + (dm->bb - dm->oy + 1) * e->ys;
            } else { gt = t2; gb = b2; }
            if (gt < 0) { float sp = fabsf(e->vy);
                          e->vy = sp; e->vx = 0; }
            if (gb > 608 + 140) { float sp = fabsf(e->vy);
                                  e->vy = -sp; e->vx = 0; }
        }
    }
    if (T == 350 || T == 450) {
        IWXEnt* f = iwxb_spawn(env, (int)e->p[1], ax, ay);
        if (f) {
            double dx = env->x - ax, dy = (env->y - 16) - ay;
            double L = sqrt(dx * dx + dy * dy);
            if (L > 0) { f->vx = (float)(7.5 * dx / L);
                         f->vy = (float)(7.5 * dy / L); }
            f->xs = 3.0f * bs->p[2];
        }
        if (T == 350) bs->p[0] = 200;          /* shooting window */
        else bs->timer = 201;
    }
    if (bs->p[0] > 0) bs->p[0] -= 1;

    /* face hits routed during shooting windows (source hp counts UP) */
    {
        float d2 = iwxb_take(bs, 0, NULL);
        if (d2 > 0) bs->dmg += d2;
    }

    /* devilism phase latches at hp milestones */
    static const int w1[6] = {-800, -900, -670, -750, -700, -850};
    static const float o1[6][2] = {{-140, 82}, {20, 82}, {-140, 210},
                                   {20, 210}, {-140, 338}, {20, 338}};
    static const int w2[6] = {-1900, -1780, -1850, -1825, -1900, -1780};
    static const float o2[6][2] = {{-90, 82}, {70, 82}, {-90, 210},
                                   {70, 210}, {-90, 338}, {70, 338}};
    static const int w3[6] = {-2700, -2900, -2750, -2850, -2750, -2800};

    if (bs->dmg >= 10 && e->y < 10 && T >= 0 && bs->p[2] > 0 &&
        !(bs->f & (DR_F20 | DR_F21 | DR_F78))) {
        e->vx = 0; e->vy = 0; bs->p[0] = 0;
        bs->timer = -1000; T = -1000;
        bs->f |= DR_F20;
    }
    iwxb_dragon_devilism(env, e, 750, o1, w1, T);
    if (T == -350) {
        e->x += 650;
        bs->p[2] = -1;
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_DEVILISM)
                xs->ents[i].state = 2;         /* retract */
        e->vy = 3.125f;
        IWXEnt* f = iwxb_spawn(env, (int)e->p[1], ax, ay);
        if (f) { f->vx = -7.5f; f->vy = 0; }
        bs->timer = 101;
    }
    if (bs->dmg >= 25 && e->y < 20 && T >= 0 && bs->p[2] < 0 &&
        !(bs->f & (DR_F21 | DR_F78))) {
        e->vx = 0; e->vy = 0; bs->p[0] = 0;
        bs->timer = -2000; T = -2000;
        bs->f |= DR_F21;
    }
    iwxb_dragon_devilism(env, e, -750, o2, w2, T);
    if (T == -1350) {
        e->x -= 650;
        bs->p[2] = 1;
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_DEVILISM)
                xs->ents[i].state = 2;
        e->vy = 3.125f;
        IWXEnt* f = iwxb_spawn(env, (int)e->p[1], ax, ay);
        if (f) { f->vx = 7.5f; f->vy = 0; }
        bs->timer = 101;
    }
    if (bs->dmg >= 50 && e->y < 10 && T >= 0 && bs->p[2] > 0 &&
        (bs->f & DR_F21) && !(bs->f & DR_F78)) {
        e->vx = 0; e->vy = 0; bs->p[0] = 0;
        bs->timer = -3000; T = -3000;
        bs->f |= DR_F20;
    }
    iwxb_dragon_devilism(env, e, 10000000, o1, w3, T);
    if (T == -2001) {
        e->x = 26806; e->y = 148;
        bs->p[2] = -1;
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_DEVILISM)
                xs->ents[i].state = 2;
        e->vx = -3.375f;                       /* mmf_speed(-27) */
        e->vy = 0;
        bs->f |= DR_F78;
        bs->timer = 3000;
    }
    if (T == 3001)
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_DRAGONBLOCK)
                iwx_ent_event(env, &xs->ents[i]);

    /* the source's manual view pans (cameraCart defers to him) */
    if (bs->timer > -600 && bs->timer < -400) xs->view_x += 1;
    if (bs->timer > -1600 && bs->timer < -1400) xs->view_x -= 1;
    if (bs->timer > -2600 && bs->timer < -2300) xs->view_x += 1;
    if ((bs->f & DR_F78) && bs->timer > 3050)
        xs->view_x = e->x - 600;

    /* markers + destructibles in his way */
    if (e->vx < 0) {
        if (!(bs->f & DR_DEADX) &&
            iwxb_marker_overlap(xs, e, XM_DRAGONDEAD)) {
            bs->f |= DR_DEADX;
            bs->timer = 50000;
            float d = 315 * 3.14159265358979323846f / 180.0f;
            e->vx = 1.25f * cosf(d);
            e->vy = -1.25f * sinf(d);
            bs->f &= ~DR_F78;
        } else if (iwxb_marker_overlap(xs, e, XM_DRAGONTURN) &&
                   !(bs->f & DR_DEADX)) {
            float d = 17 * 90.0f / 8.0f * 3.14159265358979323846f / 180.0f;
            e->vx = 3.75f * cosf(d);
            e->vy = -3.75f * sinf(d);
        }
    }
    {
        double l, r, t2, b2;
        iwx_ent_bbox(xs, e, &l, &r, &t2, &b2);
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* d = &xs->ents[i];
            if (!d->alive || d->cls != XB_DESTRUCTIBLE) continue;
            double dl, dr, dt, db;
            iwx_ent_bbox(xs, d, &dl, &dr, &dt, &db);
            if (dr >= l && dl <= r && db >= t2 && dt <= b2)
                iwx_kill_destructible(env, d, e->vx, 0);
        }
    }

    if (T == 50500) {                          /* victory: warp onward */
        iwxb_set_flag(env, (int)e->p[9]);      /* orb_dragon */
        env->pending_checkpoint = 1;           /* save_on_room_change */
        iwxb_goto_room(env, (int)e->p[8], 0, 0, 1);
        e->alive = 0;
        iwxb_release(xs, bs);
        return;
    }
    e->x += e->vx; e->y += e->vy;
}

/* ---- road/fortress family ---- */

static void iwxb_road_family_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    double l, r, t, b;
    switch (e->cls) {
    case XB_ROADMOON:
        if (e->on && e->state == 0) {
            e->state = 1;
            xs->cutscene = 1;                  /* the moon freezes input */
            xs->force_h = 0;
        }
        if (e->state == 1) {
            e->p[1] += 0.2f;
            e->xs = 1 + e->p[1];
            e->ys = e->xs;
            if (e->xs >= 9) {
                e->xs = 9; e->ys = 9;
                e->state = 2;
                for (int i = 0; i < xs->n_ents; i++)
                    if (xs->ents[i].alive &&
                        xs->ents[i].cls == XB_BOSS_DRAGON)
                        xs->ents[i].on = 1;    /* Dragon.active=1 */
            }
        }
        break;
    case XB_SINISTAR: {
        if (e->state == 2) { e->vy -= 0.2f; e->y += e->vy; break; }
        if (e->state == 1) {
            double dx = env->x - e->x, dy = env->y - e->y;
            double L = sqrt(dx * dx + dy * dy);
            if (L > 0) { e->x += (float)(e->p[0] * dx / L);
                         e->y += (float)(e->p[0] * dy / L); }
            e->p[0] += 0.02f;
            e->flags |= XEF_KILLER;
            break;
        }
        if (iwx_ent_in_view(xs, e)) {
            int bricks = 0;
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].alive && xs->ents[i].cls == XB_ARKABRICK)
                    bricks = 1;
            if (!bricks) e->state = 1;
        }
        break;
    }
    case XB_DRAGONFIRE:
        e->x += e->vx; e->y += e->vy;
        if (!iwx_ent_in_view(xs, e)) e->alive = 0;
        break;
    case XB_DEVILISM:
        if (e->state == 0) {
            e->frame += 0.20f;
            if (e->t0 > 0 && --e->t0 == 0) {
                e->vx = 6.25f * (e->p[0] > 0 ? 1 : -1);
                e->state = 1;
            }
        } else if (e->state == 1) {
            e->x += e->vx;
            if ((e->p[0] > 0 && e->x > e->x0 + e->p[0]) ||
                (e->p[0] < 0 && e->x < e->x0 + e->p[0])) {
                e->vx = 0;
                e->x = e->x0 + e->p[0];
            }
        } else {                               /* retract (event_user) */
            e->frame -= 0.10f;
            if (e->frame < 1) e->alive = 0;
        }
        break;
    case XB_VICBULLET:
        e->x += e->vx;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (!iwx_rect_free(env, (int)l, (int)r, (int)t, (int)b) ||
            l > xs->view_x + 900) { e->alive = 0; break; }
        iwxb_vicbullet_hits(env, e);
        break;
    case XB_GRADFRUIT: case XB_GRADDRONEBULLET:
        e->x += e->vx; e->y += e->vy;
        if (e->cls == XB_GRADDRONEBULLET) {
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (!iwx_rect_free(env, (int)l, (int)r, (int)t, (int)b)) {
                e->alive = 0; break;
            }
        }
        if (!iwx_ent_in_view(xs, e)) e->alive = 0;
        break;
    case XB_GRADBUGZ:
        if (!e->armed && iwxb_marker_overlap(xs, e, XM_GRADIUS)) {
            e->armed = 1;
            double dx = env->x - e->x, dy = env->y - e->y;
            double L = sqrt(dx * dx + dy * dy);
            float sp = fabsf(e->vx) > 0 ? fabsf(e->vx) : 6.25f;
            if (L > 0) { e->vx = (float)(sp * dx / L);
                         e->vy = (float)(sp * dy / L); }
        }
        e->x += e->vx; e->y += e->vy;
        break;
    case XB_GRADDRONE:
        if (!e->armed && iwxb_marker_overlap(xs, e, XM_GRADIUS)) {
            e->armed = 1;
            e->vx += 3.75f;                    /* retreat */
            static const float dirs[3] = {135, 180, 225};
            for (int k = 0; k < 3; k++) {
                IWXEnt* bl = iwxb_spawn(env, (int)e->p[0], e->x - 16,
                                        e->y - 3);
                if (bl) {
                    float d = dirs[k] * 3.14159265358979323846f / 180.0f;
                    bl->vx = 3.75f * cosf(d);
                    bl->vy = -3.75f * sinf(d);
                }
            }
        }
        e->x += e->vx; e->y += e->vy;
        break;
    case XB_GRADBOSS: {
        if (e->state == 2) break;              /* dying handled below */
        if (!e->armed && iwxb_marker_overlap(xs, e, XM_GRADIUS))
            e->armed = 1;
        if (e->armed && e->state == 0) {
            e->angle += 90.0f / 8.0f;          /* mmf_direction(1) */
            float d = e->angle * 3.14159265358979323846f / 180.0f;
            float sx = e->x + 16 + 16 * cosf(roundf(e->angle / 45.0f) *
                                             0.7853982f);
            float sy = e->y + 10 - 16 * sinf(roundf(e->angle / 45.0f) *
                                             0.7853982f);
            IWXEnt* fr = iwxb_spawn(env, (int)e->p[0], sx, sy);
            if (fr) { fr->vx = 3.75f * cosf(d); fr->vy = -3.75f * sinf(d); }
        }
        e->x += e->vx; e->y += e->vy;
        break;
    }
    case XB_VICVIPER:
        /* parked: mount on touch (handled in the contact pass); active
         * flight lives in the player step; win: fly home with the rider */
        if (e->state == 3) {                   /* win return flight */
            float ox = e->x, oy = e->y;
            e->x += e->x0 > e->x ? fminf(2, e->x0 - e->x)
                                 : fmaxf(-2, e->x0 - e->x);
            e->y += e->y0 > e->y ? fminf(2, e->y0 - e->y)
                                 : fmaxf(-2, e->y0 - e->y);
            if (e->link >= 0 && xs->ents[e->link].alive) {
                xs->ents[e->link].vx = e->x - ox;
                xs->ents[e->link].p[9] = e->y - oy;   /* platform yspeed */
                xs->ents[e->link].x = e->x - 32;
                xs->ents[e->link].y = e->y - 4;
            }
        }
        break;
    default: break;
    }
}

/* GradiusBoss beaten: clear the segment, fly the player back on an
 * invisible platform (VicViper event_user(1)) */
static void iwxb_viper_victory(IWanna* env, IWXEnt* v) {
    IWXState* xs = XS(env);
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* o = &xs->ents[i];
        if (!o->alive) continue;
        if (o->cls == XB_GRADFRUIT || o->cls == XB_GRADBUGZ ||
            o->cls == XB_GRADDRONE || o->cls == XB_GRADDRONEBULLET)
            o->alive = 0;
        if (o->cls == XB_DESTRUCTIBLE && iwx_ent_in_view(xs, o))
            o->alive = 0;
    }
    IWXEnt* p = iwxb_spawn(env, (int)v->p[1], v->x - 32, v->y - 4);
    if (p) v->link = (int)(p - xs->ents);
    v->state = 3;                               /* win return flight */
    xs->viper = -1;
    env->x = v->x;
    env->y = v->y - 24;
    env->hspeed = 0; env->vspeed = 0;
    env->prev_x = env->x; env->prev_y = env->y;
}

/* the mounted flight (replaces the player step; see deviation B8 for
 * the vertical mapping: jump held = up 4, otherwise down 4) */
static void iwxb_viper_fly(IWanna* env, int h, int jump_held,
                           int shoot_held) {
    IWXState* xs = XS(env);
    if (xs->viper < 0) return;
    IWXEnt* v = &xs->ents[xs->viper];
    if (!v->alive) { xs->viper = -1; return; }

    v->x += 4.0f * h;
    v->y += jump_held ? -4.0f : 4.0f;
    env->x = v->x;
    env->y = v->y;
    env->hspeed = 0; env->vspeed = 0;

    /* source: held shoot fires whenever under the 3-bullet cap
     * (global.autofireF defaults off, so vicautofire never gates) */
    if (v->t1 > 0) v->t1--;
    if (shoot_held) {
        /* instance_number counts ACTIVE instances: bullets deactivated
         * out of view free the 3-slot cap, as in the source */
        int nb = 0;
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].active &&
                xs->ents[i].cls == XB_VICBULLET)
                nb++;
        if (nb < 3) {
            IWXEnt* b = iwxb_spawn(env, (int)v->p[0], v->x + 64,
                                   v->y - 2);
            if (b) b->vx = 16;
            v->t1 = 16;
        }
    }

    /* death: solids, spike tiles, static killers, gradius hazards */
    double l, r, t, b;
    iwx_ent_bbox(xs, v, &l, &r, &t, &b);
    int il = (int)l, ir = (int)r, it = (int)t, ib = (int)b;
    int die = !iwx_rect_free(env, il, ir, it, ib);
    if (!die) {
        int tx0 = il / IW_TILE, tx1 = ir / IW_TILE;
        int ty0 = it / IW_TILE, ty1 = ib / IW_TILE;
        for (int ty = ty0; ty <= ty1 && !die; ty++)
            for (int tx = tx0; tx <= tx1 && !die; tx++) {
                uint8_t k = iw_tile_at(env, tx, ty);
                if (k >= T_SPIKE_UP && k <= T_SPIKE_RIGHT &&
                    spike_hit_px(il, ir, it, ib, tx * IW_TILE,
                                 ty * IW_TILE, k)) die = 1;
            }
        for (int i = 0; i < env->n_killers && !die; i++) {
            const IWPackKiller* k = &env->killers[i];
            if (il <= k->x1 && ir >= k->x0 && it <= k->y1 && ib >= k->y0 &&
                spike_hit_rect(il, ir, it, ib, k->shape, k->x0, k->y0,
                               k->x1, k->y1)) die = 1;
        }
    }
    if (!die)
        for (int i = 0; i < xs->n_ents && !die; i++) {
            IWXEnt* o = &xs->ents[i];
            if (!o->alive) continue;
            if (o->cls != XB_GRADFRUIT && o->cls != XB_GRADBUGZ &&
                o->cls != XB_GRADDRONE && o->cls != XB_GRADDRONEBULLET &&
                o->cls != XB_GRADBOSS &&
                (o->cls != XB_SINISTAR || o->state != 1)) continue;
            if (iwx_bbox_hit(xs, o, il, ir, it, ib)) die = 1;
        }
    if (die) {
        xs->pending_kill = 1;
        xs->viper = -1;
        v->state = 0;
        v->x = v->x0; v->y = v->y0;
    }
}

/* viper bullets vs the gradius actors (xent-vs-xent) */
static void iwxb_vicbullet_hits(IWanna* env, IWXEnt* b) {
    IWXState* xs = XS(env);
    double l, r, t, bt;
    iwx_ent_bbox(xs, b, &l, &r, &t, &bt);
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* o = &xs->ents[i];
        if (!o->alive) continue;
        if (o->cls == XB_GRADBUGZ || o->cls == XB_GRADDRONE ||
            o->cls == XB_GRADBOSS) {
            if (!iwx_bbox_hit(xs, o, (int)l, (int)r, (int)t, (int)bt))
                continue;
            b->alive = 0;
            if (o->cls == XB_GRADBOSS) {
                o->hp -= 1;
                if (o->hp <= 0) {
                    o->state = 2;
                    o->alive = 0;
                    for (int k = 0; k < xs->n_ents; k++)
                        if (xs->ents[k].alive &&
                            xs->ents[k].cls == XB_VICVIPER)
                            iwxb_viper_victory(env, &xs->ents[k]);
                }
            } else o->alive = 0;
            return;
        }
    }
}

#endif /* IWX_BOSS_ROAD_H */
