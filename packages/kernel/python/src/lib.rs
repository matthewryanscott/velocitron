//! The prover's fast path: explore one net from the tables the reference
//! explorer fills (`velocitron_analysis.tables`), visiting markings in the
//! reference's order, on every core or on one (`Explorer::explore`).
//!
//! The tables say what each rule of the net means for each token (an arc's
//! test, a correlate per pair, each binding's tokens taken and made, a
//! timer's hold and maturity); this module owns only the explorer's own
//! bookkeeping, as `soundness.Explorer._expand` and `_add` do it: binding
//! enumeration in the engine's order, priorities, firing caps, the relevance
//! fixed point, record postponement, the start rule, arrivals and updates
//! with their counts, the arrival wait, clock advances, successor keys,
//! dedupe and the graph.
//!
//! Before the run the tables hold the roles and the rows of the run's first
//! tokens. Every other row is filled on first use (D14): the kernel asks the
//! reference's `Rows` for it, in the same process, the first time a marking
//! needs it, and keeps it. A row that makes a new token brings that token's
//! rows with it.
//!
//! A row the reference cannot fill, or any other surprise, fails the run
//! with a `KernelError`; the kernel never guesses a rule.
//!
//! The explorer is split by who may change what: `Rules`, the net's rules,
//! never change; `Known`, the rows filled and the counts of uses met, and
//! `Store`, the graph, change only on the thread that merges; a `View` of
//! the three expands a marking on any thread into an `Out`, and stops with
//! a `Need` where `Known` lacks something.

use hashbrown::HashTable;
use pyo3::create_exception;
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use rayon::prelude::*;
use rustc_hash::{FxHashMap, FxHasher};
use std::hash::{Hash, Hasher};
use std::ops::Range;
use std::sync::Mutex;

create_exception!(velocitron_kernel, KernelError, PyException);

/// The most binding arcs one transition may have.
const MAXB: usize = 6;
const NONE: u16 = u16::MAX;
/// How many markings the kernel expands between two calls to the progress
/// line's `tick`: often enough to keep its ten seconds, rare enough that
/// taking the GIL costs nothing a run would see.
const PROGRESS_EVERY: usize = 256;

type BKey = [u16; MAXB];
type Fail = String;

// ── Tables, as the reference passes them ───────────────────────────────

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ArcT {
    place: usize,
    test: usize,
    corr: Option<usize>,
}

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct TimerT {
    clock: usize,
    bind: Vec<usize>,
    maturity: bool,
}

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct TransitionT {
    priority: i64,
    cap: Option<(usize, u32)>,
    record_move: bool,
    binding: Vec<ArcT>,
    inhibit: Vec<ArcT>,
    timer: Option<TimerT>,
    needs: u64,
    inputs: u64,
    outputs: u64,
    /// The places of the clock copies the timer's maturity reads.
    copies: Vec<usize>,
}

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct CorrT {
    /// The binding arc whose token the correlate reads, if any.
    anchor: Option<usize>,
}

/// One token's rows: its test per arc test, its reader class per place,
/// per timed transition whether each clock copy holds a listed time, and
/// the time it shows if it is a clock token.
type TokenRowT = (Vec<bool>, Vec<u32>, Vec<Vec<bool>>, Option<u32>);
/// The rows of the tokens and the times a filled row made.
type UpdateT = (Vec<TokenRowT>, Vec<f64>);
type EffectT = Option<(Vec<(usize, u16)>, Vec<(usize, u16)>)>;

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct ClockT {
    place: usize,
    listed: Vec<u32>,
}

#[derive(FromPyObject)]
#[pyo3(from_item_all)]
struct TablesT {
    places: usize,
    transitions: Vec<TransitionT>,
    tests: usize,
    corrs: Vec<CorrT>,
    update: UpdateT,
    clocks: Vec<ClockT>,
    open: u64,
    start: u64,
    records: u64,
    read_only: u64,
    entered: u64,
    sinks: u64,
    final_places: u64,
    by_name: Vec<usize>,
    injections: Vec<u32>,
    updates: Vec<u32>,
    env_tokens: Vec<Vec<u16>>,
    counted: Vec<(usize, usize)>,
    record_groups: Vec<(u64, Vec<usize>)>,
    place_users: Vec<(usize, Vec<usize>)>,
    postpone: bool,
    wait_arrivals: bool,
    priority_mode: bool,
    starts: u32,
    final_markings: Vec<Vec<usize>>,
    used_keys: Vec<(String, Option<usize>)>,
    uid_start: Option<usize>,
    uid_inject: Vec<Option<usize>>,
    uid_update: Vec<Option<usize>>,
    initial: Vec<Vec<u16>>,
    initial_used: Vec<(usize, u32)>,
}

// ── The kernel's own shapes ─────────────────────────────────────────────

struct Arc {
    place: usize,
    test: usize,
    corr: Option<usize>,
}

struct Timer {
    clock: usize,
    bind: Vec<usize>,
    maturity: bool,
}

struct Tr {
    priority: i64,
    cap: Option<(u16, u32)>,
    record_move: bool,
    binding: Vec<Arc>,
    inhibit: Vec<Arc>,
    timer: Option<Timer>,
    needs: u64,
    inputs: u64,
    outputs: u64,
    shared: bool,
    copies: Vec<usize>,
}

/// The rows filled so far, keyed as the kernel asks for them.
#[derive(Default)]
struct Rows {
    ntok: usize,
    /// [arc test][token]
    tests: Vec<Vec<bool>>,
    /// [correlate] (token, anchor token or NONE) → passes
    corrs: Vec<FxHashMap<(u16, u16), bool>>,
    fires: FxHashMap<(u16, BKey), u32>,
    fire_rows: Vec<Vec<Option<Alt>>>,
    holds: FxHashMap<(u16, u16, BKey), (bool, Option<u32>)>,
    values: Vec<f64>,
    /// [token] the time a clock token shows
    clock_now: Vec<Option<u32>>,
    tick_tokens: FxHashMap<(u16, u32), u16>,
    /// [place][token] reader class
    classes: Vec<Vec<u32>>,
    /// [transition][copy][token] whether the copy holds a listed time
    copies: Vec<Vec<Vec<bool>>>,
}

impl Rows {
    /// Take in the rows of the tokens and times a filled row made.
    fn take(&mut self, (tokens, values): UpdateT) -> Result<(), Fail> {
        for (tests, classes, copies, now) in tokens {
            if self.ntok + 1 >= NONE as usize {
                return Err(format!("the run met {} tokens; the kernel holds fewer than {NONE}", self.ntok + 1));
            }
            if tests.len() != self.tests.len() || classes.len() != self.classes.len() || copies.len() != self.copies.len() {
                return Err(format!("token {}'s rows do not fit the tables", self.ntok));
            }
            for (row, ok) in self.tests.iter_mut().zip(tests) {
                row.push(ok);
            }
            for (row, class) in self.classes.iter_mut().zip(classes) {
                row.push(class);
            }
            for (rows, oks) in self.copies.iter_mut().zip(copies) {
                if rows.len() != oks.len() {
                    return Err(format!("token {}'s copy rows do not fit the tables", self.ntok));
                }
                for (row, ok) in rows.iter_mut().zip(oks) {
                    row.push(ok);
                }
            }
            self.clock_now.push(now);
            self.ntok += 1;
        }
        self.values.extend(values);
        Ok(())
    }
}

#[derive(Clone)]
struct Alt {
    removed: Vec<(usize, u16)>,
    added: Vec<(usize, u16)>,
}

#[derive(Clone, Copy)]
enum KeyKind {
    Start,
    Fire,
    Place(usize),
}

#[derive(Default)]
struct Used {
    vecs: Vec<Vec<(u16, u32)>>,
    ids: FxHashMap<Vec<(u16, u32)>, u32>,
    inc: FxHashMap<(u32, u16), u32>,
}

impl Used {
    fn intern(&mut self, v: Vec<(u16, u32)>) -> u32 {
        if let Some(&id) = self.ids.get(&v) {
            return id;
        }
        let id = self.vecs.len() as u32;
        self.vecs.push(v.clone());
        self.ids.insert(v, id);
        id
    }
    fn get(&self, id: u32, key: u16) -> u32 {
        self.vecs[id as usize]
            .iter()
            .find(|(k, _)| *k == key)
            .map(|(_, v)| *v)
            .unwrap_or(0)
    }
    fn inc(&mut self, id: u32, key: u16) -> u32 {
        if let Some(&n) = self.inc.get(&(id, key)) {
            return n;
        }
        let n = self.intern(self.bumped(id, key));
        self.inc.insert((id, key), n);
        n
    }
    /// The counts of ``id`` with one more use of ``key``.
    fn bumped(&self, id: u32, key: u16) -> Vec<(u16, u32)> {
        let mut v = self.vecs[id as usize].clone();
        match v.iter_mut().find(|(k, _)| *k == key) {
            Some(e) => e.1 += 1,
            None => {
                v.push((key, 1));
                v.sort();
            }
        }
        v
    }
}

/// A working marking: per place, its token ids in list order.
#[derive(Clone, Default)]
struct Flat {
    start: Vec<u32>,
    toks: Vec<u16>,
}

impl Flat {
    #[inline]
    fn list(&self, p: usize) -> &[u16] {
        &self.toks[self.start[p] as usize..self.start[p + 1] as usize]
    }
    fn mask(&self, np: usize) -> u64 {
        let mut m = 0u64;
        for p in 0..np {
            if self.start[p + 1] > self.start[p] {
                m |= 1 << p;
            }
        }
        m
    }
    /// ``self`` with ``place`` holding just ``tok``.
    fn set_one(&self, np: usize, place: usize, tok: u16, out: &mut Flat) {
        out.start.clear();
        out.toks.clear();
        out.start.push(0);
        for p in 0..np {
            if p == place {
                out.toks.push(tok);
            } else {
                out.toks.extend_from_slice(self.list(p));
            }
            out.start.push(out.toks.len() as u32);
        }
    }
}

fn fx(data: &[u16]) -> u64 {
    let mut h = FxHasher::default();
    data.hash(&mut h);
    h.finish()
}

#[derive(Clone, Copy, PartialEq, Eq, Hash)]
enum MoveKey {
    Fire(u32, u16),
    Inject(u16, u16),
    Update(u16, u16),
    Advance(u16, u16),
}

const NET: u8 = 0;
const ARRIVAL: u8 = 1;
const UPDATE: u8 = 2;
const RECORD: u8 = 3;

/// What one step of the binding walk found.
#[derive(Clone, Copy, PartialEq)]
enum Step {
    Viable,
    TimerHold,
}

/// The net's rules, as the tables give them: nothing here changes once the
/// run starts.
struct Rules {
    np: usize,
    trs: Vec<Tr>,
    /// [correlate] the binding arc whose token it reads
    anchors: Vec<Option<usize>>,
    listed: Vec<Vec<u32>>,
    clocks: u64,
    timed: Vec<Vec<usize>>,
    open: u64,
    start_p: u64,
    records: u64,
    read_only: u64,
    entered: u64,
    sinks: u64,
    final_: u64,
    by_name: Vec<usize>,
    inj_limit: Vec<u32>,
    upd_limit: Vec<u32>,
    env_tokens: Vec<Vec<u16>>,
    counted: Vec<(usize, usize)>,
    record_groups: Vec<(u64, Vec<usize>)>,
    place_users: Vec<(usize, Vec<usize>)>,
    postpone: bool,
    wait_arrivals: bool,
    priority_mode: bool,
    starts: u32,
    final_markings: Vec<Vec<usize>>,
    key_kind: Vec<KeyKind>,
    uid_start: u16,
    uid_inject: Vec<u16>,
    uid_update: Vec<u16>,
}

impl Rules {
    /// `RoleSet.finished`: the marking covers `starts` final markings.
    fn finished(&self, m: &Flat) -> bool {
        let mut left: Vec<i64> = (0..self.np).map(|p| (m.start[p + 1] - m.start[p]) as i64).collect();
        fn fits(need: u32, first: usize, fms: &[Vec<usize>], left: &mut Vec<i64>) -> bool {
            if need == 0 {
                return true;
            }
            for i in first..fms.len() {
                let fm = &fms[i];
                if fm.iter().all(|&p| left[p] > 0) {
                    for &p in fm {
                        left[p] -= 1;
                    }
                    let found = fits(need - 1, i, fms, left);
                    for &p in fm {
                        left[p] += 1;
                    }
                    if found {
                        return true;
                    }
                }
            }
            false
        }
        fits(self.starts, 0, &self.final_markings, &mut left)
    }

    /// `Explorer._saturated`: a counted place keeps as many equal tokens as
    /// its readers count.
    fn saturate(&self, m: &Flat, out: &mut Flat) {
        out.start.clear();
        out.toks.clear();
        out.start.push(0);
        for p in 0..self.np {
            let l = m.list(p);
            let keep = self
                .counted
                .iter()
                .find(|(q, _)| *q == p)
                .map(|&(_, k)| k)
                .filter(|&k| l.len() > k && l.iter().all(|&x| x == l[0]));
            match keep {
                Some(k) => out.toks.extend_from_slice(&l[..k]),
                None => out.toks.extend_from_slice(l),
            }
            out.start.push(out.toks.len() as u32);
        }
    }

    #[inline]
    fn used_up(&self, t: usize, used: u32, uses: &Used) -> bool {
        match self.trs[t].cap {
            Some((k, limit)) => uses.get(used, k) >= limit,
            None => false,
        }
    }

    #[inline]
    fn can_arrive(&self, p: usize, used: u32, uses: &Used) -> bool {
        if self.clocks >> p & 1 == 1 {
            true
        } else if self.start_p >> p & 1 == 1 {
            uses.get(used, self.uid_start) < self.starts
        } else {
            uses.get(used, self.uid_inject[p]) < self.inj_limit[p]
        }
    }
}

/// What the run has learned so far: the rows the reference filled and the
/// counts of uses the run has met. Only `Explorer::resolve` adds to it, one
/// need at a time in the order the markings meet them, so every id in it is
/// the one a run on one core gives.
#[derive(Default)]
struct Known {
    rows: Rows,
    used: Used,
}

/// What `Rules::relevance` finds: the relevant open places, the live
/// places, and the counts of uses the key keeps.
type Relevance = (u64, u64, Vec<(u16, u32)>);

impl Rules {
    /// `Explorer._relevance` for (marked, used), the counts the key keeps
    /// as a vector, not yet an id.
    fn relevance(&self, uses: &Used, mask: u64, used: u32) -> Relevance {
        let mut available = mask;
        for p in 0..self.np {
            if self.open >> p & 1 == 1 && self.can_arrive(p, used, uses) {
                available |= 1 << p;
            }
        }
        let nt = self.trs.len();
        let mut possible = vec![false; nt];
        let mut changed = true;
        while changed {
            changed = false;
            for t in 0..nt {
                if possible[t] || self.used_up(t, used, uses) {
                    continue;
                }
                if self.trs[t].needs & !available == 0 {
                    possible[t] = true;
                    available |= self.trs[t].outputs;
                    changed = true;
                }
            }
        }
        let mut relevant = 0u64;
        for t in 0..nt {
            if possible[t] {
                relevant |= self.trs[t].inputs & self.open;
            }
        }
        let all = if self.np == 64 { u64::MAX } else { (1u64 << self.np) - 1 };
        let live = (all & !self.open & !(self.sinks & !self.final_)) | relevant;
        let counted = uses.vecs[used as usize]
            .iter()
            .copied()
            .filter(|&(k, _)| match self.key_kind[k as usize] {
                KeyKind::Start | KeyKind::Fire => true,
                KeyKind::Place(p) => relevant >> p & 1 == 1,
            })
            .collect();
        (relevant, live, counted)
    }

    /// `Explorer._waiting`: records no transition can use yet.
    fn waiting(&self, mask: u64) -> u64 {
        let other = self.records | self.clocks;
        let mut w = 0;
        for (members, users) in &self.record_groups {
            if !users.is_empty() && !users.iter().any(|&u| self.trs[u].needs & !other & !mask == 0) {
                w |= members;
            }
        }
        w
    }

    /// `Explorer._waiting_arrivals`: open places whose arrival waits, for
    /// the closed places marked.
    fn waiting_arrivals(&self, closed: u64) -> u64 {
        let mut w = 0;
        for (p, users) in &self.place_users {
            if !users.is_empty() && !users.iter().any(|&u| self.trs[u].needs & !self.open & !closed == 0) {
                w |= 1 << p;
            }
        }
        w
    }

    /// `Explorer._read_before_start`.
    fn read_before_start(&self, uses: &Used, mask: u64, used: u32) -> u64 {
        let mut available = mask;
        for p in 0..self.np {
            if ((self.open & !self.start_p) >> p) & 1 == 1 && self.can_arrive(p, used, uses) {
                available |= 1 << p;
            }
        }
        let nt = self.trs.len();
        let mut possible = vec![false; nt];
        let mut changed = true;
        while changed {
            changed = false;
            for t in 0..nt {
                if possible[t] || self.used_up(t, used, uses) {
                    continue;
                }
                if self.trs[t].needs & !available == 0 {
                    possible[t] = true;
                    if self.trs[t].outputs & self.entered == 0 {
                        available |= self.trs[t].outputs;
                    }
                    changed = true;
                }
            }
        }
        let mut found = 0;
        for t in 0..nt {
            if possible[t] {
                found |= self.trs[t].inputs & self.open;
            }
        }
        found
    }
}

/// One worker's caches of the explorer's pure answers, as the reference
/// keeps them. An answer depends only on its key and on ids `Known` has
/// fixed, so each worker keeps its own and none is shared.
#[derive(Default)]
struct Memo {
    relevance: FxHashMap<(u64, u32), (u64, u64, u32)>,
    before_start: FxHashMap<(u64, u32), u64>,
    waiting: FxHashMap<u64, u64>,
    waiting_places: FxHashMap<u64, u64>,
    inc: FxHashMap<(u32, u16), u32>,
}

/// What a marking's expansion lacks from `Known`: a row only the reference
/// fills, or an id for a count of uses the run has not met. The expansion
/// stops at the first one, and `Explorer::resolve` adds it before the
/// marking is expanded again.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
enum Need {
    Corr(usize, u16, u16),
    Hold(usize, u16, BKey),
    Fire(usize, BKey, Option<u16>),
    Tick(usize, u16, u32),
    /// The counts the key of (marked, used) keeps.
    Relevance(u64, u32),
    /// ``used`` with one more use of a key.
    Inc(u32, u16),
}

/// Why an expansion stopped short.
#[derive(Debug)]
enum Stop {
    Need(Need),
    Fail(Fail),
}

impl From<Fail> for Stop {
    fn from(error: Fail) -> Self {
        Stop::Fail(error)
    }
}

impl From<Need> for Stop {
    fn from(need: Need) -> Self {
        Stop::Need(need)
    }
}

type Res<T> = Result<T, Stop>;

/// The graph so far: each state's marking and key, and the edges of the
/// states expanded.
#[derive(Default)]
struct Store {
    mk: Vec<u16>,
    mk_off: Vec<u32>,
    keys: Vec<u16>,
    key_off: Vec<u32>,
    hashes: Vec<u64>,
    used_of: Vec<u32>,
    flags: Vec<u8>, // 1 final, 2 expanded, 4 cut
    parent: Vec<(u32, u32)>,
    edge_move: Vec<u32>,
    edge_target: Vec<u32>,
    edge_kind: Vec<u8>,
    edge_range: Vec<(u32, u32)>,
    table: HashTable<u32>,
}

impl Store {
    fn len(&self) -> usize {
        self.hashes.len()
    }

    fn find(&self, h: u64, key: &[u16]) -> Option<u32> {
        let (keys, key_off) = (&self.keys, &self.key_off);
        self.table
            .find(h, |&i| &keys[key_off[i as usize] as usize..key_off[i as usize + 1] as usize] == key)
            .copied()
    }

    /// `Explorer._add`: the state keyed by ``key``; adds it if new.
    fn add(&mut self, h: u64, key: &[u16], runs: &[u16], used: u32, fin: bool, via: Option<(u32, u32)>) -> u32 {
        if let Some(i) = self.find(h, key) {
            return i;
        }
        let i = self.hashes.len() as u32;
        self.keys.extend_from_slice(key);
        self.key_off.push(self.keys.len() as u32);
        let hashes = &self.hashes;
        self.table.insert_unique(h, i, |&j| hashes[j as usize]);
        self.hashes.push(h);
        self.mk.extend_from_slice(runs);
        self.mk_off.push(self.mk.len() as u32);
        self.used_of.push(used);
        self.flags.push(if fin { 1 } else { 0 });
        self.parent.push(via.unwrap_or((u32::MAX, u32::MAX)));
        self.edge_range.push((0, 0));
        i
    }

    fn decode(&self, np: usize, i: usize, out: &mut Flat) {
        out.start.clear();
        out.toks.clear();
        let s = &self.mk[self.mk_off[i] as usize..self.mk_off[i + 1] as usize];
        let mut j = 0;
        let mut p = 0usize;
        out.start.push(0);
        while j < s.len() {
            let place = s[j] as usize;
            let n = s[j + 1] as usize;
            while p < place {
                out.start.push(out.toks.len() as u32);
                p += 1;
            }
            out.toks.extend_from_slice(&s[j + 2..j + 2 + n]);
            out.start.push(out.toks.len() as u32);
            p += 1;
            j += 2 + n;
        }
        while p < np {
            out.start.push(out.toks.len() as u32);
            p += 1;
        }
    }
}

/// A successor an expansion found: a state the graph held when the
/// expansion ran, or a new marking (an index into `Out::news`), which the
/// merge adds unless a marking merged before it added it first.
#[derive(Clone, Copy)]
enum Target {
    Held(u32),
    New(u32),
}

struct EdgeOut {
    key: MoveKey,
    kind: u8,
    target: Target,
}

struct NewOut {
    hash: u64,
    key: Range<usize>,
    runs: Range<usize>,
    used: u32,
    fin: bool,
}

/// What one marking's expansion found, as ranges of its `Out`.
struct Expanded {
    i: u32,
    stop: Option<Stop>,
    cut: bool,
    edges: Range<usize>,
    stopped: Range<usize>,
    withheld: Range<usize>,
    deposits: Range<usize>,
    held: Range<usize>,
}

/// The expansions of a run of consecutive markings, for the merge.
#[derive(Default)]
struct Out {
    done: Vec<Expanded>,
    edges: Vec<EdgeOut>,
    news: Vec<NewOut>,
    keys: Vec<u16>,
    runs: Vec<u16>,
    /// The capped transitions that cut a marking short.
    stopped: Vec<u16>,
    /// (transition, value) of each maturity left out.
    withheld: Vec<(u16, u32)>,
    /// (fire row, output) of each failed deposit.
    deposits: Vec<(u32, u16)>,
    /// The record moves held back.
    held: Vec<u16>,
}

impl Out {
    fn clear(&mut self) {
        self.done.clear();
        self.edges.clear();
        self.news.clear();
        self.keys.clear();
        self.runs.clear();
        self.stopped.clear();
        self.withheld.clear();
        self.deposits.clear();
        self.held.clear();
    }
}

/// One worker's buffers and caches.
#[derive(Default)]
struct Work {
    m: Flat,
    make: Make,
    walk: Walk,
}

/// What making a successor takes: its marking before and after
/// saturation, and the worker's caches.
#[derive(Default)]
struct Make {
    succ: Flat,
    sat: Flat,
    memo: Memo,
}

/// The buffers of the binding walk and the clock's ticks.
#[derive(Default)]
struct Walk {
    scratch: Flat,
    ticks: Vec<(usize, u16)>,
    /// `walk`'s binding candidates. No walk runs inside another, so one
    /// buffer serves them all.
    cands: Vec<u32>,
}

/// How many markings the every-core mode expands before it merges them.
const CHUNK: usize = 1 << 16;
/// How many markings one worker expands at a time.
const SHARE: usize = 64;
/// How many stale states make it worth expanding them again on every core
/// (`Explorer::explore_chunk`).
const REDO_AT_ONCE: usize = 4;

/// The run as one marking's expansion sees it: the rules, what is known so
/// far and the graph so far, none of which it changes. Workers share it
/// while they expand; everything an expansion finds goes to its `Out`.
#[derive(Clone, Copy)]
struct View<'a> {
    r: &'a Rules,
    k: &'a Known,
    g: &'a Store,
}

impl<'a> View<'a> {
    fn check_tokens(&self, m: &Flat) -> Result<(), Fail> {
        let ntok = self.k.rows.ntok;
        match m.toks.iter().find(|&&t| t as usize >= ntok) {
            Some(t) => Err(format!("token {t} is not in the tables")),
            None => Ok(()),
        }
    }

    #[inline]
    fn used_up(&self, t: usize, used: u32) -> bool {
        self.r.used_up(t, used, &self.k.used)
    }

    /// ``used`` with one more use of ``key``: an id `Known` holds, or the
    /// need for one.
    fn inc(&self, used: u32, key: u16, memo: &mut Memo) -> Res<u32> {
        if let Some(&n) = self.k.used.inc.get(&(used, key)).or_else(|| memo.inc.get(&(used, key))) {
            return Ok(n);
        }
        let n = *self.k.used.ids.get(&self.k.used.bumped(used, key)).ok_or(Need::Inc(used, key))?;
        memo.inc.insert((used, key), n);
        Ok(n)
    }

    /// `Explorer._relevance`: (relevant open places, live places, counted
    /// used id) per (marked, used).
    fn relevance(&self, mask: u64, used: u32, memo: &mut Memo) -> Res<(u64, u64, u32)> {
        if let Some(&found) = memo.relevance.get(&(mask, used)) {
            return Ok(found);
        }
        let (relevant, live, counted) = self.r.relevance(&self.k.used, mask, used);
        let counted = *self.k.used.ids.get(&counted).ok_or(Need::Relevance(mask, used))?;
        memo.relevance.insert((mask, used), (relevant, live, counted));
        Ok((relevant, live, counted))
    }

    fn waiting(&self, mask: u64, memo: &mut Memo) -> u64 {
        *memo.waiting.entry(mask).or_insert_with(|| self.r.waiting(mask))
    }

    fn waiting_arrivals(&self, mask: u64, memo: &mut Memo) -> u64 {
        let closed = mask & !self.r.open;
        *memo.waiting_places.entry(closed).or_insert_with(|| self.r.waiting_arrivals(closed))
    }

    fn read_before_start(&self, mask: u64, used: u32, memo: &mut Memo) -> u64 {
        *memo.before_start.entry((mask, used)).or_insert_with(|| self.r.read_before_start(&self.k.used, mask, used))
    }

    /// Whether `Known` holds what ``need`` asked for.
    fn knows(&self, need: &Need) -> bool {
        let (rows, uses) = (&self.k.rows, &self.k.used);
        match *need {
            Need::Corr(c, tok, anchor) => rows.corrs[c].contains_key(&(tok, anchor)),
            Need::Hold(t, c, b) => rows.holds.contains_key(&(t as u16, c, b)),
            Need::Fire(t, b, _) => rows.fires.contains_key(&(t as u16, b)),
            Need::Tick(_, c, v) => rows.tick_tokens.contains_key(&(c, v)),
            Need::Relevance(mask, used) => uses.ids.contains_key(&self.r.relevance(uses, mask, used).2),
            Need::Inc(used, key) => uses.inc.contains_key(&(used, key)) || uses.ids.contains_key(&uses.bumped(used, key)),
        }
    }

    #[inline]
    fn test(&self, test: usize, tok: u16) -> Result<bool, Fail> {
        self.k.rows.tests[test]
            .get(tok as usize)
            .copied()
            .ok_or_else(|| format!("arc test {test} has no row for token {tok}"))
    }

    fn corr(&self, c: usize, tok: u16, anchor: u16) -> Res<bool> {
        Ok(*self.k.rows.corrs[c].get(&(tok, anchor)).ok_or(Need::Corr(c, tok, anchor))?)
    }

    /// Transition ``t``'s timer with clock token ``c`` and ``bind`` bound:
    /// whether it holds, and the time it matures at.
    fn hold(&self, t: usize, c: u16, bind: &[u16]) -> Res<(bool, Option<u32>)> {
        let b = bkey(bind);
        Ok(*self.k.rows.holds.get(&(t as u16, c, b)).ok_or(Need::Hold(t, c, b))?)
    }

    /// The fire row of transition ``t`` with binding ``b``.
    fn fire_row(&self, t: usize, b: &BKey, clock: Option<u16>) -> Res<u32> {
        Ok(*self.k.rows.fires.get(&(t as u16, *b)).ok_or(Need::Fire(t, *b, clock))?)
    }

    /// The token clock token ``c`` in ``clock`` becomes at time ``v``.
    fn tick(&self, clock: usize, c: u16, v: u32) -> Res<u16> {
        Ok(*self.k.rows.tick_tokens.get(&(c, v)).ok_or(Need::Tick(clock, c, v))?)
    }

    #[inline]
    fn value(&self, v: u32) -> f64 {
        self.k.rows.values[v as usize]
    }

    /// `Engine._binding_candidates` for transition ``t`` on ``m``: calls
    /// ``f`` with each binding that passes every gate (`Viable`) or every
    /// gate but the timer's hold (`TimerHold`), in the engine's order, until
    /// ``f`` returns false.
    fn walk<F: FnMut(Step, &[u16]) -> Res<bool>>(&self, t: usize, m: &Flat, cands: &mut Vec<u32>, mut f: F) -> Res<()> {
        let tr = &self.r.trs[t];
        let clock_tok = match &tr.timer {
            Some(timer) => match m.list(timer.clock).first() {
                Some(&c) => Some(c),
                None => return Ok(()),
            },
            None => None,
        };
        for a in &tr.inhibit {
            if a.corr.is_none() {
                for &x in m.list(a.place) {
                    if self.test(a.test, x)? {
                        return Ok(());
                    }
                }
            }
        }
        let n = tr.binding.len();
        // Each binding arc's candidates (positions in its place's list), one
        // run after another.
        cands.clear();
        let mut from = [0usize; MAXB + 1];
        for (i, a) in tr.binding.iter().enumerate() {
            for (j, &x) in m.list(a.place).iter().enumerate() {
                if self.test(a.test, x)? {
                    cands.push(j as u32);
                }
            }
            from[i + 1] = cands.len();
            if from[i + 1] == from[i] {
                return Ok(());
            }
        }
        let mut idx = [0usize; MAXB];
        let mut toks = [NONE; MAXB];
        'product: loop {
            for i in 0..n {
                toks[i] = m.list(tr.binding[i].place)[cands[from[i] + idx[i]] as usize];
            }
            if self.binding_ok(tr, m, &toks[..n])? {
                let step = match (&tr.timer, clock_tok) {
                    (Some(timer), Some(c)) => {
                        let bind: Vec<u16> = timer.bind.iter().map(|&i| toks[i]).collect();
                        if self.hold(t, c, &bind)?.0 {
                            Step::Viable
                        } else {
                            Step::TimerHold
                        }
                    }
                    _ => Step::Viable,
                };
                if !f(step, &toks[..n])? {
                    return Ok(());
                }
            }
            if n == 0 {
                break;
            }
            let mut k = n;
            loop {
                if k == 0 {
                    break 'product;
                }
                k -= 1;
                idx[k] += 1;
                if idx[k] < from[k + 1] - from[k] {
                    break;
                }
                idx[k] = 0;
            }
        }
        Ok(())
    }

    /// The per-binding gates before the timer: sub-multiset, the correlate
    /// join, the correlated inhibits.
    fn binding_ok(&self, tr: &Tr, m: &Flat, toks: &[u16]) -> Res<bool> {
        let n = toks.len();
        if tr.shared {
            for i in 0..n {
                let place = tr.binding[i].place;
                let bound = (0..n).filter(|&j| tr.binding[j].place == place && toks[j] == toks[i]).count();
                let held = m.list(place).iter().filter(|&&x| x == toks[i]).count();
                if bound > held {
                    return Ok(false);
                }
            }
        }
        for i in 0..n {
            if let Some(c) = tr.binding[i].corr {
                let anchor = self.r.anchors[c].map(|a| toks[a]).unwrap_or(NONE);
                if !self.corr(c, toks[i], anchor)? {
                    return Ok(false);
                }
            }
        }
        for a in &tr.inhibit {
            if let Some(c) = a.corr {
                let anchor = self.r.anchors[c].map(|j| toks[j]).unwrap_or(NONE);
                for &x in m.list(a.place) {
                    if self.test(a.test, x)? && self.corr(c, x, anchor)? {
                        return Ok(false);
                    }
                }
            }
        }
        Ok(true)
    }

    /// The viable bindings of ``t``, as `Engine.reservations` lists them.
    fn bindings(&self, t: usize, m: &Flat, cands: &mut Vec<u32>, out: &mut Vec<BKey>) -> Res<()> {
        out.clear();
        self.walk(t, m, cands, |step, toks| {
            if step == Step::Viable {
                out.push(bkey(toks));
            }
            Ok(true)
        })
    }

    fn can_fire(&self, t: usize, m: &Flat, cands: &mut Vec<u32>) -> Res<bool> {
        let mut found = false;
        self.walk(t, m, cands, |step, _| {
            if step == Step::Viable {
                found = true;
                return Ok(false);
            }
            Ok(true)
        })?;
        Ok(found)
    }

    fn apply(&self, m: &Flat, key: MoveKey, out: &mut Flat) {
        out.start.clear();
        out.toks.clear();
        out.start.push(0);
        for p in 0..self.r.np {
            match key {
                MoveKey::Fire(row, a) => {
                    let alt = self.k.rows.fire_rows[row as usize][a as usize].as_ref().unwrap();
                    let at = out.toks.len();
                    out.toks.extend_from_slice(m.list(p));
                    for &(rp, t) in &alt.removed {
                        if rp == p {
                            if let Some(pos) = out.toks[at..].iter().position(|&x| x == t) {
                                out.toks.remove(pos + at);
                            }
                        }
                    }
                    for &(ap, t) in &alt.added {
                        if ap == p {
                            out.toks.push(t);
                        }
                    }
                }
                MoveKey::Inject(ip, t) => {
                    out.toks.extend_from_slice(m.list(p));
                    if ip as usize == p {
                        out.toks.push(t);
                    }
                }
                MoveKey::Update(up, t) | MoveKey::Advance(up, t) => {
                    if up as usize == p {
                        out.toks.push(t);
                    } else {
                        out.toks.extend_from_slice(m.list(p));
                    }
                }
            }
            out.start.push(out.toks.len() as u32);
        }
    }

    /// The state ``m`` with ``used`` keys to: one the graph holds, or a new
    /// one, its key and marking put in ``out``.
    fn successor(&self, m: &Flat, used: u32, memo: &mut Memo, out: &mut Out) -> Res<Target> {
        let np = self.r.np;
        let mask = m.mask(np);
        let (_, live, counted) = self.relevance(mask, used, memo)?;
        let at = out.keys.len();
        let keep = live & mask;
        for p in 0..np {
            if keep >> p & 1 == 1 {
                let l = m.list(p);
                out.keys.push(p as u16);
                out.keys.push(l.len() as u16);
                let from = out.keys.len();
                out.keys.extend_from_slice(l);
                out.keys[from..].sort_unstable();
            }
        }
        out.keys.push((counted >> 16) as u16);
        out.keys.push(counted as u16);
        let h = fx(&out.keys[at..]);
        if let Some(i) = self.g.find(h, &out.keys[at..]) {
            out.keys.truncate(at);
            return Ok(Target::Held(i));
        }
        let runs_at = out.runs.len();
        for p in 0..np {
            let l = m.list(p);
            if !l.is_empty() {
                out.runs.push(p as u16);
                out.runs.push(l.len() as u16);
                out.runs.extend_from_slice(l);
            }
        }
        out.news.push(NewOut {
            hash: h,
            key: at..out.keys.len(),
            runs: runs_at..out.runs.len(),
            used,
            fin: self.r.finished(m),
        });
        Ok(Target::New(out.news.len() as u32 - 1))
    }

    fn edge(&self, m: &Flat, used2: u32, key: MoveKey, kind: u8, mk: &mut Make, out: &mut Out) -> Res<()> {
        self.apply(m, key, &mut mk.succ);
        self.check_tokens(&mk.succ)?;
        self.r.saturate(&mk.succ, &mut mk.sat);
        let target = self.successor(&mk.sat, used2, &mut mk.memo, out)?;
        out.edges.push(EdgeOut { key, kind, target });
        Ok(())
    }

    #[allow(clippy::too_many_arguments)]
    fn fire(&self, m: &Flat, used: u32, t: usize, bs: &[BKey], kind: u8, mk: &mut Make, out: &mut Out) -> Res<()> {
        let used2 = match self.r.trs[t].cap {
            Some((k, _)) => self.inc(used, k, &mut mk.memo)?,
            None => used,
        };
        let clock = self.r.trs[t].timer.as_ref().and_then(|timer| m.list(timer.clock).first().copied());
        for b in bs {
            let row = self.fire_row(t, b, clock)?;
            let alts = &self.k.rows.fire_rows[row as usize];
            for (a, alt) in alts.iter().enumerate() {
                if alt.is_none() {
                    out.deposits.push((row, a as u16));
                    continue;
                }
                self.edge(m, used2, MoveKey::Fire(row, a as u16), kind, mk, out)?;
            }
        }
        Ok(())
    }

    /// `Explorer._copies_listed`.
    fn copies_listed(&self, m: &Flat, t: usize) -> bool {
        self.r.trs[t]
            .copies
            .iter()
            .zip(&self.k.rows.copies[t])
            .all(|(&place, ok)| m.list(place).iter().all(|&x| ok[x as usize]))
    }

    /// `Explorer._ticks`: the clock tokens time moves to, and the
    /// maturities withheld here (transition, value).
    fn ticks(&self, m: &Flat, relevant: u64, w: &mut Walk, withheld: &mut Vec<(u16, u32)>) -> Res<()> {
        let r = self.r;
        w.ticks.clear();
        let mut ready = 0u64;
        for tr in &r.trs {
            if let Some(timer) = &tr.timer {
                if (0..r.np).all(|p| tr.needs >> p & 1 == 0 || !m.list(p).is_empty()) {
                    ready |= 1 << timer.clock;
                }
            }
        }
        for &clock in &r.by_name {
            if (r.clocks & relevant & ready) >> clock & 1 == 0 {
                continue;
            }
            let c = match m.list(clock).first() {
                Some(&c) => c,
                None => continue,
            };
            let nowi = match self.k.rows.clock_now[c as usize] {
                Some(v) => v,
                None => continue,
            };
            let now = self.value(nowi);
            // `_maturities`: per timed transition with a maturity on any
            // marked clock, the first binding whose timer does not hold.
            let mut found: Vec<u32> = Vec::new();
            for (t, tr) in r.trs.iter().enumerate() {
                let timer = match &tr.timer {
                    Some(x) if x.maturity && !m.list(x.clock).is_empty() => x,
                    _ => continue,
                };
                let tclock = timer.clock;
                if tclock != clock {
                    continue;
                }
                let ctok = m.list(tclock)[0];
                let mut first: Option<Vec<u16>> = None;
                self.walk(t, m, &mut w.cands, |step, toks| {
                    if step == Step::TimerHold {
                        first = Some(timer.bind.iter().map(|&i| toks[i]).collect());
                        return Ok(false);
                    }
                    Ok(true)
                })?;
                if let Some(bind) = first {
                    let (_, maturity) = self.hold(t, ctok, &bind)?;
                    if let Some(at) = maturity {
                        if self.value(at) <= now {
                            continue;
                        }
                        if self.copies_listed(m, t) {
                            if !found.iter().any(|&v| self.value(v) == self.value(at)) {
                                found.push(at);
                            }
                        } else {
                            withheld.push((t as u16, at));
                        }
                    }
                }
            }
            let mut later: Vec<u32> = Vec::new();
            for &v in &r.listed[clock] {
                if self.value(v) > now && !later.iter().any(|&w| self.value(w) == self.value(v)) {
                    later.push(v);
                }
            }
            for v in found {
                if !later.iter().any(|&w| self.value(w) == self.value(v)) {
                    later.push(v);
                }
            }
            if later.is_empty() {
                continue;
            }
            later.sort_by(|a, b| self.value(*a).partial_cmp(&self.value(*b)).unwrap());
            if r.postpone && !self.timer_can_fire(m, clock, c, nowi, &later, w)? {
                continue;
            }
            for v in later {
                let tok = self.tick(clock, c, v)?;
                w.ticks.push((clock, tok));
            }
        }
        Ok(())
    }

    /// `Explorer._timer_can_fire`.
    fn timer_can_fire(&self, m: &Flat, clock: usize, c: u16, nowi: u32, later: &[u32], w: &mut Walk) -> Res<bool> {
        let r = self.r;
        for &t in &r.timed[clock] {
            let needs = r.trs[t].needs;
            if !(0..r.np).all(|p| needs >> p & 1 == 0 || !m.list(p).is_empty()) {
                continue;
            }
            for &v in std::iter::once(&nowi).chain(later.iter()) {
                let tok = if v == nowi { c } else { self.tick(clock, c, v)? };
                m.set_one(r.np, clock, tok, &mut w.scratch);
                if self.can_fire(t, &w.scratch, &mut w.cands)? {
                    return Ok(true);
                }
            }
        }
        Ok(false)
    }

    /// Expand state ``i`` into ``out``: its edges and what it adds to the
    /// run's tallies, or, when it stops short, nothing but why.
    fn expand(&self, i: usize, w: &mut Work, out: &mut Out) {
        let at = (out.edges.len(), out.news.len(), out.keys.len(), out.runs.len());
        let tallies = (out.stopped.len(), out.withheld.len(), out.deposits.len(), out.held.len());
        let (stop, cut) = match self.expand_into(i, w, out) {
            Ok(cut) => (None, cut),
            Err(stop) => {
                out.edges.truncate(at.0);
                out.news.truncate(at.1);
                out.keys.truncate(at.2);
                out.runs.truncate(at.3);
                out.stopped.truncate(tallies.0);
                out.withheld.truncate(tallies.1);
                out.deposits.truncate(tallies.2);
                out.held.truncate(tallies.3);
                (Some(stop), false)
            }
        };
        out.done.push(Expanded {
            i: i as u32,
            stop,
            cut,
            edges: at.0..out.edges.len(),
            stopped: tallies.0..out.stopped.len(),
            withheld: tallies.1..out.withheld.len(),
            deposits: tallies.2..out.deposits.len(),
            held: tallies.3..out.held.len(),
        });
    }

    /// `Explorer._expand`; whether a firing cap cut the marking short.
    fn expand_into(&self, i: usize, w: &mut Work, out: &mut Out) -> Res<bool> {
        let r = self.r;
        let Work { m, make: mk, walk } = w;
        self.g.decode(r.np, i, m);
        let m = &*m;
        let used = self.g.used_of[i];
        let mask = m.mask(r.np);
        let edges_at = out.edges.len();
        let (relevant, _, _) = self.relevance(mask, used, &mut mk.memo)?;
        let mut enabled: Vec<(usize, Vec<BKey>)> = Vec::new();
        let mut record_moves: Vec<(usize, Vec<BKey>)> = Vec::new();
        let mut bs = Vec::new();
        for t in 0..r.trs.len() {
            self.bindings(t, m, &mut walk.cands, &mut bs)?;
            if !bs.is_empty() {
                let found = (t, std::mem::take(&mut bs));
                if r.trs[t].record_move {
                    record_moves.push(found);
                } else {
                    enabled.push(found);
                }
            }
        }
        if r.priority_mode && !enabled.is_empty() {
            let top = enabled.iter().map(|(t, _)| r.trs[*t].priority).max().unwrap();
            enabled.retain(|(t, _)| r.trs[*t].priority == top);
        }
        let mut cut = false;
        for (t, _) in enabled.iter().chain(record_moves.iter()) {
            if self.used_up(*t, used) {
                cut = true;
                out.stopped.push(*t as u16);
            }
        }
        enabled.retain(|(t, _)| !self.used_up(*t, used));
        record_moves.retain(|(t, _)| !self.used_up(*t, used));
        let busy = !enabled.is_empty();
        for (t, bs) in &enabled {
            self.fire(m, used, *t, bs, NET, mk, out)?;
        }
        self.ticks(m, relevant, walk, &mut out.withheld)?;
        let any_edges = out.edges.len() > edges_at;
        let (mut waiting, mut held) = (0u64, 0u64);
        if any_edges || !walk.ticks.is_empty() {
            if r.postpone {
                waiting = self.waiting(mask, &mut mk.memo);
            }
            if r.wait_arrivals {
                held = self.waiting_arrivals(mask, &mut mk.memo);
            }
        }
        for (t, bs) in &record_moves {
            let touched = r.trs[*t].inputs | r.trs[*t].outputs;
            if touched & !waiting == 0 {
                out.held.push(*t as u16);
                continue;
            }
            self.fire(m, used, *t, bs, RECORD, mk, out)?;
        }
        for k in 0..walk.ticks.len() {
            let (clock, tok) = walk.ticks[k];
            self.edge(m, used, MoveKey::Advance(clock as u16, tok), NET, mk, out)?;
        }
        let mut writable = relevant & !r.clocks;
        let started = r.start_p == 0 || mask & r.entered != 0 || (self.k.used.get(used, r.uid_start) > 0 && !busy);
        if !started {
            writable &= r.start_p | self.read_before_start(mask, used, &mut mk.memo);
        }
        for &p in &r.by_name {
            if writable >> p & 1 == 0 {
                continue;
            }
            if held >> p & 1 == 0 && r.can_arrive(p, used, &self.k.used) {
                let key = if r.start_p >> p & 1 == 1 { r.uid_start } else { r.uid_inject[p] };
                let used2 = self.inc(used, key, &mut mk.memo)?;
                for &tok in &r.env_tokens[p] {
                    self.edge(m, used2, MoveKey::Inject(p as u16, tok), ARRIVAL, mk, out)?;
                }
            }
            if r.read_only >> p & 1 == 1 && !m.list(p).is_empty() {
                let record = r.records >> p & 1 == 1;
                if record && waiting >> p & 1 == 1 {
                    continue;
                }
                if record || self.k.used.get(used, r.uid_update[p]) < r.upd_limit[p] {
                    let used2 = if record { used } else { self.inc(used, r.uid_update[p], &mut mk.memo)? };
                    let classes = &self.k.rows.classes[p];
                    let first = classes[m.list(p)[0] as usize];
                    let single = m.list(p).iter().all(|&x| classes[x as usize] == first);
                    let kind = if record { RECORD } else { UPDATE };
                    for &tok in &r.env_tokens[p] {
                        if single && classes[tok as usize] == first {
                            continue;
                        }
                        self.edge(m, used2, MoveKey::Update(p as u16, tok), kind, mk, out)?;
                    }
                }
            }
        }
        Ok(cut)
    }
}

struct Explorer {
    rules: Rules,
    known: Known,
    store: Store,
    /// The reference's `Rows`, which fills a row on first use.
    filler: Py<PyAny>,
    max_states: usize,
    moves: FxHashMap<MoveKey, u32>,
    move_list: Vec<MoveKey>,
    capped: bool,
    stopped: Vec<u32>,
    withheld: Vec<(u32, u16, u32)>,
    deposit_errors: Vec<(u32, u16)>,
    deposit_seen: FxHashMap<(u32, u16), ()>,
    held_moves: Vec<bool>,
}

fn bkey(toks: &[u16]) -> BKey {
    let mut k = [NONE; MAXB];
    k[..toks.len()].copy_from_slice(toks);
    k
}

/// Ask the reference to fill a row the tables lack, and take in the rows
/// of the tokens and times it made.
fn ask<R>(filler: &Py<PyAny>, rows: &mut Rows, what: &str, call: impl FnOnce(&Bound<'_, PyAny>) -> PyResult<(R, UpdateT)>) -> Result<R, Fail> {
    let got = Python::attach(|py| call(filler.bind(py)));
    let (row, update) = got.map_err(|e| format!("the reference could not fill {what}: {e}"))?;
    rows.take(update)?;
    Ok(row)
}

impl Explorer {
    fn new(t: TablesT, filler: Py<PyAny>, max_states: usize) -> Result<Self, Fail> {
        let np = t.places;
        if np > 64 {
            return Err(format!("the net has {np} places; the kernel holds at most 64"));
        }
        let mut trs = Vec::with_capacity(t.transitions.len());
        for tr in t.transitions {
            if tr.binding.len() > MAXB {
                return Err(format!("a transition has {} binding arcs; the kernel takes at most {MAXB}", tr.binding.len()));
            }
            let conv = |a: ArcT| Arc { place: a.place, test: a.test, corr: a.corr };
            let binding: Vec<Arc> = tr.binding.into_iter().map(conv).collect();
            let shared = (0..binding.len()).any(|i| (0..i).any(|j| binding[i].place == binding[j].place));
            trs.push(Tr {
                priority: tr.priority,
                cap: tr.cap.map(|(k, l)| (k as u16, l)),
                record_move: tr.record_move,
                binding,
                inhibit: tr.inhibit.into_iter().map(conv).collect(),
                timer: tr.timer.map(|x| Timer { clock: x.clock, bind: x.bind, maturity: x.maturity }),
                needs: tr.needs,
                inputs: tr.inputs,
                outputs: tr.outputs,
                shared,
                copies: tr.copies,
            });
        }
        let mut rows = Rows {
            tests: vec![Vec::new(); t.tests],
            corrs: vec![FxHashMap::default(); t.corrs.len()],
            classes: vec![Vec::new(); np],
            copies: trs.iter().map(|tr| vec![Vec::new(); tr.copies.len()]).collect(),
            ..Rows::default()
        };
        rows.take(t.update)?;
        let mut listed = vec![Vec::new(); np];
        let mut clocks = 0u64;
        for c in t.clocks {
            clocks |= 1 << c.place;
            listed[c.place] = c.listed;
        }
        let mut timed = vec![Vec::new(); np];
        for (i, tr) in trs.iter().enumerate() {
            if let Some(timer) = &tr.timer {
                timed[timer.clock].push(i);
            }
        }
        let key_kind = t
            .used_keys
            .iter()
            .map(|(name, place)| match (name.as_str(), place) {
                ("start", _) => KeyKind::Start,
                (_, Some(p)) => KeyKind::Place(*p),
                _ => KeyKind::Fire,
            })
            .collect();
        let mut used = Used::default();
        let init_used = used.intern(t.initial_used.iter().map(|&(k, n)| (k as u16, n)).collect());
        let opt = |x: Option<usize>| x.map(|v| v as u16).unwrap_or(NONE);
        let nt = trs.len();
        let mut ex = Explorer {
            rules: Rules {
                np,
                trs,
                anchors: t.corrs.iter().map(|c| c.anchor).collect(),
                listed,
                clocks,
                timed,
                open: t.open,
                start_p: t.start,
                records: t.records,
                read_only: t.read_only,
                entered: t.entered,
                sinks: t.sinks,
                final_: t.final_places,
                by_name: t.by_name,
                inj_limit: t.injections,
                upd_limit: t.updates,
                env_tokens: t.env_tokens,
                counted: t.counted,
                record_groups: t.record_groups,
                place_users: t.place_users,
                postpone: t.postpone,
                wait_arrivals: t.wait_arrivals,
                priority_mode: t.priority_mode,
                starts: t.starts,
                final_markings: t.final_markings,
                key_kind,
                uid_start: opt(t.uid_start),
                uid_inject: t.uid_inject.into_iter().map(opt).collect(),
                uid_update: t.uid_update.into_iter().map(opt).collect(),
            },
            known: Known { rows, used },
            store: Store { mk_off: vec![0], key_off: vec![0], ..Store::default() },
            filler,
            max_states,
            moves: FxHashMap::default(),
            move_list: Vec::new(),
            capped: false,
            stopped: vec![0; nt],
            withheld: Vec::new(),
            deposit_errors: Vec::new(),
            deposit_seen: FxHashMap::default(),
            held_moves: vec![false; nt],
        };
        let mut initial = Flat::default();
        initial.start.push(0);
        for p in 0..np {
            initial.toks.extend_from_slice(&t.initial[p]);
            initial.start.push(initial.toks.len() as u32);
        }
        let mut saturated = Flat::default();
        ex.rules.saturate(&initial, &mut saturated);
        let mut out = Out::default();
        ex.settle(&mut Work::default(), |v, w| {
            out.clear();
            v.check_tokens(&initial)?;
            v.successor(&saturated, init_used, &mut w.make.memo, &mut out)
        })?;
        ex.add_new(&out, 0, None);
        Ok(ex)
    }

    fn view(&self) -> View<'_> {
        View { r: &self.rules, k: &self.known, g: &self.store }
    }

    /// Run ``f`` until it no longer stops for a need, resolving each need
    /// it meets in the order it meets them.
    fn settle<T>(&mut self, w: &mut Work, mut f: impl FnMut(View<'_>, &mut Work) -> Res<T>) -> Result<T, Fail> {
        let mut last = None;
        loop {
            match f(self.view(), w) {
                Ok(found) => return Ok(found),
                Err(Stop::Fail(error)) => return Err(error),
                Err(Stop::Need(need)) => {
                    self.resolve(need, &mut last)?;
                }
            }
        }
    }

    /// Add what ``need`` lacks to `Known`: ask the reference for a row, or
    /// work out a cache entry. ``last`` is the need resolved before for the
    /// same marking; meeting it again is a fault, not a reason to loop.
    fn resolve(&mut self, need: Need, last: &mut Option<Need>) -> Result<(), Fail> {
        if *last == Some(need) {
            return Err(format!("the kernel met {need:?} again after it was resolved"));
        }
        *last = Some(need);
        let (r, k, filler) = (&self.rules, &mut self.known, &self.filler);
        match need {
            Need::Corr(c, tok, anchor) => {
                let a = (anchor != NONE).then_some(anchor);
                let ok: bool = ask(filler, &mut k.rows, "a correlate row", |f| Ok(f.call_method1("corr", (c, tok, a))?.extract()?))?;
                k.rows.corrs[c].insert((tok, anchor), ok);
            }
            Need::Hold(t, c, b) => {
                let bind: Vec<u16> = b.iter().copied().take_while(|&x| x != NONE).collect();
                let row: (bool, Option<u32>) = ask(filler, &mut k.rows, "a timer row", |f| {
                    let (holds, maturity, update): (bool, Option<u32>, UpdateT) = f.call_method1("timer", (t, c, bind))?.extract()?;
                    Ok(((holds, maturity), update))
                })?;
                k.rows.holds.insert((t as u16, c, b), row);
            }
            Need::Fire(t, b, clock) => {
                let combo = b[..r.trs[t].binding.len()].to_vec();
                let (row, alts): (u32, Vec<EffectT>) = ask(filler, &mut k.rows, "a fire row", |f| {
                    let (row, alts, update): (u32, Vec<EffectT>, UpdateT) = f.call_method1("fire", (t, combo, clock))?.extract()?;
                    Ok(((row, alts), update))
                })?;
                if row as usize != k.rows.fire_rows.len() {
                    return Err(format!("the reference numbered fire row {row}; the kernel expected {}", k.rows.fire_rows.len()));
                }
                k.rows.fire_rows.push(alts.into_iter().map(|a| a.map(|(removed, added)| Alt { removed, added })).collect());
                k.rows.fires.insert((t as u16, b), row);
            }
            Need::Tick(clock, c, v) => {
                let tok: u16 = ask(filler, &mut k.rows, "a tick row", |f| Ok(f.call_method1("tick", (clock, c, v))?.extract()?))?;
                k.rows.tick_tokens.insert((c, v), tok);
            }
            Need::Relevance(mask, used) => {
                let (_, _, counted) = r.relevance(&k.used, mask, used);
                k.used.intern(counted);
            }
            Need::Inc(used, key) => {
                k.used.inc(used, key);
            }
        }
        Ok(())
    }

    fn move_id(&mut self, k: MoveKey) -> u32 {
        if let Some(&id) = self.moves.get(&k) {
            return id;
        }
        let id = self.move_list.len() as u32;
        self.moves.insert(k, id);
        self.move_list.push(k);
        id
    }

    /// Add the ``n``th new marking of ``out``, unless the graph holds it.
    fn add_new(&mut self, out: &Out, n: usize, via: Option<(u32, u32)>) -> u32 {
        let s = &out.news[n];
        self.store.add(s.hash, &out.keys[s.key.clone()], &out.runs[s.runs.clone()], s.used, s.fin, via)
    }

    /// Put one marking's expansion into the graph, as `Explorer._expand`
    /// does as it goes.
    fn merge(&mut self, out: &Out, d: &Expanded) {
        let i = d.i;
        let start = self.store.edge_move.len() as u32;
        for &t in &out.stopped[d.stopped.clone()] {
            self.stopped[t as usize] += 1;
        }
        for e in &out.edges[d.edges.clone()] {
            let mv = self.move_id(e.key);
            let target = match e.target {
                Target::Held(j) => j,
                Target::New(n) => self.add_new(out, n as usize, Some((i, mv))),
            };
            self.store.edge_move.push(mv);
            self.store.edge_target.push(target);
            self.store.edge_kind.push(e.kind);
        }
        for &(t, at) in &out.withheld[d.withheld.clone()] {
            self.withheld.push((i, t, at));
        }
        for &found in &out.deposits[d.deposits.clone()] {
            if self.deposit_seen.insert(found, ()).is_none() {
                self.deposit_errors.push(found);
            }
        }
        for &t in &out.held[d.held.clone()] {
            self.held_moves[t as usize] = true;
        }
        let i = i as usize;
        self.store.edge_range[i] = (start, self.store.edge_move.len() as u32 - start);
        self.store.flags[i] |= 2 | if d.cut { 4 } else { 0 };
    }

    /// Expand state ``i`` on this thread, resolving each need it meets,
    /// and merge it. ``resolved`` hears each need resolved.
    fn expand_here(&mut self, i: usize, w: &mut Work, out: &mut Out, resolved: &mut Vec<Need>) -> Result<(), Fail> {
        let mut last = None;
        loop {
            out.clear();
            self.view().expand(i, w, out);
            match out.done[0].stop.take() {
                None => break,
                Some(Stop::Fail(error)) => return Err(error),
                Some(Stop::Need(need)) => {
                    self.resolve(need, &mut last)?;
                    resolved.push(need);
                }
            }
        }
        self.merge(out, &out.done[0]);
        Ok(())
    }

    /// Expand ``states`` on every core, each against what is known and the
    /// graph as they are now, in shares of `SHARE`. Each thread keeps its
    /// ``works`` slot, buffers and caches, from one call to the next.
    fn expand_all(&self, states: &[u32], works: &[Mutex<Work>]) -> Vec<Out> {
        let view = self.view();
        states
            .par_chunks(SHARE)
            .map(|share| {
                let slot = rayon::current_thread_index().unwrap_or(0) % works.len();
                let mut w = works[slot].lock().unwrap_or_else(|poisoned| poisoned.into_inner());
                let mut out = Out::default();
                for &i in share {
                    view.expand(i as usize, &mut w, &mut out);
                }
                out
            })
            .collect()
    }

    /// `Explorer.explore`. On one core it expands each state in turn, in
    /// the reference's order, resolving each need where it meets it. On
    /// every core, see `explore_chunk`. Both modes give the same graph, ids
    /// and all, whatever the threads did (I7).
    ///
    /// With ``progress``, its ``tick(markings, waiting)`` hears how far the
    /// run is after every `PROGRESS_EVERY` markings merged, and writes the
    /// progress line when ten seconds have passed (proofs.md, The progress
    /// line), in the reference's words.
    fn explore(&mut self, progress: Option<&Py<PyAny>>, one_core: bool) -> Result<(), Fail> {
        let mut pace = Pace { expanded: 0, progress };
        let mut w = Work::default();
        let mut here = Out::default();
        let mut resolved = Vec::new();
        let works: Vec<Mutex<Work>> = if one_core {
            Vec::new()
        } else {
            (0..rayon::current_num_threads().max(1)).map(|_| Mutex::default()).collect()
        };
        let mut next = 0usize;
        while next < self.store.len() {
            if one_core {
                let i = next;
                next += 1;
                if self.store.flags[i] & 1 == 1 {
                    continue;
                }
                if self.store.len() >= self.max_states {
                    self.capped = true;
                    return Ok(());
                }
                self.expand_here(i, &mut w, &mut here, &mut resolved)?;
                resolved.clear();
                pace.after(self.store.len(), i)?;
            } else {
                let to = (next + CHUNK).min(self.store.len());
                if !self.explore_chunk(next, to, &works, &mut w, &mut here, &mut pace)? {
                    self.capped = true;
                    return Ok(());
                }
                next = to;
            }
        }
        Ok(())
    }

    /// The every-core mode, for the waiting states ``from..to``: expand
    /// them all at once against what is known and the graph so far, then
    /// merge them one by one in the reference's order. A state whose
    /// expansion stopped for a need the run still lacks is expanded again
    /// on this thread when the merge reaches it, its needs resolved in the
    /// order it meets them, so the rows are asked for, and every state,
    /// move and token numbered, as one core does it. A state whose need was
    /// resolved since is stale: once `REDO_AT_ONCE` of them wait, the stale
    /// states ahead are expanded again on every core. False when the state
    /// cap stopped the run.
    fn explore_chunk(&mut self, from: usize, to: usize, works: &[Mutex<Work>], w: &mut Work, here: &mut Out, pace: &mut Pace) -> Result<bool, Fail> {
        let states: Vec<u32> = (from..to).filter(|&i| self.store.flags[i] & 1 == 0).map(|i| i as u32).collect();
        let mut outs = self.expand_all(&states, works);
        // Per state of the chunk, where its latest expansion is: (out, done).
        let mut at = vec![(u32::MAX, u32::MAX); to - from];
        // The states whose latest expansion stopped for each need.
        let mut waiting_on: FxHashMap<Need, Vec<u32>> = FxHashMap::default();
        let mut stale: Vec<u32> = Vec::new();
        let mut resolved = Vec::new();
        index(&outs, 0, from, &mut at, &mut waiting_on);
        for i in from..to {
            if self.store.flags[i] & 1 == 1 {
                continue;
            }
            if self.store.len() >= self.max_states {
                return Ok(false);
            }
            let mut need = latest_need(&outs, at[i - from]);
            if let Some(n) = need {
                if stale.len() >= REDO_AT_ONCE && self.view().knows(&n) {
                    // The stale states ahead whose need is answered now; the
                    // others wait on their need again (a new count of uses
                    // answers some needs of its bucket, not all).
                    let view = self.view();
                    let mut redo = vec![i as u32];
                    for s in stale.drain(..) {
                        if s as usize <= i {
                            continue;
                        }
                        if let Some(n) = latest_need(&outs, at[s as usize - from]) {
                            if view.knows(&n) {
                                redo.push(s);
                            } else {
                                waiting_on.entry(bucket(n)).or_default().push(s);
                            }
                        }
                    }
                    redo.sort_unstable();
                    redo.dedup();
                    let base = outs.len();
                    outs.extend(self.expand_all(&redo, works));
                    index(&outs, base, from, &mut at, &mut waiting_on);
                    need = latest_need(&outs, at[i - from]);
                }
            }
            match need {
                None => {
                    let (o, d) = at[i - from];
                    let out = &outs[o as usize];
                    let done = &out.done[d as usize];
                    if let Some(Stop::Fail(error)) = &done.stop {
                        return Err(error.clone());
                    }
                    self.merge(out, done);
                }
                Some(_) => {
                    self.expand_here(i, w, here, &mut resolved)?;
                    for n in resolved.drain(..) {
                        if let Some(waiting) = waiting_on.remove(&bucket(n)) {
                            stale.extend(waiting);
                        }
                    }
                }
            }
            pace.after(self.store.len(), i)?;
        }
        Ok(true)
    }
}

/// Note where each expansion in ``outs[base..]`` is, and the need it
/// stopped for.
fn index(outs: &[Out], base: usize, from: usize, at: &mut [(u32, u32)], waiting_on: &mut FxHashMap<Need, Vec<u32>>) {
    for (o, out) in outs.iter().enumerate().skip(base) {
        for (d, done) in out.done.iter().enumerate() {
            at[done.i as usize - from] = (o as u32, d as u32);
            if let Some(Stop::Need(n)) = &done.stop {
                waiting_on.entry(bucket(*n)).or_default().push(done.i);
            }
        }
    }
}

/// The need that stands for every need one resolution may answer: a fire
/// row whatever the clock, and any count of uses, as one interned vector
/// can answer needs of many keys.
fn bucket(need: Need) -> Need {
    match need {
        Need::Fire(t, b, _) => Need::Fire(t, b, None),
        Need::Relevance(..) | Need::Inc(..) => Need::Inc(u32::MAX, u16::MAX),
        other => other,
    }
}

/// The need the expansion at ``at`` stopped for, if any.
fn latest_need(outs: &[Out], (o, d): (u32, u32)) -> Option<Need> {
    match &outs[o as usize].done[d as usize].stop {
        Some(Stop::Need(n)) => Some(*n),
        _ => None,
    }
}

/// When the progress line hears how far the run is.
struct Pace<'a> {
    expanded: usize,
    progress: Option<&'a Py<PyAny>>,
}

impl Pace<'_> {
    /// One more state merged, state ``i`` of ``markings``.
    fn after(&mut self, markings: usize, i: usize) -> Result<(), Fail> {
        self.expanded += 1;
        if let Some(progress) = self.progress {
            if self.expanded.is_multiple_of(PROGRESS_EVERY) {
                let waiting = markings - i - 1;
                Python::attach(|py| progress.bind(py).call_method1("tick", (markings, waiting)).map(|_| ()))
                    .map_err(|e| format!("the progress line failed: {e}"))?;
            }
        }
        Ok(())
    }
}

/// What an exploration found: the graph, with every state's marking.
#[pyclass(frozen)]
struct Graph {
    #[pyo3(get)]
    capped: bool,
    #[pyo3(get)]
    states: usize,
    /// Per state: the marking as (place, count, tokens...) runs.
    #[pyo3(get)]
    markings: Vec<u16>,
    #[pyo3(get)]
    marking_offsets: Vec<u32>,
    #[pyo3(get)]
    used_of: Vec<u32>,
    #[pyo3(get)]
    used: Vec<Vec<(u16, u32)>>,
    /// Per state: 1 final, 2 expanded, 4 cut.
    #[pyo3(get)]
    flags: Vec<u8>,
    /// Per state but the first: (state, move) it was first reached by.
    #[pyo3(get)]
    parent: Vec<(u32, u32)>,
    /// Per state: its first edge; one more entry closes the last.
    #[pyo3(get)]
    edge_offsets: Vec<u32>,
    #[pyo3(get)]
    edge_moves: Vec<u32>,
    #[pyo3(get)]
    edge_targets: Vec<u32>,
    /// 0 net, 1 arrival, 2 update, 3 record.
    #[pyo3(get)]
    edge_kinds: Vec<u8>,
    /// Per move: (kind, a, b): 0 fire (row, output), 1 inject, 2 update,
    /// 3 advance (place, token).
    #[pyo3(get)]
    moves: Vec<(u8, u32, u32)>,
    #[pyo3(get)]
    stopped: Vec<u32>,
    /// (state, transition, value) for each maturity left out.
    #[pyo3(get)]
    withheld: Vec<(u32, u16, u32)>,
    /// (fire row, output) of each failed deposit, in the order first met.
    #[pyo3(get)]
    deposit_errors: Vec<(u32, u16)>,
    #[pyo3(get)]
    held_moves: Vec<usize>,
    /// Per state: the key it was deduped by, as `Explorer::add` makes it.
    keys: Vec<u16>,
    key_offsets: Vec<u32>,
}

/// The next of a fixed sequence of random 64-bit weights (splitmix64).
fn next_weight(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

/// How many places the place count looks at in one pass over the keys.
const PLACES_A_PASS: usize = 16;

#[pymethods]
impl Graph {
    /// For each place some marking's key holds: how many distinct keys are
    /// left when that place is ignored (proofs.md, What made the markings).
    ///
    /// As `Explorer._place_counts` does it: each key is the sum of a random
    /// 64-bit weight per (place, contents) and per count of uses, so a key
    /// without one place is the sum less that place's weight, and each
    /// place costs one set of integers.
    fn place_counts(&self, py: Python<'_>) -> PyResult<Vec<(usize, usize)>> {
        contained(py, || Ok(self.count_places()))
    }

    /// How many edges the graph holds.
    #[getter]
    fn edges(&self) -> usize {
        self.edge_moves.len()
    }

    /// The soundness checks on this graph, as `Explorer._verdict` makes
    /// them (P15): `(all_good, bad, improper, fired, stop, end, tail, cycle,
    /// rescues)`. ``instance`` is the mask of the instance's places.
    fn check(&self, py: Python<'_>, instance: u64) -> PyResult<VerdictT> {
        contained(py, || Ok(self.verdict(instance)))
    }

    /// Each step that first reached a marking: (edge kind, move, how many
    /// markings it first reached).
    fn first_steps(&self, py: Python<'_>) -> PyResult<Vec<(u8, u32, u32)>> {
        contained(py, || {
            let mut tally: FxHashMap<(u8, u32), u32> = FxHashMap::default();
            for (j, &(src, mv)) in self.parent.iter().enumerate() {
                if src == u32::MAX {
                    continue;
                }
                let kind = self
                    .edges_of(src as usize)
                    .find(|&e| self.edge_moves[e] == mv && self.edge_targets[e] as usize == j)
                    .map(|e| self.edge_kinds[e])
                    .ok_or_else(|| format!("state {j}'s parent edge is not an edge of state {src}"))?;
                *tally.entry((kind, mv)).or_insert(0) += 1;
            }
            let mut found: Vec<(u8, u32, u32)> = tally.into_iter().map(|((k, m), n)| (k, m, n)).collect();
            found.sort_unstable();
            Ok(found)
        })
    }

    /// State ``index``'s marking: (place, tokens) for each marked place.
    fn marking(&self, py: Python<'_>, index: usize) -> PyResult<Vec<(usize, Vec<u16>)>> {
        self.check_state(index)?;
        contained(py, || {
            let runs = &self.markings[self.marking_offsets[index] as usize..self.marking_offsets[index + 1] as usize];
            let mut found = Vec::new();
            let mut j = 0;
            while j < runs.len() {
                let (place, n) = (runs[j] as usize, runs[j + 1] as usize);
                found.push((place, runs[j + 2..j + 2 + n].to_vec()));
                j += 2 + n;
            }
            Ok(found)
        })
    }

    /// The moves that first reached state ``index``, from the first marking.
    fn path(&self, py: Python<'_>, index: usize) -> PyResult<Vec<u32>> {
        self.check_state(index)?;
        contained(py, || Ok(self.parent_moves(index)))
    }
}

/// What `Graph.check` gives back: see there.
type VerdictT = (bool, Option<u32>, Option<u32>, Vec<u32>, bool, u32, Vec<u32>, Vec<u32>, Vec<(u32, u8)>);

/// The markings net moves reach from one start, in the order a
/// breadth-first walk finds them, with each one's distance and the state
/// and move it was first reached by (`_net_reach`).
struct Reach {
    order: Vec<u32>,
    dist: Vec<u32>,
    pred: Vec<u32>,
    mv: Vec<u32>,
}

impl Reach {
    fn holds(&self, i: usize) -> bool {
        self.dist[i] != u32::MAX
    }

    /// The moves of the path this walk found to ``node`` (`_moves_to`).
    fn moves_to(&self, node: usize) -> Vec<u32> {
        let mut moves = Vec::new();
        let mut at = node;
        while self.pred[at] != u32::MAX {
            moves.push(self.mv[at]);
            at = self.pred[at] as usize;
        }
        moves.reverse();
        moves
    }
}

impl Graph {
    fn check_state(&self, index: usize) -> PyResult<()> {
        if index >= self.states {
            return Err(KernelError::new_err(format!("the graph has no state {index}")));
        }
        Ok(())
    }

    fn parent_moves(&self, index: usize) -> Vec<u32> {
        let mut moves = Vec::new();
        let mut at = index;
        while self.parent[at].0 != u32::MAX {
            moves.push(self.parent[at].1);
            at = self.parent[at].0 as usize;
        }
        moves.reverse();
        moves
    }

    #[inline]
    fn edges_of(&self, i: usize) -> std::ops::Range<usize> {
        self.edge_offsets[i] as usize..self.edge_offsets[i + 1] as usize
    }

    /// State ``i``'s net moves: (move, target).
    fn net_successors(&self, i: usize) -> impl Iterator<Item = (u32, usize)> + '_ {
        self.edges_of(i)
            .filter(move |&e| self.edge_kinds[e] == NET)
            .map(move |e| (self.edge_moves[e], self.edge_targets[e] as usize))
    }

    /// `Explorer._good`: the markings from which net moves reach a seed,
    /// or stop where an arrival or a record change leads on to a good one.
    fn good(&self, reverse: &(Vec<u32>, Vec<u32>), seeds: &[usize], quiet: &[usize]) -> Vec<bool> {
        let (offsets, sources) = reverse;
        let mut good = vec![false; self.states];
        let mut stack: Vec<usize> = Vec::new();
        let mut spread = |starts: &mut dyn Iterator<Item = usize>, good: &mut Vec<bool>| {
            for s in starts {
                if !good[s] {
                    good[s] = true;
                    stack.push(s);
                }
            }
            while let Some(node) = stack.pop() {
                for &pred in &sources[offsets[node] as usize..offsets[node + 1] as usize] {
                    if !good[pred as usize] {
                        good[pred as usize] = true;
                        stack.push(pred as usize);
                    }
                }
            }
        };
        spread(&mut seeds.iter().copied(), &mut good);
        loop {
            let waiting: Vec<usize> = quiet
                .iter()
                .copied()
                .filter(|&i| {
                    !good[i]
                        && self.edges_of(i).any(|e| {
                            matches!(self.edge_kinds[e], ARRIVAL | RECORD) && good[self.edge_targets[e] as usize]
                        })
                })
                .collect();
            if waiting.is_empty() {
                return good;
            }
            spread(&mut waiting.into_iter(), &mut good);
        }
    }

    /// The net moves reversed: for each state, the states with a net move
    /// into it.
    fn reverse_net(&self) -> (Vec<u32>, Vec<u32>) {
        let n = self.states;
        let mut offsets = vec![0u32; n + 1];
        for e in 0..self.edge_moves.len() {
            if self.edge_kinds[e] == NET {
                offsets[self.edge_targets[e] as usize + 1] += 1;
            }
        }
        for i in 0..n {
            offsets[i + 1] += offsets[i];
        }
        let mut fill = offsets.clone();
        let mut sources = vec![0u32; offsets[n] as usize];
        for i in 0..n {
            for e in self.edges_of(i) {
                if self.edge_kinds[e] == NET {
                    let t = self.edge_targets[e] as usize;
                    sources[fill[t] as usize] = i as u32;
                    fill[t] += 1;
                }
            }
        }
        (offsets, sources)
    }

    /// `Explorer._net_reach`.
    fn reach(&self, start: usize) -> Reach {
        let n = self.states;
        let mut r = Reach { order: vec![start as u32], dist: vec![u32::MAX; n], pred: vec![u32::MAX; n], mv: vec![u32::MAX; n] };
        r.dist[start] = 0;
        let mut head = 0;
        while head < r.order.len() {
            let node = r.order[head] as usize;
            head += 1;
            let d = r.dist[node];
            for (mv, t) in self.net_successors(node) {
                if !r.holds(t) {
                    r.dist[t] = d + 1;
                    r.pred[t] = node as u32;
                    r.mv[t] = mv;
                    r.order.push(t as u32);
                }
            }
        }
        r
    }

    /// `Explorer._on_loops`: the states of ``reach`` that net moves lead
    /// back to (a move to itself, or a strongly connected component of two
    /// or more), by Tarjan's algorithm without recursion.
    fn on_loops(&self, reach: &Reach) -> Vec<bool> {
        let n = self.states;
        let mut number = vec![u32::MAX; n];
        let mut low = vec![0u32; n];
        let mut stacked = vec![false; n];
        let mut stack: Vec<usize> = Vec::new();
        let mut found = vec![false; n];
        let mut counter = 0u32;
        for &root in &reach.order {
            let root = root as usize;
            if number[root] != u32::MAX {
                continue;
            }
            let mut work: Vec<(usize, usize)> = Vec::new();
            let mut visit = |node: usize, work: &mut Vec<(usize, usize)>, stack: &mut Vec<usize>, number: &mut Vec<u32>, low: &mut Vec<u32>, stacked: &mut Vec<bool>| {
                number[node] = counter;
                low[node] = counter;
                counter += 1;
                stack.push(node);
                stacked[node] = true;
                work.push((node, self.edge_offsets[node] as usize));
            };
            visit(root, &mut work, &mut stack, &mut number, &mut low, &mut stacked);
            while let Some(&(node, cursor)) = work.last() {
                let end = self.edge_offsets[node + 1] as usize;
                let mut deeper = None;
                let mut e = cursor;
                while e < end {
                    if self.edge_kinds[e] == NET {
                        let t = self.edge_targets[e] as usize;
                        if t == node {
                            found[node] = true;
                        }
                        if number[t] == u32::MAX {
                            deeper = Some(t);
                            e += 1;
                            break;
                        }
                        if stacked[t] {
                            low[node] = low[node].min(number[t]);
                        }
                    }
                    e += 1;
                }
                work.last_mut().unwrap().1 = e;
                if let Some(t) = deeper {
                    visit(t, &mut work, &mut stack, &mut number, &mut low, &mut stacked);
                    continue;
                }
                work.pop();
                if let Some(&(parent, _)) = work.last() {
                    low[parent] = low[parent].min(low[node]);
                }
                if low[node] == number[node] {
                    let mut members = 0;
                    loop {
                        let member = stack.pop().unwrap();
                        stacked[member] = false;
                        members += 1;
                        if member == node {
                            break;
                        }
                        found[member] = true;
                    }
                    if members > 1 {
                        found[node] = true;
                    }
                }
            }
        }
        found
    }

    /// `Explorer._find_cycle`: the nearest state on a loop of net moves
    /// from ``start``, the moves that reach it, and the shortest loop back.
    fn find_cycle(&self, start: usize) -> (usize, Vec<u32>, Vec<u32>) {
        let reach = self.reach(start);
        let looping = self.on_loops(&reach);
        let mut nodes: Vec<usize> = reach.order.iter().map(|&i| i as usize).collect();
        nodes.sort_unstable_by_key(|&i| (reach.dist[i], i));
        for node in nodes {
            if !looping[node] {
                continue;
            }
            if let Some((mv, _)) = self.net_successors(node).find(|&(_, t)| t == node) {
                return (node, reach.moves_to(node), vec![mv]);
            }
            let back = self.reach(node);
            let (_, pred, mv) = back
                .order
                .iter()
                .map(|&p| p as usize)
                .filter(|&p| p != node)
                .flat_map(|p| self.net_successors(p).filter(|&(_, t)| t == node).map(move |(mv, _)| (p, mv)))
                .map(|(p, mv)| (back.dist[p], p, mv))
                .min()
                .expect("a state on a loop of two or more has a net move into it");
            let mut cycle = back.moves_to(pred);
            cycle.push(mv);
            return (node, reach.moves_to(node), cycle);
        }
        (start, Vec::new(), Vec::new())
    }

    /// Whether state ``i``'s marking holds a token in a place of ``mask``.
    fn marks(&self, i: usize, mask: u64) -> bool {
        let runs = &self.markings[self.marking_offsets[i] as usize..self.marking_offsets[i + 1] as usize];
        let mut j = 0;
        while j < runs.len() {
            if mask >> runs[j] & 1 == 1 {
                return true;
            }
            j += 2 + runs[j + 1] as usize;
        }
        false
    }

    /// `Explorer._verdict`.
    fn verdict(&self, instance: u64) -> VerdictT {
        let n = self.states;
        let expanded = |i: usize| self.flags[i] & 2 != 0;
        let final_ = |i: usize| self.flags[i] & 1 != 0;
        let cut = |i: usize| self.flags[i] & 4 != 0;
        // A cut marking still has a net move, the one its cap stopped, so
        // it is never a stop.
        let quiet: Vec<usize> =
            (0..n).filter(|&i| expanded(i) && !final_(i) && !cut(i) && self.net_successors(i).next().is_none()).collect();
        let finals: Vec<usize> = (0..n).filter(|&i| final_(i)).collect();
        let reverse = self.reverse_net();
        let good = self.good(&reverse, &finals, &quiet);
        let mut withheld = vec![false; n];
        for &(state, _, _) in &self.withheld {
            withheld[state as usize] = true;
        }
        let cuts: Vec<usize> = (0..n).filter(|&i| cut(i) || withheld[i]).collect();
        let hopeful = if cuts.is_empty() {
            good.clone()
        } else {
            let seeds: Vec<usize> = finals.iter().chain(cuts.iter()).copied().collect();
            self.good(&reverse, &seeds, &quiet)
        };
        let all_good = (0..n).all(|i| !expanded(i) || good[i]);
        let bad = (0..n).find(|&i| expanded(i) && !hopeful[i]);
        let improper = (0..n).find(|&i| final_(i) && self.marks(i, instance)).map(|i| i as u32);
        let mut fired_move = vec![false; self.moves.len()];
        for e in 0..self.edge_moves.len() {
            let mv = self.edge_moves[e] as usize;
            if matches!(self.edge_kinds[e], NET | RECORD) && self.moves[mv].0 == 0 {
                fired_move[mv] = true;
            }
        }
        let fired: Vec<u32> = (0..self.moves.len()).filter(|&m| fired_move[m]).map(|m| m as u32).collect();
        let Some(bad) = bad else {
            return (all_good, None, improper, fired, false, 0, Vec::new(), Vec::new(), Vec::new());
        };
        let reach = self.reach(bad);
        let mut is_quiet = vec![false; n];
        for &i in &quiet {
            is_quiet[i] = true;
        }
        let mut rescues: Vec<(u32, u8)> = Vec::new();
        let mut seen: FxHashMap<(u32, u8), ()> = FxHashMap::default();
        for &i in &reach.order {
            for e in self.edges_of(i as usize) {
                let kind = self.edge_kinds[e];
                if kind != NET && hopeful[self.edge_targets[e] as usize] {
                    let key = (self.edge_moves[e], kind);
                    if seen.insert(key, ()).is_none() {
                        rescues.push(key);
                    }
                }
            }
        }
        // The breadth-first walk finds the markings by distance, so the
        // first stop it found is a nearest one.
        if let Some(&end) = reach.order.iter().find(|&&i| is_quiet[i as usize]) {
            let tail = reach.moves_to(end as usize);
            return (all_good, Some(bad as u32), improper, fired, true, end, tail, Vec::new(), rescues);
        }
        let (end, tail, cycle) = self.find_cycle(bad);
        (all_good, Some(bad as u32), improper, fired, false, end as u32, tail, cycle, rescues)
    }
}

impl Graph {
    /// The runs of state ``i``'s key: (place, sorted tokens), and its
    /// count of uses.
    fn key_runs(&self, i: usize) -> (impl Iterator<Item = (usize, &[u16])>, u32) {
        let key = &self.keys[self.key_offsets[i] as usize..self.key_offsets[i + 1] as usize];
        let (runs, used) = key.split_at(key.len() - 2);
        let used = (used[0] as u32) << 16 | used[1] as u32;
        let mut j = 0;
        let iter = std::iter::from_fn(move || {
            if j >= runs.len() {
                return None;
            }
            let (place, n) = (runs[j] as usize, runs[j + 1] as usize);
            let tokens = &runs[j + 2..j + 2 + n];
            j += 2 + n;
            Some((place, tokens))
        });
        (iter, used)
    }

    fn count_places(&self) -> Vec<(usize, usize)> {
        let n = self.states;
        let mut seed = 0u64;
        let mut used_weights: FxHashMap<u32, u64> = FxHashMap::default();
        let mut contents: Vec<FxHashMap<&[u16], u32>> = vec![FxHashMap::default(); 64];
        // Content id 0, weight 0: the place is not in the key.
        let mut weights: Vec<Vec<u64>> = vec![vec![0]; 64];
        let mut sums = Vec::with_capacity(n);
        for i in 0..n {
            let (runs, used) = self.key_runs(i);
            let mut sum = *used_weights.entry(used).or_insert_with(|| next_weight(&mut seed));
            for (place, tokens) in runs {
                let next = weights[place].len() as u32;
                let id = *contents[place].entry(tokens).or_insert(next);
                if id == next {
                    weights[place].push(next_weight(&mut seed));
                }
                sum = sum.wrapping_add(weights[place][id as usize]);
            }
            sums.push(sum);
        }
        let seen: Vec<usize> = (0..64).filter(|&p| !contents[p].is_empty()).collect();
        let mut found = Vec::with_capacity(seen.len());
        let mut column = vec![0u32; n * PLACES_A_PASS];
        let mut without: hashbrown::HashSet<u64, std::hash::BuildHasherDefault<FxHasher>> = Default::default();
        for batch in seen.chunks(PLACES_A_PASS) {
            column.fill(0);
            for i in 0..n {
                let (runs, _) = self.key_runs(i);
                for (place, tokens) in runs {
                    if let Some(slot) = batch.iter().position(|&p| p == place) {
                        column[i * PLACES_A_PASS + slot] = contents[place][tokens];
                    }
                }
            }
            for (slot, &place) in batch.iter().enumerate() {
                without.clear();
                without.reserve(n);
                for i in 0..n {
                    let id = column[i * PLACES_A_PASS + slot] as usize;
                    without.insert(sums[i].wrapping_sub(weights[place][id]));
                }
                found.push((place, without.len()));
            }
        }
        found
    }
}

impl Graph {
    fn from(ex: Explorer) -> Graph {
        let g = ex.store;
        let mut edge_offsets = Vec::with_capacity(g.edge_range.len() + 1);
        let mut edge_moves = Vec::with_capacity(g.edge_move.len());
        let mut edge_targets = Vec::with_capacity(g.edge_move.len());
        let mut edge_kinds = Vec::with_capacity(g.edge_move.len());
        // Edges are stored in expansion order; lay them out by state.
        for &(s, n) in &g.edge_range {
            edge_offsets.push(edge_moves.len() as u32);
            for e in s..s + n {
                edge_moves.push(g.edge_move[e as usize]);
                edge_targets.push(g.edge_target[e as usize]);
                edge_kinds.push(g.edge_kind[e as usize]);
            }
        }
        edge_offsets.push(edge_moves.len() as u32);
        let moves = ex
            .move_list
            .iter()
            .map(|k| match *k {
                MoveKey::Fire(row, a) => (0u8, row, a as u32),
                MoveKey::Inject(p, t) => (1, p as u32, t as u32),
                MoveKey::Update(p, t) => (2, p as u32, t as u32),
                MoveKey::Advance(p, t) => (3, p as u32, t as u32),
            })
            .collect();
        Graph {
            capped: ex.capped,
            states: g.hashes.len(),
            markings: g.mk,
            marking_offsets: g.mk_off,
            used_of: g.used_of,
            used: ex.known.used.vecs,
            flags: g.flags,
            parent: g.parent,
            edge_offsets,
            edge_moves,
            edge_targets,
            edge_kinds,
            moves,
            stopped: ex.stopped,
            withheld: ex.withheld,
            deposit_errors: ex.deposit_errors,
            held_moves: ex.held_moves.iter().enumerate().filter(|(_, &h)| h).map(|(t, _)| t).collect(),
            keys: g.keys,
            key_offsets: g.key_off,
        }
    }
}

fn run(tables: TablesT, rows: Py<PyAny>, max_states: usize, progress: Option<Py<PyAny>>, one_core: bool) -> Result<Graph, Fail> {
    let mut ex = Explorer::new(tables, rows, max_states)?;
    ex.explore(progress.as_ref(), one_core)?;
    Ok(Graph::from(ex))
}

/// Explore the net the tables describe, on every core or, with
/// ``one_core``, on one, visiting markings in the reference explorer's
/// order either way (`Explorer::explore`), until it ends or holds
/// ``max_states`` markings. ``rows`` fills each row the tables lack on
/// first use; the kernel calls its ``fire``, ``corr``, ``timer`` and
/// ``tick``. ``progress``, when given, hears how far the run is through its
/// ``tick(markings, waiting)``. Raises `KernelError` when ``rows`` cannot
/// fill a row, or on any other failure inside the kernel.
#[pyfunction]
#[pyo3(signature = (tables, rows, max_states, progress=None, *, one_core=false))]
fn explore(py: Python<'_>, tables: TablesT, rows: Py<PyAny>, max_states: usize, progress: Option<Py<PyAny>>, one_core: bool) -> PyResult<Graph> {
    contained(py, move || run(tables, rows, max_states, progress, one_core))
}

/// Run ``work`` with the GIL released; its failure, or a panic, is a
/// `KernelError`.
fn contained<T: Send>(py: Python<'_>, work: impl FnOnce() -> Result<T, Fail> + Send) -> PyResult<T> {
    let outcome = py.detach(move || std::panic::catch_unwind(std::panic::AssertUnwindSafe(work)));
    match outcome {
        Ok(Ok(found)) => Ok(found),
        Ok(Err(message)) => Err(KernelError::new_err(message)),
        Err(panic) => {
            let message = panic
                .downcast_ref::<String>()
                .cloned()
                .or_else(|| panic.downcast_ref::<&str>().map(|s| s.to_string()))
                .unwrap_or_else(|| "the kernel panicked".to_string());
            Err(KernelError::new_err(format!("the kernel panicked: {message}")))
        }
    }
}

/// The cases of one choice (`choice.Cases.unusual`): every combination,
/// in `itertools.product` order, of a choice token from ``tokens`` at
/// ``place`` and one entry of each ``context`` place's list (`NONE` for
/// empty). Gives back, for each case that enables none or more than one of
/// ``transitions``, its number in that order and a mask of the ones it
/// enables, bit ``k`` for ``transitions[k]``.
fn run_cases(
    tables: TablesT,
    rows: Py<PyAny>,
    update: UpdateT,
    transitions: Vec<usize>,
    place: usize,
    tokens: Vec<u16>,
    context: Vec<(usize, Vec<u16>)>,
) -> Result<Vec<(u64, u64)>, Fail> {
    let mut ex = Explorer::new(tables, rows, 0)?;
    ex.known.rows.take(update)?;
    let ntok = ex.known.rows.ntok;
    let np = ex.rules.np;
    if transitions.len() > 64 || transitions.iter().any(|&t| t >= ex.rules.trs.len()) {
        return Err(format!("the choice names transitions the tables do not hold: {transitions:?}"));
    }
    // Per place: which list fills it, 0 for the choice token, k + 1 for
    // context place k.
    let mut slot = vec![usize::MAX; np];
    for (k, &p) in std::iter::once(&place).chain(context.iter().map(|(p, _)| p)).enumerate() {
        if p >= np || slot[p] != usize::MAX {
            return Err(format!("place {p} is not one place of the choice's cases"));
        }
        slot[p] = k;
    }
    let lists: Vec<&[u16]> = std::iter::once(tokens.as_slice()).chain(context.iter().map(|(_, v)| v.as_slice())).collect();
    if lists.iter().flat_map(|l| l.iter()).any(|&t| t != NONE && t as usize >= ntok) {
        return Err("a case's token is not in the tables".to_string());
    }
    let mut found = Vec::new();
    if lists.iter().any(|l| l.is_empty()) {
        return Ok(found);
    }
    let mut at = vec![0usize; lists.len()];
    let mut m = Flat::default();
    let mut w = Work::default();
    let mut number = 0u64;
    loop {
        m.start.clear();
        m.toks.clear();
        m.start.push(0);
        for p in 0..np {
            if slot[p] != usize::MAX {
                let tok = lists[slot[p]][at[slot[p]]];
                if tok != NONE {
                    m.toks.push(tok);
                }
            }
            m.start.push(m.toks.len() as u32);
        }
        let mut mask = 0u64;
        for (k, &t) in transitions.iter().enumerate() {
            if ex.settle(&mut w, |v, w| v.can_fire(t, &m, &mut w.walk.cands))? {
                mask |= 1 << k;
            }
        }
        if mask.count_ones() != 1 {
            found.push((number, mask));
        }
        number += 1;
        let mut k = lists.len();
        loop {
            if k == 0 {
                return Ok(found);
            }
            k -= 1;
            at[k] += 1;
            if at[k] < lists[k].len() {
                break;
            }
            at[k] = 0;
        }
    }
}

/// The cases of one choice that enable none or more than one of
/// ``transitions``: see `run_cases`. ``update`` brings the rows of the
/// cases' tokens, which the reference numbered after it filled ``tables``;
/// ``rows`` fills a correlate or timer row on first use. Raises
/// `KernelError` as `explore` does.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
fn cases(
    py: Python<'_>,
    tables: TablesT,
    rows: Py<PyAny>,
    update: UpdateT,
    transitions: Vec<usize>,
    place: usize,
    tokens: Vec<u16>,
    context: Vec<(usize, Vec<u16>)>,
) -> PyResult<Vec<(u64, u64)>> {
    contained(py, move || run_cases(tables, rows, update, transitions, place, tokens, context))
}

#[pymodule]
fn velocitron_kernel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(explore, m)?)?;
    m.add_function(wrap_pyfunction!(cases, m)?)?;
    m.add("KernelError", m.py().get_type::<KernelError>())?;
    m.add_class::<Graph>()?;
    Ok(())
}
