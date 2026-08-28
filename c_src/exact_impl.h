/* exact_impl.h — implementation of the exact-behavior layer (see exact.h).
 * Included by iwanna.h after the IWanna struct and collision utilities.
 * Every function is a no-op / cheap guard when env->xs == NULL.
 */
#ifndef IW_EXACT_IMPL_H
#define IW_EXACT_IMPL_H

/* ---------------- forward decls into iwanna.h ---------------- */
static int place_free(IWanna* env, double px, double py);
static int rect_hits_solid(IWanna* env, int l, int r, int t, int b);
static void iw_player_shoot(IWanna* env);

static void iwx_run_ops(IWanna* env, int op0, int nops, int self);
static void iwx_ent_event(IWanna* env, IWXEnt* e);
static void iwx_view_update(IWanna* env);

/* ---------------- small helpers ---------------- */

static inline IWXState* XS(IWanna* env) { return env->xs; }

static inline void iwx_player_rect(IWanna* env, int* l, int* r, int* t, int* b) {
    int ix = gm_round(env->x), iy = gm_round(env->y);
    *l = ix + env->hb_l; *r = ix + env->hb_r;
    *t = iy + env->hb_t; *b = iy + env->hb_b;
}

/* GM distance_to_object: gap between bounding boxes (0 when overlapping) */
static inline double iwx_bbox_gap(double al, double ar, double at, double ab,
                                  double bl, double br, double bt, double bb) {
    double dx = 0, dy = 0;
    if (bl > ar) dx = bl - ar; else if (al > br) dx = al - br;
    if (bt > ab) dy = bt - ab; else if (at > bb) dy = at - bb;
    return sqrt(dx * dx + dy * dy);
}

static inline int iwx_flag_bit(IWanna* env, int bit) {
    return (env->gflags >> bit) & 1ull;
}

/* view rect helpers (800x608 view) */
static inline int iwx_in_view_bbox(IWXState* xs, double l, double r,
                                   double t, double b) {
    return r >= xs->view_x && l < xs->view_x + 800 &&
           b >= xs->view_y && t < xs->view_y + 608;
}

static int iwx_ent_in_view(IWXState* xs, const IWXEnt* e) {
    double l, r, t, b;
    iwx_ent_bbox(xs, e, &l, &r, &t, &b);
    if (r < l) /* no mask: point test (inside_view workaround) */
        return e->x >= xs->view_x && e->x < xs->view_x + 800 &&
               e->y >= xs->view_y && e->y < xs->view_y + 608;
    return iwx_in_view_bbox(xs, l, r, t, b);
}

/* spawn a live entity from a template (bounded; drops when full) */
static IWXEnt* iwx_spawn(IWanna* env, int tmpl_idx, float x, float y) {
    IWXState* xs = XS(env);
    if (tmpl_idx < 0 || tmpl_idx >= (int)xs->hdr.n_tmpl) return NULL;
    const IWXEntRec* r = &xs->tmpl[tmpl_idx];
    int slot = -1;
    for (int i = 0; i < xs->cap; i++) {
        int k = (xs->n_ents + i) % xs->cap;
        if (!xs->ents[k].alive) { slot = k; break; }
    }
    if (slot < 0) return NULL;
    IWXEnt* e = &xs->ents[slot];
    memset(e, 0, sizeof *e);
    e->cls = r->cls; e->mask = r->mask;
    e->x = x; e->y = y; e->x0 = x; e->y0 = y;
    e->xs = r->xs ? r->xs : 1.0f; e->ys = r->ys ? r->ys : 1.0f;
    e->tag = -1;
    e->flags = r->flags;
    memcpy(e->p, r->p, sizeof e->p);
    e->alive = 1;
    e->active = 1;             /* instance_create: active by default */
    e->armed = (r->flags & XEF_START_INACTIVE) ? 0 : 1;
    e->link = -1;
    e->hp = 0;
    if (slot >= xs->n_ents) xs->n_ents = slot + 1;
    return e;
}

/* ---------------- room loading / reset ---------------- */

static void iwx_load_room(IWanna* env, int room) {
    IWXState* xs = XS(env);
    if (!xs) return;
    const IWXRoomRec* rr = &xs->xrooms[room];
    xs->room = room;
    memset(xs->ents, 0, sizeof(IWXEnt) * (size_t)xs->cap);
    xs->n_ents = (int)rr->n_xents;
    const IWXEntRec* recs =
        (const IWXEntRec*)((const uint8_t*)env->pack->blob + rr->xents_off);
    for (int i = 0; i < (int)rr->n_xents; i++) {
        const IWXEntRec* r = &recs[i];
        IWXEnt* e = &xs->ents[i];
        e->cls = r->cls; e->mask = r->mask;
        e->x = e->x0 = r->x; e->y = e->y0 = r->y;
        e->xs = r->xs ? r->xs : 1.0f;
        e->ys = r->ys ? r->ys : 1.0f;
        e->tag = r->tag;
        e->flags = r->flags;
        memcpy(e->p, r->p, sizeof e->p);
        e->alive = 1;
        e->active = 1;
        e->armed = (r->flags & XEF_START_INACTIVE) ? 0 : 1;
        e->link = r->link;
        e->vx = e->vy = 0; e->angle = 0;
        e->frame = 0; e->fspd = 0;
        e->t0 = e->t1 = e->state = e->hp = 0;
        e->on = 0;
        /* per-class spawn init that the converter encodes via params */
        switch (e->cls) {
        case XB_ANIM_KILLER:
            e->armed = e->p[4] != 0;
            e->frame = e->p[1];
            if (e->armed) e->fspd = e->p[0];
            break;
        case XB_EGGPLANT: e->vy = 2.5f; break;
        case XB_BOUNCYFRUIT: e->vy = -5.0f; break;
        case XB_MEDUSA: e->vx = e->p[0]; e->t0 = 50; e->t1 = 5; break;
        case XB_CHEEP: e->state = 0; break;
        case XB_CART: e->vx = 4; xs->cart_ent = i; break;
        case XB_MOVPLAT: e->vx = e->p[0]; e->vy = e->p[1]; break;
        case XB_GUYPLAT: e->vy = e->p[0]; break;
        case XB_LONK: e->vx = 1.2625f; break;
        case XB_QUICKLASER:
            e->angle = e->p[3];
            e->p[6] = -e->p[2];          /* size = -delay */
            break;
        case XB_SPAGDISP: e->t0 = 110; break;
        case XB_HOVERGUNNER: e->t0 = 90; break;
        case XB_TOURTURRET: e->t0 = 130; break;
        case XB_GHOULGEN:
            e->t0 = 175;
            e->vx = (iw_rand(env) & 1) ? 0.625f : -0.625f;
            break;
        case XB_WITCH: e->y = -999; break;
        case XB_CONDSOLID:
            /* p0 = flag bit, p1 = 1 solid-when-set (BlownEntrance) */
            e->alive = (iwx_flag_bit(env, (int)e->p[0]) != 0) == (e->p[1] != 0);
            break;
        case XB_ORB:
            if (iwx_flag_bit(env, (int)e->p[0])) e->alive = 0;
            break;
        case XB_SECRET:
            if (iwx_flag_bit(env, (int)e->p[0])) e->alive = 0;
            break;
        case XB_GUTSMAN: e->t0 = 150; break;
        case XB_ERRORTRAP: e->t0 = 0; break;
        case XB_FRBARRIER: e->t1 = 3; break;
        case XB_TETBLOCK: case XB_KILLER:
            if (e->flags & XEF_START_INACTIVE) e->alive = 0;
            if (e->cls == XB_KILLER) {
                e->fspd = e->p[0]; e->frame = e->p[3];
                e->angle = e->p[9];
            }
            break;
        case XB_BUTTON: e->state = (int)e->p[8]; break;
        case XB_FACTORYBLOCK: e->frame = e->p[0]; break;
        case XB_BOSS_BIRDO:
            /* MechaBirdo Create: savedata("orb_birdo") skips the fight
             * (the room-enter ops warp the player on) */
            if (iwx_flag_bit(env, (int)e->p[9])) e->alive = 0;
            break;
        case XB_MOONSMALL:
            e->vy = e->p[0];               /* creation-code vspeed */
            if (e->vy != 0) e->state = 1;
            break;
        case XB_KGSPIKE: {
            /* Create: image_index = image_number-1, waiting for its
             * `active` roll (armed <- boss events, never at load) */
            const IWXMaskRec* sm = iwx_mask(xs, e->mask);
            e->frame = sm && sm->nframes ? (float)(sm->nframes - 1) : 0;
            e->armed = 0;
            break;
        }
        default: break;
        }
    }
    xs->camera = (int)rr->camera;
    xs->always_active = (int)rr->always_active;
    xs->cart_ent = -1;
    for (int i = 0; i < xs->n_ents; i++)
        if (xs->ents[i].cls == XB_CART) xs->cart_ent = i;
    /* player extension state resets with the room (source: room restart) */
    xs->frozen = 0; xs->stoned = 0; xs->birded = 0; xs->fished = 0;
    xs->carted = 0; xs->on_platform = 0;
    xs->hang = 0; xs->walljump = 0; xs->walljumpboost = 0;
    xs->walljumpdir = 0; xs->altj = 0;
    xs->fire = 0; xs->metroid_doom = 0;
    xs->pending_kill = 0; xs->pending_freeze = 0;
    xs->view_init = 0;
    /* boss framework: slots die with the room (death/retry = room reset) */
    memset(xs->boss, 0, sizeof xs->boss);
    xs->n_boss = 0;
    xs->cam_voffset = 0;
    xs->cam_locked = (uint8_t)(xs->camera == XCAM_KRAID);  /* cameraKraid */
    xs->cam_piledriver = 0;
    /* cheep start alarms (source: CheepController Other_4, random 1..n) */
    int ncheep = 0;
    for (int i = 0; i < xs->n_ents; i++)
        if (xs->ents[i].cls == XB_CHEEP) ncheep++;
    if (ncheep) {
        int n = (int)(ncheep * 2.5);
        if (n < 1) n = 1;
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].cls == XB_CHEEP)
                xs->ents[i].t0 = 1 + (int)(iw_rand(env) % (uint64_t)n);
    }
    /* room-entry ops (compiled from scripts/room_start.gml conditions) */
    iwx_run_ops(env, (int)rr->enter_op0, (int)rr->enter_nops, -1);
}

/* called after the player position is final (reset / respawn / switch) */
static void iwx_after_spawn(IWanna* env) {
    IWXState* xs = XS(env);
    if (!xs) return;
    /* Cart state on entry/respawn (scripts/room_start.gml) */
    if (xs->cart_ent >= 0) {
        IWXEnt* c = &xs->ents[xs->cart_ent];
        if (env->x > 20000) {
            if (!c->on) iwx_ent_event(env, c);   /* crashed cart + wall */
        } else {
            xs->carted = 1;
            c->x = (float)env->x - 64;
        }
    }
    if (xs->spawn_boost != 0) {
        env->vspeed = xs->spawn_boost;
        xs->spawn_boost = 0;
    }
    xs->view_init = 0;
    iwx_view_update(env);      /* cameraHard event_user(0) at room start */
}

/* ---------------- camera + activation ---------------- */

static void iwx_activation_pass(IWanna* env) {
    IWXState* xs = XS(env);
    if (xs->always_active) {
        for (int i = 0; i < xs->n_ents; i++) xs->ents[i].active = 1;
        return;
    }
    double x0 = xs->view_x - 800 + 4, y0 = xs->view_y - 608 + 4;
    double x1 = x0 + 800 * 3 - 8, y1 = y0 + 608 * 3 - 8;
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* e = &xs->ents[i];
        if (!e->alive) continue;
        if (e->flags & XEF_FORCE_ACTIVE) { e->active = 1; continue; }
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (r < l) { l = r = e->x; t = b = e->y; }
        e->active = (r >= x0 && l <= x1 && b >= y0 && t <= y1);
    }
    /* movingPlatform neighborhoods stay active (activation_update tail) */
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* p = &xs->ents[i];
        if (!p->alive || !(p->flags & XEF_PLATFORM)) continue;
        if (p->cls != XB_MOVPLAT && p->cls != XB_FALLPLAT &&
            p->cls != XB_METROIDPLAT && p->cls != XB_ASCENT &&
            p->cls != XB_KUMO && p->cls != XB_GUYPLAT)
            continue;
        double l, r, t, b;
        iwx_ent_bbox(xs, p, &l, &r, &t, &b);
        for (int k = 0; k < xs->n_ents; k++) {
            IWXEnt* e = &xs->ents[k];
            if (!e->alive || e->active) continue;
            double el, er, et, eb;
            iwx_ent_bbox(xs, e, &el, &er, &et, &eb);
            if (er >= l - 8 && el <= r + 8 && eb >= t - 8 && et <= b + 8)
                e->active = 1;
        }
        p->active = 1;
    }
    xs->act_x = xs->view_x; xs->act_y = xs->view_y;
}

static double iwx_median3(double a, double b, double c) {
    if (b < a) { double t = a; a = b; b = t; }
    if (c < b) { c = b; }
    return b < a ? a : (b < c ? b : c);
}

static void iwx_view_update(IWanna* env) {
    IWXState* xs = XS(env);
    double px = env->x, py = env->y;
    double W = env->room_pw, H = env->room_ph;
    double nx = xs->view_x, ny = xs->view_y;
    switch (xs->camera) {
    case XCAM_HARD:
    case XCAM_HARD_METROID: {
        nx = iwx_median3(0, floor(px / 800) * 800, W - 800);
        /* rMetroid smooth-y (settings("smoothmetroid") default 1) */
        if (xs->camera == XCAM_HARD_METROID &&
            (xs->hdr.flags & 2u) && nx >= 2400) {
            double cy = xs->view_init ? xs->view_y : py - 304;
            if (py - 304 > cy + 96) cy = py - 304 - 96;
            if (py - 304 < cy - 96) cy = py - 304 + 96;
            ny = iwx_median3(0, cy, H - 608);
        } else {
            ny = iwx_median3(0, floor(py / 608) * 608, H - 608);
        }
        break;
    }
    case XCAM_CART: {
        IWXEnt* c = xs->cart_ent >= 0 ? &xs->ents[xs->cart_ent] : NULL;
        if (c && !c->on) {                 /* on = dead flag for the cart */
            nx = c->x + 54 - 400;
            if (nx > px && xs->view_init) xs->pending_kill = 1;
        } else {
            double cur = xs->view_init ? xs->view_x : px - 400;
            nx = cur < 22368 + 32 ? cur : 22368 + 32;
            if (px - 400 > nx) nx = px - 400;
        }
        ny = 0;
        break;
    }
    case XCAM_KRAID: {
        /* cameraKraid Step_2: piledriver follows the boss, locked pins
         * the arena screen, otherwise follow the player (y capped 281);
         * voffset is the one-frame quake shake */
        if (xs->cam_piledriver) {
            double bx2 = px, by2 = py;
            for (int s = 0; s < IWXB_MAX; s++)
                if (xs->boss[s].used &&
                    xs->boss[s].def == IWXB_DEF_KRAIDGIEF) {
                    bx2 = xs->ents[xs->boss[s].ent].x;
                    by2 = xs->ents[xs->boss[s].ent].y;
                }
            nx = iwx_median3(0, bx2 + 103 - 400, W - 800);
            ny = iwx_median3(0, by2 + 400 - 304, 281);
        } else if (xs->cam_locked) { nx = 0; ny = 281; }
        else {
            nx = iwx_median3(0, px - 400, W - 800);
            ny = iwx_median3(0, py - 304, 281);
        }
        ny += xs->cam_voffset;
        xs->cam_voffset = 0;
        break;
    }
    case XCAM_TOWER: {
        if (px > 800) { nx = 800; ny = 2432; }
        else {
            double cy = xs->view_init ? xs->view_y
                                      : iwx_median3(0, py - 304, H - 608);
            cy = (cy * 19 + (py - 304)) / 20;
            ny = iwx_median3(0, cy, H - 608);
            nx = 0;
        }
        break;
    }
    default:
        nx = 0; ny = 0; break;
    }
    xs->view_x = nx; xs->view_y = ny;
    if (!xs->view_init) {
        xs->view_init = 1;
        iwx_activation_pass(env);
        return;
    }
    /* re-activate when the view crosses a screen (hard) or moves 32px */
    double dx = fabs(nx - xs->act_x), dy = fabs(ny - xs->act_y);
    int redo = 0;
    if (xs->camera == XCAM_HARD) redo = (dx >= 1 || dy >= 1);
    else if (xs->camera == XCAM_HARD_METROID) redo = (dx >= 1 || dy > 32);
    else redo = (dx > 32 || dy > 32);
    if (redo) iwx_activation_pass(env);
}

/* ---------------- op programs ---------------- */

static void iwx_ent_event(IWanna* env, IWXEnt* e);   /* event_user(0) */
static void iwx_kill_destructible(IWanna* env, IWXEnt* e,
                                  float dvx, float dvy);

static void iwx_op_apply(IWanna* env, const IWXOpRec* o, IWXEnt* e) {
    IWXState* xs = XS(env);
    switch (o->op) {
    case XOP_SET_ACTIVE:
        if (e) { e->on = (int)o->a; if (o->a) e->active = 1; }
        break;
    case XOP_ARM:
        if (e) {
            e->active = 1;
            if (!e->armed) {
                e->armed = 1;
                if (e->cls == XB_ANIM_KILLER) e->fspd = e->p[0];
            }
        }
        break;
    case XOP_SET_VX:
        if (e) {
            e->active = 1;
            e->vx = o->a;
            if (e->cls == XB_FRUIT && e->state == 0) e->state = 2;
        }
        break;
    case XOP_SET_VY:
        if (e) {
            e->active = 1;
            e->vy = o->a;
            if (e->cls == XB_FRUIT && e->state == 0) e->state = 2; /* 1-frame delay */
            if (e->cls == XB_BOLT) e->armed = 1;
        }
        break;
    case XOP_SET_FSPD: if (e) e->fspd = o->a; break;
    case XOP_SET_STATE: if (e) e->state = (int)o->a; break;
    case XOP_ADD_STATE: if (e) e->state += (int)o->a; break;
    case XOP_EVENT: if (e) { e->active = 1; iwx_ent_event(env, e); } break;
    case XOP_DESTROY:
        if (e) {
            if (e->cls == XB_DESTRUCTIBLE) iwx_kill_destructible(env, e, 0, 0);
            else e->alive = 0;
        }
        break;
    case XOP_KILL_PLAYER: xs->pending_kill = 1; break;
    case XOP_FREEZE_PLAYER: xs->frozen = (int)o->a; break;
    case XOP_SET_FIRE: xs->fire = (int)o->a; break;
    case XOP_SET_FLAG:
        env->gflags |= 1ull << (int)o->a;
        break;
    case XOP_GOTO_ROOM:
        env->pending_room = (int)o->a;
        if (o->b < 0) { env->pending_use_start = 1; env->pending_keep_speed = 0; }
        else { env->pending_x = o->b; env->pending_y = o->c;
               env->pending_use_start = 0; env->pending_keep_speed = 0; }
        break;
    case XOP_SET_FRAME: if (e) e->frame = o->a; break;
    case XOP_LAST_FRAME:
        if (e) {
            const IWXMaskRec* m = iwx_mask(xs, e->mask);
            e->frame = m && m->nframes ? (float)(m->nframes - 1) : e->frame;
            e->fspd = 0;
        }
        break;
    case XOP_SET_TIMER: if (e) e->t0 = (int)o->a; break;
    case XOP_SET_P: if (e) e->p[(int)o->a] = o->b; break;
    case XOP_SPAWNBOOST: xs->spawn_boost = o->a; break;
    case XOP_CAM_MODE:
        if ((int)o->a == 0) { xs->cam_locked = 0; xs->cam_piledriver = 0; }
        else if ((int)o->a == 1) xs->cam_locked = 1;
        else xs->cam_piledriver = 1;
        break;
    case XOP_SPAWN: {
        IWXEnt* s = iwx_spawn(env, (int)o->a, o->b, o->c);
        (void)s;
        break;
    }
    default: break;
    }
}

/* run an op slice; `self` = trigger's own xent index (or -1) */
static void iwx_run_ops(IWanna* env, int op0, int nops, int self) {
    IWXState* xs = XS(env);
    if (!xs || nops <= 0) return;
    int i = 0;
    while (i < nops) {
        const IWXOpRec* o = &xs->ops[op0 + i];
        /* resolve target */
        IWXEnt* tgt = NULL;
        int cls_broadcast = -1;
        if (o->tgt >= 0 && o->tgt < xs->cap) tgt = &xs->ents[o->tgt];
        else if (o->tgt == IWX_TGT_SELF && self >= 0) tgt = &xs->ents[self];
        else if (o->tgt <= IWX_TGT_CLS0) cls_broadcast = IWX_TGT_CLS0 - o->tgt;
        /* conditionals: skip (int)b ops when false */
        int skip = -1;
        switch (o->op) {
        case XOP_IF_STATE_EQ:
            if (!(tgt && tgt->alive && tgt->state == (int)o->a)) skip = (int)o->b;
            break;
        case XOP_IF_STATE_NE:
            if (!(tgt && tgt->alive && tgt->state != (int)o->a)) skip = (int)o->b;
            break;
        case XOP_IF_ALIVE: {
            int alive = 0;
            if (cls_broadcast >= 0) {
                for (int k = 0; k < xs->n_ents; k++)
                    if (xs->ents[k].alive && xs->ents[k].cls == cls_broadcast)
                        { alive = 1; break; }
            } else alive = tgt && tgt->alive;
            if (!alive) skip = (int)o->b;
            break;
        }
        case XOP_IF_DEAD: {
            int alive = 0;
            if (cls_broadcast >= 0) {
                for (int k = 0; k < xs->n_ents; k++)
                    if (xs->ents[k].alive && xs->ents[k].cls == cls_broadcast)
                        { alive = 1; break; }
            } else alive = tgt && tgt->alive;
            if (alive) skip = (int)o->b;
            break;
        }
        case XOP_IF_FLAG:
            if (!iwx_flag_bit(env, (int)o->a)) skip = (int)o->b;
            break;
        case XOP_IF_NOT_FLAG:
            if (iwx_flag_bit(env, (int)o->a)) skip = (int)o->b;
            break;
        case XOP_IF_PLAYER_FIRE:
            if (xs->fire != (int)o->a) skip = (int)o->b;
            break;
        case XOP_IF_Y_LT:
            if (!(tgt && tgt->alive && tgt->y < o->a)) skip = (int)o->b;
            break;
        case XOP_IF_VY_LE:
            if (!(tgt && tgt->alive && tgt->vy <= o->a)) skip = (int)o->b;
            break;
        case XOP_IF_X_LT:
            if (!(tgt && tgt->alive && tgt->x < o->a)) skip = (int)o->b;
            break;
        case XOP_IF_OVERLAP: {
            /* tgt overlaps the trigger (self) rect */
            int ok = 0;
            if (tgt && tgt->alive && self >= 0) {
                IWXEnt* tr = &xs->ents[self];
                double l, r, t, b;
                iwx_ent_bbox(xs, tr, &l, &r, &t, &b);
                ok = iwx_hit_rect(xs, tgt, (int)ceil(l), (int)floor(r),
                                  (int)ceil(t), (int)floor(b));
                if (!ok) {
                    /* fall back to bbox for mask-less targets */
                    double el, er, et, eb;
                    iwx_ent_bbox(xs, tgt, &el, &er, &et, &eb);
                    if (er >= el)
                        ok = el <= r && er >= l && et <= b && eb >= t;
                }
            }
            if (!ok) skip = (int)o->b;
            break;
        }
        case XOP_IF_P_EQ:
            if (!(tgt && tgt->alive && tgt->p[(int)o->c] == o->a))
                skip = (int)o->b;
            break;
        case XOP_IF_WITCH_WAIT: {
            int waiting = 0;
            for (int k = 0; k < xs->n_ents; k++)
                if (xs->ents[k].alive && xs->ents[k].cls == XB_WITCH &&
                    xs->ents[k].t1 == 0) { waiting = 1; break; }
            if (!waiting) skip = (int)o->b;
            break;
        }
        default:
            if (cls_broadcast >= 0) {
                for (int k = 0; k < xs->n_ents; k++)
                    if (xs->ents[k].alive && xs->ents[k].cls == cls_broadcast)
                        iwx_op_apply(env, o, &xs->ents[k]);
            } else if (o->tgt == IWX_TGT_PLAYER || o->tgt == IWX_TGT_NONE) {
                iwx_op_apply(env, o, NULL);
            } else {
                if (tgt && !tgt->alive &&
                    o->op != XOP_SPAWN) { i++; continue; }
                iwx_op_apply(env, o, tgt);
            }
            i++;
            continue;
        }
        i++;
        if (skip > 0) i += skip;
    }
}

/* ---------------- shared behavior helpers ---------------- */

/* destroy a blockTrapDestructible with debris velocity (cosmetic dropped) */
static void iwx_kill_destructible(IWanna* env, IWXEnt* e,
                                  float dvx, float dvy) {
    (void)dvx; (void)dvy;
    IWXState* xs = XS(env);
    if (!e->alive) return;
    e->alive = 0;
    /* destroying one also removes overlapping walljump strips (source) */
    double l, r, t, b;
    iwx_ent_bbox(xs, e, &l, &r, &t, &b);
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* w = &xs->ents[i];
        if (!w->alive) continue;
        if (w->cls == XB_WALLSTRIP) {
            double wl, wr, wt, wb;
            iwx_ent_bbox(xs, w, &wl, &wr, &wt, &wb);
            if (wr >= l && wl <= r && wb >= t && wt <= b) w->alive = 0;
        } else if (w->cls == XB_KILLER && (int)w->p[8] == e->tag + 1) {
            w->alive = 0;                 /* spikeUp dest=1 riding the block */
        }
    }
}

/* does rect [l..r]x[t..b] overlap any live marker of kind `kind`? */
static IWXEnt* iwx_marker_hit(IWXState* xs, int kind,
                              double l, double r, double t, double b) {
    for (int k3 = 0; k3 < xs->n_idx_marker; k3++) {
        IWXEnt* m = &xs->ents[xs->idx_marker[k3]];
        if (!m->alive || (int)m->p[0] != kind) continue;
        double ml, mr, mt, mb;
        iwx_ent_bbox(xs, m, &ml, &mr, &mt, &mb);
        if (mr >= l && ml <= r && mb >= t && mt <= b) return m;
    }
    return NULL;
}

/* entity-vs-entity bbox overlap */
static int iwx_ents_overlap(IWXState* xs, IWXEnt* a, IWXEnt* b) {
    double al, ar, at, ab, bl, br, bt, bb;
    iwx_ent_bbox(xs, a, &al, &ar, &at, &ab);
    iwx_ent_bbox(xs, b, &bl, &br, &bt, &bb);
    if (ar < al || br < bl) return 0;
    return ar >= bl && al <= br && ab >= bt && at <= bb;
}

/* is the rect free of solids INCLUDING dynamic xent solids? */
static int iwx_rect_free(IWanna* env, int l, int r, int t, int b) {
    if (rect_hits_solid(env, l, r, t, b)) return 0;
    return 1; /* rect_hits_solid already consults xent solids via hook */
}

/* player touching any live water region of kind at (px, py)? */
static int iwx_touch_water(IWanna* env, double px, double py, int kind) {
    IWXState* xs = XS(env);
    if (!xs) return 0;
    int ix = gm_round(px), iy = gm_round(py);
    int l = ix + env->hb_l, r = ix + env->hb_r;
    int t = iy + env->hb_t, b = iy + env->hb_b;
    for (int k4 = 0; k4 < xs->n_idx_water; k4++) {
        IWXEnt* e = &xs->ents[xs->idx_water[k4]];
        if (!e->alive || !e->active) continue;
        if (kind && (int)e->p[0] != kind) continue;
        if (iwx_bbox_hit(xs, e, l, r, t, b)) return 1;
    }
    return 0;
}

/* player touching a platform-flagged entity at (px, py)? (bbox test) */
static int iwx_touch_platform(IWanna* env, double px, double py) {
    IWXState* xs = XS(env);
    if (!xs) return 0;
    int ix = gm_round(px), iy = gm_round(py);
    int l = ix + env->hb_l, r = ix + env->hb_r;
    int t = iy + env->hb_t, b = iy + env->hb_b;
    for (int k5 = 0; k5 < xs->n_idx_plat; k5++) {
        IWXEnt* e = &xs->ents[xs->idx_plat[k5]];
        if (!e->alive || !e->active) continue;
        if (e->cls == XB_CART) {
            if (e->p[9] > 0 &&
                l <= e->x + 106 - 1 && r >= e->x &&
                t <= e->y + 4 + 16 - 1 && b >= e->y + 4) return 1;
            continue;
        }
        if (!(e->flags & XEF_PLATFORM)) continue;
        if (iwx_bbox_hit(xs, e, l, r, t, b)) return 1;
    }
    return 0;
}

/* shared movingPlatform Step (movingPlatform.gml): view freeze, solid and
 * blockNise bounces, manual yspeed, rider carry, channel swap, motion.
 * e->vy = built-in vspeed, e->p[9] = yspeed channel. */
static void iwx_platform_step(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    double l, r, t, b;
    iwx_ent_bbox(xs, e, &l, &r, &t, &b);
    int frozen_now = (r + 1 > xs->view_x + 1600 || l < xs->view_x - 800 ||
                      t < xs->view_y - 608 || b + 1 > xs->view_y + 1216);
    if (!(e->flags & XEF_NOBOUNCE)) {
        int il = (int)ceil(l), ir = (int)floor(r);
        int it = (int)ceil(t), ib = (int)floor(b);
        if (e->vx != 0 &&
            !iwx_rect_free(env, (int)(il + e->vx), (int)(ir + e->vx), it, ib)) {
            e->vx = -e->vx;
            if (e->flags & XEF_STOPPER) e->vx = 0;
        }
        double vv = e->vy + e->p[9];
        if (vv != 0 &&
            !iwx_rect_free(env, il, ir, (int)(it + vv), (int)(ib + vv))) {
            if (e->vy != 0) { e->p[9] = -e->vy; e->vy = 0; }
            else { e->vy = -e->p[9]; e->p[9] = 0; }
            if (e->flags & XEF_STOPPER) { e->vy = 0; e->p[9] = 0; }
        }
        /* blockNise bounce (reverse both dirs on overlap) */
        if (iwx_marker_hit(xs, XM_BLOCKNISE, l, r, t, b)) {
            e->vx = -e->vx;
            double m = e->vy + e->p[9];
            e->vy = 0; e->p[9] = -m;
        }
    }
    e->y += e->p[9];
    /* carry the rider (instance_place(x, y-2, player)) */
    {
        int pl, pr, pt, pb;
        iwx_player_rect(env, &pl, &pr, &pt, &pb);
        if (pr >= l && pl <= r && pb >= t - 2 && pt <= b - 2) {
            env->y += e->p[9];
            if (!(e->flags & XEF_NOPUSH) || xs->on_platform) {
                if (place_free(env, env->x + e->vx, env->y))
                    env->x += e->vx;
            }
        }
    }
    if (e->vy < 0) { e->p[9] = e->vy; e->vy = 0; }
    if (e->p[9] > 0) { e->vy = e->p[9]; e->p[9] = 0; }
    if (!frozen_now) { e->x += e->vx; e->y += e->vy; }
}

/* event_user(0) per class (XOP_EVENT / internal) */
static void iwx_ent_event(IWanna* env, IWXEnt* e) {
    IWXState* xs = XS(env);
    switch (e->cls) {
    case XB_REVEALING:            /* rise; sink again after 200 frames */
        e->vy = -4; e->t0 = 200; e->state = 1;
        break;
    case XB_FRSPIKE:              /* Other_10: alarm[0] = 2*25 */
        e->on = 1;
        e->state = 1;
        e->t0 = 50;
        break;
    case XB_FRBARRIER:            /* close (allow-save-speedstrat guard) */
        if (e->t1 < 0) {
            e->fspd = 0.5f;
            e->state = 1;
        }
        break;
    case XB_SHAKE_FALL:           /* FirstRoomSpike-style c-trigger arming */
        if (!e->on) { e->on = 1; }
        break;
    case XB_FIRECHALICE: {        /* ignite every fire in the room */
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* f = &xs->ents[i];
            if (f->alive && f->cls == XB_ANIM_KILLER && f->p[5] >= 0 &&
                !f->armed && f->p[8] == 0) {
                f->armed = 1; f->fspd = f->p[0];
            }
        }
        break;
    }
    case XB_BUTTON:
        /* RyuButton event_user(0): forced OFF (factory ceiling entry) */
        e->state = 0; e->frame = 0;
        break;
    case XB_REALYOKU: {           /* Other_10: appear, auto-hide in 100 */
        const IWXMaskRec* m = iwx_mask(xs, e->mask);
        int nfr = m ? m->nframes : 4;
        e->fspd = 0.5f;
        e->frame = 1;
        e->t0 = (int)((nfr - 1) / 0.5);
        e->t1 = e->p[9] != 0 ? 0 : 100;   /* p9: end-trigger cancels hide */
        break;
    }
    case XB_CART: {               /* crash aftermath (Other_10) */
        e->on = 1; e->state = 3; e->x = 22539; e->vx = 0;
        int wall = (int)e->p[7];
        if (wall >= 0 && wall < xs->cap) xs->ents[wall].alive = 1;
        break;
    }
    case XB_MOONBIG:              /* path end / player died: go ballistic */
        if (e->state == 0) {
            e->state = 1;
            /* vx/vy already track the per-frame path delta */
        }
        break;
    default: break;
    }
}

/* Ghoul / enemies helper: face from vx */
#define IWX_PI 3.14159265358979323846

static void iwx_aim(float* vx, float* vy, double dx, double dy, double speed) {
    double d = sqrt(dx * dx + dy * dy);
    if (d < 1e-9) { *vx = (float)speed; *vy = 0; return; }
    *vx = (float)(speed * dx / d);
    *vy = (float)(speed * dy / d);
}

/* 32-direction quantized aim (mmf_direction(mmf_direction_to(dir))) */
static void iwx_aim32(float* vx, float* vy, double dx, double dy, double speed) {
    double ang = atan2(-dy, dx);                    /* GM angles, y up */
    int d32 = (int)floor(ang / (2 * IWX_PI) * 32 + 0.5);
    d32 = ((d32 % 32) + 32) % 32;
    double a = d32 * (2 * IWX_PI / 32);
    *vx = (float)(speed * cos(a));
    *vy = (float)(-speed * sin(a));
}

/* 45-degree quantized aim (TourianTurret) */
static void iwx_aim45(float* vx, float* vy, double dx, double dy, double speed,
                      double* out_deg) {
    double ang = atan2(-dy, dx) * 180 / IWX_PI;
    double q = floor(ang / 45 + 0.5) * 45;
    *vx = (float)(speed * cos(q * IWX_PI / 180));
    *vy = (float)(-speed * sin(q * IWX_PI / 180));
    if (out_deg) *out_deg = q;
}

/* ---------------- per-frame entity behavior (pre-player, GM order) -------- */

/* ---------------- boss framework (c_src/boss/) ---------------- */
#include "boss/boss.h"
#include "boss/boss_birdo.h"
#include "boss/boss_kraidgief.h"

/* collision-phase bullet routing: weak-point consume (push mode) and
 * body deflects.  Gated by n_boss at the call site. */
static int iwxb_route_bullet(IWanna* env, IWEntity* b,
                             int bl, int br, int bt, int bb) {
    IWXState* xs = XS(env);
    for (int s = 0; s < IWXB_MAX; s++) {
        IWXBossState* bs = &xs->boss[s];
        if (!bs->used) continue;
        if (bs->def == IWXB_DEF_BIRDO || bs->def == IWXB_DEF_TEST) {
            for (int w = 0; w < IWXB_WEAK; w++) {
                int wi = bs->wp_ent[w];
                if (wi < 0 || !xs->ents[wi].alive) continue;
                if (iwx_hit_rect(xs, &xs->ents[wi], bl, br, bt, bb)) {
                    bs->wp_dmg[w] += 1.0f;   /* bullet damage = 1 */
                    return 1;
                }
            }
        }
        if (bs->def == IWXB_DEF_KRAIDGIEF && b->vy == 0) {
            /* Kraidgief Collision_bullet: deflect at choose(45,90,135,
             * -45,-90,-135), speed kept (16) */
            IWXEnt* body = &xs->ents[bs->ent];
            if (body->alive && iwx_hit_rect(xs, body, bl, br, bt, bb)) {
                static const float dirs[6] = { 45, 90, 135, -45, -90, -135 };
                float d = dirs[iw_rand(env) % 6] *
                          3.14159265358979323846f / 180.0f;
                b->vx = 16.0f * cosf(d);
                b->vy = -16.0f * sinf(d);
            }
        }
    }
    return 0;
}

static void iwx_update_ent(IWanna* env, int idx) {
    IWXState* xs = XS(env);
    IWXEnt* e = &xs->ents[idx];
    double px = env->x, py = env->y + 8;    /* global.px / global.py (Kid) */
    switch (e->cls) {

    case XB_MARKER: case XB_WALLSTRIP: case XB_WATER:
    case XB_CONDSOLID: case XB_LOCKCONTROLS: case XB_CARTPICKUP:
    case XB_TETBLOCK: case XB_WEAKBOX: case XB_KGCEIL:
        return;

    case XB_BOSS_TEST:      iwxb_test_step(env, e);      return;
    case XB_BOSS_BIRDO:     iwxb_birdo_step(env, e);     return;
    case XB_BOSS_KRAIDGIEF: iwxb_kraidgief_step(env, e); return;
    case XB_MECHAEGG: case XB_EGGHITBOX: case XB_LAZA: case XB_FLYGUY:
        iwxb_birdo_family_step(env, e);
        return;
    case XB_EGGPLAT: {                    /* movingPlatform child */
        iwx_platform_step(env, e);
        double l0, r0, t0v, b0;
        iwx_ent_bbox(xs, e, &l0, &r0, &t0v, &b0);
        if (r0 < 0) e->alive = 0;
        return;
    }
    case XB_KGPROJ: case XB_KGFIRE: case XB_BLANKA:
    case XB_KGDEBRISSPAWN: case XB_KGDEBRIS: case XB_KGSPIKE:
        iwxb_kg_family_step(env, e);
        return;

    case XB_KILLER:                     /* static killer w/ optional anim */
        e->frame += e->fspd;
        if (e->p[2] > 0 && e->frame >= e->p[2]) e->frame -= 2;  /* loop hi */
        if (e->flags & XEF_MIRROR8) e->t0++;
        return;

    case XB_ANIM_KILLER: {
        if (e->on && !e->armed) { e->armed = 1; e->fspd = e->p[0]; }
        if (e->armed && e->fspd == 0 && e->p[9] == 0) e->fspd = e->p[0];
        if (e->p[9] != 0) {             /* ping-pong (Grabby) */
            if (e->armed && e->fspd == 0) e->fspd = e->p[0];
            const IWXMaskRec* m = iwx_mask(xs, e->mask);
            int n = m ? m->nframes : 1;
            if (e->frame + e->fspd >= n || e->frame + e->fspd < 0)
                e->fspd = -e->fspd;
            e->frame += e->fspd;
            return;
        }
        if (e->armed) {
            e->frame += e->fspd;
            const IWXMaskRec* m = iwx_mask(xs, e->mask);
            int n = m ? m->nframes : 1;
            if (e->p[6] != 0 && e->frame >= n) { e->alive = 0; return; }
            if (e->p[3] > 0 && e->frame >= e->p[3]) e->frame -= 2;
            else if (e->frame >= n) e->frame -= (float)n;
        }
        return;
    }

    case XB_SHAKE_FALL: {
        if (e->on || e->t0 > 0) {
            int shake = (int)e->p[0];
            int period = e->p[4] > 0 ? (int)e->p[4] : 2;
            if (e->t0 < shake || e->p[5] != 0) {
                int phase = (e->t0 % period) < (period / 2);
                float amp = 1;
                if (e->p[3] != 0) {     /* both axes */
                    e->x = e->x0 + (phase ? -amp : amp);
                    e->y = e->y0 + (phase ? -amp : amp);
                } else {
                    e->y = e->y0 - (phase ? 1 : 0);
                }
            }
            if (e->t0 == shake) {
                if (e->p[5] == 0) { e->x = e->x0; e->y = e->y0; }
                e->vx = e->p[1];
                e->vy = e->p[2];
                if (e->p[6] != 0 && e->link >= 0)     /* FallStair solid */
                    xs->ents[e->link].alive = 0;
            }
            e->t0++;
        }
        e->x += e->vx; e->y += e->vy;
        return;
    }

    case XB_BOLT:
        e->x += e->vx; e->y += e->vy;
        return;

    case XB_SPIKEMAN: {
        /* FunnySpikeMan.gml: trigger c-code pulses state (in_range) */
        int inr = e->state;
        e->state = 0;
        const IWXMaskRec* m = iwx_mask(xs, e->mask);
        int nfr = m ? m->nframes : 5;
        if (inr) {
            if (!e->on) {                       /* waking anim */
                if (e->frame + 0.5f >= nfr) {
                    e->on = 1;
                    e->mask = (uint16_t)e->p[5];
                    e->frame = 0;
                } else e->frame += 0.5f;
            } else {                            /* walk toward the player */
                e->frame += 0.5f;
                if (e->frame >= nfr) e->frame -= (float)nfr;
                if (px < e->x) { e->xs = -(float)fabs(e->xs); e->x -= 4; }
                else if (px > e->x) { e->xs = (float)fabs(e->xs); e->x += 4; }
            }
        } else {
            if (e->on) {                        /* return to dormant sprite */
                e->on = 0;
                e->mask = (uint16_t)e->p[6];
                m = iwx_mask(xs, e->mask);
                e->frame = m ? (float)(m->nframes - 1) : 4;
            } else if (e->frame > 0) {
                e->frame -= 0.5f;
                if (e->frame < 0) e->frame = 0;
            }
        }
        return;
    }

    case XB_SPINNER: {
        /* FactorySpinner1 (p0=1): trigger-armed, tips to +90, y-1 past 45.
         * FactorySpinner2 (p0=2): tips to -90 once stood on, x-1 past -45. */
        if ((int)e->p[0] == 2 && !e->state) {
            int pl, pr, pt, pb;
            iwx_player_rect(env, &pl, &pr, &pt, &pb);
            IWXEnt probe = *e;
            probe.y -= 2;
            if (iwx_hit_rect(xs, &probe, pl, pr, pt, pb)) e->state = 1;
        }
        if ((int)e->p[0] == 1 && e->on && !e->state) e->state = 1;
        if (e->state) {
            if ((int)e->p[0] == 1) {
                e->angle = (float)fmin(90, e->angle * 1.1 + 5);
                if (e->angle > 45) e->y = e->y0 - 1;
            } else {
                e->angle = (float)fmax(-90, e->angle * 1.1 - 5);
                if (e->angle < -45) e->x = e->x0 - 1;
            }
        }
        return;
    }

    case XB_FRSPIKE: {
        /* alarm chain: 50 -> vx=35*sx (200 frames) -> vx=-2.5*sx (250) -> idle */
        if (e->state == 1 && e->t0 > 0 && --e->t0 == 0) {
            e->vx = 35 * (e->xs >= 0 ? 1 : -1);
            e->state = 2; e->t0 = 8 * 25;
        } else if (e->state == 2 && e->t0 > 0 && --e->t0 == 0) {
            e->vx = -2.5f * (e->xs >= 0 ? 1 : -1);
            e->state = 3; e->t0 = 10 * 25;
        } else if (e->state == 3 && e->t0 > 0 && --e->t0 == 0) {
            e->on = 0; e->state = 0;
        }
        float xprev = e->x;
        e->x += e->vx;
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (iwx_marker_hit(xs, XM_FRSW, l, r, t, b)) {
            e->x = xprev;
            e->vx = 0;
            if (!e->on) e->x = e->x0;
        }
        return;
    }

    case XB_FRBARRIER: {
        e->frame += e->fspd;
        const IWXMaskRec* m = iwx_mask(xs, e->mask);
        int nfr = m ? m->nframes : 6;
        if (e->state == 1 && e->frame >= nfr - 1) {
            /* closed: reopen after 10*25 minus the close anim */
            e->frame = (float)(nfr - 1);
            e->fspd = 0;
            e->t0 = 10 * 25 - (int)ceil(nfr / 0.5) - 1;
            e->state = 2;
        } else if (e->state == 2 && e->t0 > 0 && --e->t0 == 0) {
            e->fspd = -0.5f;
            e->state = 3;
        } else if (e->state == 3 && e->frame <= 0) {
            e->frame = 0; e->fspd = 0; e->state = 0;
            e->t1 = 3;                     /* alarm[2]=3 re-arm guard */
        }
        if (e->t1 > 0 && --e->t1 == 0) e->t1 = -1;
        return;
    }

    case XB_SPIKE_EXTEND: {
        if (e->state && e->y - 4 > 0) {
            double target = iwx_median3(e->y, env->y, e->y - 4);
            e->y = (float)target;
        }
        /* growing blockKill shaft below (link) */
        if (e->link >= 0) {
            IWXEnt* k = &xs->ents[e->link];
            k->y = e->y + 32;
            k->ys = (e->y0 - e->y) / 32.0f;
            if (k->ys < 0) k->ys = 0;
            k->alive = k->ys > 0;
        }
        return;
    }

    case XB_REVEALING:
        if (e->state == 1) {
            if (e->t0 > 0 && --e->t0 == 0) e->vy = 4;
            if (e->y + e->vy < e->y0 - 32) { e->y = e->y0 - 32; e->vy = 0; }
            else if (e->y + e->vy > e->y0) { e->y = e->y0; e->vy = 0; e->state = 0; }
            else e->y += e->vy;
        }
        return;

    case XB_SPIKETRAP: {
        /* Step_2: clamp + track sub-colliders; slam via trigger t-code */
        if (e->y > 860) { e->vy = 0; e->y = 860; e->t0 = 250; }
        if (e->t0 > 0 && --e->t0 == 0) e->vy = -1;
        if (e->y < e->y0) { e->vy = 0; e->y = e->y0; }
        e->y += e->vy;
        if (e->link >= 0) {              /* killer face at y+8 */
            xs->ents[e->link].x = e->x;
            xs->ents[e->link].y = e->y + 8;
        }
        return;
    }

    case XB_QUICKLASER:
        if (e->on) {
            e->p[6] += 12.5f;                     /* size += mmf_speed(100) */
            if (e->p[6] > e->p[1] * 32) e->p[6] = e->p[1] * 32;
            e->xs = e->p[6] > 1 ? e->p[6] : 1;    /* image_xscale = size */
        }
        return;

    case XB_QLTIMER: {
        static const int sched[7] = {10, 140, 200, 210, 350, 400, 590};
        if (e->on && e->state < 7) {
            e->t0++;
            if (e->t0 >= sched[e->state]) {
                int want = e->state + 1;          /* c = 1..7 */
                for (int i = 0; i < xs->n_ents; i++) {
                    IWXEnt* q = &xs->ents[i];
                    if (q->alive && q->cls == XB_QUICKLASER &&
                        (int)q->p[0] == want) q->on = 1;
                }
                e->state++;
                if (e->state == 7) e->alive = 0;
            }
        }
        return;
    }

    case XB_KILLPLANE:
        e->x += -35;
        if (e->x < env->x && !e->on) { e->on = 1; xs->pending_kill = 1; }
        return;

    case XB_HIGGER: {
        if (e->on && !e->state) e->state = 1;
        if (e->state) {
            e->p[8] += 0.2f;                       /* a += 0.2 */
            e->p[7] += e->p[8];                    /* angle += a */
            double ang = e->p[7];
            e->x = (float)(e->x0 - 64 * (ang / 90));
            e->xs = (float)(7 + 4 * (ang / 90));
            double h = 264 - 264 * cos(ang * IWX_PI / 180);
            double ysc = (264 - (264 - h)) / 32.0;   /* max(1,264-lengthdir_x) */
            ysc = (264 - 264 * cos(ang * IWX_PI / 180)) / 32.0;
            (void)h;
            e->ys = (float)(ysc < 1.0 / 32 ? 1.0 / 32 : ysc);
            /* source: image_yscale = max(1, 264-lengthdir_x(264,angle))/32
             * lengthdir_x(264,angle) = 264*cos(angle) */
            double raw = 264 - 264 * cos(ang * IWX_PI / 180);
            if (raw < 1) raw = 1;
            e->ys = (float)(raw / 32.0);
            if (ang > 180) { e->alive = 0; return; }
            int pl, pr, pt, pb;
            iwx_player_rect(env, &pl, &pr, &pt, &pb);
            if (iwx_hit_rect(xs, e, pl, pr, pt, pb)) xs->pending_kill = 1;
        }
        return;
    }

    case XB_ERRORTRAP: {
        if (e->t0 == 0) {                          /* just spawned */
            xs->frozen = 1;
            e->p[6] = (float)env->x; e->p[7] = (float)env->y;
            e->x = (float)(xs->view_x + 192 + 209);
            e->y = (float)(xs->view_y + 160 + 132);
            e->p[8] = (float)xs->view_x;
        }
        e->t0++;
        if (e->t0 == 100) xs->frozen = 0;
        if (e->t0 == 165) e->vy = 6.25f;
        if (xs->frozen && e->t0 <= 100) {
            env->x = e->p[6]; env->y = e->p[7];
            env->hspeed = 0; env->vspeed = 0;
        }
        e->y += e->vy;
        if (e->vy != 0) {
            int pl, pr, pt, pb;
            iwx_player_rect(env, &pl, &pr, &pt, &pb);
            if (iwx_hit_rect(xs, e, pl, pr, pt, pb)) xs->pending_kill = 1;
        }
        if (!iwx_ent_in_view(xs, e)) { e->y = -9999; e->vy = 0; }
        if (e->p[8] != (float)xs->view_x) e->alive = 0;
        return;
    }

    case XB_PAINTING: {
        int pl, pr, pt, pb;
        iwx_player_rect(env, &pl, &pr, &pt, &pb);
        if (e->y == e->y0 && e->state == 0) {
            IWXEnt probe = *e;
            probe.y = e->y + 32;
            if (iwx_hit_rect(xs, e, pl, pr, pt, pb) ||
                iwx_hit_rect(xs, &probe, pl, pr, pt, pb))
                e->state = 1;
        }
        if (e->state == 1) {
            e->vy += 1;                             /* gravity = 1 */
            if (e->y + e->vy > e->y0 + 32) {
                e->y = e->y0 + 32; e->state = 0; e->vy = 0;
                if (iwx_hit_rect(xs, e, pl, pr, pt, pb)) xs->pending_kill = 1;
            } else e->y += e->vy;
        }
        return;
    }

    case XB_WHEEL: {
        if (e->on && !e->state) e->state = 1;
        if (e->state) {
            e->vx = 7.5f * (e->xs >= 0 ? 1 : -1);
            e->x += e->vx;
            /* plows through destructible blocks */
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* d = &xs->ents[i];
                if (d->alive && d->cls == XB_DESTRUCTIBLE &&
                    iwx_ents_overlap(xs, e, d))
                    iwx_kill_destructible(env, d, 2, 0);
            }
        }
        return;
    }

    case XB_FLYSPIKE:
        if (e->on && !e->state) e->state = 1;
        if (e->state) { e->y -= 6.25f; if (e->y < 334) e->y = 334; }
        return;

    case XB_GUTSMAN: {
        e->t0--;
        if (e->t0 == 0) {
            xs->frozen = 1;
            e->x = (float)px;
            e->vy = 37.5f;
            e->state = 1;
        }
        if (e->state == 1) {
            e->y += e->vy;
            /* lands on a platform -> crushes the player */
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* p = &xs->ents[i];
                if (p->alive && (p->flags & XEF_PLATFORM) &&
                    iwx_ents_overlap(xs, e, p)) {
                    xs->pending_kill = 1;
                    e->vy = 0; e->state = 2;
                    break;
                }
            }
            if (e->y > env->room_ph + 64) e->alive = 0;
        }
        return;
    }

    case XB_COUCH:
        return;                          /* handled in the contact pass */

    case XB_HAMMER: {
        e->y += e->vy;
        if (e->vy > 0) {
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            IWXEnt* n = iwx_marker_hit(xs, XM_BLOCKNISE, l, r, t, b);
            if (n) {                     /* lands: becomes a solid block */
                e->y = n->y - 129;
                e->vy = 0;
                e->flags |= XEF_SOLID;
                e->flags &= ~XEF_KILLER;
                e->cls = XB_TETBLOCK;    /* inert dynamic solid from now on */
            }
        }
        return;
    }

    case XB_SPIKESHOOT: {
        if (e->state == 1) {             /* shot: spiral to rest position */
            e->p[8] += 1.0f / 21;
            if (e->p[8] > 1) e->p[8] = 1;
            float f = e->p[8];
            e->x = e->x0 + (2496 - e->x0) * f;
            e->y = e->y0 + (2367 - e->y0) * f;
            if (f >= 1) {
                e->state = 2;
                e->flags &= ~XEF_KILLER;
                e->flags |= XEF_PLATFORM;      /* becomes a platform */
                /* start the RealYoku controller */
                for (int i = 0; i < xs->n_ents; i++)
                    if (xs->ents[i].alive && xs->ents[i].cls == XB_REALYOKUCTL)
                        xs->ents[i].on = 1;
            }
        } else if (e->state == 0) {
            e->t0++;
            e->y = e->y0 + ((e->t0 % 2) ? 1 : -1);
        }
        return;
    }

    case XB_MEDUSA: {
        /* alarms: dir flip every 50, spd+1 every 5; y += spd*dir manual */
        if (--e->t0 <= 0) { e->t0 = 50; e->state = -e->state ? 0 : 0;
            e->p[8] = 0; e->p[7] = -(e->p[7] ? e->p[7] : 1); }
        if (e->p[7] == 0) e->p[7] = 1;
        if (--e->t1 <= 0) { e->t1 = 5; e->p[8] += 1; }
        e->y += e->p[8] * e->p[7];
        e->x += e->vx;
        /* MedusaModifier: recycle or despawn */
        {
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (iwx_marker_hit(xs, XM_MEDUSAMOD, l, r, t, b)) {
                if (px < e->x) { e->vx = -1.875f; e->x -= 80; }
                else e->alive = 0;
            }
        }
        if (e->x < -96 || e->x > env->room_pw + 96) e->alive = 0;
        return;
    }

    case XB_MEDUSAMAKER: {
        /* sampled relative path at keys[p1..]; every 100 frames spawn */
        int n = (int)e->p[2];
        if (n > 0) {
            int k = e->t1 % n;
            const float* base = xs->keys + (int)e->p[1];
            e->x = e->x0 + base[k * 2];
            e->y = e->y0 + base[k * 2 + 1];
            e->t1++;
        }
        if (--e->t0 <= 0) {
            e->t0 = 100;
            if (xs->view_y < e->y) {
                IWXEnt* m = iwx_spawn(env, (int)e->p[3], e->x + 16, e->y + 16);
                if (m) { m->vx = e->p[0] * 3.75f; m->p[7] = 1; m->t0 = 50; m->t1 = 5; }
            }
        }
        return;
    }

    case XB_BIRD: {
        if (--e->t0 <= 0) {
            e->t0 = 10;
            iwx_aim(&e->vx, &e->vy, px - e->x, py - e->y, 7.5);
        }
        e->x += e->vx; e->y += e->vy;
        if (e->x < -64 || e->x > env->room_pw + 64 ||
            e->y < -64 || e->y > env->room_ph + 64) e->alive = 0;
        return;
    }

    case XB_GHOUL: {
        if (e->state == 0) {             /* emerge shake, 31 frames */
            e->t0++;
            if (e->t0 >= 31) { e->state = 1; e->t0 = 0; e->frame = 0; }
        } else if (e->state == 1) {      /* rising anim at 0.2 */
            e->frame += 0.2f;
            if (e->frame >= 4) {
                e->state = 2;
                e->t0 = (int)(iw_rand(env) % 51);   /* irandom(50) */
                e->vx = 2.0f * (e->xs >= 0 ? 1 : -1);
                e->hp = 4;
            }
        } else if (e->state == 2) {      /* walking, killer */
            int il, ir, it, ib;
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            il = (int)ceil(l); ir = (int)floor(r);
            it = (int)ceil(t); ib = (int)floor(b);
            if (!iwx_rect_free(env, (int)(il + e->vx), (int)(ir + e->vx), it, ib))
                e->vx = -e->vx;
            e->x += e->vx;
            e->t0++;
            if (e->t0 >= 600) { e->state = 3; e->vx = 0; }
        } else {                         /* sink away */
            e->frame -= 0.2f;
            if (e->frame < 0) e->alive = 0;
        }
        return;
    }

    case XB_GHOULGEN: {
        int il = (int)e->x - 8, ir = (int)e->x + 8;
        if (!iwx_rect_free(env, (int)(il + e->vx), (int)(ir + e->vx),
                           (int)e->y - 8, (int)e->y + 8))
            e->vx = -e->vx;
        /* inside_active freeze */
        int inside = e->x >= xs->view_x - 792 && e->x < xs->view_x + 1592 &&
                     e->y >= xs->view_y - 600 && e->y < xs->view_y + 1208;
        if (inside) e->x += e->vx;
        if (--e->t0 <= 0) {
            e->t0 = 175;
            if (inside) {
                IWXEnt* g = iwx_spawn(env, (int)e->p[0], e->x + 16, e->y);
                if (g) g->xs = (iw_rand(env) & 1) ? 1 : -1;
            }
        }
        return;
    }

    case XB_HOVERGUNNER: {
        if (e->p[0] > 0) {               /* go: drop in 637px at 1.75 */
            e->y += 1.75f;
            if (e->y >= e->y0 + 637) { e->y = e->y0 + 637; e->p[0] = 0; }
        }
        if (--e->t0 <= 0) {
            e->t0 = 90;
            if (iwx_ent_in_view(xs, e) && e->p[0] == 0) {
                static const float sp[4] = {3.75f, 6.25f, 8.75f, 10.625f};
                for (int k = 0; k < 4; k++) {
                    IWXEnt* s = iwx_spawn(env, (int)e->p[1],
                                          e->x + 16, e->y + 10);
                    if (s) iwx_aim32(&s->vx, &s->vy,
                                     px - e->x, py - e->y, sp[k]);
                }
            }
        }
        return;
    }

    case XB_HOVERSHOT: case XB_SPAG: {
        e->x += e->vx; e->y += e->vy;
        int il = (int)e->x - 3, ir = (int)e->x + 3;
        int it = (int)e->y - 3, ib = (int)e->y + 3;
        if (e->cls == XB_HOVERSHOT && !iwx_rect_free(env, il, ir, it, ib))
            e->alive = 0;
        if (e->cls == XB_SPAG && !iwx_ent_in_view(xs, e)) e->alive = 0;
        if (e->x < -64 || e->x > env->room_pw + 64 ||
            e->y < -64 || e->y > env->room_ph + 64) e->alive = 0;
        return;
    }

    case XB_SNIPER: {
        if (e->state == 2) return;       /* dead */
        if (e->on && e->state == 0) { e->t0 = 75; e->state = 1; }
        if (e->state == 1) {
            if (e->t0 > 0) {
                e->t0--;
                if (e->t0 == 0 && iwx_ent_in_view(xs, e)) {
                    /* fire 4 shots aimed at (global.px, global.py-5) */
                    static const float sp[4] = {3.75f, 6.25f, 8.75f, 10.625f};
                    for (int k = 0; k < 4; k++) {
                        IWXEnt* s = iwx_spawn(env, (int)e->p[1], e->x, e->y);
                        if (s) iwx_aim(&s->vx, &s->vy,
                                       px - e->x, (py - 5) - e->y, sp[k]);
                    }
                    e->t0 = 75;
                }
            }
        }
        return;
    }

    case XB_TOURTURRET: {
        if (!e->on) { if (iwx_ent_in_view(xs, e)) e->on = 1; else return; }
        e->t0++;
        if (e->t0 == 80) {
            double deg = e->p[8];
            IWXEnt* s = iwx_spawn(env, (int)e->p[1],
                                  e->x + (float)(28 * cos(deg * IWX_PI / 180)),
                                  e->y - (float)(28 * sin(deg * IWX_PI / 180)));
            if (s) {
                s->vx = (float)(6.25 * cos(deg * IWX_PI / 180));
                s->vy = (float)(-6.25 * sin(deg * IWX_PI / 180));
            }
        }
        if (e->t0 >= 140) {
            double deg;
            float vx, vy;
            iwx_aim45(&vx, &vy, px - e->x, py - e->y, 1, &deg);
            e->p[8] = (float)deg;
            e->t0 = 0;
        }
        return;
    }

    case XB_SKWEE: {
        if (e->on && e->state == 0) {
            e->state = 1;
            double dir = (e->x > px) ? 247.5 : 292.5;
            e->vx = (float)(5 * cos(dir * IWX_PI / 180));
            e->vy = (float)(-5 * sin(dir * IWX_PI / 180));
        }
        if (e->state == 1) {
            e->x += e->vx; e->y += e->vy;
            int il = (int)e->x - 8, ir = (int)e->x + 8;
            int it = (int)e->y - 8, ib = (int)e->y + 8;
            if (!iwx_rect_free(env, il, ir, it, ib)) {
                e->state = 2; e->vx = e->vy = 0; e->t0 = 30;
            }
        } else if (e->state == 2) {
            if (--e->t0 <= 0) { e->alive = 0; }
        }
        return;
    }

    case XB_CRAWLER: {
        /* edge-follow: probe a 32x32 box ahead-around the corner */
        double dir = e->p[8];            /* degrees */
        double xn = e->x + 9 * cos(dir * IWX_PI / 180)
                        - 9 * sin(dir * IWX_PI / 180);
        double yn = e->y - 9 * sin(dir * IWX_PI / 180)
                        - 9 * cos(dir * IWX_PI / 180);
        /* lengthdir(9,dir) + lengthdir(9,dir+90):
         * x: 9cos(d) + 9cos(d+90) = 9cos - 9sin
         * y: -9sin(d) - 9sin(d+90) = -9sin - 9cos */
        int free1 = iwx_rect_free(env, (int)xn - 16, (int)xn + 15,
                                  (int)yn - 16, (int)yn + 15);
        if (free1) { e->p[8] = (float)(dir + 90); e->x = (float)xn; e->y = (float)yn; }
        dir = e->p[8];
        double vx = 1 * cos(dir * IWX_PI / 180);
        double vy = -1 * sin(dir * IWX_PI / 180);
        if (!iwx_rect_free(env, (int)(e->x + vx) - 16, (int)(e->x + vx) + 15,
                           (int)(e->y + vy) - 16, (int)(e->y + vy) + 15))
            e->p[8] = (float)(dir - 90);
        dir = e->p[8];
        e->vx = (float)(1 * cos(dir * IWX_PI / 180));
        e->vy = (float)(-1 * sin(dir * IWX_PI / 180));
        e->x += e->vx; e->y += e->vy;
        e->angle = -(float)dir - 90;     /* mask rotation follows */
        {
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (iwx_marker_hit(xs, XM_BLOCKNISE, l, r, t, b)) e->alive = 0;
        }
        return;
    }

    case XB_DUMBBUGZ:
        iwx_aim(&e->vx, &e->vy, px - e->x, py - e->y, 6.25);
        e->x += e->vx; e->y += e->vy;
        return;

    case XB_METROID: {
        double speed = e->state == 0 ? 12.5 : 6.25;
        if (e->state == 1) {
            e->t0++;
            if (e->t0 >= 100) {          /* latch: hidden+frozen forever */
                xs->frozen = 1;
                xs->pending_kill = 1;    /* modeled as death (documented) */
                e->state = 2;
            }
        }
        if (e->state <= 1) {
            iwx_aim(&e->vx, &e->vy, px - e->x, py - e->y, speed);
            e->x += e->vx; e->y += e->vy;
        }
        return;
    }

    case XB_METROIDTRAP:
        return;                          /* touch handled in contact pass */

    case XB_SPAGDISP:
        if (!e->on) { if (iwx_ent_in_view(xs, e)) e->on = 1; return; }
        e->t0++;
        if (e->t0 >= 220) {
            e->t0 = 0;
            IWXEnt* s = iwx_spawn(env, (int)e->p[0], e->x, e->y);
            if (s) iwx_aim(&s->vx, &s->vy, px - e->x, py - e->y, 1.25);
        }
        return;

    case XB_ROLLROCK: {
        if (e->vy == 0) {
            int below_free = iwx_rect_free(env, (int)e->x - 14, (int)e->x + 13,
                                           (int)e->y + 16, (int)e->y + 47);
            if (below_free) {
                e->x = (float)(floor(e->x / 32) * 32 + 16);
                e->vx = 0; e->vy = 3.75f;
            }
        } else {
            if (!iwx_rect_free(env, (int)e->x - 14, (int)e->x + 13,
                               (int)(e->y + e->vy) - 14, (int)(e->y + e->vy) + 15)) {
                e->y = (float)(floor(e->y / 32) * 32 + 16);
                e->vy = 0;
                /* roll direction rule (source) */
                int spike_right = 0;
                for (int i = 0; i < env->n_killers; i++) {
                    const IWPackKiller* k = &env->killers[i];
                    if (k->shape == IWPACK_KILL_SPIKE_UP &&
                        e->x + 16 >= k->x0 && e->x + 16 <= k->x1 &&
                        e->y >= k->y0 - 24 && e->y <= k->y1 + 24)
                        { spike_right = 1; break; }
                }
                int block_left = !iwx_rect_free(env, (int)e->x - 32, (int)e->x - 32,
                                                (int)e->y, (int)e->y);
                int block_right = !iwx_rect_free(env, (int)e->x + 32, (int)e->x + 32,
                                                 (int)e->y, (int)e->y);
                if ((spike_right && !block_left) || block_right)
                    e->vx = -1.875f;
                else e->vx = 1.875f;
            } else e->y += e->vy;
        }
        e->x += e->vx;
        {
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (iwx_marker_hit(xs, XM_BLOCKNISE, l, r, t, b)) e->alive = 0;
        }
        e->angle -= 45 * 0.5f * (e->vx != 0 ? (e->vx > 0 ? 1 : -1) : 1);
        return;
    }

    case XB_WATCHFOR:
        if (--e->t0 <= 0) {
            e->t0 = 200;
            iwx_spawn(env, (int)e->p[0], e->x + 16, e->y + 16);
        }
        return;

    case XB_PLAYSTATION:
        e->angle += 45 / 0.5f * 0;       /* rotation is cosmetic here */
        iwx_aim(&e->vx, &e->vy, px - e->x, py - e->y, 7.5);
        e->x += e->vx; e->y += e->vy;
        return;

    case XB_KAMEK: {
        if (e->state == 0) {
            if (iwx_ent_in_view(xs, e)) e->state = 1;
        } else if (e->state == 1) {
            e->p[8] += 0.25f;
            if (e->p[8] >= 7) e->state = 2;
        } else if (e->state == 2) {
            e->t0++;
            if (e->t0 > 28) {
                e->state = 3; e->t0 = 0;
                iwx_spawn(env, (int)e->p[0], e->x, e->y);
            }
        } else if (e->state == 3) {
            e->t0++;
            if (e->t0 == 32) e->state = 4;
        } else if (e->state == 4) {
            e->p[8] -= 0.25f;
            if (e->p[8] <= 0) e->alive = 0;
        }
        return;
    }

    case XB_EGGPLANT: {
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (iwx_marker_hit(xs, XM_BOUNCE_DOWN, l, r, t, b))
            e->vy = (float)fabs(e->vy);
        if (iwx_marker_hit(xs, XM_BOUNCE_UP, l, r, t, b))
            e->vy = -(float)fabs(e->vy);
        e->y += e->vy;
        return;
    }

    case XB_BOUNCYFRUIT: {
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        double sp = sqrt(e->vx * e->vx + e->vy * e->vy);
        if (iwx_marker_hit(xs, XM_BOUNCE_DOWN, l, r, t, b)) { e->vx = 0; e->vy = (float)sp; }
        if (iwx_marker_hit(xs, XM_BOUNCE_UP, l, r, t, b))   { e->vx = 0; e->vy = -(float)sp; }
        if (iwx_marker_hit(xs, XM_BOUNCE_LEFT, l, r, t, b)) { e->vx = -(float)sp; e->vy = 0; }
        if (iwx_marker_hit(xs, XM_BOUNCE_RIGHT, l, r, t, b)){ e->vx = (float)sp; e->vy = 0; }
        e->x += e->vx; e->y += e->vy;
        return;
    }

    case XB_WITCHSHADOW: {
        /* ping-pong along sampled key leg */
        int n = (int)e->p[2];
        if (n > 1) {
            int cyc = 2 * (n - 1);
            int k = e->t0 % cyc;
            if (k >= n) k = cyc - k;
            const float* base = xs->keys + (int)e->p[1];
            e->x = base[k * 2];
            e->y = base[k * 2 + 1];
            e->t0++;
        }
        return;
    }

    case XB_WITCH: {
        if (e->on) e->t1 = 1;            /* valid latches once triggered */
        if (e->state == 0) {
            if (e->on) {
                /* strike only when no shadow overlaps a blockNise */
                int blocked = 0;
                for (int i = 0; i < xs->n_ents; i++) {
                    IWXEnt* s = &xs->ents[i];
                    if (!s->alive || s->cls != XB_WITCHSHADOW) continue;
                    double l, r, t, b;
                    iwx_ent_bbox(xs, s, &l, &r, &t, &b);
                    if (iwx_marker_hit(xs, XM_BLOCKNISE, l, r, t, b))
                        { blocked = 1; break; }
                }
                if (!blocked) {
                    for (int i = 0; i < xs->n_ents; i++)
                        if (xs->ents[i].cls == XB_WITCHSHADOW)
                            xs->ents[i].alive = 0;
                    e->state = 1;
                    e->vx = 6.25f;
                    e->y = e->y0;
                }
            }
        } else if (e->state == 1) {
            e->x += e->vx;
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (iwx_marker_hit(xs, XM_BLOCKNISE, l, r, t, b)) {
                e->state = 2; e->vx = 0; e->vy = 7.5f;
            }
            if (e->x > env->room_pw + 64) e->alive = 0;
        } else {
            e->angle -= 20;
            e->y += e->vy;
            if (e->y > env->room_ph + 64) e->alive = 0;
        }
        return;
    }

    case XB_LONK: {
        if (e->x > 658) e->vx = -(float)fabs(e->vx);
        if (e->x < 140) e->vx = (float)fabs(e->vx);
        e->x += e->vx;
        e->xs = 5.0f * (e->vx >= 0 ? 1 : -1);
        /* attached platform: pinned each frame; carry the rider here */
        if (e->link >= 0) {
            IWXEnt* p = &xs->ents[e->link];
            p->vx = 0;
            p->x = e->x - 37;
            p->y = e->y;
            int pl, pr, pt, pb;
            iwx_player_rect(env, &pl, &pr, &pt, &pb);
            double l2, r2, t2, b2;
            iwx_ent_bbox(xs, p, &l2, &r2, &t2, &b2);
            if (pr >= l2 && pl <= r2 && pb >= t2 - 2 && pt <= b2 - 2) {
                if (place_free(env, env->x + e->vx, env->y))
                    env->x += e->vx;
            }
        }
        if (e->on && e->state == 0) { e->on = 0; e->state = 12; }
        if (e->state > 0) {
            int pl, pr, pt, pb;
            iwx_player_rect(env, &pl, &pr, &pt, &pb);
            /* slash mask: 16x28 rect at origin (8,12), scale 5 */
            double sl = e->x - 8 * 5, sr = e->x + 8 * 5 - 1;
            double st = e->y - 12 * 5, sb = e->y + 16 * 5 - 1;
            if (pr >= sl && pl <= sr && pb >= st && pt <= sb)
                xs->pending_kill = 1;
            e->state--;
        }
        return;
    }

    case XB_CHEEP: {
        if (e->t0 > 0 && --e->t0 == 0) {
            e->state = 1;
            double dir = 135.0;          /* mmf_direction(12) */
            e->vx = (float)(7.5 * cos(dir * IWX_PI / 180));
            e->vy = (float)(-7.5 * sin(dir * IWX_PI / 180));
            e->p[8] = (float)dir;
            e->t1 = 0;
        }
        if (e->state == 1) {
            e->t1++;
            if (e->t1 > 5) {
                e->t1 = 0;
                e->p[8] += 11.25f;
                double sp = sqrt(e->vx * e->vx + e->vy * e->vy);
                e->vx = (float)(sp * cos(e->p[8] * IWX_PI / 180));
                e->vy = (float)(-sp * sin(e->p[8] * IWX_PI / 180));
            }
        } else if (e->state == 2) {      /* shot: plummet */
            e->vx = 0; e->vy = 7.5f;
        }
        e->x += e->vx; e->y += e->vy;
        if (env->x > 8128) e->alive = 0;
        if (e->y > env->room_ph + 96) e->alive = 0;
        return;
    }

    case XB_CHEEPCTL:
        if (env->x > 8128) {
            for (int i = 0; i < xs->n_ents; i++)
                if (xs->ents[i].cls == XB_CHEEP) xs->ents[i].alive = 0;
            e->alive = 0;
        }
        return;

    case XB_BULLETBILL:
        e->x += e->vx;
        if (e->x < xs->view_x - 900) e->alive = 0;
        return;

    case XB_MOVPLAT:
        iwx_platform_step(env, e);
        return;

    case XB_FALLPLAT: {
        /* p0 shake frames, p1 fall vspeed, p2 up(-1)/down(+1),
         * p3 solid-until-stood (FallingFort), p4 crash-flash,
         * p5 despawn-outside-view (FactoryPlatform) */
        int pl, pr, pt, pb;
        iwx_player_rect(env, &pl, &pr, &pt, &pb);
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        int stood = xs->on_platform &&
                    pr >= l && pl <= r && pb >= t - 2 && pt <= b - 2;
        if (!e->state && stood) {
            e->state = 1;
            if (e->p[3] != 0 && e->link >= 0) {  /* FallingFort solid */
                xs->ents[e->link].alive = 0;
                env->y += 2;
            }
        }
        if (e->state) {
            e->t0++;
            if (e->t0 <= (int)e->p[0]) {
                e->x = e->x0 + ((e->t0 % 2) ? 1 : 0);
            } else {
                if (e->p[2] < 0) e->p[9] = -e->p[1];    /* rise via yspeed */
                else {
                    if (e->vy == 0) env->y += (stood ? e->p[1] : 0);
                    e->vy = e->p[1];
                }
            }
            if (e->p[4] != 0) {                          /* crash on landing */
                int il = (int)ceil(l), ir2 = (int)floor(r);
                int it = (int)ceil(t), ib = (int)floor(b);
                if (!iwx_rect_free(env, il, ir2, it, ib) && e->t1 == 0)
                    e->t1 = 25;
            }
            if (e->t1 > 0 && --e->t1 == 0) { e->alive = 0; return; }
            if (e->p[5] != 0 &&
                (e->y > xs->view_y + 608 || e->y < xs->view_y - 32)) {
                e->alive = 0; return;
            }
        }
        iwx_platform_step(env, e);
        return;
    }

    case XB_METROIDPLAT: {
        int pl, pr, pt, pb;
        iwx_player_rect(env, &pl, &pr, &pt, &pb);
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        int stood = xs->on_platform &&
                    pr >= l && pl <= r && pb >= t - 2 && pt <= b - 2;
        if (stood && e->vy == 0) { e->vy = 2; env->y += 2; }
        iwx_platform_step(env, e);
        return;
    }

    case XB_ASCENT: {
        int pl, pr, pt, pb;
        iwx_player_rect(env, &pl, &pr, &pt, &pb);
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (!e->state && xs->on_platform &&
            pr >= l && pl <= r && pb >= t - 2 && pt <= b - 2) {
            e->state = 1; e->vy = -1;
        }
        iwx_platform_step(env, e);
        return;
    }

    case XB_KUMO: {
        if (!e->on) e->vy = -(float)iw_sign(e->y - e->y0);
        /* attached collider handled through this entity's own platform flag */
        iwx_platform_step(env, e);
        {
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (iwx_marker_hit(xs, XM_KUMOSTOP, l, r, t, b)) { e->vx = 0; e->vy = 0; }
        }
        return;
    }

    case XB_GUYPLAT: {
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        if (iwx_marker_hit(xs, XM_BLOCKNISE, l, r, t, b)) {
            if (e->y > 1500) e->y = 1240; else e->y = 1792;
        }
        iwx_platform_step(env, e);
        return;
    }

    case XB_PILLAR: {
        if (e->on) e->state = 1;
        if (e->state) {
            e->p[8] += 0.3f / 6;
            if (e->p[8] > 1) e->p[8] = 1;
        }
        float f2 = e->p[8] * e->p[8];
        if (e->link >= 0) {
            IWXEnt* a = &xs->ents[e->link];
            a->x = e->x + 96 + (e->x + 8 - (e->x + 96)) * f2;
        }
        return;
    }

    case XB_HILL:
        if (e->on && e->state == 0) { e->state = 1; e->vy = -1.875f; }
        if (e->y + e->vy <= e->y0 - 32) { e->y = e->y0 - 32; e->vy = 0; }
        else e->y += e->vy;
        return;

    case XB_CART: {
        if (e->state == 3) { e->p[9] = 0; return; }   /* crashed */
        double l = e->x, r = e->x + 106 - 1, t = e->y, b = e->y + 32 - 1;
        /* state machine over DumpMoment regions */
        int on_dump = iwx_marker_hit(xs, XM_DUMP, l, r, t, b) != NULL;
        if (e->state == 0) {
            e->frame += 0.5f; if (e->frame >= 2) e->frame = 0;
            if (on_dump) { e->state = 1; e->frame = 2; }
            e->p[9] = 1;                 /* platform present */
        }
        if (e->state == 1) {
            e->frame += 0.1f; if (e->frame >= 7) e->frame = 5;
            if (!on_dump) { e->state = 2; e->frame = 5; }
            if (e->frame > 4) e->p[9] = 0;
        }
        if (e->state == 2) {
            e->frame -= 0.5f;
            if (e->frame < 2) { e->frame = 0; e->state = 0; }
        }
        /* rising player: re-cart + hide the platform */
        if (env->vspeed < 0) {
            int pl, pr, pt, pb;
            iwx_player_rect(env, &pl, &pr, &pt, &pb);
            if (pr >= l && pl <= r && pb >= t && pt <= b &&
                e->p[9] > 0 && xs->walljumpboost == 0)
                xs->carted = 1;
            e->p[9] = 0;
        }
        /* fast cart clamps the rider into the seat */
        if (e->vx > 5) {
            int pl, pr, pt, pb;
            int iy = gm_round(env->y);
            int pl2, pr2;
            iwx_player_rect(env, &pl, &pr, &pt, &pb);
            pl2 = pl; pr2 = pr;
            (void)pl2; (void)pr2; (void)iy;
            if (pr >= l && pl <= r && pb + 2 >= t && pt + 2 <= b) {
                double nx = env->x - 3;
                if (nx < e->x + 34) nx = e->x + 34;
                env->x = nx;
                env->y = e->y - 9;
                env->hspeed = 0; env->vspeed = 0;
                env->djump = IW_MAXJUMPS;      /* djump=0 in the source */
            }
        }
        /* pickups / bullet trigger / crash markers / destructible columns */
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* m = &xs->ents[i];
            if (!m->alive) continue;
            if (m->cls == XB_CARTPICKUP) {
                double ml, mr, mt, mb;
                iwx_ent_bbox(xs, m, &ml, &mr, &mt, &mb);
                if (mr >= l && ml <= r && mb >= t && mt <= b) {
                    e->vx += 1; m->alive = 0;
                }
            } else if (m->cls == XB_MARKER &&
                       (int)m->p[0] == XM_BULLETTRIGGER) {
                double ml, mr, mt, mb;
                iwx_ent_bbox(xs, m, &ml, &mr, &mt, &mb);
                if (mr >= l && ml <= r && mb >= t && mt <= b) {
                    m->alive = 0;
                    for (int k = 0; k < xs->n_ents; k++)
                        if (xs->ents[k].cls == XB_BULLETBILL)
                            xs->ents[k].vx = -1.25f;
                }
            } else if (m->cls == XB_MARKER && (int)m->p[0] == XM_BLOCKNISE) {
                double ml, mr, mt, mb;
                iwx_ent_bbox(xs, m, &ml, &mr, &mt, &mb);
                if (mr >= l && ml <= r && mb >= t && mt <= b && !e->on) {
                    /* CRASH */
                    iwx_ent_event(env, e);
                    env->x = m->x + 16;
                    env->y = m->y - 20;
                    xs->walljumpboost = -1;
                    xs->walljumpdir = 1;
                    env->hspeed = 15;
                    env->vspeed = -10;
                    env->djump = 1;
                    xs->carted = 0;
                    return;
                }
            } else if (m->cls == XB_DESTRUCTIBLE) {
                double ml, mr, mt, mb;
                iwx_ent_bbox(xs, m, &ml, &mr, &mt, &mb);
                if (mr >= l && ml <= r && mb >= t && mt <= b)
                    iwx_kill_destructible(env, m, 1.5f, -1);
            }
        }
        /* carry (like a platform at (x, y+4), 106 wide) */
        if (xs->carted) env->x += e->vx;
        e->x += e->vx;
        return;
    }

    case XB_FACTORYCTL: {
        /* pointer over the compiled chain (member indices at keys[p1..]) */
        int n = (int)e->p[2];
        if (n <= 0) return;
        const float* chain = xs->keys + (int)e->p[1];
        double before = e->p[8];
        e->p[8] += e->p[7];              /* blk += blk_spd */
        int now_i = (int)floor(before), next_i = (int)floor(e->p[8]);
        if (next_i != now_i) {
            e->p[8] = (float)next_i;
            if (next_i < n) {
                IWXEnt* nb = &xs->ents[(int)chain[next_i]];
                nb->fspd = -0.5f;        /* appear */
            } else if (now_i < n) {
                IWXEnt* ob = &xs->ents[(int)chain[now_i]];
                ob->fspd = 0.5f;         /* disappear */
            }
        }
        return;
    }

    case XB_FACTORYBLOCK: {
        e->frame += e->fspd;
        const IWXMaskRec* m = iwx_mask(xs, e->mask);
        int n = m ? m->nframes : 7;
        if (e->frame >= n) { e->frame = (float)(n - 1); e->fspd = 0; }
        if (e->frame < 0) {
            e->frame = 0;
            /* previous chain member starts disappearing */
            if (e->link >= 0) xs->ents[e->link].fspd = 0.5f;
            e->fspd = 0;
        }
        return;
    }

    case XB_REALYOKUCTL: {
        /* sequence "012345" @ 100-frame alarms (RealYokuController.gml) */
        if (!e->on) return;
        if (e->t0 == 0) e->t0 = 100;
        if (--e->t0 == 0) {
            e->t0 = 100;
            int blok = e->state % 6;
            e->state++;
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* b2 = &xs->ents[i];
                if (b2->alive && b2->cls == XB_REALYOKU &&
                    (int)b2->p[0] == blok)
                    iwx_ent_event(env, b2);
            }
        }
        return;
    }

    case XB_REALYOKU: {
        e->frame += e->fspd;
        if (e->t0 > 0 && --e->t0 == 0) {
            const IWXMaskRec* m = iwx_mask(xs, e->mask);
            int nfr = m ? m->nframes : 4;
            e->frame = e->fspd > 0 ? (float)(nfr - 1) : 0;
            e->fspd = 0;
        }
        if (e->t1 > 0 && --e->t1 == 0) {   /* auto-hide 100 frames later */
            e->fspd = -0.5f;
            e->t0 = (int)(e->frame / 0.5);
        }
        return;
    }

    case XB_TETRIS: {
        /* compiled timeline: keys[p1..] = (frame, op, a, b) quads, p2 = n.
         * abort when the controller leaves the view. */
        if (!iwx_ent_in_view(xs, e)) {
            if (e->t0 > 0) iwx_spawn(env, (int)e->p[3], 763, 64);
            e->alive = 0;
            return;
        }
        int n = (int)e->p[2];
        const float* tl = xs->keys + (int)e->p[1];
        while (e->state < n && (int)tl[e->state * 4] <= e->t0) {
            int op = (int)tl[e->state * 4 + 1];
            float a = tl[e->state * 4 + 2], b = tl[e->state * 4 + 3];
            if (op == 0) {               /* set block a -> (alive at x=?,y=b) */
                int bi = (int)a;
                if (bi >= 0 && bi < xs->cap) xs->ents[bi].alive = 1;
            } else if (op == 1) {        /* kill block a */
                int bi = (int)a;
                if (bi >= 0 && bi < xs->cap) xs->ents[bi].alive = 0;
            } else if (op == 2) {        /* move block a to (b_x=b, keep y?) */
                int bi = (int)a;
                if (bi >= 0 && bi < xs->cap) xs->ents[bi].x = b;
            } else if (op == 3) {        /* move block a vertical */
                int bi = (int)a;
                if (bi >= 0 && bi < xs->cap) xs->ents[bi].y = b;
            } else if (op == 4) {        /* spawn KillPill template a */
                iwx_spawn(env, (int)a, 375, -100);
            }
            e->state++;
        }
        e->t0++;
        if (e->state >= n) e->alive = 0;
        return;
    }

    case XB_KILLPILL: {
        /* falls 12.5; smashes tetrisBlocks; parks on static solids */
        double l, r, t, b;
        iwx_ent_bbox(xs, e, &l, &r, &t, &b);
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* tb = &xs->ents[i];
            if (tb->alive && tb->cls == XB_TETBLOCK &&
                iwx_ents_overlap(xs, e, tb)) tb->alive = 0;
        }
        if (t > 0 && e->vy > 0) {
            if (rect_hits_solid(env, (int)ceil(l), (int)floor(r),
                                (int)(t + e->vy), (int)(b + e->vy))) {
                while (!rect_hits_solid(env, (int)ceil(l), (int)floor(r),
                                        (int)t + 1, (int)b + 1)) {
                    e->y += 1; t += 1; b += 1;
                }
                e->vy = 0;
            }
        }
        e->y += e->vy;
        return;
    }

    case XB_BUTTON:
        if (e->t0 > 0) e->t0--;
        return;

    case XB_SHOOTBARRIER: case XB_NATSCAT: case XB_CHOZO:
    case XB_DESTRUCTIBLE: case XB_TOURIANBARRIER:
        if (e->cls == XB_TOURIANBARRIER) {
            if (iwx_flag_bit(env, (int)e->p[0]) && e->frame > 0) {
                e->frame -= 0.25f;
                if (e->frame < 0) e->frame = 0;
            } else if (!iwx_flag_bit(env, (int)e->p[0])) {
                const IWXMaskRec* m = iwx_mask(xs, e->mask);
                e->frame = m ? (float)(m->nframes - 1) : e->frame;
            }
        }
        return;

    case XB_BOOM: {
        e->frame += 0.5f;
        const IWXMaskRec* m = iwx_mask(xs, e->mask);
        if (m && e->frame >= m->nframes) e->alive = 0;
        return;
    }

    case XB_TRIGGER: {
        if (e->t0 > 0 && --e->t0 == 0) {
            e->on = 0;                    /* Alarm_0: active=0 (+ target) */
            int tgt = (int)e->p[3];
            if (tgt >= 0 && tgt < xs->cap) xs->ents[tgt].on = 0;
            else if (tgt <= IWX_TGT_CLS0) {
                int cls = IWX_TGT_CLS0 - tgt;
                for (int k = 0; k < xs->n_ents; k++)
                    if (xs->ents[k].cls == cls) xs->ents[k].on = 0;
            }
        }
        return;
    }

    case XB_FRUIT: {
        /* source cherry delay: moves on the 1st frame, the 2nd frame's
         * movement is undone (Step_2 x-=hspeed at delay==1), then free */
        if (e->state == 2) { e->x += e->vx; e->y += e->vy; e->state = 1; }
        else if (e->state == 1) { e->state = 3; }
        else if (e->state == 3) { e->x += e->vx; e->y += e->vy; }
        if (e->y < -80 || e->y > env->room_ph + 80 ||
            e->x < -80 || e->x > env->room_pw + 80) e->alive = 0;
        return;
    }

    case XB_CATTHING: {
        if (e->on && e->state == 0) e->state = 1;
        if (e->state == 1) {
            e->frame += 0.2f;
            if (e->frame >= 5 && !e->t1) {
                e->t1 = 1;
                IWXEnt* f = iwx_spawn(env, (int)e->p[0], e->x + 31, e->y + 44);
                if (f) { f->vy = 3.75f; f->state = 3; }
            }
            const IWXMaskRec* m = iwx_mask(xs, e->mask);
            if (m && e->frame >= m->nframes) e->alive = 0;
        }
        return;
    }

    case XB_FIRECHALICE: {
        e->y += e->vy;
        if (env->x > 800) { iwx_ent_event(env, e); e->alive = 0; return; }
        if (e->vy > 0) {
            double l, r, t, b;
            iwx_ent_bbox(xs, e, &l, &r, &t, &b);
            if (rect_hits_solid(env, (int)ceil(l), (int)floor(r),
                                (int)ceil(t), (int)floor(b))) {
                iwx_ent_event(env, e);
                e->alive = 0;
            }
        }
        return;
    }

    case XB_RYU: {
        /* keys[p1..] leg1 (n = p2), reversed slower descent after */
        if (e->on && e->state == 0) { e->state = 1; e->t0 = 0; }
        int n = (int)e->p[2];
        const float* leg = xs->keys + (int)e->p[1];
        if (e->state == 1) {
            if (e->t0 < n) {
                e->x = leg[e->t0 * 2]; e->y = leg[e->t0 * 2 + 1];
                e->t0++;
            } else { e->state = 2; e->vy = 6.25f; }
        } else if (e->state == 2) {
            e->y += e->vy;
            if (e->y > e->y0) { e->state = 3; e->y = e->y0; e->t0 = n - 1; }
        } else if (e->state == 3) {
            /* reversed at mmf_speed(50)=6.25 vs 11.25: ~x0.5556 rate */
            e->p[8] += 6.25f / 11.25f;
            while (e->p[8] >= 1 && e->t0 > 0) { e->p[8] -= 1; e->t0--; }
            e->x = leg[e->t0 * 2]; e->y = leg[e->t0 * 2 + 1];
            /* RyuWind contact -> upward acceleration */
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* w = &xs->ents[i];
                if (w->alive && w->cls == XB_RYUWIND && w->state == 0 &&
                    iwx_ents_overlap(xs, e, w)) {
                    e->state = 4; e->vy = 0;
                    break;
                }
            }
        } else if (e->state == 4) {
            e->vy -= 0.5f;
            e->y += e->vy;
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* c = &xs->ents[i];
                if (c->alive && c->cls == XB_CONDSOLID && c->p[2] == 77 &&
                    iwx_ents_overlap(xs, e, c)) {   /* FactoryCeiling id */
                    c->alive = 0;                   /* knocked away */
                    e->state = 5;
                }
            }
            if (e->y < -256) e->alive = 0;
        } else if (e->state == 5) {
            e->y += e->vy; e->vy -= 0.5f;
            if (e->y < -256) e->alive = 0;
        }
        return;
    }

    case XB_RYUWIND:
        return;                          /* effect applied in contact pass */

    case XB_MOONSMALL: {
        if (e->on && e->vy == 0 && e->state == 0) { e->vy = 6; e->state = 1; }
        if (e->vy != 0) {
            for (int i = 0; i < xs->n_ents; i++) {
                IWXEnt* d = &xs->ents[i];
                if (d->alive && d->cls == XB_DESTRUCTIBLE &&
                    d->y < e->y + 64)
                    iwx_kill_destructible(env, d, 0, 1);
            }
        }
        e->y += e->vy;
        if (e->y > env->room_ph + 96) { e->vy = 0; }
        return;
    }

    case XB_MOONBIG: {
        e->angle += 20;
        if (e->state == 0) {
            int n = (int)e->p[2];
            const float* tr = xs->keys + (int)e->p[1];
            if (e->t0 < n) {
                float nx = tr[e->t0 * 2], ny = tr[e->t0 * 2 + 1];
                e->vx = nx - e->x; e->vy = ny - e->y;
                e->x = nx; e->y = ny;
                e->t0++;
            } else iwx_ent_event(env, e);
        } else {
            e->vy += 0.4f;
            e->x += e->vx; e->y += e->vy;
            if (e->y > env->room_ph + 400) e->alive = 0;
        }
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* d = &xs->ents[i];
            if (d->alive && d->cls == XB_DESTRUCTIBLE &&
                iwx_ents_overlap(xs, e, d))
                iwx_kill_destructible(env, d, e->vx, e->vy);
        }
        return;
    }

    case XB_ORB: case XB_SECRET: case XB_ENTRANCETELE:
        return;                          /* contact pass */

    case XB_SNIFITCANNON: {
        int in_view = e->x >= xs->view_x && e->x < xs->view_x + 800 &&
                      e->y >= xs->view_y && e->y < xs->view_y + 608;
        int snifit_alive = 0;
        for (int i = 0; i < xs->n_ents; i++)
            if (xs->ents[i].alive && xs->ents[i].cls == XB_KILLER &&
                (int)xs->ents[i].p[7] == 1) { snifit_alive = 1; break; }
        if (in_view) e->t0++;
        int period = 100 - 40 * (e->state == 2 ? 1 : 0);
        if (e->t0 > period) {
            e->t0 = 0;
            if (snifit_alive && e->state != 1 && in_view) {
                IWXEnt* b2 = iwx_spawn(env, (int)e->p[0], e->x, e->y);
                if (b2) {
                    double ang = e->p[8];
                    if (e->state == 2)
                        ang = atan2(-(py - e->y), px - e->x) * 180 / IWX_PI;
                    double sp = 2.5 + 2.5 * (e->state == 2 ? 1 : 0);
                    b2->vx = (float)(sp * cos(ang * IWX_PI / 180));
                    b2->vy = (float)(-sp * sin(ang * IWX_PI / 180));
                    b2->p[7] = e->state == 2 ? 1 : 0;   /* aggressive */
                }
            }
        }
        if (e->state == 1 && snifit_alive) {
            /* laser mode: rotated 640x16 kill beam at 315 degrees */
            if (e->link >= 0) {
                IWXEnt* a = &xs->ents[e->link];
                a->alive = 1;
                a->x = e->x; a->y = e->y;
            }
        } else if (e->link >= 0) xs->ents[e->link].alive = 0;
        if (e->state == 2 && snifit_alive)
            e->p[8] = (float)(atan2(-(py - e->y), px - e->x) * 180 / IWX_PI);
        return;
    }

    case XB_SNIFITBULLET: {
        e->x += e->vx; e->y += e->vy;
        /* bullet reaching the Snifit destroys it */
        for (int i = 0; i < xs->n_ents; i++) {
            IWXEnt* s = &xs->ents[i];
            if (s->alive && s->cls == XB_KILLER && (int)s->p[7] == 1 &&
                iwx_ents_overlap(xs, e, s)) {
                s->alive = 0;
                e->alive = 0;
                return;
            }
        }
        if (e->x < -64 || e->x > env->room_pw + 64 ||
            e->y < -64 || e->y > env->room_ph + 64) e->alive = 0;
        return;
    }

    default:
        return;
    }
}

/* ---------------- collision hooks used by the core ---------------- */

/* dynamic xent solids (called from place_free / rect_hits_solid) */
static int iwx_solid_hit(IWanna* env, int l, int r, int t, int b) {
    IWXState* xs = XS(env);
    if (!xs) return 0;
    for (int k = 0; k < xs->n_idx_solid; k++) {
        IWXEnt* e = &xs->ents[xs->idx_solid[k]];
        if (!e->alive || !e->active) continue;
        if (e->cls == XB_REALYOKU || e->cls == XB_FACTORYBLOCK)
            continue;                     /* platforms, never solids */
        if (iwx_hit_rect(xs, e, l, r, t, b)) return 1;
    }
    return 0;
}

/* deadly xents (masks); called with tile/killer checks in c_step */
static int iwx_killer_hit(IWanna* env) {
    IWXState* xs = XS(env);
    if (!xs) return 0;
    if (xs->pending_kill) { xs->pending_kill = 0; return 1; }
    int l, r, t, b;
    iwx_player_rect(env, &l, &r, &t, &b);
    for (int k2 = 0; k2 < xs->n_idx_killer; k2++) {
        IWXEnt* e = &xs->ents[xs->idx_killer[k2]];
        if (!e->alive || !e->active) continue;
        switch (e->cls) {
        case XB_ANIM_KILLER:
            if (!e->armed && e->p[5] != 0) continue;   /* maskless (Fire) */
            if (e->p[7] >= 0 && e->frame < e->p[7]) continue; /* GraveTrap */
            break;
        case XB_ERRORTRAP:
            if (e->vy == 0) continue;
            break;
        case XB_SNIFITBULLET:
            if ((int)e->p[7] != 1) continue;   /* non-aggressive: bounce pad */
            break;
        case XB_GHOUL:
            if (e->state != 2) continue;               /* deadly while walking */
            break;
        case XB_SPIKESHOOT:
            if (e->state != 0) continue;
            break;
        case XB_LONK:
            continue;                                  /* slash handled in step */
        case XB_WITCH:
            if (e->state == 0) continue;
            break;
        case XB_PLAYSTATION: {
            if (iwx_hit_rect(xs, e, l, r, t, b)) {
                e->hp++;                               /* contact frames */
                if (e->hp >= 50) { e->alive = 0; return 1; }
            }
            continue;
        }
        default: break;
        }
        if (iwx_hit_rect(xs, e, l, r, t, b)) return 1;
    }
    /* burning: touching the ground kills (player.gml fire=2) */
    if (xs->fire == 2) {
        if (iwx_touch_water(env, env->x, env->y, 0)) xs->fire = 0;
        else if (!place_free(env, env->x, env->y + 1) &&
                 !iwx_touch_platform(env, env->x, env->y + 1))
            return 1;
    }
    return 0;
}

/* player bullets vs shootable xents; 1 = bullet consumed */
static int iwx_bullet_hit(IWanna* env, float bx, float by,
                          int bl, int br, int bt, int bb) {
    IWXState* xs = XS(env);
    if (!xs) return 0;
    (void)bx; (void)by;
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* e = &xs->ents[i];
        if (!e->alive || !e->active || !(e->flags & XEF_SHOOTABLE)) continue;
        if (!iwx_hit_rect(xs, e, bl, br, bt, bb)) {
            if (!(e->cls == XB_SHOOTBARRIER || e->cls == XB_NATSCAT) ||
                !iwx_bbox_hit(xs, e, bl, br, bt, bb))
                continue;
        }
        switch (e->cls) {
        case XB_BUTTON: {
            /* event_user(1): 5-frame cooldown toggle */
            if (e->t0 == 0) {
                e->t0 = 5;
                e->state = !e->state;
                if ((int)e->p[0] == 0) {
                    /* PlatformReset: platforms in view slow-rise / reset */
                    for (int k = 0; k < xs->n_ents; k++) {
                        IWXEnt* p = &xs->ents[k];
                        if (!p->alive || p->cls != XB_MOVPLAT) continue;
                        if (!iwx_ent_in_view(xs, p)) continue;
                        if (e->state) p->p[9] = -0.25f;
                        else { p->y = p->y0; p->p[9] = 0; }
                    }
                } else {
                    /* RyuButton: toggle turbine + wind/trigger swap */
                    for (int k = 0; k < xs->n_ents; k++) {
                        IWXEnt* t2 = &xs->ents[k];
                        if (!t2->alive) continue;
                        if (t2->cls == XB_KILLER && (int)t2->p[7] == 2)
                            t2->on = e->state;         /* turbine on/off */
                        if (t2->cls == XB_RYUWIND)
                            t2->state = e->state ? 0 : 1;  /* 1 = ryu trigger */
                    }
                }
            }
            return 1;
        }
        case XB_SHOOTBARRIER:
            e->frame += 0.2f;
            {
                const IWXMaskRec* m = iwx_mask(xs, e->mask);
                if (m && e->frame >= m->nframes) e->alive = 0;
            }
            return 1;
        case XB_NATSCAT:
            e->hp += 1;
            if (e->hp > 25) {
                e->alive = 0;
                iwx_spawn(env, (int)e->p[0], e->x, e->y - 32);
            }
            return 1;
        case XB_CHOZO:
            e->alive = 0;
            iwx_spawn(env, (int)e->p[0], e->x + 16, e->y + 16);
            return 1;
        case XB_SPIKESHOOT:
            if (e->state == 0) { e->state = 1; }
            return 1;
        case XB_BIRD: case XB_DUMBBUGZ: case XB_SPAG: case XB_FLYGUY:
            e->alive = 0;
            return 1;
        case XB_MEDUSA:
            e->alive = 0;
            return 1;
        case XB_GHOUL:
            if (e->hp > 0) {
                e->hp -= 1;
                if (e->hp <= 0) { e->state = 3; e->vx = 0; }
                return 1;
            }
            return 0;
        case XB_HOVERGUNNER: case XB_SNIPER:
            if (e->state != 2) {
                e->state = 2;
                e->flags &= ~XEF_KILLER;
            }
            return 1;
        case XB_SKWEE: case XB_CRAWLER: {
            /* freezes into a solid block */
            e->flags &= ~XEF_KILLER;
            e->flags |= XEF_SOLID;
            e->cls = XB_TETBLOCK;
            e->vx = e->vy = 0;
            return 1;
        }
        case XB_CHEEP:
            e->state = 2;
            return 0;                     /* source: bullet not destroyed */
        case XB_KILLER:
            if ((int)e->p[8] == 1) {      /* TextBlock-style reveal: cosmetic */
                return 1;
            }
            return 0;
        default:
            return 0;
        }
    }
    return 0;
}

/* ---------------- player contact pass (post-motion collision events) ------ */

static void iwx_platform_collisions(IWanna* env) {
    IWXState* xs = XS(env);
    int l, r, t, b;
    iwx_player_rect(env, &l, &r, &t, &b);
    env->on_platform = xs->on_platform;
    for (int k6 = 0; k6 < xs->n_idx_plat; k6++) {
        int i = xs->idx_plat[k6];
        IWXEnt* e = &xs->ents[i];
        if (!e->alive || !e->active) continue;
        double pl, pr, pt, pb, ptop;
        if (e->cls == XB_CART) {
            if (e->p[9] <= 0) continue;
            pl = e->x; pr = e->x + 106 - 1;
            pt = e->y + 4; pb = e->y + 4 + 16 - 1;
            ptop = e->y + 4;
        } else {
            if (!(e->flags & XEF_PLATFORM)) continue;
            if (e->cls == XB_FACTORYBLOCK && e->frame > 0.0f)
                continue;                /* landable only fully appeared */
            iwx_ent_bbox(xs, e, &pl, &pr, &pt, &pb);
            const IWXMaskRec* m = iwx_mask(xs, e->mask);
            if (m && m->nframes > 1 &&
                !iwx_hit_rect(xs, e, l, r, t, b)) continue;
            ptop = pt;                   /* == other.y for origin-(0,0) */
        }
        if (r < pl || l > pr || b < pt || t > pb) continue;
        if (env->y - env->vspeed / 2 <= ptop) {
            double evy = e->cls == XB_CART ? 0 : e->vy;
            env->djump = 1;
            if (evy >= 0) {
                double yp = env->y;
                env->y = ptop - 9;
                if (evy > 0 && !place_free(env, env->x, env->y)) env->y = yp;
                env->vspeed = evy;
            }
            xs->on_platform = 1;
            env->on_platform = 1;
            xs->walljumpboost = 0;
            int was_carted = xs->carted;
            xs->carted = 0;
            if (e->cls == XB_CART) xs->carted = 1;
            else if (was_carted && xs->cart_ent >= 0 &&
                     i == xs->cart_ent) xs->carted = 1;
        }
    }
}

static void iwx_contact_pass(IWanna* env) {
    IWXState* xs = XS(env);
    int l, r, t, b;
    iwx_player_rect(env, &l, &r, &t, &b);
    /* onPlatform clear (player Step: !place_meeting(x, y+4, platform)) */
    if (xs->on_platform && !iwx_touch_platform(env, env->x, env->y + 4)) {
        xs->on_platform = 0;
        env->on_platform = 0;
    }
    iwx_platform_collisions(env);
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* e = &xs->ents[i];
        if (!e->alive || !e->active) continue;
        switch (e->cls) {
        case XB_WATER:
            if (iwx_bbox_hit(xs, e, l, r, t, b)) {
                if ((int)e->p[0] == 1) env->djump = 1;
                if (env->vspeed > 2) env->vspeed = 2;
            }
            break;
        case XB_RYUWIND:
            if (e->state == 0) {
                if (iwx_bbox_hit(xs, e, l, r, t, b)) env->vspeed -= 1.5;
            } else {
                /* converted to the Ryu trigger */
                if (iwx_bbox_hit(xs, e, l, r, t, b)) {
                    for (int k = 0; k < xs->n_ents; k++)
                        if (xs->ents[k].alive && xs->ents[k].cls == XB_RYU)
                            xs->ents[k].on = 1;
                }
            }
            break;
        case XB_MEDUSA:
            if (iwx_hit_rect(xs, e, l, r, t, b) && !xs->stoned) {
                xs->stoned = 100;
                env->hspeed = ((double)(iw_rand(env) % 40001) / 1000.0) - 20.0;
                env->vspeed = ((double)(iw_rand(env) % 20001) / 1000.0) - 10.0;
            }
            break;
        case XB_BIRD:
        case XB_FLYGUY:                 /* "it's just a copy of bird" */
            if (iwx_hit_rect(xs, e, l, r, t, b) && xs->birded <= 0) {
                xs->birded = 10;
                env->hspeed = ((double)(iw_rand(env) % 40001) / 1000.0) - 20.0;
                env->vspeed = ((double)(iw_rand(env) % 20001) / 1000.0) - 10.0;
                env->djump = IW_MAXJUMPS;      /* djump=0 in the source */
                {
                    float sp = (float)sqrt(e->vx * e->vx + e->vy * e->vy);
                    e->vx = 0; e->vy = sp > 0 ? -sp : -7.5f;
                }
            }
            break;
        case XB_CHEEP:
            if (e->state == 1 && iwx_hit_rect(xs, e, l, r, t, b)) {
                env->hspeed = -8; env->vspeed = -8;
                xs->fished = 20;
                xs->carted = 0;
            }
            break;
        case XB_COUCH:
            if (e->state == 0 && iwx_hit_rect(xs, e, l, r, t, b)) {
                env->vspeed = -30;
                env->djump = 1;
                e->state = 1;
            }
            break;
        case XB_SNIFITBULLET:
            /* non-aggressive bullet: bounce pad (onPlatform + silent jump) */
            if ((int)e->p[7] == 0 && iwx_hit_rect(xs, e, l, r, t, b)) {
                e->alive = 0;
                xs->on_platform = 1;
                env->on_platform = 1;
                env->vspeed = -IW_JUMP;    /* playerJump(1): grounded path */
                env->djump = 1;
            }
            break;
        case XB_METROID:
            if (e->state == 0 && iwx_hit_rect(xs, e, l, r, t, b)) {
                e->state = 1; e->t0 = 0;
            }
            break;
        case XB_METROIDTRAP:
            if (iwx_bbox_hit(xs, e, l, r, t, b)) {
                e->alive = 0;
                iwx_spawn(env, (int)e->p[0], e->x + 700, e->y - 200);
            }
            break;
        case XB_LOCKCONTROLS:
            if (iwx_bbox_hit(xs, e, l, r, t, b)) xs->frozen = 1;
            break;
        case XB_QLTIMER:
            if (iwx_bbox_hit(xs, e, l, r, t, b)) e->on = 1;
            break;
        case XB_ASCENTMOD:
            if (iwx_bbox_hit(xs, e, l, r, t, b)) {
                for (int k = 0; k < xs->n_ents; k++)
                    if (xs->ents[k].alive && xs->ents[k].cls == XB_ASCENT)
                        xs->ents[k].p[9] -= 1;
                e->alive = 0;
            }
            break;
        case XB_FACTORYCTL:
            if (e->p[7] == 0 && iwx_bbox_hit(xs, e, l, r, t, b)) {
                e->p[7] = 0.01f;                  /* blk_spd = 1/100 */
                e->p[8] += 2 * 2 * 7 * 0.01f;     /* skip the appear anim */
            }
            break;
        case XB_MARKER:
            if ((int)e->p[0] == XM_CARTSTOP &&
                iwx_bbox_hit(xs, e, l, r, t, b)) xs->carted = 0;
            break;
        case XB_ORB:
            if (iwx_bbox_hit(xs, e, l, r, t, b)) {
                env->gflags |= 1ull << (int)e->p[0];
                e->alive = 0;
                /* source: orb pickup checkpoints immediately */
                env->respawn_x = env->x;
                env->respawn_y = env->y;
                env->respawn_face = env->face;
                env->respawn_room = env->room_id;
            }
            break;
        case XB_SECRET:
            if (iwx_bbox_hit(xs, e, l, r, t, b)) {
                env->gflags |= 1ull << (int)e->p[0];
                e->alive = 0;
            }
            break;
        case XB_ENTRANCETELE:
            if (iwx_bbox_hit(xs, e, l, r, t, b)) {
                uint64_t need = 0;
                for (int k = 0; k < 6; k++)
                    need |= 1ull << (int)e->p[k];
                if ((env->gflags & need) == need) {
                    env->pending_room = (int)e->p[6];
                    env->pending_use_start = 1;
                    env->pending_keep_speed = 0;
                } else xs->pending_kill = 1;
            }
            break;
        case XB_ANIM_KILLER:
            /* GraveTrap: touching an unopened grave arms it */
            if (e->p[8] != 0 && !e->armed &&
                iwx_hit_rect(xs, e, l, r, t, b)) {
                e->armed = 1;
                e->fspd = e->p[0];
            }
            break;
        case XB_TRIGGER: {
            if (!iwx_bbox_hit(xs, e, l, r, t, b)) break;
            int tgt = (int)e->p[3];
            if (!e->on) {
                e->on = 1;
                e->t0 = 2;                       /* alarm[0] = 2 */
                if (tgt >= 0 && tgt < xs->cap) {
                    xs->ents[tgt].on = 1;
                    xs->ents[tgt].active = 1;    /* instance_activate_object */
                } else if (tgt <= IWX_TGT_CLS0) {
                    int cls = IWX_TGT_CLS0 - tgt;
                    for (int k = 0; k < xs->n_ents; k++)
                        if (xs->ents[k].alive && xs->ents[k].cls == cls) {
                            xs->ents[k].on = 1;
                            xs->ents[k].active = 1;
                        }
                }
                if (e->p[1] >= 0)                /* t program (per touch) */
                    iwx_run_ops(env, (int)e->p[1], (int)e->p[4], i);
            }
            if (!e->state && e->p[0] >= 0) {     /* o program (once, lock) */
                e->state = 1;
                iwx_run_ops(env, (int)e->p[0], (int)e->p[5], i);
            }
            if (e->p[2] >= 0)                    /* c program (continuous) */
                iwx_run_ops(env, (int)e->p[2], (int)e->p[6], i);
            break;
        }
        default: break;
        }
    }
}

/* ---------------- walljump + exact jump (player.gml ports) --------------- */

static void iwx_walljump(IWanna* env, int h, int jump_held, int h_pressed_r,
                         int h_pressed_l, int jump_pressed) {
    IWXState* xs = XS(env);
    xs->hang = 0;
    int l, r, t, b;
    iwx_player_rect(env, &l, &r, &t, &b);
    for (int side = 0; side < 2; side++) {       /* 0 = L walls, 1 = R walls */
        double best = 1e9, best_yellow = 1e9, best_weird = 1e9;
        for (int kw = 0; kw < xs->n_idx_wall; kw++) {
            IWXEnt* e = &xs->ents[xs->idx_wall[kw]];
            if (!e->alive || !e->active) continue;
            if ((int)e->p[0] != side) continue;
            double el, er, et, eb;
            iwx_ent_bbox(xs, e, &el, &er, &et, &eb);
            double d = iwx_bbox_gap(l, r, t, b, el, er, et, eb);
            if (d < best) best = d;
            if ((int)e->p[1] >= XW_YELLOW && d < best_yellow) best_yellow = d;
            if ((int)e->p[1] == XW_WEIRD && d < best_weird) best_weird = d;
        }
        if (best >= 2) continue;
        int overlap_yellow = 0;
        for (int kw = 0; kw < xs->n_idx_wall && !overlap_yellow; kw++) {
            IWXEnt* e = &xs->ents[xs->idx_wall[kw]];
            if (!e->alive) continue;
            if ((int)e->p[0] != side || (int)e->p[1] < XW_YELLOW) continue;
            double el, er, et, eb;
            iwx_ent_bbox(xs, e, &el, &er, &et, &eb);
            if (r >= el && l <= er && b >= et && t <= eb) overlap_yellow = 1;
        }
        if (place_free(env, env->x, env->y + 2)) {
            xs->hang = 1;
            env->vspeed = 2;
        }
        int gate = xs->hang || overlap_yellow ||
                   place_free(env, env->x + env->face, env->y + 2) ||
                   place_free(env, env->x - env->face, env->y + 2);
        if (!gate) continue;
        int away_pressed = side == 0 ? h_pressed_r : h_pressed_l;
        int away_held = side == 0 ? (h == 1) : (h == -1);
        if (away_pressed || (away_held && best_yellow < 2) || jump_pressed) {
            int s = side == 0 ? 1 : -1;
            if (jump_held) {
                env->vspeed = -9;
                env->hspeed = 15 * s;
                xs->altj = 2;
                xs->walljump = 2;
                xs->walljumpboost = 0;
                if (best_weird < 2) {
                    xs->walljumpboost = 24;
                    xs->walljumpdir = s;
                } else if (best_yellow < 2) {
                    xs->carted = 0;
                    xs->walljumpboost = -1;
                    env->hspeed = 10 * s;
                    env->vspeed = -10;
                }
            } else {
                env->hspeed = 3 * s;
            }
            xs->hang = 0;
        }
    }
    if (xs->walljump > 0) xs->walljump--;
}

/* ---------------- pack v3 section loading ---------------- */

static int iwx_load_section(IWanna* env, char* err, size_t errlen) {
    IWPackRT* rt = env->pack;
    uint32_t off = rt->hdr.reserved0, len = rt->hdr.reserved1;
    if (rt->hdr.version < 3 || !off || !len) return 0;   /* no exact layer */
    if (!iwpack_range_ok(rt->len, off, sizeof(IWXHeader))) {
        iwpack_err(err, errlen, "exact section out of bounds"); return -1;
    }
    IWXState* xs = (IWXState*)calloc(1, sizeof(IWXState));
    if (!xs) { iwpack_err(err, errlen, "out of memory"); return -1; }
    memcpy(&xs->hdr, rt->blob + off, sizeof(IWXHeader));
    IWXHeader* h = &xs->hdr;
    if (h->magic != IWX_MAGIC ||
        !iwpack_range_ok(rt->len, h->masks_off, (size_t)h->n_masks * sizeof(IWXMaskRec)) ||
        !iwpack_range_ok(rt->len, h->bits_off, (size_t)h->bits_words * 4) ||
        !iwpack_range_ok(rt->len, h->ops_off, (size_t)h->n_ops * sizeof(IWXOpRec)) ||
        !iwpack_range_ok(rt->len, h->tmpl_off, (size_t)h->n_tmpl * sizeof(IWXEntRec)) ||
        !iwpack_range_ok(rt->len, h->keys_off, (size_t)h->n_keys * 4) ||
        !iwpack_range_ok(rt->len, h->xrooms_off, (size_t)h->n_xrooms * sizeof(IWXRoomRec)) ||
        h->n_xrooms != rt->hdr.n_rooms) {
        free(xs);
        iwpack_err(err, errlen, "exact section corrupt"); return -1;
    }
    xs->masks = (const IWXMaskRec*)(rt->blob + h->masks_off);
    xs->bits = (const uint32_t*)(rt->blob + h->bits_off);
    xs->ops = (const IWXOpRec*)(rt->blob + h->ops_off);
    xs->tmpl = (const IWXEntRec*)(rt->blob + h->tmpl_off);
    xs->keys = (const float*)(rt->blob + h->keys_off);
    xs->xrooms = (const IWXRoomRec*)(rt->blob + h->xrooms_off);
    xs->cap = (int)h->max_xents + 64;
    xs->ents = (IWXEnt*)calloc((size_t)xs->cap, sizeof(IWXEnt));
    xs->idx_solid = (int32_t*)calloc((size_t)xs->cap * 6, sizeof(int32_t));
    if (!xs->ents || !xs->idx_solid) {
        free(xs->ents); free(xs->idx_solid); free(xs);
        iwpack_err(err, errlen, "out of memory"); return -1;
    }
    xs->idx_killer = xs->idx_solid + xs->cap;
    xs->idx_plat = xs->idx_solid + xs->cap * 2;
    xs->idx_marker = xs->idx_solid + xs->cap * 3;
    xs->idx_wall = xs->idx_solid + xs->cap * 4;
    xs->idx_water = xs->idx_solid + xs->cap * 5;
    xs->cart_ent = -1;
    env->xs = xs;
    env->hb_l = h->hb_l; env->hb_t = h->hb_t;
    env->hb_r = h->hb_r; env->hb_b = h->hb_b;
    return 1;
}

static void iwx_free(IWanna* env) {
    if (!env->xs) return;
    free(env->xs->ents);
    free(env->xs->idx_solid);
    free(env->xs);
    env->xs = NULL;
}

/* ---------------- exact player step (player.gml port) ---------------- */

static void iwx_player_step(IWanna* env, int h, int jump_held, int pressed,
                            int released, int shoot_pressed,
                            int hpl, int hpr) {
    IWXState* xs = XS(env);
    int locked = xs->frozen || xs->stoned;

    /* --- ///movement (player.gml Step_0) --- */
    if (!xs->stoned) {
        int h_in = xs->frozen ? 0 : h;
        if (xs->walljumpboost > 0) { h_in = xs->walljumpdir; xs->walljumpboost--; }
        if (xs->walljumpboost < 0) {
            if (!xs->walljump) {
                xs->altj++;
                if (xs->altj >= 10) {
                    env->hspeed -= iw_sign(env->hspeed);
                    xs->altj = 0;
                }
                env->vspeed += 0.1;      /* simulated Guy gravity */
                if (fabs(env->hspeed) < 4) xs->walljumpboost = 0;
            } else {
                env->vspeed -= IW_GRAV;  /* pre-cancels built-in gravity */
            }
        } else if (!(xs->birded > 0) || h_in != 0) {
            if (h_in != 0) {
                env->hspeed = (xs->walljumpboost != 0 ? 4.0 : IW_MAXSPEED) * h_in;
                env->face = h_in;
            } else {
                env->hspeed = 0;
            }
        }
    }
    if (xs->carted && xs->cart_ent >= 0)
        env->x += xs->ents[xs->cart_ent].vx;
    if (xs->birded > 0) xs->birded--;
    if (xs->fished > 0) xs->fished--;
    if (xs->stoned > 0) xs->stoned--;
    if (env->hspeed == 0 && !xs->stoned) env->x = gm_round(env->x);
    if (env->vspeed > IW_MAXVSPEED) env->vspeed = IW_MAXVSPEED;
    /* couch-trap decel: emulated Guy gravity above jump speed */
    if (env->vspeed < -8.5) env->vspeed += jump_held ? 0.1 : 0.71;
    if (!locked) {
        if (shoot_pressed) iw_player_shoot(env);
        if (pressed && !xs->hang) {      /* playerJump(0) */
            int grounded = !place_free(env, env->x, env->y + 1) ||
                           xs->on_platform ||
                           iwx_touch_water(env, env->x, env->y + 1, 1);
            if (grounded) { env->vspeed = -IW_JUMP; env->djump = 1; }
            else if (env->djump < IW_MAXJUMPS ||
                     iwx_touch_water(env, env->x, env->y + 1, 2)) {
                env->vspeed = -IW_JUMP2;
                env->djump = IW_MAXJUMPS;
            }
        }
        if (released && env->vspeed < 0) env->vspeed *= IW_RELEASE_MULT;
    }

    /* --- ///walljump --- */
    iwx_walljump(env, h, jump_held, hpr, hpl, pressed);

    /* --- solid collision pre-resolve (identical arithmetic to legacy) --- */
    double rx, rxnext;
    if (env->hspeed >= 0) { rx = floor(env->x); rxnext = floor(env->x + env->hspeed); }
    else { rx = ceil(env->x); rxnext = ceil(env->x + env->hspeed); }
    env->vspeed += IW_GRAV;
    if (!place_free(env, rxnext, env->y + env->vspeed)) {
        if (!place_free(env, rxnext, env->y)) {
            env->x = rx;
            int a = (int)ceil(fabs(env->hspeed));
            int s = iw_sign(env->hspeed);
            for (int i = 0; i <= a; i++) {
                env->x += s;
                if (!place_free(env, env->x, env->y)) {
                    env->x -= s;
                    env->hspeed = 0;
                    xs->walljumpboost = 0;   /* Collision_block */
                    xs->carted = 0;
                    break;
                }
            }
            env->x -= env->hspeed;
        }
        if (!place_free(env, rx, env->y + env->vspeed)) {
            int a = (int)ceil(fabs(env->vspeed));
            int s = iw_sign(env->vspeed);
            for (int i = 0; i <= a; i++) {
                env->y += s;
                if (!place_free(env, rx, env->y)) {
                    env->y -= s;
                    env->vspeed = 0;
                    if (s == 1) {            /* landing */
                        env->djump = 1;
                        xs->walljumpboost = 0;
                        xs->carted = 0;
                        if (xs->stoned) env->hspeed = 0;
                    }
                    break;
                }
            }
        }
        if (env->hspeed >= 0) rxnext = floor(env->x + env->hspeed);
        else rxnext = ceil(env->x + env->hspeed);
        if (!place_free(env, rxnext, env->y + env->vspeed)) {
            env->hspeed = 0;
            xs->walljumpboost = 0;
            xs->carted = 0;
        }
    }
    env->vspeed -= IW_GRAV;

    /* --- GM8 built-in update: gravity then motion --- */
    env->vspeed += IW_GRAV;
    env->x += env->hspeed;
    env->y += env->vspeed;
}

/* ---------------- frame hooks (called from c_step) ---------------- */

static void iwx_reindex(IWXState* xs) {
    xs->n_idx_solid = xs->n_idx_killer = xs->n_idx_plat = 0;
    xs->n_idx_marker = xs->n_idx_wall = xs->n_idx_water = 0;
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* e = &xs->ents[i];
        if (!e->alive) continue;
        if (e->flags & XEF_SOLID) xs->idx_solid[xs->n_idx_solid++] = i;
        if (e->flags & XEF_KILLER) xs->idx_killer[xs->n_idx_killer++] = i;
        if ((e->flags & XEF_PLATFORM) || e->cls == XB_CART)
            xs->idx_plat[xs->n_idx_plat++] = i;
        if (e->cls == XB_MARKER) xs->idx_marker[xs->n_idx_marker++] = i;
        if (e->cls == XB_WALLSTRIP) xs->idx_wall[xs->n_idx_wall++] = i;
        if (e->cls == XB_WATER) xs->idx_water[xs->n_idx_water++] = i;
    }
}

static void iwx_frame_begin(IWanna* env) {
    IWXState* xs = XS(env);
    if (!xs) return;
    if (!xs->view_init) iwx_view_update(env);
    iwx_reindex(xs);
    for (int i = 0; i < xs->n_ents; i++) {
        IWXEnt* e = &xs->ents[i];
        if (!e->alive || !e->active) continue;
        iwx_update_ent(env, i);
    }
    iwx_reindex(xs);          /* spawns/solidity changes during the update */
    if (xs->metroid_doom > 0 && --xs->metroid_doom == 0)
        xs->pending_kill = 1;
}

static void iwx_frame_end(IWanna* env) {
    IWXState* xs = XS(env);
    if (!xs) return;
    iwx_contact_pass(env);
    iwx_view_update(env);
}

#endif /* IW_EXACT_IMPL_H */
