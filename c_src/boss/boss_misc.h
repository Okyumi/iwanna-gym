/* boss_misc.h — Mother Brain (rMetroid) and the Arkanoid minigame
 * (rGuyFortress2), transliterated from objects/MommyThinker.gml +
 * Samus.gml (cameo: visual) and ArkaBall / ArkaPlatform / ArkaBrick /
 * ArkaBrickShort.
 *
 * Mother Brain (plain ent, no slot): e->hp = 35; state 0 glass intact /
 * 1 shattered-open / 2 dying / 3 gone; link = her solid glass ent (a
 * removable solid with the sprMotherHitboxes frame-1 mask).  The first
 * bullet opens the glass, later ones damage; at 0 the room's turrets /
 * dispensers die, the platforms are freed and she flashes out.  The
 * escape trigger (event_user) removes her and starts the 3000-frame
 * countdown drawn as TIME in source; at 0 the player dies wherever
 * they are.  Touching the brain kills.
 *
 * Arkanoid: the paddle mirrors the player inside the zone
 * (1728<px<2336, py>200; x clamped 1776..2288) and launches the ball at
 * 45deg, 3.75 px/f.  The ball is a killer; it reflects off the Bounce*
 * markers, off the paddle (angle from the paddle center+32), and off
 * bricks with the source's circle-vs-rect test (radius 12, +0.125 speed
 * per brick, -0.25 per short brick; bricks are removable solids with
 * their center in p0/p1, p2 = short).  All bricks gone -> Sinistar.
 */
#ifndef IWX_BOSS_MISC_H
#define IWX_BOSS_MISC_H

static void iwxb_mommy_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    if (e->state == 2) {                       /* dying: 30 flashes */
        if (++e->t0 >= 75) {
            e->state = 3;
            e->x = -1000;
        }
        return;
    }
    if (e->state == 4) {                       /* escape countdown */
        if (--e->t1 <= 0) {
            xs->pending_kill = 1;              /* out of TIME */
            e->state = 3;
        }
        return;
    }
    if (e->state > 2) return;
    /* touching the brain kills */
    int pl, pr, pt, pb;
    iwx_player_rect(env, &pl, &pr, &pt, &pb);
    if (iwx_hit_rect(xs, e, pl, pr, pt, pb)) xs->pending_kill = 1;
}

static void iwxb_mommy_event(IWanna* env, IWXEnt* e) {
    /* the escape trigger: she leaves, the countdown begins */
    IWXState* xs = XS(env);
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* o = &xs->ents[i];
        if (!o->alive) continue;
        if (o->cls == XB_SPAG || o->cls == XB_SPAGDISP ||
            o->cls == XB_TOURTURRET)
            o->alive = 0;
    }
    if (e->link >= 0) xs->ents[e->link].alive = 0;   /* glass */
    e->x = -9999;
    e->state = 4;
    e->t1 = 3000;
}

static void iwxb_mommy_bullet(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    if (e->state >= 2) return;
    if (e->state == 0) {
        e->state = 1;                          /* glass shatters open */
        e->frame = 2;
        return;
    }
    e->hp -= 1;
    if (e->hp <= 0) {
        e->state = 2;
        e->t0 = 0;
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* o = &xs->ents[i];
            if (!o->alive) continue;
            if (o->cls == XB_SPAG || o->cls == XB_SPAGDISP ||
                o->cls == XB_TOURTURRET)
                o->alive = 0;
        }
        if (e->link >= 0) xs->ents[e->link].alive = 0;
    }
}

/* ---- Arkanoid ---- */

static void iwxb_arka_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    switch (e->cls) {
    case XB_ARKAPADDLE: {
        int act = env->x > 1728 && env->x < 2336 && env->y > 200;
        e->on = (uint8_t)act;
        if (act) {
            float px = (float)env->x;
            if (px < 1776) px = 1776;
            if (px > 2288) px = 2288;
            e->x = px;
            /* launch the parked ball */
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* bl = &xs->ents[i];
                if (bl->alive && bl->cls == XB_ARKABALL &&
                    bl->vx == 0 && bl->vy == 0) {
                    float d = 45 * 3.14159265358979323846f / 180.0f;
                    bl->vx = 3.75f * cosf(d);
                    bl->vy = -3.75f * sinf(d);
                }
            }
        }
        break;
    }
    case XB_ARKABALL: {
        if (e->vx == 0 && e->vy == 0) break;
        /* paddle bounce */
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* p2 = &xs->ents[i];
            if (!p2->alive || p2->cls != XB_ARKAPADDLE) continue;
            double l, r, t, b;
            iwx_ent_bbox(xs, p2, &l, &r, &t, &b);
            int hit = e->x + 12 >= l && e->x - 12 <= r &&
                      e->y + 12 >= t && e->y - 12 <= b;
            if (hit && !e->on) {
                e->on = 1;
                float dx = e->x - p2->x, dy = e->y - (p2->y + 32);
                float L = sqrtf(dx * dx + dy * dy);
                float sp = sqrtf(e->vx * e->vx + e->vy * e->vy);
                if (L > 0) { e->vx = sp * dx / L; e->vy = sp * dy / L; }
            } else if (!hit) e->on = 0;
        }
        /* bounce markers */
        {
            double l = e->x - 12, r = e->x + 12, t = e->y - 12,
                   b = e->y + 12;
            for (int k = 0; k < xs->n_idx_marker; k++) {
                IWXEnt* m = &xs->ents[xs->idx_marker[k]];
                if (!m->alive) continue;
                int kind = (int)m->p[0];
                if (kind < XM_BOUNCE_UP || kind > XM_BOUNCE_RIGHT)
                    continue;
                if (!iwx_bbox_hit(xs, m, (int)l, (int)r, (int)t, (int)b))
                    continue;
                if (kind == XM_BOUNCE_DOWN) e->vy = fabsf(e->vy);
                if (kind == XM_BOUNCE_UP) e->vy = -fabsf(e->vy);
                if (kind == XM_BOUNCE_RIGHT) e->vx = fabsf(e->vx);
                if (kind == XM_BOUNCE_LEFT) e->vx = -fabsf(e->vx);
            }
        }
        /* bricks (the source circle-vs-rect reflection) */
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* br = &xs->ents[i];
            if (!br->alive || br->cls != XB_ARKABRICK) continue;
            float cx = br->p[0], cy = br->p[1];
            float hw = br->p[2] != 0 ? 16.0f : 32.0f, hh = 16.0f;
            if (e->x + 12 < cx - hw || e->x - 12 > cx + hw ||
                e->y + 12 < cy - hh || e->y - 12 > cy + hh) continue;
            float xc, yc;
            float adx = fabsf(e->x - cx), ady = fabsf(e->y - cy);
            if (ady <= hh) { xc = cx + hw * (e->x > cx ? 1 : -1);
                             yc = e->y; }
            else if (adx <= hw) { xc = e->x;
                                  yc = cy + hh * (e->y > cy ? 1 : -1); }
            else { xc = cx + hw * (e->x > cx ? 1 : -1);
                   yc = cy + hh * (e->y > cy ? 1 : -1); }
            float ddx = e->x - xc, ddy = e->y - yc;
            float dist = sqrtf(ddx * ddx + ddy * ddy);
            if (dist >= 12) continue;
            /* moving toward the surface? */
            float nx = dist > 0 ? ddx / dist : 0,
                  ny = dist > 0 ? ddy / dist : -1;
            if (e->vx * nx + e->vy * ny >= 0) continue;
            e->x = xc + 12 * nx;
            e->y = yc + 12 * ny;
            float dot = e->vx * nx + e->vy * ny;
            e->vx -= 2 * dot * nx;
            e->vy -= 2 * dot * ny;
            float sp = sqrtf(e->vx * e->vx + e->vy * e->vy);
            float want = sp + (br->p[2] != 0 ? -0.25f : 0.125f);
            if (want < 0.5f) want = 0.5f;
            if (sp > 0) { e->vx *= want / sp; e->vy *= want / sp; }
            br->alive = 0;
        }
        e->x += e->vx; e->y += e->vy;
        break;
    }
    default: break;
    }
}

#endif /* IWX_BOSS_MISC_H */
