/* exact.h — IWBTGR exact-behavior layer (pack v3).
 *
 * Implements the full non-boss object catalog of IWBTGR 1.5.3 as compiled
 * native behaviors: sprite-mask collision, the trigger system, the camera +
 * activation model, and the player-physics extensions (walljump, water,
 * platforms, couch deceleration, frozen/stoned states). Everything is
 * decoded offline by the converter (docs/iwbtgr_nonboss_mechanics.md is the
 * source-semantics reference); this file only executes compiled data.
 *
 * The layer is OPTIONAL: envs without a v3 pack never allocate it and every
 * legacy code path is untouched (guarded by `env->xs == NULL`).
 */
#ifndef IW_EXACT_H
#define IW_EXACT_H

#include <stdint.h>
#include <math.h>

/* ------------------------------------------------------------------ *
 * On-disk records (little-endian, 4-byte aligned), pack v3 section.
 * Header reserved0/reserved1 carry x_off/x_len when version >= 3.
 * ------------------------------------------------------------------ */

#define IWX_MAGIC 0x33544358u  /* "XCT3" */

typedef struct {
    uint32_t magic;            /* IWX_MAGIC */
    uint32_t n_masks,  masks_off;    /* IWXMaskRec[n_masks] */
    uint32_t bits_off, bits_words;   /* uint32 pool for mask bitmaps */
    uint32_t n_ops,    ops_off;      /* IWXOpRec[n_ops] */
    uint32_t n_tmpl,   tmpl_off;     /* IWXEntRec[n_tmpl] spawn templates */
    uint32_t n_keys,   keys_off;     /* float pool (sampled path frames etc.) */
    uint32_t n_xrooms, xrooms_off;   /* IWXRoomRec[n_rooms] */
    uint32_t max_xents;              /* live array size (incl. spawn headroom) */
    int32_t  hb_l, hb_t, hb_r, hb_b; /* player hitbox for this pack */
    uint32_t flags;                  /* bit0 = exact player physics */
    uint32_t reserved[3];
} IWXHeader;

#define IWXF_PHYSICS 1u

/* mask shapes */
#define IWX_SHAPE_RECT 0
#define IWX_SHAPE_PRECISE 1

typedef struct {
    int16_t w, h;              /* frame size, px */
    int16_t ox, oy;            /* origin */
    int16_t bl, bt, br, bb;    /* bbox, inclusive, sprite coords */
    uint16_t shape;            /* IWX_SHAPE_* */
    uint16_t nframes;          /* stored mask frames (1 for RECT/union) */
    uint32_t bits_word0;       /* index into bits pool (per frame, row-major,
                                  rows padded to whole 32-bit words) */
} IWXMaskRec;                  /* 24 bytes */

/* trigger / event op */
typedef struct {
    int32_t op;
    int32_t tgt;               /* xent index; or IWX_TGT_* encodings */
    float a, b, c;
} IWXOpRec;                    /* 20 bytes */

#define IWX_TGT_SELF   (-1)
#define IWX_TGT_PLAYER (-2)
#define IWX_TGT_NONE   (-3)
/* tgt <= IWX_TGT_CLS0 addresses every live xent of class (IWX_TGT_CLS0-tgt) */
#define IWX_TGT_CLS0   (-1000)

enum {
    XOP_END = 0,
    XOP_SET_ACTIVE,     /* a = value (the trigger "wake" pulse)            */
    XOP_ARM,            /* armed=1 (visible=1 / on=1 in source)            */
    XOP_SET_VX,         /* vx = a                                          */
    XOP_SET_VY,         /* vy = a                                          */
    XOP_SET_FSPD,       /* image_speed = a                                 */
    XOP_SET_STATE,      /* state = (int)a                                  */
    XOP_ADD_STATE,      /* state += (int)a                                 */
    XOP_EVENT,          /* behavior-defined event_user(0)                  */
    XOP_SPAWN,          /* template (int)a at (b, c); tgt = link target    */
    XOP_DESTROY,        /* alive = 0                                       */
    XOP_KILL_PLAYER,
    XOP_FREEZE_PLAYER,  /* frozen = (int)a                                 */
    XOP_SET_FIRE,       /* player fire state = (int)a                      */
    XOP_SET_FLAG,       /* gflags |= 1<<(int)a                             */
    XOP_GOTO_ROOM,      /* a = room, b/c dest px (b<0: use start)          */
    XOP_IF_STATE_EQ,    /* skip (int)b following ops unless state == a     */
    XOP_IF_STATE_NE,
    XOP_IF_ALIVE,       /* skip b ops unless tgt alive                     */
    XOP_IF_DEAD,        /* skip b ops unless tgt dead/absent               */
    XOP_IF_FLAG,        /* skip b ops unless gflag a set                   */
    XOP_IF_NOT_FLAG,
    XOP_IF_PLAYER_FIRE, /* skip b ops unless fire == a                     */
    XOP_IF_Y_LT,        /* skip b ops unless tgt y < a                     */
    XOP_IF_VY_LE,       /* skip b ops unless tgt vy <= a                   */
    XOP_IF_X_LT,        /* skip b ops unless tgt x < a                     */
    XOP_IF_OVERLAP,     /* skip b ops unless tgt overlaps THE TRIGGER rect */
    XOP_IF_WITCH_WAIT,  /* skip b ops unless the witch is still dormant    */
    XOP_SET_FRAME,      /* frame = a (image_index)                         */
    XOP_LAST_FRAME,     /* frame = last (image_number-1)                   */
    XOP_SET_TIMER,      /* timer = (int)a                                  */
    XOP_SET_P,          /* p[(int)a] = b                                   */
    XOP_SPAWNBOOST,     /* player spawns with vspeed = a (castleboost)     */
    XOP_IF_P_EQ,        /* skip (int)b ops unless tgt p[(int)c] == a       */
    XOP_NUM
};

/* per-entity flag bits (compiled) */
#define XEF_KILLER      1u     /* mask overlap kills the player            */
#define XEF_SOLID       2u     /* mask blocks movement (place_free)        */
#define XEF_PLATFORM    4u     /* one-way platform (Collision_platform)    */
#define XEF_SHOOTABLE   8u     /* player bullets interact (behavior hook)  */
#define XEF_FORCE_ACTIVE 16u   /* ignore the activation region             */
#define XEF_START_INACTIVE 32u /* spawned dormant (armed by ops)           */
#define XEF_NOPUSH      64u    /* movingPlatform nopush                    */
#define XEF_STOPPER     128u   /* movingPlatform stopper                   */
#define XEF_NOBOUNCE    256u   /* movingPlatform exempt from solid bounce  */
#define XEF_MIRROR8     512u   /* mask mirrors every 8 frames (ZeldaFire)  */

typedef struct {
    uint16_t cls;
    uint16_t mask;             /* mask table index; 0xffff = none */
    float x, y;
    float xs, ys;              /* image scales (sign = flip) */
    int32_t tag;               /* stable id for op targeting (== spawn idx) */
    uint32_t flags;
    int32_t link;              /* attached xent index (-1 none) */
    float p[10];
} IWXEntRec;                   /* 72 bytes */

typedef struct {
    uint32_t n_xents, xents_off;   /* IWXEntRec[n_xents] */
    uint32_t camera;               /* 0 none, 1 hard, 2 cart, 3 tower */
    uint32_t always_active;        /* rGuyLabyrinth rule */
    uint32_t enter_op0, enter_nops;/* ops run on room entry (side effects) */
    uint32_t reserved[2];
} IWXRoomRec;                  /* 32 bytes */

/* ------------------------------------------------------------------ *
 * Behavior classes. MUST match tools' XCLS table (compiled data).
 * ------------------------------------------------------------------ */
enum {
    XB_MARKER = 0,     /* inert geometry other behaviors query (p0 = kind) */
    XB_KILLER,         /* static masked killer (optional anim: p0=fspd,
                          p1=loop_lo, p2=loop_hi (index-=2 loop), p3=start) */
    XB_ANIM_KILLER,    /* armed anim killer (Fire family, Grabby, CycleSpike,
                          GraveTrap, Turbine):
                          p0 fspd-when-armed, p1 start frame, p2 loop_lo,
                          p3 loop_hi (loop: index-=2 when >= p3), p4 armed0,
                          p5 maskless-until-armed, p6 die-at-anim-end,
                          p7 kill-only-from-frame (GraveTrap: 6; else -1),
                          p8 touch-arms (GraveTrap), p9 pingpong (Grabby) */
    XB_SHAKE_FALL,     /* p0 shake frames, p1 vx after, p2 vy after,
                          p3 both-axes shake (else y only), p4 shake period,
                          p5 keep-shaking+fall-at-p0 (FallingBlockTrap),
                          p6 destroy-linked-solid-at-launch (FallStair) */
    XB_BOLT,           /* static killer; ops arm and launch it */
    XB_SPIKE_EXTEND,   /* rises toward the player when armed; growing shaft */
    XB_REVEALING,      /* event: rise 32px, 200 frames, sink */
    XB_SPIKETRAP,      /* slam crusher (rGuy1): platform top + killer face */
    XB_QUICKLASER,     /* p0 c index, p1 length px, p2 delay, p3 angle deg */
    XB_QLTIMER,        /* fires lasers at the source schedule */
    XB_KILLPLANE,      /* hspeed -35; kills once x < player.x */
    XB_HIGGER,         /* falling painting formula */
    XB_ERRORTRAP,      /* freeze 100; falls at 165; deadly while moving */
    XB_PAINTING,       /* PaintingTrap: drops 32px, kills if overlapping */
    XB_WHEEL,          /* WheelTrap: rolls 7.5, breaks destructibles */
    XB_FLYSPIKE,       /* rises 6.25 to y=334 */
    XB_GUTSMAN,        /* 150-frame jingle, freeze, fall 37.5, kill */
    XB_COUCH,          /* single-use vspeed=-30 djump bounce */
    XB_HAMMER,         /* falls 6.25 on trigger; kills; lands as solid */
    XB_SPIKESHOOT,     /* TheSpikeYouShoot */
    XB_MEDUSA,         /* zigzag head */
    XB_MEDUSAMAKER,    /* path patrol + spawn every 100 */
    XB_BIRD,           /* re-aim every 10 at 7.5; knockback on touch */
    XB_GHOUL,
    XB_GHOULGEN,
    XB_HOVERGUNNER,    /* p0 drop-in (go) */
    XB_HOVERSHOT,      /* killer shot; dies on solids */
    XB_SNIPER,
    XB_TOURTURRET,
    XB_SKWEE,
    XB_CRAWLER,
    XB_DUMBBUGZ,
    XB_METROID,
    XB_METROIDTRAP,
    XB_SPAGDISP,
    XB_SPAG,
    XB_ROLLROCK,
    XB_WATCHFOR,
    XB_PLAYSTATION,
    XB_KAMEK,
    XB_EGGPLANT,       /* falls 2.5; bounces on Bounce markers */
    XB_BOUNCYFRUIT,    /* launched -5; redirected by Bounce markers */
    XB_WITCH,
    XB_WITCHSHADOW,    /* sampled path follower (ping-pong) */
    XB_LONK,
    XB_CHEEP,
    XB_CHEEPCTL,
    XB_BULLETBILL,
    XB_MOVPLAT,        /* movingPlatform (+LongForm via mask) */
    XB_FALLPLAT,       /* FallingBrick/Fort/Factory/Outskirt (params) */
    XB_METROIDPLAT,
    XB_ASCENT,
    XB_ASCENTMOD,
    XB_KUMO,
    XB_GUYPLAT,
    XB_PILLAR,
    XB_HILL,           /* solid riser */
    XB_CART,
    XB_CARTPICKUP,
    XB_FACTORYCTL,     /* factory yoku chain controller */
    XB_FACTORYBLOCK,   /* chain member (platform w/ appear anim) */
    XB_REALYOKUCTL,
    XB_REALYOKU,       /* toggling solid block */
    XB_TETRIS,         /* compiled timeline controller */
    XB_TETBLOCK,       /* dynamic solid 32x32 */
    XB_KILLPILL,
    XB_BUTTON,         /* p0: 0 = PlatformReset, 1 = RyuButton */
    XB_SHOOTBARRIER,   /* solid; bullets advance frame; dies at end */
    XB_NATSCAT,        /* solid; hp 25; explodes */
    XB_BOOM,           /* CUTE_KITTY_BOOM killer flash */
    XB_CHOZO,          /* killer; shot -> secret4 spawn */
    XB_TRIGGER,        /* the generic trigger (op programs) */
    XB_LOCKCONTROLS,
    XB_FRUIT,          /* deliciousFruit (1-frame launch delay) */
    XB_CATTHING,
    XB_FIRECHALICE,
    XB_RYU,
    XB_RYUWIND,        /* updraft region (becomes Ryu trigger when off) */
    XB_MOONSMALL,
    XB_MOONBIG,        /* sampled path killer; ballistic at end/death */
    XB_ORB,            /* p0 = flag bit; touch: flag + checkpoint */
    XB_SECRET,         /* p0 = flag bit */
    XB_ENTRANCETELE,   /* 6-orb AND gate; kills without them */
    XB_CONDSOLID,      /* solid iff gflag p0 set (BlownEntrance) / unset */
    XB_TOURIANBARRIER, /* solid; opens (mask frame 0) once orb_mother set */
    XB_DESTRUCTIBLE,   /* blockTrapDestructible: solid until event-killed */
    XB_WALLSTRIP,      /* p0 side (+1 L wall on left? see player), p1 kind */
    XB_WATER,          /* p0: 1 = objWater, 2 = objWater2 */
    XB_SNIFITCANNON,
    XB_SNIFITBULLET,
    XB_ZELDAOLDMAN,    /* killer (mask) */
    XB_PATHKILLER,     /* generic sampled-path killer (reserved) */
    XB_FRSPIKE,        /* FirstRoomSpike slam choreography */
    XB_FRBARRIER,      /* FirstRoomBarrier closing gate (mask frames) */
    XB_SPIKEMAN,       /* FunnySpikeMan: wakes in range, walks at 4 px/f */
    XB_SPINNER,        /* FactorySpinner1/2: tipping solid (angle ramp) */
    XB_NUM_CLASSES
};

/* marker kinds (XB_MARKER p0) */
enum {
    XM_GENERIC = 0,
    XM_BOUNCE_UP, XM_BOUNCE_DOWN, XM_BOUNCE_LEFT, XM_BOUNCE_RIGHT,
    XM_BLOCKNISE,        /* platform/cart bounce + witch/crawler collision */
    XM_KUMOSTOP,
    XM_DUMP,             /* cart platform gap */
    XM_BULLETTRIGGER,    /* cart: start the bullet bills */
    XM_CARTSTOP,
    XM_MEDUSAMOD,
    XM_SOFTLOCK,         /* SoftlockBlocker: saves refuse while overlapped */
    XM_FRSW,             /* FirstRoomSpikeWall */
    XM_WALLJUMP_GONE,    /* placeholder for destroyed strips */
};

/* wall strip kinds (XB_WALLSTRIP p1) */
enum { XW_PLAIN = 0, XW_YELLOW = 1, XW_WEIRD = 2 };

/* camera kinds */
enum { XCAM_NONE = 0, XCAM_HARD, XCAM_CART, XCAM_TOWER,
       XCAM_HARD_METROID };  /* rMetroid: smooth-y past camx 2400 */

/* live entity */
typedef struct {
    uint16_t cls;
    uint16_t mask;
    uint8_t alive, active, armed, on;
    float x, y, vx, vy;
    float xs, ys, angle;
    float frame, fspd;
    int32_t t0, t1, state, hp;
    int32_t link;              /* index of an attached live xent (-1 none) */
    int32_t tag;
    uint32_t flags;
    float p[10];
    float x0, y0;              /* spawn position (xstart/ystart) */
} IWXEnt;

typedef struct {
    /* decoded pack section (pointers into the pack blob) */
    IWXHeader hdr;
    const IWXMaskRec* masks;
    const uint32_t* bits;
    const IWXOpRec* ops;
    const IWXEntRec* tmpl;
    const float* keys;
    const IWXRoomRec* xrooms;

    /* live state (allocated once) */
    IWXEnt* ents;
    int n_ents;                /* high-water mark */
    int cap;

    /* per-frame index caches (rebuilt in iwx_frame_begin) */
    int32_t* idx_solid;   int n_idx_solid;
    int32_t* idx_killer;  int n_idx_killer;
    int32_t* idx_plat;    int n_idx_plat;
    int32_t* idx_marker;  int n_idx_marker;
    int32_t* idx_wall;    int n_idx_wall;
    int32_t* idx_water;   int n_idx_water;

    /* view + activation */
    int camera;                /* current room camera kind */
    int always_active;
    double view_x, view_y;
    double act_x, act_y;       /* view position of the last activation pass */
    int view_init;

    /* player extension state */
    int frozen, stoned, birded, fished, carted, on_platform;
    int hang, walljump, walljumpboost, walljumpdir, altj;
    int fire;                  /* 0 none, 1 armed, 2 burning */
    int metroid_doom;          /* frames until Metroid latch death (0 idle) */
    double plat_pull_y;        /* platform carry applied this frame */
    int cart_ent;              /* index of the Cart entity (-1 none) */
    int room;                  /* current xroom */
    int pending_kill;          /* set by behaviors/ops: kill at check time */
    int pending_freeze;
    float spawn_boost;         /* castleboost: vspeed on next spawn */
} IWXState;

/* ------------------------------------------------------------------ *
 * Mask sampling (GM8-style integer pixel tests).
 * ------------------------------------------------------------------ */

static inline const IWXMaskRec* iwx_mask(const IWXState* xs, uint16_t id) {
    return id == 0xffff ? NULL : &xs->masks[id];
}

static inline int iwx_mask_bit(const IWXState* xs, const IWXMaskRec* m,
                               int frame, int u, int v) {
    if (u < m->bl || u > m->br || v < m->bt || v > m->bb) return 0;
    if (m->shape == IWX_SHAPE_RECT) return 1;
    if (m->nframes > 1) frame = frame % m->nframes;
    else frame = 0;
    if (frame < 0) frame += m->nframes;
    int words_per_row = (m->w + 31) >> 5;
    uint32_t w = xs->bits[m->bits_word0 +
                          (size_t)frame * (size_t)m->h * words_per_row +
                          (size_t)v * words_per_row + (u >> 5)];
    return (w >> (u & 31)) & 1u;
}

/* sprite-space u for room pixel px given instance x + scale (GM pixel map) */
static inline int iwx_inv(double px, double ex, float scale, int origin) {
    double t = (px - ex) / scale;
    return origin + (scale >= 0 ? (int)floor(t) : (int)ceil(t) - 1);
}

/* transformed inclusive bbox of an entity mask -> [l,r]x[t,b] room px */
static inline void iwx_ent_bbox(const IWXState* xs, const IWXEnt* e,
                                double* l, double* r, double* t, double* b) {
    const IWXMaskRec* m = iwx_mask(xs, e->mask);
    if (!m) { *l = *t = 1; *r = *b = 0; return; }
    double xs0 = e->x + (m->bl - m->ox) * (double)e->xs;
    double xs1 = e->x + (m->br + 1 - m->ox) * (double)e->xs;
    double ys0 = e->y + (m->bt - m->oy) * (double)e->ys;
    double ys1 = e->y + (m->bb + 1 - m->oy) * (double)e->ys;
    if (e->angle != 0) {
        /* rotate the four corners about (x, y) */
        double ca = cos(e->angle * (3.14159265358979323846 / 180.0));
        double sa = sin(e->angle * (3.14159265358979323846 / 180.0));
        double cx[4] = {xs0, xs1, xs0, xs1}, cy[4] = {ys0, ys0, ys1, ys1};
        double lo_x = 1e30, hi_x = -1e30, lo_y = 1e30, hi_y = -1e30;
        for (int i = 0; i < 4; i++) {
            double dx = cx[i] - e->x, dy = cy[i] - e->y;
            double rx = e->x + dx * ca + dy * sa;   /* GM rotates CCW for +angle */
            double ry = e->y - dx * sa + dy * ca;
            if (rx < lo_x) lo_x = rx; if (rx > hi_x) hi_x = rx;
            if (ry < lo_y) lo_y = ry; if (ry > hi_y) hi_y = ry;
        }
        *l = lo_x; *r = hi_x - 1; *t = lo_y; *b = hi_y - 1;
        return;
    }
    if (xs0 > xs1) { double q = xs0; xs0 = xs1; xs1 = q; }
    if (ys0 > ys1) { double q = ys0; ys0 = ys1; ys1 = q; }
    *l = xs0; *r = xs1 - 1; *t = ys0; *b = ys1 - 1;
}

/* does the entity mask overlap the inclusive integer rect [l..r]x[t..b]? */
static int iwx_hit_rect(const IWXState* xs, const IWXEnt* e,
                        int l, int r, int t, int b) {
    const IWXMaskRec* m = iwx_mask(xs, e->mask);
    if (!m) return 0;
    double el, er, et, eb;
    iwx_ent_bbox(xs, e, &el, &er, &et, &eb);
    int cl = l > (int)ceil(el)  ? l : (int)ceil(el);
    int cr = r < (int)floor(er) ? r : (int)floor(er);
    int ct = t > (int)ceil(et)  ? t : (int)ceil(et);
    int cb = b < (int)floor(eb) ? b : (int)floor(eb);
    if (cl > cr || ct > cb) return 0;
    int frame = (int)e->frame;
    if (m->shape == IWX_SHAPE_RECT && e->angle == 0) return 1;
    if (e->angle == 0) {
        for (int py = ct; py <= cb; py++) {
            int v = iwx_inv(py + 0.0, e->y, e->ys, m->oy);
            for (int px = cl; px <= cr; px++) {
                int u = iwx_inv(px + 0.0, e->x, e->xs, m->ox);
                if ((e->flags & XEF_MIRROR8) && ((e->t0 >> 3) & 1))
                    u = m->bl + m->br - u;
                if (iwx_mask_bit(xs, m, frame, u, v)) return 1;
            }
        }
        return 0;
    }
    /* rotated: inverse-rotate each sample point about (x, y) */
    double ca = cos(e->angle * (3.14159265358979323846 / 180.0));
    double sa = sin(e->angle * (3.14159265358979323846 / 180.0));
    for (int py = ct; py <= cb; py++) {
        for (int px = cl; px <= cr; px++) {
            double dx = px - e->x, dy = py - e->y;
            double rx = e->x + dx * ca - dy * sa;
            double ry = e->y + dx * sa + dy * ca;
            int u = iwx_inv(rx, e->x, e->xs, m->ox);
            int v = iwx_inv(ry, e->y, e->ys, m->oy);
            if (iwx_mask_bit(xs, m, frame, u, v)) return 1;
        }
    }
    return 0;
}

/* rect-vs-rect helper on entity bbox only (platform tops, regions) */
static inline int iwx_bbox_hit(const IWXState* xs, const IWXEnt* e,
                               int l, int r, int t, int b) {
    double el, er, et, eb;
    iwx_ent_bbox(xs, e, &el, &er, &et, &eb);
    return l <= er && r >= el && t <= eb && b >= et;
}

#endif /* IW_EXACT_H */
