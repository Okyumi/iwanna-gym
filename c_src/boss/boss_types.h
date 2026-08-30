/* boss_types.h — compact native records for the boss framework.
 *
 * Included by exact.h BEFORE IWXState so the state struct can embed the
 * boss slots.  A "boss" is an exact-layer entity (XB_BOSS_*) that owns one
 * IWXBossState slot; the slot carries everything the source object kept in
 * instance variables: hit points / cumulative damage, phase, the master
 * frame timer, GM-style alarms, per-boss scalars, and the indices of its
 * weak-point entities (hidden XB_WEAKBOX xents whose masks are the source
 * hitbox sprites).
 *
 * When a room contains no boss, n_boss == 0 and every boss hook in the
 * engine is behind that single check — ordinary rooms pay one integer
 * compare per frame (bullet path) and nothing per entity.
 */
#ifndef IWX_BOSS_TYPES_H
#define IWX_BOSS_TYPES_H

#include <stdint.h>

#define IWXB_MAX        4     /* live bosses per room (source max: 1) */
#define IWXB_ALARMS     8     /* GM alarm[0..7] */
#define IWXB_WEAK       3     /* weak points per boss (Birdo: 3 stages) */
#define IWXB_SPAWN_KEEP 16    /* xent slots visual spawns must leave free */

/* boss definition ids (which step function drives the slot) */
enum { IWXB_DEF_NONE = 0, IWXB_DEF_TEST, IWXB_DEF_BIRDO,
       IWXB_DEF_KRAIDGIEF, IWXB_DEF_TYSON, IWXB_DEF_DRACULA,
       IWXB_DEF_CLOWNCAR, IWXB_DEF_MOMMY, IWXB_DEF_DRAGON,
       IWXB_DEF_GUYFIRST, IWXB_DEF_GUYHEAD };

/* shared slot flags (per-boss bits start at IWXB_F_USER) */
enum {
    IWXB_F_VULN   = 1u << 0,   /* body damage window open */
    IWXB_F_DEAD   = 1u << 1,   /* death/completion sequence running */
    IWXB_F_INTRO  = 1u << 2,   /* arena intro running */
    IWXB_F_PUSH   = 1u << 3,   /* router consumes bullets on weak points */
    IWXB_F_USER   = 1u << 4,
};

typedef struct {
    uint8_t  used;             /* slot allocated */
    uint8_t  def;              /* IWXB_DEF_* */
    int16_t  sprite;           /* per-boss animation-state enum (exported) */
    int32_t  ent;              /* body xent index */
    int32_t  phase;
    int32_t  timer;            /* the source master timer (timer / t) */
    int32_t  alarm[IWXB_ALARMS];   /* <0 idle, 0 firing this frame */
    float    hp;               /* current stage hit points (down counter) */
    float    dmg;              /* cumulative body damage (up counter) */
    int32_t  wp_ent[IWXB_WEAK];    /* weak-point xent index (-1 none) */
    float    wp_dmg[IWXB_WEAK];    /* damage routed in since last consume */
    float    p[10];            /* per-boss scalars (documented per boss) */
    uint32_t f;                /* IWXB_F_* */
} IWXBossState;                /* 148 bytes */

#endif /* IWX_BOSS_TYPES_H */
