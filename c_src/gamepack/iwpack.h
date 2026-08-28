/* iwpack.h — compact native game-pack format (".iwpack") for IWannaGym.
 *
 * This header is engine-agnostic: it defines the on-disk layout and a
 * bounds-checked decoder that resolves section offsets into typed pointers.
 * The engine-side integration (loading a pack into an IWanna env, room
 * switching) lives in iwanna.h, which includes this file.
 *
 * Design contract (docs/gamepack_format.md):
 *   - produced OFFLINE by `python -m tools.iwimport compile` from the
 *     inspectable canonical representation (.iwgame.json);
 *   - contiguous arrays, fixed-width little-endian records, precomputed
 *     offsets and per-pack maxima so the runtime allocates once at
 *     construction and never parses strings or allocates during stepping;
 *   - a trailing JSON metadata/provenance blob that the runtime never reads
 *     during stepping (inspection tools do).
 *
 * All offsets are byte offsets from the start of the pack. All records are
 * little-endian; fields are 4-byte-aligned so the decoder can point into
 * the blob directly on little-endian machines (x86/ARM); a byte-swapping
 * fallback is deliberately not provided — the loader rejects big-endian
 * hosts at runtime instead of silently misreading.
 */
#ifndef IWPACK_H
#define IWPACK_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define IWPACK_MAGIC 0x4B505749u /* "IWPK" little-endian */
/* v2: adds per-room static solid rects and killer shapes (exact import of
 * non-tile-aligned source collision), warp modes/extents, save difficulty
 * masks, and exact room pixel dimensions. v1 packs are rejected (packs are
 * build artifacts — recompile from the IR). */
#define IWPACK_VERSION 2u
#define IWPACK_VERSION_EXACT 3u  /* v3 = v2 + exact-behavior section
                                    (offset/length in reserved0/reserved1) */
#define IWPACK_MAX_FLAGS 64
#define IWPACK_EDGE_L 0
#define IWPACK_EDGE_R 1
#define IWPACK_EDGE_U 2
#define IWPACK_EDGE_D 3

/* physics_profile ids (docs/fidelity_contract.md; must match
 * iwanna_gym/gamepack/schema.py PHYSICS_PROFILES) */
#define IWPACK_PHYS_IWANNAGYM_RENEX 0   /* the only profile this runtime implements */

/* action_profile ids */
#define IWPACK_ACT_STANDARD6 0          /* {-1,0,+1} x {jump held} */

typedef struct {
    uint32_t magic;            /* IWPACK_MAGIC */
    uint32_t version;          /* IWPACK_VERSION */
    uint32_t total_size;       /* whole file, bytes */
    uint32_t n_rooms;
    uint32_t start_room;
    uint32_t n_flags;          /* global progression flags used (< IWPACK_MAX_FLAGS) */
    uint32_t physics_profile;  /* IWPACK_PHYS_* */
    uint32_t action_profile;   /* IWPACK_ACT_* */
    /* per-pack maxima: the runtime sizes its live buffers from these once */
    uint32_t max_tiles;        /* max tw*th over rooms */
    uint32_t max_spawns;
    uint32_t max_events;
    uint32_t max_actions;
    uint32_t max_solids;
    uint32_t max_killers;
    uint32_t rooms_off;        /* IWPackRoomRec[n_rooms] */
    uint32_t meta_off;         /* UTF-8 JSON metadata/provenance blob */
    uint32_t meta_len;
    uint32_t reserved0, reserved1, reserved2;
} IWPackHeader;                /* 80 bytes */

/* Static solid collider (GM-style inclusive integer bbox, stored as f32).
 * Used for source solids that are not exactly representable on the 32px
 * tile grid (sub-tile solids, scaled/invisible solids, odd positions). */
typedef struct {
    float x0, y0, x1, y1;
} IWPackSolid;                 /* 16 bytes */

/* Static killer collider. shape 0 = rect (bbox mask); 1..4 = spike
 * triangle (apex at the top/bottom/left/right edge center of the bbox,
 * matching the standard fangame spike mask, generalized to any extent). */
#define IWPACK_KILL_RECT 0
#define IWPACK_KILL_SPIKE_UP 1
#define IWPACK_KILL_SPIKE_DOWN 2
#define IWPACK_KILL_SPIKE_LEFT 3
#define IWPACK_KILL_SPIKE_RIGHT 4
typedef struct {
    uint32_t shape;
    float x0, y0, x1, y1;
} IWPackKiller;                /* 20 bytes */

/* Fixed-width room record. Section offsets point at contiguous arrays. */
typedef struct {
    uint32_t tw, th;           /* tile grid dims (ceil of pixel dims / 32) */
    uint32_t pw, ph;           /* EXACT room pixel dims from the source */
    float start_x, start_y;    /* default entry position, room px */
    float goal_x, goal_y;      /* completion target (or shaping objective) */
    uint32_t has_goal;         /* 1 = reaching goal terminates with success */
    int32_t edge[4];           /* L,R,U,D room id for edge transitions; -1 none */
    uint32_t tiles_off;        /* uint8[tw*th] */
    uint32_t n_spawns, spawns_off;   /* IWPackEnt[n_spawns] */
    uint32_t n_events, events_off;   /* IWPackEvt[n_events] */
    uint32_t n_actions, actions_off; /* IWPackAct[n_actions] */
    uint32_t n_solids, solids_off;   /* IWPackSolid[n_solids] */
    uint32_t n_killers, killers_off; /* IWPackKiller[n_killers] */
} IWPackRoomRec;               /* 100 bytes */

/* Mirrors the runtime IWEntity spawn template (type widened to u32). */
typedef struct {
    uint32_t type;
    uint32_t flags;
    int32_t trigger_id;
    int32_t tag;
    uint32_t collision_mask;
    float x, y, vx, vy, grav;
    int32_t state, timer;
    float params[6];
} IWPackEnt;                   /* 72 bytes */

/* Mirrors the immutable part of the runtime IWEvent. */
typedef struct {
    uint32_t when, once, auto_arm;
    int32_t dir, id, subject;
    float x0, y0, x1, y1;
    int32_t delay, period, first_action, n_actions;
} IWPackEvt;                   /* 56 bytes */

/* Mirrors the runtime IWAction. */
typedef struct {
    uint32_t type;
    int32_t tag;
    float p[6];
} IWPackAct;                   /* 32 bytes */

/* Decoded view: typed pointers into one owned blob. */
typedef struct {
    uint32_t tw, th;
    uint32_t pw, ph;
    float start_x, start_y, goal_x, goal_y;
    uint32_t has_goal;
    int32_t edge[4];
    const uint8_t* tiles;
    const IWPackEnt* spawns;   uint32_t n_spawns;
    const IWPackEvt* events;   uint32_t n_events;
    const IWPackAct* actions;  uint32_t n_actions;
    const IWPackSolid* solids; uint32_t n_solids;
    const IWPackKiller* killers; uint32_t n_killers;
} IWPackRoom;

typedef struct IWPackRT {
    uint8_t* blob;             /* owned copy of the pack file */
    size_t len;
    IWPackHeader hdr;
    IWPackRoom* rooms;         /* [hdr.n_rooms] */
    const char* meta;          /* JSON blob (not NUL-terminated); len = hdr.meta_len */
} IWPackRT;

static int iwpack_host_is_le(void) {
    uint32_t v = 1;
    return *(const uint8_t*)&v == 1;
}

static void iwpack_err(char* err, size_t errlen, const char* msg) {
    if (err && errlen) { strncpy(err, msg, errlen - 1); err[errlen - 1] = 0; }
}

static int iwpack_range_ok(size_t len, uint32_t off, size_t need) {
    return (size_t)off <= len && need <= len - (size_t)off;
}

/* Decode (and take a private copy of) a pack blob. Returns NULL + err on any
 * structural problem. All section bounds are validated here so the engine
 * never range-checks again. */
static IWPackRT* iwpack_load(const uint8_t* data, size_t len,
                             char* err, size_t errlen) {
    if (!iwpack_host_is_le()) { iwpack_err(err, errlen, "big-endian host unsupported"); return NULL; }
    if (!data || len < sizeof(IWPackHeader)) { iwpack_err(err, errlen, "pack too small"); return NULL; }
    IWPackHeader hdr;
    memcpy(&hdr, data, sizeof hdr);
    if (hdr.magic != IWPACK_MAGIC)   { iwpack_err(err, errlen, "bad magic (not an .iwpack)"); return NULL; }
    if (hdr.version != IWPACK_VERSION && hdr.version != IWPACK_VERSION_EXACT) { iwpack_err(err, errlen, "unsupported iwpack version"); return NULL; }
    if (hdr.total_size != len)       { iwpack_err(err, errlen, "size mismatch (truncated pack?)"); return NULL; }
    if (hdr.n_rooms == 0)            { iwpack_err(err, errlen, "pack has no rooms"); return NULL; }
    if (hdr.start_room >= hdr.n_rooms) { iwpack_err(err, errlen, "start_room out of range"); return NULL; }
    if (hdr.n_flags >= IWPACK_MAX_FLAGS) { iwpack_err(err, errlen, "too many global flags"); return NULL; }
    if (hdr.physics_profile != IWPACK_PHYS_IWANNAGYM_RENEX) {
        iwpack_err(err, errlen, "pack requires a physics profile this runtime does not implement");
        return NULL;
    }
    if (hdr.action_profile != IWPACK_ACT_STANDARD6) {
        iwpack_err(err, errlen, "pack requires an action profile this runtime does not implement");
        return NULL;
    }
    if (!iwpack_range_ok(len, hdr.rooms_off, (size_t)hdr.n_rooms * sizeof(IWPackRoomRec))) {
        iwpack_err(err, errlen, "room table out of bounds"); return NULL;
    }
    if (hdr.meta_len && !iwpack_range_ok(len, hdr.meta_off, hdr.meta_len)) {
        iwpack_err(err, errlen, "metadata blob out of bounds"); return NULL;
    }

    IWPackRT* rt = (IWPackRT*)calloc(1, sizeof(IWPackRT));
    if (!rt) { iwpack_err(err, errlen, "out of memory"); return NULL; }
    rt->blob = (uint8_t*)malloc(len);
    rt->rooms = (IWPackRoom*)calloc(hdr.n_rooms, sizeof(IWPackRoom));
    if (!rt->blob || !rt->rooms) {
        free(rt->blob); free(rt->rooms); free(rt);
        iwpack_err(err, errlen, "out of memory"); return NULL;
    }
    memcpy(rt->blob, data, len);
    rt->len = len;
    rt->hdr = hdr;
    rt->meta = hdr.meta_len ? (const char*)(rt->blob + hdr.meta_off) : "";

    const IWPackRoomRec* recs = (const IWPackRoomRec*)(rt->blob + hdr.rooms_off);
    for (uint32_t i = 0; i < hdr.n_rooms; i++) {
        const IWPackRoomRec* rr = &recs[i];
        IWPackRoom* r = &rt->rooms[i];
        size_t ntiles = (size_t)rr->tw * rr->th;
        if (rr->tw == 0 || rr->th == 0 || ntiles > hdr.max_tiles ||
            rr->n_spawns > hdr.max_spawns || rr->n_events > hdr.max_events ||
            rr->n_actions > hdr.max_actions ||
            rr->n_solids > hdr.max_solids || rr->n_killers > hdr.max_killers ||
            !iwpack_range_ok(len, rr->tiles_off, ntiles) ||
            !iwpack_range_ok(len, rr->spawns_off, (size_t)rr->n_spawns * sizeof(IWPackEnt)) ||
            !iwpack_range_ok(len, rr->events_off, (size_t)rr->n_events * sizeof(IWPackEvt)) ||
            !iwpack_range_ok(len, rr->actions_off, (size_t)rr->n_actions * sizeof(IWPackAct)) ||
            !iwpack_range_ok(len, rr->solids_off, (size_t)rr->n_solids * sizeof(IWPackSolid)) ||
            !iwpack_range_ok(len, rr->killers_off, (size_t)rr->n_killers * sizeof(IWPackKiller))) {
            free(rt->blob); free(rt->rooms); free(rt);
            iwpack_err(err, errlen, "room section out of bounds"); return NULL;
        }
        for (int k = 0; k < 4; k++) {
            if (rr->edge[k] >= (int32_t)hdr.n_rooms) {
                free(rt->blob); free(rt->rooms); free(rt);
                iwpack_err(err, errlen, "edge link out of range"); return NULL;
            }
        }
        r->tw = rr->tw; r->th = rr->th;
        r->pw = rr->pw ? rr->pw : rr->tw * 32u;
        r->ph = rr->ph ? rr->ph : rr->th * 32u;
        r->start_x = rr->start_x; r->start_y = rr->start_y;
        r->goal_x = rr->goal_x;   r->goal_y = rr->goal_y;
        r->has_goal = rr->has_goal;
        memcpy(r->edge, rr->edge, sizeof r->edge);
        r->tiles   = rt->blob + rr->tiles_off;
        r->spawns  = (const IWPackEnt*)(rt->blob + rr->spawns_off);
        r->n_spawns = rr->n_spawns;
        r->events  = (const IWPackEvt*)(rt->blob + rr->events_off);
        r->n_events = rr->n_events;
        r->actions = (const IWPackAct*)(rt->blob + rr->actions_off);
        r->n_actions = rr->n_actions;
        r->solids  = (const IWPackSolid*)(rt->blob + rr->solids_off);
        r->n_solids = rr->n_solids;
        r->killers = (const IWPackKiller*)(rt->blob + rr->killers_off);
        r->n_killers = rr->n_killers;
        /* events must reference actions inside this room's pool */
        for (uint32_t e = 0; e < rr->n_events; e++) {
            const IWPackEvt* ev = &r->events[e];
            if (ev->first_action < 0 || ev->n_actions < 0 ||
                (uint32_t)(ev->first_action + ev->n_actions) > rr->n_actions) {
                free(rt->blob); free(rt->rooms); free(rt);
                iwpack_err(err, errlen, "event action slice out of range"); return NULL;
            }
        }
    }
    return rt;
}

static void iwpack_free_rt(IWPackRT* rt) {
    if (!rt) return;
    free(rt->blob);
    free(rt->rooms);
    free(rt);
}

static IWPackRT* iwpack_load_file(const char* path, char* err, size_t errlen) {
    FILE* f = fopen(path, "rb");
    if (!f) { iwpack_err(err, errlen, "cannot open pack file"); return NULL; }
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (n <= 0) { fclose(f); iwpack_err(err, errlen, "empty pack file"); return NULL; }
    uint8_t* buf = (uint8_t*)malloc((size_t)n);
    if (!buf) { fclose(f); iwpack_err(err, errlen, "out of memory"); return NULL; }
    size_t rd = fread(buf, 1, (size_t)n, f);
    fclose(f);
    IWPackRT* rt = (rd == (size_t)n) ? iwpack_load(buf, (size_t)n, err, errlen) : NULL;
    if (rd != (size_t)n) iwpack_err(err, errlen, "short read on pack file");
    free(buf);
    return rt;
}

#endif /* IWPACK_H */
