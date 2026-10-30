# # # """
# # # po_gantt_service.py  -  Production Schedule: PO on Process / PO on Machines / Planned vs Actual

# # #     GET    /schedule/po-gantt                 the schedule (stations = process rows, machines = machine rows)
# # #     GET    /schedule/po-gantt/orders          yet-to-start POs + part numbers of the plant (pickers)
# # #     GET    /schedule/po-gantt/plants          plant codes
# # #     GET    /schedule/po-gantt/export          the same schedule as .xlsx (sheet 1 process, sheet 2 machines)
# # #     GET/PUT /schedule/part-process-time       machine hours + batch size per part / process
# # #     POST   /schedule/plans                    save the schedule (built again with the same inputs) -> schedule_plan(+_item)
# # #     GET    /schedule/plans?plant=             saved plans
# # #     GET    /schedule/plans/{id}               one saved plan with its snapshot
# # #     PUT    /schedule/plans/{id}/baseline      make it the baseline of its plant
# # #     DELETE /schedule/plans/{id}
# # #     GET    /schedule/plans/{id}/compare       planned (saved plan) vs actual (operator_log / pcb_process_log)

# # # Hook-up (Data_Server.py) - unchanged:
# # #     from po_gantt_service import create_po_gantt_router
# # #     app.include_router(create_po_gantt_router(init_db, verify_token, engine))

# # # RULES
# # #  * POs come ONLY from PcbData. A PO is open when every one of its PCBs is New / Assigned; quantity = sum of PCB quantity.
# # #  * CHILD / MAIN comes from product_type_master.sub_product_type_name. A MAIN part is fed by the CHILD part with the
# # #    same product_type_name (HEXA child 62005774DA -> HEXA main 113300033357). bom_items is only a fallback link.
# # #  * The flow of a part = product_workflow_mapping ordered by step_sequence. A PO runs its flow process after process,
# # #    as one block (the whole quantity). A main PO starts right after the child PO(s) that feed it
# # #     finish (not after ALL child POs): linked POs are scheduled as one chain, and a run can use any free gap of a machine.
# # #  * SMT LINE = the 4 TOP SIDE steps in LINE_GROUPS: one process / one row, run in one go INSIDE ONE WORKING DAY (and in
# # #    one free stretch of its machines). Line time = slowest step for the whole PO + one board through the other steps.
# # #  * MACHINES: equipment_details (stage_id = process, machine_id). A machine is ONE resource: if the same machine_id
# # #    serves several processes, they share it. A line run occupies one machine of every line step at once.
# # #  * MAINTENANCE: a machine is not scheduled while it is down -
# # #      machine_breakdown_logs : breakdown_date + breakdown_time  ->  mc_ready_date, else + downtime_hours,
# # #                               else (still open) until now + OPEN_BREAKDOWN_HOURS.  Closed rows with no end are ignored.
# # #      maintenance_schedules  : every quarter that is not completed blocks the whole day of its date
# # #                               (actual date if filled, else planned date).
# # #    Records are matched to equipment by machine_id, else by machine name.
# # #  * Time per unit = (actual_time or sap_time, hours) + part_process_time.machine_hours (default 0).
# # #    Fallback base: routing process_time_seconds, stage_capacity.manufacturing_time_mins, then 1 min + warning.
# # #    SERIES: qty * t.  BATCH: ceil(qty / batch_size) * t.  Plus setup_minutes once per PO run.
# # #    batch_size = part_process_time.batch_size (if set) else stage_schedule_config.batch_size else 30.
# # #  * PLANT: only POs, equipment and process times of the chosen plant_code are used.
# # #  * Shifts per process from stage_capacity (by name; for the line the line name first); default 2 x 7 h.
# # #    The working window of a day is 08:00 - 22:00 at most (starts at shift_start, lasts shifts * hours, capped at 22:00).
# # #  * Off days: Sundays, 1st/3rd Saturdays, public_holidays, calendar_exceptions 'Holiday';
# # #    'Working' reopens a day, 'Half-Day' halves its window.
# # #  * ACTUAL (Planned vs Actual): operator_log (PCB x step, start_time / end_time), pcb_process_log via pcb_assignment
# # #    when operator_log has no row. A process is done for a PO when every PCB of the PO has an end time there.
# # # """
# # # import io
# # # import math
# # # import re
# # # from collections import defaultdict
# # # from datetime import date, datetime, time, timedelta
# # # from typing import Any, Dict, Iterable, List, Optional, Tuple

# # # from fastapi import APIRouter, Depends, HTTPException, Query
# # # from fastapi.responses import StreamingResponse
# # # from pydantic import BaseModel
# # # from sqlalchemy import func, inspect as sa_inspect, text as sa_text
# # # from sqlalchemy.orm import Session, joinedload

# # # from Database_models import (
# # #     BOMItem, CalendarException, Equipments, MachineBreakdownLog, MaintenanceScheduleLog, OperatorLog,
# # #     OperatorShiftAssignment, OperatorStepMapping, PartProcessTime, PCBAssignment, PcbData, PCBProcessLog, Plant,
# # #     ProcessFlowMaster, Processtype, ProductTypeMaster, ProductWorkflowMapping, PublicHoliday, SchedulePlan,
# # #     SchedulePlanItem, ShiftDefinition, StageCapacityDB, StageScheduleConfig, InventorySpares, Consumables
# # # )

# # # # --------------------------------------------------------------------------------------
# # # # Constants (change the rules in one place)
# # # # --------------------------------------------------------------------------------------
# # # ISO = "%Y-%m-%dT%H:%M:%S"
# # # WEEKLY_OFF_DAYS = (6,)             # Python weekday(): Monday = 0 ... Sunday = 6
# # # ALT_SATURDAYS_OFF = (1, 3)         # 1st and 3rd Saturday of the month
# # # DEFAULT_SHIFTS = 2
# # # DEFAULT_HOURS_PER_SHIFT = 7.0
# # # DEFAULT_SHIFT_START = 8.0          # day window starts 08:00
# # # DAY_END_HOUR = 22.0                # ... and never runs past 22:00 (window = 08:00 - 22:00 = 14 h)
# # # DEFAULT_BATCH_SIZE = 30
# # # FALLBACK_MINUTES = 1.0
# # # MANUAL_PARALLEL_SLOTS = 1          # a MANUAL process (no machine) can work on this many POs at the same time (1 = one PO at a time)
# # # HANDOFF_WARN_HOURS = 30.0          # warn when a main PO starts later than this after the child PO it needs has finished
# # # PCB_OPEN_STATUSES = {"new", "assigned"}      # PcbData.status values that count as "not started"
# # # EXTRA_CHILD_LINKS: Dict[str, str] = {}      # {main_part_no: child_part_no} to force a link

# # # OPEN_BREAKDOWN_HOURS = 24.0        # open breakdown with no ready date / downtime: machine blocked until now + this
# # # DONE_STATUSES = {"completed", "complete", "done", "closed", "resolved"}
# # # LATE_TOLERANCE_MIN = 0.0           # Planned vs Actual: finishing up to this many minutes after plan is "on time"

# # # ROLES = ("CHILD", "MAIN")                   # section order of the rows

# # # # Steps that run as ONE line, inside one working day, shown as ONE row (matched by step name, case-insensitive)
# # # LINE_GROUPS: Dict[str, Tuple[str, ...]] = {
# # #     "SMT LINE": (
# # #         "SOLDER PASTE PRINTING - TOP SIDE",
# # #         "SOLDER PASTE INSPECTION - TOP SIDE",
# # #         "PICK N PLACE - TOP SIDE",
# # #         "REFLOW - TOP SIDE",
# # #     ),
# # # }

# # # BLUE, ORANGE = "BLUE", "ORANGE"


# # # class PoGanttError(Exception):
# # #     def __init__(self, status_code: int, detail: str):
# # #         super().__init__(detail)
# # #         self.status_code, self.detail = status_code, detail


# # # # --------------------------------------------------------------------------------------
# # # # Helpers
# # # # --------------------------------------------------------------------------------------
# # # def _iso(dt: Optional[datetime]) -> Optional[str]:
# # #     return dt.replace(microsecond=0).strftime(ISO) if dt else None


# # # def _norm(s: Optional[str]) -> str:
# # #     """Part / PO numbers: ignore spaces and leading zeros."""
# # #     return (s or "").strip().lstrip("0")


# # # def _key(s: Optional[str]) -> str:
# # #     """Name matching: case / punctuation insensitive."""
# # #     return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# # # def _hm(h: float) -> str:
# # #     hh = int(h)
# # #     return f"{hh:02d}:{int(round((h - hh) * 60)):02d}"


# # # def _chunks(seq: List[Any], n: int = 500) -> Iterable[List[Any]]:
# # #     for i in range(0, len(seq), n):
# # #         yield seq[i:i + n]


# # # _DATE_FMTS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y")
# # # _TIME_FMTS = ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "%I:%M%p", "%H:%M:%S.%f")


# # # def _parse_time(v) -> Optional[time]:
# # #     if v is None or v == "":
# # #         return None
# # #     if isinstance(v, time):
# # #         return v
# # #     s = str(v).strip()
# # #     for f in _TIME_FMTS:
# # #         try:
# # #             return datetime.strptime(s, f).time()
# # #         except ValueError:
# # #             continue
# # #     return None


# # # def _parse_dt(v) -> Optional[datetime]:
# # #     """Dates / datetimes as stored in the maintenance and log tables (ISO, dd-mm-yyyy, dd/mm/yyyy, with or without time)."""
# # #     if v is None or v == "":
# # #         return None
# # #     if isinstance(v, datetime):
# # #         return v if v.tzinfo is None else v.astimezone().replace(tzinfo=None)
# # #     if isinstance(v, date):
# # #         return datetime.combine(v, time.min)
# # #     s = str(v).strip()
# # #     if not s:
# # #         return None
# # #     try:
# # #         dt = datetime.fromisoformat(s[:-1] if s.endswith("Z") else s)
# # #         return dt if dt.tzinfo is None else dt.astimezone().replace(tzinfo=None)
# # #     except ValueError:
# # #         pass
# # #     for df in _DATE_FMTS:
# # #         for tf in ("",) + tuple(" " + t for t in _TIME_FMTS):
# # #             try:
# # #                 return datetime.strptime(s, df + tf)
# # #             except ValueError:
# # #                 continue
# # #     return None


# # # def _merge(intervals: Iterable[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
# # #     out: List[List[datetime]] = []
# # #     for a, b in sorted(intervals):
# # #         if out and a <= out[-1][1]:
# # #             out[-1][1] = max(out[-1][1], b)
# # #         else:
# # #             out.append([a, b])
# # #     return [(a, b) for a, b in out]


# # # def step_name(row) -> str:
# # #     """Stage name of a ProductWorkflowMapping row (via its process_detail relationship -> process_flow_master)."""
# # #     pd = row.process_detail
# # #     return (pd.step_name if pd and pd.step_name else None) or f"Step {row.flow_step_id}"


# # # # --------------------------------------------------------------------------------------
# # # # Calendar with a per-station daily window + machine down-time
# # # # --------------------------------------------------------------------------------------
# # # class DayCalendar:
# # #     """A working day d has a window [d shift_start, +capacity*factor). A station's capacity decides the window length.
# # #     `blocks` (sorted, merged (start, end) pairs) are times the machine is down; work never runs inside them."""

# # #     def __init__(self, holidays: Dict[date, str], exceptions: Dict[date, str], shift_start: float):
# # #         self.holidays = holidays
# # #         self.exceptions = {d: (t or "").strip().lower() for d, t in exceptions.items()}
# # #         self.shift_start = float(shift_start)

# # #     def factor(self, d: date) -> float:
# # #         exc = self.exceptions.get(d)
# # #         if exc == "working":
# # #             return 1.0
# # #         if exc == "half-day":
# # #             return 0.5
# # #         if exc == "holiday":
# # #             return 0.0
# # #         if d in self.holidays:
# # #             return 0.0
# # #         if d.weekday() in WEEKLY_OFF_DAYS:
# # #             return 0.0
# # #         if d.weekday() == 5 and ((d.day - 1) // 7 + 1) in ALT_SATURDAYS_OFF:
# # #             return 0.0
# # #         return 1.0

# # #     def off_reason(self, d: date) -> str:
# # #         if d in self.holidays:
# # #             return self.holidays[d] or "Holiday"
# # #         if self.exceptions.get(d) == "holiday":
# # #             return "Holiday"
# # #         if d.weekday() == 6:
# # #             return "Sunday"
# # #         if d.weekday() == 5:
# # #             return "1st/3rd Saturday"
# # #         return "Off"

# # #     def window(self, d: date, cap_min: float) -> Tuple[datetime, datetime]:
# # #         ws = datetime.combine(d, time.min) + timedelta(hours=self.shift_start)
# # #         return ws, ws + timedelta(minutes=cap_min * self.factor(d))

# # #     def first_working_day(self, d: date) -> date:
# # #         for _ in range(4000):
# # #             if self.factor(d) > 0:
# # #                 return d
# # #             d += timedelta(days=1)
# # #         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

# # #     def locate(self, t: datetime, cap_min: float) -> Tuple[datetime, date]:
# # #         """Earliest moment >= t inside a working window, and the working day that window belongs to."""
# # #         d = t.date() - timedelta(days=1)                      # yesterday's window may spill past midnight
# # #         for _ in range(4000):
# # #             if self.factor(d) > 0:
# # #                 ws, we = self.window(d, cap_min)
# # #                 if t < ws:
# # #                     return ws, d
# # #                 if t < we:
# # #                     return t, d
# # #             d += timedelta(days=1)
# # #         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

# # #     def free_pieces(self, t: datetime, cap_min: float, blocks=()):
# # #         """Contiguous free stretches (day, start, end) from t onward: inside working windows and outside `blocks`."""
# # #         cur, day = self.locate(t, cap_min)
# # #         i, n = 0, len(blocks)
# # #         for _ in range(500000):
# # #             _, we = self.window(day, cap_min)
# # #             while i < n and blocks[i][1] <= cur:
# # #                 i += 1
# # #             if i < n and blocks[i][0] <= cur:                    # machine down right now -> jump past it
# # #                 cur, day = self.locate(blocks[i][1], cap_min)
# # #                 continue
# # #             end = we if i >= n else min(we, blocks[i][0])
# # #             if end > cur:
# # #                 yield day, cur, end
# # #             cur, day = self.locate(end, cap_min)
# # #         raise PoGanttError(500, "Could not place a run inside the working calendar")

# # #     def consume(self, start: datetime, minutes: float, cap_min: float, blocks=()):
# # #         """Run `minutes` of work from `start`, only inside working windows and outside down-time.
# # #         Returns (real_start, end, end_day, [(day, seg_start, seg_end, minutes), ...])."""
# # #         if minutes <= 0:
# # #             cur, day = self.locate(start, cap_min)
# # #             return cur, cur, day, []
# # #         rem, segs, first = float(minutes), [], None
# # #         for day, a, b in self.free_pieces(start, cap_min, blocks):
# # #             if first is None:
# # #                 first = a
# # #             use = min(rem, (b - a).total_seconds() / 60.0)
# # #             e = a + timedelta(minutes=use)
# # #             segs.append((day, a, e, use))
# # #             rem -= use
# # #             if rem <= 1e-9:
# # #                 return first, e, day, segs
# # #         raise PoGanttError(500, "Could not place a run inside the working calendar")

# # #     def place_within_day(self, start: datetime, minutes: float, cap_min: float, blocks=()):
# # #         """The whole run must sit in ONE free stretch of ONE working day. If it does not fit in what is left, it moves
# # #         to the next stretch that can hold it. A run longer than a full day has to spill over.
# # #         Returns consume(...) + (fits_in_one_day,)."""
# # #         if minutes <= cap_min + 1e-9:
# # #             for k, (day, a, b) in enumerate(self.free_pieces(start, cap_min, blocks)):
# # #                 if (b - a).total_seconds() / 60.0 + 1e-9 >= minutes:
# # #                     e = a + timedelta(minutes=minutes)
# # #                     return a, e, day, [(day, a, e, minutes)], True
# # #                 if k > 20000:
# # #                     break
# # #         # longer than one working day: start at the beginning of a day, so it is spread over as few days as possible
# # #         for day, a, b in self.free_pieces(start, cap_min, blocks):
# # #             if a == self.window(day, cap_min)[0]:
# # #                 start = a
# # #                 break
# # #         return self.consume(start, minutes, cap_min, blocks) + (False,)


# # # # --------------------------------------------------------------------------------------
# # # # Station container
# # # # --------------------------------------------------------------------------------------
# # # class Station:
# # #     def __init__(self, key: str, name: str, kind: str, step_ids: List[int]):
# # #         self.key, self.name, self.kind, self.step_ids = key, name, kind, list(step_ids)   # kind: STEP | LINE
# # #         self.steps: List[str] = []                       # member step names (LINE only)
# # #         self.options: List[Dict[str, Any]] = []          # ways to run it: {name, resources, phys, blocks}
# # #         self.real_machines: List[Tuple[str, str]] = []   # every physical machine of the process: (machine_id, step name)
# # #         self.shifts, self.hps, self.cap_min = DEFAULT_SHIFTS, DEFAULT_HOURS_PER_SHIFT, 0.0
# # #         self.mode, self.batch_size = "SERIES", DEFAULT_BATCH_SIZE
# # #         self.setup = self.cooldown = 0.0
# # #         self.cd_working_only = self.next_day_release = False
# # #         self.operators = 0

# # #     @property
# # #     def machines(self) -> List[str]:
# # #         return [o["name"] for o in self.options if o["name"]]


# # # # --------------------------------------------------------------------------------------
# # # # Loaders
# # # # --------------------------------------------------------------------------------------
# # # def _load_candidates(db: Session, plant: Optional[str], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
# # #     """POs come ONLY from PcbData. Plant filter: the PO's part number must belong to that plant in
# # #     product_type_master (PcbData.plant is only used for parts missing from the master).
# # #     A PO is loadable when EVERY one of its PCBs has status New or Assigned."""
# # #     plant_parts, known_parts = set(), set()
# # #     if plant:
# # #         for pn, pc in db.query(ProductTypeMaster.part_number, ProductTypeMaster.plant_code).all():
# # #             known_parts.add(_norm(pn))
# # #             if pc == plant:
# # #                 plant_parts.add(_norm(pn))
# # #     q = db.query(PcbData.productionOrder, PcbData.partNumber, PcbData.quantity, PcbData.status, PcbData.createdAt,
# # #                  PcbData.plant).filter(PcbData.productionOrder.isnot(None), PcbData.productionOrder != "")
# # #     by_po: Dict[str, list] = defaultdict(list)
# # #     for r in q.all():
# # #         if plant:
# # #             n = _norm(r[1])
# # #             if not (n in plant_parts or (n not in known_parts and (r[5] or "").strip() == plant)):
# # #                 continue
# # #         by_po[_norm(r[0])].append(r)

# # #     cands: Dict[str, Dict[str, Any]] = {}
# # #     for po, rows in by_po.items():
# # #         parts = [r[1] for r in rows if r[1]]
# # #         if not parts:
# # #             warnings.append(f"PO {po}: PCBs have no part number - ignored")
# # #             continue
# # #         part = max(set(parts), key=parts.count)
# # #         if len(set(parts)) > 1:
# # #             warnings.append(f"PO {po}: PCBs carry several part numbers ({', '.join(sorted(set(parts)))}) - {part} used")
# # #         created = [r[4] for r in rows if r[4]]
# # #         cands[po] = {
# # #             "po": po, "part": part,
# # #             "qty": sum(r[2] if (r[2] and r[2] > 0) else 1 for r in rows),
# # #             "created": min(created) if created else None,
# # #             "started": any((r[3] or "").strip().lower() not in PCB_OPEN_STATUSES for r in rows),
# # #         }
# # #     return cands


# # # def _product_links(db: Session, warnings: Optional[List[str]] = None):
# # #     """Returns (products, child_of {main_pn: child_pn}, role_of(pn) -> 'CHILD' | 'MAIN').
# # #     1. product_type_master: CHILD and MAIN rows with the same product_type_name (and plant) belong together.
# # #     2. bom_items fallback: the child P/N appears as a material of the main P/N (leading zeros ignored).
# # #     3. EXTRA_CHILD_LINKS override."""
# # #     products = {p.part_number: p for p in db.query(ProductTypeMaster).all()}
# # #     part_by_norm = {_norm(pn): pn for pn in products}

# # #     def sub(pn: str) -> str:
# # #         p = products.get(pn)
# # #         return (p.sub_product_type_name or "").strip().upper() if p else ""

# # #     child_of: Dict[str, str] = {}
# # #     families: Dict[tuple, Dict[str, List[str]]] = defaultdict(lambda: {"CHILD": [], "MAIN": []})
# # #     for pn, p in products.items():
# # #         s = sub(pn)
# # #         if s in ROLES and _key(p.product_type_name):
# # #             families[(_key(p.product_type_name), p.plant_code)][s].append(pn)
# # #     for (fam, _plant), g in sorted(families.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
# # #         childs = sorted(g["CHILD"])
# # #         for m in g["MAIN"]:
# # #             if childs:
# # #                 child_of[m] = childs[0]
# # #                 if len(childs) > 1 and warnings is not None:
# # #                     warnings.append(f"Family {fam.upper()}: several child parts ({', '.join(childs)}) - "
# # #                                     f"{childs[0]} used to feed {m}")

# # #     for main_pn, material in db.query(BOMItem.product_part_number, BOMItem.material).all():
# # #         m = part_by_norm.get(_norm(main_pn)) or main_pn
# # #         c = part_by_norm.get(_norm(material))
# # #         if c and m and c != m and m not in child_of and sub(m) != "CHILD" and sub(c) != "MAIN":
# # #             child_of[m] = c
# # #     for m, c in EXTRA_CHILD_LINKS.items():
# # #         m, c = part_by_norm.get(_norm(m)), part_by_norm.get(_norm(c))
# # #         if m and c:
# # #             child_of[m] = c
# # #     for m, c in list(child_of.items()):
# # #         if child_of.get(c) == m:
# # #             del child_of[m]
# # #     child_parts = set(child_of.values())

# # #     def role_of(pn: Optional[str]) -> str:
# # #         s = sub(pn or "")
# # #         if s in ROLES:
# # #             return s
# # #         return "CHILD" if pn in child_parts else "MAIN"

# # #     return products, child_of, role_of


# # # # def _load_downtime(db: Session, machines: Dict[str, Dict[str, Any]], not_before: datetime, now: datetime,
# # # #                    warnings: List[str]) -> Dict[str, List[Dict[str, Any]]]:
# # # #     """Down-time events per machine_id from machine_breakdown_logs and maintenance_schedules.
# # # #     `machines` = {machine_id: {"name", "eqpt_no", ...}} of the plant. Only events ending after `not_before` are kept."""
# # # #     by_id = {_key(mid): mid for mid in machines}
# # # #     names: Dict[str, List[str]] = defaultdict(list)
# # # #     for mid, info in machines.items():
# # # #         for n in {_key(info.get("name")), _key(info.get("eqpt_no"))} - {""}:
# # # #             if mid not in names[n]:
# # # #                 names[n].append(mid)

# # # #     def match(rec_id, rec_name) -> Optional[str]:
# # # #         mid = by_id.get(_key(rec_id))
# # # #         if mid:
# # # #             return mid
# # # #         for k in (_key(rec_id), _key(rec_name)):
# # # #             if k and len(names.get(k, [])) == 1:          # only an unambiguous name
# # # #                 return names[k][0]
# # # #         return None

# # # #     out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# # # #     assumed = 0
# # # #     try:
# # # #         breakdowns = db.query(MachineBreakdownLog).all()
# # # #     except Exception as exc:                                 # table missing -> schedule without it
# # # #         db.rollback()
# # # #         warnings.append(f"machine_breakdown_logs could not be read ({exc.__class__.__name__}) - breakdowns ignored")
# # # #         breakdowns = []
# # # #     for b in breakdowns:
# # # #         mid = match(b.machine_id, b.machine_name)
# # # #         if not mid:
# # # #             continue
# # # #         st = _parse_dt(b.breakdown_date)
# # # #         if not st:
# # # #             continue
# # # #         tt = _parse_time(b.breakdown_time)
# # # #         if tt and st.time() == time.min:
# # # #             st = datetime.combine(st.date(), tt)
# # # #         is_open = (b.status or "").strip().lower() not in DONE_STATUSES
# # # #         en, note = _parse_dt(b.mc_ready_date), None
# # # #         if not en and b.downtime_hours and b.downtime_hours > 0:
# # # #             en = st + timedelta(hours=float(b.downtime_hours))
# # # #         if not en and is_open:
# # # #             en = max(now, st) + timedelta(hours=OPEN_BREAKDOWN_HOURS)
# # # #             note = f"still open - assumed down until {_iso(en)}"
# # # #             assumed += 1
# # # #         if not en or en <= st or en <= not_before:
# # # #             continue
# # # #         out[mid].append({"machine": mid, "kind": "BREAKDOWN", "label": b.event_type or "Breakdown",
# # # #                          "status": b.status, "start": st, "end": en,
# # # #                          "note": note or (b.issue_description or "")})

# # # #     try:
# # # #         pms = db.query(MaintenanceScheduleLog).all()
# # # #     except Exception as exc:
# # # #         db.rollback()
# # # #         warnings.append(f"maintenance_schedules could not be read ({exc.__class__.__name__}) - maintenance ignored")
# # # #         pms = []
# # # #     for m in pms:
# # # #         mid = match(m.machine_id, m.machine_name)
# # # #         if not mid:
# # # #             continue
# # # #         for q in (1, 2, 3, 4):
# # # #             status = (getattr(m, f"q{q}_status") or "").strip().lower()
# # # #             if status in DONE_STATUSES:
# # # #                 continue
# # # #             d = _parse_dt(getattr(m, f"q{q}_actual_date")) or _parse_dt(getattr(m, f"q{q}_planned_date"))
# # # #             if not d:
# # # #                 continue
# # # #             st = datetime.combine(d.date(), time.min)
# # # #             en = st + timedelta(days=1)
# # # #             if en <= not_before:
# # # #                 continue
# # # #             out[mid].append({"machine": mid, "kind": "PM", "label": m.event_type or "Preventive Maintenance",
# # # #                              "status": getattr(m, f"q{q}_status"), "start": st, "end": en,
# # # #                              "note": f"Q{q} maintenance" + (f" - {m.remarks}" if m.remarks else "")})
# # # #     if assumed:
# # # #         warnings.append(f"{assumed} open breakdown(s) without ready date / downtime - machine assumed down for "
# # # #                         f"{OPEN_BREAKDOWN_HOURS:g} h from now")
# # # #     for mid in out:
# # # #         out[mid].sort(key=lambda e: e["start"])
# # # #     return out

# # # def _load_downtime(db: Session, machines: Dict[str, Dict[str, Any]], not_before: datetime, now: datetime,
# # #                    warnings: List[str]) -> Dict[str, List[Dict[str, Any]]]:
# # #     by_id = {_key(mid): mid for mid in machines}
# # #     names: Dict[str, List[str]] = defaultdict(list)
# # #     for mid, info in machines.items():
# # #         for n in {_key(info.get("name")), _key(info.get("eqpt_no"))} - {""}:
# # #             if mid not in names[n]:
# # #                 names[n].append(mid)

# # #     def match(rec_id, rec_name) -> Optional[str]:
# # #         mid = by_id.get(_key(rec_id))
# # #         if mid: return mid
# # #         for k in (_key(rec_id), _key(rec_name)):
# # #             if k and len(names.get(k, [])) == 1: return names[k][0]
# # #         return None

# # #     out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
# # #     # 1. Machine Breakdowns
# # #     try: breakdowns = db.query(MachineBreakdownLog).all()
# # #     except Exception: breakdowns = []
    
# # #     for b in breakdowns:
# # #         mid = match(b.machine_id, b.machine_name)
# # #         if not mid: continue
# # #         st = _parse_dt(b.breakdown_date)
# # #         if not st: continue
# # #         tt = _parse_time(b.breakdown_time)
# # #         if tt and st.time() == time.min: st = datetime.combine(st.date(), tt)
# # #         is_open = (b.status or "").strip().lower() not in DONE_STATUSES
# # #         en, note = _parse_dt(b.mc_ready_date), None
# # #         if not en and b.downtime_hours and b.downtime_hours > 0:
# # #             en = st + timedelta(hours=float(b.downtime_hours))
# # #         if not en and is_open:
# # #             en = max(now, st) + timedelta(hours=OPEN_BREAKDOWN_HOURS)
# # #             note = f"still open - assumed down until {_iso(en)}"
# # #         if not en or en <= st or en <= not_before: continue
# # #         out[mid].append({"machine": mid, "kind": "BREAKDOWN", "label": b.event_type or "Breakdown",
# # #                          "status": b.status, "start": st, "end": en, "note": note or (b.issue_description or "")})

# # #     # 2. Maintenance Schedules
# # #     try: pms = db.query(MaintenanceScheduleLog).all()
# # #     except Exception: pms = []
    
# # #     for m in pms:
# # #         mid = match(m.machine_id, m.machine_name)
# # #         if not mid: continue
# # #         for q in (1, 2, 3, 4):
# # #             if (getattr(m, f"q{q}_status") or "").strip().lower() in DONE_STATUSES: continue
# # #             d = _parse_dt(getattr(m, f"q{q}_actual_date")) or _parse_dt(getattr(m, f"q{q}_planned_date"))
# # #             if not d: continue
# # #             st = datetime.combine(d.date(), time.min)
# # #             en = st + timedelta(days=1)
# # #             if en <= not_before: continue
# # #             out[mid].append({"machine": mid, "kind": "PM", "label": m.event_type or "Preventive Maintenance",
# # #                              "status": getattr(m, f"q{q}_status"), "start": st, "end": en,
# # #                              "note": f"Q{q} maintenance" + (f" - {m.remarks}" if m.remarks else "")})

# # #     # 3. Inventory Spares (Procurement Lead Time Blocks)
# # #     try: spares = db.query(InventorySpares).all()
# # #     except Exception: spares = []
    
# # #     for sp in spares:
# # #         try:
# # #             q_avl = float(sp.qty_avl or 0)
# # #             th = float(sp.threshold_qty or 0)
# # #         except ValueError: q_avl, th = 0, 0
        
# # #         mid = match(sp.eqpt_no, None)
# # #         if not mid: continue
        
# # #         if 0 < q_avl <= th:
# # #             warnings.append(f"Warning: Low spare part '{sp.decription}' for machine {mid} (Available: {q_avl}, Threshold: {th})")
# # #         if q_avl <= 0:
# # #             import re
# # #             nums = re.findall(r'\d+', str(sp.procurement_lead_time or "7"))
# # #             lt_days = int(nums[0]) if nums else 7
# # #             en = now + timedelta(days=lt_days)
# # #             if en > not_before:
# # #                 out[mid].append({"machine": mid, "kind": "SHORTAGE", "label": "Spare Part Out of Stock",
# # #                                  "status": "Awaiting", "start": now, "end": en,
# # #                                  "note": f"Waiting for spare: {sp.decription} (Lead time: {lt_days} days)"})

# # #     # 4. Consumables Shortages
# # #     try: consumables = db.query(Consumables).all()
# # #     except Exception: consumables = []
    
# # #     for cs in consumables:
# # #         try:
# # #             q_avl = float(cs.quantity or 0)
# # #             th = float(cs.threshold_qty or 0)
# # #         except ValueError: q_avl, th = 0, 0
        
# # #         sid = cs.stage_id
# # #         if 0 < q_avl <= th:
# # #             warnings.append(f"Warning: Low consumable '{cs.consumable_material_name}' for stage ID {sid} (Available: {q_avl}, Threshold: {th})")
# # #         if q_avl <= 0:
# # #             mids = [m for m, info in machines.items() if sid in info.get("stage_ids", [])]
# # #             en = now + timedelta(days=7) # Default consumable restocking delay
# # #             for mid in mids:
# # #                 if en > not_before:
# # #                     out[mid].append({"machine": mid, "kind": "SHORTAGE", "label": "Consumable Out of Stock",
# # #                                      "status": "Awaiting", "start": now, "end": en,
# # #                                      "note": f"Waiting for consumable: {cs.consumable_material_name}"})

# # #     for mid in out:
# # #         out[mid].sort(key=lambda e: e["start"])
# # #     return out

# # # def _dt_json(e: Dict[str, Any]) -> Dict[str, Any]:
# # #     return {**e, "start": _iso(e["start"]), "end": _iso(e["end"])}


# # # def list_open_orders(db: Session, plant: Optional[str] = None) -> Dict[str, Any]:
# # #     """Yet-to-start POs for the picker (oldest first) + the part numbers of the plant (product_type_master)."""
# # #     warnings: List[str] = []
# # #     _, _, role_of = _product_links(db)
# # #     cands = _load_candidates(db, plant, warnings)
# # #     open_pos = sorted((c for c in cands.values() if not c["started"]),
# # #                       key=lambda c: (c["created"] or datetime.max, c["po"]))
# # #     pq = db.query(ProductTypeMaster)
# # #     if plant:
# # #         pq = pq.filter(ProductTypeMaster.plant_code == plant)
# # #     parts = [{"part_number": p.part_number, "role": role_of(p.part_number), "product_type": p.product_type_name,
# # #               "sub_type": p.sub_product_type_name, "description": p.description}
# # #              for p in pq.order_by(ProductTypeMaster.product_type_name, ProductTypeMaster.part_number).all()]
# # #     return {"orders": [{"production_order": c["po"], "part_number": c["part"], "quantity": c["qty"],
# # #                         "role": role_of(c["part"]), "created": c["created"].isoformat() if c["created"] else None}
# # #                        for c in open_pos],
# # #             "parts": parts,
# # #             "warnings": warnings}


# # # def list_plants(db: Session) -> Dict[str, Any]:
# # #     """Plant codes of product_type_master (a PO belongs to the plant of its part number)."""
# # #     codes = sorted({(r[0] or "").strip() for r in db.query(ProductTypeMaster.plant_code).distinct().all()
# # #                     if (r[0] or "").strip()})
# # #     info = {p.plant_code: p.location for p in db.query(Plant).all()}
# # #     return {"plants": [{"plant_code": c, "location": info.get(c) or ""} for c in codes]}


# # # def ensure_part_process_time_columns(engine) -> None:
# # #     """create_all() does not alter existing tables - add machine_hours / batch_size once if they are missing."""
# # #     try:
# # #         cols = {c["name"] for c in sa_inspect(engine).get_columns("part_process_time")}
# # #         with engine.begin() as conn:
# # #             if "machine_hours" not in cols:
# # #                 conn.execute(sa_text("ALTER TABLE part_process_time ADD COLUMN machine_hours DOUBLE PRECISION NOT NULL DEFAULT 0"))
# # #             if "batch_size" not in cols:
# # #                 conn.execute(sa_text("ALTER TABLE part_process_time ADD COLUMN batch_size INTEGER"))
# # #     except Exception as exc:                                   # never block start-up
# # #         print(f"[po_gantt] could not verify part_process_time columns: {exc}")


# # # _PLAN_TABLES_READY = False


# # # def ensure_plan_tables(bind) -> None:
# # #     """Create schedule_plan / schedule_plan_item if they do not exist yet (create_all does this too)."""
# # #     global _PLAN_TABLES_READY
# # #     if _PLAN_TABLES_READY:
# # #         return
# # #     SchedulePlan.__table__.create(bind=bind, checkfirst=True)
# # #     SchedulePlanItem.__table__.create(bind=bind, checkfirst=True)
# # #     _PLAN_TABLES_READY = True


# # # def list_part_process_times(db: Session, plant: Optional[str], part_no: Optional[str] = None) -> Dict[str, Any]:
# # #     """Every routing step of every part of the plant, joined with its part_process_time row (if any)."""
# # #     pq = db.query(ProductTypeMaster)
# # #     if plant:
# # #         pq = pq.filter(ProductTypeMaster.plant_code == plant)
# # #     if part_no:
# # #         pq = pq.filter(ProductTypeMaster.part_number == part_no)
# # #     products = pq.order_by(ProductTypeMaster.product_type_name, ProductTypeMaster.sub_product_type_name,
# # #                            ProductTypeMaster.part_number).all()
# # #     pns = [p.part_number for p in products]
# # #     if not pns:
# # #         return {"plant": plant, "parts": [], "rows": []}
# # #     batch = {p.stage_id for p in db.query(Processtype).filter(Processtype.process_type_batch.is_(True)).all()}
# # #     ppt = {}
# # #     tq = db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(pns))
# # #     if plant:
# # #         tq = tq.filter(PartProcessTime.plant == plant)
# # #     for r in tq.all():
# # #         ppt[(r.part_no, r.process_id)] = r
# # #     rows = []
# # #     for p in products:
# # #         steps = db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
# # #                 ).filter(ProductWorkflowMapping.product_part_number == p.part_number
# # #                 ).order_by(ProductWorkflowMapping.step_sequence, ProductWorkflowMapping.id).all()
# # #         for st in steps:
# # #             r = ppt.get((p.part_number, st.flow_step_id))
# # #             rows.append({
# # #                 "part_no": p.part_number, "product_type": p.product_type_name, "sub_type": p.sub_product_type_name,
# # #                 "process_id": st.flow_step_id, "process_name": step_name(st), "step_sequence": st.step_sequence,
# # #                 "is_batch": st.flow_step_id in batch,
# # #                 "sap_time": r.sap_time if r else None, "actual_time": r.actual_time if r else None,
# # #                 "machine_hours": float(r.machine_hours or 0) if r else 0.0,
# # #                 "batch_size": r.batch_size if r else None,
# # #             })
# # #     return {"plant": plant,
# # #             "parts": [{"part_no": p.part_number, "product_type": p.product_type_name, "sub_type": p.sub_product_type_name,
# # #                        "description": p.description} for p in products],
# # #             "rows": rows}


# # # class PartTimeItem(BaseModel):
# # #     part_no: str
# # #     process_id: int
# # #     machine_hours: Optional[float] = 0.0
# # #     batch_size: Optional[int] = None


# # # class PartTimeSave(BaseModel):
# # #     plant: str
# # #     items: List[PartTimeItem]


# # # def save_part_process_times(db: Session, body: PartTimeSave) -> Dict[str, Any]:
# # #     stage_names = {s.flow_step_id: s.step_name for s in db.query(ProcessFlowMaster).all()}
# # #     updated = created = 0
# # #     for it in body.items:
# # #         mh = float(it.machine_hours or 0)
# # #         if mh < 0:
# # #             raise PoGanttError(422, f"{it.part_no} / step {it.process_id}: machine hours cannot be negative")
# # #         if it.batch_size is not None and it.batch_size < 0:
# # #             raise PoGanttError(422, f"{it.part_no} / step {it.process_id}: batch size cannot be negative")
# # #         bs = int(it.batch_size) if it.batch_size and it.batch_size > 0 else None
# # #         row = db.query(PartProcessTime).filter(
# # #             PartProcessTime.part_no == it.part_no, PartProcessTime.plant == body.plant,
# # #             PartProcessTime.process_id == it.process_id).first()
# # #         if row:
# # #             row.machine_hours, row.batch_size = mh, bs
# # #             updated += 1
# # #         else:
# # #             if it.process_id not in stage_names:
# # #                 raise PoGanttError(404, f"Process step {it.process_id} not found")
# # #             db.add(PartProcessTime(part_no=it.part_no, plant=body.plant, process_id=it.process_id,
# # #                                    process_name=stage_names[it.process_id], machine_hours=mh, batch_size=bs))
# # #             created += 1
# # #     db.commit()
# # #     return {"updated": updated, "created": created}


# # # # --------------------------------------------------------------------------------------
# # # # Builder
# # # # --------------------------------------------------------------------------------------
# # # def build_po_gantt(db: Session, production_orders: Optional[List[str]] = None, plant: Optional[str] = None,
# # #                    start_date: Optional[date] = None, time_source: str = "actual", label_mode: str = "seq",
# # #                    show_holidays: bool = False, shift_start: float = DEFAULT_SHIFT_START,
# # #                    today: Optional[date] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
# # #     if time_source not in ("actual", "sap"):
# # #         raise PoGanttError(400, "time_source must be 'actual' or 'sap'")
# # #     if label_mode not in ("seq", "po"):
# # #         raise PoGanttError(400, "label_mode must be 'seq' or 'po'")
# # #     warnings: List[str] = []
# # #     now = now or datetime.now()
# # #     today = today or now.date()

# # #     # ---------------- calendar ----------------
# # #     holidays = {h.holiday_date: h.name for h in db.query(PublicHoliday).all()}
# # #     exceptions = {e.exception_date: e.exception_type for e in db.query(CalendarException).all()}
# # #     cal = DayCalendar(holidays, exceptions, shift_start)
# # #     day_cap = max((DAY_END_HOUR - shift_start) * 60.0, 60.0)       # the working day ends at 22:00

# # #     # ---------------- masters (loaded once) ----------------
# # #     products, child_of, role_of = _product_links(db, warnings)

# # #     is_batch: Dict[int, bool] = defaultdict(bool)
# # #     for p in db.query(Processtype).all():
# # #         if p.process_type_batch:
# # #             is_batch[p.stage_id] = True
# # #     cfg = {c.stage_id: c for c in db.query(StageScheduleConfig).all()}
# # #     cap_by_key = {_key(c.name): c for c in db.query(StageCapacityDB).all()}
# # #     cap_compact = {k.replace(" ", ""): c for k, c in cap_by_key.items()}

# # #     def find_cap(name: Optional[str]):
# # #         """stage_capacity row of a process: exact name, then ignoring spaces / punctuation, then a UNIQUE partial match."""
# # #         k = _key(name)
# # #         if not k:
# # #             return None
# # #         c = cap_by_key.get(k) or cap_compact.get(k.replace(" ", ""))
# # #         if c:
# # #             return c
# # #         hits = [v for ck, v in cap_by_key.items() if ck and (ck in k or k in ck)]
# # #         return hits[0] if len(hits) == 1 else None

# # #     equipment: Dict[int, List[str]] = defaultdict(list)          # stage_id -> machine_ids
# # #     machine_info: Dict[str, Dict[str, Any]] = {}                  # machine_id -> details
# # #     for e in db.query(Equipments).order_by(Equipments.stage_id, Equipments.id).all():
# # #         if plant and e.plant_code and e.plant_code != plant:          # only the machines of the chosen plant
# # #             continue
# # #         mid = e.machine_id or e.eqpt_no or f"EQ-{e.id}"
# # #         if e.stage_id is not None and mid not in equipment[e.stage_id]:
# # #             equipment[e.stage_id].append(mid)
# # #         info = machine_info.setdefault(mid, {"machine_id": mid, "name": e.eqpt_name or mid, "eqpt_no": e.eqpt_no,
# # #                                              "process_type": e.process_type,
# # #                                              "make": e.eqpt_make, "model": e.eqpt_model,
# # #                                              "workcenter": e.workcenter_name, "stage_ids": []})
# # #         if e.stage_id is not None and e.stage_id not in info["stage_ids"]:
# # #             info["stage_ids"].append(e.stage_id)

# # #     # equipment is normally linked by stage_id = flow_step_id. A process whose flow step has a different id / spelling
# # #     # (e.g. "BAKING" vs "Baking") would then wrongly look manual - so also match by the step NAME, and by the
# # #     # equipment's own process_type / workcenter / name.
# # #     stage_names = {r.flow_step_id: r.step_name for r in db.query(ProcessFlowMaster).all()}
# # #     eq_by_stage_name: Dict[str, List[str]] = defaultdict(list)
# # #     for sid_, mids_ in equipment.items():
# # #         k_ = _key(stage_names.get(sid_))
# # #         for m_ in mids_:
# # #             if k_ and m_ not in eq_by_stage_name[k_]:
# # #                 eq_by_stage_name[k_].append(m_)
# # #     eq_by_label: Dict[str, List[str]] = defaultdict(list)
# # #     for m_, inf_ in machine_info.items():
# # #         for lab_ in (inf_.get("process_type"), inf_.get("workcenter"), inf_.get("name")):
# # #             k_ = _key(lab_)
# # #             if k_ and m_ not in eq_by_label[k_]:
# # #                 eq_by_label[k_].append(m_)

# # #     def machines_for_step(sid: int, name: str) -> List[str]:
# # #         k_ = _key(name)
# # #         for pool in (equipment.get(sid), eq_by_stage_name.get(k_), eq_by_label.get(k_)):
# # #             if pool:
# # #                 return list(pool)
# # #         return []

# # #     shift_names = [s.name for s in db.query(ShiftDefinition).filter(ShiftDefinition.is_active.is_(True))
# # #                    .order_by(ShiftDefinition.sort_order, ShiftDefinition.id).all()]
# # #     assigned: Dict[str, set] = defaultdict(set)
# # #     for a in db.query(OperatorShiftAssignment).all():
# # #         assigned[a.operator_staff_no].add(a.shift_name)
# # #     ops_by_stage: Dict[int, List[str]] = defaultdict(list)
# # #     for o in db.query(OperatorStepMapping).all():
# # #         who = o.operator_staff_no or o.operator_name
# # #         if who and who not in ops_by_stage[o.flow_step_id]:
# # #             ops_by_stage[o.flow_step_id].append(who)

# # #     def operators_per_shift(sid: int) -> int:
# # #         ops = ops_by_stage.get(sid, [])
# # #         if not shift_names:
# # #             return len(ops)
# # #         return max((sum(1 for o in ops if not assigned.get(o) or sn in assigned[o]) for sn in shift_names), default=0)

# # #     line_of_name = {_key(n): g for g, names in LINE_GROUPS.items() for n in names}

# # #     # ---------------- select the POs to load ----------------
# # #     cands = _load_candidates(db, plant, warnings)
# # #     if production_orders:
# # #         selected, seen = [], set()
# # #         for raw in production_orders:
# # #             k = _norm(raw) or raw
# # #             if k in seen:
# # #                 continue
# # #             seen.add(k)
# # #             if k not in cands:
# # #                 raise PoGanttError(404, f"Production order {raw} not found")
# # #             if cands[k]["started"]:
# # #                 warnings.append(f"PO {k} has already started - scheduled from scratch as requested")
# # #             selected.append(cands[k])
# # #         explicit = True
# # #     else:
# # #         selected = sorted((c for c in cands.values() if not c["started"]),
# # #                           key=lambda c: (c["created"] or datetime.max, c["po"]))
# # #         explicit = False

# # #     # ---------------- routing (product_workflow_mapping) + times ----------------
# # #     part_numbers = {c["part"] for c in selected if c["part"]}
# # #     routing: Dict[str, list] = defaultdict(list)
# # #     times: Dict[tuple, list] = defaultdict(list)
# # #     if part_numbers:
# # #         for r in db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
# # #                 ).filter(ProductWorkflowMapping.product_part_number.in_(part_numbers)
# # #                 ).order_by(ProductWorkflowMapping.product_part_number, ProductWorkflowMapping.step_sequence,
# # #                            ProductWorkflowMapping.id).all():
# # #             routing[r.product_part_number].append(r)
# # #         tq = db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(part_numbers))
# # #         if plant:
# # #             tq = tq.filter(PartProcessTime.plant == plant)
# # #         for r in tq.all():
# # #             times[(r.part_no, r.process_id)].append(r)
# # #     other = "sap" if time_source == "actual" else "actual"

# # #     def time_row(part: str, sid: int):
# # #         rows = times.get((part, sid), [])
# # #         if not rows:
# # #             return None
# # #         pref = plant or (products[part].plant_code if part in products else None)
# # #         return next((r for r in rows if r.plant == pref), rows[0])

# # #     def hours_per_unit(part: str, step) -> Tuple[Optional[float], str]:
# # #         """Hours for one unit (SERIES) / one batch (BATCH) = base time + machine hours."""
# # #         row = time_row(part, step.flow_step_id)
# # #         mh = max(float(getattr(row, "machine_hours", 0) or 0), 0.0) if row else 0.0
# # #         base, src = None, "none"
# # #         if row:
# # #             for s in (time_source, other):
# # #                 val = row.actual_time if s == "actual" else row.sap_time
# # #                 if val and val > 0:
# # #                     base, src = float(val), f"part_process_time.{s}"
# # #                     break
# # #         if base is None and getattr(step, "process_time_seconds", None) and step.process_time_seconds > 0:
# # #             base, src = step.process_time_seconds / 3600.0, "routing"
# # #         if base is None:
# # #             cap = find_cap(step_name(step))
# # #             if cap and cap.manufacturing_time_mins and cap.manufacturing_time_mins > 0:
# # #                 base, src = float(cap.manufacturing_time_mins) / 60.0, "stage_capacity"
# # #         if base is None and mh <= 0:
# # #             return None, "none"
# # #         return (base or 0.0) + mh, src + (" + machine_hours" if mh > 0 else "")

# # #     def batch_size_for(part: str, sid: int) -> int:
# # #         row = time_row(part, sid)
# # #         if row and getattr(row, "batch_size", None) and row.batch_size > 0:
# # #             return int(row.batch_size)
# # #         return max(int((cfg[sid].batch_size if sid in cfg else 0) or DEFAULT_BATCH_SIZE), 1)

# # #     def capacity_for(names: List[str]) -> Optional[Tuple[int, float]]:
# # #         for n in names:
# # #             c = find_cap(n)
# # #             if c:
# # #                 sh = int(c.shifts_per_day or 0)
# # #                 hp = float(c.hours_per_shift or 0)
# # #                 return (sh if sh > 0 else DEFAULT_SHIFTS), (hp if hp > 0 else DEFAULT_HOURS_PER_SHIFT)
# # #         return None

# # #     # ---------------- operations of a part (its flow, with the line steps merged) ----------------
# # #     ops_cache: Dict[str, List[Dict[str, Any]]] = {}

# # #     def ops_for(part: str) -> List[Dict[str, Any]]:
# # #         if part in ops_cache:
# # #             return ops_cache[part]
# # #         steps = routing.get(part, [])
# # #         ops, done = [], set()
# # #         for st in steps:
# # #             g = line_of_name.get(_key(step_name(st)))
# # #             if g:
# # #                 if g in done:
# # #                     continue
# # #                 done.add(g)
# # #                 members = [x for x in steps if line_of_name.get(_key(step_name(x))) == g]
# # #                 ops.append({"key": f"LINE-{g}", "line": g, "steps": members})
# # #             else:
# # #                 ops.append({"key": f"STEP-{st.flow_step_id}", "line": None, "steps": [st]})
# # #         ops_cache[part] = ops
# # #         return ops

# # #     # ---------------- build PO objects ----------------
# # #     pos: List[Dict[str, Any]] = []
# # #     for c in selected:
# # #         part, po_no = c["part"], c["po"]
# # #         steps = routing.get(part or "", [])
# # #         if not steps or c["qty"] <= 0:
# # #             msg = (f"PO {po_no}: part {part} has no flow in product_workflow_mapping" if not steps
# # #                    else f"PO {po_no}: quantity is 0")
# # #             if explicit:
# # #                 raise PoGanttError(422, msg)
# # #             warnings.append(msg + " - not scheduled")
# # #             continue
# # #         pos.append({"po": po_no, "part": part, "qty": c["qty"], "ops": ops_for(part), "idx": len(pos) + 1,
# # #                     "role": role_of(part)})
# # #     if not pos:
# # #         raise PoGanttError(404, "No production orders to schedule")
# # #     for p in pos:
# # #         p["label"] = f"B{p['idx']}" if label_mode == "seq" else p["po"]
# # #     label_idx = {p["label"]: p["idx"] for p in pos}
# # #     label_role = {p["label"]: p["role"] for p in pos}

# # #     # ---------------- machine down-time (breakdowns + preventive maintenance) ----------------
# # #     start_day = cal.first_working_day(start_date or today)
# # #     start_dt = datetime.combine(start_day, time.min) + timedelta(hours=shift_start)
# # #     downtime = _load_downtime(db, machine_info, start_dt, now, warnings)
# # #     blocks_of = {mid: _merge((e["start"], e["end"]) for e in evs) for mid, evs in downtime.items()}

# # #     # ---------------- stations ----------------
# # #     stations: Dict[str, Station] = {}
# # #     cap_missing: List[str] = []

# # #     def make_station(op: Dict[str, Any]) -> Station:
# # #         key = op["key"]
# # #         if key in stations:
# # #             return stations[key]
# # #         members = op["steps"]
# # #         sids = [m.flow_step_id for m in members]
# # #         if op["line"]:
# # #             g = op["line"]
# # #             s = Station(key, g, "LINE", sids)
# # #             s.steps = [step_name(m) for m in members]
# # #             s.mode = "LINE"
# # #             mach_of = {m.flow_step_id: machines_for_step(m.flow_step_id, step_name(m)) for m in members}
# # #             with_eq = [(m.flow_step_id, step_name(m)) for m in members if mach_of[m.flow_step_id]]
# # #             n = min(len(mach_of[i]) for i, _ in with_eq) if with_eq else 1   # as parallel as its narrowest step
# # #             for i in range(n):
# # #                 phys = [(mach_of[sid][i], nm) for sid, nm in with_eq]
# # #                 s.options.append({"name": g if n == 1 else f"{g} #{i + 1}",
# # #                                   "resources": [m for m, _ in phys] or [f"LINE-{g}-{i}"], "phys": phys})
# # #             s.real_machines = [(mid, nm) for sid, nm in with_eq for mid in mach_of[sid]]
# # #             s.setup = max([float(cfg[i].setup_minutes or 0) for i in sids if i in cfg], default=0.0)
# # #             s.operators = max(operators_per_shift(i) for i in sids)
# # #             last = cfg.get(sids[-1])
# # #             names = [g] + s.steps
# # #         else:
# # #             sid = sids[0]
# # #             s = Station(key, step_name(members[0]), "STEP", sids)
# # #             s.mode = "BATCH" if is_batch.get(sid) else "SERIES"
# # #             last = cfg.get(sid)
# # #             if last:
# # #                 s.batch_size = max(int(last.batch_size or DEFAULT_BATCH_SIZE), 1)
# # #                 s.setup = float(last.setup_minutes or 0)
# # #             mids = machines_for_step(sid, s.name)
# # #             rmode = (str(getattr(last, "resource_mode", None) or "AUTO")).upper() if last else "AUTO"
# # #             if rmode == "MANUAL":                                   # stage_schedule_config.resource_mode forces manual
# # #                 mids = []
# # #             elif rmode == "MACHINE" and not mids:
# # #                 warnings.append(f"{s.name}: resource_mode is MACHINE but no machine is mapped in equipment_details")
# # #             if mids:
# # #                 s.options = [{"name": mid, "resources": [mid], "phys": [(mid, s.name)]} for mid in mids]
# # #                 s.real_machines = [(mid, s.name) for mid in mids]
# # #             else:
# # #                 slots = max(int(MANUAL_PARALLEL_SLOTS), 1)          # no machine -> people: several POs can run side by side
# # #                 s.options = [{"name": "", "resources": [f"NO-MACHINE-{sid}-{k}"], "phys": []} for k in range(slots)]
# # #             s.operators = operators_per_shift(sid)
# # #             names = [s.name]
# # #         for o in s.options:
# # #             o["blocks"] = _merge(b for r in o["resources"] for b in blocks_of.get(r, []))
# # #         if last:
# # #             s.cooldown = float(last.cooldown_minutes or 0)
# # #             s.cd_working_only = bool(last.cooldown_working_time_only)
# # #             s.next_day_release = bool(last.next_day_release) and bool(is_batch.get(sids[-1]))
# # #         got = capacity_for(names)
# # #         if got:
# # #             s.shifts, s.hps = got
# # #         if not got:
# # #             cap_missing.append(s.name)
# # #         s.cap_min = min(s.shifts * s.hps * 60.0, day_cap)
# # #         stations[key] = s
# # #         return s

# # #     for p in pos:
# # #         for op in p["ops"]:
# # #             make_station(op)
# # #     if cap_missing:
# # #         warnings.append(f"No stage_capacity row matches: {', '.join(dict.fromkeys(cap_missing))} - default "
# # #                         f"{DEFAULT_SHIFTS} shifts x {DEFAULT_HOURS_PER_SHIFT:g} h used (add the process name to stage_capacity)")

# # #     # ---------------- run time of one operation ----------------
# # #     missing_time: Dict[str, List[str]] = defaultdict(list)

# # #     def step_minutes(part: str, st, qty: int) -> Optional[Tuple[float, float]]:
# # #         """(minutes for the whole PO, minutes for the first board / batch) of one routing step."""
# # #         hrs, _src = hours_per_unit(part, st)
# # #         if hrs is None:
# # #             return None
# # #         t = hrs * 60.0
# # #         sid = st.flow_step_id
# # #         if is_batch.get(sid):
# # #             bs = batch_size_for(part, sid)
# # #             return math.ceil(qty / bs) * t, t
# # #         return qty * t, t

# # #     def op_minutes_and_parts(p: Dict[str, Any], op: Dict[str, Any], s: Station):
# # #         """Minutes of one operation for the whole PO, and (PO minutes, first board / batch minutes) of each step in it.
# # #         SMT LINE: the steps run one after the other, so the line time is the SUM of its steps."""
# # #         parts = []
# # #         for st in op["steps"]:
# # #             m = step_minutes(p["part"], st, p["qty"])
# # #             if m is None:
# # #                 missing_time[p["part"]].append(step_name(st))
# # #                 m = (FALLBACK_MINUTES, FALLBACK_MINUTES)
# # #             parts.append(m)
# # #         total = sum(m[0] for m in parts) if s.kind == "LINE" else parts[0][0]
# # #         return max(total + s.setup, 1.0), parts

# # #     # ---------------- child PO -> main PO supply (FIFO by quantity) ----------------
# # #     depends_on: Dict[str, List[str]] = defaultdict(list)
# # #     by_part: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# # #     for p in pos:
# # #         by_part[p["part"]].append(p)
# # #     for main_pn, child_pn in child_of.items():
# # #         mains, childs = by_part.get(main_pn, []), by_part.get(child_pn, [])
# # #         if not mains:
# # #             continue
# # #         if not childs:
# # #             warnings.append(f"Part {main_pn}: no child PO ({child_pn}) loaded - child PCBs assumed in stock, "
# # #                             f"main PO(s) {', '.join(m['label'] for m in mains)} start right away")
# # #             continue
# # #         supply, run = [], 0
# # #         for c in childs:
# # #             supply.append((run, run + c["qty"], c["po"]))
# # #             run += c["qty"]
# # #         need = 0
# # #         for m in mains:
# # #             lo, hi = need, need + m["qty"]
# # #             need = hi
# # #             depends_on[m["po"]] = [cpo for (a, b, cpo) in supply if a < hi and b > lo]
# # #             if hi > run:
# # #                 warnings.append(f"PO {m['po']}: needs more child PCBs than the loaded child POs provide - rest assumed in stock")

# # #     def depth(part: str) -> int:
# # #         d = 0
# # #         while part in child_of and d < 10:
# # #             part, d = child_of[part], d + 1
# # #         return d

# # #     # ---------------- chains: a child PO and the main PO(s) it feeds belong together ----------------
# # #     parent = {p["po"]: p["po"] for p in pos}

# # #     def find(x: str) -> str:
# # #         while parent[x] != x:
# # #             parent[x] = parent[parent[x]]
# # #             x = parent[x]
# # #         return x

# # #     for m_po, c_pos in depends_on.items():
# # #         for c_po in c_pos:
# # #             if c_po in parent and m_po in parent:
# # #                 parent[find(c_po)] = find(m_po)
# # #     chain_first: Dict[str, int] = {}
# # #     for p in pos:
# # #         r = find(p["po"])
# # #         chain_first[r] = min(chain_first.get(r, p["idx"]), p["idx"])
# # #     chain_key = {p["po"]: chain_first[find(p["po"])] for p in pos}        # chain = its first PO (load order)
# # #     chain_no = {k: i + 1 for i, k in enumerate(sorted(set(chain_key.values())))}

# # #     # ---------------- schedule (finite capacity, machines shared, down-time skipped) ----------------
# # #     default_cap = min(DEFAULT_SHIFTS * DEFAULT_HOURS_PER_SHIFT * 60.0, day_cap)
# # #     busy: Dict[str, List[Tuple[datetime, datetime, str]]] = defaultdict(list)   # resource -> runs already booked (first-fit gaps)
# # #     usage: Dict[str, Dict[date, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
# # #     segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# # #     machine_segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# # #     runs: Dict[Tuple[str, str], List[datetime]] = {}
# # #     run_list: List[Dict[str, Any]] = []
# # #     po_ready: Dict[str, datetime] = {}
# # #     po_span: Dict[str, List[datetime]] = {}
# # #     route: Dict[str, List[str]] = defaultdict(list)
# # #     delayed_by_downtime: Dict[str, set] = defaultdict(set)

# # #     # placement order: a main PO is placed immediately after the last child PO that feeds it (child, main, child, main ...)
# # #     # - NOT "all children first", which pushed every main behind all the child work on shared machines.
# # #     by_po = {p["po"]: p for p in pos}
# # #     kids = {m: [c for c in cs if c in by_po] for m, cs in depends_on.items()}
# # #     feeds: Dict[str, List[str]] = defaultdict(list)
# # #     for m_po, cs in kids.items():
# # #         for c_po in cs:
# # #             feeds[c_po].append(m_po)
# # #     order: List[Dict[str, Any]] = []
# # #     placed_po: set = set()

# # #     def emit(p: Dict[str, Any]) -> None:
# # #         if p["po"] in placed_po:
# # #             return
# # #         placed_po.add(p["po"])
# # #         for c_po in kids.get(p["po"], []):
# # #             emit(by_po[c_po])
# # #         order.append(p)
# # #         for m_po in feeds.get(p["po"], []):
# # #             if m_po not in placed_po and all(c in placed_po for c in kids[m_po]):
# # #                 emit(by_po[m_po])

# # #     for p in sorted(pos, key=lambda x: x["idx"]):
# # #         emit(p)
# # #     handoff: Dict[str, Dict[str, Any]] = {}

# # #     open_batches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # station key -> batches already booked (for co-loading)

# # #     def book(st: Station, ready: datetime, minutes: float, one_day: bool = False):
# # #         """First fit on every machine (option) of the station: the earliest start >= ready where the whole run clears the runs
# # #         already booked there and the machine's down-time. The machine that FINISHES first wins.
# # #         one_day = the run must sit inside one free stretch of one working day (SMT LINE, an oven batch).
# # #         Returns (mi, o, start, end, end_day, pieces, fits_in_one_day, blocked_by)."""
# # #         best = None
# # #         for mi, o in enumerate(st.options):
# # #             booked = sorted(iv for r in o["resources"] for iv in busy[r])
# # #             s0, first_block = ready, None
# # #             for _ in range(100000):
# # #                 if one_day:
# # #                     s, e, eday, segs, same = cal.place_within_day(s0, minutes, st.cap_min, o["blocks"])
# # #                 else:
# # #                     s, e, eday, segs = cal.consume(s0, minutes, st.cap_min, o["blocks"])
# # #                     same = True
# # #                 clash = next((iv for iv in booked if iv[0] < e and iv[1] > s), None)
# # #                 if clash is None:
# # #                     break
# # #                 if first_block is None:
# # #                     first_block = clash[2]
# # #                 s0 = clash[1]
# # #             else:
# # #                 raise PoGanttError(500, f"No free slot found on {o['name'] or st.name}")
# # #             if best is None or e < best[3]:
# # #                 best = (mi, o, s, e, eday, segs, same, first_block)
# # #         return best

# # #     def add_segment(p: Dict[str, Any], st: Station, row_id: str, mi: int, o: Dict[str, Any], piece, s: datetime, e: datetime,
# # #                     phys: List[Tuple[str, str]], extra: Dict[str, Any]) -> None:
# # #         """One bar of the Gantt (one PO, one day, one machine / step) + the same bar on each machine row."""
# # #         d, a, b, m = piece
# # #         seg = {
# # #             "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"], "quantity": p["qty"],
# # #             "machine": o["name"], "machine_no": mi, "machines": [mid for mid, _ in phys], "operation": st.name,
# # #             "row_id": row_id, "date": d.isoformat(), "start": _iso(a), "end": _iso(b), "minutes": round(m, 1),
# # #             "run_start": _iso(s), "run_end": _iso(e),
# # #         }
# # #         seg.update(extra)
# # #         segments[st.key].append(seg)
# # #         for mid, nm in phys:
# # #             machine_segments[mid].append({**seg, "machine": mid, "step": nm})
# # #         usage[st.key][d][p["label"]] += m

# # #     def split_steps(segs, step_mins: List[float]):
# # #         """Cut a line run [(day, a, b, minutes)] into its steps, one after the other -> [(step_index, (day, a, b, minutes))]."""
# # #         out, i, left, n = [], 0, step_mins[0], len(step_mins)
# # #         for d, a, b, m in segs:
# # #             while m > 1e-9:
# # #                 while left <= 1e-9 and i < n - 1:          # a step with no time: go to the next one
# # #                     i += 1
# # #                     left = step_mins[i]
# # #                 use = m if i == n - 1 else min(m, left)    # the last step takes whatever is left (rounding)
# # #                 out.append((i, (d, a, a + timedelta(minutes=use), use)))
# # #                 a, m, left = a + timedelta(minutes=use), m - use, left - use
# # #         return out

# # #     def place_batches(p: Dict[str, Any], st: Station, parts, ready: datetime, row_id: str):
# # #         """Batch process: batch_size PCBs go in together and come out together (one bar per batch).
# # #         70 PCBs / batch 30 -> 30 + 30 + 10. Batches of one PO run side by side on free ovens.
# # #         A batch of the SAME part that still has room, is not started before this PO is ready and does not finish later
# # #         than a new batch would, takes the PCBs instead (co-loading).
# # #         Returns (start, end, end_day, machine names, blocked_by)."""
# # #         size = batch_size_for(p["part"], st.step_ids[0])
# # #         per_batch = parts[0][1]                                   # minutes for one batch (time of a batch, not per PCB)
# # #         left, mine, blocked_by = p["qty"], [], None
# # #         while left > 0:
# # #             mins = per_batch + (st.setup if not mine else 0.0)
# # #             mi, o, s, e, eday, segs, same, blocked = book(st, ready, mins, one_day=True)
# # #             join = min((b for b in open_batches[st.key]
# # #                         if b["part"] == p["part"] and b["room"] > 0 and b["start"] >= ready and b["end"] <= e),
# # #                        key=lambda b: b["start"], default=None)
# # #             if join:
# # #                 take = min(left, join["room"])
# # #                 join["room"] -= take
# # #                 mi, o, s, e, eday, segs = join["mi"], join["o"], join["start"], join["end"], join["eday"], join["segs"]
# # #                 together = join["together"]
# # #             else:
# # #                 take = min(left, size)
# # #                 for r in o["resources"]:
# # #                     busy[r].append((s, e, p["label"]))
# # #                 together = []
# # #                 open_batches[st.key].append({"part": p["part"], "room": size - take, "start": s, "end": e, "eday": eday,
# # #                                              "mi": mi, "o": o, "segs": segs, "together": together})
# # #                 if blocked_by is None:
# # #                     blocked_by = blocked
# # #                 if o["blocks"] and any(a < e and b > ready for a, b in o["blocks"]):
# # #                     delayed_by_downtime[p["po"]].add(st.name)
# # #                 if not same:
# # #                     warnings.append(f"PO {p['po']} ({p['label']}): one {st.name} batch needs {mins / 60:.1f} h, more than "
# # #                                     f"one working day ({st.cap_min / 60:g} h) - the batch is spread over several days")
# # #             together.append({"label": p["label"], "po": p["po"], "qty": take})   # every PO inside this batch (shared list)
# # #             left -= take
# # #             mine.append((mi, o, s, e, eday, segs, take, mins, together))
# # #         for k, (mi, o, s, e, eday, segs, take, mins, together) in enumerate(mine, start=1):
# # #             info = {"no": k, "count": len(mine), "qty": take, "size": size, "minutes": round(mins, 1),
# # #                     "start": _iso(s), "end": _iso(e), "together": together}
# # #             for piece in segs:
# # #                 add_segment(p, st, row_id, mi, o, piece, s, e, o["phys"], {"batch": info})
# # #         s_all, e_all = min(b[2] for b in mine), max(b[3] for b in mine)
# # #         last = max(mine, key=lambda b: b[3])
# # #         names = list(dict.fromkeys(b[1]["name"] for b in mine if b[1]["name"]))
# # #         return s_all, e_all, last[4], ", ".join(names), blocked_by

# # #     for p in order:
# # #         prev_ready = max([start_dt] + [po_ready[c] for c in depends_on.get(p["po"], []) if c in po_ready])
# # #         ready0 = prev_ready
# # #         for seq, op in enumerate(p["ops"], start=1):
# # #             st = stations[op["key"]]
# # #             minutes, parts = op_minutes_and_parts(p, op, st)
# # #             row_id = f"{p['role']}:{st.key}"

# # #             if st.mode == "BATCH":
# # #                 # -------- batch process: one bar per batch --------
# # #                 s, e, eday, machine_text, blocked_by = place_batches(p, st, parts, prev_ready, row_id)
# # #                 phys_ids = []
# # #             else:
# # #                 # -------- normal process / SMT LINE: the whole PO in one run --------
# # #                 mi, o, s, e, eday, segs, same, blocked_by = book(st, prev_ready, minutes, one_day=(st.kind == "LINE"))
# # #                 for r in o["resources"]:
# # #                     busy[r].append((s, e, p["label"]))
# # #                 if o["blocks"] and any(a < e and b > prev_ready for a, b in o["blocks"]):
# # #                     delayed_by_downtime[p["po"]].add(st.name)
# # #                 if not same:
# # #                     warnings.append(f"PO {p['po']} ({p['label']}): {st.name} needs {minutes / 60:.1f} h, more than one "
# # #                                     f"working day ({st.cap_min / 60:g} h) - the run is spread over several days")
# # #                 machine_text = o["name"]
# # #                 phys_ids = [m for m, _ in o["phys"]]

# # #                 if st.kind == "LINE":
# # #                     # the line steps run ONE AFTER THE OTHER (step 1 for the whole PO, then step 2 ...), all inside the day
# # #                     step_mins = [parts[i][0] + (st.setup if i == 0 else 0.0) for i in range(len(parts))]
# # #                     pieces = split_steps(segs, step_mins)
# # #                     for i, name in enumerate(st.steps):
# # #                         mine = [pc for k, pc in pieces if k == i]
# # #                         if not mine:
# # #                             continue
# # #                         step_phys = [(mid, nm) for mid, nm in o["phys"] if nm == name]
# # #                         extra = {"step": name, "step_no": i + 1, "step_count": len(st.steps),
# # #                                  "step_start": _iso(mine[0][1]), "step_end": _iso(mine[-1][2]),
# # #                                  "step_minutes": round(step_mins[i], 1)}
# # #                         if step_phys:
# # #                             extra["machine"] = step_phys[0][0]
# # #                         for piece in mine:
# # #                             add_segment(p, st, row_id, mi, o, piece, s, e, step_phys, extra)
# # #                 else:
# # #                     for piece in segs:
# # #                         add_segment(p, st, row_id, mi, o, piece, s, e, o["phys"], {})

# # #             if seq == 1 and any(c in po_ready for c in depends_on.get(p["po"], [])):      # main PO: how soon after its child?
# # #                 wait_h = max((s - ready0).total_seconds() / 3600.0, 0.0)
# # #                 handoff[p["po"]] = {"child_ready": _iso(ready0), "main_start": _iso(s), "wait_hours": round(wait_h, 1),
# # #                                     "station": st.name, "machine": machine_text, "blocked_by": blocked_by}
# # #                 if wait_h > HANDOFF_WARN_HOURS:
# # #                     warnings.append(f"PO {p['po']} ({p['label']}) starts {wait_h / 24:.1f} days after its child PO finished: "
# # #                                     f"{st.name} is busy" + (f" with PO {blocked_by}" if blocked_by else ""))

# # #             span = runs.setdefault((st.key, p["label"]), [s, e])
# # #             span[0], span[1] = min(span[0], s), max(span[1], e)
# # #             ps = po_span.setdefault(p["po"], [s, e])
# # #             ps[0], ps[1] = min(ps[0], s), max(ps[1], e)
# # #             if row_id not in route[p["po"]]:
# # #                 route[p["po"]].append(row_id)
# # #             run_list.append({"seq": seq, "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"],
# # #                              "quantity": p["qty"], "row_id": row_id, "station": st.name, "kind": st.kind,
# # #                              "flow_step_ids": st.step_ids, "machine": machine_text, "machines": phys_ids,
# # #                              "start": _iso(s), "end": _iso(e), "minutes": round(minutes, 1)})

# # #             ready = e                                            # when the PO may enter the next process
# # #             if st.next_day_release:
# # #                 ready = datetime.combine(cal.first_working_day(eday + timedelta(days=1)), time.min) + timedelta(hours=shift_start)
# # #             if st.cooldown > 0:
# # #                 if st.cd_working_only:
# # #                     ready = cal.consume(ready, st.cooldown, default_cap)[1]
# # #                 else:
# # #                     ready = ready + timedelta(minutes=st.cooldown)
# # #             prev_ready = ready
# # #         po_ready[p["po"]] = prev_ready

# # #     for part, names in missing_time.items():
# # #         uniq = list(dict.fromkeys(names))
# # #         warnings.append(f"Part {part}: no process time for {len(uniq)} step(s) "
# # #                         f"[{', '.join(uniq[:6])}{'...' if len(uniq) > 6 else ''}] - {FALLBACK_MINUTES:g} min used")
# # #     if delayed_by_downtime:
# # #         warnings.append(f"{len(delayed_by_downtime)} PO(s) were moved around machine breakdowns / maintenance")

# # #     # ---------------- days ----------------
# # #     used_days = [d for per_day in usage.values() for d in per_day]
# # #     last_day = max(used_days + [start_day])
# # #     days, day_no, working_nos = [], {}, 0
# # #     d = start_day
# # #     while d <= last_day:
# # #         if cal.factor(d) > 0:
# # #             working_nos += 1
# # #             day_no[d] = working_nos
# # #             days.append({"working_day_no": working_nos, "date": d.isoformat(), "weekday": d.strftime("%a"),
# # #                          "is_holiday": False, "off_reason": None})
# # #         elif show_holidays:
# # #             days.append({"working_day_no": None, "date": d.isoformat(), "weekday": d.strftime("%a"),
# # #                          "is_holiday": True, "off_reason": cal.off_reason(d)})
# # #         d += timedelta(days=1)

# # #     # ---------------- rows: CHILD section first, then MAIN; each in flow order ----------------
# # #     def part_sort(pn: str):
# # #         prod = products.get(pn)
# # #         return (_key(prod.product_type_name) if prod else "", pn)

# # #     part_order = sorted({p["part"] for p in pos}, key=part_sort)
# # #     section_rows: Dict[str, List[str]] = {r: [] for r in ROLES}
# # #     parts_by_row: Dict[Tuple[str, str], List[str]] = defaultdict(list)
# # #     for part in part_order:
# # #         role = role_of(part)
# # #         lst, at = section_rows[role], -1
# # #         for op in ops_for(part):                              # merge the flows of several parts in one section
# # #             if op["key"] in lst:
# # #                 at = lst.index(op["key"])
# # #             else:
# # #                 at += 1
# # #                 lst.insert(at, op["key"])
# # #             if part not in parts_by_row[(role, op["key"])]:
# # #                 parts_by_row[(role, op["key"])].append(part)
# # #     roles_of_station: Dict[str, set] = defaultdict(set)
# # #     for role, keys in section_rows.items():
# # #         for k in keys:
# # #             roles_of_station[k].add(role)

# # #     def order_labels(labels) -> List[str]:
# # #         return sorted(labels, key=lambda x: label_idx.get(x, 0))

# # #     def cells_for(key: str, role: str) -> List[Dict[str, Any]]:
# # #         s, out = stations[key], []
# # #         for dd, no in day_no.items():
# # #             u = usage.get(key, {}).get(dd)
# # #             if not u:
# # #                 continue
# # #             labels = [lb for lb in u if label_role.get(lb) == role]
# # #             if not labels:
# # #                 continue
# # #             out.append({"working_day_no": no, "date": dd.isoformat(), "pos": order_labels(labels),
# # #                         "color": ORANGE if len(labels) >= 2 else BLUE,
# # #                         "minutes_used": round(sum(u[lb] for lb in labels), 1),
# # #                         "station_minutes_used": round(sum(u.values()), 1),
# # #                         "capacity_minutes": round(len(s.options) * s.cap_min * cal.factor(dd), 1)})
# # #         return out

# # #     def runs_for(key: str, role: str) -> List[Dict[str, str]]:
# # #         out = [(lb, v) for (k, lb), v in runs.items() if k == key and label_role.get(lb) == role]
# # #         return [{"label": lb, "start": _iso(v[0]), "end": _iso(v[1])}
# # #                 for lb, v in sorted(out, key=lambda kv: (kv[1][0], label_idx.get(kv[0], 0)))]

# # #     def station_downtime(s: Station) -> List[Dict[str, Any]]:
# # #         step_of = {m: nm for m, nm in s.real_machines}                 # SMT LINE: which step the machine belongs to
# # #         evs = [_dt_json({**e, "machine_name": machine_info.get(mid, {}).get("name", mid),
# # #                          "step": step_of[mid] if s.kind == "LINE" else None})
# # #                for mid in dict.fromkeys(m for m, _ in s.real_machines) for e in downtime.get(mid, [])]
# # #         return sorted(evs, key=lambda e: e["start"])

# # #     rows: List[Dict[str, Any]] = []
# # #     for role in ROLES:
# # #         for key in section_rows[role]:
# # #             s = stations[key]
# # #             parts = parts_by_row[(role, key)]
# # #             real = list(dict.fromkeys(m for m, _ in s.real_machines))
# # #             rows.append({
# # #                 "row_id": f"{role}:{key}", "station_id": key, "name": s.name, "kind": s.kind, "section": role,
# # #                 "role": role, "part_number": parts[0], "part_numbers": parts,
# # #                 "flow_step_ids": s.step_ids, "steps": s.steps,
# # #                 "shifts": s.shifts, "mins_per_shift": int(s.hps * 60), "machines": len(s.options),
# # #                 "machine_names": s.machines, "has_machine": bool(real), "real_machines": real,
# # #                 "real_machine_names": [machine_info[m]["name"] for m in real],
# # #                 "operators_per_shift": s.operators, "process_mode": s.mode, "is_batch": s.mode == "BATCH",
# # #                 "day_end_hour": round(shift_start + s.cap_min / 60.0, 2),
# # #                 "shared_with": [r for r in ROLES if r != role and r in roles_of_station[key]],
# # #                 "cells": cells_for(key, role), "po_runs": runs_for(key, role),
# # #                 "segments": [sg for sg in segments.get(key, []) if sg["role"] == role],
# # #                 "downtime": station_downtime(s),
# # #             })

# # #     # ---------------- machine rows (PO on Machines), grouped by process in flow order ----------------
# # #     machine_rows: List[Dict[str, Any]] = []
# # #     placed: Dict[str, Dict[str, Any]] = {}
# # #     for row in rows:
# # #         s = stations[row["station_id"]]
# # #         for mid, step in s.real_machines:
# # #             if mid in placed:
# # #                 if s.name not in placed[mid]["processes"]:
# # #                     placed[mid]["processes"].append(s.name)
# # #                 if row["role"] not in placed[mid]["roles"]:
# # #                     placed[mid]["roles"].append(row["role"])
# # #                 continue
# # #             info = machine_info.get(mid, {"name": mid})
# # #             segs = sorted(machine_segments.get(mid, []), key=lambda x: x["start"])
# # #             mr = {
# # #                 "row_id": f"M:{mid}", "machine_id": mid, "name": info.get("name") or mid, "eqpt_no": info.get("eqpt_no"),
# # #                 "make": info.get("make"), "model": info.get("model"), "workcenter": info.get("workcenter"),
# # #                 "group": s.key, "group_name": s.name, "group_kind": s.kind, "step": step if s.kind == "LINE" else None,
# # #                 "processes": [s.name], "roles": [row["role"]], "shifts": s.shifts,
# # #                 "day_end_hour": round(shift_start + s.cap_min / 60.0, 2), "is_batch": s.mode == "BATCH",
# # #                 "segments": segs, "downtime": [_dt_json(e) for e in downtime.get(mid, [])],
# # #                 # a batch shared by 2 POs is 2 bars at the same time - count the oven time once
# # #                 "busy_minutes": round(sum({(x["start"], x["end"]): x["minutes"] for x in segs}.values()), 1),
# # #             }
# # #             placed[mid] = mr
# # #             machine_rows.append(mr)
# # #     manual_processes = [r["name"] for r in rows if not r["has_machine"]]
# # #     if manual_processes:
# # #         warnings.append("No machine mapped in equipment_details for: " + ", ".join(
# # #             dict.fromkeys(f"{r['name']} (step {', '.join(str(x) for x in r['flow_step_ids'])})" for r in rows if not r["has_machine"])))

# # #     all_down = [_dt_json({**e, "machine_name": machine_info.get(mid, {}).get("name", mid)})
# # #                 for mid in placed for e in downtime.get(mid, [])]

# # #     day_end = shift_start + max((s.cap_min for s in stations.values()), default=default_cap) / 60.0
# # #     line_text = "; ".join(f"{g} = {', '.join(n)}" for g, n in LINE_GROUPS.items())
# # #     assumptions = [
# # #         "Child / main comes from product_type_master (sub product type); a main part is fed by the child part of the same product type.",
# # #         "Each part follows its flow from product_workflow_mapping (step sequence). Linked child / main POs are scheduled as one chain; "
# # #         "a main PO starts after the child PO(s) that feed it are finished.",
# # #         "Unit of work is the whole PO quantity; a PO moves through its processes as a block.",
# # #         f"Line processes run inside one working day ({line_text}). The steps run one after the other "
# # #         "(step 1 for the whole PO, then step 2 ...); line time = sum of the step times.",
# # #         "Machines come from equipment_details; the same machine serving several processes is shared between them.",
# # #         "Machine breakdowns (machine_breakdown_logs: until ready date, else + downtime hours, else open = "
# # #         f"{OPEN_BREAKDOWN_HOURS:g} h from now) and pending preventive maintenance (maintenance_schedules: the whole day) "
# # #         "block the machine.",
# # #         f"Shifts per process come from stage_capacity (default {DEFAULT_SHIFTS} x {DEFAULT_HOURS_PER_SHIFT:g} h); "
# # #         f"the working day runs {_hm(shift_start)} - {_hm(DAY_END_HOUR)} at most.",
# # #         "Off days: Sundays, 1st and 3rd Saturdays, public holidays and calendar 'Holiday' exceptions; "
# # #         "'Working' reopens a day, 'Half-Day' halves it.",
# # #         f"Time per unit = {'actual' if time_source == 'actual' else 'SAP'} time (fallback to the other, routing, stage_capacity) "
# # #         "+ machine hours of part_process_time.",
# # #         "Batch processes (process_type.process_type_batch): batch size PCBs go in together and come out together - "
# # #         "70 PCBs / batch 30 = 3 batches (30, 30, 10), each one bar, run on free machines side by side. "
# # #         "A batch of the same part with room left takes PCBs of the next PO when that does not delay it. "
# # #         "Batch size = part_process_time.batch_size, else stage_schedule_config.batch_size, else 30.",
# # #         f"Plant filter: only POs, machines and process times of plant {plant or '(all)'}.",
# # #         "Operators per shift is informational; it does not limit the schedule.",
# # #     ]
# # #     return {
# # #         "meta": {
# # #             "plant": plant, "number_of_pos": len(pos), "start_date": start_day.isoformat(), "finish_date": last_day.isoformat(),
# # #             "working_days": working_nos, "time_source": time_source, "label_mode": label_mode,
# # #             "generated_at": _iso(now),
# # #             "params": {"plant": plant, "production_order": [p["po"] for p in pos] if explicit else None,
# # #                        "start_date": start_date.isoformat() if start_date else None, "time_source": time_source,
# # #                        "label_mode": label_mode, "shift_start": shift_start},
# # #             "day_window": {"start_hour": shift_start, "end_hour": round(day_end, 2)},
# # #             "line_groups": {g: list(n) for g, n in LINE_GROUPS.items()},
# # #             "machines_down": len({e["machine"] for e in all_down}),
# # #             "downtime_events": len(all_down),
# # #             "manual_processes": manual_processes,
# # #             "pos": [{"label": p["label"], "production_order": p["po"], "part_number": p["part"], "role": p["role"],
# # #                      "quantity": p["qty"], "depends_on": depends_on.get(p["po"], []), "handoff": handoff.get(p["po"]), "route": route[p["po"]],
# # #                      "chain": chain_no[chain_key[p["po"]]],
# # #                      "moved_by_downtime": sorted(delayed_by_downtime.get(p["po"], [])),
# # #                      "start": _iso(po_span[p["po"]][0]), "end": _iso(po_span[p["po"]][1])} for p in pos],
# # #         },
# # #         "days": days, "stations": rows, "machines": machine_rows, "downtime": all_down, "runs": run_list,
# # #         "warnings": warnings, "assumptions": assumptions,
# # #     }


# # # # --------------------------------------------------------------------------------------
# # # # Saved plans
# # # # --------------------------------------------------------------------------------------
# # # class PlanSave(BaseModel):
# # #     name: Optional[str] = None
# # #     remarks: Optional[str] = None
# # #     set_baseline: bool = True
# # #     created_by: Optional[str] = None
# # #     plant: Optional[str] = None
# # #     production_order: Optional[List[str]] = None
# # #     start_date: Optional[date] = None
# # #     time_source: str = "actual"
# # #     label_mode: str = "po"
# # #     shift_start: float = DEFAULT_SHIFT_START


# # # def _plan_header(p: SchedulePlan) -> Dict[str, Any]:
# # #     return {"id": p.id, "name": p.name, "plant": p.plant_code, "is_baseline": bool(p.is_baseline), "status": p.status,
# # #             "time_source": p.time_source, "label_mode": p.label_mode,
# # #             "start_date": p.start_date.isoformat() if p.start_date else None,
# # #             "finish_date": p.finish_date.isoformat() if p.finish_date else None,
# # #             "number_of_pos": p.number_of_pos, "working_days": p.working_days, "remarks": p.remarks,
# # #             "created_by": p.created_by, "created_at": _iso(p.created_at), "params": p.params}


# # # def save_plan(db: Session, body: PlanSave) -> Dict[str, Any]:
# # #     """Build the schedule again with the same inputs (so what is stored is consistent) and store it."""
# # #     ensure_plan_tables(db.get_bind())
# # #     result = build_po_gantt(db, body.production_order, body.plant, body.start_date, body.time_source,
# # #                             body.label_mode, True, body.shift_start)
# # #     meta = result["meta"]
# # #     now = datetime.now()
# # #     if body.set_baseline:
# # #         q = db.query(SchedulePlan).filter(SchedulePlan.is_baseline.is_(True))
# # #         q = q.filter(SchedulePlan.plant_code == body.plant) if body.plant else q.filter(SchedulePlan.plant_code.is_(None))
# # #         q.update({SchedulePlan.is_baseline: False}, synchronize_session=False)
# # #     plan = SchedulePlan(
# # #         name=(body.name or "").strip() or f"Plan {body.plant or 'all'} · {now:%d %b %Y %H:%M}",
# # #         plant_code=body.plant, is_baseline=bool(body.set_baseline), status="SAVED",
# # #         time_source=body.time_source, label_mode=body.label_mode,
# # #         start_date=date.fromisoformat(meta["start_date"]), finish_date=date.fromisoformat(meta["finish_date"]),
# # #         number_of_pos=meta["number_of_pos"], working_days=meta["working_days"], params=meta["params"],
# # #         snapshot=result, remarks=body.remarks, created_by=body.created_by, created_at=now,
# # #     )
# # #     db.add(plan)
# # #     db.flush()
# # #     db.add_all([SchedulePlanItem(
# # #         plan_id=plan.id, seq=r["seq"], production_order=r["po"], part_number=r["part"], label=r["label"],
# # #         role=r["role"], quantity=r["quantity"], row_id=r["row_id"], station_name=r["station"], station_kind=r["kind"],
# # #         flow_step_ids=r["flow_step_ids"], machine=r["machine"], machines=r["machines"],
# # #         planned_start=datetime.strptime(r["start"], ISO), planned_end=datetime.strptime(r["end"], ISO),
# # #         run_minutes=r["minutes"]) for r in result["runs"]])
# # #     db.commit()
# # #     return {"plan": _plan_header(plan), "items": len(result["runs"])}


# # # def list_plans(db: Session, plant: Optional[str]) -> Dict[str, Any]:
# # #     ensure_plan_tables(db.get_bind())
# # #     q = db.query(SchedulePlan.id, SchedulePlan.name, SchedulePlan.plant_code, SchedulePlan.is_baseline,
# # #                  SchedulePlan.status, SchedulePlan.start_date, SchedulePlan.finish_date, SchedulePlan.number_of_pos,
# # #                  SchedulePlan.working_days, SchedulePlan.created_by, SchedulePlan.created_at, SchedulePlan.remarks,
# # #                  SchedulePlan.time_source)
# # #     if plant:
# # #         q = q.filter(SchedulePlan.plant_code == plant)
# # #     out = []
# # #     for r in q.order_by(SchedulePlan.created_at.desc(), SchedulePlan.id.desc()).all():
# # #         out.append({"id": r.id, "name": r.name, "plant": r.plant_code, "is_baseline": bool(r.is_baseline),
# # #                     "status": r.status, "start_date": r.start_date.isoformat() if r.start_date else None,
# # #                     "finish_date": r.finish_date.isoformat() if r.finish_date else None,
# # #                     "number_of_pos": r.number_of_pos, "working_days": r.working_days, "created_by": r.created_by,
# # #                     "created_at": _iso(r.created_at), "remarks": r.remarks, "time_source": r.time_source})
# # #     return {"plans": out}


# # # def _get_plan(db: Session, plan_id: int) -> SchedulePlan:
# # #     ensure_plan_tables(db.get_bind())
# # #     p = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
# # #     if not p:
# # #         raise PoGanttError(404, f"Saved plan {plan_id} not found")
# # #     return p


# # # def set_baseline(db: Session, plan_id: int) -> Dict[str, Any]:
# # #     p = _get_plan(db, plan_id)
# # #     q = db.query(SchedulePlan).filter(SchedulePlan.is_baseline.is_(True), SchedulePlan.id != p.id)
# # #     q = q.filter(SchedulePlan.plant_code == p.plant_code) if p.plant_code else q.filter(SchedulePlan.plant_code.is_(None))
# # #     q.update({SchedulePlan.is_baseline: False}, synchronize_session=False)
# # #     p.is_baseline = True
# # #     db.commit()
# # #     return {"plan": _plan_header(p)}


# # # def delete_plan(db: Session, plan_id: int) -> Dict[str, Any]:
# # #     p = _get_plan(db, plan_id)
# # #     db.query(SchedulePlanItem).filter(SchedulePlanItem.plan_id == p.id).delete(synchronize_session=False)
# # #     db.delete(p)
# # #     db.commit()
# # #     return {"deleted": plan_id}


# # # # --------------------------------------------------------------------------------------
# # # # Actual (what the operators did) and Planned vs Actual
# # # # --------------------------------------------------------------------------------------
# # # _MACHINE_KEYS = ("machine_id", "machineId", "machine", "machine_name", "equipment", "eqpt_no", "equipment_id")


# # # def load_actuals(db: Session, po_numbers: List[str]):
# # #     """Returns (pcb_qty {po: total pieces}, agg {(po, flow_step_id): {...}}) from operator_log, then pcb_process_log
# # #     (via pcb_assignment) for PCB x step pairs operator_log does not have."""
# # #     pos = sorted({_norm(p) for p in po_numbers if p})
# # #     pcbs: Dict[str, Tuple[str, int]] = {}
# # #     serial_to_pcb: Dict[str, str] = {}
# # #     pcb_qty: Dict[str, int] = defaultdict(int)
# # #     norm_col = func.ltrim(func.trim(PcbData.productionOrder), "0")
# # #     for chunk in _chunks(pos):
# # #         for pcb, serial, po, qty in db.query(PcbData.PCBserialNoPartNumber, PcbData.serialNo, PcbData.productionOrder,
# # #                                              PcbData.quantity).filter(norm_col.in_(chunk)).all():
# # #             q = qty if qty and qty > 0 else 1
# # #             n = _norm(po)
# # #             pcbs[pcb] = (n, q)
# # #             pcb_qty[n] += q
# # #             if serial:
# # #                 serial_to_pcb.setdefault(serial, pcb)

# # #     events: Dict[Tuple[str, int], Dict[str, Any]] = {}
# # #     keys = list(pcbs)
# # #     for chunk in _chunks(keys):
# # #         for r in db.query(OperatorLog).filter(OperatorLog.PCBserialNoPartNumber.in_(chunk)).all():
# # #             st, en = _parse_dt(r.start_time), _parse_dt(r.end_time)
# # #             if not en and (r.Task_Status or "").strip().lower() in DONE_STATUSES:
# # #                 en = st
# # #             if not st and not en:
# # #                 continue
# # #             machine = None
# # #             if isinstance(r.log_Data, dict):
# # #                 machine = next((str(r.log_Data[k]) for k in _MACHINE_KEYS if r.log_Data.get(k)), None)
# # #             events[(r.PCBserialNoPartNumber, r.current_step_id)] = {
# # #                 "start": st or en, "end": en, "operator": r.operator_name or r.operator_staff_no, "machine": machine}

# # #     assign: Dict[int, str] = {}
# # #     lookup = keys + [s for s in serial_to_pcb if s not in pcbs]
# # #     for chunk in _chunks(lookup):
# # #         for aid, pid in db.query(PCBAssignment.assignment_id, PCBAssignment.assigned_pcb_id).filter(
# # #                 PCBAssignment.assigned_pcb_id.in_(chunk)).all():
# # #             pcb = pid if pid in pcbs else serial_to_pcb.get(pid)
# # #             if pcb:
# # #                 assign[aid] = pcb
# # #     for chunk in _chunks(list(assign)):
# # #         for r in db.query(PCBProcessLog).filter(PCBProcessLog.assignment_id.in_(chunk)).all():
# # #             k = (assign[r.assignment_id], r.flow_step_id)
# # #             if k in events:
# # #                 continue
# # #             st, en = _parse_dt(r.start_time), _parse_dt(r.end_time)
# # #             if not en and (r.process_status or "").strip().lower() in DONE_STATUSES:
# # #                 en = st
# # #             if not st and not en:
# # #                 continue
# # #             events[k] = {"start": st or en, "end": en, "operator": r.assigned_operator_staff_no, "machine": None}

# # #     agg: Dict[Tuple[str, int], Dict[str, Any]] = {}
# # #     for (pcb, sid), ev in events.items():
# # #         po, q = pcbs[pcb]
# # #         a = agg.setdefault((po, sid), {"start": None, "end": None, "done": 0, "wip": 0,
# # #                                        "operators": set(), "machines": set()})
# # #         a["start"] = min(a["start"], ev["start"]) if a["start"] else ev["start"]
# # #         if ev["end"]:
# # #             a["done"] += q
# # #             a["end"] = max(a["end"], ev["end"]) if a["end"] else ev["end"]
# # #         else:
# # #             a["wip"] += q
# # #         if ev["operator"]:
# # #             a["operators"].add(ev["operator"])
# # #         if ev["machine"]:
# # #             a["machines"].add(ev["machine"])
# # #     return pcb_qty, agg


# # # def _status(ps, pe, a_start, a_end, complete, now) -> Tuple[str, Optional[float]]:
# # #     tol = timedelta(minutes=LATE_TOLERANCE_MIN)
# # #     mins = lambda d: round(d.total_seconds() / 60.0, 1)
# # #     if complete:
# # #         return ("DONE_LATE" if a_end > pe + tol else "DONE_ON_TIME"), mins(a_end - pe)
# # #     if a_start:
# # #         return ("RUNNING_LATE" if now > pe + tol else "RUNNING"), (mins(now - pe) if now > pe else None)
# # #     if now > ps + tol:
# # #         return "START_OVERDUE", mins(now - ps)
# # #     return "UPCOMING", None


# # # def compare_plan(db: Session, plan_id: int, now: Optional[datetime] = None) -> Dict[str, Any]:
# # #     plan = _get_plan(db, plan_id)
# # #     snap = plan.snapshot or {}
# # #     now = now or datetime.now()
# # #     runs = snap.get("runs") or []
# # #     if not runs:                                             # a plan saved without runs -> rebuild from items
# # #         runs = [{"seq": i.seq, "label": i.label, "po": i.production_order, "part": i.part_number, "role": i.role,
# # #                  "quantity": i.quantity, "row_id": i.row_id, "station": i.station_name, "kind": i.station_kind,
# # #                  "flow_step_ids": i.flow_step_ids or [], "machine": i.machine, "machines": i.machines or [],
# # #                  "start": _iso(i.planned_start), "end": _iso(i.planned_end), "minutes": i.run_minutes}
# # #                 for i in db.query(SchedulePlanItem).filter(SchedulePlanItem.plan_id == plan.id).all()]
# # #     pcb_qty, agg = load_actuals(db, [r["po"] for r in runs])

# # #     by_row: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# # #     by_po: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# # #     for r in runs:
# # #         ps, pe = datetime.strptime(r["start"], ISO), datetime.strptime(r["end"], ISO)
# # #         total = pcb_qty.get(r["po"]) or r["quantity"] or 1
# # #         acts = [agg.get((r["po"], sid)) for sid in r["flow_step_ids"]]
# # #         got = [a for a in acts if a]
# # #         a_start = min(a["start"] for a in got) if got else None
# # #         done_qty = min((a["done"] if a else 0) for a in acts) if acts else 0
# # #         complete = bool(acts) and all(a and a["done"] >= total for a in acts)
# # #         a_end = max(a["end"] for a in got if a["end"]) if complete else None
# # #         status, var = _status(ps, pe, a_start, a_end, complete, now)
# # #         item = {
# # #             "label": r["label"], "po": r["po"], "part": r["part"], "role": r["role"], "quantity": r["quantity"],
# # #             "seq": r["seq"], "row_id": r["row_id"], "station": r["station"], "machine": r["machine"],
# # #             "planned_start": r["start"], "planned_end": r["end"], "planned_minutes": r["minutes"],
# # #             "actual_start": _iso(a_start), "actual_end": _iso(a_end), "actual_until": _iso(a_end or (now if a_start else None)),
# # #             "done_qty": done_qty, "total_qty": total,
# # #             "wip_qty": max((a["wip"] for a in got), default=0),
# # #             "start_variance_min": round((a_start - ps).total_seconds() / 60.0, 1) if a_start else None,
# # #             "variance_min": var, "status": status,
# # #             "operators": sorted({o for a in got for o in a["operators"]}),
# # #             "actual_machines": sorted({m for a in got for m in a["machines"]}),
# # #         }
# # #         by_row[r["row_id"]].append(item)
# # #         by_po[r["po"]].append(item)

# # #     rows = []
# # #     for st in snap.get("stations", []):
# # #         items = sorted(by_row.get(st["row_id"], []), key=lambda x: x["planned_start"])
# # #         row = {k: st.get(k) for k in ("row_id", "station_id", "name", "kind", "section", "role", "steps",
# # #                                       "part_numbers", "shifts", "has_machine", "real_machine_names",
# # #                                       "machines", "flow_step_ids")}
# # #         row["items"] = items
# # #         rows.append(row)

# # #     po_meta = {p["production_order"]: p for p in snap.get("meta", {}).get("pos", [])}
# # #     pos_out, kpi = [], defaultdict(int)
# # #     for po, items in by_po.items():
# # #         items.sort(key=lambda x: x["seq"])
# # #         ps = min(i["planned_start"] for i in items)
# # #         pe = max(i["planned_end"] for i in items)
# # #         starts = [i["actual_start"] for i in items if i["actual_start"]]
# # #         complete = all(i["status"].startswith("DONE") for i in items)
# # #         a_end = max(i["actual_end"] for i in items) if complete else None
# # #         status, var = _status(datetime.strptime(ps, ISO), datetime.strptime(pe, ISO),
# # #                               datetime.strptime(min(starts), ISO) if starts else None,
# # #                               datetime.strptime(a_end, ISO) if a_end else None, complete, now)
# # #         current = next((i for i in items if not i["status"].startswith("DONE")), None)
# # #         kpi[status] += 1
# # #         m = po_meta.get(po, {})
# # #         pos_out.append({
# # #             "po": po, "label": items[0]["label"], "part": items[0]["part"], "role": items[0]["role"],
# # #             "quantity": items[0]["quantity"], "planned_start": ps, "planned_end": pe,
# # #             "actual_start": min(starts) if starts else None, "actual_end": a_end, "status": status, "variance_min": var,
# # #             "current_process": current["station"] if current else None,
# # #             "current_status": current["status"] if current else None,
# # #             "processes_done": sum(1 for i in items if i["status"].startswith("DONE")), "processes": len(items),
# # #             "late_processes": sum(1 for i in items if i["status"] in ("DONE_LATE", "RUNNING_LATE", "START_OVERDUE")),
# # #             "depends_on": m.get("depends_on", []), "handoff": m.get("handoff"),
# # #         })
# # #     order = {p["production_order"]: i for i, p in enumerate(snap.get("meta", {}).get("pos", []))}
# # #     pos_out.sort(key=lambda p: order.get(p["po"], 10 ** 6))
# # #     process_kpi = defaultdict(int)
# # #     for items in by_row.values():
# # #         for i in items:
# # #             process_kpi[i["status"]] += 1

# # #     actual_ends = [i["actual_until"] for items in by_row.values() for i in items if i["actual_until"]]
# # #     return {
# # #         "plan": _plan_header(plan), "now": _iso(now),
# # #         "days": snap.get("days", []),
# # #         "meta": dict({k: snap.get("meta", {}).get(k) for k in ("day_window", "line_groups", "pos", "start_date",
# # #                                                                "finish_date", "working_days", "number_of_pos")},
# # #                      actual_last=max(actual_ends) if actual_ends else None),
# # #         "rows": rows, "pos": pos_out,
# # #         "kpis": {"pos": dict(kpi), "processes": dict(process_kpi), "total_pos": len(pos_out),
# # #                  "total_runs": sum(len(v) for v in by_row.values())},
# # #     }


# # # # --------------------------------------------------------------------------------------
# # # # Excel export
# # # # --------------------------------------------------------------------------------------
# # # def build_po_gantt_xlsx(result: Dict[str, Any]) -> bytes:
# # #     from openpyxl import Workbook
# # #     from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
# # #     from openpyxl.utils import get_column_letter

# # #     font = lambda **kw: Font(name="Arial", size=10, **kw)
# # #     thin = Side(style="thin", color="BFBFBF")
# # #     border = Border(left=thin, right=thin, top=thin, bottom=thin)
# # #     head = PatternFill("solid", start_color="DDE3EE")
# # #     off = PatternFill("solid", start_color="D9D9D9")
# # #     down = PatternFill("solid", start_color="F4CCCC")
# # #     machine_fill = PatternFill("solid", start_color="FFF4DB")
# # #     section_fill = {"CHILD": PatternFill("solid", start_color="D3F9D8"), "MAIN": PatternFill("solid", start_color="D0EBFF")}
# # #     fills = {BLUE: PatternFill("solid", start_color="9FC5E8"), ORANGE: PatternFill("solid", start_color="F6B26B")}
# # #     center = Alignment(horizontal="center", vertical="center", wrap_text=True)
# # #     days = result["days"]
# # #     last_col = 2 + len(days)

# # #     def header(ws, first_col_title):
# # #         ws.column_dimensions["A"].width = 36
# # #         ws.column_dimensions["B"].width = 12
# # #         for i, label in enumerate(("Working day #", "Date", "Day"), start=1):
# # #             c = ws.cell(row=i, column=1, value=first_col_title if i == 3 else label)
# # #             c.font, c.fill, c.border = font(bold=True), head, border
# # #             ws.cell(row=i, column=2).fill = head
# # #             ws.cell(row=i, column=2).border = border
# # #         for j, d in enumerate(days, start=3):
# # #             ws.column_dimensions[get_column_letter(j)].width = 11
# # #             dt = date.fromisoformat(d["date"])
# # #             vals = ("Off" if d["is_holiday"] else d["working_day_no"], dt.strftime("%d-%b"), d["weekday"])
# # #             for i, v in enumerate(vals, start=1):
# # #                 c = ws.cell(row=i, column=j, value=v)
# # #                 c.font, c.border, c.alignment = font(bold=(i == 1)), border, center
# # #                 c.fill = off if d["is_holiday"] else head
# # #         ws.freeze_panes = "C4"

# # #     def band(ws, r, text, fill):
# # #         for j in range(1, last_col + 1):
# # #             c = ws.cell(row=r, column=j)
# # #             c.fill, c.border = fill, border
# # #         ws.cell(row=r, column=1, value=text).font = font(bold=True)

# # #     def day_cells(ws, r, segs, downs):
# # #         col_of_date = {d["date"]: j for j, d in enumerate(days, start=3)}
# # #         for j, d in enumerate(days, start=3):
# # #             c = ws.cell(row=r, column=j)
# # #             c.border = border
# # #             if d["is_holiday"]:
# # #                 c.fill = off
# # #         for e in downs:
# # #             dd = date.fromisoformat(e["start"][:10])
# # #             while dd.isoformat() <= e["end"][:10]:
# # #                 j = col_of_date.get(dd.isoformat())
# # #                 if j and not (dd.isoformat() == e["end"][:10] and e["end"][11:] == "00:00:00" and e["end"][:10] != e["start"][:10]):
# # #                     c = ws.cell(row=r, column=j, value="DOWN")
# # #                     c.fill, c.font, c.alignment = down, font(bold=True, color="990000"), center
# # #                 dd += timedelta(days=1)
# # #         per_day: Dict[str, List[str]] = defaultdict(list)
# # #         for s in segs:
# # #             if s["label"] not in per_day[s["date"]]:
# # #                 per_day[s["date"]].append(s["label"])
# # #         for dstr, labels in per_day.items():
# # #             j = col_of_date.get(dstr)
# # #             if not j:
# # #                 continue
# # #             c = ws.cell(row=r, column=j, value=" ".join(labels))
# # #             c.fill = fills[ORANGE if len(labels) >= 2 else BLUE]
# # #             c.font, c.alignment = font(bold=True), center

# # #     wb = Workbook()
# # #     ws = wb.active
# # #     ws.title = "PO on Process"
# # #     header(ws, "Process")
# # #     r, current = 4, None
# # #     for st in result["stations"]:
# # #         if st["section"] != current:
# # #             current = st["section"]
# # #             band(ws, r, f"{current} PROCESSES", section_fill.get(current, head))
# # #             r += 1
# # #         name = st["name"] + (f"  ({len(st['steps'])} steps, same day)" if st.get("kind") == "LINE" else "")
# # #         a = ws.cell(row=r, column=1, value=name)
# # #         a.font, a.border = font(bold=True), border
# # #         if st.get("has_machine"):
# # #             a.fill = machine_fill
# # #         b = ws.cell(row=r, column=2, value=f"{st['shifts']} shift" + (f" · {len(st['real_machines'])} m/c" if st.get("real_machines") else ""))
# # #         b.font, b.border, b.alignment = font(), border, center
# # #         day_cells(ws, r, st["segments"], [])
# # #         r += 1

# # #     r += 1
# # #     ws.cell(row=r, column=1, value="Legend").font = font(bold=True)
# # #     for k, (txt, fill) in enumerate((("1 PO on the process", fills[BLUE]), ("2 or more POs share the process", fills[ORANGE]),
# # #                                      ("Process with machine(s)", machine_fill)), 1):
# # #         ws.cell(row=r + k, column=1, value=txt).font = font()
# # #         ws.cell(row=r + k, column=2).fill = fill
# # #     r += 5
# # #     for j, h in enumerate(("Label", "Production order", "Part number", "Child / Main", "Quantity", "Start", "End"), start=1):
# # #         c = ws.cell(row=r, column=j, value=h)
# # #         c.font, c.fill, c.border = font(bold=True), head, border
# # #     for k, p in enumerate(result["meta"]["pos"], start=1):
# # #         for j, v in enumerate((p["label"], p["production_order"], p["part_number"], p["role"], p["quantity"],
# # #                                p["start"], p["end"]), start=1):
# # #             c = ws.cell(row=r + k, column=j, value=v)
# # #             c.font, c.border = font(), border

# # #     ws2 = wb.create_sheet("PO on Machines")
# # #     header(ws2, "Machine")
# # #     r, current = 4, None
# # #     for m in result.get("machines", []):
# # #         if m["group"] != current:
# # #             current = m["group"]
# # #             band(ws2, r, m["group_name"], machine_fill)
# # #             r += 1
# # #         a = ws2.cell(row=r, column=1, value=f"{m['name']} ({m['machine_id']})" + (f" · {m['step']}" if m.get("step") else ""))
# # #         a.font, a.border = font(bold=True), border
# # #         b = ws2.cell(row=r, column=2, value=f"{round(m['busy_minutes'] / 60, 1)} h")
# # #         b.font, b.border, b.alignment = font(), border, center
# # #         day_cells(ws2, r, m["segments"], m["downtime"])
# # #         r += 1

# # #     buf = io.BytesIO()
# # #     wb.save(buf)
# # #     return buf.getvalue()


# # # # --------------------------------------------------------------------------------------
# # # # Router
# # # # --------------------------------------------------------------------------------------
# # # def create_po_gantt_router(init_db, verify_token=None, engine=None) -> APIRouter:
# # #     """Pass `engine` so machine_hours / batch_size are added to part_process_time and the plan tables are created
# # #     at start-up (otherwise they are created on first use)."""
# # #     if engine is not None:
# # #         ensure_part_process_time_columns(engine)
# # #         try:
# # #             ensure_plan_tables(engine)
# # #         except Exception as exc:
# # #             print(f"[po_gantt] could not create schedule_plan tables: {exc}")
# # #     router = APIRouter()
# # #     deps = [Depends(verify_token)] if verify_token else []

# # #     def _guard(fn, db=None):
# # #         try:
# # #             return fn()
# # #         except PoGanttError as e:
# # #             if db is not None:
# # #                 db.rollback()
# # #             raise HTTPException(status_code=e.status_code, detail=e.detail)

# # #     def _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start):
# # #         return _guard(lambda: build_po_gantt(db, production_order, plant, start_date, time_source, label_mode,
# # #                                              show_holidays, shift_start))

# # #     @router.get("/schedule/po-gantt/plants", dependencies=deps)
# # #     def po_gantt_plants(db: Session = Depends(init_db)):
# # #         return list_plants(db)

# # #     @router.get("/schedule/part-process-time", dependencies=deps)
# # #     def part_process_time_list(plant: Optional[str] = Query(None), part_no: Optional[str] = Query(None),
# # #                                db: Session = Depends(init_db)):
# # #         return list_part_process_times(db, plant, part_no)

# # #     @router.put("/schedule/part-process-time", dependencies=deps)
# # #     def part_process_time_save(body: PartTimeSave, db: Session = Depends(init_db)):
# # #         return _guard(lambda: save_part_process_times(db, body), db)

# # #     @router.get("/schedule/po-gantt/orders", dependencies=deps)
# # #     def po_gantt_orders(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
# # #         return list_open_orders(db, plant)

# # #     @router.get("/schedule/po-gantt", dependencies=deps)
# # #     def po_gantt(
# # #         production_order: Optional[List[str]] = Query(None, description="PO numbers to load; order = load priority"),
# # #         plant: Optional[str] = Query(None),
# # #         start_date: Optional[date] = Query(None, description="default: first working day on/after today"),
# # #         time_source: str = Query("actual"),
# # #         label_mode: str = Query("seq", description="'seq' = B1, B2... | 'po' = PO number"),
# # #         show_holidays: bool = Query(True, description="send off days as flagged columns"),
# # #         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=20),
# # #         db: Session = Depends(init_db),
# # #     ):
# # #         return _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)

# # #     @router.get("/schedule/po-gantt/export", dependencies=deps)
# # #     def po_gantt_export(
# # #         production_order: Optional[List[str]] = Query(None),
# # #         plant: Optional[str] = Query(None),
# # #         start_date: Optional[date] = Query(None),
# # #         time_source: str = Query("actual"),
# # #         label_mode: str = Query("seq"),
# # #         show_holidays: bool = Query(True),
# # #         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=20),
# # #         db: Session = Depends(init_db),
# # #     ):
# # #         result = _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)
# # #         return StreamingResponse(
# # #             io.BytesIO(build_po_gantt_xlsx(result)),
# # #             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
# # #             headers={"Content-Disposition": 'attachment; filename="po_gantt.xlsx"'},
# # #         )

# # #     @router.post("/schedule/plans", dependencies=deps)
# # #     def plans_save(body: PlanSave, db: Session = Depends(init_db)):
# # #         return _guard(lambda: save_plan(db, body), db)

# # #     @router.get("/schedule/plans", dependencies=deps)
# # #     def plans_list(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
# # #         return list_plans(db, plant)

# # #     @router.get("/schedule/plans/{plan_id}", dependencies=deps)
# # #     def plans_get(plan_id: int, db: Session = Depends(init_db)):
# # #         def go():
# # #             p = _get_plan(db, plan_id)
# # #             return {"plan": _plan_header(p), "snapshot": p.snapshot}
# # #         return _guard(go)

# # #     @router.put("/schedule/plans/{plan_id}/baseline", dependencies=deps)
# # #     def plans_baseline(plan_id: int, db: Session = Depends(init_db)):
# # #         return _guard(lambda: set_baseline(db, plan_id), db)

# # #     @router.delete("/schedule/plans/{plan_id}", dependencies=deps)
# # #     def plans_delete(plan_id: int, db: Session = Depends(init_db)):
# # #         return _guard(lambda: delete_plan(db, plan_id), db)

# # #     @router.get("/schedule/plans/{plan_id}/compare", dependencies=deps)
# # #     def plans_compare(plan_id: int, db: Session = Depends(init_db)):
# # #         return _guard(lambda: compare_plan(db, plan_id))

# # #     return router


# # """
# # po_gantt_service.py  -  Production Schedule: PO on Process / PO on Machines / Planned vs Actual

# #     GET    /schedule/po-gantt                 the schedule (stations = process rows, machines = machine rows)
# #     GET    /schedule/po-gantt/orders          yet-to-start POs + part numbers of the plant (pickers)
# #     GET    /schedule/po-gantt/plants          plant codes
# #     GET    /schedule/po-gantt/export          the same schedule as .xlsx (sheet 1 process, sheet 2 machines)
# #     GET/PUT /schedule/part-process-time       machine hours + batch size per part / process
# #     POST   /schedule/plans                    save the schedule (built again with the same inputs) -> schedule_plan(+_item)
# #     GET    /schedule/plans?plant=             saved plans
# #     GET    /schedule/plans/{id}               one saved plan with its snapshot
# #     PUT    /schedule/plans/{id}/baseline      make it the baseline of its plant
# #     DELETE /schedule/plans/{id}
# #     GET    /schedule/plans/{id}/compare       planned (saved plan) vs actual (operator_log / pcb_process_log)

# # Hook-up (Data_Server.py) - unchanged:
# #     from po_gantt_service import create_po_gantt_router
# #     app.include_router(create_po_gantt_router(init_db, verify_token, engine))

# # RULES
# #  * POs come ONLY from PcbData. A PO is open when every one of its PCBs is New / Assigned; quantity = sum of PCB quantity.
# #  * CHILD / MAIN comes from product_type_master.sub_product_type_name. A MAIN part is fed by the CHILD part with the
# #    same product_type_name (HEXA child 62005774DA -> HEXA main 113300033357). bom_items is only a fallback link.
# #  * The flow of a part = product_workflow_mapping ordered by step_sequence. A PO runs its flow process after process,
# #    as one block (the whole quantity). A main PO starts right after the child PO(s) that feed it
# #     finish (not after ALL child POs): linked POs are scheduled as one chain, and a run can use any free gap of a machine.
# #  * SMT LINE = the 4 TOP SIDE steps in LINE_GROUPS: one process / one row, run in one go INSIDE ONE WORKING DAY (and in
# #    one free stretch of its machines). Line time = slowest step for the whole PO + one board through the other steps.
# #  * MACHINES: equipment_details (stage_id = process, machine_id). A machine is ONE resource: if the same machine_id
# #    serves several processes, they share it. A line run occupies one machine of every line step at once.
# #  * MAINTENANCE: a machine is not scheduled while it is down -
# #      machine_breakdown_logs : breakdown_date + breakdown_time  ->  mc_ready_date, else + downtime_hours,
# #                               else (still open) until now + OPEN_BREAKDOWN_HOURS.  Closed rows with no end are ignored.
# #      maintenance_schedules  : every quarter that is not completed blocks the whole day of its date
# #                               (actual date if filled, else planned date).
# #    Records are matched to equipment by machine_id, else by machine name.
# #  * Time per unit = (actual_time or sap_time, hours) + part_process_time.machine_hours (default 0).
# #    Fallback base: routing process_time_seconds, stage_capacity.manufacturing_time_mins, then 1 min + warning.
# #    SERIES: qty * t.  BATCH: ceil(qty / batch_size) * t.  Plus setup_minutes once per PO run.
# #    batch_size = part_process_time.batch_size (if set) else stage_schedule_config.batch_size else 30.
# #  * PLANT: only POs, equipment and process times of the chosen plant_code are used.
# #  * Shifts per process from stage_capacity (by name; for the line the line name first); default 2 x 7 h.
# #    The working window of a day is 08:00 - 22:00 at most (starts at shift_start, lasts shifts * hours, capped at 22:00).
# #  * Off days: Sundays, 1st/3rd Saturdays, public_holidays, calendar_exceptions 'Holiday';
# #    'Working' reopens a day, 'Half-Day' halves its window.
# #  * ACTUAL (Planned vs Actual): operator_log (PCB x step, start_time / end_time), pcb_process_log via pcb_assignment
# #    when operator_log has no row. A process is done for a PO when every PCB of the PO has an end time there.
# # """
# # import io
# # import math
# # import re
# # from collections import defaultdict
# # from datetime import date, datetime, time, timedelta
# # from typing import Any, Dict, Iterable, List, Optional, Tuple

# # from fastapi import APIRouter, Depends, HTTPException, Query
# # from fastapi.responses import StreamingResponse
# # from pydantic import BaseModel
# # from sqlalchemy import func, inspect as sa_inspect, text as sa_text
# # from sqlalchemy.orm import Session, joinedload

# # from Database_models import (
# #     BOMItem, CalendarException, Equipments, MachineBreakdownLog, MaintenanceScheduleLog, OperatorLog,
# #     OperatorShiftAssignment, OperatorStepMapping, PartProcessTime, PCBAssignment, PcbData, PCBProcessLog, Plant,
# #     ProcessFlowMaster, Processtype, ProductTypeMaster, ProductWorkflowMapping, PublicHoliday, SchedulePlan,
# #     SchedulePlanItem, ShiftDefinition, StageCapacityDB, StageScheduleConfig, InventorySpares, Consumables
# # )

# # # --------------------------------------------------------------------------------------
# # # Constants (change the rules in one place)
# # # --------------------------------------------------------------------------------------
# # ISO = "%Y-%m-%dT%H:%M:%S"
# # WEEKLY_OFF_DAYS = (6,)             # Python weekday(): Monday = 0 ... Sunday = 6
# # ALT_SATURDAYS_OFF = (1, 3)         # 1st and 3rd Saturday of the month
# # DEFAULT_SHIFTS = 2
# # DEFAULT_HOURS_PER_SHIFT = 7.0
# # DEFAULT_SHIFT_START = 8.0          # day window starts 08:00
# # DAY_END_HOUR = 22.0                # ... and never runs past 22:00 (window = 08:00 - 22:00 = 14 h)
# # DEFAULT_BATCH_SIZE = 30
# # FALLBACK_MINUTES = 1.0
# # MANUAL_PARALLEL_SLOTS = 1          # a MANUAL process (no machine) can work on this many POs at the same time (1 = one PO at a time)
# # HANDOFF_WARN_HOURS = 30.0          # warn when a main PO starts later than this after the child PO it needs has finished
# # PCB_OPEN_STATUSES = {"new", "assigned"}      # PcbData.status values that count as "not started"
# # EXTRA_CHILD_LINKS: Dict[str, str] = {}      # {main_part_no: child_part_no} to force a link

# # OPEN_BREAKDOWN_HOURS = 24.0        # open breakdown with no ready date / downtime: machine blocked until now + this
# # DEFAULT_SPARE_LEAD_DAYS = 7        # inventorty_spares.procurement_lead_time empty / not a number
# # CONSUMABLE_RESTOCK_DAYS = 7        # consumable out of stock / expired: process blocked from now for this many days (no restock date in the table)
# # DONE_STATUSES = {"completed", "complete", "done", "closed", "resolved"}
# # LATE_TOLERANCE_MIN = 0.0           # Planned vs Actual: finishing up to this many minutes after plan is "on time"

# # ROLES = ("CHILD", "MAIN")                   # section order of the rows

# # # Steps that run as ONE line, inside one working day, shown as ONE row (matched by step name, case-insensitive)
# # LINE_GROUPS: Dict[str, Tuple[str, ...]] = {
# #     "SMT LINE": (
# #         "SOLDER PASTE PRINTING - TOP SIDE",
# #         "SOLDER PASTE INSPECTION - TOP SIDE",
# #         "PICK N PLACE - TOP SIDE",
# #         "REFLOW - TOP SIDE",
# #     ),
# # }

# # BLUE, ORANGE = "BLUE", "ORANGE"


# # class PoGanttError(Exception):
# #     def __init__(self, status_code: int, detail: str):
# #         super().__init__(detail)
# #         self.status_code, self.detail = status_code, detail


# # # --------------------------------------------------------------------------------------
# # # Helpers
# # # --------------------------------------------------------------------------------------
# # def _iso(dt: Optional[datetime]) -> Optional[str]:
# #     return dt.replace(microsecond=0).strftime(ISO) if dt else None


# # def _norm(s: Optional[str]) -> str:
# #     """Part / PO numbers: ignore spaces and leading zeros."""
# #     return (s or "").strip().lstrip("0")


# # def _key(s: Optional[str]) -> str:
# #     """Name matching: case / punctuation insensitive."""
# #     return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# # def _hm(h: float) -> str:
# #     hh = int(h)
# #     return f"{hh:02d}:{int(round((h - hh) * 60)):02d}"


# # def _chunks(seq: List[Any], n: int = 500) -> Iterable[List[Any]]:
# #     for i in range(0, len(seq), n):
# #         yield seq[i:i + n]


# # _DATE_FMTS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y")
# # _TIME_FMTS = ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "%I:%M%p", "%H:%M:%S.%f")


# # def _parse_time(v) -> Optional[time]:
# #     if v is None or v == "":
# #         return None
# #     if isinstance(v, time):
# #         return v
# #     s = str(v).strip()
# #     for f in _TIME_FMTS:
# #         try:
# #             return datetime.strptime(s, f).time()
# #         except ValueError:
# #             continue
# #     return None


# # def _parse_dt(v) -> Optional[datetime]:
# #     """Dates / datetimes as stored in the maintenance and log tables (ISO, dd-mm-yyyy, dd/mm/yyyy, with or without time)."""
# #     if v is None or v == "":
# #         return None
# #     if isinstance(v, datetime):
# #         return v if v.tzinfo is None else v.astimezone().replace(tzinfo=None)
# #     if isinstance(v, date):
# #         return datetime.combine(v, time.min)
# #     s = str(v).strip()
# #     if not s:
# #         return None
# #     try:
# #         dt = datetime.fromisoformat(s[:-1] if s.endswith("Z") else s)
# #         return dt if dt.tzinfo is None else dt.astimezone().replace(tzinfo=None)
# #     except ValueError:
# #         pass
# #     for df in _DATE_FMTS:
# #         for tf in ("",) + tuple(" " + t for t in _TIME_FMTS):
# #             try:
# #                 return datetime.strptime(s, df + tf)
# #             except ValueError:
# #                 continue
# #     return None


# # def _merge(intervals: Iterable[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
# #     out: List[List[datetime]] = []
# #     for a, b in sorted(intervals):
# #         if out and a <= out[-1][1]:
# #             out[-1][1] = max(out[-1][1], b)
# #         else:
# #             out.append([a, b])
# #     return [(a, b) for a, b in out]


# # def step_name(row) -> str:
# #     """Stage name of a ProductWorkflowMapping row (via its process_detail relationship -> process_flow_master)."""
# #     pd = row.process_detail
# #     return (pd.step_name if pd and pd.step_name else None) or f"Step {row.flow_step_id}"


# # # --------------------------------------------------------------------------------------
# # # Calendar with a per-station daily window + machine down-time
# # # --------------------------------------------------------------------------------------
# # class DayCalendar:
# #     """A working day d has a window [d shift_start, +capacity*factor). A station's capacity decides the window length.
# #     `blocks` (sorted, merged (start, end) pairs) are times the machine is down; work never runs inside them."""

# #     def __init__(self, holidays: Dict[date, str], exceptions: Dict[date, str], shift_start: float):
# #         self.holidays = holidays
# #         self.exceptions = {d: (t or "").strip().lower() for d, t in exceptions.items()}
# #         self.shift_start = float(shift_start)

# #     def factor(self, d: date) -> float:
# #         exc = self.exceptions.get(d)
# #         if exc == "working":
# #             return 1.0
# #         if exc == "half-day":
# #             return 0.5
# #         if exc == "holiday":
# #             return 0.0
# #         if d in self.holidays:
# #             return 0.0
# #         if d.weekday() in WEEKLY_OFF_DAYS:
# #             return 0.0
# #         if d.weekday() == 5 and ((d.day - 1) // 7 + 1) in ALT_SATURDAYS_OFF:
# #             return 0.0
# #         return 1.0

# #     def off_reason(self, d: date) -> str:
# #         if d in self.holidays:
# #             return self.holidays[d] or "Holiday"
# #         if self.exceptions.get(d) == "holiday":
# #             return "Holiday"
# #         if d.weekday() == 6:
# #             return "Sunday"
# #         if d.weekday() == 5:
# #             return "1st/3rd Saturday"
# #         return "Off"

# #     def window(self, d: date, cap_min: float) -> Tuple[datetime, datetime]:
# #         ws = datetime.combine(d, time.min) + timedelta(hours=self.shift_start)
# #         return ws, ws + timedelta(minutes=cap_min * self.factor(d))

# #     def first_working_day(self, d: date) -> date:
# #         for _ in range(4000):
# #             if self.factor(d) > 0:
# #                 return d
# #             d += timedelta(days=1)
# #         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

# #     def locate(self, t: datetime, cap_min: float) -> Tuple[datetime, date]:
# #         """Earliest moment >= t inside a working window, and the working day that window belongs to."""
# #         d = t.date() - timedelta(days=1)                      # yesterday's window may spill past midnight
# #         for _ in range(4000):
# #             if self.factor(d) > 0:
# #                 ws, we = self.window(d, cap_min)
# #                 if t < ws:
# #                     return ws, d
# #                 if t < we:
# #                     return t, d
# #             d += timedelta(days=1)
# #         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

# #     def free_pieces(self, t: datetime, cap_min: float, blocks=()):
# #         """Contiguous free stretches (day, start, end) from t onward: inside working windows and outside `blocks`."""
# #         cur, day = self.locate(t, cap_min)
# #         i, n = 0, len(blocks)
# #         for _ in range(500000):
# #             _, we = self.window(day, cap_min)
# #             while i < n and blocks[i][1] <= cur:
# #                 i += 1
# #             if i < n and blocks[i][0] <= cur:                    # machine down right now -> jump past it
# #                 cur, day = self.locate(blocks[i][1], cap_min)
# #                 continue
# #             end = we if i >= n else min(we, blocks[i][0])
# #             if end > cur:
# #                 yield day, cur, end
# #             cur, day = self.locate(end, cap_min)
# #         raise PoGanttError(500, "Could not place a run inside the working calendar")

# #     def consume(self, start: datetime, minutes: float, cap_min: float, blocks=()):
# #         """Run `minutes` of work from `start`, only inside working windows and outside down-time.
# #         Returns (real_start, end, end_day, [(day, seg_start, seg_end, minutes), ...])."""
# #         if minutes <= 0:
# #             cur, day = self.locate(start, cap_min)
# #             return cur, cur, day, []
# #         rem, segs, first = float(minutes), [], None
# #         for day, a, b in self.free_pieces(start, cap_min, blocks):
# #             if first is None:
# #                 first = a
# #             use = min(rem, (b - a).total_seconds() / 60.0)
# #             e = a + timedelta(minutes=use)
# #             segs.append((day, a, e, use))
# #             rem -= use
# #             if rem <= 1e-9:
# #                 return first, e, day, segs
# #         raise PoGanttError(500, "Could not place a run inside the working calendar")

# #     def place_within_day(self, start: datetime, minutes: float, cap_min: float, blocks=()):
# #         """The whole run must sit in ONE free stretch of ONE working day. If it does not fit in what is left, it moves
# #         to the next stretch that can hold it. A run longer than a full day has to spill over.
# #         Returns consume(...) + (fits_in_one_day,)."""
# #         if minutes <= cap_min + 1e-9:
# #             for k, (day, a, b) in enumerate(self.free_pieces(start, cap_min, blocks)):
# #                 if (b - a).total_seconds() / 60.0 + 1e-9 >= minutes:
# #                     e = a + timedelta(minutes=minutes)
# #                     return a, e, day, [(day, a, e, minutes)], True
# #                 if k > 20000:
# #                     break
# #         # longer than one working day: start at the beginning of a day, so it is spread over as few days as possible
# #         for day, a, b in self.free_pieces(start, cap_min, blocks):
# #             if a == self.window(day, cap_min)[0]:
# #                 start = a
# #                 break
# #         return self.consume(start, minutes, cap_min, blocks) + (False,)


# # # --------------------------------------------------------------------------------------
# # # Station container
# # # --------------------------------------------------------------------------------------
# # class Station:
# #     def __init__(self, key: str, name: str, kind: str, step_ids: List[int]):
# #         self.key, self.name, self.kind, self.step_ids = key, name, kind, list(step_ids)   # kind: STEP | LINE
# #         self.steps: List[str] = []                       # member step names (LINE only)
# #         self.options: List[Dict[str, Any]] = []          # ways to run it: {name, resources, phys, blocks}
# #         self.real_machines: List[Tuple[str, str]] = []   # every physical machine of the process: (machine_id, step name)
# #         self.shifts, self.hps, self.cap_min = DEFAULT_SHIFTS, DEFAULT_HOURS_PER_SHIFT, 0.0
# #         self.mode, self.batch_size = "SERIES", DEFAULT_BATCH_SIZE
# #         self.setup = self.cooldown = 0.0
# #         self.cd_working_only = self.next_day_release = False
# #         self.operators = 0
# #         self.material: List[Dict[str, Any]] = []        # consumable shortages of its steps

# #     @property
# #     def machines(self) -> List[str]:
# #         return [o["name"] for o in self.options if o["name"]]


# # # --------------------------------------------------------------------------------------
# # # Loaders
# # # --------------------------------------------------------------------------------------
# # def _load_candidates(db: Session, plant: Optional[str], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
# #     """POs come ONLY from PcbData. Plant filter: the PO's part number must belong to that plant in
# #     product_type_master (PcbData.plant is only used for parts missing from the master).
# #     A PO is loadable when EVERY one of its PCBs has status New or Assigned."""
# #     plant_parts, known_parts = set(), set()
# #     if plant:
# #         for pn, pc in db.query(ProductTypeMaster.part_number, ProductTypeMaster.plant_code).all():
# #             known_parts.add(_norm(pn))
# #             if pc == plant:
# #                 plant_parts.add(_norm(pn))
# #     q = db.query(PcbData.productionOrder, PcbData.partNumber, PcbData.quantity, PcbData.status, PcbData.createdAt,
# #                  PcbData.plant, PcbData.serialNo, PcbData.PCBserialNoPartNumber, PcbData.Type
# #                  ).filter(PcbData.productionOrder.isnot(None), PcbData.productionOrder != "")
# #     by_po: Dict[str, list] = defaultdict(list)
# #     for r in q.all():
# #         if plant:
# #             n = _norm(r[1])
# #             if not (n in plant_parts or (n not in known_parts and (r[5] or "").strip() == plant)):
# #                 continue
# #         by_po[_norm(r[0])].append(r)

# #     cands: Dict[str, Dict[str, Any]] = {}
# #     for po, rows in by_po.items():
# #         parts = [r[1] for r in rows if r[1]]
# #         if not parts:
# #             warnings.append(f"PO {po}: PCBs have no part number - ignored")
# #             continue
# #         part = max(set(parts), key=parts.count)
# #         if len(set(parts)) > 1:
# #             warnings.append(f"PO {po}: PCBs carry several part numbers ({', '.join(sorted(set(parts)))}) - {part} used")
# #         created = [r[4] for r in rows if r[4]]
# #         cands[po] = {
# #             "po": po, "part": part,
# #             "qty": sum(r[2] if (r[2] and r[2] > 0) else 1 for r in rows),
# #             "created": min(created) if created else None,
# #             "started": any((r[3] or "").strip().lower() not in PCB_OPEN_STATUSES for r in rows),
# #             # every PCB of the PO: serial number (links child <-> main), PCB id (pcb_assignment), Type, status
# #             "pcbs": [{"serial": (r[6] or "").strip().upper(), "pcb_id": r[7], "part": r[1], "type": (r[8] or "").strip().upper(),
# #                       "status": (r[3] or "").strip().lower()} for r in rows],
# #         }
# #     return cands


# # def _serial_links(db: Session, cands: Dict[str, Dict[str, Any]], role_of, child_of: Dict[str, str]):
# #     """Child -> main link by SERIAL NUMBER (same rule as the assign step, can_proceed in Data_Server):
# #     the main PCB with serialNo S needs the child PCB with the same serialNo S.
# #     Returns
# #       links {main_po: [{child_po, child_part, pcbs, done, in_progress, not_assigned, steps}]}
# #       unmatched {main_po: number of main PCBs with no child PCB of the same serial}
# #     State of a child PCB (pcb_assignment.assigned_pcb_id = PCBserialNoPartNumber):
# #       no assignment row                     -> not assigned
# #       current_step_id empty / status done   -> done (child flow finished)
# #       current_step_id filled                -> in process (at that step)"""
# #     def is_child(pcb) -> bool:
# #         return pcb["type"].endswith("CHILD") or role_of(pcb["part"]) == "CHILD"

# #     def is_main(pcb) -> bool:
# #         return pcb["type"].endswith("MAIN") or role_of(pcb["part"]) == "MAIN"

# #     child_by_serial: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
# #     for po, c in cands.items():
# #         for pcb in c["pcbs"]:
# #             if pcb["serial"] and is_child(pcb):
# #                 child_by_serial[pcb["serial"]].append((po, pcb))

# #     # assignment state of the child PCBs that can matter
# #     ids = [pcb["pcb_id"] for lst in child_by_serial.values() for _, pcb in lst if pcb["pcb_id"]]
# #     state: Dict[str, Tuple[Optional[int], str]] = {}
# #     for chunk in _chunks(ids):
# #         for a in db.query(PCBAssignment).filter(PCBAssignment.assigned_pcb_id.in_(chunk)).all():
# #             state[a.assigned_pcb_id] = (a.current_step_id, (a.overall_status or "").strip().lower())

# #     links: Dict[str, List[Dict[str, Any]]] = {}
# #     unmatched: Dict[str, int] = {}
# #     for po, c in cands.items():
# #         if role_of(c["part"]) != "MAIN":
# #             continue
# #         per_child: Dict[str, Dict[str, Any]] = {}
# #         missing = 0
# #         for pcb in c["pcbs"]:
# #             if not is_main(pcb):
# #                 continue
# #             hits = [(cpo, ch) for cpo, ch in child_by_serial.get(pcb["serial"], []) if ch["part"] != c["part"]]
# #             want = child_of.get(c["part"])
# #             hits = [h for h in hits if h[1]["part"] == want] or hits        # prefer the child part of its family
# #             if not hits:
# #                 missing += 1
# #                 continue
# #             cpo, ch = hits[0]
# #             l = per_child.setdefault(cpo, {"child_po": cpo, "child_part": ch["part"], "pcbs": 0, "done": 0,
# #                                            "in_progress": 0, "not_assigned": 0, "steps": []})
# #             l["pcbs"] += 1
# #             st = state.get(ch["pcb_id"])
# #             if ch["status"] in DONE_STATUSES or (st and (st[0] is None or st[1] in DONE_STATUSES)):
# #                 l["done"] += 1
# #             elif st:
# #                 l["in_progress"] += 1
# #                 if st[0] not in l["steps"]:
# #                     l["steps"].append(st[0])
# #             else:
# #                 l["not_assigned"] += 1
# #         if per_child:
# #             links[po] = list(per_child.values())
# #             unmatched[po] = missing
# #     return links, unmatched


# # def _product_links(db: Session, warnings: Optional[List[str]] = None):
# #     """Returns (products, child_of {main_pn: child_pn}, role_of(pn) -> 'CHILD' | 'MAIN').
# #     1. product_type_master: CHILD and MAIN rows with the same product_type_name (and plant) belong together.
# #     2. bom_items fallback: the child P/N appears as a material of the main P/N (leading zeros ignored).
# #     3. EXTRA_CHILD_LINKS override."""
# #     products = {p.part_number: p for p in db.query(ProductTypeMaster).all()}
# #     part_by_norm = {_norm(pn): pn for pn in products}

# #     def sub(pn: str) -> str:
# #         p = products.get(pn)
# #         return (p.sub_product_type_name or "").strip().upper() if p else ""

# #     child_of: Dict[str, str] = {}
# #     families: Dict[tuple, Dict[str, List[str]]] = defaultdict(lambda: {"CHILD": [], "MAIN": []})
# #     for pn, p in products.items():
# #         s = sub(pn)
# #         if s in ROLES and _key(p.product_type_name):
# #             families[(_key(p.product_type_name), p.plant_code)][s].append(pn)
# #     for (fam, _plant), g in sorted(families.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
# #         childs = sorted(g["CHILD"])
# #         for m in g["MAIN"]:
# #             if childs:
# #                 child_of[m] = childs[0]
# #                 if len(childs) > 1 and warnings is not None:
# #                     warnings.append(f"Family {fam.upper()}: several child parts ({', '.join(childs)}) - "
# #                                     f"{childs[0]} used to feed {m}")

# #     for main_pn, material in db.query(BOMItem.product_part_number, BOMItem.material).all():
# #         m = part_by_norm.get(_norm(main_pn)) or main_pn
# #         c = part_by_norm.get(_norm(material))
# #         if c and m and c != m and m not in child_of and sub(m) != "CHILD" and sub(c) != "MAIN":
# #             child_of[m] = c
# #     for m, c in EXTRA_CHILD_LINKS.items():
# #         m, c = part_by_norm.get(_norm(m)), part_by_norm.get(_norm(c))
# #         if m and c:
# #             child_of[m] = c
# #     for m, c in list(child_of.items()):
# #         if child_of.get(c) == m:
# #             del child_of[m]
# #     child_parts = set(child_of.values())

# #     def role_of(pn: Optional[str]) -> str:
# #         s = sub(pn or "")
# #         if s in ROLES:
# #             return s
# #         return "CHILD" if pn in child_parts else "MAIN"

# #     return products, child_of, role_of


# # # def _load_downtime(db: Session, machines: Dict[str, Dict[str, Any]], not_before: datetime, now: datetime,
# # #                    warnings: List[str]) -> Dict[str, List[Dict[str, Any]]]:
# # #     """Down-time events per machine_id from machine_breakdown_logs and maintenance_schedules.
# # #     `machines` = {machine_id: {"name", "eqpt_no", ...}} of the plant. Only events ending after `not_before` are kept."""
# # #     by_id = {_key(mid): mid for mid in machines}
# # #     names: Dict[str, List[str]] = defaultdict(list)
# # #     for mid, info in machines.items():
# # #         for n in {_key(info.get("name")), _key(info.get("eqpt_no"))} - {""}:
# # #             if mid not in names[n]:
# # #                 names[n].append(mid)

# # #     def match(rec_id, rec_name) -> Optional[str]:
# # #         mid = by_id.get(_key(rec_id))
# # #         if mid:
# # #             return mid
# # #         for k in (_key(rec_id), _key(rec_name)):
# # #             if k and len(names.get(k, [])) == 1:          # only an unambiguous name
# # #                 return names[k][0]
# # #         return None

# # #     out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# # #     assumed = 0
# # #     try:
# # #         breakdowns = db.query(MachineBreakdownLog).all()
# # #     except Exception as exc:                                 # table missing -> schedule without it
# # #         db.rollback()
# # #         warnings.append(f"machine_breakdown_logs could not be read ({exc.__class__.__name__}) - breakdowns ignored")
# # #         breakdowns = []
# # #     for b in breakdowns:
# # #         mid = match(b.machine_id, b.machine_name)
# # #         if not mid:
# # #             continue
# # #         st = _parse_dt(b.breakdown_date)
# # #         if not st:
# # #             continue
# # #         tt = _parse_time(b.breakdown_time)
# # #         if tt and st.time() == time.min:
# # #             st = datetime.combine(st.date(), tt)
# # #         is_open = (b.status or "").strip().lower() not in DONE_STATUSES
# # #         en, note = _parse_dt(b.mc_ready_date), None
# # #         if not en and b.downtime_hours and b.downtime_hours > 0:
# # #             en = st + timedelta(hours=float(b.downtime_hours))
# # #         if not en and is_open:
# # #             en = max(now, st) + timedelta(hours=OPEN_BREAKDOWN_HOURS)
# # #             note = f"still open - assumed down until {_iso(en)}"
# # #             assumed += 1
# # #         if not en or en <= st or en <= not_before:
# # #             continue
# # #         out[mid].append({"machine": mid, "kind": "BREAKDOWN", "label": b.event_type or "Breakdown",
# # #                          "status": b.status, "start": st, "end": en,
# # #                          "note": note or (b.issue_description or "")})

# # #     try:
# # #         pms = db.query(MaintenanceScheduleLog).all()
# # #     except Exception as exc:
# # #         db.rollback()
# # #         warnings.append(f"maintenance_schedules could not be read ({exc.__class__.__name__}) - maintenance ignored")
# # #         pms = []
# # #     for m in pms:
# # #         mid = match(m.machine_id, m.machine_name)
# # #         if not mid:
# # #             continue
# # #         for q in (1, 2, 3, 4):
# # #             status = (getattr(m, f"q{q}_status") or "").strip().lower()
# # #             if status in DONE_STATUSES:
# # #                 continue
# # #             d = _parse_dt(getattr(m, f"q{q}_actual_date")) or _parse_dt(getattr(m, f"q{q}_planned_date"))
# # #             if not d:
# # #                 continue
# # #             st = datetime.combine(d.date(), time.min)
# # #             en = st + timedelta(days=1)
# # #             if en <= not_before:
# # #                 continue
# # #             out[mid].append({"machine": mid, "kind": "PM", "label": m.event_type or "Preventive Maintenance",
# # #                              "status": getattr(m, f"q{q}_status"), "start": st, "end": en,
# # #                              "note": f"Q{q} maintenance" + (f" - {m.remarks}" if m.remarks else "")})
# # #     if assumed:
# # #         warnings.append(f"{assumed} open breakdown(s) without ready date / downtime - machine assumed down for "
# # #                         f"{OPEN_BREAKDOWN_HOURS:g} h from now")
# # #     for mid in out:
# # #         out[mid].sort(key=lambda e: e["start"])
# # #     return out

# # def _load_downtime(db: Session, machines: Dict[str, Dict[str, Any]], not_before: datetime, now: datetime,
# #                    warnings: List[str]) -> Dict[str, List[Dict[str, Any]]]:
# #     by_id = {_key(mid): mid for mid in machines}
# #     names: Dict[str, List[str]] = defaultdict(list)
# #     for mid, info in machines.items():
# #         for n in {_key(info.get("name")), _key(info.get("eqpt_no"))} - {""}:
# #             if mid not in names[n]:
# #                 names[n].append(mid)

# #     def match(rec_id, rec_name) -> Optional[str]:
# #         mid = by_id.get(_key(rec_id))
# #         if mid: return mid
# #         for k in (_key(rec_id), _key(rec_name)):
# #             if k and len(names.get(k, [])) == 1: return names[k][0]
# #         return None

# #     out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

# #     # 1. Spares (inventorty_spares): a spare only matters when its machine is DOWN. If the spare is out of stock, an open
# #     #    breakdown of that machine lasts at least the procurement lead time (the repair waits for the spare).
# #     #    A running machine is NOT blocked because a spare is missing - that is only a risk (warning).
# #     try:
# #         spares = db.query(InventorySpares).all()
# #     except Exception:
# #         db.rollback()
# #         spares = []
# #     spare_out: Dict[str, Tuple[int, str]] = {}           # machine_id -> (lead days, spare text)
# #     low_spares: List[str] = []
# #     for sp in spares:
# #         q, th = _num(sp.qty_avl), _num(sp.threshold_qty)
# #         if q is None:                                    # no stock figure -> nothing to check
# #             continue
# #         if sp.eqpt_no:
# #             mids = [match(sp.eqpt_no, None)]
# #         else:                                            # spare of a process: every machine of that process
# #             mids = [m for m, info in machines.items() if sp.flow_step_id in info.get("stage_ids", [])]
# #         mids = [m for m in mids if m]
# #         text = sp.decription or sp.part_number or "spare"
# #         if q <= 0:
# #             days = _lead_days(sp.procurement_lead_time)
# #             for m in mids:
# #                 if days >= spare_out.get(m, (0, ""))[0]:
# #                     spare_out[m] = (days, text)
# #         elif th is not None and q <= th:
# #             low_spares.append(f"{text} ({', '.join(mids) or sp.eqpt_no or 'no machine'}: {q:g} left, threshold {th:g})")

# #     # 2. Machine Breakdowns
# #     try:
# #         breakdowns = db.query(MachineBreakdownLog).all()
# #     except Exception:
# #         db.rollback()
# #         breakdowns = []
# #     waiting_spare = set()
# #     for b in breakdowns:
# #         mid = match(b.machine_id, b.machine_name)
# #         if not mid: continue
# #         st = _parse_dt(b.breakdown_date)
# #         if not st: continue
# #         tt = _parse_time(b.breakdown_time)
# #         if tt and st.time() == time.min: st = datetime.combine(st.date(), tt)
# #         is_open = (b.status or "").strip().lower() not in DONE_STATUSES
# #         en, note = _parse_dt(b.mc_ready_date), None
# #         if not en and b.downtime_hours and b.downtime_hours > 0:
# #             en = st + timedelta(hours=float(b.downtime_hours))
# #         if not en and is_open:
# #             en = max(now, st) + timedelta(hours=OPEN_BREAKDOWN_HOURS)
# #             note = f"still open - assumed down until {_iso(en)}"
# #             if mid in spare_out:                         # the repair needs a spare that is not in stock
# #                 days, text = spare_out[mid]
# #                 en = max(en, max(now, st) + timedelta(days=days))
# #                 note = f"waiting for spare '{text}' (out of stock, lead time {days} day(s)) - down until {_iso(en)}"
# #                 waiting_spare.add(mid)
# #         if not en or en <= st or en <= not_before: continue
# #         out[mid].append({"machine": mid, "kind": "BREAKDOWN", "label": b.event_type or "Breakdown",
# #                          "status": b.status, "start": st, "end": en, "note": note or (b.issue_description or "")})
# #     if waiting_spare:
# #         warnings.append("Breakdown repair waits for an out-of-stock spare (lead time used): "
# #                         + ", ".join(f"{m} - {spare_out[m][1]} ({spare_out[m][0]} d)" for m in sorted(waiting_spare)))
# #     risk = sorted(m for m in spare_out if m not in waiting_spare)
# #     if risk:
# #         warnings.append("Spare out of stock (machine still running - a breakdown there would take the lead time): "
# #                         + ", ".join(f"{m} - {spare_out[m][1]} ({spare_out[m][0]} d)" for m in risk))
# #     if low_spares:
# #         warnings.append("Spares at or below threshold: " + "; ".join(low_spares))

# #     # 3. Maintenance Schedules
# #     try:
# #         pms = db.query(MaintenanceScheduleLog).all()
# #     except Exception:
# #         db.rollback()
# #         pms = []
# #     for m in pms:
# #         mid = match(m.machine_id, m.machine_name)
# #         if not mid: continue
# #         for q in (1, 2, 3, 4):
# #             if (getattr(m, f"q{q}_status") or "").strip().lower() in DONE_STATUSES: continue
# #             d = _parse_dt(getattr(m, f"q{q}_actual_date")) or _parse_dt(getattr(m, f"q{q}_planned_date"))
# #             if not d: continue
# #             st = datetime.combine(d.date(), time.min)
# #             en = st + timedelta(days=1)
# #             if en <= not_before: continue
# #             out[mid].append({"machine": mid, "kind": "PM", "label": m.event_type or "Preventive Maintenance",
# #                              "status": getattr(m, f"q{q}_status"), "start": st, "end": en,
# #                              "note": f"Q{q} maintenance" + (f" - {m.remarks}" if m.remarks else "")})

# #     for mid in out:
# #         out[mid].sort(key=lambda e: e["start"])
# #     return out

# # def _num(v) -> Optional[float]:
# #     """'12', '12.5', ' 12 nos' -> number; empty / text -> None."""
# #     m = re.search(r"-?\d+(\.\d+)?", str(v)) if v is not None else None
# #     return float(m.group()) if m else None


# # def _lead_days(v) -> int:
# #     """procurement_lead_time: '10', '10 days', '2 weeks' -> days."""
# #     n = _num(v)
# #     if n is None or n <= 0:
# #         return DEFAULT_SPARE_LEAD_DAYS
# #     return int(math.ceil(n * 7)) if "week" in str(v).lower() else int(math.ceil(n))


# # def _load_consumable_blocks(db: Session, now: datetime, not_before: datetime,
# #                             warnings: List[str]) -> Dict[int, List[Dict[str, Any]]]:
# #     """Consumables (consumables table) of every process (stage_id = flow_step_id).
# #     A consumable (material number) is usable when one of its rows has quantity > 0 (empty quantity = not counted, taken
# #     as available) and is not past consumable_shelf_life. The PROCESS cannot run (all its machines, and a process without
# #     a machine too) while one of its consumables is not usable:
# #         out of stock / already expired -> blocked from now for CONSUMABLE_RESTOCK_DAYS
# #         every batch in stock expires   -> blocked from the day after the last expiry for CONSUMABLE_RESTOCK_DAYS
# #     The table has no use per PCB, so stock is checked as available yes / no, it is not used up PCB by PCB."""
# #     try:
# #         rows = db.query(Consumables).all()
# #     except Exception:
# #         db.rollback()
# #         return {}
# #     groups: Dict[Tuple[int, str], list] = defaultdict(list)
# #     for c in rows:
# #         if c.stage_id is not None:
# #             groups[(c.stage_id, _key(c.consumable_material_number) or _key(c.consumable_material_name))].append(c)
# #     today = now.date()

# #     def expiry(c) -> Optional[date]:
# #         d = c.consumable_shelf_life
# #         return d.date() if isinstance(d, datetime) else d

# #     out: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
# #     low: List[str] = []
# #     for (sid, _), lst in groups.items():
# #         first = lst[0]
# #         name = first.consumable_material_name or first.consumable_material_number or "consumable"
# #         mat = first.consumable_material_number or ""
# #         in_stock = [c for c in lst if c.quantity is None or c.quantity > 0]
# #         usable = [c for c in in_stock if not expiry(c) or expiry(c) >= today]
# #         ev = None
# #         if not usable:
# #             why = "out of stock" if not in_stock else f"expired on {max(expiry(c) for c in in_stock):%d-%m-%Y}"
# #             ev = {"label": "Consumable " + ("out of stock" if not in_stock else "expired"), "start": now,
# #                   "end": now + timedelta(days=CONSUMABLE_RESTOCK_DAYS),
# #                   "note": f"{name} {mat} {why} - assumed back in {CONSUMABLE_RESTOCK_DAYS} day(s)"}
# #         elif all(expiry(c) for c in usable):
# #             last = max(expiry(c) for c in usable)
# #             st = datetime.combine(last + timedelta(days=1), time.min)
# #             ev = {"label": "Consumable expires", "start": st, "end": st + timedelta(days=CONSUMABLE_RESTOCK_DAYS),
# #                   "note": f"{name} {mat}: the stock expires on {last:%d-%m-%Y} - assumed back in {CONSUMABLE_RESTOCK_DAYS} day(s)"}
# #         if ev and ev["end"] > not_before:
# #             out[sid].append({"machine": None, "kind": "SHORTAGE", "status": "Awaiting stock", "stage_id": sid,
# #                              "material": mat, "material_name": name, **ev})
# #         qty = [c.quantity for c in usable if c.quantity is not None]
# #         th = max((x for x in (_num(c.threshold_qty) for c in lst) if x is not None), default=None)
# #         if usable and qty and th is not None and sum(qty) <= th:
# #             low.append(f"{name} (step {sid}: {sum(qty)} left, threshold {th:g})")
# #     if low:
# #         warnings.append("Consumables at or below threshold: " + "; ".join(low))
# #     return out


# # def _dt_json(e: Dict[str, Any]) -> Dict[str, Any]:
# #     return {**e, "start": _iso(e["start"]), "end": _iso(e["end"])}


# # def list_open_orders(db: Session, plant: Optional[str] = None) -> Dict[str, Any]:
# #     """Yet-to-start POs for the picker (oldest first) + the part numbers of the plant (product_type_master)."""
# #     warnings: List[str] = []
# #     _, _, role_of = _product_links(db)
# #     cands = _load_candidates(db, plant, warnings)
# #     open_pos = sorted((c for c in cands.values() if not c["started"]),
# #                       key=lambda c: (c["created"] or datetime.max, c["po"]))
# #     pq = db.query(ProductTypeMaster)
# #     if plant:
# #         pq = pq.filter(ProductTypeMaster.plant_code == plant)
# #     parts = [{"part_number": p.part_number, "role": role_of(p.part_number), "product_type": p.product_type_name,
# #               "sub_type": p.sub_product_type_name, "description": p.description}
# #              for p in pq.order_by(ProductTypeMaster.product_type_name, ProductTypeMaster.part_number).all()]
# #     return {"orders": [{"production_order": c["po"], "part_number": c["part"], "quantity": c["qty"],
# #                         "role": role_of(c["part"]), "created": c["created"].isoformat() if c["created"] else None}
# #                        for c in open_pos],
# #             "parts": parts,
# #             "warnings": warnings}


# # def list_plants(db: Session) -> Dict[str, Any]:
# #     """Plant codes of product_type_master (a PO belongs to the plant of its part number)."""
# #     codes = sorted({(r[0] or "").strip() for r in db.query(ProductTypeMaster.plant_code).distinct().all()
# #                     if (r[0] or "").strip()})
# #     info = {p.plant_code: p.location for p in db.query(Plant).all()}
# #     return {"plants": [{"plant_code": c, "location": info.get(c) or ""} for c in codes]}


# # def ensure_part_process_time_columns(engine) -> None:
# #     """create_all() does not alter existing tables - add machine_hours / batch_size once if they are missing."""
# #     try:
# #         cols = {c["name"] for c in sa_inspect(engine).get_columns("part_process_time")}
# #         with engine.begin() as conn:
# #             if "machine_hours" not in cols:
# #                 conn.execute(sa_text("ALTER TABLE part_process_time ADD COLUMN machine_hours DOUBLE PRECISION NOT NULL DEFAULT 0"))
# #             if "batch_size" not in cols:
# #                 conn.execute(sa_text("ALTER TABLE part_process_time ADD COLUMN batch_size INTEGER"))
# #     except Exception as exc:                                   # never block start-up
# #         print(f"[po_gantt] could not verify part_process_time columns: {exc}")


# # _PLAN_TABLES_READY = False


# # def ensure_plan_tables(bind) -> None:
# #     """Create schedule_plan / schedule_plan_item if they do not exist yet (create_all does this too)."""
# #     global _PLAN_TABLES_READY
# #     if _PLAN_TABLES_READY:
# #         return
# #     SchedulePlan.__table__.create(bind=bind, checkfirst=True)
# #     SchedulePlanItem.__table__.create(bind=bind, checkfirst=True)
# #     _PLAN_TABLES_READY = True


# # def list_part_process_times(db: Session, plant: Optional[str], part_no: Optional[str] = None) -> Dict[str, Any]:
# #     """Every routing step of every part of the plant, joined with its part_process_time row (if any)."""
# #     pq = db.query(ProductTypeMaster)
# #     if plant:
# #         pq = pq.filter(ProductTypeMaster.plant_code == plant)
# #     if part_no:
# #         pq = pq.filter(ProductTypeMaster.part_number == part_no)
# #     products = pq.order_by(ProductTypeMaster.product_type_name, ProductTypeMaster.sub_product_type_name,
# #                            ProductTypeMaster.part_number).all()
# #     pns = [p.part_number for p in products]
# #     if not pns:
# #         return {"plant": plant, "parts": [], "rows": []}
# #     batch = {p.stage_id for p in db.query(Processtype).filter(Processtype.process_type_batch.is_(True)).all()}
# #     ppt = {}
# #     tq = db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(pns))
# #     if plant:
# #         tq = tq.filter(PartProcessTime.plant == plant)
# #     for r in tq.all():
# #         ppt[(r.part_no, r.process_id)] = r
# #     rows = []
# #     for p in products:
# #         steps = db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
# #                 ).filter(ProductWorkflowMapping.product_part_number == p.part_number
# #                 ).order_by(ProductWorkflowMapping.step_sequence, ProductWorkflowMapping.id).all()
# #         for st in steps:
# #             r = ppt.get((p.part_number, st.flow_step_id))
# #             rows.append({
# #                 "part_no": p.part_number, "product_type": p.product_type_name, "sub_type": p.sub_product_type_name,
# #                 "process_id": st.flow_step_id, "process_name": step_name(st), "step_sequence": st.step_sequence,
# #                 "is_batch": st.flow_step_id in batch,
# #                 "sap_time": r.sap_time if r else None, "actual_time": r.actual_time if r else None,
# #                 "machine_hours": float(r.machine_hours or 0) if r else 0.0,
# #                 "batch_size": r.batch_size if r else None,
# #             })
# #     return {"plant": plant,
# #             "parts": [{"part_no": p.part_number, "product_type": p.product_type_name, "sub_type": p.sub_product_type_name,
# #                        "description": p.description} for p in products],
# #             "rows": rows}


# # class PartTimeItem(BaseModel):
# #     part_no: str
# #     process_id: int
# #     machine_hours: Optional[float] = 0.0
# #     batch_size: Optional[int] = None


# # class PartTimeSave(BaseModel):
# #     plant: str
# #     items: List[PartTimeItem]


# # def save_part_process_times(db: Session, body: PartTimeSave) -> Dict[str, Any]:
# #     stage_names = {s.flow_step_id: s.step_name for s in db.query(ProcessFlowMaster).all()}
# #     updated = created = 0
# #     for it in body.items:
# #         mh = float(it.machine_hours or 0)
# #         if mh < 0:
# #             raise PoGanttError(422, f"{it.part_no} / step {it.process_id}: machine hours cannot be negative")
# #         if it.batch_size is not None and it.batch_size < 0:
# #             raise PoGanttError(422, f"{it.part_no} / step {it.process_id}: batch size cannot be negative")
# #         bs = int(it.batch_size) if it.batch_size and it.batch_size > 0 else None
# #         row = db.query(PartProcessTime).filter(
# #             PartProcessTime.part_no == it.part_no, PartProcessTime.plant == body.plant,
# #             PartProcessTime.process_id == it.process_id).first()
# #         if row:
# #             row.machine_hours, row.batch_size = mh, bs
# #             updated += 1
# #         else:
# #             if it.process_id not in stage_names:
# #                 raise PoGanttError(404, f"Process step {it.process_id} not found")
# #             db.add(PartProcessTime(part_no=it.part_no, plant=body.plant, process_id=it.process_id,
# #                                    process_name=stage_names[it.process_id], machine_hours=mh, batch_size=bs))
# #             created += 1
# #     db.commit()
# #     return {"updated": updated, "created": created}


# # # --------------------------------------------------------------------------------------
# # # Builder
# # # --------------------------------------------------------------------------------------
# # def build_po_gantt(db: Session, production_orders: Optional[List[str]] = None, plant: Optional[str] = None,
# #                    start_date: Optional[date] = None, time_source: str = "actual", label_mode: str = "seq",
# #                    show_holidays: bool = False, shift_start: float = DEFAULT_SHIFT_START,
# #                    today: Optional[date] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
# #     if time_source not in ("actual", "sap"):
# #         raise PoGanttError(400, "time_source must be 'actual' or 'sap'")
# #     if label_mode not in ("seq", "po"):
# #         raise PoGanttError(400, "label_mode must be 'seq' or 'po'")
# #     warnings: List[str] = []
# #     now = now or datetime.now()
# #     today = today or now.date()

# #     # ---------------- calendar ----------------
# #     holidays = {h.holiday_date: h.name for h in db.query(PublicHoliday).all()}
# #     exceptions = {e.exception_date: e.exception_type for e in db.query(CalendarException).all()}
# #     cal = DayCalendar(holidays, exceptions, shift_start)
# #     day_cap = max((DAY_END_HOUR - shift_start) * 60.0, 60.0)       # the working day ends at 22:00

# #     # ---------------- masters (loaded once) ----------------
# #     products, child_of, role_of = _product_links(db, warnings)

# #     is_batch: Dict[int, bool] = defaultdict(bool)
# #     for p in db.query(Processtype).all():
# #         if p.process_type_batch:
# #             is_batch[p.stage_id] = True
# #     cfg = {c.stage_id: c for c in db.query(StageScheduleConfig).all()}
# #     cap_by_key = {_key(c.name): c for c in db.query(StageCapacityDB).all()}
# #     cap_compact = {k.replace(" ", ""): c for k, c in cap_by_key.items()}

# #     def find_cap(name: Optional[str]):
# #         """stage_capacity row of a process: exact name, then ignoring spaces / punctuation, then a UNIQUE partial match."""
# #         k = _key(name)
# #         if not k:
# #             return None
# #         c = cap_by_key.get(k) or cap_compact.get(k.replace(" ", ""))
# #         if c:
# #             return c
# #         hits = [v for ck, v in cap_by_key.items() if ck and (ck in k or k in ck)]
# #         return hits[0] if len(hits) == 1 else None

# #     equipment: Dict[int, List[str]] = defaultdict(list)          # stage_id -> machine_ids
# #     machine_info: Dict[str, Dict[str, Any]] = {}                  # machine_id -> details
# #     for e in db.query(Equipments).order_by(Equipments.stage_id, Equipments.id).all():
# #         if plant and e.plant_code and e.plant_code != plant:          # only the machines of the chosen plant
# #             continue
# #         mid = e.machine_id or e.eqpt_no or f"EQ-{e.id}"
# #         if e.stage_id is not None and mid not in equipment[e.stage_id]:
# #             equipment[e.stage_id].append(mid)
# #         info = machine_info.setdefault(mid, {"machine_id": mid, "name": e.eqpt_name or mid, "eqpt_no": e.eqpt_no,
# #                                              "process_type": e.process_type,
# #                                              "make": e.eqpt_make, "model": e.eqpt_model,
# #                                              "workcenter": e.workcenter_name, "stage_ids": []})
# #         if e.stage_id is not None and e.stage_id not in info["stage_ids"]:
# #             info["stage_ids"].append(e.stage_id)

# #     # equipment is normally linked by stage_id = flow_step_id. A process whose flow step has a different id / spelling
# #     # (e.g. "BAKING" vs "Baking") would then wrongly look manual - so also match by the step NAME, and by the
# #     # equipment's own process_type / workcenter / name.
# #     stage_names = {r.flow_step_id: r.step_name for r in db.query(ProcessFlowMaster).all()}
# #     eq_by_stage_name: Dict[str, List[str]] = defaultdict(list)
# #     for sid_, mids_ in equipment.items():
# #         k_ = _key(stage_names.get(sid_))
# #         for m_ in mids_:
# #             if k_ and m_ not in eq_by_stage_name[k_]:
# #                 eq_by_stage_name[k_].append(m_)
# #     eq_by_label: Dict[str, List[str]] = defaultdict(list)
# #     for m_, inf_ in machine_info.items():
# #         for lab_ in (inf_.get("process_type"), inf_.get("workcenter"), inf_.get("name")):
# #             k_ = _key(lab_)
# #             if k_ and m_ not in eq_by_label[k_]:
# #                 eq_by_label[k_].append(m_)

# #     def machines_for_step(sid: int, name: str) -> List[str]:
# #         k_ = _key(name)
# #         for pool in (equipment.get(sid), eq_by_stage_name.get(k_), eq_by_label.get(k_)):
# #             if pool:
# #                 return list(pool)
# #         return []

# #     shift_names = [s.name for s in db.query(ShiftDefinition).filter(ShiftDefinition.is_active.is_(True))
# #                    .order_by(ShiftDefinition.sort_order, ShiftDefinition.id).all()]
# #     assigned: Dict[str, set] = defaultdict(set)
# #     for a in db.query(OperatorShiftAssignment).all():
# #         assigned[a.operator_staff_no].add(a.shift_name)
# #     ops_by_stage: Dict[int, List[str]] = defaultdict(list)
# #     for o in db.query(OperatorStepMapping).all():
# #         who = o.operator_staff_no or o.operator_name
# #         if who and who not in ops_by_stage[o.flow_step_id]:
# #             ops_by_stage[o.flow_step_id].append(who)

# #     def operators_per_shift(sid: int) -> int:
# #         ops = ops_by_stage.get(sid, [])
# #         if not shift_names:
# #             return len(ops)
# #         return max((sum(1 for o in ops if not assigned.get(o) or sn in assigned[o]) for sn in shift_names), default=0)

# #     line_of_name = {_key(n): g for g, names in LINE_GROUPS.items() for n in names}

# #     # ---------------- select the POs to load ----------------
# #     cands = _load_candidates(db, plant, warnings)
# #     if production_orders:
# #         selected, seen = [], set()
# #         for raw in production_orders:
# #             k = _norm(raw) or raw
# #             if k in seen:
# #                 continue
# #             seen.add(k)
# #             if k not in cands:
# #                 raise PoGanttError(404, f"Production order {raw} not found")
# #             if cands[k]["started"]:
# #                 warnings.append(f"PO {k} has already started - scheduled from scratch as requested")
# #             selected.append(cands[k])
# #         explicit = True
# #     else:
# #         selected = sorted((c for c in cands.values() if not c["started"]),
# #                           key=lambda c: (c["created"] or datetime.max, c["po"]))
# #         explicit = False

# #     # ---------------- routing (product_workflow_mapping) + times ----------------
# #     # child -> main by serial number; the child POs that are NOT in this schedule are still needed (in process / what-if)
# #     serial_links, serial_unmatched = _serial_links(db, cands, role_of, child_of)
# #     sel_pos = {c["po"] for c in selected}
# #     outside_child_pos = {l["child_po"] for c in selected for l in serial_links.get(c["po"], []) if l["child_po"] not in sel_pos}
# #     part_numbers = {c["part"] for c in selected if c["part"]} | {cands[x]["part"] for x in outside_child_pos if cands[x]["part"]}
# #     routing: Dict[str, list] = defaultdict(list)
# #     times: Dict[tuple, list] = defaultdict(list)
# #     if part_numbers:
# #         for r in db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
# #                 ).filter(ProductWorkflowMapping.product_part_number.in_(part_numbers)
# #                 ).order_by(ProductWorkflowMapping.product_part_number, ProductWorkflowMapping.step_sequence,
# #                            ProductWorkflowMapping.id).all():
# #             routing[r.product_part_number].append(r)
# #         tq = db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(part_numbers))
# #         if plant:
# #             tq = tq.filter(PartProcessTime.plant == plant)
# #         for r in tq.all():
# #             times[(r.part_no, r.process_id)].append(r)
# #     other = "sap" if time_source == "actual" else "actual"

# #     def time_row(part: str, sid: int):
# #         rows = times.get((part, sid), [])
# #         if not rows:
# #             return None
# #         pref = plant or (products[part].plant_code if part in products else None)
# #         return next((r for r in rows if r.plant == pref), rows[0])

# #     def hours_per_unit(part: str, step) -> Tuple[Optional[float], str]:
# #         """Hours for one unit (SERIES) / one batch (BATCH) = base time + machine hours."""
# #         row = time_row(part, step.flow_step_id)
# #         mh = max(float(getattr(row, "machine_hours", 0) or 0), 0.0) if row else 0.0
# #         base, src = None, "none"
# #         if row:
# #             for s in (time_source, other):
# #                 val = row.actual_time if s == "actual" else row.sap_time
# #                 if val and val > 0:
# #                     base, src = float(val), f"part_process_time.{s}"
# #                     break
# #         if base is None and getattr(step, "process_time_seconds", None) and step.process_time_seconds > 0:
# #             base, src = step.process_time_seconds / 3600.0, "routing"
# #         if base is None:
# #             cap = find_cap(step_name(step))
# #             if cap and cap.manufacturing_time_mins and cap.manufacturing_time_mins > 0:
# #                 base, src = float(cap.manufacturing_time_mins) / 60.0, "stage_capacity"
# #         if base is None and mh <= 0:
# #             return None, "none"
# #         return (base or 0.0) + mh, src + (" + machine_hours" if mh > 0 else "")

# #     def batch_size_for(part: str, sid: int) -> int:
# #         row = time_row(part, sid)
# #         if row and getattr(row, "batch_size", None) and row.batch_size > 0:
# #             return int(row.batch_size)
# #         return max(int((cfg[sid].batch_size if sid in cfg else 0) or DEFAULT_BATCH_SIZE), 1)

# #     def capacity_for(names: List[str]) -> Optional[Tuple[int, float]]:
# #         for n in names:
# #             c = find_cap(n)
# #             if c:
# #                 sh = int(c.shifts_per_day or 0)
# #                 hp = float(c.hours_per_shift or 0)
# #                 return (sh if sh > 0 else DEFAULT_SHIFTS), (hp if hp > 0 else DEFAULT_HOURS_PER_SHIFT)
# #         return None

# #     # ---------------- operations of a part (its flow, with the line steps merged) ----------------
# #     ops_cache: Dict[str, List[Dict[str, Any]]] = {}

# #     def ops_for(part: str) -> List[Dict[str, Any]]:
# #         if part in ops_cache:
# #             return ops_cache[part]
# #         steps = routing.get(part, [])
# #         ops, done = [], set()
# #         for st in steps:
# #             g = line_of_name.get(_key(step_name(st)))
# #             if g:
# #                 if g in done:
# #                     continue
# #                 done.add(g)
# #                 members = [x for x in steps if line_of_name.get(_key(step_name(x))) == g]
# #                 ops.append({"key": f"LINE-{g}", "line": g, "steps": members})
# #             else:
# #                 ops.append({"key": f"STEP-{st.flow_step_id}", "line": None, "steps": [st]})
# #         ops_cache[part] = ops
# #         return ops

# #     # ---------------- build PO objects ----------------
# #     pos: List[Dict[str, Any]] = []
# #     for c in selected:
# #         part, po_no = c["part"], c["po"]
# #         steps = routing.get(part or "", [])
# #         if not steps or c["qty"] <= 0:
# #             msg = (f"PO {po_no}: part {part} has no flow in product_workflow_mapping" if not steps
# #                    else f"PO {po_no}: quantity is 0")
# #             if explicit:
# #                 raise PoGanttError(422, msg)
# #             warnings.append(msg + " - not scheduled")
# #             continue
# #         pos.append({"po": po_no, "part": part, "qty": c["qty"], "ops": ops_for(part), "idx": len(pos) + 1,
# #                     "role": role_of(part)})
# #     if not pos:
# #         raise PoGanttError(404, "No production orders to schedule")
# #     for p in pos:
# #         p["label"] = f"B{p['idx']}" if label_mode == "seq" else p["po"]
# #     label_idx = {p["label"]: p["idx"] for p in pos}
# #     label_role = {p["label"]: p["role"] for p in pos}

# #     # ---------------- machine down-time (breakdowns + preventive maintenance) ----------------
# #     start_day = cal.first_working_day(start_date or today)
# #     start_dt = datetime.combine(start_day, time.min) + timedelta(hours=shift_start)
# #     downtime = _load_downtime(db, machine_info, start_dt, now, warnings)
# #     blocks_of = {mid: _merge((e["start"], e["end"]) for e in evs) for mid, evs in downtime.items()}
# #     material = _load_consumable_blocks(db, now, start_dt, warnings)     # flow_step_id -> consumable shortages

# #     # ---------------- stations ----------------
# #     stations: Dict[str, Station] = {}
# #     cap_missing: List[str] = []

# #     def make_station(op: Dict[str, Any]) -> Station:
# #         key = op["key"]
# #         if key in stations:
# #             return stations[key]
# #         members = op["steps"]
# #         sids = [m.flow_step_id for m in members]
# #         if op["line"]:
# #             g = op["line"]
# #             s = Station(key, g, "LINE", sids)
# #             s.steps = [step_name(m) for m in members]
# #             s.mode = "LINE"
# #             mach_of = {m.flow_step_id: machines_for_step(m.flow_step_id, step_name(m)) for m in members}
# #             with_eq = [(m.flow_step_id, step_name(m)) for m in members if mach_of[m.flow_step_id]]
# #             n = min(len(mach_of[i]) for i, _ in with_eq) if with_eq else 1   # as parallel as its narrowest step
# #             for i in range(n):
# #                 phys = [(mach_of[sid][i], nm) for sid, nm in with_eq]
# #                 s.options.append({"name": g if n == 1 else f"{g} #{i + 1}",
# #                                   "resources": [m for m, _ in phys] or [f"LINE-{g}-{i}"], "phys": phys})
# #             s.real_machines = [(mid, nm) for sid, nm in with_eq for mid in mach_of[sid]]
# #             s.setup = max([float(cfg[i].setup_minutes or 0) for i in sids if i in cfg], default=0.0)
# #             s.operators = max(operators_per_shift(i) for i in sids)
# #             last = cfg.get(sids[-1])
# #             names = [g] + s.steps
# #         else:
# #             sid = sids[0]
# #             s = Station(key, step_name(members[0]), "STEP", sids)
# #             s.mode = "BATCH" if is_batch.get(sid) else "SERIES"
# #             last = cfg.get(sid)
# #             if last:
# #                 s.batch_size = max(int(last.batch_size or DEFAULT_BATCH_SIZE), 1)
# #                 s.setup = float(last.setup_minutes or 0)
# #             mids = machines_for_step(sid, s.name)
# #             rmode = (str(getattr(last, "resource_mode", None) or "AUTO")).upper() if last else "AUTO"
# #             if rmode == "MANUAL":                                   # stage_schedule_config.resource_mode forces manual
# #                 mids = []
# #             elif rmode == "MACHINE" and not mids:
# #                 warnings.append(f"{s.name}: resource_mode is MACHINE but no machine is mapped in equipment_details")
# #             if mids:
# #                 s.options = [{"name": mid, "resources": [mid], "phys": [(mid, s.name)]} for mid in mids]
# #                 s.real_machines = [(mid, s.name) for mid in mids]
# #             else:
# #                 slots = max(int(MANUAL_PARALLEL_SLOTS), 1)          # no machine -> people: several POs can run side by side
# #                 s.options = [{"name": "", "resources": [f"NO-MACHINE-{sid}-{k}"], "phys": []} for k in range(slots)]
# #             s.operators = operators_per_shift(sid)
# #             names = [s.name]
# #         # a consumable shortage of ANY step stops the whole process (SMT LINE: the whole line), machine or not
# #         s.material = [e for i in sids for e in material.get(i, [])]
# #         mat_blocks = [(e["start"], e["end"]) for e in s.material]
# #         for o in s.options:
# #             o["blocks"] = _merge([b for r in o["resources"] for b in blocks_of.get(r, [])] + mat_blocks)
# #         if last:
# #             s.cooldown = float(last.cooldown_minutes or 0)
# #             s.cd_working_only = bool(last.cooldown_working_time_only)
# #             s.next_day_release = bool(last.next_day_release) and bool(is_batch.get(sids[-1]))
# #         got = capacity_for(names)
# #         if got:
# #             s.shifts, s.hps = got
# #         if not got:
# #             cap_missing.append(s.name)
# #         s.cap_min = min(s.shifts * s.hps * 60.0, day_cap)
# #         stations[key] = s
# #         return s

# #     for p in pos:
# #         for op in p["ops"]:
# #             make_station(op)
# #     for cpo in outside_child_pos:                       # child POs outside the schedule (only for estimates)
# #         for op in ops_for(cands[cpo]["part"]):
# #             make_station(op)
# #     if cap_missing:
# #         warnings.append(f"No stage_capacity row matches: {', '.join(dict.fromkeys(cap_missing))} - default "
# #                         f"{DEFAULT_SHIFTS} shifts x {DEFAULT_HOURS_PER_SHIFT:g} h used (add the process name to stage_capacity)")

# #     # ---------------- run time of one operation ----------------
# #     missing_time: Dict[str, List[str]] = defaultdict(list)

# #     def step_minutes(part: str, st, qty: int) -> Optional[Tuple[float, float]]:
# #         """(minutes for the whole PO, minutes for the first board / batch) of one routing step."""
# #         hrs, _src = hours_per_unit(part, st)
# #         if hrs is None:
# #             return None
# #         t = hrs * 60.0
# #         sid = st.flow_step_id
# #         if is_batch.get(sid):
# #             bs = batch_size_for(part, sid)
# #             return math.ceil(qty / bs) * t, t
# #         return qty * t, t

# #     def op_minutes_and_parts(p: Dict[str, Any], op: Dict[str, Any], s: Station):
# #         """Minutes of one operation for the whole PO, and (PO minutes, first board / batch minutes) of each step in it.
# #         SMT LINE: the steps run one after the other, so the line time is the SUM of its steps."""
# #         parts = []
# #         for st in op["steps"]:
# #             m = step_minutes(p["part"], st, p["qty"])
# #             if m is None:
# #                 missing_time[p["part"]].append(step_name(st))
# #                 m = (FALLBACK_MINUTES, FALLBACK_MINUTES)
# #             parts.append(m)
# #         total = sum(m[0] for m in parts) if s.kind == "LINE" else parts[0][0]
# #         return max(total + s.setup, 1.0), parts

# #     # ---------------- child PO -> main PO ----------------
# #     # 1. by SERIAL number: the main PCB needs the child PCB with the same serial (as the assign step checks it).
# #     #    child PO in this schedule          -> the main PO waits for it
# #     #    child PO outside, PCBs done        -> nothing to wait for
# #     #    child PO outside, PCBs in process  -> the main PO waits for the estimated end of the child (rest of its flow)
# #     #    child PO outside, NOT assigned     -> the main PO is scheduled without waiting (FORCED) + "assign the child on
# #     #                                          day X -> main can start on day Y" message
# #     # 2. main POs without any serial match: first come, first served by quantity (as before).
# #     depends_on: Dict[str, List[str]] = defaultdict(list)
# #     link_by: Dict[str, str] = {}                                    # main po -> "serial" | "quantity"
# #     outside_links: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # main po -> child links outside the schedule
# #     by_part: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# #     for p in pos:
# #         by_part[p["part"]].append(p)
# #     in_plan = {p["po"] for p in pos}
# #     taken_by_serial: Dict[str, int] = defaultdict(int)             # child po -> PCBs already linked by serial
# #     for m in pos:
# #         links = serial_links.get(m["po"], [])
# #         if not links:
# #             continue
# #         link_by[m["po"]] = "serial"
# #         for l in links:
# #             taken_by_serial[l["child_po"]] += l["pcbs"]
# #             if l["child_po"] in in_plan:
# #                 depends_on[m["po"]].append(l["child_po"])
# #             else:
# #                 outside_links[m["po"]].append(l)
# #         if serial_unmatched.get(m["po"]):
# #             warnings.append(f"PO {m['po']} ({m['label']}): {serial_unmatched[m['po']]} main PCB(s) have no child PCB with "
# #                             f"the same serial number - those child PCBs are assumed in stock")
# #     for main_pn, child_pn in child_of.items():
# #         mains = [m for m in by_part.get(main_pn, []) if m["po"] not in link_by]
# #         childs = by_part.get(child_pn, [])
# #         if not mains:
# #             continue
# #         if not childs:
# #             warnings.append(f"Part {main_pn}: no child PO ({child_pn}) loaded and no child PCB with the same serial - "
# #                             f"child PCBs assumed in stock, main PO(s) {', '.join(m['label'] for m in mains)} start right away")
# #             continue
# #         supply, run = [], 0
# #         for c in childs:
# #             free = max(c["qty"] - taken_by_serial.get(c["po"], 0), 0)
# #             if free:
# #                 supply.append((run, run + free, c["po"]))
# #                 run += free
# #         need = 0
# #         for m in mains:
# #             lo, hi = need, need + m["qty"]
# #             need = hi
# #             depends_on[m["po"]] = [cpo for (a, b, cpo) in supply if a < hi and b > lo]
# #             link_by[m["po"]] = "quantity"
# #             if hi > run:
# #                 warnings.append(f"PO {m['po']}: needs more child PCBs than the loaded child POs provide - rest assumed in stock")

# #     def depth(part: str) -> int:
# #         d = 0
# #         while part in child_of and d < 10:
# #             part, d = child_of[part], d + 1
# #         return d

# #     # ---------------- chains: a child PO and the main PO(s) it feeds belong together ----------------
# #     parent = {p["po"]: p["po"] for p in pos}

# #     def find(x: str) -> str:
# #         while parent[x] != x:
# #             parent[x] = parent[parent[x]]
# #             x = parent[x]
# #         return x

# #     for m_po, c_pos in depends_on.items():
# #         for c_po in c_pos:
# #             if c_po in parent and m_po in parent:
# #                 parent[find(c_po)] = find(m_po)
# #     chain_first: Dict[str, int] = {}
# #     for p in pos:
# #         r = find(p["po"])
# #         chain_first[r] = min(chain_first.get(r, p["idx"]), p["idx"])
# #     chain_key = {p["po"]: chain_first[find(p["po"])] for p in pos}        # chain = its first PO (load order)
# #     chain_no = {k: i + 1 for i, k in enumerate(sorted(set(chain_key.values())))}

# #     # ---------------- schedule (finite capacity, machines shared, down-time skipped) ----------------
# #     default_cap = min(DEFAULT_SHIFTS * DEFAULT_HOURS_PER_SHIFT * 60.0, day_cap)
# #     busy: Dict[str, List[Tuple[datetime, datetime, str]]] = defaultdict(list)   # resource -> runs already booked (first-fit gaps)
# #     usage: Dict[str, Dict[date, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
# #     segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# #     machine_segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# #     runs: Dict[Tuple[str, str], List[datetime]] = {}
# #     run_list: List[Dict[str, Any]] = []
# #     po_ready: Dict[str, datetime] = {}
# #     po_span: Dict[str, List[datetime]] = {}
# #     route: Dict[str, List[str]] = defaultdict(list)
# #     delayed_by_downtime: Dict[str, set] = defaultdict(set)

# #     # placement order: a main PO is placed immediately after the last child PO that feeds it (child, main, child, main ...)
# #     # - NOT "all children first", which pushed every main behind all the child work on shared machines.
# #     by_po = {p["po"]: p for p in pos}
# #     kids = {m: [c for c in cs if c in by_po] for m, cs in depends_on.items()}
# #     feeds: Dict[str, List[str]] = defaultdict(list)
# #     for m_po, cs in kids.items():
# #         for c_po in cs:
# #             feeds[c_po].append(m_po)
# #     order: List[Dict[str, Any]] = []
# #     placed_po: set = set()

# #     def emit(p: Dict[str, Any]) -> None:
# #         if p["po"] in placed_po:
# #             return
# #         placed_po.add(p["po"])
# #         for c_po in kids.get(p["po"], []):
# #             emit(by_po[c_po])
# #         order.append(p)
# #         for m_po in feeds.get(p["po"], []):
# #             if m_po not in placed_po and all(c in placed_po for c in kids[m_po]):
# #                 emit(by_po[m_po])

# #     for p in sorted(pos, key=lambda x: x["idx"]):
# #         emit(p)
# #     handoff: Dict[str, Dict[str, Any]] = {}

# #     open_batches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # station key -> batches already booked (for co-loading)

# #     def book(st: Station, ready: datetime, minutes: float, one_day: bool = False, dry=None):
# #         """First fit on every machine (option) of the station: the earliest start >= ready where the whole run clears the runs
# #         already booked there and the machine's down-time. The machine that FINISHES first wins.
# #         one_day = the run must sit inside one free stretch of one working day (SMT LINE, an oven batch).
# #         dry = bookings of a trial run (estimates) - looked at, but never kept.
# #         Returns (mi, o, start, end, end_day, pieces, fits_in_one_day, blocked_by)."""
# #         best = None
# #         for mi, o in enumerate(st.options):
# #             booked = sorted(iv for r in o["resources"] for iv in busy[r] + (dry.get(r, []) if dry is not None else []))
# #             s0, first_block = ready, None
# #             for _ in range(100000):
# #                 if one_day:
# #                     s, e, eday, segs, same = cal.place_within_day(s0, minutes, st.cap_min, o["blocks"])
# #                 else:
# #                     s, e, eday, segs = cal.consume(s0, minutes, st.cap_min, o["blocks"])
# #                     same = True
# #                 clash = next((iv for iv in booked if iv[0] < e and iv[1] > s), None)
# #                 if clash is None:
# #                     break
# #                 if first_block is None:
# #                     first_block = clash[2]
# #                 s0 = clash[1]
# #             else:
# #                 raise PoGanttError(500, f"No free slot found on {o['name'] or st.name}")
# #             if best is None or e < best[3]:
# #                 best = (mi, o, s, e, eday, segs, same, first_block)
# #         return best

# #     def reserve(o: Dict[str, Any], s: datetime, e: datetime, label: str, dry=None) -> None:
# #         for r in o["resources"]:
# #             (busy if dry is None else dry).setdefault(r, []).append((s, e, label))

# #     def add_segment(p: Dict[str, Any], st: Station, row_id: str, mi: int, o: Dict[str, Any], piece, s: datetime, e: datetime,
# #                     phys: List[Tuple[str, str]], extra: Dict[str, Any]) -> None:
# #         """One bar of the Gantt (one PO, one day, one machine / step) + the same bar on each machine row."""
# #         d, a, b, m = piece
# #         seg = {
# #             "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"], "quantity": p["qty"],
# #             "machine": o["name"], "machine_no": mi, "machines": [mid for mid, _ in phys], "operation": st.name,
# #             "row_id": row_id, "date": d.isoformat(), "start": _iso(a), "end": _iso(b), "minutes": round(m, 1),
# #             "run_start": _iso(s), "run_end": _iso(e),
# #         }
# #         seg.update(extra)
# #         segments[st.key].append(seg)
# #         for mid, nm in phys:
# #             machine_segments[mid].append({**seg, "machine": mid, "step": nm})
# #         usage[st.key][d][p["label"]] += m

# #     def split_steps(segs, step_mins: List[float]):
# #         """Cut a line run [(day, a, b, minutes)] into its steps, one after the other -> [(step_index, (day, a, b, minutes))]."""
# #         out, i, left, n = [], 0, step_mins[0], len(step_mins)
# #         for d, a, b, m in segs:
# #             while m > 1e-9:
# #                 while left <= 1e-9 and i < n - 1:          # a step with no time: go to the next one
# #                     i += 1
# #                     left = step_mins[i]
# #                 use = m if i == n - 1 else min(m, left)    # the last step takes whatever is left (rounding)
# #                 out.append((i, (d, a, a + timedelta(minutes=use), use)))
# #                 a, m, left = a + timedelta(minutes=use), m - use, left - use
# #         return out

# #     def place_batches(p: Dict[str, Any], st: Station, parts, ready: datetime, row_id: str, dry=None):
# #         """Batch process: batch_size PCBs go in together and come out together (one bar per batch).
# #         70 PCBs / batch 30 -> 30 + 30 + 10. Batches of one PO run side by side on free ovens.
# #         A batch of the SAME part that still has room, is not started before this PO is ready and does not finish later
# #         than a new batch would, takes the PCBs instead (co-loading). A trial run (dry) never co-loads.
# #         Returns (start, end, end_day, machine names, blocked_by)."""
# #         size = batch_size_for(p["part"], st.step_ids[0])
# #         per_batch = parts[0][1]                                   # minutes for one batch (time of a batch, not per PCB)
# #         left, mine, blocked_by = p["qty"], [], None
# #         while left > 0:
# #             mins = per_batch + (st.setup if not mine else 0.0)
# #             mi, o, s, e, eday, segs, same, blocked = book(st, ready, mins, one_day=True, dry=dry)
# #             join = None
# #             if dry is None:
# #                 join = min((b for b in open_batches[st.key]
# #                             if b["part"] == p["part"] and b["room"] > 0 and b["start"] >= ready and b["end"] <= e),
# #                            key=lambda b: b["start"], default=None)
# #             if join:
# #                 take = min(left, join["room"])
# #                 join["room"] -= take
# #                 mi, o, s, e, eday, segs = join["mi"], join["o"], join["start"], join["end"], join["eday"], join["segs"]
# #                 together = join["together"]
# #             else:
# #                 take = min(left, size)
# #                 reserve(o, s, e, p["label"], dry)
# #                 together = []
# #                 if dry is None:
# #                     open_batches[st.key].append({"part": p["part"], "room": size - take, "start": s, "end": e, "eday": eday,
# #                                                  "mi": mi, "o": o, "segs": segs, "together": together})
# #                     if blocked_by is None:
# #                         blocked_by = blocked
# #                     if o["blocks"] and any(a < e and b > ready for a, b in o["blocks"]):
# #                         delayed_by_downtime[p["po"]].add(st.name)
# #                     if not same:
# #                         warnings.append(f"PO {p['po']} ({p['label']}): one {st.name} batch needs {mins / 60:.1f} h, more than "
# #                                         f"one working day ({st.cap_min / 60:g} h) - the batch is spread over several days")
# #             together.append({"label": p["label"], "po": p["po"], "qty": take})   # every PO inside this batch (shared list)
# #             left -= take
# #             mine.append((mi, o, s, e, eday, segs, take, mins, together))
# #         if dry is None:
# #             for k, (mi, o, s, e, eday, segs, take, mins, together) in enumerate(mine, start=1):
# #                 info = {"no": k, "count": len(mine), "qty": take, "size": size, "minutes": round(mins, 1),
# #                         "start": _iso(s), "end": _iso(e), "together": together}
# #                 for piece in segs:
# #                     add_segment(p, st, row_id, mi, o, piece, s, e, o["phys"], {"batch": info})
# #         s_all, e_all = min(b[2] for b in mine), max(b[3] for b in mine)
# #         last = max(mine, key=lambda b: b[3])
# #         names = list(dict.fromkeys(b[1]["name"] for b in mine if b[1]["name"]))
# #         return s_all, e_all, last[4], ", ".join(names), blocked_by

# #     def run_po(p: Dict[str, Any], ready: datetime, dry=None) -> Tuple[Optional[datetime], datetime]:
# #         """Place a PO through its operations (p["ops"]), one after the other, from `ready`.
# #         dry = None: book it into the schedule. dry = {}: a trial run on top of the schedule (estimate only, nothing kept).
# #         Returns (start of its first operation, when the PO is ready for the next step / the main PO)."""
# #         ready0, first_start = ready, None
# #         for seq, op in enumerate(p["ops"], start=1):
# #             st = stations[op["key"]]
# #             minutes, parts = op_minutes_and_parts(p, op, st)
# #             row_id = f"{p['role']}:{st.key}"

# #             if st.mode == "BATCH":
# #                 # -------- batch process: one bar per batch --------
# #                 s, e, eday, machine_text, blocked_by = place_batches(p, st, parts, ready, row_id, dry)
# #                 phys_ids = []
# #             else:
# #                 # -------- normal process / SMT LINE: the whole PO in one run --------
# #                 mi, o, s, e, eday, segs, same, blocked_by = book(st, ready, minutes, one_day=(st.kind == "LINE"), dry=dry)
# #                 reserve(o, s, e, p["label"], dry)
# #                 machine_text = o["name"]
# #                 phys_ids = [m for m, _ in o["phys"]]
# #                 if dry is None:
# #                     if o["blocks"] and any(a < e and b > ready for a, b in o["blocks"]):
# #                         delayed_by_downtime[p["po"]].add(st.name)
# #                     if not same:
# #                         warnings.append(f"PO {p['po']} ({p['label']}): {st.name} needs {minutes / 60:.1f} h, more than one "
# #                                         f"working day ({st.cap_min / 60:g} h) - the run is spread over several days")
# #                     if st.kind == "LINE":
# #                         # the line steps run ONE AFTER THE OTHER (step 1 for the whole PO, then step 2 ...), all inside the day
# #                         step_mins = [parts[i][0] + (st.setup if i == 0 else 0.0) for i in range(len(parts))]
# #                         pieces = split_steps(segs, step_mins)
# #                         for i, name in enumerate(st.steps):
# #                             mine = [pc for k, pc in pieces if k == i]
# #                             if not mine:
# #                                 continue
# #                             step_phys = [(mid, nm) for mid, nm in o["phys"] if nm == name]
# #                             extra = {"step": name, "step_no": i + 1, "step_count": len(st.steps),
# #                                      "step_start": _iso(mine[0][1]), "step_end": _iso(mine[-1][2]),
# #                                      "step_minutes": round(step_mins[i], 1)}
# #                             if step_phys:
# #                                 extra["machine"] = step_phys[0][0]
# #                             for piece in mine:
# #                                 add_segment(p, st, row_id, mi, o, piece, s, e, step_phys, extra)
# #                     else:
# #                         for piece in segs:
# #                             add_segment(p, st, row_id, mi, o, piece, s, e, o["phys"], {})

# #             first_start = s if first_start is None else first_start
# #             if dry is None:
# #                 if seq == 1 and any(c in po_ready for c in depends_on.get(p["po"], [])):   # main PO: how soon after its child?
# #                     wait_h = max((s - ready0).total_seconds() / 3600.0, 0.0)
# #                     handoff[p["po"]] = {"child_ready": _iso(ready0), "main_start": _iso(s), "wait_hours": round(wait_h, 1),
# #                                         "station": st.name, "machine": machine_text, "blocked_by": blocked_by}
# #                     if wait_h > HANDOFF_WARN_HOURS:
# #                         warnings.append(f"PO {p['po']} ({p['label']}) starts {wait_h / 24:.1f} days after its child PO "
# #                                         f"finished: {st.name} is busy" + (f" with PO {blocked_by}" if blocked_by else ""))
# #                 span = runs.setdefault((st.key, p["label"]), [s, e])
# #                 span[0], span[1] = min(span[0], s), max(span[1], e)
# #                 ps = po_span.setdefault(p["po"], [s, e])
# #                 ps[0], ps[1] = min(ps[0], s), max(ps[1], e)
# #                 if row_id not in route[p["po"]]:
# #                     route[p["po"]].append(row_id)
# #                 run_list.append({"seq": seq, "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"],
# #                                  "quantity": p["qty"], "row_id": row_id, "station": st.name, "kind": st.kind,
# #                                  "flow_step_ids": st.step_ids, "machine": machine_text, "machines": phys_ids,
# #                                  "start": _iso(s), "end": _iso(e), "minutes": round(minutes, 1)})

# #             ready = e                                            # when the PO may enter the next process
# #             if st.next_day_release:
# #                 ready = datetime.combine(cal.first_working_day(eday + timedelta(days=1)), time.min) + timedelta(hours=shift_start)
# #             if st.cooldown > 0:
# #                 if st.cd_working_only:
# #                     ready = cal.consume(ready, st.cooldown, default_cap)[1]
# #                 else:
# #                     ready = ready + timedelta(minutes=st.cooldown)
# #         return first_start, ready

# #     def outside_child(l: Dict[str, Any], qty: int, from_step: bool) -> Dict[str, Any]:
# #         """A child PO that is not in this schedule, as a PO for a trial run: its whole flow, or (in process) the rest of
# #         its flow from the earliest step its PCBs are at."""
# #         c = cands[l["child_po"]]
# #         ops = ops_for(c["part"])
# #         if from_step and l["steps"]:
# #             at = [i for i, op in enumerate(ops) if any(m.flow_step_id in l["steps"] for m in op["steps"])]
# #             ops = ops[min(at):] if at else ops
# #         return {"po": c["po"], "label": c["po"], "part": c["part"], "qty": qty, "role": "CHILD", "ops": ops}

# #     child_notes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # main po -> what the child outside the plan means
# #     forced: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []          # (main PO, child link) scheduled without waiting

# #     for p in order:
# #         waits = [po_ready[c] for c in depends_on.get(p["po"], []) if c in po_ready]
# #         for l in outside_links.get(p["po"], []):
# #             note = {"child_po": l["child_po"], "child_part": l["child_part"], "pcbs": l["pcbs"], "done": l["done"],
# #                     "in_progress": l["in_progress"], "not_assigned": l["not_assigned"], "in_plan": False}
# #             if l["in_progress"]:
# #                 # child PCBs are on the floor: the main waits for the rest of the child flow (estimate, nothing booked)
# #                 trial = outside_child(l, l["in_progress"], from_step=True)
# #                 if trial["ops"]:
# #                     _, est = run_po(trial, max(now, start_dt), dry={})
# #                     waits.append(est)
# #                     note["child_ready_estimate"] = _iso(est)
# #                     warnings.append(f"PO {p['po']} ({p['label']}): {l['in_progress']} child PCB(s) of PO {l['child_po']} are "
# #                                     f"still in process - estimated done {est:%d-%m-%Y %H:%M}, the main PO waits for that")
# #             if l["not_assigned"]:
# #                 note["forced"] = True
# #                 forced.append((p, l))
# #             child_notes[p["po"]].append(note)
# #         _, po_ready[p["po"]] = run_po(p, max([start_dt] + waits))

# #     # child not assigned -> main was scheduled without waiting. What if the child is assigned on the first working day?
# #     for p, l in forced:
# #         trial = outside_child(l, l["not_assigned"], from_step=False)
# #         note = next(n for n in child_notes[p["po"]] if n["child_po"] == l["child_po"])
# #         main_start = po_span[p["po"]][0]
# #         if not trial["ops"]:
# #             warnings.append(f"PO {p['po']} ({p['label']}): child PO {l['child_po']} is not assigned yet and its part "
# #                             f"{l['child_part']} has no flow - main PO scheduled without waiting for it (forced)")
# #             continue
# #         c_start, c_end = run_po(trial, start_dt, dry={})
# #         note.update({"assign_on": _iso(c_start), "child_done": _iso(c_end), "main_can_start": _iso(c_end),
# #                      "main_planned_start": _iso(main_start)})
# #         warnings.append(
# #             f"PO {p['po']} ({p['label']}): child PO {l['child_po']} ({l['not_assigned']} PCB(s)) is not assigned yet - the "
# #             f"main PO is scheduled without waiting for it (forced, from {main_start:%d-%m-%Y %H:%M}). If child PO "
# #             f"{l['child_po']} is assigned on {c_start:%d-%m-%Y}, it is done by {c_end:%d-%m-%Y %H:%M} and PO {p['po']} "
# #             f"can start from {c_end:%d-%m-%Y %H:%M}"
# #             + (" - until then its PCBs cannot be assigned (the child must be complete)." if c_end > main_start else "."))

# #     for part, names in missing_time.items():
# #         uniq = list(dict.fromkeys(names))
# #         warnings.append(f"Part {part}: no process time for {len(uniq)} step(s) "
# #                         f"[{', '.join(uniq[:6])}{'...' if len(uniq) > 6 else ''}] - {FALLBACK_MINUTES:g} min used")
# #     if delayed_by_downtime:
# #         warnings.append(f"{len(delayed_by_downtime)} PO(s) were moved around machine breakdowns / maintenance / "
# #                         f"consumable shortages")

# #     # ---------------- days ----------------
# #     used_days = [d for per_day in usage.values() for d in per_day]
# #     last_day = max(used_days + [start_day])
# #     days, day_no, working_nos = [], {}, 0
# #     d = start_day
# #     while d <= last_day:
# #         if cal.factor(d) > 0:
# #             working_nos += 1
# #             day_no[d] = working_nos
# #             days.append({"working_day_no": working_nos, "date": d.isoformat(), "weekday": d.strftime("%a"),
# #                          "is_holiday": False, "off_reason": None})
# #         elif show_holidays:
# #             days.append({"working_day_no": None, "date": d.isoformat(), "weekday": d.strftime("%a"),
# #                          "is_holiday": True, "off_reason": cal.off_reason(d)})
# #         d += timedelta(days=1)

# #     # ---------------- rows: CHILD section first, then MAIN; each in flow order ----------------
# #     def part_sort(pn: str):
# #         prod = products.get(pn)
# #         return (_key(prod.product_type_name) if prod else "", pn)

# #     part_order = sorted({p["part"] for p in pos}, key=part_sort)
# #     section_rows: Dict[str, List[str]] = {r: [] for r in ROLES}
# #     parts_by_row: Dict[Tuple[str, str], List[str]] = defaultdict(list)
# #     for part in part_order:
# #         role = role_of(part)
# #         lst, at = section_rows[role], -1
# #         for op in ops_for(part):                              # merge the flows of several parts in one section
# #             if op["key"] in lst:
# #                 at = lst.index(op["key"])
# #             else:
# #                 at += 1
# #                 lst.insert(at, op["key"])
# #             if part not in parts_by_row[(role, op["key"])]:
# #                 parts_by_row[(role, op["key"])].append(part)
# #     roles_of_station: Dict[str, set] = defaultdict(set)
# #     for role, keys in section_rows.items():
# #         for k in keys:
# #             roles_of_station[k].add(role)

# #     def order_labels(labels) -> List[str]:
# #         return sorted(labels, key=lambda x: label_idx.get(x, 0))

# #     def cells_for(key: str, role: str) -> List[Dict[str, Any]]:
# #         s, out = stations[key], []
# #         for dd, no in day_no.items():
# #             u = usage.get(key, {}).get(dd)
# #             if not u:
# #                 continue
# #             labels = [lb for lb in u if label_role.get(lb) == role]
# #             if not labels:
# #                 continue
# #             out.append({"working_day_no": no, "date": dd.isoformat(), "pos": order_labels(labels),
# #                         "color": ORANGE if len(labels) >= 2 else BLUE,
# #                         "minutes_used": round(sum(u[lb] for lb in labels), 1),
# #                         "station_minutes_used": round(sum(u.values()), 1),
# #                         "capacity_minutes": round(len(s.options) * s.cap_min * cal.factor(dd), 1)})
# #         return out

# #     def runs_for(key: str, role: str) -> List[Dict[str, str]]:
# #         out = [(lb, v) for (k, lb), v in runs.items() if k == key and label_role.get(lb) == role]
# #         return [{"label": lb, "start": _iso(v[0]), "end": _iso(v[1])}
# #                 for lb, v in sorted(out, key=lambda kv: (kv[1][0], label_idx.get(kv[0], 0)))]

# #     def station_downtime(s: Station) -> List[Dict[str, Any]]:
# #         step_of = {m: nm for m, nm in s.real_machines}                 # SMT LINE: which step the machine belongs to
# #         evs = [_dt_json({**e, "machine_name": machine_info.get(mid, {}).get("name", mid),
# #                          "step": step_of[mid] if s.kind == "LINE" else None})
# #                for mid in dict.fromkeys(m for m, _ in s.real_machines) for e in downtime.get(mid, [])]
# #         sname = dict(zip(s.step_ids, s.steps)) if s.kind == "LINE" else {}
# #         evs += [_dt_json({**e, "process": s.name, "step": sname.get(e["stage_id"])}) for e in s.material]
# #         return sorted(evs, key=lambda e: e["start"])

# #     rows: List[Dict[str, Any]] = []
# #     for role in ROLES:
# #         for key in section_rows[role]:
# #             s = stations[key]
# #             parts = parts_by_row[(role, key)]
# #             real = list(dict.fromkeys(m for m, _ in s.real_machines))
# #             rows.append({
# #                 "row_id": f"{role}:{key}", "station_id": key, "name": s.name, "kind": s.kind, "section": role,
# #                 "role": role, "part_number": parts[0], "part_numbers": parts,
# #                 "flow_step_ids": s.step_ids, "steps": s.steps,
# #                 "shifts": s.shifts, "mins_per_shift": int(s.hps * 60), "machines": len(s.options),
# #                 "machine_names": s.machines, "has_machine": bool(real), "real_machines": real,
# #                 "real_machine_names": [machine_info[m]["name"] for m in real],
# #                 "operators_per_shift": s.operators, "process_mode": s.mode, "is_batch": s.mode == "BATCH",
# #                 "day_end_hour": round(shift_start + s.cap_min / 60.0, 2),
# #                 "shared_with": [r for r in ROLES if r != role and r in roles_of_station[key]],
# #                 "cells": cells_for(key, role), "po_runs": runs_for(key, role),
# #                 "segments": [sg for sg in segments.get(key, []) if sg["role"] == role],
# #                 "downtime": station_downtime(s),
# #             })

# #     # ---------------- machine rows (PO on Machines), grouped by process in flow order ----------------
# #     machine_rows: List[Dict[str, Any]] = []
# #     placed: Dict[str, Dict[str, Any]] = {}
# #     for row in rows:
# #         s = stations[row["station_id"]]
# #         for mid, step in s.real_machines:
# #             if mid in placed:
# #                 if s.name not in placed[mid]["processes"]:
# #                     placed[mid]["processes"].append(s.name)
# #                 if row["role"] not in placed[mid]["roles"]:
# #                     placed[mid]["roles"].append(row["role"])
# #                 continue
# #             info = machine_info.get(mid, {"name": mid})
# #             segs = sorted(machine_segments.get(mid, []), key=lambda x: x["start"])
# #             mr = {
# #                 "row_id": f"M:{mid}", "machine_id": mid, "name": info.get("name") or mid, "eqpt_no": info.get("eqpt_no"),
# #                 "make": info.get("make"), "model": info.get("model"), "workcenter": info.get("workcenter"),
# #                 "group": s.key, "group_name": s.name, "group_kind": s.kind, "step": step if s.kind == "LINE" else None,
# #                 "processes": [s.name], "roles": [row["role"]], "shifts": s.shifts,
# #                 "day_end_hour": round(shift_start + s.cap_min / 60.0, 2), "is_batch": s.mode == "BATCH",
# #                 "segments": segs, "downtime": [_dt_json(e) for e in downtime.get(mid, [])],
# #                 # a batch shared by 2 POs is 2 bars at the same time - count the oven time once
# #                 "busy_minutes": round(sum({(x["start"], x["end"]): x["minutes"] for x in segs}.values()), 1),
# #             }
# #             placed[mid] = mr
# #             machine_rows.append(mr)
# #     manual_processes = [r["name"] for r in rows if not r["has_machine"]]
# #     if manual_processes:
# #         warnings.append("No machine mapped in equipment_details for: " + ", ".join(
# #             dict.fromkeys(f"{r['name']} (step {', '.join(str(x) for x in r['flow_step_ids'])})" for r in rows if not r["has_machine"])))

# #     for s in stations.values():
# #         for e in s.material:
# #             warnings.append(f"Consumable not available - {s.name} does not run from {e['start']:%d-%m-%Y %H:%M} to "
# #                             f"{e['end']:%d-%m-%Y %H:%M}: {e['note']}")

# #     # most important first: forced main POs, consumable shortages, children still in process
# #     first = ("is not assigned yet", "Consumable not available", "still in process", "Breakdown repair waits")
# #     warnings.sort(key=lambda w: next((i for i, k in enumerate(first) if k in w), len(first)))

# #     all_down = [_dt_json({**e, "machine_name": machine_info.get(mid, {}).get("name", mid)})
# #                 for mid in placed for e in downtime.get(mid, [])]

# #     day_end = shift_start + max((s.cap_min for s in stations.values()), default=default_cap) / 60.0
# #     line_text = "; ".join(f"{g} = {', '.join(n)}" for g, n in LINE_GROUPS.items())
# #     assumptions = [
# #         "Child / main comes from product_type_master (sub product type); a main part is fed by the child part of the same product type.",
# #         "Each part follows its flow from product_workflow_mapping (step sequence). Linked child / main POs are scheduled as one chain; "
# #         "a main PO starts after the child PO(s) that feed it are finished.",
# #         "Child -> main link by SERIAL number first (PcbData.serialNo, the same check as PCB assignment): the main PCB needs the "
# #         "child PCB with the same serial. Main POs without a serial match use first come, first served by quantity.",
# #         "Child PO not in this schedule: PCBs done -> no wait; in process (pcb_assignment.current_step_id) -> the main waits for "
# #         "the estimated end of the rest of the child flow; NOT assigned -> the main is scheduled without waiting (forced) and "
# #         "the warning says on which day the child must be assigned and from when the main can really start.",
# #         "Unit of work is the whole PO quantity; a PO moves through its processes as a block.",
# #         f"Line processes run inside one working day ({line_text}). The steps run one after the other "
# #         "(step 1 for the whole PO, then step 2 ...); line time = sum of the step times.",
# #         "Machines come from equipment_details; the same machine serving several processes is shared between them.",
# #         "Machine breakdowns (machine_breakdown_logs: until ready date, else + downtime hours, else open = "
# #         f"{OPEN_BREAKDOWN_HOURS:g} h from now) and pending preventive maintenance (maintenance_schedules: the whole day) "
# #         "block the machine.",
# #         "Spares (inventorty_spares): an open breakdown whose machine has a spare out of stock lasts at least the spare's "
# #         f"procurement lead time (default {DEFAULT_SPARE_LEAD_DAYS} d). A running machine is not blocked by a missing spare (warning only).",
# #         "Consumables (consumables, by process): out of stock or past shelf life -> the process (all its machines, or the "
# #         f"process without machine) is blocked for {CONSUMABLE_RESTOCK_DAYS} days; stock that expires blocks it from the day "
# #         "after expiry. Stock is checked as available yes / no (the table has no use per PCB). Low stock = warning.",
# #         f"Shifts per process come from stage_capacity (default {DEFAULT_SHIFTS} x {DEFAULT_HOURS_PER_SHIFT:g} h); "
# #         f"the working day runs {_hm(shift_start)} - {_hm(DAY_END_HOUR)} at most.",
# #         "Off days: Sundays, 1st and 3rd Saturdays, public holidays and calendar 'Holiday' exceptions; "
# #         "'Working' reopens a day, 'Half-Day' halves it.",
# #         f"Time per unit = {'actual' if time_source == 'actual' else 'SAP'} time (fallback to the other, routing, stage_capacity) "
# #         "+ machine hours of part_process_time.",
# #         "Batch processes (process_type.process_type_batch): batch size PCBs go in together and come out together - "
# #         "70 PCBs / batch 30 = 3 batches (30, 30, 10), each one bar, run on free machines side by side. "
# #         "A batch of the same part with room left takes PCBs of the next PO when that does not delay it. "
# #         "Batch size = part_process_time.batch_size, else stage_schedule_config.batch_size, else 30.",
# #         f"Plant filter: only POs, machines and process times of plant {plant or '(all)'}.",
# #         "Operators per shift is informational; it does not limit the schedule.",
# #     ]
# #     return {
# #         "meta": {
# #             "plant": plant, "number_of_pos": len(pos), "start_date": start_day.isoformat(), "finish_date": last_day.isoformat(),
# #             "working_days": working_nos, "time_source": time_source, "label_mode": label_mode,
# #             "generated_at": _iso(now),
# #             "params": {"plant": plant, "production_order": [p["po"] for p in pos] if explicit else None,
# #                        "start_date": start_date.isoformat() if start_date else None, "time_source": time_source,
# #                        "label_mode": label_mode, "shift_start": shift_start},
# #             "day_window": {"start_hour": shift_start, "end_hour": round(day_end, 2)},
# #             "line_groups": {g: list(n) for g, n in LINE_GROUPS.items()},
# #             "machines_down": len({e["machine"] for e in all_down}),
# #             "downtime_events": len(all_down),
# #             "manual_processes": manual_processes,
# #             "material_shortages": [_dt_json({**e, "process": s.name}) for s in stations.values() for e in s.material],
# #             "pos": [{"label": p["label"], "production_order": p["po"], "part_number": p["part"], "role": p["role"],
# #                      "quantity": p["qty"], "depends_on": depends_on.get(p["po"], []), "handoff": handoff.get(p["po"]), "route": route[p["po"]],
# #                      "chain": chain_no[chain_key[p["po"]]],
# #                      "link_by": link_by.get(p["po"]),                         # serial | quantity | None (not a main PO)
# #                      "child_outside": child_notes.get(p["po"], []),           # child POs not in this schedule
# #                      "forced": any(n.get("forced") for n in child_notes.get(p["po"], [])),
# #                      "moved_by_downtime": sorted(delayed_by_downtime.get(p["po"], [])),
# #                      "start": _iso(po_span[p["po"]][0]), "end": _iso(po_span[p["po"]][1])} for p in pos],
# #         },
# #         "days": days, "stations": rows, "machines": machine_rows, "downtime": all_down, "runs": run_list,
# #         "warnings": warnings, "assumptions": assumptions,
# #     }


# # # --------------------------------------------------------------------------------------
# # # Saved plans
# # # --------------------------------------------------------------------------------------
# # class PlanSave(BaseModel):
# #     name: Optional[str] = None
# #     remarks: Optional[str] = None
# #     set_baseline: bool = True
# #     created_by: Optional[str] = None
# #     plant: Optional[str] = None
# #     production_order: Optional[List[str]] = None
# #     start_date: Optional[date] = None
# #     time_source: str = "actual"
# #     label_mode: str = "po"
# #     shift_start: float = DEFAULT_SHIFT_START


# # def _plan_header(p: SchedulePlan) -> Dict[str, Any]:
# #     return {"id": p.id, "name": p.name, "plant": p.plant_code, "is_baseline": bool(p.is_baseline), "status": p.status,
# #             "time_source": p.time_source, "label_mode": p.label_mode,
# #             "start_date": p.start_date.isoformat() if p.start_date else None,
# #             "finish_date": p.finish_date.isoformat() if p.finish_date else None,
# #             "number_of_pos": p.number_of_pos, "working_days": p.working_days, "remarks": p.remarks,
# #             "created_by": p.created_by, "created_at": _iso(p.created_at), "params": p.params}


# # def save_plan(db: Session, body: PlanSave) -> Dict[str, Any]:
# #     """Build the schedule again with the same inputs (so what is stored is consistent) and store it."""
# #     ensure_plan_tables(db.get_bind())
# #     result = build_po_gantt(db, body.production_order, body.plant, body.start_date, body.time_source,
# #                             body.label_mode, True, body.shift_start)
# #     meta = result["meta"]
# #     now = datetime.now()
# #     if body.set_baseline:
# #         q = db.query(SchedulePlan).filter(SchedulePlan.is_baseline.is_(True))
# #         q = q.filter(SchedulePlan.plant_code == body.plant) if body.plant else q.filter(SchedulePlan.plant_code.is_(None))
# #         q.update({SchedulePlan.is_baseline: False}, synchronize_session=False)
# #     plan = SchedulePlan(
# #         name=(body.name or "").strip() or f"Plan {body.plant or 'all'} · {now:%d %b %Y %H:%M}",
# #         plant_code=body.plant, is_baseline=bool(body.set_baseline), status="SAVED",
# #         time_source=body.time_source, label_mode=body.label_mode,
# #         start_date=date.fromisoformat(meta["start_date"]), finish_date=date.fromisoformat(meta["finish_date"]),
# #         number_of_pos=meta["number_of_pos"], working_days=meta["working_days"], params=meta["params"],
# #         snapshot=result, remarks=body.remarks, created_by=body.created_by, created_at=now,
# #     )
# #     db.add(plan)
# #     db.flush()
# #     db.add_all([SchedulePlanItem(
# #         plan_id=plan.id, seq=r["seq"], production_order=r["po"], part_number=r["part"], label=r["label"],
# #         role=r["role"], quantity=r["quantity"], row_id=r["row_id"], station_name=r["station"], station_kind=r["kind"],
# #         flow_step_ids=r["flow_step_ids"], machine=r["machine"], machines=r["machines"],
# #         planned_start=datetime.strptime(r["start"], ISO), planned_end=datetime.strptime(r["end"], ISO),
# #         run_minutes=r["minutes"]) for r in result["runs"]])
# #     db.commit()
# #     return {"plan": _plan_header(plan), "items": len(result["runs"])}


# # def list_plans(db: Session, plant: Optional[str]) -> Dict[str, Any]:
# #     ensure_plan_tables(db.get_bind())
# #     q = db.query(SchedulePlan.id, SchedulePlan.name, SchedulePlan.plant_code, SchedulePlan.is_baseline,
# #                  SchedulePlan.status, SchedulePlan.start_date, SchedulePlan.finish_date, SchedulePlan.number_of_pos,
# #                  SchedulePlan.working_days, SchedulePlan.created_by, SchedulePlan.created_at, SchedulePlan.remarks,
# #                  SchedulePlan.time_source)
# #     if plant:
# #         q = q.filter(SchedulePlan.plant_code == plant)
# #     out = []
# #     for r in q.order_by(SchedulePlan.created_at.desc(), SchedulePlan.id.desc()).all():
# #         out.append({"id": r.id, "name": r.name, "plant": r.plant_code, "is_baseline": bool(r.is_baseline),
# #                     "status": r.status, "start_date": r.start_date.isoformat() if r.start_date else None,
# #                     "finish_date": r.finish_date.isoformat() if r.finish_date else None,
# #                     "number_of_pos": r.number_of_pos, "working_days": r.working_days, "created_by": r.created_by,
# #                     "created_at": _iso(r.created_at), "remarks": r.remarks, "time_source": r.time_source})
# #     return {"plans": out}


# # def _get_plan(db: Session, plan_id: int) -> SchedulePlan:
# #     ensure_plan_tables(db.get_bind())
# #     p = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
# #     if not p:
# #         raise PoGanttError(404, f"Saved plan {plan_id} not found")
# #     return p


# # def set_baseline(db: Session, plan_id: int) -> Dict[str, Any]:
# #     p = _get_plan(db, plan_id)
# #     q = db.query(SchedulePlan).filter(SchedulePlan.is_baseline.is_(True), SchedulePlan.id != p.id)
# #     q = q.filter(SchedulePlan.plant_code == p.plant_code) if p.plant_code else q.filter(SchedulePlan.plant_code.is_(None))
# #     q.update({SchedulePlan.is_baseline: False}, synchronize_session=False)
# #     p.is_baseline = True
# #     db.commit()
# #     return {"plan": _plan_header(p)}


# # def delete_plan(db: Session, plan_id: int) -> Dict[str, Any]:
# #     p = _get_plan(db, plan_id)
# #     db.query(SchedulePlanItem).filter(SchedulePlanItem.plan_id == p.id).delete(synchronize_session=False)
# #     db.delete(p)
# #     db.commit()
# #     return {"deleted": plan_id}


# # # --------------------------------------------------------------------------------------
# # # Actual (what the operators did) and Planned vs Actual
# # # --------------------------------------------------------------------------------------
# # _MACHINE_KEYS = ("machine_id", "machineId", "machine", "machine_name", "equipment", "eqpt_no", "equipment_id")


# # def load_actuals(db: Session, po_numbers: List[str]):
# #     """Returns (pcb_qty {po: total pieces}, agg {(po, flow_step_id): {...}}) from operator_log, then pcb_process_log
# #     (via pcb_assignment) for PCB x step pairs operator_log does not have."""
# #     pos = sorted({_norm(p) for p in po_numbers if p})
# #     pcbs: Dict[str, Tuple[str, int]] = {}
# #     serial_to_pcb: Dict[str, str] = {}
# #     pcb_qty: Dict[str, int] = defaultdict(int)
# #     norm_col = func.ltrim(func.trim(PcbData.productionOrder), "0")
# #     for chunk in _chunks(pos):
# #         for pcb, serial, po, qty in db.query(PcbData.PCBserialNoPartNumber, PcbData.serialNo, PcbData.productionOrder,
# #                                              PcbData.quantity).filter(norm_col.in_(chunk)).all():
# #             q = qty if qty and qty > 0 else 1
# #             n = _norm(po)
# #             pcbs[pcb] = (n, q)
# #             pcb_qty[n] += q
# #             if serial:
# #                 serial_to_pcb.setdefault(serial, pcb)

# #     events: Dict[Tuple[str, int], Dict[str, Any]] = {}
# #     keys = list(pcbs)
# #     for chunk in _chunks(keys):
# #         for r in db.query(OperatorLog).filter(OperatorLog.PCBserialNoPartNumber.in_(chunk)).all():
# #             st, en = _parse_dt(r.start_time), _parse_dt(r.end_time)
# #             if not en and (r.Task_Status or "").strip().lower() in DONE_STATUSES:
# #                 en = st
# #             if not st and not en:
# #                 continue
# #             machine = None
# #             if isinstance(r.log_Data, dict):
# #                 machine = next((str(r.log_Data[k]) for k in _MACHINE_KEYS if r.log_Data.get(k)), None)
# #             events[(r.PCBserialNoPartNumber, r.current_step_id)] = {
# #                 "start": st or en, "end": en, "operator": r.operator_name or r.operator_staff_no, "machine": machine}

# #     assign: Dict[int, str] = {}
# #     lookup = keys + [s for s in serial_to_pcb if s not in pcbs]
# #     for chunk in _chunks(lookup):
# #         for aid, pid in db.query(PCBAssignment.assignment_id, PCBAssignment.assigned_pcb_id).filter(
# #                 PCBAssignment.assigned_pcb_id.in_(chunk)).all():
# #             pcb = pid if pid in pcbs else serial_to_pcb.get(pid)
# #             if pcb:
# #                 assign[aid] = pcb
# #     for chunk in _chunks(list(assign)):
# #         for r in db.query(PCBProcessLog).filter(PCBProcessLog.assignment_id.in_(chunk)).all():
# #             k = (assign[r.assignment_id], r.flow_step_id)
# #             if k in events:
# #                 continue
# #             st, en = _parse_dt(r.start_time), _parse_dt(r.end_time)
# #             if not en and (r.process_status or "").strip().lower() in DONE_STATUSES:
# #                 en = st
# #             if not st and not en:
# #                 continue
# #             events[k] = {"start": st or en, "end": en, "operator": r.assigned_operator_staff_no, "machine": None}

# #     agg: Dict[Tuple[str, int], Dict[str, Any]] = {}
# #     for (pcb, sid), ev in events.items():
# #         po, q = pcbs[pcb]
# #         a = agg.setdefault((po, sid), {"start": None, "end": None, "done": 0, "wip": 0,
# #                                        "operators": set(), "machines": set()})
# #         a["start"] = min(a["start"], ev["start"]) if a["start"] else ev["start"]
# #         if ev["end"]:
# #             a["done"] += q
# #             a["end"] = max(a["end"], ev["end"]) if a["end"] else ev["end"]
# #         else:
# #             a["wip"] += q
# #         if ev["operator"]:
# #             a["operators"].add(ev["operator"])
# #         if ev["machine"]:
# #             a["machines"].add(ev["machine"])
# #     return pcb_qty, agg


# # def _status(ps, pe, a_start, a_end, complete, now) -> Tuple[str, Optional[float]]:
# #     tol = timedelta(minutes=LATE_TOLERANCE_MIN)
# #     mins = lambda d: round(d.total_seconds() / 60.0, 1)
# #     if complete:
# #         return ("DONE_LATE" if a_end > pe + tol else "DONE_ON_TIME"), mins(a_end - pe)
# #     if a_start:
# #         return ("RUNNING_LATE" if now > pe + tol else "RUNNING"), (mins(now - pe) if now > pe else None)
# #     if now > ps + tol:
# #         return "START_OVERDUE", mins(now - ps)
# #     return "UPCOMING", None


# # def compare_plan(db: Session, plan_id: int, now: Optional[datetime] = None) -> Dict[str, Any]:
# #     plan = _get_plan(db, plan_id)
# #     snap = plan.snapshot or {}
# #     now = now or datetime.now()
# #     runs = snap.get("runs") or []
# #     if not runs:                                             # a plan saved without runs -> rebuild from items
# #         runs = [{"seq": i.seq, "label": i.label, "po": i.production_order, "part": i.part_number, "role": i.role,
# #                  "quantity": i.quantity, "row_id": i.row_id, "station": i.station_name, "kind": i.station_kind,
# #                  "flow_step_ids": i.flow_step_ids or [], "machine": i.machine, "machines": i.machines or [],
# #                  "start": _iso(i.planned_start), "end": _iso(i.planned_end), "minutes": i.run_minutes}
# #                 for i in db.query(SchedulePlanItem).filter(SchedulePlanItem.plan_id == plan.id).all()]
# #     pcb_qty, agg = load_actuals(db, [r["po"] for r in runs])

# #     by_row: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# #     by_po: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# #     for r in runs:
# #         ps, pe = datetime.strptime(r["start"], ISO), datetime.strptime(r["end"], ISO)
# #         total = pcb_qty.get(r["po"]) or r["quantity"] or 1
# #         acts = [agg.get((r["po"], sid)) for sid in r["flow_step_ids"]]
# #         got = [a for a in acts if a]
# #         a_start = min(a["start"] for a in got) if got else None
# #         done_qty = min((a["done"] if a else 0) for a in acts) if acts else 0
# #         complete = bool(acts) and all(a and a["done"] >= total for a in acts)
# #         a_end = max(a["end"] for a in got if a["end"]) if complete else None
# #         status, var = _status(ps, pe, a_start, a_end, complete, now)
# #         item = {
# #             "label": r["label"], "po": r["po"], "part": r["part"], "role": r["role"], "quantity": r["quantity"],
# #             "seq": r["seq"], "row_id": r["row_id"], "station": r["station"], "machine": r["machine"],
# #             "planned_start": r["start"], "planned_end": r["end"], "planned_minutes": r["minutes"],
# #             "actual_start": _iso(a_start), "actual_end": _iso(a_end), "actual_until": _iso(a_end or (now if a_start else None)),
# #             "done_qty": done_qty, "total_qty": total,
# #             "wip_qty": max((a["wip"] for a in got), default=0),
# #             "start_variance_min": round((a_start - ps).total_seconds() / 60.0, 1) if a_start else None,
# #             "variance_min": var, "status": status,
# #             "operators": sorted({o for a in got for o in a["operators"]}),
# #             "actual_machines": sorted({m for a in got for m in a["machines"]}),
# #         }
# #         by_row[r["row_id"]].append(item)
# #         by_po[r["po"]].append(item)

# #     rows = []
# #     for st in snap.get("stations", []):
# #         items = sorted(by_row.get(st["row_id"], []), key=lambda x: x["planned_start"])
# #         row = {k: st.get(k) for k in ("row_id", "station_id", "name", "kind", "section", "role", "steps",
# #                                       "part_numbers", "shifts", "has_machine", "real_machine_names",
# #                                       "machines", "flow_step_ids")}
# #         row["items"] = items
# #         rows.append(row)

# #     po_meta = {p["production_order"]: p for p in snap.get("meta", {}).get("pos", [])}
# #     pos_out, kpi = [], defaultdict(int)
# #     for po, items in by_po.items():
# #         items.sort(key=lambda x: x["seq"])
# #         ps = min(i["planned_start"] for i in items)
# #         pe = max(i["planned_end"] for i in items)
# #         starts = [i["actual_start"] for i in items if i["actual_start"]]
# #         complete = all(i["status"].startswith("DONE") for i in items)
# #         a_end = max(i["actual_end"] for i in items) if complete else None
# #         status, var = _status(datetime.strptime(ps, ISO), datetime.strptime(pe, ISO),
# #                               datetime.strptime(min(starts), ISO) if starts else None,
# #                               datetime.strptime(a_end, ISO) if a_end else None, complete, now)
# #         current = next((i for i in items if not i["status"].startswith("DONE")), None)
# #         kpi[status] += 1
# #         m = po_meta.get(po, {})
# #         pos_out.append({
# #             "po": po, "label": items[0]["label"], "part": items[0]["part"], "role": items[0]["role"],
# #             "quantity": items[0]["quantity"], "planned_start": ps, "planned_end": pe,
# #             "actual_start": min(starts) if starts else None, "actual_end": a_end, "status": status, "variance_min": var,
# #             "current_process": current["station"] if current else None,
# #             "current_status": current["status"] if current else None,
# #             "processes_done": sum(1 for i in items if i["status"].startswith("DONE")), "processes": len(items),
# #             "late_processes": sum(1 for i in items if i["status"] in ("DONE_LATE", "RUNNING_LATE", "START_OVERDUE")),
# #             "depends_on": m.get("depends_on", []), "handoff": m.get("handoff"),
# #         })
# #     order = {p["production_order"]: i for i, p in enumerate(snap.get("meta", {}).get("pos", []))}
# #     pos_out.sort(key=lambda p: order.get(p["po"], 10 ** 6))
# #     process_kpi = defaultdict(int)
# #     for items in by_row.values():
# #         for i in items:
# #             process_kpi[i["status"]] += 1

# #     actual_ends = [i["actual_until"] for items in by_row.values() for i in items if i["actual_until"]]
# #     return {
# #         "plan": _plan_header(plan), "now": _iso(now),
# #         "days": snap.get("days", []),
# #         "meta": dict({k: snap.get("meta", {}).get(k) for k in ("day_window", "line_groups", "pos", "start_date",
# #                                                                "finish_date", "working_days", "number_of_pos")},
# #                      actual_last=max(actual_ends) if actual_ends else None),
# #         "rows": rows, "pos": pos_out,
# #         "kpis": {"pos": dict(kpi), "processes": dict(process_kpi), "total_pos": len(pos_out),
# #                  "total_runs": sum(len(v) for v in by_row.values())},
# #     }


# # # --------------------------------------------------------------------------------------
# # # Excel export
# # # --------------------------------------------------------------------------------------
# # def build_po_gantt_xlsx(result: Dict[str, Any]) -> bytes:
# #     from openpyxl import Workbook
# #     from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
# #     from openpyxl.utils import get_column_letter

# #     font = lambda **kw: Font(name="Arial", size=10, **kw)
# #     thin = Side(style="thin", color="BFBFBF")
# #     border = Border(left=thin, right=thin, top=thin, bottom=thin)
# #     head = PatternFill("solid", start_color="DDE3EE")
# #     off = PatternFill("solid", start_color="D9D9D9")
# #     down = PatternFill("solid", start_color="F4CCCC")
# #     machine_fill = PatternFill("solid", start_color="FFF4DB")
# #     section_fill = {"CHILD": PatternFill("solid", start_color="D3F9D8"), "MAIN": PatternFill("solid", start_color="D0EBFF")}
# #     fills = {BLUE: PatternFill("solid", start_color="9FC5E8"), ORANGE: PatternFill("solid", start_color="F6B26B")}
# #     center = Alignment(horizontal="center", vertical="center", wrap_text=True)
# #     days = result["days"]
# #     last_col = 2 + len(days)

# #     def header(ws, first_col_title):
# #         ws.column_dimensions["A"].width = 36
# #         ws.column_dimensions["B"].width = 12
# #         for i, label in enumerate(("Working day #", "Date", "Day"), start=1):
# #             c = ws.cell(row=i, column=1, value=first_col_title if i == 3 else label)
# #             c.font, c.fill, c.border = font(bold=True), head, border
# #             ws.cell(row=i, column=2).fill = head
# #             ws.cell(row=i, column=2).border = border
# #         for j, d in enumerate(days, start=3):
# #             ws.column_dimensions[get_column_letter(j)].width = 11
# #             dt = date.fromisoformat(d["date"])
# #             vals = ("Off" if d["is_holiday"] else d["working_day_no"], dt.strftime("%d-%b"), d["weekday"])
# #             for i, v in enumerate(vals, start=1):
# #                 c = ws.cell(row=i, column=j, value=v)
# #                 c.font, c.border, c.alignment = font(bold=(i == 1)), border, center
# #                 c.fill = off if d["is_holiday"] else head
# #         ws.freeze_panes = "C4"

# #     def band(ws, r, text, fill):
# #         for j in range(1, last_col + 1):
# #             c = ws.cell(row=r, column=j)
# #             c.fill, c.border = fill, border
# #         ws.cell(row=r, column=1, value=text).font = font(bold=True)

# #     def day_cells(ws, r, segs, downs):
# #         col_of_date = {d["date"]: j for j, d in enumerate(days, start=3)}
# #         for j, d in enumerate(days, start=3):
# #             c = ws.cell(row=r, column=j)
# #             c.border = border
# #             if d["is_holiday"]:
# #                 c.fill = off
# #         for e in downs:
# #             dd = date.fromisoformat(e["start"][:10])
# #             while dd.isoformat() <= e["end"][:10]:
# #                 j = col_of_date.get(dd.isoformat())
# #                 if j and not (dd.isoformat() == e["end"][:10] and e["end"][11:] == "00:00:00" and e["end"][:10] != e["start"][:10]):
# #                     c = ws.cell(row=r, column=j, value="DOWN")
# #                     c.fill, c.font, c.alignment = down, font(bold=True, color="990000"), center
# #                 dd += timedelta(days=1)
# #         per_day: Dict[str, List[str]] = defaultdict(list)
# #         for s in segs:
# #             if s["label"] not in per_day[s["date"]]:
# #                 per_day[s["date"]].append(s["label"])
# #         for dstr, labels in per_day.items():
# #             j = col_of_date.get(dstr)
# #             if not j:
# #                 continue
# #             c = ws.cell(row=r, column=j, value=" ".join(labels))
# #             c.fill = fills[ORANGE if len(labels) >= 2 else BLUE]
# #             c.font, c.alignment = font(bold=True), center

# #     wb = Workbook()
# #     ws = wb.active
# #     ws.title = "PO on Process"
# #     header(ws, "Process")
# #     r, current = 4, None
# #     for st in result["stations"]:
# #         if st["section"] != current:
# #             current = st["section"]
# #             band(ws, r, f"{current} PROCESSES", section_fill.get(current, head))
# #             r += 1
# #         name = st["name"] + (f"  ({len(st['steps'])} steps, same day)" if st.get("kind") == "LINE" else "")
# #         a = ws.cell(row=r, column=1, value=name)
# #         a.font, a.border = font(bold=True), border
# #         if st.get("has_machine"):
# #             a.fill = machine_fill
# #         b = ws.cell(row=r, column=2, value=f"{st['shifts']} shift" + (f" · {len(st['real_machines'])} m/c" if st.get("real_machines") else ""))
# #         b.font, b.border, b.alignment = font(), border, center
# #         day_cells(ws, r, st["segments"], [])
# #         r += 1

# #     r += 1
# #     ws.cell(row=r, column=1, value="Legend").font = font(bold=True)
# #     for k, (txt, fill) in enumerate((("1 PO on the process", fills[BLUE]), ("2 or more POs share the process", fills[ORANGE]),
# #                                      ("Process with machine(s)", machine_fill)), 1):
# #         ws.cell(row=r + k, column=1, value=txt).font = font()
# #         ws.cell(row=r + k, column=2).fill = fill
# #     r += 5
# #     for j, h in enumerate(("Label", "Production order", "Part number", "Child / Main", "Quantity", "Start", "End"), start=1):
# #         c = ws.cell(row=r, column=j, value=h)
# #         c.font, c.fill, c.border = font(bold=True), head, border
# #     for k, p in enumerate(result["meta"]["pos"], start=1):
# #         for j, v in enumerate((p["label"], p["production_order"], p["part_number"], p["role"], p["quantity"],
# #                                p["start"], p["end"]), start=1):
# #             c = ws.cell(row=r + k, column=j, value=v)
# #             c.font, c.border = font(), border

# #     ws2 = wb.create_sheet("PO on Machines")
# #     header(ws2, "Machine")
# #     r, current = 4, None
# #     for m in result.get("machines", []):
# #         if m["group"] != current:
# #             current = m["group"]
# #             band(ws2, r, m["group_name"], machine_fill)
# #             r += 1
# #         a = ws2.cell(row=r, column=1, value=f"{m['name']} ({m['machine_id']})" + (f" · {m['step']}" if m.get("step") else ""))
# #         a.font, a.border = font(bold=True), border
# #         b = ws2.cell(row=r, column=2, value=f"{round(m['busy_minutes'] / 60, 1)} h")
# #         b.font, b.border, b.alignment = font(), border, center
# #         day_cells(ws2, r, m["segments"], m["downtime"])
# #         r += 1

# #     buf = io.BytesIO()
# #     wb.save(buf)
# #     return buf.getvalue()


# # # --------------------------------------------------------------------------------------
# # # Router
# # # --------------------------------------------------------------------------------------
# # def create_po_gantt_router(init_db, verify_token=None, engine=None) -> APIRouter:
# #     """Pass `engine` so machine_hours / batch_size are added to part_process_time and the plan tables are created
# #     at start-up (otherwise they are created on first use)."""
# #     if engine is not None:
# #         ensure_part_process_time_columns(engine)
# #         try:
# #             ensure_plan_tables(engine)
# #         except Exception as exc:
# #             print(f"[po_gantt] could not create schedule_plan tables: {exc}")
# #     router = APIRouter()
# #     deps = [Depends(verify_token)] if verify_token else []

# #     def _guard(fn, db=None):
# #         try:
# #             return fn()
# #         except PoGanttError as e:
# #             if db is not None:
# #                 db.rollback()
# #             raise HTTPException(status_code=e.status_code, detail=e.detail)

# #     def _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start):
# #         return _guard(lambda: build_po_gantt(db, production_order, plant, start_date, time_source, label_mode,
# #                                              show_holidays, shift_start))

# #     @router.get("/schedule/po-gantt/plants", dependencies=deps)
# #     def po_gantt_plants(db: Session = Depends(init_db)):
# #         return list_plants(db)

# #     @router.get("/schedule/part-process-time", dependencies=deps)
# #     def part_process_time_list(plant: Optional[str] = Query(None), part_no: Optional[str] = Query(None),
# #                                db: Session = Depends(init_db)):
# #         return list_part_process_times(db, plant, part_no)

# #     @router.put("/schedule/part-process-time", dependencies=deps)
# #     def part_process_time_save(body: PartTimeSave, db: Session = Depends(init_db)):
# #         return _guard(lambda: save_part_process_times(db, body), db)

# #     @router.get("/schedule/po-gantt/orders", dependencies=deps)
# #     def po_gantt_orders(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
# #         return list_open_orders(db, plant)

# #     @router.get("/schedule/po-gantt", dependencies=deps)
# #     def po_gantt(
# #         production_order: Optional[List[str]] = Query(None, description="PO numbers to load; order = load priority"),
# #         plant: Optional[str] = Query(None),
# #         start_date: Optional[date] = Query(None, description="default: first working day on/after today"),
# #         time_source: str = Query("actual"),
# #         label_mode: str = Query("seq", description="'seq' = B1, B2... | 'po' = PO number"),
# #         show_holidays: bool = Query(True, description="send off days as flagged columns"),
# #         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=20),
# #         db: Session = Depends(init_db),
# #     ):
# #         return _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)

# #     @router.get("/schedule/po-gantt/export", dependencies=deps)
# #     def po_gantt_export(
# #         production_order: Optional[List[str]] = Query(None),
# #         plant: Optional[str] = Query(None),
# #         start_date: Optional[date] = Query(None),
# #         time_source: str = Query("actual"),
# #         label_mode: str = Query("seq"),
# #         show_holidays: bool = Query(True),
# #         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=20),
# #         db: Session = Depends(init_db),
# #     ):
# #         result = _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)
# #         return StreamingResponse(
# #             io.BytesIO(build_po_gantt_xlsx(result)),
# #             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
# #             headers={"Content-Disposition": 'attachment; filename="po_gantt.xlsx"'},
# #         )

# #     @router.post("/schedule/plans", dependencies=deps)
# #     def plans_save(body: PlanSave, db: Session = Depends(init_db)):
# #         return _guard(lambda: save_plan(db, body), db)

# #     @router.get("/schedule/plans", dependencies=deps)
# #     def plans_list(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
# #         return list_plans(db, plant)

# #     @router.get("/schedule/plans/{plan_id}", dependencies=deps)
# #     def plans_get(plan_id: int, db: Session = Depends(init_db)):
# #         def go():
# #             p = _get_plan(db, plan_id)
# #             return {"plan": _plan_header(p), "snapshot": p.snapshot}
# #         return _guard(go)

# #     @router.put("/schedule/plans/{plan_id}/baseline", dependencies=deps)
# #     def plans_baseline(plan_id: int, db: Session = Depends(init_db)):
# #         return _guard(lambda: set_baseline(db, plan_id), db)

# #     @router.delete("/schedule/plans/{plan_id}", dependencies=deps)
# #     def plans_delete(plan_id: int, db: Session = Depends(init_db)):
# #         return _guard(lambda: delete_plan(db, plan_id), db)

# #     @router.get("/schedule/plans/{plan_id}/compare", dependencies=deps)
# #     def plans_compare(plan_id: int, db: Session = Depends(init_db)):
# #         return _guard(lambda: compare_plan(db, plan_id))

# #     return router











# """
# po_gantt_service.py  -  Production Schedule: PO on Process / PO on Machines / Planned vs Actual

#     GET    /schedule/po-gantt                 the schedule (stations = process rows, machines = machine rows)
#     GET    /schedule/po-gantt/orders          yet-to-start POs + part numbers of the plant (pickers)
#     GET    /schedule/po-gantt/plants          plant codes
#     GET    /schedule/po-gantt/export          the same schedule as .xlsx (sheet 1 process, sheet 2 machines)
#     GET/PUT /schedule/part-process-time       machine hours + batch size per part / process
#     POST   /schedule/plans                    save the schedule (built again with the same inputs) -> schedule_plan(+_item)
#     GET    /schedule/plans?plant=             saved plans
#     GET    /schedule/plans/{id}               one saved plan with its snapshot
#     PUT    /schedule/plans/{id}/baseline      make it the baseline of its plant
#     DELETE /schedule/plans/{id}
#     GET    /schedule/plans/{id}/compare       planned (saved plan) vs actual (operator_log / pcb_process_log)

# Hook-up (Data_Server.py) - unchanged:
#     from po_gantt_service import create_po_gantt_router
#     app.include_router(create_po_gantt_router(init_db, verify_token, engine))

# RULES
#  * POs come ONLY from PcbData. A PO is open when every one of its PCBs is New / Assigned; quantity = sum of PCB quantity.
#  * CHILD / MAIN comes from product_type_master.sub_product_type_name. A MAIN part is fed by the CHILD part with the
#    same product_type_name (HEXA child 62005774DA -> HEXA main 113300033357). bom_items is only a fallback link.
#  * The flow of a part = product_workflow_mapping ordered by step_sequence. A PO runs its flow process after process,
#    as one block (the whole quantity). A main PO starts right after the child PO(s) that feed it
#     finish (not after ALL child POs): linked POs are scheduled as one chain, and a run can use any free gap of a machine.
#  * SMT LINE = the 4 TOP SIDE steps in LINE_GROUPS: one process / one row, run in one go INSIDE ONE WORKING DAY (and in
#    one free stretch of its machines). Line time = slowest step for the whole PO + one board through the other steps.
#  * MACHINES: equipment_details (stage_id = process, machine_id). A machine is ONE resource: if the same machine_id
#    serves several processes, they share it. A line run occupies one machine of every line step at once.
#  * MAINTENANCE: a machine is not scheduled while it is down -
#      machine_breakdown_logs : breakdown_date + breakdown_time  ->  mc_ready_date, else + downtime_hours,
#                               else (still open) until now + OPEN_BREAKDOWN_HOURS.  Closed rows with no end are ignored.
#      maintenance_schedules  : every quarter that is not completed blocks the whole day of its date
#                               (actual date if filled, else planned date).
#    Records are matched to equipment by machine_id, else by machine name.
#  * Time per unit = (actual_time or sap_time, hours) + part_process_time.machine_hours (default 0).
#    Fallback base: routing process_time_seconds, stage_capacity.manufacturing_time_mins, then 1 min + warning.
#    SERIES: qty * t.  BATCH: ceil(qty / batch_size) * t.  Plus setup_minutes once per PO run.
#    batch_size = part_process_time.batch_size (if set) else stage_schedule_config.batch_size else 30.
#  * PLANT: only POs, equipment and process times of the chosen plant_code are used.
#  * Shifts per process from stage_capacity (by name; for the line the line name first); default 2 x 7 h.
#    The working window of a day is 08:00 - 22:00 at most (starts at shift_start, lasts shifts * hours, capped at 22:00).
#  * Off days: Sundays, 1st/3rd Saturdays, public_holidays, calendar_exceptions 'Holiday';
#    'Working' reopens a day, 'Half-Day' halves its window.
#  * ACTUAL (Planned vs Actual): operator_log (PCB x step, start_time / end_time), pcb_process_log via pcb_assignment
#    when operator_log has no row. A process is done for a PO when every PCB of the PO has an end time there.
# """
# import gzip
# import io
# import json
# import math
# import re
# from collections import defaultdict
# from datetime import date, datetime, time, timedelta
# from typing import Any, Dict, Iterable, List, Optional, Tuple

# from fastapi import APIRouter, Depends, HTTPException, Query, Request
# from fastapi.responses import Response, StreamingResponse
# from pydantic import BaseModel
# from sqlalchemy import func, or_, inspect as sa_inspect, text as sa_text
# from sqlalchemy.orm import Session, joinedload

# from Database_models import (
#     BOMItem, CalendarException, Equipments, MachineBreakdownLog, MaintenanceScheduleLog, OperatorLog,
#     OperatorShiftAssignment, OperatorStepMapping, PartProcessTime, PCBAssignment, PcbData, PCBProcessLog, Plant,
#     ProcessFlowMaster, Processtype, ProductTypeMaster, ProductWorkflowMapping, PublicHoliday, SchedulePlan,
#     SchedulePlanItem, ShiftDefinition, StageCapacityDB, StageScheduleConfig, InventorySpares, Consumables
# )

# # --------------------------------------------------------------------------------------
# # Constants (change the rules in one place)
# # --------------------------------------------------------------------------------------
# ISO = "%Y-%m-%dT%H:%M:%S"
# WEEKLY_OFF_DAYS = (6,)             # Python weekday(): Monday = 0 ... Sunday = 6
# ALT_SATURDAYS_OFF = (1, 3)         # 1st and 3rd Saturday of the month
# DEFAULT_SHIFTS = 2
# DEFAULT_HOURS_PER_SHIFT = 7.0
# DEFAULT_SHIFT_START = 8.0          # day window starts 08:00
# DAY_END_HOUR = 22.0                # ... and never runs past 22:00 (window = 08:00 - 22:00 = 14 h)
# DEFAULT_BATCH_SIZE = 30
# FALLBACK_MINUTES = 1.0
# MANUAL_PARALLEL_SLOTS = 1          # a MANUAL process (no machine) can work on this many POs at the same time (1 = one PO at a time)
# HANDOFF_WARN_HOURS = 30.0          # warn when a main PO starts later than this after the child PO it needs has finished
# PCB_OPEN_STATUSES = {"new", "assigned"}      # PcbData.status values that count as "not started"
# EXTRA_CHILD_LINKS: Dict[str, str] = {}      # {main_part_no: child_part_no} to force a link

# OPEN_BREAKDOWN_HOURS = 24.0        # open breakdown with no ready date / downtime: machine blocked until now + this
# DEFAULT_SPARE_LEAD_DAYS = 7        # inventorty_spares.procurement_lead_time empty / not a number
# CONSUMABLE_RESTOCK_DAYS = 7        # consumable out of stock / expired: process blocked from now for this many days (no restock date in the table)
# DONE_STATUSES = {"completed", "complete", "done", "closed", "resolved"}
# LATE_TOLERANCE_MIN = 0.0           # Planned vs Actual: finishing up to this many minutes after plan is "on time"

# ROLES = ("CHILD", "MAIN")                   # section order of the rows

# # Steps that run as ONE line, inside one working day, shown as ONE row (matched by step name, case-insensitive)
# LINE_GROUPS: Dict[str, Tuple[str, ...]] = {
#     "SMT LINE": (
#         "SOLDER PASTE PRINTING - TOP SIDE",
#         "SOLDER PASTE INSPECTION - TOP SIDE",
#         "PICK N PLACE - TOP SIDE",
#         "REFLOW - TOP SIDE",
#     ),
# }

# BLUE, ORANGE = "BLUE", "ORANGE"


# class PoGanttError(Exception):
#     def __init__(self, status_code: int, detail: str):
#         super().__init__(detail)
#         self.status_code, self.detail = status_code, detail


# # --------------------------------------------------------------------------------------
# # Helpers
# # --------------------------------------------------------------------------------------
# def _iso(dt: Optional[datetime]) -> Optional[str]:
#     return dt.replace(microsecond=0).strftime(ISO) if dt else None


# def _norm(s: Optional[str]) -> str:
#     """Part / PO numbers: ignore spaces and leading zeros."""
#     return (s or "").strip().lstrip("0")


# def _key(s: Optional[str]) -> str:
#     """Name matching: case / punctuation insensitive."""
#     return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


# def _hm(h: float) -> str:
#     hh = int(h)
#     return f"{hh:02d}:{int(round((h - hh) * 60)):02d}"


# def _chunks(seq: List[Any], n: int = 500) -> Iterable[List[Any]]:
#     for i in range(0, len(seq), n):
#         yield seq[i:i + n]


# _DATE_FMTS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y")
# _TIME_FMTS = ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "%I:%M%p", "%H:%M:%S.%f")


# def _parse_time(v) -> Optional[time]:
#     if v is None or v == "":
#         return None
#     if isinstance(v, time):
#         return v
#     s = str(v).strip()
#     for f in _TIME_FMTS:
#         try:
#             return datetime.strptime(s, f).time()
#         except ValueError:
#             continue
#     return None


# def _parse_dt(v) -> Optional[datetime]:
#     """Dates / datetimes as stored in the maintenance and log tables (ISO, dd-mm-yyyy, dd/mm/yyyy, with or without time)."""
#     if v is None or v == "":
#         return None
#     if isinstance(v, datetime):
#         return v if v.tzinfo is None else v.astimezone().replace(tzinfo=None)
#     if isinstance(v, date):
#         return datetime.combine(v, time.min)
#     s = str(v).strip()
#     if not s:
#         return None
#     try:
#         dt = datetime.fromisoformat(s[:-1] if s.endswith("Z") else s)
#         return dt if dt.tzinfo is None else dt.astimezone().replace(tzinfo=None)
#     except ValueError:
#         pass
#     for df in _DATE_FMTS:
#         for tf in ("",) + tuple(" " + t for t in _TIME_FMTS):
#             try:
#                 return datetime.strptime(s, df + tf)
#             except ValueError:
#                 continue
#     return None


# def _merge(intervals: Iterable[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
#     out: List[List[datetime]] = []
#     for a, b in sorted(intervals):
#         if out and a <= out[-1][1]:
#             out[-1][1] = max(out[-1][1], b)
#         else:
#             out.append([a, b])
#     return [(a, b) for a, b in out]


# def step_name(row) -> str:
#     """Stage name of a ProductWorkflowMapping row (via its process_detail relationship -> process_flow_master)."""
#     pd = row.process_detail
#     return (pd.step_name if pd and pd.step_name else None) or f"Step {row.flow_step_id}"


# # --------------------------------------------------------------------------------------
# # Calendar with a per-station daily window + machine down-time
# # --------------------------------------------------------------------------------------
# class DayCalendar:
#     """A working day d has a window [d shift_start, +capacity*factor). A station's capacity decides the window length.
#     `blocks` (sorted, merged (start, end) pairs) are times the machine is down; work never runs inside them."""

#     def __init__(self, holidays: Dict[date, str], exceptions: Dict[date, str], shift_start: float):
#         self.holidays = holidays
#         self.exceptions = {d: (t or "").strip().lower() for d, t in exceptions.items()}
#         self.shift_start = float(shift_start)

#     def factor(self, d: date) -> float:
#         exc = self.exceptions.get(d)
#         if exc == "working":
#             return 1.0
#         if exc == "half-day":
#             return 0.5
#         if exc == "holiday":
#             return 0.0
#         if d in self.holidays:
#             return 0.0
#         if d.weekday() in WEEKLY_OFF_DAYS:
#             return 0.0
#         if d.weekday() == 5 and ((d.day - 1) // 7 + 1) in ALT_SATURDAYS_OFF:
#             return 0.0
#         return 1.0

#     def off_reason(self, d: date) -> str:
#         if d in self.holidays:
#             return self.holidays[d] or "Holiday"
#         if self.exceptions.get(d) == "holiday":
#             return "Holiday"
#         if d.weekday() == 6:
#             return "Sunday"
#         if d.weekday() == 5:
#             return "1st/3rd Saturday"
#         return "Off"

#     def window(self, d: date, cap_min: float) -> Tuple[datetime, datetime]:
#         ws = datetime.combine(d, time.min) + timedelta(hours=self.shift_start)
#         return ws, ws + timedelta(minutes=cap_min * self.factor(d))

#     def first_working_day(self, d: date) -> date:
#         for _ in range(4000):
#             if self.factor(d) > 0:
#                 return d
#             d += timedelta(days=1)
#         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

#     def locate(self, t: datetime, cap_min: float) -> Tuple[datetime, date]:
#         """Earliest moment >= t inside a working window, and the working day that window belongs to."""
#         d = t.date() - timedelta(days=1)                      # yesterday's window may spill past midnight
#         for _ in range(4000):
#             if self.factor(d) > 0:
#                 ws, we = self.window(d, cap_min)
#                 if t < ws:
#                     return ws, d
#                 if t < we:
#                     return t, d
#             d += timedelta(days=1)
#         raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

#     def free_pieces(self, t: datetime, cap_min: float, blocks=()):
#         """Contiguous free stretches (day, start, end) from t onward: inside working windows and outside `blocks`."""
#         cur, day = self.locate(t, cap_min)
#         i, n = 0, len(blocks)
#         for _ in range(500000):
#             _, we = self.window(day, cap_min)
#             while i < n and blocks[i][1] <= cur:
#                 i += 1
#             if i < n and blocks[i][0] <= cur:                    # machine down right now -> jump past it
#                 cur, day = self.locate(blocks[i][1], cap_min)
#                 continue
#             end = we if i >= n else min(we, blocks[i][0])
#             if end > cur:
#                 yield day, cur, end
#             cur, day = self.locate(end, cap_min)
#         raise PoGanttError(500, "Could not place a run inside the working calendar")

#     def consume(self, start: datetime, minutes: float, cap_min: float, blocks=()):
#         """Run `minutes` of work from `start`, only inside working windows and outside down-time.
#         Returns (real_start, end, end_day, [(day, seg_start, seg_end, minutes), ...])."""
#         if minutes <= 0:
#             cur, day = self.locate(start, cap_min)
#             return cur, cur, day, []
#         rem, segs, first = float(minutes), [], None
#         for day, a, b in self.free_pieces(start, cap_min, blocks):
#             if first is None:
#                 first = a
#             use = min(rem, (b - a).total_seconds() / 60.0)
#             e = a + timedelta(minutes=use)
#             segs.append((day, a, e, use))
#             rem -= use
#             if rem <= 1e-9:
#                 return first, e, day, segs
#         raise PoGanttError(500, "Could not place a run inside the working calendar")

#     def place_within_day(self, start: datetime, minutes: float, cap_min: float, blocks=()):
#         """The whole run must sit in ONE free stretch of ONE working day. If it does not fit in what is left, it moves
#         to the next stretch that can hold it. A run longer than a full day has to spill over.
#         Returns consume(...) + (fits_in_one_day,)."""
#         if minutes <= cap_min + 1e-9:
#             for k, (day, a, b) in enumerate(self.free_pieces(start, cap_min, blocks)):
#                 if (b - a).total_seconds() / 60.0 + 1e-9 >= minutes:
#                     e = a + timedelta(minutes=minutes)
#                     return a, e, day, [(day, a, e, minutes)], True
#                 if k > 20000:
#                     break
#         # longer than one working day: start at the beginning of a day, so it is spread over as few days as possible
#         for day, a, b in self.free_pieces(start, cap_min, blocks):
#             if a == self.window(day, cap_min)[0]:
#                 start = a
#                 break
#         return self.consume(start, minutes, cap_min, blocks) + (False,)


# # --------------------------------------------------------------------------------------
# # Station container
# # --------------------------------------------------------------------------------------
# class Station:
#     def __init__(self, key: str, name: str, kind: str, step_ids: List[int]):
#         self.key, self.name, self.kind, self.step_ids = key, name, kind, list(step_ids)   # kind: STEP | LINE
#         self.steps: List[str] = []                       # member step names (LINE only)
#         self.options: List[Dict[str, Any]] = []          # ways to run it: {name, resources, phys, blocks}
#         self.real_machines: List[Tuple[str, str]] = []   # every physical machine of the process: (machine_id, step name)
#         self.shifts, self.hps, self.cap_min = DEFAULT_SHIFTS, DEFAULT_HOURS_PER_SHIFT, 0.0
#         self.mode, self.batch_size = "SERIES", DEFAULT_BATCH_SIZE
#         self.setup = self.cooldown = 0.0
#         self.cd_working_only = self.next_day_release = False
#         self.operators = 0
#         self.material: List[Dict[str, Any]] = []        # consumable shortages of its steps

#     @property
#     def machines(self) -> List[str]:
#         return [o["name"] for o in self.options if o["name"]]


# # --------------------------------------------------------------------------------------
# # Loaders
# # --------------------------------------------------------------------------------------
# def _load_candidates(db: Session, plant: Optional[str], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
#     """POs come ONLY from PcbData. Plant filter: the PO's part number must belong to that plant in
#     product_type_master (PcbData.plant is only used for parts missing from the master).
#     A PO is loadable when EVERY one of its PCBs has status New or Assigned.
#     PcbData.status stays 'Assigned' after the PCB is finished (the assign step is the only place that changes it), so a
#     PO whose PCBs are ALL finished in pcb_assignment (current_step_id empty or overall_status done) is left out -
#     otherwise every PO ever made would be scheduled again."""
#     finished = set()
#     for (pid,) in db.query(PCBAssignment.assigned_pcb_id).filter(or_(
#             PCBAssignment.current_step_id.is_(None),
#             func.lower(func.coalesce(PCBAssignment.overall_status, "")).in_(list(DONE_STATUSES)))).all():
#         finished.add(pid)
#     plant_parts, known_parts = set(), set()
#     if plant:
#         for pn, pc in db.query(ProductTypeMaster.part_number, ProductTypeMaster.plant_code).all():
#             known_parts.add(_norm(pn))
#             if pc == plant:
#                 plant_parts.add(_norm(pn))
#     q = db.query(PcbData.productionOrder, PcbData.partNumber, PcbData.quantity, PcbData.status, PcbData.createdAt,
#                  PcbData.plant, PcbData.serialNo, PcbData.PCBserialNoPartNumber, PcbData.Type
#                  ).filter(PcbData.productionOrder.isnot(None), PcbData.productionOrder != "")
#     by_po: Dict[str, list] = defaultdict(list)
#     for r in q.all():
#         if plant:
#             n = _norm(r[1])
#             if not (n in plant_parts or (n not in known_parts and (r[5] or "").strip() == plant)):
#                 continue
#         by_po[_norm(r[0])].append(r)

#     cands: Dict[str, Dict[str, Any]] = {}
#     for po, rows in by_po.items():
#         if all(r[7] in finished for r in rows):              # every PCB finished -> history, not scheduled
#             continue
#         parts = [r[1] for r in rows if r[1]]
#         if not parts:
#             warnings.append(f"PO {po}: PCBs have no part number - ignored")
#             continue
#         part = max(set(parts), key=parts.count)
#         if len(set(parts)) > 1:
#             warnings.append(f"PO {po}: PCBs carry several part numbers ({', '.join(sorted(set(parts)))}) - {part} used")
#         created = [r[4] for r in rows if r[4]]
#         cands[po] = {
#             "po": po, "part": part,
#             "qty": sum(r[2] if (r[2] and r[2] > 0) else 1 for r in rows),
#             "created": min(created) if created else None,
#             "started": any((r[3] or "").strip().lower() not in PCB_OPEN_STATUSES for r in rows),
#             # every PCB of the PO: serial number (links child <-> main), PCB id (pcb_assignment), Type, status
#             "pcbs": [{"sn": r[6], "serial": (r[6] or "").strip().upper(), "pcb_id": r[7], "part": r[1],
#                       "type": (r[8] or "").strip().upper(), "status": (r[3] or "").strip().lower()} for r in rows],
#         }
#     return cands


# def _serial_links(db: Session, cands: Dict[str, Dict[str, Any]], role_of, child_of: Dict[str, str], main_pos: List[str]):
#     """Child -> main link by SERIAL NUMBER (same rule as the assign step, can_proceed in Data_Server):
#     the main PCB with serialNo S needs the child PCB with the same serialNo S.
#     Only for `main_pos` (the main POs being scheduled); their child PCBs are looked up in PcbData by serial number, so a
#     child PO that is already finished (and so not a candidate) is still found.
#     Returns
#       links {main_po: [{child_po, child_part, pcbs, done, in_progress, not_assigned, steps}]}
#       unmatched {main_po: number of main PCBs with no child PCB of the same serial}
#     State of a child PCB (pcb_assignment.assigned_pcb_id = PCBserialNoPartNumber):
#       no assignment row                     -> not assigned
#       current_step_id empty / status done   -> done (child flow finished)
#       current_step_id filled                -> in process (at that step)"""
#     def is_main(pcb) -> bool:
#         return pcb["type"].endswith("MAIN") or role_of(pcb["part"]) == "MAIN"

#     mains = [po for po in main_pos if po in cands and role_of(cands[po]["part"]) == "MAIN"]
#     serials = sorted({pcb["sn"].strip() for po in mains for pcb in cands[po]["pcbs"] if pcb["sn"] and pcb["sn"].strip()})
#     child_by_serial: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
#     for chunk in _chunks(serials):
#         for sn, pid, part, po, typ, status in db.query(
#                 PcbData.serialNo, PcbData.PCBserialNoPartNumber, PcbData.partNumber, PcbData.productionOrder,
#                 PcbData.Type, PcbData.status).filter(PcbData.serialNo.in_(chunk)).all():
#             typ = (typ or "").strip().upper()
#             if po and (typ.endswith("CHILD") or role_of(part) == "CHILD"):
#                 child_by_serial[(sn or "").strip().upper()].append(
#                     {"po": _norm(po), "pcb_id": pid, "part": part, "status": (status or "").strip().lower()})

#     ids = [ch["pcb_id"] for lst in child_by_serial.values() for ch in lst if ch["pcb_id"]]
#     state: Dict[str, Tuple[Optional[int], str]] = {}
#     for chunk in _chunks(ids):
#         for a in db.query(PCBAssignment).filter(PCBAssignment.assigned_pcb_id.in_(chunk)).all():
#             state[a.assigned_pcb_id] = (a.current_step_id, (a.overall_status or "").strip().lower())

#     links: Dict[str, List[Dict[str, Any]]] = {}
#     unmatched: Dict[str, int] = {}
#     for po in mains:
#         c = cands[po]
#         per_child: Dict[str, Dict[str, Any]] = {}
#         missing = 0
#         for pcb in c["pcbs"]:
#             if not is_main(pcb):
#                 continue
#             hits = [ch for ch in child_by_serial.get(pcb["serial"], []) if ch["part"] != c["part"]]
#             want = child_of.get(c["part"])
#             hits = [h for h in hits if h["part"] == want] or hits          # prefer the child part of its family
#             if not hits:
#                 missing += 1
#                 continue
#             ch = hits[0]
#             l = per_child.setdefault(ch["po"], {"child_po": ch["po"], "child_part": ch["part"], "pcbs": 0, "done": 0,
#                                                 "in_progress": 0, "not_assigned": 0, "steps": []})
#             l["pcbs"] += 1
#             st = state.get(ch["pcb_id"])
#             if ch["status"] in DONE_STATUSES or (st and (st[0] is None or st[1] in DONE_STATUSES)):
#                 l["done"] += 1
#             elif st:
#                 l["in_progress"] += 1
#                 if st[0] not in l["steps"]:
#                     l["steps"].append(st[0])
#             else:
#                 l["not_assigned"] += 1
#         if per_child:
#             links[po] = list(per_child.values())
#             unmatched[po] = missing
#     return links, unmatched


# def _product_links(db: Session, warnings: Optional[List[str]] = None):
#     """Returns (products, child_of {main_pn: child_pn}, role_of(pn) -> 'CHILD' | 'MAIN').
#     1. product_type_master: CHILD and MAIN rows with the same product_type_name (and plant) belong together.
#     2. bom_items fallback: the child P/N appears as a material of the main P/N (leading zeros ignored).
#     3. EXTRA_CHILD_LINKS override."""
#     products = {p.part_number: p for p in db.query(ProductTypeMaster).all()}
#     part_by_norm = {_norm(pn): pn for pn in products}

#     def sub(pn: str) -> str:
#         p = products.get(pn)
#         return (p.sub_product_type_name or "").strip().upper() if p else ""

#     child_of: Dict[str, str] = {}
#     families: Dict[tuple, Dict[str, List[str]]] = defaultdict(lambda: {"CHILD": [], "MAIN": []})
#     for pn, p in products.items():
#         s = sub(pn)
#         if s in ROLES and _key(p.product_type_name):
#             families[(_key(p.product_type_name), p.plant_code)][s].append(pn)
#     for (fam, _plant), g in sorted(families.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
#         childs = sorted(g["CHILD"])
#         for m in g["MAIN"]:
#             if childs:
#                 child_of[m] = childs[0]
#                 if len(childs) > 1 and warnings is not None:
#                     warnings.append(f"Family {fam.upper()}: several child parts ({', '.join(childs)}) - "
#                                     f"{childs[0]} used to feed {m}")

#     for main_pn, material in db.query(BOMItem.product_part_number, BOMItem.material).all():
#         m = part_by_norm.get(_norm(main_pn)) or main_pn
#         c = part_by_norm.get(_norm(material))
#         if c and m and c != m and m not in child_of and sub(m) != "CHILD" and sub(c) != "MAIN":
#             child_of[m] = c
#     for m, c in EXTRA_CHILD_LINKS.items():
#         m, c = part_by_norm.get(_norm(m)), part_by_norm.get(_norm(c))
#         if m and c:
#             child_of[m] = c
#     for m, c in list(child_of.items()):
#         if child_of.get(c) == m:
#             del child_of[m]
#     child_parts = set(child_of.values())

#     def role_of(pn: Optional[str]) -> str:
#         s = sub(pn or "")
#         if s in ROLES:
#             return s
#         return "CHILD" if pn in child_parts else "MAIN"

#     return products, child_of, role_of


# # def _load_downtime(db: Session, machines: Dict[str, Dict[str, Any]], not_before: datetime, now: datetime,
# #                    warnings: List[str]) -> Dict[str, List[Dict[str, Any]]]:
# #     """Down-time events per machine_id from machine_breakdown_logs and maintenance_schedules.
# #     `machines` = {machine_id: {"name", "eqpt_no", ...}} of the plant. Only events ending after `not_before` are kept."""
# #     by_id = {_key(mid): mid for mid in machines}
# #     names: Dict[str, List[str]] = defaultdict(list)
# #     for mid, info in machines.items():
# #         for n in {_key(info.get("name")), _key(info.get("eqpt_no"))} - {""}:
# #             if mid not in names[n]:
# #                 names[n].append(mid)

# #     def match(rec_id, rec_name) -> Optional[str]:
# #         mid = by_id.get(_key(rec_id))
# #         if mid:
# #             return mid
# #         for k in (_key(rec_id), _key(rec_name)):
# #             if k and len(names.get(k, [])) == 1:          # only an unambiguous name
# #                 return names[k][0]
# #         return None

# #     out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
# #     assumed = 0
# #     try:
# #         breakdowns = db.query(MachineBreakdownLog).all()
# #     except Exception as exc:                                 # table missing -> schedule without it
# #         db.rollback()
# #         warnings.append(f"machine_breakdown_logs could not be read ({exc.__class__.__name__}) - breakdowns ignored")
# #         breakdowns = []
# #     for b in breakdowns:
# #         mid = match(b.machine_id, b.machine_name)
# #         if not mid:
# #             continue
# #         st = _parse_dt(b.breakdown_date)
# #         if not st:
# #             continue
# #         tt = _parse_time(b.breakdown_time)
# #         if tt and st.time() == time.min:
# #             st = datetime.combine(st.date(), tt)
# #         is_open = (b.status or "").strip().lower() not in DONE_STATUSES
# #         en, note = _parse_dt(b.mc_ready_date), None
# #         if not en and b.downtime_hours and b.downtime_hours > 0:
# #             en = st + timedelta(hours=float(b.downtime_hours))
# #         if not en and is_open:
# #             en = max(now, st) + timedelta(hours=OPEN_BREAKDOWN_HOURS)
# #             note = f"still open - assumed down until {_iso(en)}"
# #             assumed += 1
# #         if not en or en <= st or en <= not_before:
# #             continue
# #         out[mid].append({"machine": mid, "kind": "BREAKDOWN", "label": b.event_type or "Breakdown",
# #                          "status": b.status, "start": st, "end": en,
# #                          "note": note or (b.issue_description or "")})

# #     try:
# #         pms = db.query(MaintenanceScheduleLog).all()
# #     except Exception as exc:
# #         db.rollback()
# #         warnings.append(f"maintenance_schedules could not be read ({exc.__class__.__name__}) - maintenance ignored")
# #         pms = []
# #     for m in pms:
# #         mid = match(m.machine_id, m.machine_name)
# #         if not mid:
# #             continue
# #         for q in (1, 2, 3, 4):
# #             status = (getattr(m, f"q{q}_status") or "").strip().lower()
# #             if status in DONE_STATUSES:
# #                 continue
# #             d = _parse_dt(getattr(m, f"q{q}_actual_date")) or _parse_dt(getattr(m, f"q{q}_planned_date"))
# #             if not d:
# #                 continue
# #             st = datetime.combine(d.date(), time.min)
# #             en = st + timedelta(days=1)
# #             if en <= not_before:
# #                 continue
# #             out[mid].append({"machine": mid, "kind": "PM", "label": m.event_type or "Preventive Maintenance",
# #                              "status": getattr(m, f"q{q}_status"), "start": st, "end": en,
# #                              "note": f"Q{q} maintenance" + (f" - {m.remarks}" if m.remarks else "")})
# #     if assumed:
# #         warnings.append(f"{assumed} open breakdown(s) without ready date / downtime - machine assumed down for "
# #                         f"{OPEN_BREAKDOWN_HOURS:g} h from now")
# #     for mid in out:
# #         out[mid].sort(key=lambda e: e["start"])
# #     return out

# def _load_downtime(db: Session, machines: Dict[str, Dict[str, Any]], not_before: datetime, now: datetime,
#                    warnings: List[str]) -> Dict[str, List[Dict[str, Any]]]:
#     by_id = {_key(mid): mid for mid in machines}
#     names: Dict[str, List[str]] = defaultdict(list)
#     for mid, info in machines.items():
#         for n in {_key(info.get("name")), _key(info.get("eqpt_no"))} - {""}:
#             if mid not in names[n]:
#                 names[n].append(mid)

#     def match(rec_id, rec_name) -> Optional[str]:
#         mid = by_id.get(_key(rec_id))
#         if mid: return mid
#         for k in (_key(rec_id), _key(rec_name)):
#             if k and len(names.get(k, [])) == 1: return names[k][0]
#         return None

#     out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

#     # 1. Spares (inventorty_spares): a spare only matters when its machine is DOWN. If the spare is out of stock, an open
#     #    breakdown of that machine lasts at least the procurement lead time (the repair waits for the spare).
#     #    A running machine is NOT blocked because a spare is missing - that is only a risk (warning).
#     try:
#         spares = db.query(InventorySpares).all()
#     except Exception:
#         db.rollback()
#         spares = []
#     spare_out: Dict[str, Tuple[int, str]] = {}           # machine_id -> (lead days, spare text)
#     low_spares: List[str] = []
#     for sp in spares:
#         q, th = _num(sp.qty_avl), _num(sp.threshold_qty)
#         if q is None:                                    # no stock figure -> nothing to check
#             continue
#         if sp.eqpt_no:
#             mids = [match(sp.eqpt_no, None)]
#         else:                                            # spare of a process: every machine of that process
#             mids = [m for m, info in machines.items() if sp.flow_step_id in info.get("stage_ids", [])]
#         mids = [m for m in mids if m]
#         text = sp.decription or sp.part_number or "spare"
#         if q <= 0:
#             days = _lead_days(sp.procurement_lead_time)
#             for m in mids:
#                 if days >= spare_out.get(m, (0, ""))[0]:
#                     spare_out[m] = (days, text)
#         elif th is not None and q <= th:
#             low_spares.append(f"{text} ({', '.join(mids) or sp.eqpt_no or 'no machine'}: {q:g} left, threshold {th:g})")

#     # 2. Machine Breakdowns
#     try:
#         breakdowns = db.query(MachineBreakdownLog).all()
#     except Exception:
#         db.rollback()
#         breakdowns = []
#     waiting_spare = set()
#     for b in breakdowns:
#         mid = match(b.machine_id, b.machine_name)
#         if not mid: continue
#         st = _parse_dt(b.breakdown_date)
#         if not st: continue
#         tt = _parse_time(b.breakdown_time)
#         if tt and st.time() == time.min: st = datetime.combine(st.date(), tt)
#         is_open = (b.status or "").strip().lower() not in DONE_STATUSES
#         en, note = _parse_dt(b.mc_ready_date), None
#         if not en and b.downtime_hours and b.downtime_hours > 0:
#             en = st + timedelta(hours=float(b.downtime_hours))
#         if not en and is_open:
#             en = max(now, st) + timedelta(hours=OPEN_BREAKDOWN_HOURS)
#             note = f"still open - assumed down until {_iso(en)}"
#             if mid in spare_out:                         # the repair needs a spare that is not in stock
#                 days, text = spare_out[mid]
#                 en = max(en, max(now, st) + timedelta(days=days))
#                 note = f"waiting for spare '{text}' (out of stock, lead time {days} day(s)) - down until {_iso(en)}"
#                 waiting_spare.add(mid)
#         if not en or en <= st or en <= not_before: continue
#         out[mid].append({"machine": mid, "kind": "BREAKDOWN", "label": b.event_type or "Breakdown",
#                          "status": b.status, "start": st, "end": en, "note": note or (b.issue_description or "")})
#     if waiting_spare:
#         warnings.append("Breakdown repair waits for an out-of-stock spare (lead time used): "
#                         + ", ".join(f"{m} - {spare_out[m][1]} ({spare_out[m][0]} d)" for m in sorted(waiting_spare)))
#     risk = sorted(m for m in spare_out if m not in waiting_spare)
#     if risk:
#         warnings.append("Spare out of stock (machine still running - a breakdown there would take the lead time): "
#                         + ", ".join(f"{m} - {spare_out[m][1]} ({spare_out[m][0]} d)" for m in risk))
#     if low_spares:
#         warnings.append("Spares at or below threshold: " + "; ".join(low_spares))

#     # 3. Maintenance Schedules
#     try:
#         pms = db.query(MaintenanceScheduleLog).all()
#     except Exception:
#         db.rollback()
#         pms = []
#     for m in pms:
#         mid = match(m.machine_id, m.machine_name)
#         if not mid: continue
#         for q in (1, 2, 3, 4):
#             if (getattr(m, f"q{q}_status") or "").strip().lower() in DONE_STATUSES: continue
#             d = _parse_dt(getattr(m, f"q{q}_actual_date")) or _parse_dt(getattr(m, f"q{q}_planned_date"))
#             if not d: continue
#             st = datetime.combine(d.date(), time.min)
#             en = st + timedelta(days=1)
#             if en <= not_before: continue
#             out[mid].append({"machine": mid, "kind": "PM", "label": m.event_type or "Preventive Maintenance",
#                              "status": getattr(m, f"q{q}_status"), "start": st, "end": en,
#                              "note": f"Q{q} maintenance" + (f" - {m.remarks}" if m.remarks else "")})

#     for mid in out:
#         out[mid].sort(key=lambda e: e["start"])
#     return out

# def _num(v) -> Optional[float]:
#     """'12', '12.5', ' 12 nos' -> number; empty / text -> None."""
#     m = re.search(r"-?\d+(\.\d+)?", str(v)) if v is not None else None
#     return float(m.group()) if m else None


# def _lead_days(v) -> int:
#     """procurement_lead_time: '10', '10 days', '2 weeks' -> days."""
#     n = _num(v)
#     if n is None or n <= 0:
#         return DEFAULT_SPARE_LEAD_DAYS
#     return int(math.ceil(n * 7)) if "week" in str(v).lower() else int(math.ceil(n))


# def _load_consumable_blocks(db: Session, now: datetime, not_before: datetime,
#                             warnings: List[str]) -> Dict[int, List[Dict[str, Any]]]:
#     """Consumables (consumables table) of every process (stage_id = flow_step_id).
#     A consumable (material number) is usable when one of its rows has quantity > 0 (empty quantity = not counted, taken
#     as available) and is not past consumable_shelf_life. The PROCESS cannot run (all its machines, and a process without
#     a machine too) while one of its consumables is not usable:
#         out of stock / already expired -> blocked from now for CONSUMABLE_RESTOCK_DAYS
#         every batch in stock expires   -> blocked from the day after the last expiry for CONSUMABLE_RESTOCK_DAYS
#     The table has no use per PCB, so stock is checked as available yes / no, it is not used up PCB by PCB."""
#     try:
#         rows = db.query(Consumables).all()
#     except Exception:
#         db.rollback()
#         return {}
#     groups: Dict[Tuple[int, str], list] = defaultdict(list)
#     for c in rows:
#         if c.stage_id is not None:
#             groups[(c.stage_id, _key(c.consumable_material_number) or _key(c.consumable_material_name))].append(c)
#     today = now.date()

#     def expiry(c) -> Optional[date]:
#         d = c.consumable_shelf_life
#         return d.date() if isinstance(d, datetime) else d

#     out: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
#     low: List[str] = []
#     for (sid, _), lst in groups.items():
#         first = lst[0]
#         name = first.consumable_material_name or first.consumable_material_number or "consumable"
#         mat = first.consumable_material_number or ""
#         in_stock = [c for c in lst if c.quantity is None or c.quantity > 0]
#         usable = [c for c in in_stock if not expiry(c) or expiry(c) >= today]
#         ev = None
#         if not usable:
#             why = "out of stock" if not in_stock else f"expired on {max(expiry(c) for c in in_stock):%d-%m-%Y}"
#             ev = {"label": "Consumable " + ("out of stock" if not in_stock else "expired"), "start": now,
#                   "end": now + timedelta(days=CONSUMABLE_RESTOCK_DAYS),
#                   "note": f"{name} {mat} {why} - assumed back in {CONSUMABLE_RESTOCK_DAYS} day(s)"}
#         elif all(expiry(c) for c in usable):
#             last = max(expiry(c) for c in usable)
#             st = datetime.combine(last + timedelta(days=1), time.min)
#             ev = {"label": "Consumable expires", "start": st, "end": st + timedelta(days=CONSUMABLE_RESTOCK_DAYS),
#                   "note": f"{name} {mat}: the stock expires on {last:%d-%m-%Y} - assumed back in {CONSUMABLE_RESTOCK_DAYS} day(s)"}
#         if ev and ev["end"] > not_before:
#             out[sid].append({"machine": None, "kind": "SHORTAGE", "status": "Awaiting stock", "stage_id": sid,
#                              "material": mat, "material_name": name, **ev})
#         qty = [c.quantity for c in usable if c.quantity is not None]
#         th = max((x for x in (_num(c.threshold_qty) for c in lst) if x is not None), default=None)
#         if usable and qty and th is not None and sum(qty) <= th:
#             low.append(f"{name} (step {sid}: {sum(qty)} left, threshold {th:g})")
#     if low:
#         warnings.append("Consumables at or below threshold: " + "; ".join(low))
#     return out


# def _send(result: Dict[str, Any], request: Request, drop_for_page: bool = False) -> Response:
#     """Fast JSON for big schedules: no jsonable_encoder walk (the result is already plain JSON), no spaces, and gzip when
#     the browser accepts it (1.2 MB -> ~0.1 MB). drop_for_page: leave out what the page does not use
#     (rows' cells / po_runs and the flat runs list - Save plan / Excel build the schedule again on the server)."""
#     if drop_for_page:
#         result = {**result, "runs": None,
#                   "stations": [{k: v for k, v in s.items() if k not in ("cells", "po_runs")} for s in result["stations"]]}
#     body = json.dumps(result, separators=(",", ":"), default=str).encode()
#     if len(body) > 20000 and "gzip" in (request.headers.get("accept-encoding") or ""):
#         return Response(gzip.compress(body, 5), media_type="application/json",
#                         headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
#     return Response(body, media_type="application/json")


# def _dt_json(e: Dict[str, Any]) -> Dict[str, Any]:
#     return {**e, "start": _iso(e["start"]), "end": _iso(e["end"])}


# def list_open_orders(db: Session, plant: Optional[str] = None) -> Dict[str, Any]:
#     """Yet-to-start POs for the picker (oldest first) + the part numbers of the plant (product_type_master)."""
#     warnings: List[str] = []
#     _, _, role_of = _product_links(db)
#     cands = _load_candidates(db, plant, warnings)
#     open_pos = sorted((c for c in cands.values() if not c["started"]),
#                       key=lambda c: (c["created"] or datetime.max, c["po"]))
#     pq = db.query(ProductTypeMaster)
#     if plant:
#         pq = pq.filter(ProductTypeMaster.plant_code == plant)
#     parts = [{"part_number": p.part_number, "role": role_of(p.part_number), "product_type": p.product_type_name,
#               "sub_type": p.sub_product_type_name, "description": p.description}
#              for p in pq.order_by(ProductTypeMaster.product_type_name, ProductTypeMaster.part_number).all()]
#     return {"orders": [{"production_order": c["po"], "part_number": c["part"], "quantity": c["qty"],
#                         "role": role_of(c["part"]), "created": c["created"].isoformat() if c["created"] else None}
#                        for c in open_pos],
#             "parts": parts,
#             "warnings": warnings}


# def list_plants(db: Session) -> Dict[str, Any]:
#     """Plant codes of product_type_master (a PO belongs to the plant of its part number)."""
#     codes = sorted({(r[0] or "").strip() for r in db.query(ProductTypeMaster.plant_code).distinct().all()
#                     if (r[0] or "").strip()})
#     info = {p.plant_code: p.location for p in db.query(Plant).all()}
#     return {"plants": [{"plant_code": c, "location": info.get(c) or ""} for c in codes]}


# def ensure_part_process_time_columns(engine) -> None:
#     """create_all() does not alter existing tables - add machine_hours / batch_size once if they are missing."""
#     try:
#         cols = {c["name"] for c in sa_inspect(engine).get_columns("part_process_time")}
#         with engine.begin() as conn:
#             if "machine_hours" not in cols:
#                 conn.execute(sa_text("ALTER TABLE part_process_time ADD COLUMN machine_hours DOUBLE PRECISION NOT NULL DEFAULT 0"))
#             if "batch_size" not in cols:
#                 conn.execute(sa_text("ALTER TABLE part_process_time ADD COLUMN batch_size INTEGER"))
#     except Exception as exc:                                   # never block start-up
#         print(f"[po_gantt] could not verify part_process_time columns: {exc}")


# _PLAN_TABLES_READY = False


# def ensure_plan_tables(bind) -> None:
#     """Create schedule_plan / schedule_plan_item if they do not exist yet (create_all does this too)."""
#     global _PLAN_TABLES_READY
#     if _PLAN_TABLES_READY:
#         return
#     SchedulePlan.__table__.create(bind=bind, checkfirst=True)
#     SchedulePlanItem.__table__.create(bind=bind, checkfirst=True)
#     _PLAN_TABLES_READY = True


# def list_part_process_times(db: Session, plant: Optional[str], part_no: Optional[str] = None) -> Dict[str, Any]:
#     """Every routing step of every part of the plant, joined with its part_process_time row (if any)."""
#     pq = db.query(ProductTypeMaster)
#     if plant:
#         pq = pq.filter(ProductTypeMaster.plant_code == plant)
#     if part_no:
#         pq = pq.filter(ProductTypeMaster.part_number == part_no)
#     products = pq.order_by(ProductTypeMaster.product_type_name, ProductTypeMaster.sub_product_type_name,
#                            ProductTypeMaster.part_number).all()
#     pns = [p.part_number for p in products]
#     if not pns:
#         return {"plant": plant, "parts": [], "rows": []}
#     batch = {p.stage_id for p in db.query(Processtype).filter(Processtype.process_type_batch.is_(True)).all()}
#     ppt = {}
#     tq = db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(pns))
#     if plant:
#         tq = tq.filter(PartProcessTime.plant == plant)
#     for r in tq.all():
#         ppt[(r.part_no, r.process_id)] = r
#     rows = []
#     for p in products:
#         steps = db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
#                 ).filter(ProductWorkflowMapping.product_part_number == p.part_number
#                 ).order_by(ProductWorkflowMapping.step_sequence, ProductWorkflowMapping.id).all()
#         for st in steps:
#             r = ppt.get((p.part_number, st.flow_step_id))
#             rows.append({
#                 "part_no": p.part_number, "product_type": p.product_type_name, "sub_type": p.sub_product_type_name,
#                 "process_id": st.flow_step_id, "process_name": step_name(st), "step_sequence": st.step_sequence,
#                 "is_batch": st.flow_step_id in batch,
#                 "sap_time": r.sap_time if r else None, "actual_time": r.actual_time if r else None,
#                 "machine_hours": float(r.machine_hours or 0) if r else 0.0,
#                 "batch_size": r.batch_size if r else None,
#             })
#     return {"plant": plant,
#             "parts": [{"part_no": p.part_number, "product_type": p.product_type_name, "sub_type": p.sub_product_type_name,
#                        "description": p.description} for p in products],
#             "rows": rows}


# class PartTimeItem(BaseModel):
#     part_no: str
#     process_id: int
#     machine_hours: Optional[float] = 0.0
#     batch_size: Optional[int] = None


# class PartTimeSave(BaseModel):
#     plant: str
#     items: List[PartTimeItem]


# def save_part_process_times(db: Session, body: PartTimeSave) -> Dict[str, Any]:
#     stage_names = {s.flow_step_id: s.step_name for s in db.query(ProcessFlowMaster).all()}
#     updated = created = 0
#     for it in body.items:
#         mh = float(it.machine_hours or 0)
#         if mh < 0:
#             raise PoGanttError(422, f"{it.part_no} / step {it.process_id}: machine hours cannot be negative")
#         if it.batch_size is not None and it.batch_size < 0:
#             raise PoGanttError(422, f"{it.part_no} / step {it.process_id}: batch size cannot be negative")
#         bs = int(it.batch_size) if it.batch_size and it.batch_size > 0 else None
#         row = db.query(PartProcessTime).filter(
#             PartProcessTime.part_no == it.part_no, PartProcessTime.plant == body.plant,
#             PartProcessTime.process_id == it.process_id).first()
#         if row:
#             row.machine_hours, row.batch_size = mh, bs
#             updated += 1
#         else:
#             if it.process_id not in stage_names:
#                 raise PoGanttError(404, f"Process step {it.process_id} not found")
#             db.add(PartProcessTime(part_no=it.part_no, plant=body.plant, process_id=it.process_id,
#                                    process_name=stage_names[it.process_id], machine_hours=mh, batch_size=bs))
#             created += 1
#     db.commit()
#     return {"updated": updated, "created": created}


# # --------------------------------------------------------------------------------------
# # Builder
# # --------------------------------------------------------------------------------------
# def build_po_gantt(db: Session, production_orders: Optional[List[str]] = None, plant: Optional[str] = None,
#                    start_date: Optional[date] = None, time_source: str = "actual", label_mode: str = "seq",
#                    show_holidays: bool = False, shift_start: float = DEFAULT_SHIFT_START,
#                    today: Optional[date] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
#     if time_source not in ("actual", "sap"):
#         raise PoGanttError(400, "time_source must be 'actual' or 'sap'")
#     if label_mode not in ("seq", "po"):
#         raise PoGanttError(400, "label_mode must be 'seq' or 'po'")
#     warnings: List[str] = []
#     now = now or datetime.now()
#     today = today or now.date()

#     # ---------------- calendar ----------------
#     holidays = {h.holiday_date: h.name for h in db.query(PublicHoliday).all()}
#     exceptions = {e.exception_date: e.exception_type for e in db.query(CalendarException).all()}
#     cal = DayCalendar(holidays, exceptions, shift_start)
#     day_cap = max((DAY_END_HOUR - shift_start) * 60.0, 60.0)       # the working day ends at 22:00

#     # ---------------- masters (loaded once) ----------------
#     products, child_of, role_of = _product_links(db, warnings)

#     is_batch: Dict[int, bool] = defaultdict(bool)
#     for p in db.query(Processtype).all():
#         if p.process_type_batch:
#             is_batch[p.stage_id] = True
#     cfg = {c.stage_id: c for c in db.query(StageScheduleConfig).all()}
#     cap_by_key = {_key(c.name): c for c in db.query(StageCapacityDB).all()}
#     cap_compact = {k.replace(" ", ""): c for k, c in cap_by_key.items()}

#     def find_cap(name: Optional[str]):
#         """stage_capacity row of a process: exact name, then ignoring spaces / punctuation, then a UNIQUE partial match."""
#         k = _key(name)
#         if not k:
#             return None
#         c = cap_by_key.get(k) or cap_compact.get(k.replace(" ", ""))
#         if c:
#             return c
#         hits = [v for ck, v in cap_by_key.items() if ck and (ck in k or k in ck)]
#         return hits[0] if len(hits) == 1 else None

#     equipment: Dict[int, List[str]] = defaultdict(list)          # stage_id -> machine_ids
#     machine_info: Dict[str, Dict[str, Any]] = {}                  # machine_id -> details
#     for e in db.query(Equipments).order_by(Equipments.stage_id, Equipments.id).all():
#         if plant and e.plant_code and e.plant_code != plant:          # only the machines of the chosen plant
#             continue
#         mid = e.machine_id or e.eqpt_no or f"EQ-{e.id}"
#         if e.stage_id is not None and mid not in equipment[e.stage_id]:
#             equipment[e.stage_id].append(mid)
#         info = machine_info.setdefault(mid, {"machine_id": mid, "name": e.eqpt_name or mid, "eqpt_no": e.eqpt_no,
#                                              "process_type": e.process_type,
#                                              "make": e.eqpt_make, "model": e.eqpt_model,
#                                              "workcenter": e.workcenter_name, "stage_ids": []})
#         if e.stage_id is not None and e.stage_id not in info["stage_ids"]:
#             info["stage_ids"].append(e.stage_id)

#     # equipment is normally linked by stage_id = flow_step_id. A process whose flow step has a different id / spelling
#     # (e.g. "BAKING" vs "Baking") would then wrongly look manual - so also match by the step NAME, and by the
#     # equipment's own process_type / workcenter / name.
#     stage_names = {r.flow_step_id: r.step_name for r in db.query(ProcessFlowMaster).all()}
#     eq_by_stage_name: Dict[str, List[str]] = defaultdict(list)
#     for sid_, mids_ in equipment.items():
#         k_ = _key(stage_names.get(sid_))
#         for m_ in mids_:
#             if k_ and m_ not in eq_by_stage_name[k_]:
#                 eq_by_stage_name[k_].append(m_)
#     eq_by_label: Dict[str, List[str]] = defaultdict(list)
#     for m_, inf_ in machine_info.items():
#         for lab_ in (inf_.get("process_type"), inf_.get("workcenter"), inf_.get("name")):
#             k_ = _key(lab_)
#             if k_ and m_ not in eq_by_label[k_]:
#                 eq_by_label[k_].append(m_)

#     def machines_for_step(sid: int, name: str) -> List[str]:
#         k_ = _key(name)
#         for pool in (equipment.get(sid), eq_by_stage_name.get(k_), eq_by_label.get(k_)):
#             if pool:
#                 return list(pool)
#         return []

#     shift_names = [s.name for s in db.query(ShiftDefinition).filter(ShiftDefinition.is_active.is_(True))
#                    .order_by(ShiftDefinition.sort_order, ShiftDefinition.id).all()]
#     assigned: Dict[str, set] = defaultdict(set)
#     for a in db.query(OperatorShiftAssignment).all():
#         assigned[a.operator_staff_no].add(a.shift_name)
#     ops_by_stage: Dict[int, List[str]] = defaultdict(list)
#     for o in db.query(OperatorStepMapping).all():
#         who = o.operator_staff_no or o.operator_name
#         if who and who not in ops_by_stage[o.flow_step_id]:
#             ops_by_stage[o.flow_step_id].append(who)

#     def operators_per_shift(sid: int) -> int:
#         ops = ops_by_stage.get(sid, [])
#         if not shift_names:
#             return len(ops)
#         return max((sum(1 for o in ops if not assigned.get(o) or sn in assigned[o]) for sn in shift_names), default=0)

#     line_of_name = {_key(n): g for g, names in LINE_GROUPS.items() for n in names}

#     # ---------------- select the POs to load ----------------
#     cands = _load_candidates(db, plant, warnings)
#     if production_orders:
#         selected, seen = [], set()
#         for raw in production_orders:
#             k = _norm(raw) or raw
#             if k in seen:
#                 continue
#             seen.add(k)
#             if k not in cands:
#                 raise PoGanttError(404, f"Production order {raw} not found")
#             if cands[k]["started"]:
#                 warnings.append(f"PO {k} has already started - scheduled from scratch as requested")
#             selected.append(cands[k])
#         explicit = True
#     else:
#         selected = sorted((c for c in cands.values() if not c["started"]),
#                           key=lambda c: (c["created"] or datetime.max, c["po"]))
#         explicit = False

#     # ---------------- routing (product_workflow_mapping) + times ----------------
#     # child -> main by serial number; the child POs that are NOT in this schedule are still needed (in process / what-if)
#     serial_links, serial_unmatched = _serial_links(db, cands, role_of, child_of, [c["po"] for c in selected])
#     sel_pos = {c["po"] for c in selected}
#     outside_child_parts = {l["child_part"] for c in selected for l in serial_links.get(c["po"], [])
#                            if l["child_po"] not in sel_pos and l["child_part"]}
#     part_numbers = {c["part"] for c in selected if c["part"]} | outside_child_parts
#     routing: Dict[str, list] = defaultdict(list)
#     times: Dict[tuple, list] = defaultdict(list)
#     if part_numbers:
#         for r in db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
#                 ).filter(ProductWorkflowMapping.product_part_number.in_(part_numbers)
#                 ).order_by(ProductWorkflowMapping.product_part_number, ProductWorkflowMapping.step_sequence,
#                            ProductWorkflowMapping.id).all():
#             routing[r.product_part_number].append(r)
#         tq = db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(part_numbers))
#         if plant:
#             tq = tq.filter(PartProcessTime.plant == plant)
#         for r in tq.all():
#             times[(r.part_no, r.process_id)].append(r)
#     other = "sap" if time_source == "actual" else "actual"

#     def time_row(part: str, sid: int):
#         rows = times.get((part, sid), [])
#         if not rows:
#             return None
#         pref = plant or (products[part].plant_code if part in products else None)
#         return next((r for r in rows if r.plant == pref), rows[0])

#     def hours_per_unit(part: str, step) -> Tuple[Optional[float], str]:
#         """Hours for one unit (SERIES) / one batch (BATCH) = base time + machine hours."""
#         row = time_row(part, step.flow_step_id)
#         mh = max(float(getattr(row, "machine_hours", 0) or 0), 0.0) if row else 0.0
#         base, src = None, "none"
#         if row:
#             for s in (time_source, other):
#                 val = row.actual_time if s == "actual" else row.sap_time
#                 if val and val > 0:
#                     base, src = float(val), f"part_process_time.{s}"
#                     break
#         if base is None and getattr(step, "process_time_seconds", None) and step.process_time_seconds > 0:
#             base, src = step.process_time_seconds / 3600.0, "routing"
#         if base is None:
#             cap = find_cap(step_name(step))
#             if cap and cap.manufacturing_time_mins and cap.manufacturing_time_mins > 0:
#                 base, src = float(cap.manufacturing_time_mins) / 60.0, "stage_capacity"
#         if base is None and mh <= 0:
#             return None, "none"
#         return (base or 0.0) + mh, src + (" + machine_hours" if mh > 0 else "")

#     def batch_size_for(part: str, sid: int) -> int:
#         row = time_row(part, sid)
#         if row and getattr(row, "batch_size", None) and row.batch_size > 0:
#             return int(row.batch_size)
#         return max(int((cfg[sid].batch_size if sid in cfg else 0) or DEFAULT_BATCH_SIZE), 1)

#     def capacity_for(names: List[str]) -> Optional[Tuple[int, float]]:
#         for n in names:
#             c = find_cap(n)
#             if c:
#                 sh = int(c.shifts_per_day or 0)
#                 hp = float(c.hours_per_shift or 0)
#                 return (sh if sh > 0 else DEFAULT_SHIFTS), (hp if hp > 0 else DEFAULT_HOURS_PER_SHIFT)
#         return None

#     # ---------------- operations of a part (its flow, with the line steps merged) ----------------
#     ops_cache: Dict[str, List[Dict[str, Any]]] = {}

#     def ops_for(part: str) -> List[Dict[str, Any]]:
#         if part in ops_cache:
#             return ops_cache[part]
#         steps = routing.get(part, [])
#         ops, done = [], set()
#         for st in steps:
#             g = line_of_name.get(_key(step_name(st)))
#             if g:
#                 if g in done:
#                     continue
#                 done.add(g)
#                 members = [x for x in steps if line_of_name.get(_key(step_name(x))) == g]
#                 ops.append({"key": f"LINE-{g}", "line": g, "steps": members})
#             else:
#                 ops.append({"key": f"STEP-{st.flow_step_id}", "line": None, "steps": [st]})
#         ops_cache[part] = ops
#         return ops

#     # ---------------- build PO objects ----------------
#     pos: List[Dict[str, Any]] = []
#     for c in selected:
#         part, po_no = c["part"], c["po"]
#         steps = routing.get(part or "", [])
#         if not steps or c["qty"] <= 0:
#             msg = (f"PO {po_no}: part {part} has no flow in product_workflow_mapping" if not steps
#                    else f"PO {po_no}: quantity is 0")
#             if explicit:
#                 raise PoGanttError(422, msg)
#             warnings.append(msg + " - not scheduled")
#             continue
#         pos.append({"po": po_no, "part": part, "qty": c["qty"], "ops": ops_for(part), "idx": len(pos) + 1,
#                     "role": role_of(part)})
#     if not pos:
#         raise PoGanttError(404, "No production orders to schedule")
#     for p in pos:
#         p["label"] = f"B{p['idx']}" if label_mode == "seq" else p["po"]
#     label_idx = {p["label"]: p["idx"] for p in pos}
#     label_role = {p["label"]: p["role"] for p in pos}

#     # ---------------- machine down-time (breakdowns + preventive maintenance) ----------------
#     start_day = cal.first_working_day(start_date or today)
#     start_dt = datetime.combine(start_day, time.min) + timedelta(hours=shift_start)
#     downtime = _load_downtime(db, machine_info, start_dt, now, warnings)
#     blocks_of = {mid: _merge((e["start"], e["end"]) for e in evs) for mid, evs in downtime.items()}
#     material = _load_consumable_blocks(db, now, start_dt, warnings)     # flow_step_id -> consumable shortages

#     # ---------------- stations ----------------
#     stations: Dict[str, Station] = {}
#     cap_missing: List[str] = []

#     def make_station(op: Dict[str, Any]) -> Station:
#         key = op["key"]
#         if key in stations:
#             return stations[key]
#         members = op["steps"]
#         sids = [m.flow_step_id for m in members]
#         if op["line"]:
#             g = op["line"]
#             s = Station(key, g, "LINE", sids)
#             s.steps = [step_name(m) for m in members]
#             s.mode = "LINE"
#             mach_of = {m.flow_step_id: machines_for_step(m.flow_step_id, step_name(m)) for m in members}
#             with_eq = [(m.flow_step_id, step_name(m)) for m in members if mach_of[m.flow_step_id]]
#             n = min(len(mach_of[i]) for i, _ in with_eq) if with_eq else 1   # as parallel as its narrowest step
#             for i in range(n):
#                 phys = [(mach_of[sid][i], nm) for sid, nm in with_eq]
#                 s.options.append({"name": g if n == 1 else f"{g} #{i + 1}",
#                                   "resources": [m for m, _ in phys] or [f"LINE-{g}-{i}"], "phys": phys})
#             s.real_machines = [(mid, nm) for sid, nm in with_eq for mid in mach_of[sid]]
#             s.setup = max([float(cfg[i].setup_minutes or 0) for i in sids if i in cfg], default=0.0)
#             s.operators = max(operators_per_shift(i) for i in sids)
#             last = cfg.get(sids[-1])
#             names = [g] + s.steps
#         else:
#             sid = sids[0]
#             s = Station(key, step_name(members[0]), "STEP", sids)
#             s.mode = "BATCH" if is_batch.get(sid) else "SERIES"
#             last = cfg.get(sid)
#             if last:
#                 s.batch_size = max(int(last.batch_size or DEFAULT_BATCH_SIZE), 1)
#                 s.setup = float(last.setup_minutes or 0)
#             mids = machines_for_step(sid, s.name)
#             rmode = (str(getattr(last, "resource_mode", None) or "AUTO")).upper() if last else "AUTO"
#             if rmode == "MANUAL":                                   # stage_schedule_config.resource_mode forces manual
#                 mids = []
#             elif rmode == "MACHINE" and not mids:
#                 warnings.append(f"{s.name}: resource_mode is MACHINE but no machine is mapped in equipment_details")
#             if mids:
#                 s.options = [{"name": mid, "resources": [mid], "phys": [(mid, s.name)]} for mid in mids]
#                 s.real_machines = [(mid, s.name) for mid in mids]
#             else:
#                 slots = max(int(MANUAL_PARALLEL_SLOTS), 1)          # no machine -> people: several POs can run side by side
#                 s.options = [{"name": "", "resources": [f"NO-MACHINE-{sid}-{k}"], "phys": []} for k in range(slots)]
#             s.operators = operators_per_shift(sid)
#             names = [s.name]
#         # a consumable shortage of ANY step stops the whole process (SMT LINE: the whole line), machine or not
#         s.material = [e for i in sids for e in material.get(i, [])]
#         mat_blocks = [(e["start"], e["end"]) for e in s.material]
#         for o in s.options:
#             o["blocks"] = _merge([b for r in o["resources"] for b in blocks_of.get(r, [])] + mat_blocks)
#         if last:
#             s.cooldown = float(last.cooldown_minutes or 0)
#             s.cd_working_only = bool(last.cooldown_working_time_only)
#             s.next_day_release = bool(last.next_day_release) and bool(is_batch.get(sids[-1]))
#         got = capacity_for(names)
#         if got:
#             s.shifts, s.hps = got
#         if not got:
#             cap_missing.append(s.name)
#         s.cap_min = min(s.shifts * s.hps * 60.0, day_cap)
#         stations[key] = s
#         return s

#     for p in pos:
#         for op in p["ops"]:
#             make_station(op)
#     for cpart in outside_child_parts:                   # child POs outside the schedule (only for estimates)
#         for op in ops_for(cpart):
#             make_station(op)
#     if cap_missing:
#         warnings.append(f"No stage_capacity row matches: {', '.join(dict.fromkeys(cap_missing))} - default "
#                         f"{DEFAULT_SHIFTS} shifts x {DEFAULT_HOURS_PER_SHIFT:g} h used (add the process name to stage_capacity)")

#     # ---------------- run time of one operation ----------------
#     missing_time: Dict[str, List[str]] = defaultdict(list)

#     def step_minutes(part: str, st, qty: int) -> Optional[Tuple[float, float]]:
#         """(minutes for the whole PO, minutes for the first board / batch) of one routing step."""
#         hrs, _src = hours_per_unit(part, st)
#         if hrs is None:
#             return None
#         t = hrs * 60.0
#         sid = st.flow_step_id
#         if is_batch.get(sid):
#             bs = batch_size_for(part, sid)
#             return math.ceil(qty / bs) * t, t
#         return qty * t, t

#     def op_minutes_and_parts(p: Dict[str, Any], op: Dict[str, Any], s: Station):
#         """Minutes of one operation for the whole PO, and (PO minutes, first board / batch minutes) of each step in it.
#         SMT LINE: the steps run one after the other, so the line time is the SUM of its steps."""
#         parts = []
#         for st in op["steps"]:
#             m = step_minutes(p["part"], st, p["qty"])
#             if m is None:
#                 missing_time[p["part"]].append(step_name(st))
#                 m = (FALLBACK_MINUTES, FALLBACK_MINUTES)
#             parts.append(m)
#         total = sum(m[0] for m in parts) if s.kind == "LINE" else parts[0][0]
#         return max(total + s.setup, 1.0), parts

#     # ---------------- child PO -> main PO ----------------
#     # 1. by SERIAL number: the main PCB needs the child PCB with the same serial (as the assign step checks it).
#     #    child PO in this schedule          -> the main PO waits for it
#     #    child PO outside, PCBs done        -> nothing to wait for
#     #    child PO outside, PCBs in process  -> the main PO waits for the estimated end of the child (rest of its flow)
#     #    child PO outside, NOT assigned     -> the main PO is scheduled without waiting (FORCED) + "assign the child on
#     #                                          day X -> main can start on day Y" message
#     # 2. main POs without any serial match: first come, first served by quantity (as before).
#     depends_on: Dict[str, List[str]] = defaultdict(list)
#     link_by: Dict[str, str] = {}                                    # main po -> "serial" | "quantity"
#     outside_links: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # main po -> child links outside the schedule
#     by_part: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
#     for p in pos:
#         by_part[p["part"]].append(p)
#     in_plan = {p["po"] for p in pos}
#     taken_by_serial: Dict[str, int] = defaultdict(int)             # child po -> PCBs already linked by serial
#     for m in pos:
#         links = serial_links.get(m["po"], [])
#         if not links:
#             continue
#         link_by[m["po"]] = "serial"
#         for l in links:
#             taken_by_serial[l["child_po"]] += l["pcbs"]
#             if l["child_po"] in in_plan:
#                 depends_on[m["po"]].append(l["child_po"])
#             else:
#                 outside_links[m["po"]].append(l)
#         if serial_unmatched.get(m["po"]):
#             warnings.append(f"PO {m['po']} ({m['label']}): {serial_unmatched[m['po']]} main PCB(s) have no child PCB with "
#                             f"the same serial number - those child PCBs are assumed in stock")
#     for main_pn, child_pn in child_of.items():
#         mains = [m for m in by_part.get(main_pn, []) if m["po"] not in link_by]
#         childs = by_part.get(child_pn, [])
#         if not mains:
#             continue
#         if not childs:
#             warnings.append(f"Part {main_pn}: no child PO ({child_pn}) loaded and no child PCB with the same serial - "
#                             f"child PCBs assumed in stock, main PO(s) {', '.join(m['label'] for m in mains)} start right away")
#             continue
#         supply, run = [], 0
#         for c in childs:
#             free = max(c["qty"] - taken_by_serial.get(c["po"], 0), 0)
#             if free:
#                 supply.append((run, run + free, c["po"]))
#                 run += free
#         need = 0
#         for m in mains:
#             lo, hi = need, need + m["qty"]
#             need = hi
#             depends_on[m["po"]] = [cpo for (a, b, cpo) in supply if a < hi and b > lo]
#             link_by[m["po"]] = "quantity"
#             if hi > run:
#                 warnings.append(f"PO {m['po']}: needs more child PCBs than the loaded child POs provide - rest assumed in stock")

#     def depth(part: str) -> int:
#         d = 0
#         while part in child_of and d < 10:
#             part, d = child_of[part], d + 1
#         return d

#     # ---------------- chains: a child PO and the main PO(s) it feeds belong together ----------------
#     parent = {p["po"]: p["po"] for p in pos}

#     def find(x: str) -> str:
#         while parent[x] != x:
#             parent[x] = parent[parent[x]]
#             x = parent[x]
#         return x

#     for m_po, c_pos in depends_on.items():
#         for c_po in c_pos:
#             if c_po in parent and m_po in parent:
#                 parent[find(c_po)] = find(m_po)
#     chain_first: Dict[str, int] = {}
#     for p in pos:
#         r = find(p["po"])
#         chain_first[r] = min(chain_first.get(r, p["idx"]), p["idx"])
#     chain_key = {p["po"]: chain_first[find(p["po"])] for p in pos}        # chain = its first PO (load order)
#     chain_no = {k: i + 1 for i, k in enumerate(sorted(set(chain_key.values())))}

#     # ---------------- schedule (finite capacity, machines shared, down-time skipped) ----------------
#     default_cap = min(DEFAULT_SHIFTS * DEFAULT_HOURS_PER_SHIFT * 60.0, day_cap)
#     busy: Dict[str, List[Tuple[datetime, datetime, str]]] = defaultdict(list)   # resource -> runs already booked (first-fit gaps)
#     usage: Dict[str, Dict[date, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
#     segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
#     machine_segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
#     runs: Dict[Tuple[str, str], List[datetime]] = {}
#     run_list: List[Dict[str, Any]] = []
#     po_ready: Dict[str, datetime] = {}
#     po_span: Dict[str, List[datetime]] = {}
#     route: Dict[str, List[str]] = defaultdict(list)
#     delayed_by_downtime: Dict[str, set] = defaultdict(set)

#     # placement order: a main PO is placed immediately after the last child PO that feeds it (child, main, child, main ...)
#     # - NOT "all children first", which pushed every main behind all the child work on shared machines.
#     by_po = {p["po"]: p for p in pos}
#     kids = {m: [c for c in cs if c in by_po] for m, cs in depends_on.items()}
#     feeds: Dict[str, List[str]] = defaultdict(list)
#     for m_po, cs in kids.items():
#         for c_po in cs:
#             feeds[c_po].append(m_po)
#     order: List[Dict[str, Any]] = []
#     placed_po: set = set()

#     def emit(p: Dict[str, Any]) -> None:
#         if p["po"] in placed_po:
#             return
#         placed_po.add(p["po"])
#         for c_po in kids.get(p["po"], []):
#             emit(by_po[c_po])
#         order.append(p)
#         for m_po in feeds.get(p["po"], []):
#             if m_po not in placed_po and all(c in placed_po for c in kids[m_po]):
#                 emit(by_po[m_po])

#     for p in sorted(pos, key=lambda x: x["idx"]):
#         emit(p)
#     handoff: Dict[str, Dict[str, Any]] = {}

#     open_batches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # station key -> batches already booked (for co-loading)

#     def book(st: Station, ready: datetime, minutes: float, one_day: bool = False, dry=None):
#         """First fit on every machine (option) of the station: the earliest start >= ready where the whole run clears the runs
#         already booked there and the machine's down-time. The machine that FINISHES first wins.
#         one_day = the run must sit inside one free stretch of one working day (SMT LINE, an oven batch).
#         dry = bookings of a trial run (estimates) - looked at, but never kept.
#         Returns (mi, o, start, end, end_day, pieces, fits_in_one_day, blocked_by)."""
#         best = None
#         for mi, o in enumerate(st.options):
#             booked = sorted(iv for r in o["resources"] for iv in busy[r] + (dry.get(r, []) if dry is not None else []))
#             s0, first_block = ready, None
#             for _ in range(100000):
#                 if one_day:
#                     s, e, eday, segs, same = cal.place_within_day(s0, minutes, st.cap_min, o["blocks"])
#                 else:
#                     s, e, eday, segs = cal.consume(s0, minutes, st.cap_min, o["blocks"])
#                     same = True
#                 clash = next((iv for iv in booked if iv[0] < e and iv[1] > s), None)
#                 if clash is None:
#                     break
#                 if first_block is None:
#                     first_block = clash[2]
#                 s0 = clash[1]
#             else:
#                 raise PoGanttError(500, f"No free slot found on {o['name'] or st.name}")
#             if best is None or e < best[3]:
#                 best = (mi, o, s, e, eday, segs, same, first_block)
#         return best

#     def reserve(o: Dict[str, Any], s: datetime, e: datetime, label: str, dry=None) -> None:
#         for r in o["resources"]:
#             (busy if dry is None else dry).setdefault(r, []).append((s, e, label))

#     def add_segment(p: Dict[str, Any], st: Station, row_id: str, mi: int, o: Dict[str, Any], piece, s: datetime, e: datetime,
#                     phys: List[Tuple[str, str]], extra: Dict[str, Any]) -> None:
#         """One bar of the Gantt (one PO, one day, one machine / step) + the same bar on each machine row."""
#         d, a, b, m = piece
#         seg = {
#             "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"], "quantity": p["qty"],
#             "machine": o["name"], "machine_no": mi, "machines": [mid for mid, _ in phys], "operation": st.name,
#             "row_id": row_id, "date": d.isoformat(), "start": _iso(a), "end": _iso(b), "minutes": round(m, 1),
#             "run_start": _iso(s), "run_end": _iso(e),
#         }
#         seg.update(extra)
#         segments[st.key].append(seg)
#         for mid, nm in phys:
#             machine_segments[mid].append({**seg, "machine": mid, "step": nm})
#         usage[st.key][d][p["label"]] += m

#     def split_steps(segs, step_mins: List[float]):
#         """Cut a line run [(day, a, b, minutes)] into its steps, one after the other -> [(step_index, (day, a, b, minutes))]."""
#         out, i, left, n = [], 0, step_mins[0], len(step_mins)
#         for d, a, b, m in segs:
#             while m > 1e-9:
#                 while left <= 1e-9 and i < n - 1:          # a step with no time: go to the next one
#                     i += 1
#                     left = step_mins[i]
#                 use = m if i == n - 1 else min(m, left)    # the last step takes whatever is left (rounding)
#                 out.append((i, (d, a, a + timedelta(minutes=use), use)))
#                 a, m, left = a + timedelta(minutes=use), m - use, left - use
#         return out

#     def place_batches(p: Dict[str, Any], st: Station, parts, ready: datetime, row_id: str, dry=None):
#         """Batch process: batch_size PCBs go in together and come out together (one bar per batch).
#         70 PCBs / batch 30 -> 30 + 30 + 10. Batches of one PO run side by side on free ovens.
#         A batch of the SAME part that still has room, is not started before this PO is ready and does not finish later
#         than a new batch would, takes the PCBs instead (co-loading). A trial run (dry) never co-loads.
#         Returns (start, end, end_day, machine names, blocked_by)."""
#         size = batch_size_for(p["part"], st.step_ids[0])
#         per_batch = parts[0][1]                                   # minutes for one batch (time of a batch, not per PCB)
#         left, mine, blocked_by = p["qty"], [], None
#         while left > 0:
#             mins = per_batch + (st.setup if not mine else 0.0)
#             mi, o, s, e, eday, segs, same, blocked = book(st, ready, mins, one_day=True, dry=dry)
#             join = None
#             if dry is None:
#                 join = min((b for b in open_batches[st.key]
#                             if b["part"] == p["part"] and b["room"] > 0 and b["start"] >= ready and b["end"] <= e),
#                            key=lambda b: b["start"], default=None)
#             if join:
#                 take = min(left, join["room"])
#                 join["room"] -= take
#                 mi, o, s, e, eday, segs = join["mi"], join["o"], join["start"], join["end"], join["eday"], join["segs"]
#                 together = join["together"]
#             else:
#                 take = min(left, size)
#                 reserve(o, s, e, p["label"], dry)
#                 together = []
#                 if dry is None:
#                     open_batches[st.key].append({"part": p["part"], "room": size - take, "start": s, "end": e, "eday": eday,
#                                                  "mi": mi, "o": o, "segs": segs, "together": together})
#                     if blocked_by is None:
#                         blocked_by = blocked
#                     if o["blocks"] and any(a < e and b > ready for a, b in o["blocks"]):
#                         delayed_by_downtime[p["po"]].add(st.name)
#                     if not same:
#                         warnings.append(f"PO {p['po']} ({p['label']}): one {st.name} batch needs {mins / 60:.1f} h, more than "
#                                         f"one working day ({st.cap_min / 60:g} h) - the batch is spread over several days")
#             together.append({"label": p["label"], "po": p["po"], "qty": take})   # every PO inside this batch (shared list)
#             left -= take
#             mine.append((mi, o, s, e, eday, segs, take, mins, together))
#         if dry is None:
#             for k, (mi, o, s, e, eday, segs, take, mins, together) in enumerate(mine, start=1):
#                 info = {"no": k, "count": len(mine), "qty": take, "size": size, "minutes": round(mins, 1),
#                         "start": _iso(s), "end": _iso(e), "together": together}
#                 for piece in segs:
#                     add_segment(p, st, row_id, mi, o, piece, s, e, o["phys"], {"batch": info})
#         s_all, e_all = min(b[2] for b in mine), max(b[3] for b in mine)
#         last = max(mine, key=lambda b: b[3])
#         names = list(dict.fromkeys(b[1]["name"] for b in mine if b[1]["name"]))
#         return s_all, e_all, last[4], ", ".join(names), blocked_by

#     def run_po(p: Dict[str, Any], ready: datetime, dry=None) -> Tuple[Optional[datetime], datetime]:
#         """Place a PO through its operations (p["ops"]), one after the other, from `ready`.
#         dry = None: book it into the schedule. dry = {}: a trial run on top of the schedule (estimate only, nothing kept).
#         Returns (start of its first operation, when the PO is ready for the next step / the main PO)."""
#         ready0, first_start = ready, None
#         for seq, op in enumerate(p["ops"], start=1):
#             st = stations[op["key"]]
#             minutes, parts = op_minutes_and_parts(p, op, st)
#             row_id = f"{p['role']}:{st.key}"

#             if st.mode == "BATCH":
#                 # -------- batch process: one bar per batch --------
#                 s, e, eday, machine_text, blocked_by = place_batches(p, st, parts, ready, row_id, dry)
#                 phys_ids = []
#             else:
#                 # -------- normal process / SMT LINE: the whole PO in one run --------
#                 mi, o, s, e, eday, segs, same, blocked_by = book(st, ready, minutes, one_day=(st.kind == "LINE"), dry=dry)
#                 reserve(o, s, e, p["label"], dry)
#                 machine_text = o["name"]
#                 phys_ids = [m for m, _ in o["phys"]]
#                 if dry is None:
#                     if o["blocks"] and any(a < e and b > ready for a, b in o["blocks"]):
#                         delayed_by_downtime[p["po"]].add(st.name)
#                     if not same:
#                         warnings.append(f"PO {p['po']} ({p['label']}): {st.name} needs {minutes / 60:.1f} h, more than one "
#                                         f"working day ({st.cap_min / 60:g} h) - the run is spread over several days")
#                     if st.kind == "LINE":
#                         # the line steps run ONE AFTER THE OTHER (step 1 for the whole PO, then step 2 ...), all inside the day
#                         step_mins = [parts[i][0] + (st.setup if i == 0 else 0.0) for i in range(len(parts))]
#                         pieces = split_steps(segs, step_mins)
#                         for i, name in enumerate(st.steps):
#                             mine = [pc for k, pc in pieces if k == i]
#                             if not mine:
#                                 continue
#                             step_phys = [(mid, nm) for mid, nm in o["phys"] if nm == name]
#                             extra = {"step": name, "step_no": i + 1, "step_count": len(st.steps),
#                                      "step_start": _iso(mine[0][1]), "step_end": _iso(mine[-1][2]),
#                                      "step_minutes": round(step_mins[i], 1)}
#                             if step_phys:
#                                 extra["machine"] = step_phys[0][0]
#                             for piece in mine:
#                                 add_segment(p, st, row_id, mi, o, piece, s, e, step_phys, extra)
#                     else:
#                         for piece in segs:
#                             add_segment(p, st, row_id, mi, o, piece, s, e, o["phys"], {})

#             first_start = s if first_start is None else first_start
#             if dry is None:
#                 if seq == 1 and any(c in po_ready for c in depends_on.get(p["po"], [])):   # main PO: how soon after its child?
#                     wait_h = max((s - ready0).total_seconds() / 3600.0, 0.0)
#                     handoff[p["po"]] = {"child_ready": _iso(ready0), "main_start": _iso(s), "wait_hours": round(wait_h, 1),
#                                         "station": st.name, "machine": machine_text, "blocked_by": blocked_by}
#                     if wait_h > HANDOFF_WARN_HOURS:
#                         warnings.append(f"PO {p['po']} ({p['label']}) starts {wait_h / 24:.1f} days after its child PO "
#                                         f"finished: {st.name} is busy" + (f" with PO {blocked_by}" if blocked_by else ""))
#                 span = runs.setdefault((st.key, p["label"]), [s, e])
#                 span[0], span[1] = min(span[0], s), max(span[1], e)
#                 ps = po_span.setdefault(p["po"], [s, e])
#                 ps[0], ps[1] = min(ps[0], s), max(ps[1], e)
#                 if row_id not in route[p["po"]]:
#                     route[p["po"]].append(row_id)
#                 run_list.append({"seq": seq, "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"],
#                                  "quantity": p["qty"], "row_id": row_id, "station": st.name, "kind": st.kind,
#                                  "flow_step_ids": st.step_ids, "machine": machine_text, "machines": phys_ids,
#                                  "start": _iso(s), "end": _iso(e), "minutes": round(minutes, 1)})

#             ready = e                                            # when the PO may enter the next process
#             if st.next_day_release:
#                 ready = datetime.combine(cal.first_working_day(eday + timedelta(days=1)), time.min) + timedelta(hours=shift_start)
#             if st.cooldown > 0:
#                 if st.cd_working_only:
#                     ready = cal.consume(ready, st.cooldown, default_cap)[1]
#                 else:
#                     ready = ready + timedelta(minutes=st.cooldown)
#         return first_start, ready

#     def outside_child(l: Dict[str, Any], qty: int, from_step: bool) -> Dict[str, Any]:
#         """A child PO that is not in this schedule, as a PO for a trial run: its whole flow, or (in process) the rest of
#         its flow from the earliest step its PCBs are at."""
#         ops = ops_for(l["child_part"])
#         if from_step and l["steps"]:
#             at = [i for i, op in enumerate(ops) if any(m.flow_step_id in l["steps"] for m in op["steps"])]
#             ops = ops[min(at):] if at else ops
#         return {"po": l["child_po"], "label": l["child_po"], "part": l["child_part"], "qty": qty, "role": "CHILD", "ops": ops}

#     child_notes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # main po -> what the child outside the plan means
#     forced: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []          # (main PO, child link) scheduled without waiting

#     for p in order:
#         waits = [po_ready[c] for c in depends_on.get(p["po"], []) if c in po_ready]
#         for l in outside_links.get(p["po"], []):
#             note = {"child_po": l["child_po"], "child_part": l["child_part"], "pcbs": l["pcbs"], "done": l["done"],
#                     "in_progress": l["in_progress"], "not_assigned": l["not_assigned"], "in_plan": False}
#             if l["in_progress"]:
#                 # child PCBs are on the floor: the main waits for the rest of the child flow (estimate, nothing booked)
#                 trial = outside_child(l, l["in_progress"], from_step=True)
#                 if trial["ops"]:
#                     _, est = run_po(trial, max(now, start_dt), dry={})
#                     waits.append(est)
#                     note["child_ready_estimate"] = _iso(est)
#                     warnings.append(f"PO {p['po']} ({p['label']}): {l['in_progress']} child PCB(s) of PO {l['child_po']} are "
#                                     f"still in process - estimated done {est:%d-%m-%Y %H:%M}, the main PO waits for that")
#             if l["not_assigned"]:
#                 note["forced"] = True
#                 forced.append((p, l))
#             child_notes[p["po"]].append(note)
#         _, po_ready[p["po"]] = run_po(p, max([start_dt] + waits))

#     # child not assigned -> main was scheduled without waiting. What if the child is assigned on the first working day?
#     for p, l in forced:
#         trial = outside_child(l, l["not_assigned"], from_step=False)
#         note = next(n for n in child_notes[p["po"]] if n["child_po"] == l["child_po"])
#         main_start = po_span[p["po"]][0]
#         if not trial["ops"]:
#             warnings.append(f"PO {p['po']} ({p['label']}): child PO {l['child_po']} is not assigned yet and its part "
#                             f"{l['child_part']} has no flow - main PO scheduled without waiting for it (forced)")
#             continue
#         c_start, c_end = run_po(trial, start_dt, dry={})
#         note.update({"assign_on": _iso(c_start), "child_done": _iso(c_end), "main_can_start": _iso(c_end),
#                      "main_planned_start": _iso(main_start)})
#         warnings.append(
#             f"PO {p['po']} ({p['label']}): child PO {l['child_po']} ({l['not_assigned']} PCB(s)) is not assigned yet - the "
#             f"main PO is scheduled without waiting for it (forced, from {main_start:%d-%m-%Y %H:%M}). If child PO "
#             f"{l['child_po']} is assigned on {c_start:%d-%m-%Y}, it is done by {c_end:%d-%m-%Y %H:%M} and PO {p['po']} "
#             f"can start from {c_end:%d-%m-%Y %H:%M}"
#             + (" - until then its PCBs cannot be assigned (the child must be complete)." if c_end > main_start else "."))

#     for part, names in missing_time.items():
#         uniq = list(dict.fromkeys(names))
#         warnings.append(f"Part {part}: no process time for {len(uniq)} step(s) "
#                         f"[{', '.join(uniq[:6])}{'...' if len(uniq) > 6 else ''}] - {FALLBACK_MINUTES:g} min used")
#     if delayed_by_downtime:
#         warnings.append(f"{len(delayed_by_downtime)} PO(s) were moved around machine breakdowns / maintenance / "
#                         f"consumable shortages")

#     # ---------------- days ----------------
#     used_days = [d for per_day in usage.values() for d in per_day]
#     last_day = max(used_days + [start_day])
#     days, day_no, working_nos = [], {}, 0
#     d = start_day
#     while d <= last_day:
#         if cal.factor(d) > 0:
#             working_nos += 1
#             day_no[d] = working_nos
#             days.append({"working_day_no": working_nos, "date": d.isoformat(), "weekday": d.strftime("%a"),
#                          "is_holiday": False, "off_reason": None})
#         elif show_holidays:
#             days.append({"working_day_no": None, "date": d.isoformat(), "weekday": d.strftime("%a"),
#                          "is_holiday": True, "off_reason": cal.off_reason(d)})
#         d += timedelta(days=1)

#     # ---------------- rows: CHILD section first, then MAIN; each in flow order ----------------
#     def part_sort(pn: str):
#         prod = products.get(pn)
#         return (_key(prod.product_type_name) if prod else "", pn)

#     part_order = sorted({p["part"] for p in pos}, key=part_sort)
#     section_rows: Dict[str, List[str]] = {r: [] for r in ROLES}
#     parts_by_row: Dict[Tuple[str, str], List[str]] = defaultdict(list)
#     for part in part_order:
#         role = role_of(part)
#         lst, at = section_rows[role], -1
#         for op in ops_for(part):                              # merge the flows of several parts in one section
#             if op["key"] in lst:
#                 at = lst.index(op["key"])
#             else:
#                 at += 1
#                 lst.insert(at, op["key"])
#             if part not in parts_by_row[(role, op["key"])]:
#                 parts_by_row[(role, op["key"])].append(part)
#     roles_of_station: Dict[str, set] = defaultdict(set)
#     for role, keys in section_rows.items():
#         for k in keys:
#             roles_of_station[k].add(role)

#     def order_labels(labels) -> List[str]:
#         return sorted(labels, key=lambda x: label_idx.get(x, 0))

#     def cells_for(key: str, role: str) -> List[Dict[str, Any]]:
#         s, out = stations[key], []
#         for dd, no in day_no.items():
#             u = usage.get(key, {}).get(dd)
#             if not u:
#                 continue
#             labels = [lb for lb in u if label_role.get(lb) == role]
#             if not labels:
#                 continue
#             out.append({"working_day_no": no, "date": dd.isoformat(), "pos": order_labels(labels),
#                         "color": ORANGE if len(labels) >= 2 else BLUE,
#                         "minutes_used": round(sum(u[lb] for lb in labels), 1),
#                         "station_minutes_used": round(sum(u.values()), 1),
#                         "capacity_minutes": round(len(s.options) * s.cap_min * cal.factor(dd), 1)})
#         return out

#     def runs_for(key: str, role: str) -> List[Dict[str, str]]:
#         out = [(lb, v) for (k, lb), v in runs.items() if k == key and label_role.get(lb) == role]
#         return [{"label": lb, "start": _iso(v[0]), "end": _iso(v[1])}
#                 for lb, v in sorted(out, key=lambda kv: (kv[1][0], label_idx.get(kv[0], 0)))]

#     def station_downtime(s: Station) -> List[Dict[str, Any]]:
#         step_of = {m: nm for m, nm in s.real_machines}                 # SMT LINE: which step the machine belongs to
#         evs = [_dt_json({**e, "machine_name": machine_info.get(mid, {}).get("name", mid),
#                          "step": step_of[mid] if s.kind == "LINE" else None})
#                for mid in dict.fromkeys(m for m, _ in s.real_machines) for e in downtime.get(mid, [])]
#         sname = dict(zip(s.step_ids, s.steps)) if s.kind == "LINE" else {}
#         evs += [_dt_json({**e, "process": s.name, "step": sname.get(e["stage_id"])}) for e in s.material]
#         return sorted(evs, key=lambda e: e["start"])

#     rows: List[Dict[str, Any]] = []
#     for role in ROLES:
#         for key in section_rows[role]:
#             s = stations[key]
#             parts = parts_by_row[(role, key)]
#             real = list(dict.fromkeys(m for m, _ in s.real_machines))
#             rows.append({
#                 "row_id": f"{role}:{key}", "station_id": key, "name": s.name, "kind": s.kind, "section": role,
#                 "role": role, "part_number": parts[0], "part_numbers": parts,
#                 "flow_step_ids": s.step_ids, "steps": s.steps,
#                 "shifts": s.shifts, "mins_per_shift": int(s.hps * 60), "machines": len(s.options),
#                 "machine_names": s.machines, "has_machine": bool(real), "real_machines": real,
#                 "real_machine_names": [machine_info[m]["name"] for m in real],
#                 "operators_per_shift": s.operators, "process_mode": s.mode, "is_batch": s.mode == "BATCH",
#                 "day_end_hour": round(shift_start + s.cap_min / 60.0, 2),
#                 "shared_with": [r for r in ROLES if r != role and r in roles_of_station[key]],
#                 "cells": cells_for(key, role), "po_runs": runs_for(key, role),
#                 "segments": [sg for sg in segments.get(key, []) if sg["role"] == role],
#                 "downtime": station_downtime(s),
#             })

#     # ---------------- machine rows (PO on Machines), grouped by process in flow order ----------------
#     machine_rows: List[Dict[str, Any]] = []
#     placed: Dict[str, Dict[str, Any]] = {}
#     for row in rows:
#         s = stations[row["station_id"]]
#         for mid, step in s.real_machines:
#             if mid in placed:
#                 if s.name not in placed[mid]["processes"]:
#                     placed[mid]["processes"].append(s.name)
#                 if row["role"] not in placed[mid]["roles"]:
#                     placed[mid]["roles"].append(row["role"])
#                 continue
#             info = machine_info.get(mid, {"name": mid})
#             segs = sorted(machine_segments.get(mid, []), key=lambda x: x["start"])
#             mr = {
#                 "row_id": f"M:{mid}", "machine_id": mid, "name": info.get("name") or mid, "eqpt_no": info.get("eqpt_no"),
#                 "make": info.get("make"), "model": info.get("model"), "workcenter": info.get("workcenter"),
#                 "group": s.key, "group_name": s.name, "group_kind": s.kind, "step": step if s.kind == "LINE" else None,
#                 "processes": [s.name], "roles": [row["role"]], "shifts": s.shifts,
#                 "day_end_hour": round(shift_start + s.cap_min / 60.0, 2), "is_batch": s.mode == "BATCH",
#                 "segments": segs, "downtime": [_dt_json(e) for e in downtime.get(mid, [])],
#                 # a batch shared by 2 POs is 2 bars at the same time - count the oven time once
#                 "busy_minutes": round(sum({(x["start"], x["end"]): x["minutes"] for x in segs}.values()), 1),
#             }
#             placed[mid] = mr
#             machine_rows.append(mr)
#     manual_processes = [r["name"] for r in rows if not r["has_machine"]]
#     if manual_processes:
#         warnings.append("No machine mapped in equipment_details for: " + ", ".join(
#             dict.fromkeys(f"{r['name']} (step {', '.join(str(x) for x in r['flow_step_ids'])})" for r in rows if not r["has_machine"])))

#     for s in stations.values():
#         for e in s.material:
#             warnings.append(f"Consumable not available - {s.name} does not run from {e['start']:%d-%m-%Y %H:%M} to "
#                             f"{e['end']:%d-%m-%Y %H:%M}: {e['note']}")

#     # most important first: forced main POs, consumable shortages, children still in process
#     first = ("is not assigned yet", "Consumable not available", "still in process", "Breakdown repair waits")
#     warnings.sort(key=lambda w: next((i for i, k in enumerate(first) if k in w), len(first)))

#     all_down = [_dt_json({**e, "machine_name": machine_info.get(mid, {}).get("name", mid)})
#                 for mid in placed for e in downtime.get(mid, [])]

#     day_end = shift_start + max((s.cap_min for s in stations.values()), default=default_cap) / 60.0
#     line_text = "; ".join(f"{g} = {', '.join(n)}" for g, n in LINE_GROUPS.items())
#     assumptions = [
#         "Child / main comes from product_type_master (sub product type); a main part is fed by the child part of the same product type.",
#         "Each part follows its flow from product_workflow_mapping (step sequence). Linked child / main POs are scheduled as one chain; "
#         "a main PO starts after the child PO(s) that feed it are finished.",
#         "Child -> main link by SERIAL number first (PcbData.serialNo, the same check as PCB assignment): the main PCB needs the "
#         "child PCB with the same serial. Main POs without a serial match use first come, first served by quantity.",
#         "Child PO not in this schedule: PCBs done -> no wait; in process (pcb_assignment.current_step_id) -> the main waits for "
#         "the estimated end of the rest of the child flow; NOT assigned -> the main is scheduled without waiting (forced) and "
#         "the warning says on which day the child must be assigned and from when the main can really start.",
#         "Unit of work is the whole PO quantity; a PO moves through its processes as a block.",
#         f"Line processes run inside one working day ({line_text}). The steps run one after the other "
#         "(step 1 for the whole PO, then step 2 ...); line time = sum of the step times.",
#         "Machines come from equipment_details; the same machine serving several processes is shared between them.",
#         "Machine breakdowns (machine_breakdown_logs: until ready date, else + downtime hours, else open = "
#         f"{OPEN_BREAKDOWN_HOURS:g} h from now) and pending preventive maintenance (maintenance_schedules: the whole day) "
#         "block the machine.",
#         "Spares (inventorty_spares): an open breakdown whose machine has a spare out of stock lasts at least the spare's "
#         f"procurement lead time (default {DEFAULT_SPARE_LEAD_DAYS} d). A running machine is not blocked by a missing spare (warning only).",
#         "Consumables (consumables, by process): out of stock or past shelf life -> the process (all its machines, or the "
#         f"process without machine) is blocked for {CONSUMABLE_RESTOCK_DAYS} days; stock that expires blocks it from the day "
#         "after expiry. Stock is checked as available yes / no (the table has no use per PCB). Low stock = warning.",
#         f"Shifts per process come from stage_capacity (default {DEFAULT_SHIFTS} x {DEFAULT_HOURS_PER_SHIFT:g} h); "
#         f"the working day runs {_hm(shift_start)} - {_hm(DAY_END_HOUR)} at most.",
#         "Off days: Sundays, 1st and 3rd Saturdays, public holidays and calendar 'Holiday' exceptions; "
#         "'Working' reopens a day, 'Half-Day' halves it.",
#         f"Time per unit = {'actual' if time_source == 'actual' else 'SAP'} time (fallback to the other, routing, stage_capacity) "
#         "+ machine hours of part_process_time.",
#         "Batch processes (process_type.process_type_batch): batch size PCBs go in together and come out together - "
#         "70 PCBs / batch 30 = 3 batches (30, 30, 10), each one bar, run on free machines side by side. "
#         "A batch of the same part with room left takes PCBs of the next PO when that does not delay it. "
#         "Batch size = part_process_time.batch_size, else stage_schedule_config.batch_size, else 30.",
#         f"Plant filter: only POs, machines and process times of plant {plant or '(all)'}.",
#         "Operators per shift is informational; it does not limit the schedule.",
#     ]
#     return {
#         "meta": {
#             "plant": plant, "number_of_pos": len(pos), "start_date": start_day.isoformat(), "finish_date": last_day.isoformat(),
#             "working_days": working_nos, "time_source": time_source, "label_mode": label_mode,
#             "generated_at": _iso(now),
#             "params": {"plant": plant, "production_order": [p["po"] for p in pos] if explicit else None,
#                        "start_date": start_date.isoformat() if start_date else None, "time_source": time_source,
#                        "label_mode": label_mode, "shift_start": shift_start},
#             "day_window": {"start_hour": shift_start, "end_hour": round(day_end, 2)},
#             "line_groups": {g: list(n) for g, n in LINE_GROUPS.items()},
#             "machines_down": len({e["machine"] for e in all_down}),
#             "downtime_events": len(all_down),
#             "manual_processes": manual_processes,
#             "material_shortages": [_dt_json({**e, "process": s.name}) for s in stations.values() for e in s.material],
#             "pos": [{"label": p["label"], "production_order": p["po"], "part_number": p["part"], "role": p["role"],
#                      "quantity": p["qty"], "depends_on": depends_on.get(p["po"], []), "handoff": handoff.get(p["po"]), "route": route[p["po"]],
#                      "chain": chain_no[chain_key[p["po"]]],
#                      "link_by": link_by.get(p["po"]),                         # serial | quantity | None (not a main PO)
#                      "child_outside": child_notes.get(p["po"], []),           # child POs not in this schedule
#                      "forced": any(n.get("forced") for n in child_notes.get(p["po"], [])),
#                      "moved_by_downtime": sorted(delayed_by_downtime.get(p["po"], [])),
#                      "start": _iso(po_span[p["po"]][0]), "end": _iso(po_span[p["po"]][1])} for p in pos],
#         },
#         "days": days, "stations": rows, "machines": machine_rows, "downtime": all_down, "runs": run_list,
#         "warnings": warnings, "assumptions": assumptions,
#     }


# # --------------------------------------------------------------------------------------
# # Saved plans
# # --------------------------------------------------------------------------------------
# class PlanSave(BaseModel):
#     name: Optional[str] = None
#     remarks: Optional[str] = None
#     set_baseline: bool = True
#     created_by: Optional[str] = None
#     plant: Optional[str] = None
#     production_order: Optional[List[str]] = None
#     start_date: Optional[date] = None
#     time_source: str = "actual"
#     label_mode: str = "po"
#     shift_start: float = DEFAULT_SHIFT_START


# def _plan_header(p: SchedulePlan) -> Dict[str, Any]:
#     return {"id": p.id, "name": p.name, "plant": p.plant_code, "is_baseline": bool(p.is_baseline), "status": p.status,
#             "time_source": p.time_source, "label_mode": p.label_mode,
#             "start_date": p.start_date.isoformat() if p.start_date else None,
#             "finish_date": p.finish_date.isoformat() if p.finish_date else None,
#             "number_of_pos": p.number_of_pos, "working_days": p.working_days, "remarks": p.remarks,
#             "created_by": p.created_by, "created_at": _iso(p.created_at), "params": p.params}


# def save_plan(db: Session, body: PlanSave) -> Dict[str, Any]:
#     """Build the schedule again with the same inputs (so what is stored is consistent) and store it."""
#     ensure_plan_tables(db.get_bind())
#     result = build_po_gantt(db, body.production_order, body.plant, body.start_date, body.time_source,
#                             body.label_mode, True, body.shift_start)
#     meta = result["meta"]
#     now = datetime.now()
#     if body.set_baseline:
#         q = db.query(SchedulePlan).filter(SchedulePlan.is_baseline.is_(True))
#         q = q.filter(SchedulePlan.plant_code == body.plant) if body.plant else q.filter(SchedulePlan.plant_code.is_(None))
#         q.update({SchedulePlan.is_baseline: False}, synchronize_session=False)
#     plan = SchedulePlan(
#         name=(body.name or "").strip() or f"Plan {body.plant or 'all'} · {now:%d %b %Y %H:%M}",
#         plant_code=body.plant, is_baseline=bool(body.set_baseline), status="SAVED",
#         time_source=body.time_source, label_mode=body.label_mode,
#         start_date=date.fromisoformat(meta["start_date"]), finish_date=date.fromisoformat(meta["finish_date"]),
#         number_of_pos=meta["number_of_pos"], working_days=meta["working_days"], params=meta["params"],
#         snapshot=result, remarks=body.remarks, created_by=body.created_by, created_at=now,
#     )
#     db.add(plan)
#     db.flush()
#     db.add_all([SchedulePlanItem(
#         plan_id=plan.id, seq=r["seq"], production_order=r["po"], part_number=r["part"], label=r["label"],
#         role=r["role"], quantity=r["quantity"], row_id=r["row_id"], station_name=r["station"], station_kind=r["kind"],
#         flow_step_ids=r["flow_step_ids"], machine=r["machine"], machines=r["machines"],
#         planned_start=datetime.strptime(r["start"], ISO), planned_end=datetime.strptime(r["end"], ISO),
#         run_minutes=r["minutes"]) for r in result["runs"]])
#     db.commit()
#     return {"plan": _plan_header(plan), "items": len(result["runs"])}


# def list_plans(db: Session, plant: Optional[str]) -> Dict[str, Any]:
#     ensure_plan_tables(db.get_bind())
#     q = db.query(SchedulePlan.id, SchedulePlan.name, SchedulePlan.plant_code, SchedulePlan.is_baseline,
#                  SchedulePlan.status, SchedulePlan.start_date, SchedulePlan.finish_date, SchedulePlan.number_of_pos,
#                  SchedulePlan.working_days, SchedulePlan.created_by, SchedulePlan.created_at, SchedulePlan.remarks,
#                  SchedulePlan.time_source)
#     if plant:
#         q = q.filter(SchedulePlan.plant_code == plant)
#     out = []
#     for r in q.order_by(SchedulePlan.created_at.desc(), SchedulePlan.id.desc()).all():
#         out.append({"id": r.id, "name": r.name, "plant": r.plant_code, "is_baseline": bool(r.is_baseline),
#                     "status": r.status, "start_date": r.start_date.isoformat() if r.start_date else None,
#                     "finish_date": r.finish_date.isoformat() if r.finish_date else None,
#                     "number_of_pos": r.number_of_pos, "working_days": r.working_days, "created_by": r.created_by,
#                     "created_at": _iso(r.created_at), "remarks": r.remarks, "time_source": r.time_source})
#     return {"plans": out}


# def _get_plan(db: Session, plan_id: int) -> SchedulePlan:
#     ensure_plan_tables(db.get_bind())
#     p = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
#     if not p:
#         raise PoGanttError(404, f"Saved plan {plan_id} not found")
#     return p


# def set_baseline(db: Session, plan_id: int) -> Dict[str, Any]:
#     p = _get_plan(db, plan_id)
#     q = db.query(SchedulePlan).filter(SchedulePlan.is_baseline.is_(True), SchedulePlan.id != p.id)
#     q = q.filter(SchedulePlan.plant_code == p.plant_code) if p.plant_code else q.filter(SchedulePlan.plant_code.is_(None))
#     q.update({SchedulePlan.is_baseline: False}, synchronize_session=False)
#     p.is_baseline = True
#     db.commit()
#     return {"plan": _plan_header(p)}


# def delete_plan(db: Session, plan_id: int) -> Dict[str, Any]:
#     p = _get_plan(db, plan_id)
#     db.query(SchedulePlanItem).filter(SchedulePlanItem.plan_id == p.id).delete(synchronize_session=False)
#     db.delete(p)
#     db.commit()
#     return {"deleted": plan_id}


# # --------------------------------------------------------------------------------------
# # Actual (what the operators did) and Planned vs Actual
# # --------------------------------------------------------------------------------------
# _MACHINE_KEYS = ("machine_id", "machineId", "machine", "machine_name", "equipment", "eqpt_no", "equipment_id")


# def load_actuals(db: Session, po_numbers: List[str]):
#     """Returns (pcb_qty {po: total pieces}, agg {(po, flow_step_id): {...}}) from operator_log, then pcb_process_log
#     (via pcb_assignment) for PCB x step pairs operator_log does not have."""
#     pos = sorted({_norm(p) for p in po_numbers if p})
#     pcbs: Dict[str, Tuple[str, int]] = {}
#     serial_to_pcb: Dict[str, str] = {}
#     pcb_qty: Dict[str, int] = defaultdict(int)
#     norm_col = func.ltrim(func.trim(PcbData.productionOrder), "0")
#     for chunk in _chunks(pos):
#         for pcb, serial, po, qty in db.query(PcbData.PCBserialNoPartNumber, PcbData.serialNo, PcbData.productionOrder,
#                                              PcbData.quantity).filter(norm_col.in_(chunk)).all():
#             q = qty if qty and qty > 0 else 1
#             n = _norm(po)
#             pcbs[pcb] = (n, q)
#             pcb_qty[n] += q
#             if serial:
#                 serial_to_pcb.setdefault(serial, pcb)

#     events: Dict[Tuple[str, int], Dict[str, Any]] = {}
#     keys = list(pcbs)
#     for chunk in _chunks(keys):
#         for r in db.query(OperatorLog).filter(OperatorLog.PCBserialNoPartNumber.in_(chunk)).all():
#             st, en = _parse_dt(r.start_time), _parse_dt(r.end_time)
#             if not en and (r.Task_Status or "").strip().lower() in DONE_STATUSES:
#                 en = st
#             if not st and not en:
#                 continue
#             machine = None
#             if isinstance(r.log_Data, dict):
#                 machine = next((str(r.log_Data[k]) for k in _MACHINE_KEYS if r.log_Data.get(k)), None)
#             events[(r.PCBserialNoPartNumber, r.current_step_id)] = {
#                 "start": st or en, "end": en, "operator": r.operator_name or r.operator_staff_no, "machine": machine}

#     assign: Dict[int, str] = {}
#     lookup = keys + [s for s in serial_to_pcb if s not in pcbs]
#     for chunk in _chunks(lookup):
#         for aid, pid in db.query(PCBAssignment.assignment_id, PCBAssignment.assigned_pcb_id).filter(
#                 PCBAssignment.assigned_pcb_id.in_(chunk)).all():
#             pcb = pid if pid in pcbs else serial_to_pcb.get(pid)
#             if pcb:
#                 assign[aid] = pcb
#     for chunk in _chunks(list(assign)):
#         for r in db.query(PCBProcessLog).filter(PCBProcessLog.assignment_id.in_(chunk)).all():
#             k = (assign[r.assignment_id], r.flow_step_id)
#             if k in events:
#                 continue
#             st, en = _parse_dt(r.start_time), _parse_dt(r.end_time)
#             if not en and (r.process_status or "").strip().lower() in DONE_STATUSES:
#                 en = st
#             if not st and not en:
#                 continue
#             events[k] = {"start": st or en, "end": en, "operator": r.assigned_operator_staff_no, "machine": None}

#     agg: Dict[Tuple[str, int], Dict[str, Any]] = {}
#     for (pcb, sid), ev in events.items():
#         po, q = pcbs[pcb]
#         a = agg.setdefault((po, sid), {"start": None, "end": None, "done": 0, "wip": 0,
#                                        "operators": set(), "machines": set()})
#         a["start"] = min(a["start"], ev["start"]) if a["start"] else ev["start"]
#         if ev["end"]:
#             a["done"] += q
#             a["end"] = max(a["end"], ev["end"]) if a["end"] else ev["end"]
#         else:
#             a["wip"] += q
#         if ev["operator"]:
#             a["operators"].add(ev["operator"])
#         if ev["machine"]:
#             a["machines"].add(ev["machine"])
#     return pcb_qty, agg


# def _status(ps, pe, a_start, a_end, complete, now) -> Tuple[str, Optional[float]]:
#     tol = timedelta(minutes=LATE_TOLERANCE_MIN)
#     mins = lambda d: round(d.total_seconds() / 60.0, 1)
#     if complete:
#         return ("DONE_LATE" if a_end > pe + tol else "DONE_ON_TIME"), mins(a_end - pe)
#     if a_start:
#         return ("RUNNING_LATE" if now > pe + tol else "RUNNING"), (mins(now - pe) if now > pe else None)
#     if now > ps + tol:
#         return "START_OVERDUE", mins(now - ps)
#     return "UPCOMING", None


# def compare_plan(db: Session, plan_id: int, now: Optional[datetime] = None) -> Dict[str, Any]:
#     plan = _get_plan(db, plan_id)
#     snap = plan.snapshot or {}
#     now = now or datetime.now()
#     runs = snap.get("runs") or []
#     if not runs:                                             # a plan saved without runs -> rebuild from items
#         runs = [{"seq": i.seq, "label": i.label, "po": i.production_order, "part": i.part_number, "role": i.role,
#                  "quantity": i.quantity, "row_id": i.row_id, "station": i.station_name, "kind": i.station_kind,
#                  "flow_step_ids": i.flow_step_ids or [], "machine": i.machine, "machines": i.machines or [],
#                  "start": _iso(i.planned_start), "end": _iso(i.planned_end), "minutes": i.run_minutes}
#                 for i in db.query(SchedulePlanItem).filter(SchedulePlanItem.plan_id == plan.id).all()]
#     pcb_qty, agg = load_actuals(db, [r["po"] for r in runs])

#     by_row: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
#     by_po: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
#     for r in runs:
#         ps, pe = datetime.strptime(r["start"], ISO), datetime.strptime(r["end"], ISO)
#         total = pcb_qty.get(r["po"]) or r["quantity"] or 1
#         acts = [agg.get((r["po"], sid)) for sid in r["flow_step_ids"]]
#         got = [a for a in acts if a]
#         a_start = min(a["start"] for a in got) if got else None
#         done_qty = min((a["done"] if a else 0) for a in acts) if acts else 0
#         complete = bool(acts) and all(a and a["done"] >= total for a in acts)
#         a_end = max(a["end"] for a in got if a["end"]) if complete else None
#         status, var = _status(ps, pe, a_start, a_end, complete, now)
#         item = {
#             "label": r["label"], "po": r["po"], "part": r["part"], "role": r["role"], "quantity": r["quantity"],
#             "seq": r["seq"], "row_id": r["row_id"], "station": r["station"], "machine": r["machine"],
#             "planned_start": r["start"], "planned_end": r["end"], "planned_minutes": r["minutes"],
#             "actual_start": _iso(a_start), "actual_end": _iso(a_end), "actual_until": _iso(a_end or (now if a_start else None)),
#             "done_qty": done_qty, "total_qty": total,
#             "wip_qty": max((a["wip"] for a in got), default=0),
#             "start_variance_min": round((a_start - ps).total_seconds() / 60.0, 1) if a_start else None,
#             "variance_min": var, "status": status,
#             "operators": sorted({o for a in got for o in a["operators"]}),
#             "actual_machines": sorted({m for a in got for m in a["machines"]}),
#         }
#         by_row[r["row_id"]].append(item)
#         by_po[r["po"]].append(item)

#     rows = []
#     for st in snap.get("stations", []):
#         items = sorted(by_row.get(st["row_id"], []), key=lambda x: x["planned_start"])
#         row = {k: st.get(k) for k in ("row_id", "station_id", "name", "kind", "section", "role", "steps",
#                                       "part_numbers", "shifts", "has_machine", "real_machine_names",
#                                       "machines", "flow_step_ids")}
#         row["items"] = items
#         rows.append(row)

#     po_meta = {p["production_order"]: p for p in snap.get("meta", {}).get("pos", [])}
#     pos_out, kpi = [], defaultdict(int)
#     for po, items in by_po.items():
#         items.sort(key=lambda x: x["seq"])
#         ps = min(i["planned_start"] for i in items)
#         pe = max(i["planned_end"] for i in items)
#         starts = [i["actual_start"] for i in items if i["actual_start"]]
#         complete = all(i["status"].startswith("DONE") for i in items)
#         a_end = max(i["actual_end"] for i in items) if complete else None
#         status, var = _status(datetime.strptime(ps, ISO), datetime.strptime(pe, ISO),
#                               datetime.strptime(min(starts), ISO) if starts else None,
#                               datetime.strptime(a_end, ISO) if a_end else None, complete, now)
#         current = next((i for i in items if not i["status"].startswith("DONE")), None)
#         kpi[status] += 1
#         m = po_meta.get(po, {})
#         pos_out.append({
#             "po": po, "label": items[0]["label"], "part": items[0]["part"], "role": items[0]["role"],
#             "quantity": items[0]["quantity"], "planned_start": ps, "planned_end": pe,
#             "actual_start": min(starts) if starts else None, "actual_end": a_end, "status": status, "variance_min": var,
#             "current_process": current["station"] if current else None,
#             "current_status": current["status"] if current else None,
#             "processes_done": sum(1 for i in items if i["status"].startswith("DONE")), "processes": len(items),
#             "late_processes": sum(1 for i in items if i["status"] in ("DONE_LATE", "RUNNING_LATE", "START_OVERDUE")),
#             "depends_on": m.get("depends_on", []), "handoff": m.get("handoff"),
#         })
#     order = {p["production_order"]: i for i, p in enumerate(snap.get("meta", {}).get("pos", []))}
#     pos_out.sort(key=lambda p: order.get(p["po"], 10 ** 6))
#     process_kpi = defaultdict(int)
#     for items in by_row.values():
#         for i in items:
#             process_kpi[i["status"]] += 1

#     actual_ends = [i["actual_until"] for items in by_row.values() for i in items if i["actual_until"]]
#     return {
#         "plan": _plan_header(plan), "now": _iso(now),
#         "days": snap.get("days", []),
#         "meta": dict({k: snap.get("meta", {}).get(k) for k in ("day_window", "line_groups", "pos", "start_date",
#                                                                "finish_date", "working_days", "number_of_pos")},
#                      actual_last=max(actual_ends) if actual_ends else None),
#         "rows": rows, "pos": pos_out,
#         "kpis": {"pos": dict(kpi), "processes": dict(process_kpi), "total_pos": len(pos_out),
#                  "total_runs": sum(len(v) for v in by_row.values())},
#     }


# # --------------------------------------------------------------------------------------
# # Excel export
# # --------------------------------------------------------------------------------------
# def build_po_gantt_xlsx(result: Dict[str, Any]) -> bytes:
#     from openpyxl import Workbook
#     from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
#     from openpyxl.utils import get_column_letter

#     font = lambda **kw: Font(name="Arial", size=10, **kw)
#     thin = Side(style="thin", color="BFBFBF")
#     border = Border(left=thin, right=thin, top=thin, bottom=thin)
#     head = PatternFill("solid", start_color="DDE3EE")
#     off = PatternFill("solid", start_color="D9D9D9")
#     down = PatternFill("solid", start_color="F4CCCC")
#     machine_fill = PatternFill("solid", start_color="FFF4DB")
#     section_fill = {"CHILD": PatternFill("solid", start_color="D3F9D8"), "MAIN": PatternFill("solid", start_color="D0EBFF")}
#     fills = {BLUE: PatternFill("solid", start_color="9FC5E8"), ORANGE: PatternFill("solid", start_color="F6B26B")}
#     center = Alignment(horizontal="center", vertical="center", wrap_text=True)
#     days = result["days"]
#     last_col = 2 + len(days)

#     def header(ws, first_col_title):
#         ws.column_dimensions["A"].width = 36
#         ws.column_dimensions["B"].width = 12
#         for i, label in enumerate(("Working day #", "Date", "Day"), start=1):
#             c = ws.cell(row=i, column=1, value=first_col_title if i == 3 else label)
#             c.font, c.fill, c.border = font(bold=True), head, border
#             ws.cell(row=i, column=2).fill = head
#             ws.cell(row=i, column=2).border = border
#         for j, d in enumerate(days, start=3):
#             ws.column_dimensions[get_column_letter(j)].width = 11
#             dt = date.fromisoformat(d["date"])
#             vals = ("Off" if d["is_holiday"] else d["working_day_no"], dt.strftime("%d-%b"), d["weekday"])
#             for i, v in enumerate(vals, start=1):
#                 c = ws.cell(row=i, column=j, value=v)
#                 c.font, c.border, c.alignment = font(bold=(i == 1)), border, center
#                 c.fill = off if d["is_holiday"] else head
#         ws.freeze_panes = "C4"

#     def band(ws, r, text, fill):
#         for j in range(1, last_col + 1):
#             c = ws.cell(row=r, column=j)
#             c.fill, c.border = fill, border
#         ws.cell(row=r, column=1, value=text).font = font(bold=True)

#     def day_cells(ws, r, segs, downs):
#         col_of_date = {d["date"]: j for j, d in enumerate(days, start=3)}
#         for j, d in enumerate(days, start=3):
#             c = ws.cell(row=r, column=j)
#             c.border = border
#             if d["is_holiday"]:
#                 c.fill = off
#         for e in downs:
#             dd = date.fromisoformat(e["start"][:10])
#             while dd.isoformat() <= e["end"][:10]:
#                 j = col_of_date.get(dd.isoformat())
#                 if j and not (dd.isoformat() == e["end"][:10] and e["end"][11:] == "00:00:00" and e["end"][:10] != e["start"][:10]):
#                     c = ws.cell(row=r, column=j, value="DOWN")
#                     c.fill, c.font, c.alignment = down, font(bold=True, color="990000"), center
#                 dd += timedelta(days=1)
#         per_day: Dict[str, List[str]] = defaultdict(list)
#         for s in segs:
#             if s["label"] not in per_day[s["date"]]:
#                 per_day[s["date"]].append(s["label"])
#         for dstr, labels in per_day.items():
#             j = col_of_date.get(dstr)
#             if not j:
#                 continue
#             c = ws.cell(row=r, column=j, value=" ".join(labels))
#             c.fill = fills[ORANGE if len(labels) >= 2 else BLUE]
#             c.font, c.alignment = font(bold=True), center

#     wb = Workbook()
#     ws = wb.active
#     ws.title = "PO on Process"
#     header(ws, "Process")
#     r, current = 4, None
#     for st in result["stations"]:
#         if st["section"] != current:
#             current = st["section"]
#             band(ws, r, f"{current} PROCESSES", section_fill.get(current, head))
#             r += 1
#         name = st["name"] + (f"  ({len(st['steps'])} steps, same day)" if st.get("kind") == "LINE" else "")
#         a = ws.cell(row=r, column=1, value=name)
#         a.font, a.border = font(bold=True), border
#         if st.get("has_machine"):
#             a.fill = machine_fill
#         b = ws.cell(row=r, column=2, value=f"{st['shifts']} shift" + (f" · {len(st['real_machines'])} m/c" if st.get("real_machines") else ""))
#         b.font, b.border, b.alignment = font(), border, center
#         day_cells(ws, r, st["segments"], [])
#         r += 1

#     r += 1
#     ws.cell(row=r, column=1, value="Legend").font = font(bold=True)
#     for k, (txt, fill) in enumerate((("1 PO on the process", fills[BLUE]), ("2 or more POs share the process", fills[ORANGE]),
#                                      ("Process with machine(s)", machine_fill)), 1):
#         ws.cell(row=r + k, column=1, value=txt).font = font()
#         ws.cell(row=r + k, column=2).fill = fill
#     r += 5
#     for j, h in enumerate(("Label", "Production order", "Part number", "Child / Main", "Quantity", "Start", "End"), start=1):
#         c = ws.cell(row=r, column=j, value=h)
#         c.font, c.fill, c.border = font(bold=True), head, border
#     for k, p in enumerate(result["meta"]["pos"], start=1):
#         for j, v in enumerate((p["label"], p["production_order"], p["part_number"], p["role"], p["quantity"],
#                                p["start"], p["end"]), start=1):
#             c = ws.cell(row=r + k, column=j, value=v)
#             c.font, c.border = font(), border

#     ws2 = wb.create_sheet("PO on Machines")
#     header(ws2, "Machine")
#     r, current = 4, None
#     for m in result.get("machines", []):
#         if m["group"] != current:
#             current = m["group"]
#             band(ws2, r, m["group_name"], machine_fill)
#             r += 1
#         a = ws2.cell(row=r, column=1, value=f"{m['name']} ({m['machine_id']})" + (f" · {m['step']}" if m.get("step") else ""))
#         a.font, a.border = font(bold=True), border
#         b = ws2.cell(row=r, column=2, value=f"{round(m['busy_minutes'] / 60, 1)} h")
#         b.font, b.border, b.alignment = font(), border, center
#         day_cells(ws2, r, m["segments"], m["downtime"])
#         r += 1

#     buf = io.BytesIO()
#     wb.save(buf)
#     return buf.getvalue()


# # --------------------------------------------------------------------------------------
# # Router
# # --------------------------------------------------------------------------------------
# def create_po_gantt_router(init_db, verify_token=None, engine=None) -> APIRouter:
#     """Pass `engine` so machine_hours / batch_size are added to part_process_time and the plan tables are created
#     at start-up (otherwise they are created on first use)."""
#     if engine is not None:
#         ensure_part_process_time_columns(engine)
#         try:
#             ensure_plan_tables(engine)
#         except Exception as exc:
#             print(f"[po_gantt] could not create schedule_plan tables: {exc}")
#     router = APIRouter()
#     deps = [Depends(verify_token)] if verify_token else []

#     def _guard(fn, db=None):
#         try:
#             return fn()
#         except PoGanttError as e:
#             if db is not None:
#                 db.rollback()
#             raise HTTPException(status_code=e.status_code, detail=e.detail)

#     def _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start):
#         return _guard(lambda: build_po_gantt(db, production_order, plant, start_date, time_source, label_mode,
#                                              show_holidays, shift_start))

#     @router.get("/schedule/po-gantt/plants", dependencies=deps)
#     def po_gantt_plants(db: Session = Depends(init_db)):
#         return list_plants(db)

#     @router.get("/schedule/part-process-time", dependencies=deps)
#     def part_process_time_list(plant: Optional[str] = Query(None), part_no: Optional[str] = Query(None),
#                                db: Session = Depends(init_db)):
#         return list_part_process_times(db, plant, part_no)

#     @router.put("/schedule/part-process-time", dependencies=deps)
#     def part_process_time_save(body: PartTimeSave, db: Session = Depends(init_db)):
#         return _guard(lambda: save_part_process_times(db, body), db)

#     @router.get("/schedule/po-gantt/orders", dependencies=deps)
#     def po_gantt_orders(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
#         return list_open_orders(db, plant)

#     @router.get("/schedule/po-gantt", dependencies=deps)
#     def po_gantt(
#         request: Request,
#         production_order: Optional[List[str]] = Query(None, description="PO numbers to load; order = load priority"),
#         plant: Optional[str] = Query(None),
#         start_date: Optional[date] = Query(None, description="default: first working day on/after today"),
#         time_source: str = Query("actual"),
#         label_mode: str = Query("seq", description="'seq' = B1, B2... | 'po' = PO number"),
#         show_holidays: bool = Query(True, description="send off days as flagged columns"),
#         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=20),
#         db: Session = Depends(init_db),
#     ):
#         return _send(_run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start),
#                      request, drop_for_page=True)

#     @router.get("/schedule/po-gantt/export", dependencies=deps)
#     def po_gantt_export(
#         production_order: Optional[List[str]] = Query(None),
#         plant: Optional[str] = Query(None),
#         start_date: Optional[date] = Query(None),
#         time_source: str = Query("actual"),
#         label_mode: str = Query("seq"),
#         show_holidays: bool = Query(True),
#         shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=20),
#         db: Session = Depends(init_db),
#     ):
#         result = _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)
#         return StreamingResponse(
#             io.BytesIO(build_po_gantt_xlsx(result)),
#             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#             headers={"Content-Disposition": 'attachment; filename="po_gantt.xlsx"'},
#         )

#     @router.post("/schedule/plans", dependencies=deps)
#     def plans_save(body: PlanSave, db: Session = Depends(init_db)):
#         return _guard(lambda: save_plan(db, body), db)

#     @router.get("/schedule/plans", dependencies=deps)
#     def plans_list(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
#         return list_plans(db, plant)

#     @router.get("/schedule/plans/{plan_id}", dependencies=deps)
#     def plans_get(plan_id: int, db: Session = Depends(init_db)):
#         def go():
#             p = _get_plan(db, plan_id)
#             return {"plan": _plan_header(p), "snapshot": p.snapshot}
#         return _guard(go)

#     @router.put("/schedule/plans/{plan_id}/baseline", dependencies=deps)
#     def plans_baseline(plan_id: int, db: Session = Depends(init_db)):
#         return _guard(lambda: set_baseline(db, plan_id), db)

#     @router.delete("/schedule/plans/{plan_id}", dependencies=deps)
#     def plans_delete(plan_id: int, db: Session = Depends(init_db)):
#         return _guard(lambda: delete_plan(db, plan_id), db)

#     @router.get("/schedule/plans/{plan_id}/compare", dependencies=deps)
#     def plans_compare(plan_id: int, request: Request, db: Session = Depends(init_db)):
#         return _send(_guard(lambda: compare_plan(db, plan_id)), request)

#     return router







"""
po_gantt_service.py  -  Production Schedule: PO on Process / PO on Machines / Planned vs Actual

    GET    /schedule/po-gantt                 the schedule (stations = process rows, machines = machine rows)
    GET    /schedule/po-gantt/orders          yet-to-start POs + part numbers of the plant (pickers)
    GET    /schedule/po-gantt/plants          plant codes
    GET    /schedule/po-gantt/process-check   every process: batch or series and why (process_type), batch size, machines
    GET    /schedule/po-gantt/export          the same schedule as .xlsx (sheet 1 process, sheet 2 machines)
    GET/PUT /schedule/part-process-time       machine hours + batch size per part / process
    POST   /schedule/plans                    save the schedule (built again with the same inputs) -> schedule_plan(+_item)
    GET    /schedule/plans?plant=             saved plans
    GET    /schedule/plans/{id}               one saved plan with its snapshot
    PUT    /schedule/plans/{id}/baseline      make it the baseline of its plant
    DELETE /schedule/plans/{id}
    GET    /schedule/plans/{id}/compare       planned (saved plan) vs actual (operator_log / pcb_process_log)

Hook-up (Data_Server.py) - unchanged:
    from po_gantt_service import create_po_gantt_router
    app.include_router(create_po_gantt_router(init_db, verify_token, engine))

RULES
 * POs come ONLY from PcbData. A PO is open when every one of its PCBs is New / Assigned; quantity = sum of PCB quantity.
 * CHILD / MAIN comes from product_type_master.sub_product_type_name. A MAIN part is fed by the CHILD part with the
   same product_type_name (HEXA child 62005774DA -> HEXA main 113300033357). bom_items is only a fallback link.
 * The flow of a part = product_workflow_mapping ordered by step_sequence. A PO runs its flow process after process,
   as one block (the whole quantity). A main PO starts right after the child PO(s) that feed it
    finish (not after ALL child POs): linked POs are scheduled as one chain, and a run can use any free gap of a machine.
 * SMT LINE = the 4 TOP SIDE steps in LINE_GROUPS: one process / one row, run in one go INSIDE ONE WORKING DAY (and in
   one free stretch of its machines). Line time = slowest step for the whole PO + one board through the other steps.
 * MACHINES: equipment_details (stage_id = process, machine_id). A machine is ONE resource: if the same machine_id
   serves several processes, they share it. A line run occupies one machine of every line step at once.
 * MAINTENANCE: a machine is not scheduled while it is down -
     machine_breakdown_logs : breakdown_date + breakdown_time  ->  mc_ready_date, else + downtime_hours,
                              else (still open) until now + OPEN_BREAKDOWN_HOURS.  Closed rows with no end are ignored.
     maintenance_schedules  : every quarter that is not completed blocks the whole day of its date
                              (actual date if filled, else planned date).
   Records are matched to equipment by machine_id, else by machine name.
 * Time per unit = (actual_time or sap_time, hours) + part_process_time.machine_hours (default 0).
   Fallback base: routing process_time_seconds, stage_capacity.manufacturing_time_mins, then 1 min + warning.
   SERIES: qty * t.  BATCH: ceil(qty / batch_size) * t.  Plus setup_minutes once per PO run.
   batch_size = part_process_time.batch_size (if set) else stage_schedule_config.batch_size else 30.
 * PLANT: only POs, equipment and process times of the chosen plant_code are used.
 * Shifts per process from stage_capacity (by name; for the line the line name first); default 2 x 7 h.
   The working window of a day is 08:00 - 22:00 at most (starts at shift_start, lasts shifts * hours, capped at 22:00).
 * Off days: Sundays, 1st/3rd Saturdays, public_holidays, calendar_exceptions 'Holiday';
   'Working' reopens a day, 'Half-Day' halves its window.
 * ACTUAL (Planned vs Actual): operator_log (PCB x step, start_time / end_time), pcb_process_log via pcb_assignment
   when operator_log has no row. A process is done for a PO when every PCB of the PO has an end time there.
"""
import gzip
import io
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, inspect as sa_inspect, text as sa_text
from sqlalchemy.orm import Session, joinedload

from Database_models import (
    BOMItem, CalendarException, Equipments, MachineBreakdownLog, MaintenanceScheduleLog, OperatorLog,
    OperatorShiftAssignment, OperatorStepMapping, PartProcessTime, PCBAssignment, PcbData, PCBProcessLog, Plant,
    ProcessFlowMaster, Processtype, ProductTypeMaster, ProductWorkflowMapping, PublicHoliday, SchedulePlan,
    SchedulePlanItem, ShiftDefinition, StageCapacityDB, StageScheduleConfig, InventorySpares, Consumables
)

# --------------------------------------------------------------------------------------
# Constants (change the rules in one place)
# --------------------------------------------------------------------------------------
ISO = "%Y-%m-%dT%H:%M:%S"
WEEKLY_OFF_DAYS = (6,)             # Python weekday(): Monday = 0 ... Sunday = 6
ALT_SATURDAYS_OFF = (1, 3)         # 1st and 3rd Saturday of the month
DEFAULT_SHIFTS = 2
DEFAULT_HOURS_PER_SHIFT = 7.0
DEFAULT_SHIFT_START = 8.0          # day window starts 08:00
DAY_END_HOUR = 22.0                # ... and never runs past 22:00 (window = 08:00 - 22:00 = 14 h)
DEFAULT_BATCH_SIZE = 30
FALLBACK_MINUTES = 1.0
MANUAL_PARALLEL_SLOTS = 1          # a MANUAL process (no machine) can work on this many POs at the same time (1 = one PO at a time)
HANDOFF_WARN_HOURS = 30.0          # warn when a main PO starts later than this after the child PO it needs has finished
PCB_OPEN_STATUSES = {"new", "assigned"}      # PcbData.status values that count as "not started"
EXTRA_CHILD_LINKS: Dict[str, str] = {}      # {main_part_no: child_part_no} to force a link

OPEN_BREAKDOWN_HOURS = 24.0        # open breakdown with no ready date / downtime: machine blocked until now + this
DEFAULT_SPARE_LEAD_DAYS = 7        # inventorty_spares.procurement_lead_time empty / not a number
CONSUMABLE_RESTOCK_DAYS = 7        # consumable out of stock / expired: process blocked from now for this many days (no restock date in the table)
DONE_STATUSES = {"completed", "complete", "done", "closed", "resolved"}
LATE_TOLERANCE_MIN = 0.0           # Planned vs Actual: finishing up to this many minutes after plan is "on time"

ROLES = ("CHILD", "MAIN")                   # section order of the rows

# Steps that run as ONE line, inside one working day, shown as ONE row (matched by step name, case-insensitive)
LINE_GROUPS: Dict[str, Tuple[str, ...]] = {
    "SMT LINE": (
        "SOLDER PASTE PRINTING - TOP SIDE",
        "SOLDER PASTE INSPECTION - TOP SIDE",
        "PICK N PLACE - TOP SIDE",
        "REFLOW - TOP SIDE",
    ),
}

BLUE, ORANGE = "BLUE", "ORANGE"


class PoGanttError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.replace(microsecond=0).strftime(ISO) if dt else None


def _norm(s: Optional[str]) -> str:
    """Part / PO numbers: ignore spaces and leading zeros."""
    return (s or "").strip().lstrip("0")


def _key(s: Optional[str]) -> str:
    """Name matching: case / punctuation insensitive."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _hm(h: float) -> str:
    hh = int(h)
    return f"{hh:02d}:{int(round((h - hh) * 60)):02d}"


def _chunks(seq: List[Any], n: int = 500) -> Iterable[List[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


_DATE_FMTS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y")
_TIME_FMTS = ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "%I:%M%p", "%H:%M:%S.%f")


def _parse_time(v) -> Optional[time]:
    if v is None or v == "":
        return None
    if isinstance(v, time):
        return v
    s = str(v).strip()
    for f in _TIME_FMTS:
        try:
            return datetime.strptime(s, f).time()
        except ValueError:
            continue
    return None


def _parse_dt(v) -> Optional[datetime]:
    """Dates / datetimes as stored in the maintenance and log tables (ISO, dd-mm-yyyy, dd/mm/yyyy, with or without time)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo is None else v.astimezone().replace(tzinfo=None)
    if isinstance(v, date):
        return datetime.combine(v, time.min)
    s = str(v).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s[:-1] if s.endswith("Z") else s)
        return dt if dt.tzinfo is None else dt.astimezone().replace(tzinfo=None)
    except ValueError:
        pass
    for df in _DATE_FMTS:
        for tf in ("",) + tuple(" " + t for t in _TIME_FMTS):
            try:
                return datetime.strptime(s, df + tf)
            except ValueError:
                continue
    return None


def _merge(intervals: Iterable[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    out: List[List[datetime]] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def step_name(row) -> str:
    """Stage name of a ProductWorkflowMapping row (via its process_detail relationship -> process_flow_master)."""
    pd = row.process_detail
    return (pd.step_name if pd and pd.step_name else None) or f"Step {row.flow_step_id}"


# --------------------------------------------------------------------------------------
# Calendar with a per-station daily window + machine down-time
# --------------------------------------------------------------------------------------
class DayCalendar:
    """A working day d has a window [d shift_start, +capacity*factor). A station's capacity decides the window length.
    `blocks` (sorted, merged (start, end) pairs) are times the machine is down; work never runs inside them."""

    def __init__(self, holidays: Dict[date, str], exceptions: Dict[date, str], shift_start: float):
        self.holidays = holidays
        self.exceptions = {d: (t or "").strip().lower() for d, t in exceptions.items()}
        self.shift_start = float(shift_start)

    def factor(self, d: date) -> float:
        exc = self.exceptions.get(d)
        if exc == "working":
            return 1.0
        if exc == "half-day":
            return 0.5
        if exc == "holiday":
            return 0.0
        if d in self.holidays:
            return 0.0
        if d.weekday() in WEEKLY_OFF_DAYS:
            return 0.0
        if d.weekday() == 5 and ((d.day - 1) // 7 + 1) in ALT_SATURDAYS_OFF:
            return 0.0
        return 1.0

    def off_reason(self, d: date) -> str:
        if d in self.holidays:
            return self.holidays[d] or "Holiday"
        if self.exceptions.get(d) == "holiday":
            return "Holiday"
        if d.weekday() == 6:
            return "Sunday"
        if d.weekday() == 5:
            return "1st/3rd Saturday"
        return "Off"

    def window(self, d: date, cap_min: float) -> Tuple[datetime, datetime]:
        ws = datetime.combine(d, time.min) + timedelta(hours=self.shift_start)
        return ws, ws + timedelta(minutes=cap_min * self.factor(d))

    def first_working_day(self, d: date) -> date:
        for _ in range(4000):
            if self.factor(d) > 0:
                return d
            d += timedelta(days=1)
        raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

    def locate(self, t: datetime, cap_min: float) -> Tuple[datetime, date]:
        """Earliest moment >= t inside a working window, and the working day that window belongs to."""
        d = t.date() - timedelta(days=1)                      # yesterday's window may spill past midnight
        for _ in range(4000):
            if self.factor(d) > 0:
                ws, we = self.window(d, cap_min)
                if t < ws:
                    return ws, d
                if t < we:
                    return t, d
            d += timedelta(days=1)
        raise PoGanttError(500, "No working day found - check public_holidays / calendar_exceptions")

    def free_pieces(self, t: datetime, cap_min: float, blocks=()):
        """Contiguous free stretches (day, start, end) from t onward: inside working windows and outside `blocks`."""
        cur, day = self.locate(t, cap_min)
        i, n = 0, len(blocks)
        for _ in range(500000):
            _, we = self.window(day, cap_min)
            while i < n and blocks[i][1] <= cur:
                i += 1
            if i < n and blocks[i][0] <= cur:                    # machine down right now -> jump past it
                cur, day = self.locate(blocks[i][1], cap_min)
                continue
            end = we if i >= n else min(we, blocks[i][0])
            if end > cur:
                yield day, cur, end
            cur, day = self.locate(end, cap_min)
        raise PoGanttError(500, "Could not place a run inside the working calendar")

    def consume(self, start: datetime, minutes: float, cap_min: float, blocks=()):
        """Run `minutes` of work from `start`, only inside working windows and outside down-time.
        Returns (real_start, end, end_day, [(day, seg_start, seg_end, minutes), ...])."""
        if minutes <= 0:
            cur, day = self.locate(start, cap_min)
            return cur, cur, day, []
        rem, segs, first = float(minutes), [], None
        for day, a, b in self.free_pieces(start, cap_min, blocks):
            if first is None:
                first = a
            use = min(rem, (b - a).total_seconds() / 60.0)
            e = a + timedelta(minutes=use)
            segs.append((day, a, e, use))
            rem -= use
            if rem <= 1e-9:
                return first, e, day, segs
        raise PoGanttError(500, "Could not place a run inside the working calendar")

    def place_within_day(self, start: datetime, minutes: float, cap_min: float, blocks=()):
        """The whole run must sit in ONE free stretch of ONE working day. If it does not fit in what is left, it moves
        to the next stretch that can hold it. A run longer than a full day has to spill over.
        Returns consume(...) + (fits_in_one_day,)."""
        if minutes <= cap_min + 1e-9:
            for k, (day, a, b) in enumerate(self.free_pieces(start, cap_min, blocks)):
                if (b - a).total_seconds() / 60.0 + 1e-9 >= minutes:
                    e = a + timedelta(minutes=minutes)
                    return a, e, day, [(day, a, e, minutes)], True
                if k > 20000:
                    break
        # longer than one working day: start at the beginning of a day, so it is spread over as few days as possible
        for day, a, b in self.free_pieces(start, cap_min, blocks):
            if a == self.window(day, cap_min)[0]:
                start = a
                break
        return self.consume(start, minutes, cap_min, blocks) + (False,)


# --------------------------------------------------------------------------------------
# Station container
# --------------------------------------------------------------------------------------
class Station:
    def __init__(self, key: str, name: str, kind: str, step_ids: List[int]):
        self.key, self.name, self.kind, self.step_ids = key, name, kind, list(step_ids)   # kind: STEP | LINE
        self.steps: List[str] = []                       # member step names (LINE only)
        self.options: List[Dict[str, Any]] = []          # ways to run it: {name, resources, phys, blocks}
        self.real_machines: List[Tuple[str, str]] = []   # every physical machine of the process: (machine_id, step name)
        self.shifts, self.hps, self.cap_min = DEFAULT_SHIFTS, DEFAULT_HOURS_PER_SHIFT, 0.0
        self.mode, self.batch_size = "SERIES", DEFAULT_BATCH_SIZE
        self.setup = self.cooldown = 0.0
        self.cd_working_only = self.next_day_release = False
        self.operators = 0
        self.material: List[Dict[str, Any]] = []        # consumable shortages of its steps

    @property
    def machines(self) -> List[str]:
        return [o["name"] for o in self.options if o["name"]]


# --------------------------------------------------------------------------------------
# Loaders
# --------------------------------------------------------------------------------------
def _load_candidates(db: Session, plant: Optional[str], warnings: List[str]) -> Dict[str, Dict[str, Any]]:
    """POs come ONLY from PcbData. Plant filter: the PO's part number must belong to that plant in
    product_type_master (PcbData.plant is only used for parts missing from the master).
    A PO is loadable when EVERY one of its PCBs has status New or Assigned.
    PcbData.status stays 'Assigned' after the PCB is finished (the assign step is the only place that changes it), so a
    PO whose PCBs are ALL finished in pcb_assignment (current_step_id empty or overall_status done) is left out -
    otherwise every PO ever made would be scheduled again."""
    finished = set()
    for (pid,) in db.query(PCBAssignment.assigned_pcb_id).filter(or_(
            PCBAssignment.current_step_id.is_(None),
            func.lower(func.coalesce(PCBAssignment.overall_status, "")).in_(list(DONE_STATUSES)))).all():
        finished.add(pid)
    plant_parts, known_parts = set(), set()
    if plant:
        for pn, pc in db.query(ProductTypeMaster.part_number, ProductTypeMaster.plant_code).all():
            known_parts.add(_norm(pn))
            if pc == plant:
                plant_parts.add(_norm(pn))
    q = db.query(PcbData.productionOrder, PcbData.partNumber, PcbData.quantity, PcbData.status, PcbData.createdAt,
                 PcbData.plant, PcbData.serialNo, PcbData.PCBserialNoPartNumber, PcbData.Type
                 ).filter(PcbData.productionOrder.isnot(None), PcbData.productionOrder != "")
    by_po: Dict[str, list] = defaultdict(list)
    for r in q.all():
        if plant:
            n = _norm(r[1])
            if not (n in plant_parts or (n not in known_parts and (r[5] or "").strip() == plant)):
                continue
        by_po[_norm(r[0])].append(r)

    cands: Dict[str, Dict[str, Any]] = {}
    for po, rows in by_po.items():
        if all(r[7] in finished for r in rows):              # every PCB finished -> history, not scheduled
            continue
        parts = [r[1] for r in rows if r[1]]
        if not parts:
            warnings.append(f"PO {po}: PCBs have no part number - ignored")
            continue
        part = max(set(parts), key=parts.count)
        if len(set(parts)) > 1:
            warnings.append(f"PO {po}: PCBs carry several part numbers ({', '.join(sorted(set(parts)))}) - {part} used")
        created = [r[4] for r in rows if r[4]]
        cands[po] = {
            "po": po, "part": part,
            "qty": sum(r[2] if (r[2] and r[2] > 0) else 1 for r in rows),
            "created": min(created) if created else None,
            "started": any((r[3] or "").strip().lower() not in PCB_OPEN_STATUSES for r in rows),
            # every PCB of the PO: serial number (links child <-> main), PCB id (pcb_assignment), Type, status
            "pcbs": [{"sn": r[6], "serial": (r[6] or "").strip().upper(), "pcb_id": r[7], "part": r[1],
                      "type": (r[8] or "").strip().upper(), "status": (r[3] or "").strip().lower()} for r in rows],
        }
    return cands


def _serial_links(db: Session, cands: Dict[str, Dict[str, Any]], role_of, child_of: Dict[str, str], main_pos: List[str]):
    """Child -> main link by SERIAL NUMBER (same rule as the assign step, can_proceed in Data_Server):
    the main PCB with serialNo S needs the child PCB with the same serialNo S.
    Only for `main_pos` (the main POs being scheduled); their child PCBs are looked up in PcbData by serial number, so a
    child PO that is already finished (and so not a candidate) is still found.
    Returns
      links {main_po: [{child_po, child_part, pcbs, done, in_progress, not_assigned, steps}]}
      unmatched {main_po: number of main PCBs with no child PCB of the same serial}
    State of a child PCB (pcb_assignment.assigned_pcb_id = PCBserialNoPartNumber):
      no assignment row                     -> not assigned
      current_step_id empty / status done   -> done (child flow finished)
      current_step_id filled                -> in process (at that step)"""
    def is_main(pcb) -> bool:
        return pcb["type"].endswith("MAIN") or role_of(pcb["part"]) == "MAIN"

    mains = [po for po in main_pos if po in cands and role_of(cands[po]["part"]) == "MAIN"]
    serials = sorted({pcb["sn"].strip() for po in mains for pcb in cands[po]["pcbs"] if pcb["sn"] and pcb["sn"].strip()})
    child_by_serial: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for chunk in _chunks(serials):
        for sn, pid, part, po, typ, status in db.query(
                PcbData.serialNo, PcbData.PCBserialNoPartNumber, PcbData.partNumber, PcbData.productionOrder,
                PcbData.Type, PcbData.status).filter(PcbData.serialNo.in_(chunk)).all():
            typ = (typ or "").strip().upper()
            if po and (typ.endswith("CHILD") or role_of(part) == "CHILD"):
                child_by_serial[(sn or "").strip().upper()].append(
                    {"po": _norm(po), "pcb_id": pid, "part": part, "status": (status or "").strip().lower()})

    ids = [ch["pcb_id"] for lst in child_by_serial.values() for ch in lst if ch["pcb_id"]]
    state: Dict[str, Tuple[Optional[int], str]] = {}
    for chunk in _chunks(ids):
        for a in db.query(PCBAssignment).filter(PCBAssignment.assigned_pcb_id.in_(chunk)).all():
            state[a.assigned_pcb_id] = (a.current_step_id, (a.overall_status or "").strip().lower())

    links: Dict[str, List[Dict[str, Any]]] = {}
    unmatched: Dict[str, int] = {}
    for po in mains:
        c = cands[po]
        per_child: Dict[str, Dict[str, Any]] = {}
        missing = 0
        for pcb in c["pcbs"]:
            if not is_main(pcb):
                continue
            hits = [ch for ch in child_by_serial.get(pcb["serial"], []) if ch["part"] != c["part"]]
            want = child_of.get(c["part"])
            hits = [h for h in hits if h["part"] == want] or hits          # prefer the child part of its family
            if not hits:
                missing += 1
                continue
            ch = hits[0]
            l = per_child.setdefault(ch["po"], {"child_po": ch["po"], "child_part": ch["part"], "pcbs": 0, "done": 0,
                                                "in_progress": 0, "not_assigned": 0, "steps": []})
            l["pcbs"] += 1
            st = state.get(ch["pcb_id"])
            if ch["status"] in DONE_STATUSES or (st and (st[0] is None or st[1] in DONE_STATUSES)):
                l["done"] += 1
            elif st:
                l["in_progress"] += 1
                if st[0] not in l["steps"]:
                    l["steps"].append(st[0])
            else:
                l["not_assigned"] += 1
        if per_child:
            links[po] = list(per_child.values())
            unmatched[po] = missing
    return links, unmatched


def _product_links(db: Session, warnings: Optional[List[str]] = None):
    """Returns (products, child_of {main_pn: child_pn}, role_of(pn) -> 'CHILD' | 'MAIN').
    1. product_type_master: CHILD and MAIN rows with the same product_type_name (and plant) belong together.
    2. bom_items fallback: the child P/N appears as a material of the main P/N (leading zeros ignored).
    3. EXTRA_CHILD_LINKS override."""
    products = {p.part_number: p for p in db.query(ProductTypeMaster).all()}
    part_by_norm = {_norm(pn): pn for pn in products}

    def sub(pn: str) -> str:
        p = products.get(pn)
        return (p.sub_product_type_name or "").strip().upper() if p else ""

    child_of: Dict[str, str] = {}
    families: Dict[tuple, Dict[str, List[str]]] = defaultdict(lambda: {"CHILD": [], "MAIN": []})
    for pn, p in products.items():
        s = sub(pn)
        if s in ROLES and _key(p.product_type_name):
            families[(_key(p.product_type_name), p.plant_code)][s].append(pn)
    for (fam, _plant), g in sorted(families.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        childs = sorted(g["CHILD"])
        for m in g["MAIN"]:
            if childs:
                child_of[m] = childs[0]
                if len(childs) > 1 and warnings is not None:
                    warnings.append(f"Family {fam.upper()}: several child parts ({', '.join(childs)}) - "
                                    f"{childs[0]} used to feed {m}")

    for main_pn, material in db.query(BOMItem.product_part_number, BOMItem.material).all():
        m = part_by_norm.get(_norm(main_pn)) or main_pn
        c = part_by_norm.get(_norm(material))
        if c and m and c != m and m not in child_of and sub(m) != "CHILD" and sub(c) != "MAIN":
            child_of[m] = c
    for m, c in EXTRA_CHILD_LINKS.items():
        m, c = part_by_norm.get(_norm(m)), part_by_norm.get(_norm(c))
        if m and c:
            child_of[m] = c
    for m, c in list(child_of.items()):
        if child_of.get(c) == m:
            del child_of[m]
    child_parts = set(child_of.values())

    def role_of(pn: Optional[str]) -> str:
        s = sub(pn or "")
        if s in ROLES:
            return s
        return "CHILD" if pn in child_parts else "MAIN"

    return products, child_of, role_of


# def _load_downtime(db: Session, machines: Dict[str, Dict[str, Any]], not_before: datetime, now: datetime,
#                    warnings: List[str]) -> Dict[str, List[Dict[str, Any]]]:
#     """Down-time events per machine_id from machine_breakdown_logs and maintenance_schedules.
#     `machines` = {machine_id: {"name", "eqpt_no", ...}} of the plant. Only events ending after `not_before` are kept."""
#     by_id = {_key(mid): mid for mid in machines}
#     names: Dict[str, List[str]] = defaultdict(list)
#     for mid, info in machines.items():
#         for n in {_key(info.get("name")), _key(info.get("eqpt_no"))} - {""}:
#             if mid not in names[n]:
#                 names[n].append(mid)

#     def match(rec_id, rec_name) -> Optional[str]:
#         mid = by_id.get(_key(rec_id))
#         if mid:
#             return mid
#         for k in (_key(rec_id), _key(rec_name)):
#             if k and len(names.get(k, [])) == 1:          # only an unambiguous name
#                 return names[k][0]
#         return None

#     out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
#     assumed = 0
#     try:
#         breakdowns = db.query(MachineBreakdownLog).all()
#     except Exception as exc:                                 # table missing -> schedule without it
#         db.rollback()
#         warnings.append(f"machine_breakdown_logs could not be read ({exc.__class__.__name__}) - breakdowns ignored")
#         breakdowns = []
#     for b in breakdowns:
#         mid = match(b.machine_id, b.machine_name)
#         if not mid:
#             continue
#         st = _parse_dt(b.breakdown_date)
#         if not st:
#             continue
#         tt = _parse_time(b.breakdown_time)
#         if tt and st.time() == time.min:
#             st = datetime.combine(st.date(), tt)
#         is_open = (b.status or "").strip().lower() not in DONE_STATUSES
#         en, note = _parse_dt(b.mc_ready_date), None
#         if not en and b.downtime_hours and b.downtime_hours > 0:
#             en = st + timedelta(hours=float(b.downtime_hours))
#         if not en and is_open:
#             en = max(now, st) + timedelta(hours=OPEN_BREAKDOWN_HOURS)
#             note = f"still open - assumed down until {_iso(en)}"
#             assumed += 1
#         if not en or en <= st or en <= not_before:
#             continue
#         out[mid].append({"machine": mid, "kind": "BREAKDOWN", "label": b.event_type or "Breakdown",
#                          "status": b.status, "start": st, "end": en,
#                          "note": note or (b.issue_description or "")})

#     try:
#         pms = db.query(MaintenanceScheduleLog).all()
#     except Exception as exc:
#         db.rollback()
#         warnings.append(f"maintenance_schedules could not be read ({exc.__class__.__name__}) - maintenance ignored")
#         pms = []
#     for m in pms:
#         mid = match(m.machine_id, m.machine_name)
#         if not mid:
#             continue
#         for q in (1, 2, 3, 4):
#             status = (getattr(m, f"q{q}_status") or "").strip().lower()
#             if status in DONE_STATUSES:
#                 continue
#             d = _parse_dt(getattr(m, f"q{q}_actual_date")) or _parse_dt(getattr(m, f"q{q}_planned_date"))
#             if not d:
#                 continue
#             st = datetime.combine(d.date(), time.min)
#             en = st + timedelta(days=1)
#             if en <= not_before:
#                 continue
#             out[mid].append({"machine": mid, "kind": "PM", "label": m.event_type or "Preventive Maintenance",
#                              "status": getattr(m, f"q{q}_status"), "start": st, "end": en,
#                              "note": f"Q{q} maintenance" + (f" - {m.remarks}" if m.remarks else "")})
#     if assumed:
#         warnings.append(f"{assumed} open breakdown(s) without ready date / downtime - machine assumed down for "
#                         f"{OPEN_BREAKDOWN_HOURS:g} h from now")
#     for mid in out:
#         out[mid].sort(key=lambda e: e["start"])
#     return out

def _load_downtime(db: Session, machines: Dict[str, Dict[str, Any]], not_before: datetime, now: datetime,
                   warnings: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    by_id = {_key(mid): mid for mid in machines}
    names: Dict[str, List[str]] = defaultdict(list)
    for mid, info in machines.items():
        for n in {_key(info.get("name")), _key(info.get("eqpt_no"))} - {""}:
            if mid not in names[n]:
                names[n].append(mid)

    def match(rec_id, rec_name) -> Optional[str]:
        mid = by_id.get(_key(rec_id))
        if mid: return mid
        for k in (_key(rec_id), _key(rec_name)):
            if k and len(names.get(k, [])) == 1: return names[k][0]
        return None

    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    # 1. Spares (inventorty_spares): a spare only matters when its machine is DOWN. If the spare is out of stock, an open
    #    breakdown of that machine lasts at least the procurement lead time (the repair waits for the spare).
    #    A running machine is NOT blocked because a spare is missing - that is only a risk (warning).
    try:
        spares = db.query(InventorySpares).all()
    except Exception:
        db.rollback()
        spares = []
    spare_out: Dict[str, Tuple[int, str]] = {}           # machine_id -> (lead days, spare text)
    low_spares: List[str] = []
    for sp in spares:
        q, th = _num(sp.qty_avl), _num(sp.threshold_qty)
        if q is None:                                    # no stock figure -> nothing to check
            continue
        if sp.eqpt_no:
            mids = [match(sp.eqpt_no, None)]
        else:                                            # spare of a process: every machine of that process
            mids = [m for m, info in machines.items() if sp.flow_step_id in info.get("stage_ids", [])]
        mids = [m for m in mids if m]
        text = sp.decription or sp.part_number or "spare"
        if q <= 0:
            days = _lead_days(sp.procurement_lead_time)
            for m in mids:
                if days >= spare_out.get(m, (0, ""))[0]:
                    spare_out[m] = (days, text)
        elif th is not None and q <= th:
            low_spares.append(f"{text} ({', '.join(mids) or sp.eqpt_no or 'no machine'}: {q:g} left, threshold {th:g})")

    # 2. Machine Breakdowns
    try:
        breakdowns = db.query(MachineBreakdownLog).all()
    except Exception:
        db.rollback()
        breakdowns = []
    waiting_spare = set()
    for b in breakdowns:
        mid = match(b.machine_id, b.machine_name)
        if not mid: continue
        st = _parse_dt(b.breakdown_date)
        if not st: continue
        tt = _parse_time(b.breakdown_time)
        if tt and st.time() == time.min: st = datetime.combine(st.date(), tt)
        is_open = (b.status or "").strip().lower() not in DONE_STATUSES
        en, note = _parse_dt(b.mc_ready_date), None
        if not en and b.downtime_hours and b.downtime_hours > 0:
            en = st + timedelta(hours=float(b.downtime_hours))
        if not en and is_open:
            en = max(now, st) + timedelta(hours=OPEN_BREAKDOWN_HOURS)
            note = f"still open - assumed down until {_iso(en)}"
            if mid in spare_out:                         # the repair needs a spare that is not in stock
                days, text = spare_out[mid]
                en = max(en, max(now, st) + timedelta(days=days))
                note = f"waiting for spare '{text}' (out of stock, lead time {days} day(s)) - down until {_iso(en)}"
                waiting_spare.add(mid)
        if not en or en <= st or en <= not_before: continue
        out[mid].append({"machine": mid, "kind": "BREAKDOWN", "label": b.event_type or "Breakdown",
                         "status": b.status, "start": st, "end": en, "note": note or (b.issue_description or "")})
    if waiting_spare:
        warnings.append("Breakdown repair waits for an out-of-stock spare (lead time used): "
                        + ", ".join(f"{m} - {spare_out[m][1]} ({spare_out[m][0]} d)" for m in sorted(waiting_spare)))
    risk = sorted(m for m in spare_out if m not in waiting_spare)
    if risk:
        warnings.append("Spare out of stock (machine still running - a breakdown there would take the lead time): "
                        + ", ".join(f"{m} - {spare_out[m][1]} ({spare_out[m][0]} d)" for m in risk))
    if low_spares:
        warnings.append("Spares at or below threshold: " + "; ".join(low_spares))

    # 3. Maintenance Schedules
    try:
        pms = db.query(MaintenanceScheduleLog).all()
    except Exception:
        db.rollback()
        pms = []
    for m in pms:
        mid = match(m.machine_id, m.machine_name)
        if not mid: continue
        for q in (1, 2, 3, 4):
            if (getattr(m, f"q{q}_status") or "").strip().lower() in DONE_STATUSES: continue
            d = _parse_dt(getattr(m, f"q{q}_actual_date")) or _parse_dt(getattr(m, f"q{q}_planned_date"))
            if not d: continue
            st = datetime.combine(d.date(), time.min)
            en = st + timedelta(days=1)
            if en <= not_before: continue
            out[mid].append({"machine": mid, "kind": "PM", "label": m.event_type or "Preventive Maintenance",
                             "status": getattr(m, f"q{q}_status"), "start": st, "end": en,
                             "note": f"Q{q} maintenance" + (f" - {m.remarks}" if m.remarks else "")})

    for mid in out:
        out[mid].sort(key=lambda e: e["start"])
    return out

def _num(v) -> Optional[float]:
    """'12', '12.5', ' 12 nos' -> number; empty / text -> None."""
    m = re.search(r"-?\d+(\.\d+)?", str(v)) if v is not None else None
    return float(m.group()) if m else None


def _lead_days(v) -> int:
    """procurement_lead_time: '10', '10 days', '2 weeks' -> days."""
    n = _num(v)
    if n is None or n <= 0:
        return DEFAULT_SPARE_LEAD_DAYS
    return int(math.ceil(n * 7)) if "week" in str(v).lower() else int(math.ceil(n))


def _load_consumable_blocks(db: Session, now: datetime, not_before: datetime,
                            warnings: List[str]) -> Dict[int, List[Dict[str, Any]]]:
    """Consumables (consumables table) of every process (stage_id = flow_step_id).
    A consumable (material number) is usable when one of its rows has quantity > 0 (empty quantity = not counted, taken
    as available) and is not past consumable_shelf_life. The PROCESS cannot run (all its machines, and a process without
    a machine too) while one of its consumables is not usable:
        out of stock / already expired -> blocked from now for CONSUMABLE_RESTOCK_DAYS
        every batch in stock expires   -> blocked from the day after the last expiry for CONSUMABLE_RESTOCK_DAYS
    The table has no use per PCB, so stock is checked as available yes / no, it is not used up PCB by PCB."""
    try:
        rows = db.query(Consumables).all()
    except Exception:
        db.rollback()
        return {}
    groups: Dict[Tuple[int, str], list] = defaultdict(list)
    for c in rows:
        if c.stage_id is not None:
            groups[(c.stage_id, _key(c.consumable_material_number) or _key(c.consumable_material_name))].append(c)
    today = now.date()

    def expiry(c) -> Optional[date]:
        d = c.consumable_shelf_life
        return d.date() if isinstance(d, datetime) else d

    out: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    low: List[str] = []
    for (sid, _), lst in groups.items():
        first = lst[0]
        name = first.consumable_material_name or first.consumable_material_number or "consumable"
        mat = first.consumable_material_number or ""
        in_stock = [c for c in lst if c.quantity is None or c.quantity > 0]
        usable = [c for c in in_stock if not expiry(c) or expiry(c) >= today]
        ev = None
        if not usable:
            why = "out of stock" if not in_stock else f"expired on {max(expiry(c) for c in in_stock):%d-%m-%Y}"
            ev = {"label": "Consumable " + ("out of stock" if not in_stock else "expired"), "start": now,
                  "end": now + timedelta(days=CONSUMABLE_RESTOCK_DAYS),
                  "note": f"{name} {mat} {why} - assumed back in {CONSUMABLE_RESTOCK_DAYS} day(s)"}
        elif all(expiry(c) for c in usable):
            last = max(expiry(c) for c in usable)
            st = datetime.combine(last + timedelta(days=1), time.min)
            ev = {"label": "Consumable expires", "start": st, "end": st + timedelta(days=CONSUMABLE_RESTOCK_DAYS),
                  "note": f"{name} {mat}: the stock expires on {last:%d-%m-%Y} - assumed back in {CONSUMABLE_RESTOCK_DAYS} day(s)"}
        if ev and ev["end"] > not_before:
            out[sid].append({"machine": None, "kind": "SHORTAGE", "status": "Awaiting stock", "stage_id": sid,
                             "material": mat, "material_name": name, **ev})
        qty = [c.quantity for c in usable if c.quantity is not None]
        th = max((x for x in (_num(c.threshold_qty) for c in lst) if x is not None), default=None)
        if usable and qty and th is not None and sum(qty) <= th:
            low.append(f"{name} (step {sid}: {sum(qty)} left, threshold {th:g})")
    if low:
        warnings.append("Consumables at or below threshold: " + "; ".join(low))
    return out


def _send(result: Dict[str, Any], request: Request, drop_for_page: bool = False) -> Response:
    """Fast JSON for big schedules: no jsonable_encoder walk (the result is already plain JSON), no spaces, and gzip when
    the browser accepts it (1.2 MB -> ~0.1 MB). drop_for_page: leave out what the page does not use
    (rows' cells / po_runs and the flat runs list - Save plan / Excel build the schedule again on the server)."""
    if drop_for_page:
        result = {**result, "runs": None,
                  "stations": [{k: v for k, v in s.items() if k not in ("cells", "po_runs")} for s in result["stations"]]}
    body = json.dumps(result, separators=(",", ":"), default=str).encode()
    if len(body) > 20000 and "gzip" in (request.headers.get("accept-encoding") or ""):
        return Response(gzip.compress(body, 5), media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
    return Response(body, media_type="application/json")


def _batch_steps(db: Session) -> Dict[int, Tuple[Optional[bool], str]]:
    """Batch or series for every process (flow_step_id) and WHY - from process_type (stage_id, process_type_batch).
      1. a process_type row with stage_id = flow_step_id                         -> its process_type_batch
      2. else a row with stage_id = the step's step_order (the way the equipment page stores stage_id),
         when that number is not the flow_step_id of another step                -> its process_type_batch
      3. else no row                                                              -> series (None = row missing)
    stage_schedule_config.batch_size is NOT used to decide: it defaults to 30 for every process."""
    flags: Dict[int, bool] = {}
    for p in db.query(Processtype).all():
        if p.stage_id is not None:
            flags[p.stage_id] = flags.get(p.stage_id, False) or bool(p.process_type_batch)
    steps = db.query(ProcessFlowMaster).all()
    ids = {s.flow_step_id for s in steps}
    out: Dict[int, Tuple[Optional[bool], str]] = {}
    for s in steps:
        sid, so = s.flow_step_id, s.step_order
        if sid in flags:
            out[sid] = (flags[sid], f"process_type.stage_id = {sid} (flow_step_id)")
        elif so is not None and so in flags and so not in ids:
            out[sid] = (flags[so], f"process_type.stage_id = {so} (stored as step_order)")
        else:
            out[sid] = (None, f"no process_type row for flow_step_id {sid}" + (f" / step_order {so}" if so is not None else ""))
    return out


def process_check(db: Session, plant: Optional[str] = None) -> Dict[str, Any]:
    """GET /schedule/po-gantt/process-check - every process: batch or series and why, batch size, machines.
    Use it when a process is scheduled the wrong way (e.g. a batch process shown as one block per PO)."""
    batch = _batch_steps(db)
    cfg = {c.stage_id: c for c in db.query(StageScheduleConfig).all()}
    eq: Dict[int, List[str]] = defaultdict(list)
    for e in db.query(Equipments).all():
        if e.stage_id is not None and (not plant or not e.plant_code or e.plant_code == plant):
            eq[e.stage_id].append(e.machine_id or e.eqpt_no or f"EQ-{e.id}")
    sizes: Dict[int, List[int]] = defaultdict(list)
    tq = db.query(PartProcessTime.process_id, PartProcessTime.batch_size).filter(PartProcessTime.batch_size.isnot(None))
    if plant:
        tq = tq.filter(PartProcessTime.plant == plant)
    for pid, bs in tq.all():
        if bs and bs > 0 and bs not in sizes[pid]:
            sizes[pid].append(bs)
    q = db.query(ProcessFlowMaster)
    if plant:
        q = q.filter(or_(ProcessFlowMaster.plant_code == plant, ProcessFlowMaster.plant_code.is_(None)))
    rows = []
    for s in q.order_by(ProcessFlowMaster.step_order, ProcessFlowMaster.flow_step_id).all():
        b, why = batch.get(s.flow_step_id, (None, "-"))
        c = cfg.get(s.flow_step_id)
        rows.append({
            "flow_step_id": s.flow_step_id, "step_order": s.step_order, "process": s.step_name,
            "scheduled_as": "BATCH" if b else "SERIES", "why": why, "process_type_row": b is not None,
            "batch_size_config": c.batch_size if c else None, "batch_size_parts": sorted(sizes.get(s.flow_step_id, [])),
            "machines_by_flow_step_id": eq.get(s.flow_step_id, []),
            "machines_by_step_order": eq.get(s.step_order, []) if s.step_order != s.flow_step_id else [],
        })
    return {"plant": plant, "processes": rows,
            "missing_process_type": [r["process"] for r in rows if not r["process_type_row"]]}


def _dt_json(e: Dict[str, Any]) -> Dict[str, Any]:
    return {**e, "start": _iso(e["start"]), "end": _iso(e["end"])}


def list_open_orders(db: Session, plant: Optional[str] = None) -> Dict[str, Any]:
    """Yet-to-start POs for the picker (oldest first) + the part numbers of the plant (product_type_master)."""
    warnings: List[str] = []
    _, _, role_of = _product_links(db)
    cands = _load_candidates(db, plant, warnings)
    open_pos = sorted((c for c in cands.values() if not c["started"]),
                      key=lambda c: (c["created"] or datetime.max, c["po"]))
    pq = db.query(ProductTypeMaster)
    if plant:
        pq = pq.filter(ProductTypeMaster.plant_code == plant)
    parts = [{"part_number": p.part_number, "role": role_of(p.part_number), "product_type": p.product_type_name,
              "sub_type": p.sub_product_type_name, "description": p.description}
             for p in pq.order_by(ProductTypeMaster.product_type_name, ProductTypeMaster.part_number).all()]
    return {"orders": [{"production_order": c["po"], "part_number": c["part"], "quantity": c["qty"],
                        "role": role_of(c["part"]), "created": c["created"].isoformat() if c["created"] else None}
                       for c in open_pos],
            "parts": parts,
            "warnings": warnings}


def list_plants(db: Session) -> Dict[str, Any]:
    """Plant codes of product_type_master (a PO belongs to the plant of its part number)."""
    codes = sorted({(r[0] or "").strip() for r in db.query(ProductTypeMaster.plant_code).distinct().all()
                    if (r[0] or "").strip()})
    info = {p.plant_code: p.location for p in db.query(Plant).all()}
    return {"plants": [{"plant_code": c, "location": info.get(c) or ""} for c in codes]}


def ensure_part_process_time_columns(engine) -> None:
    """create_all() does not alter existing tables - add machine_hours / batch_size once if they are missing."""
    try:
        cols = {c["name"] for c in sa_inspect(engine).get_columns("part_process_time")}
        with engine.begin() as conn:
            if "machine_hours" not in cols:
                conn.execute(sa_text("ALTER TABLE part_process_time ADD COLUMN machine_hours DOUBLE PRECISION NOT NULL DEFAULT 0"))
            if "batch_size" not in cols:
                conn.execute(sa_text("ALTER TABLE part_process_time ADD COLUMN batch_size INTEGER"))
    except Exception as exc:                                   # never block start-up
        print(f"[po_gantt] could not verify part_process_time columns: {exc}")


_PLAN_TABLES_READY = False


def ensure_plan_tables(bind) -> None:
    """Create schedule_plan / schedule_plan_item if they do not exist yet (create_all does this too)."""
    global _PLAN_TABLES_READY
    if _PLAN_TABLES_READY:
        return
    SchedulePlan.__table__.create(bind=bind, checkfirst=True)
    SchedulePlanItem.__table__.create(bind=bind, checkfirst=True)
    _PLAN_TABLES_READY = True


def list_part_process_times(db: Session, plant: Optional[str], part_no: Optional[str] = None) -> Dict[str, Any]:
    """Every routing step of every part of the plant, joined with its part_process_time row (if any)."""
    pq = db.query(ProductTypeMaster)
    if plant:
        pq = pq.filter(ProductTypeMaster.plant_code == plant)
    if part_no:
        pq = pq.filter(ProductTypeMaster.part_number == part_no)
    products = pq.order_by(ProductTypeMaster.product_type_name, ProductTypeMaster.sub_product_type_name,
                           ProductTypeMaster.part_number).all()
    pns = [p.part_number for p in products]
    if not pns:
        return {"plant": plant, "parts": [], "rows": []}
    batch = {sid for sid, (b, _) in _batch_steps(db).items() if b}
    ppt = {}
    tq = db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(pns))
    if plant:
        tq = tq.filter(PartProcessTime.plant == plant)
    for r in tq.all():
        ppt[(r.part_no, r.process_id)] = r
    rows = []
    for p in products:
        steps = db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
                ).filter(ProductWorkflowMapping.product_part_number == p.part_number
                ).order_by(ProductWorkflowMapping.step_sequence, ProductWorkflowMapping.id).all()
        for st in steps:
            r = ppt.get((p.part_number, st.flow_step_id))
            rows.append({
                "part_no": p.part_number, "product_type": p.product_type_name, "sub_type": p.sub_product_type_name,
                "process_id": st.flow_step_id, "process_name": step_name(st), "step_sequence": st.step_sequence,
                "is_batch": st.flow_step_id in batch,
                "sap_time": r.sap_time if r else None, "actual_time": r.actual_time if r else None,
                "machine_hours": float(r.machine_hours or 0) if r else 0.0,
                "batch_size": r.batch_size if r else None,
            })
    return {"plant": plant,
            "parts": [{"part_no": p.part_number, "product_type": p.product_type_name, "sub_type": p.sub_product_type_name,
                       "description": p.description} for p in products],
            "rows": rows}


class PartTimeItem(BaseModel):
    part_no: str
    process_id: int
    machine_hours: Optional[float] = 0.0
    batch_size: Optional[int] = None


class PartTimeSave(BaseModel):
    plant: str
    items: List[PartTimeItem]


def save_part_process_times(db: Session, body: PartTimeSave) -> Dict[str, Any]:
    stage_names = {s.flow_step_id: s.step_name for s in db.query(ProcessFlowMaster).all()}
    updated = created = 0
    for it in body.items:
        mh = float(it.machine_hours or 0)
        if mh < 0:
            raise PoGanttError(422, f"{it.part_no} / step {it.process_id}: machine hours cannot be negative")
        if it.batch_size is not None and it.batch_size < 0:
            raise PoGanttError(422, f"{it.part_no} / step {it.process_id}: batch size cannot be negative")
        bs = int(it.batch_size) if it.batch_size and it.batch_size > 0 else None
        row = db.query(PartProcessTime).filter(
            PartProcessTime.part_no == it.part_no, PartProcessTime.plant == body.plant,
            PartProcessTime.process_id == it.process_id).first()
        if row:
            row.machine_hours, row.batch_size = mh, bs
            updated += 1
        else:
            if it.process_id not in stage_names:
                raise PoGanttError(404, f"Process step {it.process_id} not found")
            db.add(PartProcessTime(part_no=it.part_no, plant=body.plant, process_id=it.process_id,
                                   process_name=stage_names[it.process_id], machine_hours=mh, batch_size=bs))
            created += 1
    db.commit()
    return {"updated": updated, "created": created}


# --------------------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------------------
def build_po_gantt(db: Session, production_orders: Optional[List[str]] = None, plant: Optional[str] = None,
                   start_date: Optional[date] = None, time_source: str = "actual", label_mode: str = "seq",
                   show_holidays: bool = False, shift_start: float = DEFAULT_SHIFT_START,
                   today: Optional[date] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    if time_source not in ("actual", "sap"):
        raise PoGanttError(400, "time_source must be 'actual' or 'sap'")
    if label_mode not in ("seq", "po"):
        raise PoGanttError(400, "label_mode must be 'seq' or 'po'")
    warnings: List[str] = []
    now = now or datetime.now()
    today = today or now.date()

    # ---------------- calendar ----------------
    holidays = {h.holiday_date: h.name for h in db.query(PublicHoliday).all()}
    exceptions = {e.exception_date: e.exception_type for e in db.query(CalendarException).all()}
    cal = DayCalendar(holidays, exceptions, shift_start)
    day_cap = max((DAY_END_HOUR - shift_start) * 60.0, 60.0)       # the working day ends at 22:00

    # ---------------- masters (loaded once) ----------------
    products, child_of, role_of = _product_links(db, warnings)

    batch_rule = _batch_steps(db)                                  # flow_step_id -> (batch?, why)
    is_batch: Dict[int, bool] = defaultdict(bool, {sid: bool(b) for sid, (b, _) in batch_rule.items()})
    cfg = {c.stage_id: c for c in db.query(StageScheduleConfig).all()}
    cap_by_key = {_key(c.name): c for c in db.query(StageCapacityDB).all()}
    cap_compact = {k.replace(" ", ""): c for k, c in cap_by_key.items()}

    def find_cap(name: Optional[str]):
        """stage_capacity row of a process: exact name, then ignoring spaces / punctuation, then a UNIQUE partial match."""
        k = _key(name)
        if not k:
            return None
        c = cap_by_key.get(k) or cap_compact.get(k.replace(" ", ""))
        if c:
            return c
        hits = [v for ck, v in cap_by_key.items() if ck and (ck in k or k in ck)]
        return hits[0] if len(hits) == 1 else None

    equipment: Dict[int, List[str]] = defaultdict(list)          # stage_id -> machine_ids
    machine_info: Dict[str, Dict[str, Any]] = {}                  # machine_id -> details
    for e in db.query(Equipments).order_by(Equipments.stage_id, Equipments.id).all():
        if plant and e.plant_code and e.plant_code != plant:          # only the machines of the chosen plant
            continue
        mid = e.machine_id or e.eqpt_no or f"EQ-{e.id}"
        if e.stage_id is not None and mid not in equipment[e.stage_id]:
            equipment[e.stage_id].append(mid)
        info = machine_info.setdefault(mid, {"machine_id": mid, "name": e.eqpt_name or mid, "eqpt_no": e.eqpt_no,
                                             "process_type": e.process_type,
                                             "make": e.eqpt_make, "model": e.eqpt_model,
                                             "workcenter": e.workcenter_name, "stage_ids": []})
        if e.stage_id is not None and e.stage_id not in info["stage_ids"]:
            info["stage_ids"].append(e.stage_id)

    # equipment is normally linked by stage_id = flow_step_id. A process whose flow step has a different id / spelling
    # (e.g. "BAKING" vs "Baking") would then wrongly look manual - so also match by the step NAME, and by the
    # equipment's own process_type / workcenter / name.
    stage_names = {r.flow_step_id: r.step_name for r in db.query(ProcessFlowMaster).all()}
    eq_by_stage_name: Dict[str, List[str]] = defaultdict(list)
    for sid_, mids_ in equipment.items():
        k_ = _key(stage_names.get(sid_))
        for m_ in mids_:
            if k_ and m_ not in eq_by_stage_name[k_]:
                eq_by_stage_name[k_].append(m_)
    eq_by_label: Dict[str, List[str]] = defaultdict(list)
    for m_, inf_ in machine_info.items():
        for lab_ in (inf_.get("process_type"), inf_.get("workcenter"), inf_.get("name")):
            k_ = _key(lab_)
            if k_ and m_ not in eq_by_label[k_]:
                eq_by_label[k_].append(m_)

    def machines_for_step(sid: int, name: str) -> List[str]:
        k_ = _key(name)
        for pool in (equipment.get(sid), eq_by_stage_name.get(k_), eq_by_label.get(k_)):
            if pool:
                return list(pool)
        return []

    shift_names = [s.name for s in db.query(ShiftDefinition).filter(ShiftDefinition.is_active.is_(True))
                   .order_by(ShiftDefinition.sort_order, ShiftDefinition.id).all()]
    assigned: Dict[str, set] = defaultdict(set)
    for a in db.query(OperatorShiftAssignment).all():
        assigned[a.operator_staff_no].add(a.shift_name)
    ops_by_stage: Dict[int, List[str]] = defaultdict(list)
    for o in db.query(OperatorStepMapping).all():
        who = o.operator_staff_no or o.operator_name
        if who and who not in ops_by_stage[o.flow_step_id]:
            ops_by_stage[o.flow_step_id].append(who)

    def operators_per_shift(sid: int) -> int:
        ops = ops_by_stage.get(sid, [])
        if not shift_names:
            return len(ops)
        return max((sum(1 for o in ops if not assigned.get(o) or sn in assigned[o]) for sn in shift_names), default=0)

    line_of_name = {_key(n): g for g, names in LINE_GROUPS.items() for n in names}

    # ---------------- select the POs to load ----------------
    cands = _load_candidates(db, plant, warnings)
    if production_orders:
        selected, seen = [], set()
        for raw in production_orders:
            k = _norm(raw) or raw
            if k in seen:
                continue
            seen.add(k)
            if k not in cands:
                raise PoGanttError(404, f"Production order {raw} not found")
            if cands[k]["started"]:
                warnings.append(f"PO {k} has already started - scheduled from scratch as requested")
            selected.append(cands[k])
        explicit = True
    else:
        selected = sorted((c for c in cands.values() if not c["started"]),
                          key=lambda c: (c["created"] or datetime.max, c["po"]))
        explicit = False

    # ---------------- routing (product_workflow_mapping) + times ----------------
    # child -> main by serial number; the child POs that are NOT in this schedule are still needed (in process / what-if)
    serial_links, serial_unmatched = _serial_links(db, cands, role_of, child_of, [c["po"] for c in selected])
    sel_pos = {c["po"] for c in selected}
    outside_child_parts = {l["child_part"] for c in selected for l in serial_links.get(c["po"], [])
                           if l["child_po"] not in sel_pos and l["child_part"]}
    part_numbers = {c["part"] for c in selected if c["part"]} | outside_child_parts
    routing: Dict[str, list] = defaultdict(list)
    times: Dict[tuple, list] = defaultdict(list)
    if part_numbers:
        for r in db.query(ProductWorkflowMapping).options(joinedload(ProductWorkflowMapping.process_detail)
                ).filter(ProductWorkflowMapping.product_part_number.in_(part_numbers)
                ).order_by(ProductWorkflowMapping.product_part_number, ProductWorkflowMapping.step_sequence,
                           ProductWorkflowMapping.id).all():
            routing[r.product_part_number].append(r)
        tq = db.query(PartProcessTime).filter(PartProcessTime.part_no.in_(part_numbers))
        if plant:
            tq = tq.filter(PartProcessTime.plant == plant)
        for r in tq.all():
            times[(r.part_no, r.process_id)].append(r)
    other = "sap" if time_source == "actual" else "actual"

    def time_row(part: str, sid: int):
        rows = times.get((part, sid), [])
        if not rows:
            return None
        pref = plant or (products[part].plant_code if part in products else None)
        return next((r for r in rows if r.plant == pref), rows[0])

    def hours_per_unit(part: str, step) -> Tuple[Optional[float], str]:
        """Hours for one unit (SERIES) / one batch (BATCH) = base time + machine hours."""
        row = time_row(part, step.flow_step_id)
        mh = max(float(getattr(row, "machine_hours", 0) or 0), 0.0) if row else 0.0
        base, src = None, "none"
        if row:
            for s in (time_source, other):
                val = row.actual_time if s == "actual" else row.sap_time
                if val and val > 0:
                    base, src = float(val), f"part_process_time.{s}"
                    break
        if base is None and getattr(step, "process_time_seconds", None) and step.process_time_seconds > 0:
            base, src = step.process_time_seconds / 3600.0, "routing"
        if base is None:
            cap = find_cap(step_name(step))
            if cap and cap.manufacturing_time_mins and cap.manufacturing_time_mins > 0:
                base, src = float(cap.manufacturing_time_mins) / 60.0, "stage_capacity"
        if base is None and mh <= 0:
            return None, "none"
        return (base or 0.0) + mh, src + (" + machine_hours" if mh > 0 else "")

    def batch_size_for(part: str, sid: int) -> int:
        row = time_row(part, sid)
        if row and getattr(row, "batch_size", None) and row.batch_size > 0:
            return int(row.batch_size)
        return max(int((cfg[sid].batch_size if sid in cfg else 0) or DEFAULT_BATCH_SIZE), 1)

    def capacity_for(names: List[str]) -> Optional[Tuple[int, float]]:
        for n in names:
            c = find_cap(n)
            if c:
                sh = int(c.shifts_per_day or 0)
                hp = float(c.hours_per_shift or 0)
                return (sh if sh > 0 else DEFAULT_SHIFTS), (hp if hp > 0 else DEFAULT_HOURS_PER_SHIFT)
        return None

    # ---------------- operations of a part (its flow, with the line steps merged) ----------------
    ops_cache: Dict[str, List[Dict[str, Any]]] = {}

    def ops_for(part: str) -> List[Dict[str, Any]]:
        if part in ops_cache:
            return ops_cache[part]
        steps = routing.get(part, [])
        ops, done = [], set()
        for st in steps:
            g = line_of_name.get(_key(step_name(st)))
            if g:
                if g in done:
                    continue
                done.add(g)
                members = [x for x in steps if line_of_name.get(_key(step_name(x))) == g]
                ops.append({"key": f"LINE-{g}", "line": g, "steps": members})
            else:
                ops.append({"key": f"STEP-{st.flow_step_id}", "line": None, "steps": [st]})
        ops_cache[part] = ops
        return ops

    # ---------------- build PO objects ----------------
    pos: List[Dict[str, Any]] = []
    for c in selected:
        part, po_no = c["part"], c["po"]
        steps = routing.get(part or "", [])
        if not steps or c["qty"] <= 0:
            msg = (f"PO {po_no}: part {part} has no flow in product_workflow_mapping" if not steps
                   else f"PO {po_no}: quantity is 0")
            if explicit:
                raise PoGanttError(422, msg)
            warnings.append(msg + " - not scheduled")
            continue
        pos.append({"po": po_no, "part": part, "qty": c["qty"], "ops": ops_for(part), "idx": len(pos) + 1,
                    "role": role_of(part)})
    if not pos:
        raise PoGanttError(404, "No production orders to schedule")
    for p in pos:
        p["label"] = f"B{p['idx']}" if label_mode == "seq" else p["po"]
    label_idx = {p["label"]: p["idx"] for p in pos}
    label_role = {p["label"]: p["role"] for p in pos}

    # ---------------- machine down-time (breakdowns + preventive maintenance) ----------------
    start_day = cal.first_working_day(start_date or today)
    start_dt = datetime.combine(start_day, time.min) + timedelta(hours=shift_start)
    downtime = _load_downtime(db, machine_info, start_dt, now, warnings)
    blocks_of = {mid: _merge((e["start"], e["end"]) for e in evs) for mid, evs in downtime.items()}
    material = _load_consumable_blocks(db, now, start_dt, warnings)     # flow_step_id -> consumable shortages

    # ---------------- stations ----------------
    stations: Dict[str, Station] = {}
    cap_missing: List[str] = []

    def make_station(op: Dict[str, Any]) -> Station:
        key = op["key"]
        if key in stations:
            return stations[key]
        members = op["steps"]
        sids = [m.flow_step_id for m in members]
        if op["line"]:
            g = op["line"]
            s = Station(key, g, "LINE", sids)
            s.steps = [step_name(m) for m in members]
            s.mode = "LINE"
            mach_of = {m.flow_step_id: machines_for_step(m.flow_step_id, step_name(m)) for m in members}
            with_eq = [(m.flow_step_id, step_name(m)) for m in members if mach_of[m.flow_step_id]]
            n = min(len(mach_of[i]) for i, _ in with_eq) if with_eq else 1   # as parallel as its narrowest step
            for i in range(n):
                phys = [(mach_of[sid][i], nm) for sid, nm in with_eq]
                s.options.append({"name": g if n == 1 else f"{g} #{i + 1}",
                                  "resources": [m for m, _ in phys] or [f"LINE-{g}-{i}"], "phys": phys})
            s.real_machines = [(mid, nm) for sid, nm in with_eq for mid in mach_of[sid]]
            s.setup = max([float(cfg[i].setup_minutes or 0) for i in sids if i in cfg], default=0.0)
            s.operators = max(operators_per_shift(i) for i in sids)
            last = cfg.get(sids[-1])
            names = [g] + s.steps
        else:
            sid = sids[0]
            s = Station(key, step_name(members[0]), "STEP", sids)
            s.mode = "BATCH" if is_batch.get(sid) else "SERIES"
            last = cfg.get(sid)
            if last:
                s.batch_size = max(int(last.batch_size or DEFAULT_BATCH_SIZE), 1)
                s.setup = float(last.setup_minutes or 0)
            mids = machines_for_step(sid, s.name)
            rmode = (str(getattr(last, "resource_mode", None) or "AUTO")).upper() if last else "AUTO"
            if rmode == "MANUAL":                                   # stage_schedule_config.resource_mode forces manual
                mids = []
            elif rmode == "MACHINE" and not mids:
                warnings.append(f"{s.name}: resource_mode is MACHINE but no machine is mapped in equipment_details")
            if mids:
                s.options = [{"name": mid, "resources": [mid], "phys": [(mid, s.name)]} for mid in mids]
                s.real_machines = [(mid, s.name) for mid in mids]
            else:
                slots = max(int(MANUAL_PARALLEL_SLOTS), 1)          # no machine -> people: several POs can run side by side
                s.options = [{"name": "", "resources": [f"NO-MACHINE-{sid}-{k}"], "phys": []} for k in range(slots)]
            s.operators = operators_per_shift(sid)
            names = [s.name]
        # a consumable shortage of ANY step stops the whole process (SMT LINE: the whole line), machine or not
        s.material = [e for i in sids for e in material.get(i, [])]
        mat_blocks = [(e["start"], e["end"]) for e in s.material]
        for o in s.options:
            o["blocks"] = _merge([b for r in o["resources"] for b in blocks_of.get(r, [])] + mat_blocks)
        if last:
            s.cooldown = float(last.cooldown_minutes or 0)
            s.cd_working_only = bool(last.cooldown_working_time_only)
            s.next_day_release = bool(last.next_day_release) and bool(is_batch.get(sids[-1]))
        got = capacity_for(names)
        if got:
            s.shifts, s.hps = got
        if not got:
            cap_missing.append(s.name)
        s.cap_min = min(s.shifts * s.hps * 60.0, day_cap)
        stations[key] = s
        return s

    for p in pos:
        for op in p["ops"]:
            make_station(op)
    no_type = sorted({f"{step_name(m)} (step {m.flow_step_id})" for p in pos for op in p["ops"] for m in op["steps"]
                      if not op["line"] and batch_rule.get(m.flow_step_id, (None, ""))[0] is None})
    if no_type:
        warnings.append("No process_type row (batch / series not set) - scheduled as series, one PO block: "
                        + ", ".join(no_type) + ". If one of them is a batch process, add it to process_type with "
                        "process_type_batch = true (stage_id = flow_step_id). Check: /schedule/po-gantt/process-check")
    for cpart in outside_child_parts:                   # child POs outside the schedule (only for estimates)
        for op in ops_for(cpart):
            make_station(op)
    if cap_missing:
        warnings.append(f"No stage_capacity row matches: {', '.join(dict.fromkeys(cap_missing))} - default "
                        f"{DEFAULT_SHIFTS} shifts x {DEFAULT_HOURS_PER_SHIFT:g} h used (add the process name to stage_capacity)")

    # ---------------- run time of one operation ----------------
    missing_time: Dict[str, List[str]] = defaultdict(list)

    def step_minutes(part: str, st, qty: int) -> Optional[Tuple[float, float]]:
        """(minutes for the whole PO, minutes for the first board / batch) of one routing step."""
        hrs, _src = hours_per_unit(part, st)
        if hrs is None:
            return None
        t = hrs * 60.0
        sid = st.flow_step_id
        if is_batch.get(sid):
            bs = batch_size_for(part, sid)
            return math.ceil(qty / bs) * t, t
        return qty * t, t

    def op_minutes_and_parts(p: Dict[str, Any], op: Dict[str, Any], s: Station):
        """Minutes of one operation for the whole PO, and (PO minutes, first board / batch minutes) of each step in it.
        SMT LINE: the steps run one after the other, so the line time is the SUM of its steps."""
        parts = []
        for st in op["steps"]:
            m = step_minutes(p["part"], st, p["qty"])
            if m is None:
                missing_time[p["part"]].append(step_name(st))
                m = (FALLBACK_MINUTES, FALLBACK_MINUTES)
            parts.append(m)
        total = sum(m[0] for m in parts) if s.kind == "LINE" else parts[0][0]
        return max(total + s.setup, 1.0), parts

    # ---------------- child PO -> main PO ----------------
    # 1. by SERIAL number: the main PCB needs the child PCB with the same serial (as the assign step checks it).
    #    child PO in this schedule          -> the main PO waits for it
    #    child PO outside, PCBs done        -> nothing to wait for
    #    child PO outside, PCBs in process  -> the main PO waits for the estimated end of the child (rest of its flow)
    #    child PO outside, NOT assigned     -> the main PO is scheduled without waiting (FORCED) + "assign the child on
    #                                          day X -> main can start on day Y" message
    # 2. main POs without any serial match: first come, first served by quantity (as before).
    depends_on: Dict[str, List[str]] = defaultdict(list)
    link_by: Dict[str, str] = {}                                    # main po -> "serial" | "quantity"
    outside_links: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # main po -> child links outside the schedule
    by_part: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in pos:
        by_part[p["part"]].append(p)
    in_plan = {p["po"] for p in pos}
    taken_by_serial: Dict[str, int] = defaultdict(int)             # child po -> PCBs already linked by serial
    for m in pos:
        links = serial_links.get(m["po"], [])
        if not links:
            continue
        link_by[m["po"]] = "serial"
        for l in links:
            taken_by_serial[l["child_po"]] += l["pcbs"]
            if l["child_po"] in in_plan:
                depends_on[m["po"]].append(l["child_po"])
            else:
                outside_links[m["po"]].append(l)
        if serial_unmatched.get(m["po"]):
            warnings.append(f"PO {m['po']} ({m['label']}): {serial_unmatched[m['po']]} main PCB(s) have no child PCB with "
                            f"the same serial number - those child PCBs are assumed in stock")
    for main_pn, child_pn in child_of.items():
        mains = [m for m in by_part.get(main_pn, []) if m["po"] not in link_by]
        childs = by_part.get(child_pn, [])
        if not mains:
            continue
        if not childs:
            warnings.append(f"Part {main_pn}: no child PO ({child_pn}) loaded and no child PCB with the same serial - "
                            f"child PCBs assumed in stock, main PO(s) {', '.join(m['label'] for m in mains)} start right away")
            continue
        supply, run = [], 0
        for c in childs:
            free = max(c["qty"] - taken_by_serial.get(c["po"], 0), 0)
            if free:
                supply.append((run, run + free, c["po"]))
                run += free
        need = 0
        for m in mains:
            lo, hi = need, need + m["qty"]
            need = hi
            depends_on[m["po"]] = [cpo for (a, b, cpo) in supply if a < hi and b > lo]
            link_by[m["po"]] = "quantity"
            if hi > run:
                warnings.append(f"PO {m['po']}: needs more child PCBs than the loaded child POs provide - rest assumed in stock")

    def depth(part: str) -> int:
        d = 0
        while part in child_of and d < 10:
            part, d = child_of[part], d + 1
        return d

    # ---------------- chains: a child PO and the main PO(s) it feeds belong together ----------------
    parent = {p["po"]: p["po"] for p in pos}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for m_po, c_pos in depends_on.items():
        for c_po in c_pos:
            if c_po in parent and m_po in parent:
                parent[find(c_po)] = find(m_po)
    chain_first: Dict[str, int] = {}
    for p in pos:
        r = find(p["po"])
        chain_first[r] = min(chain_first.get(r, p["idx"]), p["idx"])
    chain_key = {p["po"]: chain_first[find(p["po"])] for p in pos}        # chain = its first PO (load order)
    chain_no = {k: i + 1 for i, k in enumerate(sorted(set(chain_key.values())))}

    # ---------------- schedule (finite capacity, machines shared, down-time skipped) ----------------
    default_cap = min(DEFAULT_SHIFTS * DEFAULT_HOURS_PER_SHIFT * 60.0, day_cap)
    busy: Dict[str, List[Tuple[datetime, datetime, str]]] = defaultdict(list)   # resource -> runs already booked (first-fit gaps)
    usage: Dict[str, Dict[date, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    machine_segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    runs: Dict[Tuple[str, str], List[datetime]] = {}
    run_list: List[Dict[str, Any]] = []
    po_ready: Dict[str, datetime] = {}
    po_span: Dict[str, List[datetime]] = {}
    route: Dict[str, List[str]] = defaultdict(list)
    delayed_by_downtime: Dict[str, set] = defaultdict(set)

    # placement order: a main PO is placed immediately after the last child PO that feeds it (child, main, child, main ...)
    # - NOT "all children first", which pushed every main behind all the child work on shared machines.
    by_po = {p["po"]: p for p in pos}
    kids = {m: [c for c in cs if c in by_po] for m, cs in depends_on.items()}
    feeds: Dict[str, List[str]] = defaultdict(list)
    for m_po, cs in kids.items():
        for c_po in cs:
            feeds[c_po].append(m_po)
    order: List[Dict[str, Any]] = []
    placed_po: set = set()

    def emit(p: Dict[str, Any]) -> None:
        if p["po"] in placed_po:
            return
        placed_po.add(p["po"])
        for c_po in kids.get(p["po"], []):
            emit(by_po[c_po])
        order.append(p)
        for m_po in feeds.get(p["po"], []):
            if m_po not in placed_po and all(c in placed_po for c in kids[m_po]):
                emit(by_po[m_po])

    for p in sorted(pos, key=lambda x: x["idx"]):
        emit(p)
    handoff: Dict[str, Dict[str, Any]] = {}

    open_batches: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # station key -> batches already booked (for co-loading)

    def book(st: Station, ready: datetime, minutes: float, one_day: bool = False, dry=None):
        """First fit on every machine (option) of the station: the earliest start >= ready where the whole run clears the runs
        already booked there and the machine's down-time. The machine that FINISHES first wins.
        one_day = the run must sit inside one free stretch of one working day (SMT LINE, an oven batch).
        dry = bookings of a trial run (estimates) - looked at, but never kept.
        Returns (mi, o, start, end, end_day, pieces, fits_in_one_day, blocked_by)."""
        best = None
        for mi, o in enumerate(st.options):
            booked = sorted(iv for r in o["resources"] for iv in busy[r] + (dry.get(r, []) if dry is not None else []))
            s0, first_block = ready, None
            for _ in range(100000):
                if one_day:
                    s, e, eday, segs, same = cal.place_within_day(s0, minutes, st.cap_min, o["blocks"])
                else:
                    s, e, eday, segs = cal.consume(s0, minutes, st.cap_min, o["blocks"])
                    same = True
                clash = next((iv for iv in booked if iv[0] < e and iv[1] > s), None)
                if clash is None:
                    break
                if first_block is None:
                    first_block = clash[2]
                s0 = clash[1]
            else:
                raise PoGanttError(500, f"No free slot found on {o['name'] or st.name}")
            if best is None or e < best[3]:
                best = (mi, o, s, e, eday, segs, same, first_block)
        return best

    def reserve(o: Dict[str, Any], s: datetime, e: datetime, label: str, dry=None) -> None:
        for r in o["resources"]:
            (busy if dry is None else dry).setdefault(r, []).append((s, e, label))

    def add_segment(p: Dict[str, Any], st: Station, row_id: str, mi: int, o: Dict[str, Any], piece, s: datetime, e: datetime,
                    phys: List[Tuple[str, str]], extra: Dict[str, Any]) -> None:
        """One bar of the Gantt (one PO, one day, one machine / step) + the same bar on each machine row."""
        d, a, b, m = piece
        seg = {
            "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"], "quantity": p["qty"],
            "machine": o["name"], "machine_no": mi, "machines": [mid for mid, _ in phys], "operation": st.name,
            "row_id": row_id, "date": d.isoformat(), "start": _iso(a), "end": _iso(b), "minutes": round(m, 1),
            "run_start": _iso(s), "run_end": _iso(e),
        }
        seg.update(extra)
        segments[st.key].append(seg)
        for mid, nm in phys:
            machine_segments[mid].append({**seg, "machine": mid, "step": nm})
        usage[st.key][d][p["label"]] += m

    def split_steps(segs, step_mins: List[float]):
        """Cut a line run [(day, a, b, minutes)] into its steps, one after the other -> [(step_index, (day, a, b, minutes))]."""
        out, i, left, n = [], 0, step_mins[0], len(step_mins)
        for d, a, b, m in segs:
            while m > 1e-9:
                while left <= 1e-9 and i < n - 1:          # a step with no time: go to the next one
                    i += 1
                    left = step_mins[i]
                use = m if i == n - 1 else min(m, left)    # the last step takes whatever is left (rounding)
                out.append((i, (d, a, a + timedelta(minutes=use), use)))
                a, m, left = a + timedelta(minutes=use), m - use, left - use
        return out

    def place_batches(p: Dict[str, Any], st: Station, parts, ready: datetime, row_id: str, dry=None):
        """Batch process: batch_size PCBs go in together and come out together (one bar per batch).
        70 PCBs / batch 30 -> 30 + 30 + 10. Batches of one PO run side by side on free ovens.
        A batch of the SAME part that still has room, is not started before this PO is ready and does not finish later
        than a new batch would, takes the PCBs instead (co-loading). A trial run (dry) never co-loads.
        Returns (start, end, end_day, machine names, blocked_by)."""
        size = batch_size_for(p["part"], st.step_ids[0])
        per_batch = parts[0][1]                                   # minutes for one batch (time of a batch, not per PCB)
        left, mine, blocked_by = p["qty"], [], None
        while left > 0:
            mins = per_batch + (st.setup if not mine else 0.0)
            mi, o, s, e, eday, segs, same, blocked = book(st, ready, mins, one_day=True, dry=dry)
            join = None
            if dry is None:
                join = min((b for b in open_batches[st.key]
                            if b["part"] == p["part"] and b["room"] > 0 and b["start"] >= ready and b["end"] <= e),
                           key=lambda b: b["start"], default=None)
            if join:
                take = min(left, join["room"])
                join["room"] -= take
                mi, o, s, e, eday, segs = join["mi"], join["o"], join["start"], join["end"], join["eday"], join["segs"]
                together = join["together"]
            else:
                take = min(left, size)
                reserve(o, s, e, p["label"], dry)
                together = []
                if dry is None:
                    open_batches[st.key].append({"part": p["part"], "room": size - take, "start": s, "end": e, "eday": eday,
                                                 "mi": mi, "o": o, "segs": segs, "together": together})
                    if blocked_by is None:
                        blocked_by = blocked
                    if o["blocks"] and any(a < e and b > ready for a, b in o["blocks"]):
                        delayed_by_downtime[p["po"]].add(st.name)
                    if not same:
                        warnings.append(f"PO {p['po']} ({p['label']}): one {st.name} batch needs {mins / 60:.1f} h, more than "
                                        f"one working day ({st.cap_min / 60:g} h) - the batch is spread over several days")
            together.append({"label": p["label"], "po": p["po"], "qty": take})   # every PO inside this batch (shared list)
            left -= take
            mine.append((mi, o, s, e, eday, segs, take, mins, together))
        if dry is None:
            for k, (mi, o, s, e, eday, segs, take, mins, together) in enumerate(mine, start=1):
                info = {"no": k, "count": len(mine), "qty": take, "size": size, "minutes": round(mins, 1),
                        "start": _iso(s), "end": _iso(e), "together": together}
                for piece in segs:
                    add_segment(p, st, row_id, mi, o, piece, s, e, o["phys"], {"batch": info})
        s_all, e_all = min(b[2] for b in mine), max(b[3] for b in mine)
        last = max(mine, key=lambda b: b[3])
        names = list(dict.fromkeys(b[1]["name"] for b in mine if b[1]["name"]))
        return s_all, e_all, last[4], ", ".join(names), blocked_by

    def run_po(p: Dict[str, Any], ready: datetime, dry=None) -> Tuple[Optional[datetime], datetime]:
        """Place a PO through its operations (p["ops"]), one after the other, from `ready`.
        dry = None: book it into the schedule. dry = {}: a trial run on top of the schedule (estimate only, nothing kept).
        Returns (start of its first operation, when the PO is ready for the next step / the main PO)."""
        ready0, first_start = ready, None
        for seq, op in enumerate(p["ops"], start=1):
            st = stations[op["key"]]
            minutes, parts = op_minutes_and_parts(p, op, st)
            row_id = f"{p['role']}:{st.key}"

            if st.mode == "BATCH":
                # -------- batch process: one bar per batch --------
                s, e, eday, machine_text, blocked_by = place_batches(p, st, parts, ready, row_id, dry)
                phys_ids = []
            else:
                # -------- normal process / SMT LINE: the whole PO in one run --------
                mi, o, s, e, eday, segs, same, blocked_by = book(st, ready, minutes, one_day=(st.kind == "LINE"), dry=dry)
                reserve(o, s, e, p["label"], dry)
                machine_text = o["name"]
                phys_ids = [m for m, _ in o["phys"]]
                if dry is None:
                    if o["blocks"] and any(a < e and b > ready for a, b in o["blocks"]):
                        delayed_by_downtime[p["po"]].add(st.name)
                    if not same:
                        warnings.append(f"PO {p['po']} ({p['label']}): {st.name} needs {minutes / 60:.1f} h, more than one "
                                        f"working day ({st.cap_min / 60:g} h) - the run is spread over several days")
                    if st.kind == "LINE":
                        # the line steps run ONE AFTER THE OTHER (step 1 for the whole PO, then step 2 ...), all inside the day
                        step_mins = [parts[i][0] + (st.setup if i == 0 else 0.0) for i in range(len(parts))]
                        pieces = split_steps(segs, step_mins)
                        for i, name in enumerate(st.steps):
                            mine = [pc for k, pc in pieces if k == i]
                            if not mine:
                                continue
                            step_phys = [(mid, nm) for mid, nm in o["phys"] if nm == name]
                            extra = {"step": name, "step_no": i + 1, "step_count": len(st.steps),
                                     "step_start": _iso(mine[0][1]), "step_end": _iso(mine[-1][2]),
                                     "step_minutes": round(step_mins[i], 1)}
                            if step_phys:
                                extra["machine"] = step_phys[0][0]
                            for piece in mine:
                                add_segment(p, st, row_id, mi, o, piece, s, e, step_phys, extra)
                    else:
                        for piece in segs:
                            add_segment(p, st, row_id, mi, o, piece, s, e, o["phys"], {})

            first_start = s if first_start is None else first_start
            if dry is None:
                if seq == 1 and any(c in po_ready for c in depends_on.get(p["po"], [])):   # main PO: how soon after its child?
                    wait_h = max((s - ready0).total_seconds() / 3600.0, 0.0)
                    handoff[p["po"]] = {"child_ready": _iso(ready0), "main_start": _iso(s), "wait_hours": round(wait_h, 1),
                                        "station": st.name, "machine": machine_text, "blocked_by": blocked_by}
                    if wait_h > HANDOFF_WARN_HOURS:
                        warnings.append(f"PO {p['po']} ({p['label']}) starts {wait_h / 24:.1f} days after its child PO "
                                        f"finished: {st.name} is busy" + (f" with PO {blocked_by}" if blocked_by else ""))
                span = runs.setdefault((st.key, p["label"]), [s, e])
                span[0], span[1] = min(span[0], s), max(span[1], e)
                ps = po_span.setdefault(p["po"], [s, e])
                ps[0], ps[1] = min(ps[0], s), max(ps[1], e)
                if row_id not in route[p["po"]]:
                    route[p["po"]].append(row_id)
                run_list.append({"seq": seq, "label": p["label"], "po": p["po"], "part": p["part"], "role": p["role"],
                                 "quantity": p["qty"], "row_id": row_id, "station": st.name, "kind": st.kind,
                                 "flow_step_ids": st.step_ids, "machine": machine_text, "machines": phys_ids,
                                 "start": _iso(s), "end": _iso(e), "minutes": round(minutes, 1)})

            ready = e                                            # when the PO may enter the next process
            if st.next_day_release:
                ready = datetime.combine(cal.first_working_day(eday + timedelta(days=1)), time.min) + timedelta(hours=shift_start)
            if st.cooldown > 0:
                if st.cd_working_only:
                    ready = cal.consume(ready, st.cooldown, default_cap)[1]
                else:
                    ready = ready + timedelta(minutes=st.cooldown)
        return first_start, ready

    def outside_child(l: Dict[str, Any], qty: int, from_step: bool) -> Dict[str, Any]:
        """A child PO that is not in this schedule, as a PO for a trial run: its whole flow, or (in process) the rest of
        its flow from the earliest step its PCBs are at."""
        ops = ops_for(l["child_part"])
        if from_step and l["steps"]:
            at = [i for i, op in enumerate(ops) if any(m.flow_step_id in l["steps"] for m in op["steps"])]
            ops = ops[min(at):] if at else ops
        return {"po": l["child_po"], "label": l["child_po"], "part": l["child_part"], "qty": qty, "role": "CHILD", "ops": ops}

    child_notes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)   # main po -> what the child outside the plan means
    forced: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []          # (main PO, child link) scheduled without waiting

    for p in order:
        waits = [po_ready[c] for c in depends_on.get(p["po"], []) if c in po_ready]
        for l in outside_links.get(p["po"], []):
            note = {"child_po": l["child_po"], "child_part": l["child_part"], "pcbs": l["pcbs"], "done": l["done"],
                    "in_progress": l["in_progress"], "not_assigned": l["not_assigned"], "in_plan": False}
            if l["in_progress"]:
                # child PCBs are on the floor: the main waits for the rest of the child flow (estimate, nothing booked)
                trial = outside_child(l, l["in_progress"], from_step=True)
                if trial["ops"]:
                    _, est = run_po(trial, max(now, start_dt), dry={})
                    waits.append(est)
                    note["child_ready_estimate"] = _iso(est)
                    warnings.append(f"PO {p['po']} ({p['label']}): {l['in_progress']} child PCB(s) of PO {l['child_po']} are "
                                    f"still in process - estimated done {est:%d-%m-%Y %H:%M}, the main PO waits for that")
            if l["not_assigned"]:
                note["forced"] = True
                forced.append((p, l))
            child_notes[p["po"]].append(note)
        _, po_ready[p["po"]] = run_po(p, max([start_dt] + waits))

    # child not assigned -> main was scheduled without waiting. What if the child is assigned on the first working day?
    for p, l in forced:
        trial = outside_child(l, l["not_assigned"], from_step=False)
        note = next(n for n in child_notes[p["po"]] if n["child_po"] == l["child_po"])
        main_start = po_span[p["po"]][0]
        if not trial["ops"]:
            warnings.append(f"PO {p['po']} ({p['label']}): child PO {l['child_po']} is not assigned yet and its part "
                            f"{l['child_part']} has no flow - main PO scheduled without waiting for it (forced)")
            continue
        c_start, c_end = run_po(trial, start_dt, dry={})
        note.update({"assign_on": _iso(c_start), "child_done": _iso(c_end), "main_can_start": _iso(c_end),
                     "main_planned_start": _iso(main_start)})
        warnings.append(
            f"PO {p['po']} ({p['label']}): child PO {l['child_po']} ({l['not_assigned']} PCB(s)) is not assigned yet - the "
            f"main PO is scheduled without waiting for it (forced, from {main_start:%d-%m-%Y %H:%M}). If child PO "
            f"{l['child_po']} is assigned on {c_start:%d-%m-%Y}, it is done by {c_end:%d-%m-%Y %H:%M} and PO {p['po']} "
            f"can start from {c_end:%d-%m-%Y %H:%M}"
            + (" - until then its PCBs cannot be assigned (the child must be complete)." if c_end > main_start else "."))

    for part, names in missing_time.items():
        uniq = list(dict.fromkeys(names))
        warnings.append(f"Part {part}: no process time for {len(uniq)} step(s) "
                        f"[{', '.join(uniq[:6])}{'...' if len(uniq) > 6 else ''}] - {FALLBACK_MINUTES:g} min used")
    if delayed_by_downtime:
        warnings.append(f"{len(delayed_by_downtime)} PO(s) were moved around machine breakdowns / maintenance / "
                        f"consumable shortages")

    # ---------------- days ----------------
    used_days = [d for per_day in usage.values() for d in per_day]
    last_day = max(used_days + [start_day])
    days, day_no, working_nos = [], {}, 0
    d = start_day
    while d <= last_day:
        if cal.factor(d) > 0:
            working_nos += 1
            day_no[d] = working_nos
            days.append({"working_day_no": working_nos, "date": d.isoformat(), "weekday": d.strftime("%a"),
                         "is_holiday": False, "off_reason": None})
        elif show_holidays:
            days.append({"working_day_no": None, "date": d.isoformat(), "weekday": d.strftime("%a"),
                         "is_holiday": True, "off_reason": cal.off_reason(d)})
        d += timedelta(days=1)

    # ---------------- rows: CHILD section first, then MAIN; each in flow order ----------------
    def part_sort(pn: str):
        prod = products.get(pn)
        return (_key(prod.product_type_name) if prod else "", pn)

    part_order = sorted({p["part"] for p in pos}, key=part_sort)
    section_rows: Dict[str, List[str]] = {r: [] for r in ROLES}
    parts_by_row: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    for part in part_order:
        role = role_of(part)
        lst, at = section_rows[role], -1
        for op in ops_for(part):                              # merge the flows of several parts in one section
            if op["key"] in lst:
                at = lst.index(op["key"])
            else:
                at += 1
                lst.insert(at, op["key"])
            if part not in parts_by_row[(role, op["key"])]:
                parts_by_row[(role, op["key"])].append(part)
    roles_of_station: Dict[str, set] = defaultdict(set)
    for role, keys in section_rows.items():
        for k in keys:
            roles_of_station[k].add(role)

    def order_labels(labels) -> List[str]:
        return sorted(labels, key=lambda x: label_idx.get(x, 0))

    def cells_for(key: str, role: str) -> List[Dict[str, Any]]:
        s, out = stations[key], []
        for dd, no in day_no.items():
            u = usage.get(key, {}).get(dd)
            if not u:
                continue
            labels = [lb for lb in u if label_role.get(lb) == role]
            if not labels:
                continue
            out.append({"working_day_no": no, "date": dd.isoformat(), "pos": order_labels(labels),
                        "color": ORANGE if len(labels) >= 2 else BLUE,
                        "minutes_used": round(sum(u[lb] for lb in labels), 1),
                        "station_minutes_used": round(sum(u.values()), 1),
                        "capacity_minutes": round(len(s.options) * s.cap_min * cal.factor(dd), 1)})
        return out

    def runs_for(key: str, role: str) -> List[Dict[str, str]]:
        out = [(lb, v) for (k, lb), v in runs.items() if k == key and label_role.get(lb) == role]
        return [{"label": lb, "start": _iso(v[0]), "end": _iso(v[1])}
                for lb, v in sorted(out, key=lambda kv: (kv[1][0], label_idx.get(kv[0], 0)))]

    def station_downtime(s: Station) -> List[Dict[str, Any]]:
        step_of = {m: nm for m, nm in s.real_machines}                 # SMT LINE: which step the machine belongs to
        evs = [_dt_json({**e, "machine_name": machine_info.get(mid, {}).get("name", mid),
                         "step": step_of[mid] if s.kind == "LINE" else None})
               for mid in dict.fromkeys(m for m, _ in s.real_machines) for e in downtime.get(mid, [])]
        sname = dict(zip(s.step_ids, s.steps)) if s.kind == "LINE" else {}
        evs += [_dt_json({**e, "process": s.name, "step": sname.get(e["stage_id"])}) for e in s.material]
        return sorted(evs, key=lambda e: e["start"])

    rows: List[Dict[str, Any]] = []
    for role in ROLES:
        for key in section_rows[role]:
            s = stations[key]
            parts = parts_by_row[(role, key)]
            real = list(dict.fromkeys(m for m, _ in s.real_machines))
            rows.append({
                "row_id": f"{role}:{key}", "station_id": key, "name": s.name, "kind": s.kind, "section": role,
                "role": role, "part_number": parts[0], "part_numbers": parts,
                "flow_step_ids": s.step_ids, "steps": s.steps,
                "shifts": s.shifts, "mins_per_shift": int(s.hps * 60), "machines": len(s.options),
                "machine_names": s.machines, "has_machine": bool(real), "real_machines": real,
                "real_machine_names": [machine_info[m]["name"] for m in real],
                "operators_per_shift": s.operators, "process_mode": s.mode, "is_batch": s.mode == "BATCH",
                "batch_why": batch_rule.get(s.step_ids[0], (None, ""))[1] if s.kind != "LINE" else None,
                "batch_size": batch_size_for(parts[0], s.step_ids[0]) if s.mode == "BATCH" else None,
                "day_end_hour": round(shift_start + s.cap_min / 60.0, 2),
                "shared_with": [r for r in ROLES if r != role and r in roles_of_station[key]],
                "cells": cells_for(key, role), "po_runs": runs_for(key, role),
                "segments": [sg for sg in segments.get(key, []) if sg["role"] == role],
                "downtime": station_downtime(s),
            })

    # ---------------- machine rows (PO on Machines), grouped by process in flow order ----------------
    machine_rows: List[Dict[str, Any]] = []
    placed: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        s = stations[row["station_id"]]
        for mid, step in s.real_machines:
            if mid in placed:
                if s.name not in placed[mid]["processes"]:
                    placed[mid]["processes"].append(s.name)
                if row["role"] not in placed[mid]["roles"]:
                    placed[mid]["roles"].append(row["role"])
                continue
            info = machine_info.get(mid, {"name": mid})
            segs = sorted(machine_segments.get(mid, []), key=lambda x: x["start"])
            mr = {
                "row_id": f"M:{mid}", "machine_id": mid, "name": info.get("name") or mid, "eqpt_no": info.get("eqpt_no"),
                "make": info.get("make"), "model": info.get("model"), "workcenter": info.get("workcenter"),
                "group": s.key, "group_name": s.name, "group_kind": s.kind, "step": step if s.kind == "LINE" else None,
                "processes": [s.name], "roles": [row["role"]], "shifts": s.shifts,
                "day_end_hour": round(shift_start + s.cap_min / 60.0, 2), "is_batch": s.mode == "BATCH",
                "segments": segs, "downtime": [_dt_json(e) for e in downtime.get(mid, [])],
                # a batch shared by 2 POs is 2 bars at the same time - count the oven time once
                "busy_minutes": round(sum({(x["start"], x["end"]): x["minutes"] for x in segs}.values()), 1),
            }
            placed[mid] = mr
            machine_rows.append(mr)
    manual_processes = [r["name"] for r in rows if not r["has_machine"]]
    if manual_processes:
        warnings.append("No machine mapped in equipment_details for: " + ", ".join(
            dict.fromkeys(f"{r['name']} (step {', '.join(str(x) for x in r['flow_step_ids'])})" for r in rows if not r["has_machine"])))

    for s in stations.values():
        for e in s.material:
            warnings.append(f"Consumable not available - {s.name} does not run from {e['start']:%d-%m-%Y %H:%M} to "
                            f"{e['end']:%d-%m-%Y %H:%M}: {e['note']}")

    # most important first: forced main POs, consumable shortages, children still in process
    first = ("is not assigned yet", "Consumable not available", "still in process", "Breakdown repair waits")
    warnings.sort(key=lambda w: next((i for i, k in enumerate(first) if k in w), len(first)))

    all_down = [_dt_json({**e, "machine_name": machine_info.get(mid, {}).get("name", mid)})
                for mid in placed for e in downtime.get(mid, [])]

    day_end = shift_start + max((s.cap_min for s in stations.values()), default=default_cap) / 60.0
    line_text = "; ".join(f"{g} = {', '.join(n)}" for g, n in LINE_GROUPS.items())
    assumptions = [
        "Child / main comes from product_type_master (sub product type); a main part is fed by the child part of the same product type.",
        "Each part follows its flow from product_workflow_mapping (step sequence). Linked child / main POs are scheduled as one chain; "
        "a main PO starts after the child PO(s) that feed it are finished.",
        "Child -> main link by SERIAL number first (PcbData.serialNo, the same check as PCB assignment): the main PCB needs the "
        "child PCB with the same serial. Main POs without a serial match use first come, first served by quantity.",
        "Child PO not in this schedule: PCBs done -> no wait; in process (pcb_assignment.current_step_id) -> the main waits for "
        "the estimated end of the rest of the child flow; NOT assigned -> the main is scheduled without waiting (forced) and "
        "the warning says on which day the child must be assigned and from when the main can really start.",
        "Unit of work is the whole PO quantity; a PO moves through its processes as a block.",
        f"Line processes run inside one working day ({line_text}). The steps run one after the other "
        "(step 1 for the whole PO, then step 2 ...); line time = sum of the step times.",
        "Machines come from equipment_details; the same machine serving several processes is shared between them.",
        "Machine breakdowns (machine_breakdown_logs: until ready date, else + downtime hours, else open = "
        f"{OPEN_BREAKDOWN_HOURS:g} h from now) and pending preventive maintenance (maintenance_schedules: the whole day) "
        "block the machine.",
        "Spares (inventorty_spares): an open breakdown whose machine has a spare out of stock lasts at least the spare's "
        f"procurement lead time (default {DEFAULT_SPARE_LEAD_DAYS} d). A running machine is not blocked by a missing spare (warning only).",
        "Consumables (consumables, by process): out of stock or past shelf life -> the process (all its machines, or the "
        f"process without machine) is blocked for {CONSUMABLE_RESTOCK_DAYS} days; stock that expires blocks it from the day "
        "after expiry. Stock is checked as available yes / no (the table has no use per PCB). Low stock = warning.",
        f"Shifts per process come from stage_capacity (default {DEFAULT_SHIFTS} x {DEFAULT_HOURS_PER_SHIFT:g} h); "
        f"the working day runs {_hm(shift_start)} - {_hm(DAY_END_HOUR)} at most.",
        "Off days: Sundays, 1st and 3rd Saturdays, public holidays and calendar 'Holiday' exceptions; "
        "'Working' reopens a day, 'Half-Day' halves it.",
        f"Time per unit = {'actual' if time_source == 'actual' else 'SAP'} time (fallback to the other, routing, stage_capacity) "
        "+ machine hours of part_process_time.",
        "Batch processes (process_type.process_type_batch): batch size PCBs go in together and come out together - "
        "70 PCBs / batch 30 = 3 batches (30, 30, 10), each one bar, run on free machines side by side. "
        "A batch of the same part with room left takes PCBs of the next PO when that does not delay it. "
        "Batch size = part_process_time.batch_size, else stage_schedule_config.batch_size, else 30.",
        f"Plant filter: only POs, machines and process times of plant {plant or '(all)'}.",
        "Operators per shift is informational; it does not limit the schedule.",
    ]
    return {
        "meta": {
            "plant": plant, "number_of_pos": len(pos), "start_date": start_day.isoformat(), "finish_date": last_day.isoformat(),
            "working_days": working_nos, "time_source": time_source, "label_mode": label_mode,
            "generated_at": _iso(now),
            "params": {"plant": plant, "production_order": [p["po"] for p in pos] if explicit else None,
                       "start_date": start_date.isoformat() if start_date else None, "time_source": time_source,
                       "label_mode": label_mode, "shift_start": shift_start},
            "day_window": {"start_hour": shift_start, "end_hour": round(day_end, 2)},
            "line_groups": {g: list(n) for g, n in LINE_GROUPS.items()},
            "machines_down": len({e["machine"] for e in all_down}),
            "downtime_events": len(all_down),
            "manual_processes": manual_processes,
            "material_shortages": [_dt_json({**e, "process": s.name}) for s in stations.values() for e in s.material],
            "pos": [{"label": p["label"], "production_order": p["po"], "part_number": p["part"], "role": p["role"],
                     "quantity": p["qty"], "depends_on": depends_on.get(p["po"], []), "handoff": handoff.get(p["po"]), "route": route[p["po"]],
                     "chain": chain_no[chain_key[p["po"]]],
                     "link_by": link_by.get(p["po"]),                         # serial | quantity | None (not a main PO)
                     "child_outside": child_notes.get(p["po"], []),           # child POs not in this schedule
                     "forced": any(n.get("forced") for n in child_notes.get(p["po"], [])),
                     "moved_by_downtime": sorted(delayed_by_downtime.get(p["po"], [])),
                     "start": _iso(po_span[p["po"]][0]), "end": _iso(po_span[p["po"]][1])} for p in pos],
        },
        "days": days, "stations": rows, "machines": machine_rows, "downtime": all_down, "runs": run_list,
        "warnings": warnings, "assumptions": assumptions,
    }


# --------------------------------------------------------------------------------------
# Saved plans
# --------------------------------------------------------------------------------------
class PlanSave(BaseModel):
    name: Optional[str] = None
    remarks: Optional[str] = None
    set_baseline: bool = True
    created_by: Optional[str] = None
    plant: Optional[str] = None
    production_order: Optional[List[str]] = None
    start_date: Optional[date] = None
    time_source: str = "actual"
    label_mode: str = "po"
    shift_start: float = DEFAULT_SHIFT_START


def _plan_header(p: SchedulePlan) -> Dict[str, Any]:
    return {"id": p.id, "name": p.name, "plant": p.plant_code, "is_baseline": bool(p.is_baseline), "status": p.status,
            "time_source": p.time_source, "label_mode": p.label_mode,
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "finish_date": p.finish_date.isoformat() if p.finish_date else None,
            "number_of_pos": p.number_of_pos, "working_days": p.working_days, "remarks": p.remarks,
            "created_by": p.created_by, "created_at": _iso(p.created_at), "params": p.params}


def save_plan(db: Session, body: PlanSave) -> Dict[str, Any]:
    """Build the schedule again with the same inputs (so what is stored is consistent) and store it."""
    ensure_plan_tables(db.get_bind())
    result = build_po_gantt(db, body.production_order, body.plant, body.start_date, body.time_source,
                            body.label_mode, True, body.shift_start)
    meta = result["meta"]
    now = datetime.now()
    if body.set_baseline:
        q = db.query(SchedulePlan).filter(SchedulePlan.is_baseline.is_(True))
        q = q.filter(SchedulePlan.plant_code == body.plant) if body.plant else q.filter(SchedulePlan.plant_code.is_(None))
        q.update({SchedulePlan.is_baseline: False}, synchronize_session=False)
    plan = SchedulePlan(
        name=(body.name or "").strip() or f"Plan {body.plant or 'all'} · {now:%d %b %Y %H:%M}",
        plant_code=body.plant, is_baseline=bool(body.set_baseline), status="SAVED",
        time_source=body.time_source, label_mode=body.label_mode,
        start_date=date.fromisoformat(meta["start_date"]), finish_date=date.fromisoformat(meta["finish_date"]),
        number_of_pos=meta["number_of_pos"], working_days=meta["working_days"], params=meta["params"],
        snapshot=result, remarks=body.remarks, created_by=body.created_by, created_at=now,
    )
    db.add(plan)
    db.flush()
    db.add_all([SchedulePlanItem(
        plan_id=plan.id, seq=r["seq"], production_order=r["po"], part_number=r["part"], label=r["label"],
        role=r["role"], quantity=r["quantity"], row_id=r["row_id"], station_name=r["station"], station_kind=r["kind"],
        flow_step_ids=r["flow_step_ids"], machine=r["machine"], machines=r["machines"],
        planned_start=datetime.strptime(r["start"], ISO), planned_end=datetime.strptime(r["end"], ISO),
        run_minutes=r["minutes"]) for r in result["runs"]])
    db.commit()
    return {"plan": _plan_header(plan), "items": len(result["runs"])}


def list_plans(db: Session, plant: Optional[str]) -> Dict[str, Any]:
    ensure_plan_tables(db.get_bind())
    q = db.query(SchedulePlan.id, SchedulePlan.name, SchedulePlan.plant_code, SchedulePlan.is_baseline,
                 SchedulePlan.status, SchedulePlan.start_date, SchedulePlan.finish_date, SchedulePlan.number_of_pos,
                 SchedulePlan.working_days, SchedulePlan.created_by, SchedulePlan.created_at, SchedulePlan.remarks,
                 SchedulePlan.time_source)
    if plant:
        q = q.filter(SchedulePlan.plant_code == plant)
    out = []
    for r in q.order_by(SchedulePlan.created_at.desc(), SchedulePlan.id.desc()).all():
        out.append({"id": r.id, "name": r.name, "plant": r.plant_code, "is_baseline": bool(r.is_baseline),
                    "status": r.status, "start_date": r.start_date.isoformat() if r.start_date else None,
                    "finish_date": r.finish_date.isoformat() if r.finish_date else None,
                    "number_of_pos": r.number_of_pos, "working_days": r.working_days, "created_by": r.created_by,
                    "created_at": _iso(r.created_at), "remarks": r.remarks, "time_source": r.time_source})
    return {"plans": out}


def _get_plan(db: Session, plan_id: int) -> SchedulePlan:
    ensure_plan_tables(db.get_bind())
    p = db.query(SchedulePlan).filter(SchedulePlan.id == plan_id).first()
    if not p:
        raise PoGanttError(404, f"Saved plan {plan_id} not found")
    return p


def set_baseline(db: Session, plan_id: int) -> Dict[str, Any]:
    p = _get_plan(db, plan_id)
    q = db.query(SchedulePlan).filter(SchedulePlan.is_baseline.is_(True), SchedulePlan.id != p.id)
    q = q.filter(SchedulePlan.plant_code == p.plant_code) if p.plant_code else q.filter(SchedulePlan.plant_code.is_(None))
    q.update({SchedulePlan.is_baseline: False}, synchronize_session=False)
    p.is_baseline = True
    db.commit()
    return {"plan": _plan_header(p)}


def delete_plan(db: Session, plan_id: int) -> Dict[str, Any]:
    p = _get_plan(db, plan_id)
    db.query(SchedulePlanItem).filter(SchedulePlanItem.plan_id == p.id).delete(synchronize_session=False)
    db.delete(p)
    db.commit()
    return {"deleted": plan_id}


# --------------------------------------------------------------------------------------
# Actual (what the operators did) and Planned vs Actual
# --------------------------------------------------------------------------------------
_MACHINE_KEYS = ("machine_id", "machineId", "machine", "machine_name", "equipment", "eqpt_no", "equipment_id")


def load_actuals(db: Session, po_numbers: List[str]):
    """Returns (pcb_qty {po: total pieces}, agg {(po, flow_step_id): {...}}) from operator_log, then pcb_process_log
    (via pcb_assignment) for PCB x step pairs operator_log does not have."""
    pos = sorted({_norm(p) for p in po_numbers if p})
    pcbs: Dict[str, Tuple[str, int]] = {}
    serial_to_pcb: Dict[str, str] = {}
    pcb_qty: Dict[str, int] = defaultdict(int)
    norm_col = func.ltrim(func.trim(PcbData.productionOrder), "0")
    for chunk in _chunks(pos):
        for pcb, serial, po, qty in db.query(PcbData.PCBserialNoPartNumber, PcbData.serialNo, PcbData.productionOrder,
                                             PcbData.quantity).filter(norm_col.in_(chunk)).all():
            q = qty if qty and qty > 0 else 1
            n = _norm(po)
            pcbs[pcb] = (n, q)
            pcb_qty[n] += q
            if serial:
                serial_to_pcb.setdefault(serial, pcb)

    events: Dict[Tuple[str, int], Dict[str, Any]] = {}
    keys = list(pcbs)
    for chunk in _chunks(keys):
        for r in db.query(OperatorLog).filter(OperatorLog.PCBserialNoPartNumber.in_(chunk)).all():
            st, en = _parse_dt(r.start_time), _parse_dt(r.end_time)
            if not en and (r.Task_Status or "").strip().lower() in DONE_STATUSES:
                en = st
            if not st and not en:
                continue
            machine = None
            if isinstance(r.log_Data, dict):
                machine = next((str(r.log_Data[k]) for k in _MACHINE_KEYS if r.log_Data.get(k)), None)
            events[(r.PCBserialNoPartNumber, r.current_step_id)] = {
                "start": st or en, "end": en, "operator": r.operator_name or r.operator_staff_no, "machine": machine}

    assign: Dict[int, str] = {}
    lookup = keys + [s for s in serial_to_pcb if s not in pcbs]
    for chunk in _chunks(lookup):
        for aid, pid in db.query(PCBAssignment.assignment_id, PCBAssignment.assigned_pcb_id).filter(
                PCBAssignment.assigned_pcb_id.in_(chunk)).all():
            pcb = pid if pid in pcbs else serial_to_pcb.get(pid)
            if pcb:
                assign[aid] = pcb
    for chunk in _chunks(list(assign)):
        for r in db.query(PCBProcessLog).filter(PCBProcessLog.assignment_id.in_(chunk)).all():
            k = (assign[r.assignment_id], r.flow_step_id)
            if k in events:
                continue
            st, en = _parse_dt(r.start_time), _parse_dt(r.end_time)
            if not en and (r.process_status or "").strip().lower() in DONE_STATUSES:
                en = st
            if not st and not en:
                continue
            events[k] = {"start": st or en, "end": en, "operator": r.assigned_operator_staff_no, "machine": None}

    agg: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for (pcb, sid), ev in events.items():
        po, q = pcbs[pcb]
        a = agg.setdefault((po, sid), {"start": None, "end": None, "done": 0, "wip": 0,
                                       "operators": set(), "machines": set()})
        a["start"] = min(a["start"], ev["start"]) if a["start"] else ev["start"]
        if ev["end"]:
            a["done"] += q
            a["end"] = max(a["end"], ev["end"]) if a["end"] else ev["end"]
        else:
            a["wip"] += q
        if ev["operator"]:
            a["operators"].add(ev["operator"])
        if ev["machine"]:
            a["machines"].add(ev["machine"])
    return pcb_qty, agg


def _status(ps, pe, a_start, a_end, complete, now) -> Tuple[str, Optional[float]]:
    tol = timedelta(minutes=LATE_TOLERANCE_MIN)
    mins = lambda d: round(d.total_seconds() / 60.0, 1)
    if complete:
        return ("DONE_LATE" if a_end > pe + tol else "DONE_ON_TIME"), mins(a_end - pe)
    if a_start:
        return ("RUNNING_LATE" if now > pe + tol else "RUNNING"), (mins(now - pe) if now > pe else None)
    if now > ps + tol:
        return "START_OVERDUE", mins(now - ps)
    return "UPCOMING", None


def compare_plan(db: Session, plan_id: int, now: Optional[datetime] = None) -> Dict[str, Any]:
    plan = _get_plan(db, plan_id)
    snap = plan.snapshot or {}
    now = now or datetime.now()
    runs = snap.get("runs") or []
    if not runs:                                             # a plan saved without runs -> rebuild from items
        runs = [{"seq": i.seq, "label": i.label, "po": i.production_order, "part": i.part_number, "role": i.role,
                 "quantity": i.quantity, "row_id": i.row_id, "station": i.station_name, "kind": i.station_kind,
                 "flow_step_ids": i.flow_step_ids or [], "machine": i.machine, "machines": i.machines or [],
                 "start": _iso(i.planned_start), "end": _iso(i.planned_end), "minutes": i.run_minutes}
                for i in db.query(SchedulePlanItem).filter(SchedulePlanItem.plan_id == plan.id).all()]
    pcb_qty, agg = load_actuals(db, [r["po"] for r in runs])

    by_row: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_po: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in runs:
        ps, pe = datetime.strptime(r["start"], ISO), datetime.strptime(r["end"], ISO)
        total = pcb_qty.get(r["po"]) or r["quantity"] or 1
        acts = [agg.get((r["po"], sid)) for sid in r["flow_step_ids"]]
        got = [a for a in acts if a]
        a_start = min(a["start"] for a in got) if got else None
        done_qty = min((a["done"] if a else 0) for a in acts) if acts else 0
        complete = bool(acts) and all(a and a["done"] >= total for a in acts)
        a_end = max(a["end"] for a in got if a["end"]) if complete else None
        status, var = _status(ps, pe, a_start, a_end, complete, now)
        item = {
            "label": r["label"], "po": r["po"], "part": r["part"], "role": r["role"], "quantity": r["quantity"],
            "seq": r["seq"], "row_id": r["row_id"], "station": r["station"], "machine": r["machine"],
            "planned_start": r["start"], "planned_end": r["end"], "planned_minutes": r["minutes"],
            "actual_start": _iso(a_start), "actual_end": _iso(a_end), "actual_until": _iso(a_end or (now if a_start else None)),
            "done_qty": done_qty, "total_qty": total,
            "wip_qty": max((a["wip"] for a in got), default=0),
            "start_variance_min": round((a_start - ps).total_seconds() / 60.0, 1) if a_start else None,
            "variance_min": var, "status": status,
            "operators": sorted({o for a in got for o in a["operators"]}),
            "actual_machines": sorted({m for a in got for m in a["machines"]}),
        }
        by_row[r["row_id"]].append(item)
        by_po[r["po"]].append(item)

    rows = []
    for st in snap.get("stations", []):
        items = sorted(by_row.get(st["row_id"], []), key=lambda x: x["planned_start"])
        row = {k: st.get(k) for k in ("row_id", "station_id", "name", "kind", "section", "role", "steps",
                                      "part_numbers", "shifts", "has_machine", "real_machine_names",
                                      "machines", "flow_step_ids")}
        row["items"] = items
        rows.append(row)

    po_meta = {p["production_order"]: p for p in snap.get("meta", {}).get("pos", [])}
    pos_out, kpi = [], defaultdict(int)
    for po, items in by_po.items():
        items.sort(key=lambda x: x["seq"])
        ps = min(i["planned_start"] for i in items)
        pe = max(i["planned_end"] for i in items)
        starts = [i["actual_start"] for i in items if i["actual_start"]]
        complete = all(i["status"].startswith("DONE") for i in items)
        a_end = max(i["actual_end"] for i in items) if complete else None
        status, var = _status(datetime.strptime(ps, ISO), datetime.strptime(pe, ISO),
                              datetime.strptime(min(starts), ISO) if starts else None,
                              datetime.strptime(a_end, ISO) if a_end else None, complete, now)
        current = next((i for i in items if not i["status"].startswith("DONE")), None)
        kpi[status] += 1
        m = po_meta.get(po, {})
        pos_out.append({
            "po": po, "label": items[0]["label"], "part": items[0]["part"], "role": items[0]["role"],
            "quantity": items[0]["quantity"], "planned_start": ps, "planned_end": pe,
            "actual_start": min(starts) if starts else None, "actual_end": a_end, "status": status, "variance_min": var,
            "current_process": current["station"] if current else None,
            "current_status": current["status"] if current else None,
            "processes_done": sum(1 for i in items if i["status"].startswith("DONE")), "processes": len(items),
            "late_processes": sum(1 for i in items if i["status"] in ("DONE_LATE", "RUNNING_LATE", "START_OVERDUE")),
            "depends_on": m.get("depends_on", []), "handoff": m.get("handoff"),
        })
    order = {p["production_order"]: i for i, p in enumerate(snap.get("meta", {}).get("pos", []))}
    pos_out.sort(key=lambda p: order.get(p["po"], 10 ** 6))
    process_kpi = defaultdict(int)
    for items in by_row.values():
        for i in items:
            process_kpi[i["status"]] += 1

    actual_ends = [i["actual_until"] for items in by_row.values() for i in items if i["actual_until"]]
    return {
        "plan": _plan_header(plan), "now": _iso(now),
        "days": snap.get("days", []),
        "meta": dict({k: snap.get("meta", {}).get(k) for k in ("day_window", "line_groups", "pos", "start_date",
                                                               "finish_date", "working_days", "number_of_pos")},
                     actual_last=max(actual_ends) if actual_ends else None),
        "rows": rows, "pos": pos_out,
        "kpis": {"pos": dict(kpi), "processes": dict(process_kpi), "total_pos": len(pos_out),
                 "total_runs": sum(len(v) for v in by_row.values())},
    }


# --------------------------------------------------------------------------------------
# Excel export
# --------------------------------------------------------------------------------------
def build_po_gantt_xlsx(result: Dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    font = lambda **kw: Font(name="Arial", size=10, **kw)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    head = PatternFill("solid", start_color="DDE3EE")
    off = PatternFill("solid", start_color="D9D9D9")
    down = PatternFill("solid", start_color="F4CCCC")
    machine_fill = PatternFill("solid", start_color="FFF4DB")
    section_fill = {"CHILD": PatternFill("solid", start_color="D3F9D8"), "MAIN": PatternFill("solid", start_color="D0EBFF")}
    fills = {BLUE: PatternFill("solid", start_color="9FC5E8"), ORANGE: PatternFill("solid", start_color="F6B26B")}
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    days = result["days"]
    last_col = 2 + len(days)

    def header(ws, first_col_title):
        ws.column_dimensions["A"].width = 36
        ws.column_dimensions["B"].width = 12
        for i, label in enumerate(("Working day #", "Date", "Day"), start=1):
            c = ws.cell(row=i, column=1, value=first_col_title if i == 3 else label)
            c.font, c.fill, c.border = font(bold=True), head, border
            ws.cell(row=i, column=2).fill = head
            ws.cell(row=i, column=2).border = border
        for j, d in enumerate(days, start=3):
            ws.column_dimensions[get_column_letter(j)].width = 11
            dt = date.fromisoformat(d["date"])
            vals = ("Off" if d["is_holiday"] else d["working_day_no"], dt.strftime("%d-%b"), d["weekday"])
            for i, v in enumerate(vals, start=1):
                c = ws.cell(row=i, column=j, value=v)
                c.font, c.border, c.alignment = font(bold=(i == 1)), border, center
                c.fill = off if d["is_holiday"] else head
        ws.freeze_panes = "C4"

    def band(ws, r, text, fill):
        for j in range(1, last_col + 1):
            c = ws.cell(row=r, column=j)
            c.fill, c.border = fill, border
        ws.cell(row=r, column=1, value=text).font = font(bold=True)

    def day_cells(ws, r, segs, downs):
        col_of_date = {d["date"]: j for j, d in enumerate(days, start=3)}
        for j, d in enumerate(days, start=3):
            c = ws.cell(row=r, column=j)
            c.border = border
            if d["is_holiday"]:
                c.fill = off
        for e in downs:
            dd = date.fromisoformat(e["start"][:10])
            while dd.isoformat() <= e["end"][:10]:
                j = col_of_date.get(dd.isoformat())
                if j and not (dd.isoformat() == e["end"][:10] and e["end"][11:] == "00:00:00" and e["end"][:10] != e["start"][:10]):
                    c = ws.cell(row=r, column=j, value="DOWN")
                    c.fill, c.font, c.alignment = down, font(bold=True, color="990000"), center
                dd += timedelta(days=1)
        per_day: Dict[str, List[str]] = defaultdict(list)
        for s in segs:
            if s["label"] not in per_day[s["date"]]:
                per_day[s["date"]].append(s["label"])
        for dstr, labels in per_day.items():
            j = col_of_date.get(dstr)
            if not j:
                continue
            c = ws.cell(row=r, column=j, value=" ".join(labels))
            c.fill = fills[ORANGE if len(labels) >= 2 else BLUE]
            c.font, c.alignment = font(bold=True), center

    wb = Workbook()
    ws = wb.active
    ws.title = "PO on Process"
    header(ws, "Process")
    r, current = 4, None
    for st in result["stations"]:
        if st["section"] != current:
            current = st["section"]
            band(ws, r, f"{current} PROCESSES", section_fill.get(current, head))
            r += 1
        name = st["name"] + (f"  ({len(st['steps'])} steps, same day)" if st.get("kind") == "LINE" else "")
        a = ws.cell(row=r, column=1, value=name)
        a.font, a.border = font(bold=True), border
        if st.get("has_machine"):
            a.fill = machine_fill
        b = ws.cell(row=r, column=2, value=f"{st['shifts']} shift" + (f" · {len(st['real_machines'])} m/c" if st.get("real_machines") else ""))
        b.font, b.border, b.alignment = font(), border, center
        day_cells(ws, r, st["segments"], [])
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Legend").font = font(bold=True)
    for k, (txt, fill) in enumerate((("1 PO on the process", fills[BLUE]), ("2 or more POs share the process", fills[ORANGE]),
                                     ("Process with machine(s)", machine_fill)), 1):
        ws.cell(row=r + k, column=1, value=txt).font = font()
        ws.cell(row=r + k, column=2).fill = fill
    r += 5
    for j, h in enumerate(("Label", "Production order", "Part number", "Child / Main", "Quantity", "Start", "End"), start=1):
        c = ws.cell(row=r, column=j, value=h)
        c.font, c.fill, c.border = font(bold=True), head, border
    for k, p in enumerate(result["meta"]["pos"], start=1):
        for j, v in enumerate((p["label"], p["production_order"], p["part_number"], p["role"], p["quantity"],
                               p["start"], p["end"]), start=1):
            c = ws.cell(row=r + k, column=j, value=v)
            c.font, c.border = font(), border

    ws2 = wb.create_sheet("PO on Machines")
    header(ws2, "Machine")
    r, current = 4, None
    for m in result.get("machines", []):
        if m["group"] != current:
            current = m["group"]
            band(ws2, r, m["group_name"], machine_fill)
            r += 1
        a = ws2.cell(row=r, column=1, value=f"{m['name']} ({m['machine_id']})" + (f" · {m['step']}" if m.get("step") else ""))
        a.font, a.border = font(bold=True), border
        b = ws2.cell(row=r, column=2, value=f"{round(m['busy_minutes'] / 60, 1)} h")
        b.font, b.border, b.alignment = font(), border, center
        day_cells(ws2, r, m["segments"], m["downtime"])
        r += 1

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------------------
def create_po_gantt_router(init_db, verify_token=None, engine=None) -> APIRouter:
    """Pass `engine` so machine_hours / batch_size are added to part_process_time and the plan tables are created
    at start-up (otherwise they are created on first use)."""
    if engine is not None:
        ensure_part_process_time_columns(engine)
        try:
            ensure_plan_tables(engine)
        except Exception as exc:
            print(f"[po_gantt] could not create schedule_plan tables: {exc}")
    router = APIRouter()
    deps = [Depends(verify_token)] if verify_token else []

    def _guard(fn, db=None):
        try:
            return fn()
        except PoGanttError as e:
            if db is not None:
                db.rollback()
            raise HTTPException(status_code=e.status_code, detail=e.detail)

    def _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start):
        return _guard(lambda: build_po_gantt(db, production_order, plant, start_date, time_source, label_mode,
                                             show_holidays, shift_start))

    @router.get("/schedule/po-gantt/process-check", dependencies=deps)
    def po_gantt_process_check(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
        return _guard(lambda: process_check(db, plant))

    @router.get("/schedule/po-gantt/plants", dependencies=deps)
    def po_gantt_plants(db: Session = Depends(init_db)):
        return list_plants(db)

    @router.get("/schedule/part-process-time", dependencies=deps)
    def part_process_time_list(plant: Optional[str] = Query(None), part_no: Optional[str] = Query(None),
                               db: Session = Depends(init_db)):
        return list_part_process_times(db, plant, part_no)

    @router.put("/schedule/part-process-time", dependencies=deps)
    def part_process_time_save(body: PartTimeSave, db: Session = Depends(init_db)):
        return _guard(lambda: save_part_process_times(db, body), db)

    @router.get("/schedule/po-gantt/orders", dependencies=deps)
    def po_gantt_orders(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
        return list_open_orders(db, plant)

    @router.get("/schedule/po-gantt", dependencies=deps)
    def po_gantt(
        request: Request,
        production_order: Optional[List[str]] = Query(None, description="PO numbers to load; order = load priority"),
        plant: Optional[str] = Query(None),
        start_date: Optional[date] = Query(None, description="default: first working day on/after today"),
        time_source: str = Query("actual"),
        label_mode: str = Query("seq", description="'seq' = B1, B2... | 'po' = PO number"),
        show_holidays: bool = Query(True, description="send off days as flagged columns"),
        shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=20),
        db: Session = Depends(init_db),
    ):
        return _send(_run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start),
                     request, drop_for_page=True)

    @router.get("/schedule/po-gantt/export", dependencies=deps)
    def po_gantt_export(
        production_order: Optional[List[str]] = Query(None),
        plant: Optional[str] = Query(None),
        start_date: Optional[date] = Query(None),
        time_source: str = Query("actual"),
        label_mode: str = Query("seq"),
        show_holidays: bool = Query(True),
        shift_start: float = Query(DEFAULT_SHIFT_START, ge=0, le=20),
        db: Session = Depends(init_db),
    ):
        result = _run(db, production_order, plant, start_date, time_source, label_mode, show_holidays, shift_start)
        return StreamingResponse(
            io.BytesIO(build_po_gantt_xlsx(result)),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="po_gantt.xlsx"'},
        )

    @router.post("/schedule/plans", dependencies=deps)
    def plans_save(body: PlanSave, db: Session = Depends(init_db)):
        return _guard(lambda: save_plan(db, body), db)

    @router.get("/schedule/plans", dependencies=deps)
    def plans_list(plant: Optional[str] = Query(None), db: Session = Depends(init_db)):
        return list_plans(db, plant)

    @router.get("/schedule/plans/{plan_id}", dependencies=deps)
    def plans_get(plan_id: int, db: Session = Depends(init_db)):
        def go():
            p = _get_plan(db, plan_id)
            return {"plan": _plan_header(p), "snapshot": p.snapshot}
        return _guard(go)

    @router.put("/schedule/plans/{plan_id}/baseline", dependencies=deps)
    def plans_baseline(plan_id: int, db: Session = Depends(init_db)):
        return _guard(lambda: set_baseline(db, plan_id), db)

    @router.delete("/schedule/plans/{plan_id}", dependencies=deps)
    def plans_delete(plan_id: int, db: Session = Depends(init_db)):
        return _guard(lambda: delete_plan(db, plan_id), db)

    @router.get("/schedule/plans/{plan_id}/compare", dependencies=deps)
    def plans_compare(plan_id: int, request: Request, db: Session = Depends(init_db)):
        return _send(_guard(lambda: compare_plan(db, plan_id)), request)

    return router